"""
Parse USPTO XML file and extract trademark data
Self-Hosted Airflow with GCS Storage
"""
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime, timedelta
import logging
from google.cloud import storage
import tempfile
from config.config import (
    TARGET_STATUS_CODES,
    GCS_BUCKET,
    GCS_RESULT_PREFIX,
    GCP_PROJECT_ID
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_from_gcs(gcs_path):
    """Download XML file from GCS to local temp file"""
    if gcs_path.startswith('gs://'):
        gcs_path = gcs_path[5:]
    
    parts = gcs_path.split('/', 1)
    bucket_name = parts[0]
    blob_path = parts[1] if len(parts) > 1 else ''
    
    logger.info(f"Downloading from GCS: gs://{bucket_name}/{blob_path}")
    
    temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.xml', delete=False)
    local_path = temp_file.name
    
    try:
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_path)
        blob.download_to_filename(local_path)
        
        logger.info(f"Downloaded to: {local_path}")
        return local_path
        
    except Exception as e:
        logger.error(f"Error downloading from GCS: {str(e)}")
        raise


def parse_xml_file(xml_path):
    """
    Parse XML file and extract trademark data.

    Args:
        xml_path: Path to XML file
    """
    logger.info("="*80)
    logger.info("USPTO Trademark XML Parser")
    logger.info("="*80)
    logger.info(f"Filtering for status codes: {', '.join(TARGET_STATUS_CODES)}")
    logger.info(f"\nParsing XML file: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    all_cases = root.findall('.//case-file')
    logger.info(f"Total cases in file: {len(all_cases)}")

    extracted_data = []
    filtered_count = 0
    processed_count = 0

    for case in all_cases:
        processed_count += 1

        if processed_count % 5000 == 0:
            logger.info(f"Processed {processed_count}/{len(all_cases)} cases... Found {filtered_count} matching cases")

        header = case.find('case-file-header')
        if header is None:
            continue

        status_code_elem = header.find('status-code')
        if status_code_elem is None:
            continue

        status_code = status_code_elem.text

        if status_code not in TARGET_STATUS_CODES:
            continue

        filing_date_elem = header.find('filing-date')
        if filing_date_elem is None or not filing_date_elem.text:
            continue

        filing_date_str = filing_date_elem.text
        try:
            filing_date_obj = datetime.strptime(filing_date_str, '%Y%m%d')
        except (ValueError, TypeError):
            continue

        filtered_count += 1

        serial_elem = case.find('serial-number')
        serial_number = serial_elem.text if serial_elem is not None else 'NOT FOUND'

        attorney_elem = header.find('attorney-name')
        attorney_name = attorney_elem.text if attorney_elem is not None else 'NOT FOUND'

        correspondent = case.find('correspondent')
        correspondent_name = 'NOT FOUND'
        correspondent_address = 'NOT FOUND'
        if correspondent is not None:
            addr1 = correspondent.find('address-1')
            correspondent_name = addr1.text if addr1 is not None else 'NOT FOUND'

            address_parts = []
            for addr in [correspondent.find('address-2'), correspondent.find('address-3'), correspondent.find('address-4')]:
                if addr is not None and addr.text and addr.text.strip():
                    address_parts.append(addr.text.strip())
            correspondent_address = ', '.join(address_parts) if address_parts else 'NOT FOUND'

        owners = case.findall('case-file-owners/case-file-owner')
        owner_name = 'NOT FOUND'
        owner_address = 'NOT FOUND'

        if owners and len(owners) > 0:
            owner = None
            for o in owners:
                party_type = o.find('party-type')
                if party_type is not None and party_type.text == '10':
                    owner = o
                    break

            if owner is None:
                owner = owners[0]

            party_name = owner.find('party-name')
            owner_name = party_name.text if party_name is not None else 'NOT FOUND'

            address_parts = []
            for elem in [owner.find('address-1'), owner.find('address-2'), owner.find('city'), 
                        owner.find('country'), owner.find('postcode')]:
                if elem is not None and elem.text and elem.text.strip():
                    address_parts.append(elem.text.strip())
            owner_address = ', '.join(address_parts) if address_parts else 'NOT FOUND'

        events = case.findall('case-file-event-statements/case-file-event-statement')
        most_recent_date = 'NOT FOUND'
        most_recent_description = 'NOT FOUND'

        if events and len(events) > 0:
            latest_event = events[-1]
            date_elem = latest_event.find('date')
            desc_elem = latest_event.find('description-text')

            if date_elem is not None and date_elem.text:
                try:
                    date_obj = datetime.strptime(date_elem.text, '%Y%m%d')
                    most_recent_date = date_obj.strftime('%Y-%m-%d')
                except:
                    most_recent_date = date_elem.text

            most_recent_description = desc_elem.text if desc_elem is not None else 'NOT FOUND'

        url = f"https://tsdr.uspto.gov/statusview/sn{serial_number}"
        formatted_filing_date = filing_date_obj.strftime('%Y-%m-%d')

        extracted_data.append({
            'serial_number': serial_number,
            'url': url,
            'filing_date': formatted_filing_date,
            'status_code': status_code,
            'most_recent_status_date': most_recent_date,
            'status_description': most_recent_description,
            'attorney_name': attorney_name,
            'correspondent_name': correspondent_name,
            'correspondent_address': correspondent_address,
            'owner_name': owner_name,
            'owner_address': owner_address
        })

    logger.info(f"\nProcessing complete!")
    logger.info(f"Total cases processed: {processed_count}")
    logger.info(f"Cases matching filters: {filtered_count}")

    if extracted_data:
        df = pd.DataFrame(extracted_data)
        logger.info(f"Total records extracted: {len(df)}")
        return df
    else:
        logger.warning("No cases found matching the specified criteria!")
        return pd.DataFrame()


def upload_csv_to_gcs(df, target_date=None):
    """Upload parsed DataFrame to GCS as CSV"""
    if target_date is None:
        raise ValueError("target_date is required — must match the XML daily file date")
    
    date_str = target_date.strftime('%Y%m%d')
    file_name = f"parsed_trademarks_{date_str}.csv"
    
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    temp_path = temp_file.name
    temp_file.close()
    
    df.to_csv(temp_path, index=False, encoding='utf-8-sig')
    logger.info(f"Saved CSV to temp file: {temp_path}")
    
    date_path = target_date.strftime('%Y/%m/%d')
    gcs_path = f"{GCS_RESULT_PREFIX}/{date_path}/{file_name}"
    
    logger.info(f"Uploading to GCS: gs://{GCS_BUCKET}/{gcs_path}")
    
    try:
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET)
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(temp_path)
        
        logger.info(f"Upload complete: gs://{GCS_BUCKET}/{gcs_path}")
        
        import os
        os.remove(temp_path)
        
        return f"gs://{GCS_BUCKET}/{gcs_path}"
        
    except Exception as e:
        logger.error(f"Error uploading CSV to GCS: {str(e)}")
        raise


def main(gcs_xml_path, target_date=None, **kwargs):
    """
    Main function for Airflow task.

    Args:
        gcs_xml_path: GCS path to XML file
        target_date: Target date for output naming
    """
    import os
    
    logger.info("="*80)
    logger.info("XML Parser - Starting")
    logger.info("="*80)
    
    local_xml_path = download_from_gcs(gcs_xml_path)
    
    try:
        df = parse_xml_file(local_xml_path)
        
        if df.empty:
            logger.warning("No data extracted from XML")
            return {'status': 'no_data', 'record_count': 0}
        
        gcs_csv_path = upload_csv_to_gcs(df, target_date)
        
        result = {
            'status': 'success',
            'gcs_csv_path': gcs_csv_path,
            'record_count': len(df),
            'status_breakdown': df['status_code'].value_counts().to_dict()
        }
        
        logger.info("="*80)
        logger.info("Parsing Complete!")
        logger.info(f"Records extracted: {len(df)}")
        logger.info(f"Output CSV: {gcs_csv_path}")
        logger.info("="*80)
        
        return result
        
    finally:
        if os.path.exists(local_xml_path):
            os.remove(local_xml_path)
            logger.info(f"Cleaned up local XML file")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_gcs_path = sys.argv[1]
        result = main(test_gcs_path)
        print(f"Result: {result}")
    else:
        print("Usage: python parse_xml.py <gcs_path>")
