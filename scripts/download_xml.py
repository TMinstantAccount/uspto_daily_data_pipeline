"""
Download latest USPTO XML file using their API
Self-Hosted Airflow with GCS Storage
"""
import requests
import logging
from datetime import datetime, timedelta
from google.cloud import storage
import os
import tempfile
from config.config import (
    USPTO_API_KEY, 
    USPTO_API_BASE_URL,
    GCS_BUCKET, 
    GCS_XML_PREFIX,
    GCP_PROJECT_ID
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_latest_file_info(target_date=None):
    """Query USPTO API to get latest available XML file"""
    if target_date is None:
        raise ValueError("target_date is required — must match the XML daily file date")
    
    from_date = target_date.strftime('%Y-%m-%d')
    to_date = target_date.strftime('%Y-%m-%d')
    
    url = USPTO_API_BASE_URL
    params = {
        'fileDataFromDate': from_date,
        'fileDataToDate': to_date,
        'includeFiles': 'true'
    }
    
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'x-api-key': USPTO_API_KEY
    }
    
    logger.info(f"Querying USPTO API for date: {from_date}")
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # USPTO API uses bulkDataProductBag structure
        if 'bulkDataProductBag' in data and len(data['bulkDataProductBag']) > 0:
            product = data['bulkDataProductBag'][0]
            file_bag = product.get('productFileBag', {})
            files = file_bag.get('fileDataBag', [])
            
            # Filter for Data type files only (not documentation)
            data_files = [f for f in files if f.get('fileTypeText') == 'Data']
            
            if data_files:
                file_info = data_files[0]
                logger.info(f"Found file: {file_info.get('fileName')}")
                logger.info(f"File size: {file_info.get('fileSize', 0):,} bytes")
                logger.info(f"File date: {file_info.get('fileDataFromDate')}")
                return file_info
            else:
                logger.warning(f"No data files found for date: {from_date}")
                return None
        else:
            logger.warning(f"No results returned from API for date: {from_date}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error querying USPTO API: {str(e)}")
        raise


def download_xml_file(file_info, local_path=None):
    """Download and extract XML file from USPTO (handles ZIP files)"""
    # USPTO uses fileDownloadURI
    download_url = file_info.get('fileDownloadURI') or file_info.get('fileDownloadUrl') or file_info.get('downloadUrl')
    file_name = file_info.get('fileName')
    
    if not download_url:
        raise ValueError("No download URL found in file info")
    
    if not file_name:
        file_name = f"apc{datetime.now().strftime('%Y%m%d')}.zip"
    
    if local_path is None:
        local_path = f"/tmp/{file_name}"
    
    logger.info(f"Downloading file: {file_name}")
    logger.info(f"Download URL: {download_url}")
    
    try:
        # Add API key to download headers
        download_headers = {
            'x-api-key': USPTO_API_KEY
        }
        
        response = requests.get(download_url, headers=download_headers, stream=True, timeout=300)
        response.raise_for_status()
        
        downloaded_size = 0
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024*1024):  # 1MB chunks
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    # Log progress every 10MB
                    if downloaded_size % (10*1024*1024) == 0:
                        logger.info(f"Downloaded: {downloaded_size / (1024*1024):.1f} MB")
        
        file_size = os.path.getsize(local_path)
        logger.info(f"Downloaded {file_name} ({file_size:,} bytes) to {local_path}")
        
        # If it's a ZIP file, extract it
        if file_name.endswith('.zip'):
            logger.info("Extracting ZIP file...")
            import zipfile
            import tempfile
            
            temp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(local_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
                file_list = zip_ref.namelist()
                logger.info(f"Extracted {len(file_list)} file(s)")
            
            # Find the XML file
            xml_files = [f for f in file_list if f.endswith('.xml')]
            if xml_files:
                xml_file = xml_files[0]
                xml_path = os.path.join(temp_dir, xml_file)
                logger.info(f"Found XML file: {xml_file}")
                
                # Remove the ZIP and return XML path
                os.remove(local_path)
                return xml_path
            else:
                raise ValueError("No XML file found in ZIP archive")
        
        return local_path
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading file: {str(e)}")
        raise


def upload_to_gcs(local_path, target_date=None):
    """Upload XML file to Google Cloud Storage with chunked resumable upload."""
    if target_date is None:
        raise ValueError("target_date is required — must match the XML daily file date")
    
    date_path = target_date.strftime('%Y/%m/%d')
    file_name = os.path.basename(local_path)
    gcs_path = f"{GCS_XML_PREFIX}/{date_path}/{file_name}"
    
    file_size = os.path.getsize(local_path)
    logger.info(f"Uploading to GCS: gs://{GCS_BUCKET}/{gcs_path} ({file_size / (1024*1024):.1f} MB)")
    
    try:
        storage_client = storage.Client(project=GCP_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET)
        blob = bucket.blob(gcs_path)
        blob.chunk_size = 10 * 1024 * 1024  # 10 MB chunks for resumable upload
        
        blob.upload_from_filename(local_path, timeout=600)
        
        logger.info(f"Upload complete: gs://{GCS_BUCKET}/{gcs_path}")
        
        return f"gs://{GCS_BUCKET}/{gcs_path}"
        
    except Exception as e:
        logger.error(f"Error uploading to GCS: {str(e)}")
        raise


def main(target_date=None, **kwargs):
    """Main function to download latest USPTO XML and upload to GCS"""
    logger.info("="*80)
    logger.info("USPTO XML Downloader - Starting")
    logger.info("="*80)
    
    # Get file information from API
    file_info = get_latest_file_info(target_date)
    
    if not file_info:
        raise ValueError("No XML file found for the target date")
    
    # Download file
    local_path = download_xml_file(file_info)
    
    # Upload to GCS
    gcs_path = upload_to_gcs(local_path, target_date)
    
    # Clean up local file
    if os.path.exists(local_path):
        os.remove(local_path)
        logger.info(f"Cleaned up local file: {local_path}")
    
    xml_file_date = file_info.get('fileDataFromDate')
    if not xml_file_date and target_date:
        xml_file_date = target_date.strftime('%Y-%m-%d')

    result = {
        'gcs_path': gcs_path,
        'file_name': file_info.get('fileName'),
        'file_size': file_info.get('fileSize'),
        'target_date': target_date.strftime('%Y-%m-%d') if target_date else None,
        'xml_file_date': xml_file_date,
    }
    
    logger.info("="*80)
    logger.info("Download Complete!")
    logger.info(f"GCS Path: {gcs_path}")
    logger.info("="*80)
    
    return result


if __name__ == "__main__":
    result = main()
    print(f"Result: {result}")
