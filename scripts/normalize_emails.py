"""
Normalize emails: One row per email per case with email_sent (single) and email_r_to_sent (full list).
Self-Hosted Airflow with GCS Storage
Output: serial_number | status_code | email_sent | email_r_to_sent | ...
e.g. 1111 | 641 | email1 | email1,email2,email3 | ...
Removes "email notification" from status_description.
"""
import pandas as pd
import logging
from datetime import datetime, timedelta
from google.cloud import storage
import tempfile
import re
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


def split_emails(email_string):
    """Split comma-separated emails into a list, handling various formats."""
    if pd.isna(email_string) or email_string == 'NOT FOUND' or not email_string:
        return []
    
    # Remove extra whitespace and split by comma
    emails = [e.strip() for e in str(email_string).split(',')]
    
    # Filter out empty strings and 'NOT FOUND'
    emails = [e for e in emails if e and e != 'NOT FOUND']
    
    # Validate email format using regex
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    valid_emails = []
    for email in emails:
        if re.match(email_pattern, email):
            valid_emails.append(email)
    
    return valid_emails


def _remove_email_notification(text):
    """Remove 'email notification' from text (case-insensitive), collapse spaces."""
    if pd.isna(text) or not isinstance(text, str):
        return text
    cleaned = re.sub(r'\bemail\s+notification\b', '', text, flags=re.IGNORECASE)
    return ' '.join(cleaned.split()).strip()


def normalize_emails(df, refresh_date):
    """
    One row per email per case: email_sent = single email for this row, email_r_to_sent = full list.
    Removes "email notification" from status_description.
    
    Returns:
        DataFrame: serial_number | status_code | email_sent | email_r_to_sent | refresh_date | ...
    """
    logger.info("Normalizing emails: one row per email, email_sent (single) + email_r_to_sent (full list)...")
    
    if 'serial_number' not in df.columns:
        raise ValueError("serial_number column not found in DataFrame")
    if 'all_emails' not in df.columns:
        raise ValueError("all_emails column not found in DataFrame")
    
    normalized_df = df.copy()
    if 'status_description' in normalized_df.columns:
        normalized_df['status_description'] = normalized_df['status_description'].apply(
            _remove_email_notification
        )
    
    def combine_emails(series):
        all_emails = []
        for v in series:
            if pd.notna(v) and v != 'NOT FOUND' and v:
                all_emails.extend(split_emails(v))
        unique = list(dict.fromkeys(all_emails))
        return ', '.join(unique) if unique else ''
    
    agg_dict = {col: (combine_emails if col == 'all_emails' else 'first') for col in normalized_df.columns if col != 'serial_number'}
    normalized_df = normalized_df.groupby('serial_number', as_index=False).agg(agg_dict)
    
    # Full comma-separated list per case
    normalized_df['email_r_to_sent'] = normalized_df['all_emails'].apply(
        lambda x: x if (pd.notna(x) and x != 'NOT FOUND' and x) else ''
    )
    normalized_df['refresh_date'] = refresh_date
    
    # Explode: one row per email; the exploded value is the single email for that row
    email_lists = normalized_df['email_r_to_sent'].apply(
        lambda s: split_emails(s) if (s and s != 'NOT FOUND') else ['']
    )
    normalized_df['_email_list'] = email_lists
    normalized_df = normalized_df.explode('_email_list', ignore_index=True)
    # Single email for this row (exploded value); email_r_to_sent stays the full list
    normalized_df['email_sent'] = normalized_df['_email_list'].astype(str).str.strip()
    normalized_df = normalized_df.drop(columns=['_email_list'])
    
    # Column order: email_sent, email_r_to_sent, refresh_date after status_code
    cols = [c for c in normalized_df.columns if c not in ('email_r_to_sent', 'refresh_date', 'email_sent', 'all_emails')]
    if 'status_code' in cols:
        idx = cols.index('status_code') + 1
        cols.insert(idx, 'email_sent')
        cols.insert(idx + 1, 'email_r_to_sent')
        cols.insert(idx + 2, 'refresh_date')
    else:
        cols.insert(0, 'email_sent')
        cols.insert(1, 'email_r_to_sent')
        cols.insert(2, 'refresh_date')
    normalized_df = normalized_df[cols]
    
    logger.info(f"Normalization complete:")
    logger.info(f"  Rows (one per email per case): {len(normalized_df)}")
    logger.info(f"  Refresh date: {refresh_date}")
    
    return normalized_df


def upload_to_gcs(local_path, target_date=None):
    """Upload normalized CSV to GCS."""
    if target_date is None:
        raise ValueError("target_date is required — must match the XML daily file date")

    date_str = target_date.strftime('%Y%m%d')
    file_name = f"normalized_emails_{date_str}.csv"

    date_path = target_date.strftime('%Y/%m/%d')
    gcs_path = f"{GCS_RESULT_PREFIX}/{date_path}/{file_name}"

    logger.info(f"Uploading normalized CSV to GCS: gs://{GCS_BUCKET}/{gcs_path}")

    storage_client = storage.Client(project=GCP_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)

    logger.info(f"Upload complete: gs://{GCS_BUCKET}/{gcs_path}")
    return f"gs://{GCS_BUCKET}/{gcs_path}"


def main(gcs_final_csv_path, target_date=None, **kwargs):
    """Main function for Airflow task"""
    import os
    
    logger.info("="*80)
    logger.info("Email Normalization - Starting")
    logger.info("="*80)

    local_csv_path = download_csv_from_gcs(gcs_final_csv_path)
    
    if target_date is None:
        raise ValueError("target_date is required — must match the XML daily file date")
    refresh_date = target_date.date() if isinstance(target_date, datetime) else target_date

    try:
        df = pd.read_csv(local_csv_path)
        logger.info(f"Loaded {len(df)} rows from CSV")
        
        normalized_df = normalize_emails(df, refresh_date)
        
        temp_output = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        temp_output_path = temp_output.name
        temp_output.close()
        normalized_df.to_csv(temp_output_path, index=False, encoding='utf-8-sig')
        
        gcs_output_path = upload_to_gcs(temp_output_path, target_date)
        
        os.remove(temp_output_path)
        
        result = {
            'status': 'success',
            'gcs_csv_path': gcs_output_path,
            'input_rows': len(df),
            'output_rows': len(normalized_df),
            'total_emails': len(normalized_df),
            'refresh_date': str(refresh_date)
        }
        
        logger.info("="*80)
        logger.info("Normalization Complete!")
        logger.info(f"Total rows: {result['output_rows']}")
        logger.info(f"Total emails found: {result['total_emails']}")
        logger.info(f"Refresh date: {result['refresh_date']}")
        logger.info(f"Output CSV: {gcs_output_path}")
        logger.info("="*80)
        
        return result

    finally:
        if os.path.exists(local_csv_path):
            os.remove(local_csv_path)
            logger.info("Cleaned up local CSV file")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_gcs_path = sys.argv[1]
        result = main(test_gcs_path)
        print(f"Result: {result}")
    else:
        print("Usage: python normalize_emails.py <gcs_final_csv_path>")

