"""
Ingest normalized email data into Azure SQL Database
Self-Hosted Airflow with GCS Storage
"""
import pandas as pd
import logging
from datetime import datetime, timedelta
from google.cloud import storage
import tempfile
import sys
import os
from typing import Optional

# Import azure_sql_connection from scripts directory
# Add scripts directory to path to ensure azure_sql_connection can be found
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


def insert_batch_to_database(db_conn, df, refresh_date):
    """
    Insert DataFrame rows into database, skipping duplicates.
    
    Args:
        db_conn: AzureSQLConnection instance
        df: DataFrame with normalized email data
        refresh_date: Refresh date to filter duplicates
        
    Returns:
        Dictionary with insertion statistics
    """
    logger.info(f"Preparing to insert {len(df)} rows into database...")
    
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
        'owner_name', 'owner_address', 'most_recent_status_date'
    ]
    
    # Get available columns from DataFrame
    available_cols = [col for col in db_columns if col in df.columns]
    
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
                
                # Skip if we already have this row (case + email_sent) for this refresh_date
                if check_duplicate(db_conn, serial_number, status_code, email_sent, refresh_date):
                    skipped_count += 1
                    continue
                
                # Prepare values
                values = []
                for col in available_cols:
                    value = row.get(col)
                    if pd.isna(value):
                        values.append(None)
                    elif col == 'refresh_date':
                        values.append(refresh_date)
                    elif col in ['filing_date', 'most_recent_status_date']:
                        # Convert date strings to date objects
                        if isinstance(value, str):
                            try:
                                values.append(datetime.strptime(value, '%Y-%m-%d').date())
                            except:
                                values.append(None)
                        else:
                            values.append(value)
                    else:
                        values.append(str(value)[:1000] if len(str(value)) > 1000 else str(value))
                
                # Check if record exists (same serial_number + status_code + email_sent)
                check_existing_query = """
                SELECT COUNT(*) as cnt
                FROM uspto_trademark_emails
                WHERE serial_number = ? AND status_code = ? AND email_sent = ?
                """
                existing_results = db_conn.execute_query(
                    check_existing_query,
                    (str(serial_number), str(status_code), email_sent)
                )
                
                if existing_results[0]['cnt'] > 0:
                    # Record exists (same row), update it
                    update_cols = [col for col in available_cols if col not in ['serial_number', 'status_code', 'email_sent']]
                    set_clause = ', '.join([f"{col} = ?" for col in update_cols])
                    
                    update_query = f"""
                    UPDATE uspto_trademark_emails
                    SET {set_clause}
                    WHERE serial_number = ? AND status_code = ? AND email_sent = ?
                    """
                    
                    update_values = []
                    for col in update_cols:
                        idx = available_cols.index(col)
                        update_values.append(values[idx])
                    update_values.append(str(serial_number))
                    update_values.append(str(status_code))
                    update_values.append(email_sent)
                    
                    db_conn.execute_non_query(update_query, tuple(update_values))
                    inserted_count += 1  # Count as inserted (actually updated)
                else:
                    # New record, insert it
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
    """
    from zoneinfo import ZoneInfo

    _central = ZoneInfo("America/Chicago")
    end_time_ct = datetime.now(_central).replace(tzinfo=None)  # naive Central Time for SQL Server

    if isinstance(data_fetch_date, str):
        data_fetch_date = datetime.strptime(data_fetch_date, '%Y-%m-%d').date()

    error_message_trimmed = (error_message or '')[:2000] or None

    merge_query = """
    MERGE dbo.uspto_pipeline_daily_summary AS tgt
    USING (SELECT ? AS data_fetch_date) AS src
        ON tgt.data_fetch_date = src.data_fetch_date
    WHEN MATCHED THEN
        UPDATE SET
            rows_processed            = ?,
            end_time_ct               = ?,
            pipeline_execution_status = ?,
            dag_run_id                = ?,
            error_message             = ?
    WHEN NOT MATCHED THEN
        INSERT (data_fetch_date, rows_processed, end_time_ct,
                pipeline_execution_status, dag_run_id, error_message)
        VALUES (?, ?, ?, ?, ?, ?);
    """
    params = (
        # USING clause
        data_fetch_date,
        # UPDATE SET
        rows_processed, end_time_ct, status, dag_run_id, error_message_trimmed,
        # INSERT VALUES
        data_fetch_date, rows_processed, end_time_ct, status, dag_run_id, error_message_trimmed,
    )

    db_conn = None
    try:
        db_conn = get_db_connection_from_airflow_variables()
        db_conn.connect()
        db_conn.execute_non_query(merge_query, params)
        logger.info(
            f"Pipeline summary written — date={data_fetch_date} "
            f"rows={rows_processed} status={status} "
            f"end_time_ct={end_time_ct.strftime('%Y-%m-%d %H:%M:%S')} CT"
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

