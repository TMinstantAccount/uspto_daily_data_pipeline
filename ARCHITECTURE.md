# USPTO Daily Pipeline - Architecture Document

## System Overview

The USPTO Daily Trademark Pipeline is an automated data extraction and processing system built on Google Cloud Platform (GCP) using Apache Airflow for orchestration.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Google Cloud Platform                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Cloud Scheduler (Daily 2 AM EST)                          │  │
│  └────────────────────┬──────────────────────────────────────┘  │
│                       │                                          │
│                       ▼                                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Cloud Composer (Managed Airflow)                          │  │
│  │ ┌─────────────────────────────────────────────────────┐  │  │
│  │ │  DAG: uspto_daily_trademark_pipeline                │  │  │
│  │ │                                                       │  │  │
│  │ │  ┌──────────────────────────────────────────┐       │  │  │
│  │ │  │ Task 1: Download XML from USPTO API      │       │  │  │
│  │ │  │ - Fetch daily XML file (by file date)     │       │  │  │
│  │ │  │ - Upload to GCS: daily_xml_file/         │       │  │  │
│  │ │  └─────────┬────────────────────────────────┘       │  │  │
│  │ │            │                                          │  │  │
│  │ │            ▼                                          │  │  │
│  │ │  ┌──────────────────────────────────────────┐       │  │  │
│  │ │  │ Task 2: Parse XML                        │       │  │  │
│  │ │  │ - Filter by status codes (630,631,640,641)│       │  │  │
│  │ │  │ - Filter by filing date (> June 12, 2025)│       │  │  │
│  │ │  │ - Extract trademark data + URLs          │       │  │  │
│  │ │  │ - Upload CSV to GCS                      │       │  │  │
│  │ │  └─────────┬────────────────────────────────┘       │  │  │
│  │ │            │                                          │  │  │
│  │ │            ▼                                          │  │  │
│  │ │  ┌──────────────────────────────────────────┐       │  │  │
│  │ │  │ Task 3: Scrape Emails & Prosecution      │       │  │  │
│  │ │  │ - Iterate through URLs                   │       │  │  │
│  │ │  │ - Extract attorney emails                │       │  │  │
│  │ │  │ - Extract correspondent emails           │       │  │  │
│  │ │  │ - Extract prosecution history            │       │  │  │
│  │ │  │ - Upload scraped data to GCS             │       │  │  │
│  │ │  └─────────┬────────────────────────────────┘       │  │  │
│  │ │            │                                          │  │  │
│  │ │            ▼                                          │  │  │
│  │ │  ┌──────────────────────────────────────────┐       │  │  │
│  │ │  │ Task 4: Merge & Validate                 │       │  │  │
│  │ │  │ - Join parsed + scraped data             │       │  │  │
│  │ │  │ - Deduplicate emails                     │       │  │  │
│  │ │  │ - Quality checks                         │       │  │  │
│  │ │  │ - Upload final CSV to GCS                │       │  │  │
│  │ │  └─────────┬────────────────────────────────┘       │  │  │
│  │ │            │                                          │  │  │
│  │ │            ▼                                          │  │  │
│  │ │  ┌──────────────────────────────────────────┐       │  │  │
│  │ │  │ Task 5: Send Notification Email          │       │  │  │
│  │ │  │ - Generate HTML summary                  │       │  │  │
│  │ │  │ - Include metrics & GCS path             │       │  │  │
│  │ │  └──────────────────────────────────────────┘       │  │  │
│  │ └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Cloud Storage (GCS)                                       │  │
│  │ ┌─────────────────────────────────────────────────────┐  │  │
│  │ │ daily-file-staging/                                  │  │  │
│  │ │ ├── daily_xml_file/YYYY/MM/DD/apcYYYYMMDD.xml       │  │  │
│  │ │ └── daily_final_result/YYYY/MM/DD/                   │  │  │
│  │ │     ├── parsed_trademarks_YYYYMMDD.csv               │  │  │
│  │ │     ├── scraped_trademarks_YYYYMMDD.csv              │  │  │
│  │ │     └── final_trademarks_YYYYMMDD.csv                │  │  │
│  │ └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ BigQuery (Optional)                                       │  │
│  │ Dataset: uspto_data                                       │  │
│  │ Table: daily_trademarks                                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Cloud Logging & Monitoring                                │  │
│  │ - Airflow task logs                                       │  │
│  │ - Performance metrics                                     │  │
│  │ - Alert notifications                                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘

External Dependencies:
┌──────────────────────────┐
│ USPTO API                │
│ api.uspto.gov            │
│ - Daily XML feeds        │
└──────────────────────────┘

┌──────────────────────────┐
│ USPTO TSDR Web Pages     │
│ tsdr.uspto.gov           │
│ - Attorney emails        │
│ - Correspondent emails   │
│ - Prosecution history    │
└──────────────────────────┘
```

## Component Details

### 1. Cloud Scheduler
- **Purpose:** Trigger daily pipeline execution
- **Schedule:** 2:00 AM EST (7:00 AM UTC)
- **Trigger:** HTTP POST to Cloud Composer DAG endpoint

### 2. Cloud Composer (Apache Airflow)

**Environment Configuration:**
- **Region:** us-central1
- **Python Version:** 3.10
- **Machine Type:** n1-standard-2
- **Node Count:** 3 workers
- **Disk Size:** 30 GB per node

**DAG Configuration:**
- **Name:** `uspto_daily_trademark_pipeline`
- **Schedule:** Daily @ 2 AM EST
- **Retries:** 2 attempts per task
- **Timeout:** 2 hours total
- **Catchup:** Disabled (no backfill)

### 3. Storage Layer (Cloud Storage)

**Bucket Structure:**
```
daily-file-staging/
├── daily_xml_file/
│   └── YYYY/MM/DD/
│       └── apcYYYYMMDD.xml        # Raw USPTO XML
└── daily_final_result/
    └── YYYY/MM/DD/
        ├── parsed_trademarks_YYYYMMDD.csv    # Parsed data
        ├── scraped_trademarks_YYYYMMDD.csv   # With emails
        └── final_trademarks_YYYYMMDD.csv     # Final merged
```

**Data Retention:**
- XML files: 90 days
- CSV files: 1 year
- Final outputs: Indefinite

### 4. Task Breakdown

#### Task 1: Download XML (`download_xml.py`)
**Input:**
- Execution date (from Airflow)
- USPTO API key (from Airflow Variables)

**Process:**
1. Use execution date as the target date for the XML file
2. Query USPTO API for available files
3. Download XML file (streaming)
4. Upload to GCS with date-based path
5. Extract and propagate the XML file date as refresh_date for all downstream tasks

**Output:**
- GCS path: `gs://daily-file-staging/daily_xml_file/YYYY/MM/DD/apcYYYYMMDD.xml`
- Metadata: file size, record count

**Error Handling:**
- Retry on network errors (3x)
- Skip if no file available (weekends/holidays)
- Alert on repeated failures

---

#### Task 2: Parse XML (`parse_xml.py`)
**Input:**
- GCS XML path (from Task 1 XCom)
- Filter criteria (from config)

**Process:**
1. Download XML from GCS
2. Parse XML using ElementTree
3. Filter by:
   - Status codes: 630, 631, 640, 641
   - Filing date > June 12, 2025
4. Extract fields:
   - Serial number
   - Attorney name
   - Correspondent info
   - Owner info
   - Status description
   - Prosecution events
5. Generate USPTO TSDR URLs
6. Create DataFrame and upload CSV

**Output:**
- GCS path: `gs://daily-file-staging/daily_final_result/YYYY/MM/DD/parsed_trademarks_YYYYMMDD.csv`
- Record count
- Status code breakdown

**Performance:**
- Processes ~50K records in ~5 minutes
- Memory-efficient streaming

---

#### Task 3: Scrape Emails (`scrape_emails.py`)
**Input:**
- GCS parsed CSV path (from Task 2 XCom)
- Scraping configuration (from config)

**Process:**
1. Download parsed CSV from GCS
2. For each URL:
   a. HTTP GET request with rate limiting
   b. Parse HTML with BeautifulSoup
   c. Extract attorney email (labeled field)
   d. Extract correspondent email (labeled field)
   e. Extract all emails (regex pattern)
   f. Extract prosecution history (table parsing)
3. Handle retries (3x with exponential backoff)
4. Update DataFrame with scraped data
5. Upload updated CSV to GCS

**Output:**
- GCS path: `gs://daily-file-staging/daily_final_result/YYYY/MM/DD/scraped_trademarks_YYYYMMDD.csv`
- Success/failure counts
- Success rate percentage

**Rate Limiting:**
- 2 seconds between requests (default)
- Respects USPTO servers
- Adjustable via config

**Performance:**
- ~1,800 URLs per hour (2s delay)
- Typical run: 100-500 URLs = 3-15 minutes

---

#### Task 4: Merge Data (`merge_data.py`)
**Input:**
- GCS parsed CSV path (from Task 2 XCom)
- GCS scraped CSV path (from Task 3 XCom)

**Process:**
1. Download both CSVs from GCS
2. Merge on `serial_number` (left join)
3. Deduplicate emails:
   - Combine attorney_email, correspondent_email, all_emails_found
   - Remove duplicates
   - Create unified `all_emails` field
4. Quality validation:
   - Email format check (regex)
   - Completeness metrics
   - Data integrity checks
5. Sort by filing date (desc)
6. Upload final CSV to GCS

**Output:**
- GCS path: `gs://daily-file-staging/daily_final_result/YYYY/MM/DD/final_trademarks_YYYYMMDD.csv`
- Quality metrics:
  - Total records
  - Has attorney email (%)
  - Has correspondent email (%)
  - Has any email (%)
  - Has prosecution history (%)

**Final Schema:**
| Column | Type | Description |
|--------|------|-------------|
| serial_number | String | Unique trademark ID |
| filing_date | Date | Application filing date |
| status_code | String | Status code (630/631/640/641) |
| status_description | String | Human-readable status |
| attorney_name | String | Attorney from XML |
| attorney_email | String | Attorney email (scraped) |
| correspondent_name | String | Correspondent from XML |
| correspondent_email | String | Correspondent email (scraped) |
| all_emails | String | All unique emails (comma-separated) |
| prosecution_date | Date | Most recent prosecution date |
| prosecution_description | String | Most recent event |
| url | String | USPTO TSDR page URL |
| correspondent_address | String | Full address |
| owner_name | String | Trademark owner |
| owner_address | String | Owner address |
| most_recent_status_date | Date | Status date from XML |

---

#### Task 5: Send Notification (`EmailOperator`)
**Input:**
- Summary metrics (from XCom)
- Final GCS path (from Task 4)

**Process:**
1. Generate HTML email with:
   - Success banner
   - Record counts
   - Scraping statistics
   - Email extraction metrics
   - GCS output path
   - Execution metadata
2. Send via SMTP (configured in Airflow)

**Recipients:**
- Configured via Airflow Variable: `notification_email`
- Failure notifications go to DAG owner

---

## Data Flow

```
[USPTO API]
    │
    │ (HTTPS GET)
    ▼
[Task 1: Download]
    │
    │ (Upload)
    ▼
[GCS: daily_xml_file/]
    │
    │ (Download)
    ▼
[Task 2: Parse]
    │
    │ (Upload CSV)
    ▼
[GCS: daily_final_result/parsed_*.csv]
    │
    │ (Download)
    ▼
[Task 3: Scrape] ◄─── [USPTO TSDR Web Pages]
    │
    │ (Upload CSV)
    ▼
[GCS: daily_final_result/scraped_*.csv]
    │
    │ (Download)
    ▼
[Task 4: Merge]
    │
    │ (Upload Final CSV)
    ▼
[GCS: daily_final_result/final_*.csv]
    │
    │ (Optional)
    ▼
[BigQuery Table]
```

## Security & Access Control

### IAM Roles

**Composer Service Account:**
- `roles/storage.objectAdmin` - Read/Write GCS
- `roles/bigquery.dataEditor` - Load to BigQuery (optional)
- `roles/logging.logWriter` - Write logs

**Human Users:**
- `roles/composer.user` - View/trigger DAGs
- `roles/storage.objectViewer` - View output files

### Secrets Management

**Airflow Variables (Encrypted):**
- `USPTO_API_KEY` - USPTO API key
- `notification_email` - Alert recipient

**Environment Variables:**
- Set via Airflow UI or gcloud CLI
- Encrypted at rest
- Not visible in logs

## Monitoring & Alerting

### Metrics Tracked

1. **DAG-level:**
   - Success/failure rate
   - Execution duration
   - Schedule adherence

2. **Task-level:**
   - Individual task duration
   - Retry counts
   - Error types

3. **Data-level:**
   - Records processed
   - Email extraction rate
   - Data completeness

### Alerts

**Critical Alerts:**
- DAG failure (any task)
- API authentication failure
- No data extracted (0 records)

**Warning Alerts:**
- Success rate < 50% (scraping)
- Execution time > 1 hour
- Retry exhausted

**Notification Channels:**
- Email (via Airflow)
- Cloud Monitoring (optional)
- Slack webhook (optional)

## Performance Optimization

### Current Performance

| Task | Typical Duration | Records Processed |
|------|-----------------|-------------------|
| Download XML | 2-3 min | 1 file (~50MB) |
| Parse XML | 3-5 min | 50,000 cases → 100-500 filtered |
| Scrape Emails | 5-15 min | 100-500 URLs |
| Merge Data | < 1 min | 100-500 records |
| **Total** | **10-25 min** | **100-500 final records** |

### Optimization Strategies

1. **Parallel Scraping:**
   - Use ThreadPoolExecutor for concurrent requests
   - Batch URLs into groups

2. **Caching:**
   - Cache already-scraped URLs
   - Skip if data exists and recent

3. **Incremental Processing:**
   - Only scrape new serial numbers
   - Track processed IDs in BigQuery

4. **Resource Scaling:**
   - Increase Composer worker nodes
   - Use higher machine types during peak

## Disaster Recovery

### Backup Strategy

1. **Code:**
   - Git repository (version control)
   - Automated backups of Composer bucket

2. **Data:**
   - GCS versioning enabled
   - 30-day soft delete
   - Cross-region replication (optional)

3. **Configuration:**
   - Airflow Variables exported regularly
   - Infrastructure as Code (Terraform - future)

### Recovery Procedures

**Scenario 1: DAG Failure**
- Automatic retry (2x)
- Manual trigger from Airflow UI
- Check logs in Cloud Logging

**Scenario 2: Data Corruption**
- Restore from GCS versioned objects
- Re-run DAG for specific date

**Scenario 3: API Outage**
- Pipeline gracefully fails
- Retry next day (catchup disabled)
- Manual backfill if needed

## Cost Analysis

### Monthly Costs (Estimated)

| Service | Usage | Cost |
|---------|-------|------|
| Cloud Composer | 3 x n1-standard-2 (24/7) | $300-350 |
| Cloud Storage | ~5GB new data/month | $0.10 |
| Egress | ~1.5GB downloads/month | $0.15 |
| Cloud Logging | ~2GB logs/month | $1.00 |
| BigQuery (opt) | ~100MB/month | $1.00 |
| **Total** | | **~$302-352/month** |

### Cost Optimization

1. **Pause Composer during off-hours** (save 50%)
2. **Use Preemptible workers** (save 60% on compute)
3. **Auto-scaling** (scale down when idle)
4. **Self-hosted Airflow on GCE** ($25-30/month alternative)

## Future Enhancements

### Phase 2 (Planned)
- [ ] BigQuery integration for historical analysis
- [ ] Incremental updates (only new/changed records)
- [ ] Advanced email validation and normalization
- [ ] Parallel scraping with concurrent workers

### Phase 3 (Future)
- [ ] Real-time monitoring dashboard (Grafana)
- [ ] Machine learning for email prediction
- [ ] API endpoint for querying results
- [ ] Integration with CRM systems

## References

- [Cloud Composer Documentation](https://cloud.google.com/composer/docs)
- [Apache Airflow Documentation](https://airflow.apache.org/docs/)
- [USPTO Bulk Data Documentation](https://bulkdata.uspto.gov/)
- [USPTO API Documentation](https://developer.uspto.gov/)

---

**Document Version:** 1.0  
**Last Updated:** December 15, 2025  
**Owner:** Trademark Data Pipeline Team

