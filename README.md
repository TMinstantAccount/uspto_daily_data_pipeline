# 📧 USPTO Trademark Email Scraper - Daily Pipeline

> **Automated daily extraction of USPTO trademark applications with attorney/correspondent contact information**

---

## 🎯 What This Does

Every day at **12:30 AM EST** (as soon as USPTO publishes the daily feed around midnight EST), this pipeline automatically:

1. 📥 Downloads the latest USPTO trademark XML feed
2. 🔍 Filters for status codes 
3. 📋 Extracts trademark details and generates TSDR URLs
4. 🌐 Scrapes attorney & correspondent emails from USPTO websites
5. 📊 Merges everything into a final CSV with prosecution history
6. ☁️ Stores results in Google Cloud Storage
7. 📧 Emails you a summary report

---

## 🏗️ Architecture

**Hybrid Cost-Optimized Design:**
- 🖥️ **Self-Hosted Apache Airflow** (orchestration) - $30/month
- ☁️ **Google Cloud Storage** (data storage) - $2/month

**Total: ~$32/month** (vs $300+ for full Cloud Composer)  
**Annual Savings: ~$3,000!** 💰

See [HYBRID_ARCHITECTURE.md](HYBRID_ARCHITECTURE.md) for details.

---

## 📦 What You Get

### Final Output Format

Daily CSV file with all trademark data:

```csv
serial_number,filing_date,status_code,status_description,attorney_name,attorney_email,correspondent_name,correspondent_email,all_emails,prosecution_date,prosecution_description,url,...
```

### Output Location

```
gs://daily-file-staging/daily_final_result/YYYY/MM/DD/final_trademarks_YYYYMMDD.csv
```

Access via:
- [Google Cloud Console](https://console.cloud.google.com/storage/browser/daily-file-staging)
- gsutil: `gsutil cp gs://daily-file-staging/daily_final_result/...`
- Python: Using `google-cloud-storage` library

---

## 🚀 Quick Start

### Option 1: Test Locally First (Recommended)

```powershell
# 1. Install Docker Desktop
# Download from: https://www.docker.com/products/docker-desktop

# 2. Start Docker Desktop

# 3. Navigate to project
cd C:\Legal\Legal_AI\uspto_airflow_pipeline

# 4. Start local Airflow
docker-compose up -d

# 5. Access UI
# Open browser: http://localhost:8080
# Login: admin / admin
```

📖 **Full Guide:** [LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md)

### Option 2: Deploy to Production Server

```bash
# 1. Set up GCP credentials
#    See: GCP_CREDENTIALS_SETUP.md

# 2. Deploy to your server
#    See: SELF_HOSTED_DEPLOYMENT.md

# 3. Configure USPTO API key
export USPTO_API_KEY="your-api-key-here"

# 4. Start the pipeline
docker-compose up -d
```

📖 **Full Guide:** [SELF_HOSTED_DEPLOYMENT.md](SELF_HOSTED_DEPLOYMENT.md)

---

## 📋 Prerequisites

### Required

- ✅ Docker & Docker Compose
- ✅ Google Cloud Project: `trademark-daily-pipeline`
- ✅ GCS Bucket: `daily-file-staging`
- ✅ GCP Service Account with Storage access

### Optional

- USPTO API key (placeholder provided for testing)
- SMTP credentials for email notifications

---

## 📁 Project Structure

```
uspto_airflow_pipeline/
├── config/
│   └── config.py                 # Central configuration
├── dags/
│   └── uspto_daily_pipeline.py   # Main Airflow DAG
├── scripts/
│   ├── download_xml.py           # Download USPTO XML
│   ├── parse_xml.py              # Parse and filter XML
│   ├── scrape_emails.py          # Scrape email addresses
│   └── merge_data.py             # Merge and finalize data
├── docker-compose.yml            # Docker configuration
├── requirements.txt              # Python dependencies
├── README.md                     # This file
├── HYBRID_ARCHITECTURE.md        # Architecture overview
├── GCP_CREDENTIALS_SETUP.md      # GCP setup guide
├── SELF_HOSTED_DEPLOYMENT.md     # Deployment guide
└── LOCAL_TESTING_GUIDE.md        # Local testing guide
```

---

## ⚙️ Configuration

### Environment Variables

Set these in `docker-compose.yml` or `.env`:

```bash
# Required
GOOGLE_APPLICATION_CREDENTIALS=/opt/airflow/gcs-key.json

# Optional
USPTO_API_KEY=your-api-key-here
NOTIFICATION_EMAIL=your-email@example.com
```

### Filtering Criteria

Edit `config/config.py`:



### Schedule

Edit `dags/uspto_daily_pipeline.py`:

```python
# Current: 12:30 AM EST daily (05:30 UTC)
schedule_interval='30 5 * * *'
```

---

## 🔐 GCP Setup

### 1. Create Service Account

```bash
gcloud iam service-accounts create airflow-self-hosted \
    --project=trademark-daily-pipeline
```

### 2. Grant Storage Permissions

```bash
gsutil iam ch serviceAccount:airflow-self-hosted@trademark-daily-pipeline.iam.gserviceaccount.com:roles/storage.objectAdmin \
    gs://daily-file-staging
```

### 3. Create Key File

```bash
gcloud iam service-accounts keys create gcs-key.json \
    --iam-account=airflow-self-hosted@trademark-daily-pipeline.iam.gserviceaccount.com
```

### 4. Place Key in Project

```powershell
# Copy to project root
copy gcs-key.json C:\Legal\Legal_AI\uspto_airflow_pipeline\
```

### 5. Update docker-compose.yml

Uncomment the GCS key volume line:

```yaml
volumes:
  - ./gcs-key.json:/opt/airflow/gcs-key.json:ro  # Uncomment this!
```

📖 **Full Guide:** [GCP_CREDENTIALS_SETUP.md](GCP_CREDENTIALS_SETUP.md)

---

## 🎬 Usage

### View Pipeline in Airflow UI

```
http://localhost:8080          # Local
http://your-server-ip:8080     # Production
```

**Login:** `admin` / `admin`

### Manually Trigger Pipeline

1. Go to Airflow UI
2. Click on `uspto_daily_pipeline`
3. Click "Trigger DAG" button (▶️)
4. Monitor progress in Graph/Tree view

### Check Logs

```bash
# View scheduler logs
docker-compose logs -f airflow-scheduler

# View webserver logs
docker-compose logs -f airflow-webserver

# View task logs
# Go to Airflow UI > DAG > Task > Logs
```

### Download Results

```bash
# Via gsutil
gsutil cp gs://daily-file-staging/daily_final_result/2025/12/17/final_trademarks_20251217.csv ./

# Via Python
from google.cloud import storage
client = storage.Client(project='trademark-daily-pipeline')
bucket = client.bucket('daily-file-staging')
blob = bucket.blob('daily_final_result/2025/12/17/final_trademarks_20251217.csv')
blob.download_to_filename('local_file.csv')
```

---

## 📊 Pipeline Steps

### Step 1: Download XML (5-10 minutes)

- Queries USPTO API for latest daily feed
- Downloads XML file (~100-500 MB)
- Uploads to GCS: `gs://daily-file-staging/daily_xml_file/`

### Step 2: Parse XML (5-10 minutes)

- Parses XML file
- Filters by status codes and filing date
- Extracts trademark data
- Generates TSDR URLs
- Uploads CSV to GCS

### Step 3: Scrape Emails (30-60 minutes)

- Reads parsed CSV from GCS
- Scrapes each TSDR URL for emails
- Extracts prosecution history
- Uploads CSV to GCS

### Step 4: Merge Data (1-2 minutes)

- Downloads parsed and scraped CSVs
- Merges by serial number
- Deduplicates emails
- Uploads final CSV to GCS

### Step 5: Send Notification (< 1 minute)

- Sends email with summary and link

**Total Runtime:** ~40-80 minutes per day

---

## 🔧 Troubleshooting

### Docker not running

```powershell
# Start Docker Desktop
# Look for Docker icon in system tray
# Wait until it says "Docker Desktop is running"
```

### Can't access Airflow UI

```bash
# Check if containers are running
docker-compose ps

# Restart containers
docker-compose restart

# Check logs
docker-compose logs airflow-webserver
```

### GCS permission errors

```bash
# Verify credentials
docker-compose exec airflow-webserver \
    python -c "from google.cloud import storage; print(storage.Client().list_buckets())"

# Check service account permissions
gsutil iam get gs://daily-file-staging
```

### Pipeline fails

```bash
# Check Airflow logs
docker-compose logs airflow-scheduler

# Check task logs in Airflow UI
# Go to DAG > Failed Task > Logs

# Clear failed tasks and retry
# In Airflow UI: Click task > Clear > Upstream/Downstream
```

---

## 📈 Monitoring

### Airflow UI Dashboards

- **DAGs View:** Overall pipeline status
- **Graph View:** Task dependencies and current state
- **Tree View:** Historical run status
- **Gantt Chart:** Task execution timeline
- **Task Duration:** Performance trends

### Email Notifications

Daily email includes:
- ✅ Success/failure status
- 📊 Record counts at each step
- 📧 Email extraction success rate
- 🔗 Link to final output file
- ⏱️ Total execution time

### GCS Monitoring

View in Cloud Console:
- Storage usage trends
- File sizes over time
- Access patterns

---

## 💡 Tips & Best Practices

### Cost Optimization

1. **Use regional buckets** (us-central1) to reduce network costs
2. **Enable lifecycle policies** to auto-delete old files:
   ```bash
   gsutil lifecycle set lifecycle.json gs://daily-file-staging
   ```
3. **Monitor storage usage** monthly
4. **Shut down VM** when not in use (if testing)

### Performance Optimization

1. **Increase scraping workers** if you have many URLs
2. **Adjust `SCRAPE_DELAY_SECONDS`** to balance speed vs politeness
3. **Use larger VM** if pipeline is too slow
4. **Enable parallel uploads** in scripts

### Reliability

1. **Set up email alerts** for failures
2. **Enable DAG retries** in config
3. **Monitor disk space** on server
4. **Backup GCS data** to another bucket periodically

---

## 🔄 Updates & Maintenance

### Update Dependencies

```bash
# Update requirements.txt
pip install --upgrade -r requirements.txt

# Rebuild Docker image
docker-compose build --no-cache
docker-compose up -d
```

### Update Configuration

```bash
# Edit config
vim config/config.py

# Restart Airflow
docker-compose restart
```

### Update DAG

```bash
# Edit DAG file
vim dags/uspto_daily_pipeline.py

# Airflow auto-reloads DAGs (no restart needed)
# Refresh Airflow UI to see changes
```

---

## 📚 Documentation

- **[HYBRID_ARCHITECTURE.md](HYBRID_ARCHITECTURE.md)** - Detailed architecture explanation
- **[GCP_CREDENTIALS_SETUP.md](GCP_CREDENTIALS_SETUP.md)** - GCP authentication setup
- **[SELF_HOSTED_DEPLOYMENT.md](SELF_HOSTED_DEPLOYMENT.md)** - Server deployment guide
- **[LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md)** - Local development guide

---

## ⚠️ Important Notes

### Security

- ⚠️ **NEVER commit `gcs-key.json` to Git!**
- ⚠️ Keep USPTO API key in environment variables, not code
- ⚠️ Use firewall rules to restrict Airflow UI access
- ⚠️ Enable HTTPS for production deployments
- ⚠️ Rotate service account keys every 90 days

### Data Privacy

- ⚠️ This scrapes **public USPTO data** only
- ⚠️ Email addresses are publicly available on USPTO.gov
- ⚠️ Always respect robots.txt and rate limits
- ⚠️ Add delays between requests (`SCRAPE_DELAY_SECONDS`)

### Compliance

- ✅ Uses official USPTO API
- ✅ Respects rate limits
- ✅ Only scrapes public information
- ✅ Follows robots.txt guidelines

---

## 🆘 Support

### Common Issues

| Issue | Solution |
|-------|----------|
| Docker not starting | Make sure Docker Desktop is running |
| Can't access UI | Check port 8080 is not in use |
| GCS errors | Verify service account has correct permissions |
| Pipeline fails | Check task logs in Airflow UI |
| Slow scraping | Increase `SCRAPE_DELAY_SECONDS` or add more workers |

### Getting Help

1. Check the logs: `docker-compose logs`
2. Review documentation in this repo
3. Check Airflow UI task logs
4. Verify GCP credentials and permissions

---

## 📝 License

This project is for internal use. USPTO data is public domain.

---

## ✅ Checklist Before First Run

- [ ] Docker Desktop installed and running
- [ ] GCP project created (`trademark-daily-pipeline`)
- [ ] GCS bucket created (`daily-file-staging`)
- [ ] Service account created with Storage permissions
- [ ] Key file downloaded and placed in project root
- [ ] `docker-compose.yml` updated with GCS key volume
- [ ] `gcs-key.json` added to `.gitignore`
- [ ] USPTO API key obtained (or using placeholder)
- [ ] Tested locally: `docker-compose up -d`
- [ ] Accessed Airflow UI: http://localhost:8080
- [ ] Manually triggered test run
- [ ] Verified output in GCS

---

## 🎉 You're All Set!

Your pipeline will now run automatically every day at 7 PM, extracting the latest USPTO trademark applications and scraping contact information!

**Check your results:**
```
gs://daily-file-staging/daily_final_result/YYYY/MM/DD/final_trademarks_YYYYMMDD.csv
```

**Questions?** Check the docs in this repo! 📚
