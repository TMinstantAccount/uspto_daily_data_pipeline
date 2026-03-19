"""
Configuration for USPTO Daily Pipeline - Self-Hosted Airflow with GCS Storage
"""
import os

# GCP Configuration (for storage only)
GCP_PROJECT_ID = "trademark-daily-pipeline"
GCS_BUCKET = "daily-file-staging"
GCS_XML_PREFIX = "daily_xml_file"
GCS_RESULT_PREFIX = "daily_final_result"

# Local temporary directory (for processing)
LOCAL_TEMP_DIR = "/tmp/uspto_pipeline"

# USPTO API Configuration
USPTO_API_KEY = os.getenv("USPTO_API_KEY", "YOUR_USPTO_API_KEY_HERE")
USPTO_API_BASE_URL = "https://api.uspto.gov/api/v1/datasets/products/trtdxfap"

# Filtering Criteria
TARGET_STATUS_CODES = ['416', '417', '641', '649', '807', '813']

# Scraping Configuration
SCRAPE_DELAY_SECONDS = 2.0
SCRAPE_BATCH_SIZE = 50
MAX_RETRIES = 3

# Notification Configuration
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "account@tminstant.com")
