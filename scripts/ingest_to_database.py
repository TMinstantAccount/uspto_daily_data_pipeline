"""
Ingest normalized email data into Azure SQL Database
Self-Hosted Airflow with GCS Storage
"""
import pandas as pd
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from google.cloud import storage
import tempfile
import sys
import os
scripts_dir = os.path.dirname(os.path.abspath(__file__))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from azure_sql_connection import AzureSQLConnection

from config.config import (
    GCS_BUCKET,
    GCS_RESULT_PREFIX,
    GCP_PROJECT_ID
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_CENTRAL_TZ = ZoneInfo("America/Chicago")


def _central_today() -> date:
    """Calendar date (YYYY-MM-DD) in America/Chicago for the current instant."""
    return datetime.now(_CENTRAL_TZ).date()


def download_csv_from_gcs(gcs_path):
    """Download CSV from GCS."""
    if gcs_path.startswith('gs://'):
        gcs_path = gcs_path[5:]

    parts = gcs_path.split('/', 1)
    bucket_name = parts[0]
    blob_path = parts[1] if len(parts) > 1 else ''

    logger.info(f"Downloading: gs://{bucket_name}/{blob_path}")

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    local_path = temp_file.name
    temp_file.close()

    storage_client = storage.Client(project=GCP_PROJECT_ID)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)

    return local_path


def get_db_connection_from_airflow_variables():
    """
    Get Azure SQL connection parameters from Airflow Variables.
    
    Expected Variables:
    - azure_sql_server: Server name (e.g., tminstant-sqlserver.database.windows.net)
    - azure_sql_database: Database name (e.g., TMinstantSales)
    - azure_sql_auth_method: "sql_server" or "azure_ad"
    - azure_sql_username: SQL Server username (for sql_server auth)
    - azure_sql_password: SQL Server password (for sql_server auth)
    - azure_sql_account: Azure AD account email (for azure_ad auth)
    
    Returns:
        AzureSQLConnection instance
    """
    from airflow.models import Variable
    
    try:
        server = Variable.get('azure_sql_server')
        database = Variable.get('azure_sql_database')
        auth_method = Variable.get('azure_sql_auth_method', default_var='sql_server')
    except Exception as e:
        raise ValueError(
            f"Missing required Airflow Variables for database connection. "
            f"Please set: azure_sql_server, azure_sql_database, azure_sql_auth_method. "
            f"Error: {e}"
        )
    
    if auth_method == 'sql_server':
        try:
            username = Variable.get('azure_sql_username')
            password = Variable.get('azure_sql_password')
        except Exception as e:
            raise ValueError(
                f"Missing SQL Server authentication variables. "
                f"Please set: azure_sql_username, azure_sql_password. "
                f"Error: {e}"
            )
        db_conn = AzureSQLConnection(
            server=server,
            database=database,
            auth_method='sql_server',
            username=username,
            password=password
        )
    elif auth_method == 'azure_ad':
        azure_account = Variable.get('azure_sql_account', default_var=None)
        db_conn = AzureSQLConnection(
            server=server,
            database=database,
            auth_method='azure_ad',
            azure_account=azure_account
        )
    else:
        raise ValueError(f"Unknown auth_method: {auth_method}. Must be 'sql_server' or 'azure_ad'")
    
    return db_conn


def check_duplicate(db_conn, serial_number, status_code, email_sent, refresh_date):
    """
    Check if this row (case + email_sent) already exists for this refresh_date.
    Duplicates: serial_number + status_code + email_sent + refresh_date.
    
    Returns:
        True if duplicate exists, False otherwise
    """
    query = """
    SELECT COUNT(*) as cnt
    FROM uspto_trademark_emails
    WHERE serial_number = ?
      AND status_code = ?
      AND email_sent = ?
      AND refresh_date = ?
    """
    try:
        results = db_conn.execute_query(
            query,
            (str(serial_number), str(status_code), str(email_sent), refresh_date)
        )
        return results[0]['cnt'] > 0
    except Exception as e:
        logger.error(f"Error checking duplicate: {e}")
        return False


def insert_batch_to_database(db_conn, df, refresh_date, created_at_ct=None):
    """
    Insert DataFrame rows into database, skipping duplicates.

    Args:
        db_conn: AzureSQLConnection instance
        df: DataFrame with normalized email data
        refresh_date: XML file date (duplicate key / business date)
        created_at_ct: DATE in Central time when ingest runs; defaults to now (Central calendar date)

    Returns:
        Dictionary with insertion statistics
    """
    if created_at_ct is None:
        created_at_ct = _central_today()
    logger.info(
        f"Preparing to insert {len(df)} rows — created_at (Central date at ingest): {created_at_ct}"
    )
    
    # Required columns for insertion
    required_cols = ['serial_number', 'status_code', 'email_sent', 'email_r_to_sent']
    
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Required column '{col}' not found in DataFrame")
    
    # Prepare data for insertion
    inserted_count = 0
    skipped_count = 0
    error_count = 0
    
    # Column mapping for database table
    db_columns = [
        'serial_number', 'status_code', 'email_sent', 'email_r_to_sent', 'refresh_date',
        'filing_date', 'status_description', 'attorney_name', 'attorney_email',
        'correspondent_name', 'correspondent_email', 'prosecution_date',
        'prosecution_description', 'url', 'correspondent_address',
        'owner_name', 'owner_address', 'most_recent_status_date',
        'created_at'
    ]
    
    # Columns from CSV plus created_at (not present in CSV)
    available_cols = [col for col in db_columns if col in df.columns or col == 'created_at']
    
    # Process in batches
    batch_size = 100
    total_batches = (len(df) + batch_size - 1) // batch_size
    
    for batch_idx in range(0, len(df), batch_size):
        batch_df = df.iloc[batch_idx:batch_idx + batch_size]
        current_batch = (batch_idx // batch_size) + 1
        
        logger.info(f"Processing batch {current_batch}/{total_batches} ({len(batch_df)} rows)...")
        
        for idx, row in batch_df.iterrows():
            try:
                serial_number = str(row['serial_number'])
                status_code = str(row['status_code'])
                email_sent = str(row['email_sent']) if pd.notna(row['email_sent']) else ''
                email_r_to_sent = str(row['email_r_to_sent']) if pd.notna(row['email_r_to_sent']) else ''
                
                # Skip if we already have this exact row for this refresh_date
                if check_duplicate(db_conn, serial_number, status_code, email_sent, refresh_date):
                    skipped_count += 1
                    continue
                
                # Prepare values
                values = []
                for col in available_cols:
                    if col == 'refresh_date':
                        values.append(refresh_date)
                    elif col == 'created_at':
                        values.append(created_at_ct)
                    elif col in ['filing_date', 'most_recent_status_date']:
                        value = row.get(col)
                        if pd.isna(value):
                            values.append(None)
                        elif isinstance(value, str):
                            try:
                                values.append(datetime.strptime(value, '%Y-%m-%d').date())
                            except Exception:
                                values.append(None)
                        else:
                            values.append(value)
                    else:
                        value = row.get(col)
                        if pd.isna(value):
                            values.append(None)
                        else:
                            values.append(str(value)[:1000] if len(str(value)) > 1000 else str(value))
                
                # Insert new row (PK includes refresh_date, so same case on a different day is a new row)
                columns_str = ', '.join(available_cols)
                placeholders = ', '.join(['?' for _ in available_cols])
                
                insert_query = f"""
                INSERT INTO uspto_trademark_emails ({columns_str})
                VALUES ({placeholders})
                """
                
                db_conn.execute_non_query(insert_query, tuple(values))
                inserted_count += 1
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error inserting row {idx}: {e}")
                continue
        
        logger.info(f"Batch {current_batch} complete: {inserted_count} inserted, {skipped_count} skipped, {error_count} errors")
    
    stats = {
        'total_rows': len(df),
        'inserted': inserted_count,
        'skipped_duplicates': skipped_count,
        'errors': error_count
    }
    
    logger.info("="*60)
    logger.info("Insertion Summary:")
    logger.info(f"  Total rows processed: {stats['total_rows']}")
    logger.info(f"  Successfully inserted: {stats['inserted']}")
    logger.info(f"  Skipped (duplicates): {stats['skipped_duplicates']}")
    logger.info(f"  Errors: {stats['errors']}")
    logger.info("="*60)
    
    return stats


def main(gcs_normalized_csv_path, target_date=None, **kwargs):
    """Main function for Airflow task"""
    import os
    
    logger.info("="*80)
    logger.info("Database Ingestion - Starting")
    logger.info("="*80)

    local_csv_path = download_csv_from_gcs(gcs_normalized_csv_path)
    
    if target_date is None:
        raise ValueError("target_date is required — must match the XML daily file date")
    refresh_date = target_date.date() if isinstance(target_date, datetime) else target_date

    db_conn = None
    
    try:
        # Get database connection
        logger.info("Connecting to Azure SQL Database...")
        try:
            db_conn = get_db_connection_from_airflow_variables()
            logger.info("Database connection object created successfully")
        except Exception as e:
            logger.error(f"Failed to create database connection object: {e}")
            raise Exception(f"Failed to create database connection: {e}")
        
        # Connect to database (will raise exception on failure)
        try:
            db_conn.connect()
            logger.info("Database connection established successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Azure SQL Database: {e}")
            raise Exception(f"Database connection failed: {e}")
        
        # Test connection (will raise exception on failure)
        try:
            db_conn.test_connection()
            logger.info("Database connection test passed")
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            raise Exception(f"Database connection test failed: {e}")
        
        # Load normalized CSV
        df = pd.read_csv(local_csv_path)
        logger.info(f"Loaded {len(df)} rows from normalized CSV")
        
        # Insert into database
        stats = insert_batch_to_database(db_conn, df, refresh_date)
        
        result = {
            'status': 'success',
            'refresh_date': str(refresh_date),
            'total_rows': stats['total_rows'],
            'inserted': stats['inserted'],
            'skipped_duplicates': stats['skipped_duplicates'],
            'errors': stats['errors']
        }
        
        logger.info("="*80)
        logger.info("Database Ingestion Complete!")
        logger.info(f"Rows inserted: {result['inserted']}")
        logger.info(f"Rows skipped (duplicates): {result['skipped_duplicates']}")
        logger.info(f"Errors: {result['errors']}")
        logger.info("="*80)
        
        return result

    except Exception as e:
        logger.error(f"Database ingestion failed: {e}")
        raise

    finally:
        if db_conn:
            db_conn.close()
        if os.path.exists(local_csv_path):
            os.remove(local_csv_path)
            logger.info("Cleaned up local CSV file")


def write_pipeline_summary(
    data_fetch_date,
    rows_processed,
    status,
    dag_run_id=None,
    error_message=None,
):
    """
    MERGE a single summary row into dbo.uspto_pipeline_daily_summary.

    Always uses MERGE so a re-run on the same day overwrites the previous row
    rather than raising a UNIQUE-constraint error.

    Args:
        data_fetch_date : date | str  – the XML logical date (e.g. 2026-03-05)
        rows_processed  : int         – total rows processed by the ingest step
        status          : str         – 'SUCCESS' | 'FAILED' | 'PARTIAL'
        dag_run_id      : str | None  – Airflow dag_run_id for traceability
        error_message   : str | None  – first 2 000 chars of any error detail

    ended_at is the Central (America/Chicago) calendar date when this summary runs,
    stored as DATE (YYYY-MM-DD), not the XML file date.
    """
    if isinstance(data_fetch_date, str):
        data_fetch_date = datetime.strptime(data_fetch_date, '%Y-%m-%d').date()

    ended_at = _central_today()

    error_message_trimmed = (error_message or '')[:2000] or None

    merge_query = """
    MERGE dbo.uspto_pipeline_daily_summary AS tgt
    USING (SELECT ? AS data_fetch_date) AS src
        ON tgt.data_fetch_date = src.data_fetch_date
    WHEN MATCHED THEN
        UPDATE SET
            rows_processed            = ?,
            ended_at                  = ?,
            pipeline_execution_status = ?,
            dag_run_id                = ?,
            error_message             = ?
    WHEN NOT MATCHED THEN
        INSERT (data_fetch_date, rows_processed, ended_at,
                pipeline_execution_status, dag_run_id, error_message)
        VALUES (?, ?, ?, ?, ?, ?);
    """
    params = (
        # USING clause
        data_fetch_date,
        # UPDATE SET
        rows_processed, ended_at, status, dag_run_id, error_message_trimmed,
        # INSERT VALUES
        data_fetch_date, rows_processed, ended_at, status, dag_run_id, error_message_trimmed,
    )

    db_conn = None
    try:
        db_conn = get_db_connection_from_airflow_variables()
        db_conn.connect()
        db_conn.execute_non_query(merge_query, params)
        logger.info(
            f"Pipeline summary written — data_fetch_date={data_fetch_date} "
            f"rows={rows_processed} status={status} ended_at={ended_at} (Central calendar date)"
        )
    except Exception as e:
        logger.error(f"Failed to write pipeline summary: {e}")
        raise
    finally:
        if db_conn:
            db_conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_gcs_path = sys.argv[1]
        result = main(test_gcs_path)
        print(f"Result: {result}")
    else:
        print("Usage: python ingest_to_database.py <gcs_normalized_csv_path>")

