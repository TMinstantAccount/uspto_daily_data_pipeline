"""
Merge parsed and scraped data into final output
Self-Hosted Airflow with GCS Storage
"""
import pandas as pd
import logging
from datetime import datetime, timedelta
from google.cloud import storage
import tempfile
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


def deduplicate_emails(email_list):
    """Remove duplicates and 'NOT FOUND' from email list."""
    if not email_list:
        return 'NOT FOUND'
    
    emails = []
    for item in email_list:
        if pd.isna(item) or item == 'NOT FOUND':
            continue
        if isinstance(item, str):
            emails.extend([e.strip() for e in item.split(',')])
    
    unique_emails = list(set([e for e in emails if e and e != 'NOT FOUND']))
    
    return ', '.join(unique_emails) if unique_emails else 'NOT FOUND'


def merge_datasets(parsed_csv_path, scraped_csv_path):
    """Merge parsed and scraped datasets"""
    logger.info("Loading datasets...")
    
    parsed_df = pd.read_csv(parsed_csv_path)
    scraped_df = pd.read_csv(scraped_csv_path)
    
    logger.info(f"Parsed records: {len(parsed_df)}")
    logger.info(f"Scraped records: {len(scraped_df)}")
    
    final_df = scraped_df.copy()
    
    logger.info("Deduplicating emails...")
    
    final_df['all_emails'] = final_df.apply(
        lambda row: deduplicate_emails([
            row.get('attorney_email', ''),
            row.get('correspondent_email', ''),
            row.get('all_emails_found', '')
        ]),
        axis=1
    )
    
    final_columns = [
        'serial_number',
        'filing_date',
        'status_code',
        'status_description',
        'attorney_name',
        'attorney_email',
        'correspondent_name',
        'correspondent_email',
        'all_emails',
        'prosecution_date',
        'prosecution_description',
        'url',
        'correspondent_address',
        'owner_name',
        'owner_address',
        'most_recent_status_date'
    ]
    
    available_columns = [col for col in final_columns if col in final_df.columns]
    final_df = final_df[available_columns]
    
    final_df = final_df.sort_values('filing_date', ascending=False)
    
    logger.info(f"Final merged records: {len(final_df)}")
    
    return final_df


def validate_data(df):
    """Perform data quality checks"""
    logger.info("Performing data quality checks...")
    
    total_records = len(df)
    
    metrics = {
        'total_records': total_records,
        'has_attorney_email': (df['attorney_email'] != 'NOT FOUND').sum(),
        'has_correspondent_email': (df['correspondent_email'] != 'NOT FOUND').sum(),
        'has_any_email': (df['all_emails'] != 'NOT FOUND').sum(),
        'has_prosecution_history': (df['prosecution_date'] != 'NOT FOUND').sum(),
        'completeness_rate': 0.0
    }
    
    if total_records > 0:
        metrics['completeness_rate'] = (metrics['has_any_email'] / total_records) * 100
    
    logger.info(f"Validation Results:")
    logger.info(f"  Total records: {metrics['total_records']}")
    logger.info(f"  Has attorney email: {metrics['has_attorney_email']} ({metrics['has_attorney_email']/total_records*100:.1f}%)")
    logger.info(f"  Has correspondent email: {metrics['has_correspondent_email']} ({metrics['has_correspondent_email']/total_records*100:.1f}%)")
    logger.info(f"  Has any email: {metrics['has_any_email']} ({metrics['completeness_rate']:.1f}%)")
    logger.info(f"  Has prosecution history: {metrics['has_prosecution_history']} ({metrics['has_prosecution_history']/total_records*100:.1f}%)")
    
    return metrics


def upload_to_gcs(local_path, target_date=None):
    """Upload final CSV to GCS."""
    if target_date is None:
        raise ValueError("target_date is required — must match the XML daily file date")

    date_str = target_date.strftime('%Y%m%d')
    file_name = f"final_trademarks_{date_str}.csv"

    date_path = target_date.strftime('%Y/%m/%d')
    gcs_path = f"{GCS_RESULT_PREFIX}/{date_path}/{file_name}"

    logger.info(f"Uploading final CSV to GCS: gs://{GCS_BUCKET}/{gcs_path}")

    storage_client = storage.Client(project=GCP_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)

    logger.info(f"Upload complete: gs://{GCS_BUCKET}/{gcs_path}")
    return f"gs://{GCS_BUCKET}/{gcs_path}"


def main(gcs_parsed_csv_path, gcs_scraped_csv_path, target_date=None, **kwargs):
    """Main function for Airflow task"""
    import os
    
    logger.info("="*80)
    logger.info("Data Merge - Starting")
    logger.info("="*80)

    parsed_local = download_csv_from_gcs(gcs_parsed_csv_path)
    scraped_local = download_csv_from_gcs(gcs_scraped_csv_path)

    try:
        final_df = merge_datasets(parsed_local, scraped_local)
        
        metrics = validate_data(final_df)
        
        temp_output = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        temp_output_path = temp_output.name
        temp_output.close()
        final_df.to_csv(temp_output_path, index=False, encoding='utf-8-sig')
        
        gcs_final_path = upload_to_gcs(temp_output_path, target_date)
        
        os.remove(temp_output_path)
        
        result = {
            'status': 'success',
            'gcs_final_path': gcs_final_path,
            'metrics': metrics
        }
        
        logger.info("="*80)
        logger.info("Merge Complete!")
        logger.info(f"Final output: {gcs_final_path}")
        logger.info("="*80)
        
        return result

    finally:
        for path in [parsed_local, scraped_local]:
            if os.path.exists(path):
                os.remove(path)
        logger.info("Cleaned up temporary files")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        parsed_path = sys.argv[1]
        scraped_path = sys.argv[2]
        result = main(parsed_path, scraped_path)
        print(f"Result: {result}")
    else:
        print("Usage: python merge_data.py <gcs_parsed_csv> <gcs_scraped_csv>")
