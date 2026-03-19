# 📧 USPTO Trademark Email Scraper - Daily Pipeline

> **Automated daily extraction of USPTO trademark applications with attorney/correspondent contact information**

---

## 🎯 What This Does

Every day at **4:00 AM CST** (10:00 UTC), this pipeline automatically:

1. ⏳ Waits for USPTO daily data to become available (sensor)
2. 📥 Downloads the latest USPTO trademark XML feed
3. 🔍 Parses XML, filters by status codes, and generates TSDR URLs
4. 🌐 Scrapes attorney & correspondent emails from USPTO websites
5. 📊 Merges parsed and scraped data into a single CSV
6. 📧 Normalizes emails (one row per case, comma-separated email lists)
7. 🗄️ Ingests data into Azure SQL Database (`dbo.uspto_trademark_emails`)
8. 📋 Writes a daily summary row to `dbo.uspto_pipeline_daily_summary` (Central Time)
9. 📬 Sends email on failure (Airflow email alerts)

---

## 🏗️ Architecture

**Hybrid Cost-Optimized Design:**
- 🖥️ **Self-Hosted Apache Airflow** (orchestration) - $30/month
- ☁️ **Google Cloud Storage** (data storage) - $2/month

**Total: ~$32/month** (vs $300+ for full Cloud Composer)  
**Annual Savings: ~$3,000!** 💰

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

---

## 📦 What You Get

### Final Output Format

Daily CSV file with all trademark data:

```csv
serial_number,filing_date,status_code,status_description,attorney_name,attorney_email,correspondent_name,correspondent_email,all_emails,prosecution_date,prosecution_description,url,...
```

### Output Locations

- **GCS (CSV):** `gs://daily-file-staging/daily_final_result/YYYY/MM/DD/final_trademarks_YYYYMMDD.csv`
- **Azure SQL:** `dbo.uspto_trademark_emails` (one row per email per case), `dbo.uspto_pipeline_daily_summary` (one row per run, timestamps in Central Time)

Access GCS via:
- [Google Cloud Console](https://console.cloud.google.com/storage/browser/daily-file-staging)
- gsutil: `gsutil cp gs://daily-file-staging/daily_final_result/...`
- Python: `google-cloud-storage` library

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

### Option 2: Deploy to Self-Hosted Server

1. Set up GCP credentials and Azure SQL (see [GCP_CREDENTIALS_SETUP.md](GCP_CREDENTIALS_SETUP.md), [DATABASE_SETUP.md](DATABASE_SETUP.md)).
2. Share and place `.env` and `gcs-key.json` on the server (see [Sharing .env and GCS key with teammates](#-sharing-env-and-gcs-key-with-teammates)).
3. Configure Airflow Variables for Azure SQL (Admin → Variables).
4. Deploy and start: see [SELF_HOSTED_DEPLOYMENT.md](SELF_HOSTED_DEPLOYMENT.md).

```bash
docker-compose up -d
```

---

## 📋 Prerequisites

### Required

- ✅ Docker & Docker Compose
- ✅ Google Cloud Project: `trademark-daily-pipeline`
- ✅ GCS Bucket: `daily-file-staging`
- ✅ GCP Service Account with Storage access

### Optional

- USPTO API key (for API-based download; placeholder may work for testing)
- SMTP credentials (e.g. Gmail App Password) for Airflow failure emails
- Azure SQL connection (Airflow Variables) for database ingest

---

## 📁 Project Structure

```
uspto_airflow_pipeline/
├── config/
│   ├── __init__.py
│   └── config.py                 # Central configuration (GCS, USPTO, scrape settings)
├── dags/
│   └── uspto_daily_pipeline.py   # Main Airflow DAG (schedule: 4:00 AM CST)
├── plugins/
│   └── .gitkeep                  # Custom Airflow plugins (optional)
├── scripts/
│   ├── __init__.py
│   ├── download_xml.py           # Download USPTO XML to GCS
│   ├── parse_xml.py              # Parse XML, filter by status, output CSV
│   ├── scrape_emails.py          # Scrape attorney/correspondent emails from TSDR
│   ├── merge_data.py             # Merge parsed + scraped CSVs
│   ├── normalize_emails.py       # One row per case, comma-separated emails
│   ├── ingest_to_database.py    # Ingest to Azure SQL + pipeline summary
│   ├── azure_sql_connection.py    # Azure SQL connection helper
│   └── sql/
│       ├── 01_drop_uspto_trademark_emails.sql
│       └── 02_create_uspto_trademark_emails.sql
├── docker-compose.yml            # Airflow + Postgres (LocalExecutor)
├── requirements.txt              # Python dependencies
├── .env.example                  # Template for .env (copy to .env, do not commit .env)
├── start_local_airflow.ps1       # Start Airflow (PowerShell)
├── stop_local_airflow.ps1        # Stop Airflow (PowerShell)
├── README.md                     # This file
├── ARCHITECTURE.md               # Architecture overview
├── DATABASE_SETUP.md             # Azure SQL schema and setup
├── GCP_CREDENTIALS_SETUP.md      # GCP service account and bucket
├── SELF_HOSTED_DEPLOYMENT.md     # Server deployment guide
└── LOCAL_TESTING_GUIDE.md        # Local testing guide
```

**Not in Git (add locally / share securely):** `.env`, `gcs-key.json` — see [Sharing .env and GCS key with teammates](#-sharing-env-and-gcs-key-with-teammates).

---

## ⚙️ Configuration

### Environment Variables

- **For Docker/Airflow:** Copy `.env.example` to `.env` in the project root and set at least:
  - `AIRFLOW_UID` (e.g. `50000`)
  - `AIRFLOW_SMTP_PASSWORD` (Gmail App Password or SMTP password for failure emails)
  - `USPTO_API_KEY` (if required by the download step)
- **Inside the container,** `docker-compose` sets `GOOGLE_APPLICATION_CREDENTIALS=/opt/airflow/gcs-key.json`; the host file `gcs-key.json` must exist in the project root (see [Sharing .env and GCS key with teammates](#-sharing-env-and-gcs-key-with-teammates)).

### Filtering Criteria

Edit `config/config.py`:



### Schedule

The DAG runs daily at **4:00 AM CST** (10:00 UTC). Defined in `dags/uspto_daily_pipeline.py`:

```python
schedule_interval='0 10 * * *'  # 4:00 AM CST = 10:00 UTC
```

---

## 🔐 Sharing .env and GCS key with teammates

`.env` and `gcs-key.json` are in `.gitignore` and must **never** be committed. To run the pipeline on a self-hosted server, teammates need these files in the project root. Share them securely:

### 1. Use a secure channel (recommended)

- **Password manager / secrets vault:** 1Password, Bitwarden, Azure Key Vault, etc. Store the file contents or attach the files; teammates download and save as `.env` and `gcs-key.json` in the repo root.
- **Encrypted archive:** Create a password-protected zip (e.g. 7-Zip, WinRAR) with `.env` and `gcs-key.json`, share the zip and the password over a different channel (e.g. password in chat, zip via email or shared drive).
- **Secure file share:** Use a link with expiry and access control (e.g. OneDrive/SharePoint “share link” with limited people, or your company’s secure file share). Tell teammates to save the files in the pipeline project root.

### 2. What to put in `.env`

Copy `.env.example` to `.env` and fill in real values (see below). Typical variables:

- `AIRFLOW_UID` – for Docker (e.g. `50000`).
- `AIRFLOW_SMTP_PASSWORD` – Gmail App Password (or SMTP password) for Airflow failure emails.
- `USPTO_API_KEY` – USPTO API key if your download step uses it.

Teammates on the server: create `.env` in the same directory as `docker-compose.yml` and ensure no one commits it.

### 3. What to share for GCS

- **`gcs-key.json`** – JSON key for the GCP service account that has access to your GCS bucket. Teammates place it in the project root. `docker-compose.yml` mounts it into the Airflow container as `/opt/airflow/gcs-key.json` (and `GOOGLE_APPLICATION_CREDENTIALS` points there).

Do **not** email or Slack the raw contents in plain text. Prefer a secrets vault or encrypted file + separate password.

### 4. On the self-hosted server

After cloning the repo:

1. Copy `.env.example` to `.env` and fill in values (or get `.env` from a teammate via a secure channel).
2. Place `gcs-key.json` in the project root (obtained securely).
3. Ensure `docker-compose.yml` has the volume mount for the key (e.g. `./gcs-key.json:/opt/airflow/gcs-key.json:ro`).
4. Set Airflow Variables for Azure SQL (Admin → Variables) if you use database ingest.
5. Run `docker-compose up -d`.

The pipeline will then have access to GCS and, if configured, to Azure SQL and SMTP.

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

## 📊 Pipeline Steps (DAG Tasks)

| # | Task ID | Description | Typical duration |
|---|---------|-------------|------------------|
| 0 | `wait_for_data` | Sensor: wait until USPTO daily XML is available | Until data appears |
| 1 | `download_xml` | Download USPTO XML, upload to GCS | 5–10 min |
| 2 | `parse_xml` | Parse XML, filter by status codes, output CSV to GCS | 5–10 min |
| 3 | `scrape_emails` | Scrape attorney/correspondent emails from TSDR URLs | 30–60 min |
| 4 | `merge_data` | Merge parsed + scraped CSVs, upload to GCS | 1–2 min |
| 5 | `normalize_emails` | One row per case, comma-separated emails, upload to GCS | 1–2 min |
| 6 | `ingest_to_database` | Ingest normalized CSV into Azure SQL `dbo.uspto_trademark_emails` | 2–5 min |
| 7 | `write_pipeline_summary` | Write one row to `dbo.uspto_pipeline_daily_summary` (Central Time) | &lt; 1 min |

**Total runtime:** ~45–90 minutes per day. Airflow sends email on task failure.

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

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Architecture overview
- **[DATABASE_SETUP.md](DATABASE_SETUP.md)** - Azure SQL schema and setup
- **[GCP_CREDENTIALS_SETUP.md](GCP_CREDENTIALS_SETUP.md)** - GCP service account and bucket
- **[SELF_HOSTED_DEPLOYMENT.md](SELF_HOSTED_DEPLOYMENT.md)** - Server deployment guide
- **[LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md)** - Local testing guide

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
- [ ] Verified output in GCS and/or Azure SQL
- [ ] (Self-hosted) `.env` and `gcs-key.json` in place; Airflow Variables set for Azure SQL if used

---

## 🎉 You're All Set!

The pipeline runs automatically every day at **4:00 AM CST**, extracting the latest USPTO trademark data, scraping contact information, and ingesting into Azure SQL.

**Check your results:**

- GCS: `gs://daily-file-staging/daily_final_result/YYYY/MM/DD/final_trademarks_YYYYMMDD.csv`
- Azure SQL: `dbo.uspto_trademark_emails`, `dbo.uspto_pipeline_daily_summary`

**Questions?** Check the docs in this repo! 📚
