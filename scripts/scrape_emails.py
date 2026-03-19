"""
Scrape attorney and correspondent emails from USPTO trademark pages
Self-Hosted Airflow with GCS Storage
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import logging
from datetime import datetime, timedelta
from google.cloud import storage
import tempfile
from typing import Optional, Dict
from config.config import (
    SCRAPE_DELAY_SECONDS,
    MAX_RETRIES,
    GCS_BUCKET,
    GCS_RESULT_PREFIX,
    GCP_PROJECT_ID
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class USPTOEmailScraper:
    """Scraper for extracting email addresses from USPTO trademark pages."""

    def __init__(self, delay: float = SCRAPE_DELAY_SECONDS):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })

    def extract_emails(self, text: str) -> list:
        """Extract email addresses from text using regex."""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        return list(set(emails))

    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse a date string into a datetime object."""
        date_str = date_str.strip()
        date_str_clean = re.sub(r'([A-Z][a-z]{2})\.', r'\1', date_str)

        date_formats = [
            '%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y',
            '%B %d, %Y', '%b %d, %Y', '%Y%m%d'
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str_clean, fmt)
            except ValueError:
                continue
        return None

    def extract_prosecution_history(self, soup: BeautifulSoup) -> tuple:
        """Extract the most recent prosecution history date and description."""
        most_recent_date = None
        most_recent_description = None
        latest_datetime = None

        try:
            headings = soup.find_all('h2')
            for heading in headings:
                if 'Prosecution History' in heading.get_text().strip():
                    parent_div = heading.find_parent('div', class_='expand_wrapper')
                    if parent_div:
                        toggle_div = parent_div.find('div', class_='toggle_container')
                        if toggle_div:
                            table = toggle_div.find('table')
                            if table:
                                rows = table.find_all('tr')
                                for row in rows:
                                    if row.find('strong') or row.find('th'):
                                        continue
                                    cells = row.find_all('td')
                                    if len(cells) >= 2:
                                        date_cell = cells[0].get_text().strip()
                                        desc_cell = cells[1].get_text().strip()
                                        parsed_date = self.parse_date(date_cell)
                                        if parsed_date:
                                            if latest_datetime is None or parsed_date > latest_datetime:
                                                latest_datetime = parsed_date
                                                most_recent_date = date_cell
                                                most_recent_description = desc_cell
                                break

            if not most_recent_date:
                tables = soup.find_all('table')
                for table in tables:
                    header_row = table.find('tr')
                    if header_row:
                        header_text = header_row.get_text().lower()
                        if 'date' in header_text and 'description' in header_text:
                            rows = table.find_all('tr')[1:]
                            for row in rows:
                                cells = row.find_all('td')
                                if len(cells) >= 2:
                                    date_cell = cells[0].get_text().strip()
                                    desc_cell = cells[1].get_text().strip()
                                    parsed_date = self.parse_date(date_cell)
                                    if parsed_date:
                                        if latest_datetime is None or parsed_date > latest_datetime:
                                            latest_datetime = parsed_date
                                            most_recent_date = date_cell
                                            most_recent_description = desc_cell

        except Exception as e:
            logger.error(f"Error extracting prosecution history: {str(e)}")

        return (most_recent_date or 'NOT FOUND', most_recent_description or 'NOT FOUND')

    def scrape_trademark_page(self, url: str) -> Dict:
        """Scrape a single trademark page for email addresses."""
        result = {
            'attorney_email': 'NOT FOUND',
            'correspondent_email': 'NOT FOUND',
            'all_emails': '',
            'prosecution_date': 'NOT FOUND',
            'prosecution_description': 'NOT FOUND',
            'error': None
        }

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Scraping: {url} (attempt {attempt + 1}/{MAX_RETRIES})")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'lxml')

                for label_div in soup.find_all('div', class_='key'):
                    label_text = label_div.get_text().strip()
                    value_div = label_div.find_next_sibling('div')
                    if not value_div:
                        continue
                    value_text = value_div.get_text().strip()

                    if 'Attorney Primary Email Address' in label_text:
                        result['attorney_email'] = value_text if value_text else 'NOT FOUND'
                    elif 'Correspondent e-mail' in label_text and 'Authorized' not in label_text:
                        result['correspondent_email'] = value_text.replace('\n', ', ') if value_text else 'NOT FOUND'

                page_text = soup.get_text()
                all_emails = self.extract_emails(page_text)
                result['all_emails'] = ', '.join(all_emails)

                prosecution_date, prosecution_desc = self.extract_prosecution_history(soup)
                result['prosecution_date'] = prosecution_date
                result['prosecution_description'] = prosecution_desc

                break

            except requests.exceptions.RequestException as e:
                error_msg = f"Request error: {str(e)}"
                logger.error(error_msg)
                result['error'] = error_msg
                if attempt < MAX_RETRIES - 1:
                    time.sleep(self.delay * (attempt + 1))
                    continue
                else:
                    break
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error(error_msg)
                result['error'] = error_msg
                break

        time.sleep(self.delay)
        return result


def download_csv_from_gcs(gcs_path):
    """Download CSV from GCS to local temp file."""
    if gcs_path.startswith('gs://'):
        gcs_path = gcs_path[5:]

    parts = gcs_path.split('/', 1)
    bucket_name = parts[0]
    blob_path = parts[1] if len(parts) > 1 else ''

    logger.info(f"Downloading CSV from GCS: gs://{bucket_name}/{blob_path}")

    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
    local_path = temp_file.name
    temp_file.close()

    storage_client = storage.Client(project=GCP_PROJECT_ID)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)

    logger.info(f"Downloaded to: {local_path}")
    return local_path


def upload_csv_to_gcs(local_path, target_date=None):
    """Upload CSV to GCS."""
    if target_date is None:
        raise ValueError("target_date is required — must match the XML daily file date")

    date_str = target_date.strftime('%Y%m%d')
    file_name = f"scraped_trademarks_{date_str}.csv"

    date_path = target_date.strftime('%Y/%m/%d')
    gcs_path = f"{GCS_RESULT_PREFIX}/{date_path}/{file_name}"

    logger.info(f"Uploading to GCS: gs://{GCS_BUCKET}/{gcs_path}")

    storage_client = storage.Client(project=GCP_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(local_path)

    logger.info(f"Upload complete: gs://{GCS_BUCKET}/{gcs_path}")
    return f"gs://{GCS_BUCKET}/{gcs_path}"


def main(gcs_parsed_csv_path, target_date=None, **kwargs):
    """Main function for Airflow task.

    Args:
        gcs_parsed_csv_path: Path to parsed CSV in GCS
        target_date: Target date for processing
    """
    import os
    
    logger.info("="*80)
    logger.info("Email Scraper - Starting")
    logger.info("="*80)

    local_csv_path = download_csv_from_gcs(gcs_parsed_csv_path)

    try:
        df = pd.read_csv(local_csv_path)
        total = len(df)
        logger.info(f"Processing {total} URLs")

        df['attorney_email'] = 'NOT FOUND'
        df['correspondent_email'] = 'NOT FOUND'
        df['all_emails_found'] = ''
        df['prosecution_date'] = 'NOT FOUND'
        df['prosecution_description'] = 'NOT FOUND'
        df['scrape_error'] = None

        scraper = USPTOEmailScraper()
        successful = 0
        failed = 0

        for idx, row in df.iterrows():
            if (idx + 1) % 10 == 0:
                logger.info(f"Progress: {idx + 1}/{total} ({(idx + 1) / total * 100:.1f}%)")

            result = scraper.scrape_trademark_page(row['url'])

            df.at[idx, 'attorney_email'] = result['attorney_email']
            df.at[idx, 'correspondent_email'] = result['correspondent_email']
            df.at[idx, 'all_emails_found'] = result['all_emails']
            df.at[idx, 'prosecution_date'] = result['prosecution_date']
            df.at[idx, 'prosecution_description'] = result['prosecution_description']
            df.at[idx, 'scrape_error'] = result['error']

            if result['error'] is None:
                successful += 1
            else:
                failed += 1

        temp_output = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        temp_output_path = temp_output.name
        temp_output.close()
        df.to_csv(temp_output_path, index=False, encoding='utf-8-sig')

        gcs_output_path = upload_csv_to_gcs(temp_output_path, target_date)

        os.remove(temp_output_path)

        result = {
            'status': 'success',
            'gcs_csv_path': gcs_output_path,
            'total_urls': total,
            'successful': successful,
            'failed': failed,
            'success_rate': f"{(successful / total * 100):.1f}%" if total > 0 else "0%"
        }

        logger.info("="*80)
        logger.info("Scraping Complete!")
        logger.info(f"Successful: {successful}/{total}")
        logger.info(f"Failed: {failed}/{total}")
        logger.info(f"Output CSV: {gcs_output_path}")
        logger.info("="*80)

        return result

    finally:
        if os.path.exists(local_csv_path):
            os.remove(local_csv_path)
            logger.info(f"Cleaned up local CSV file")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_gcs_path = sys.argv[1]
        result = main(test_gcs_path)
        print(f"Result: {result}")
    else:
        print("Usage: python scrape_emails.py <gcs_csv_path>")
