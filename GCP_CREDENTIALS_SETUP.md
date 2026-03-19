# 🔐 GCP Credentials Setup for Self-Hosted Airflow

Your pipeline uses **Self-Hosted Airflow** (saves $300/month) but stores data in **Google Cloud Storage** (for cloud storage benefits).

This guide shows how to set up GCP credentials so your self-hosted Airflow can access GCS.

---

## 🎯 What You Need

- Google Cloud Project: `trademark-daily-pipeline`
- GCS Bucket: `daily-file-staging`
- Service Account with Storage permissions

---

## 📋 Step-by-Step Setup

### **Step 1: Create Service Account**

```bash
# Login to GCP
gcloud auth login
gcloud config set project trademark-daily-pipeline

# Create service account
gcloud iam service-accounts create airflow-self-hosted \
    --display-name="Airflow Self-Hosted Storage Access" \
    --description="Service account for self-hosted Airflow to access GCS"
```

### **Step 2: Grant Storage Permissions**

```bash
# Grant storage admin role to the bucket
gsutil iam ch serviceAccount:airflow-self-hosted@trademark-daily-pipeline.iam.gserviceaccount.com:roles/storage.objectAdmin \
    gs://daily-file-staging
```

### **Step 3: Create and Download Key**

```bash
# Create JSON key
gcloud iam service-accounts keys create ~/airflow-gcs-key.json \
    --iam-account=airflow-self-hosted@trademark-daily-pipeline.iam.gserviceaccount.com

# Download the key
# Location: ~/airflow-gcs-key.json
```

**Important:** Keep this key file secure! It's like a password for your GCS bucket.

---

## 🐳 For Docker Compose (Local Testing)

### **Step 1: Copy Key to Project**

```powershell
# Windows
copy %USERPROFILE%\airflow-gcs-key.json C:\Legal\Legal_AI\uspto_airflow_pipeline\gcs-key.json
```

### **Step 2: Update docker-compose.yml**

Add the credentials path to the environment section:

```yaml
x-airflow-common:
  &airflow-common
  image: apache/airflow:2.8.0-python3.10
  environment:
    &airflow-common-env
    # ... existing environment variables ...
    GOOGLE_APPLICATION_CREDENTIALS: /opt/airflow/gcs-key.json
  volumes:
    # ... existing volumes ...
    - ./gcs-key.json:/opt/airflow/gcs-key.json:ro  # Add this line
```

### **Step 3: Restart Airflow**

```powershell
docker-compose down
docker-compose up -d
```

---

## 🖥️ For Server Deployment

### **Option A: Using Environment Variable**

```bash
# On your server
cd /root/uspto_airflow_pipeline

# Upload the key file
# (Use SCP or SFTP to transfer gcs-key.json to server)

# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS=/root/uspto_airflow_pipeline/gcs-key.json

# Add to docker-compose.yml environment section
cat >> docker-compose.yml << 'EOF'
    GOOGLE_APPLICATION_CREDENTIALS: /opt/airflow/gcs-key.json
EOF

# Update volumes section
# Add: - ./gcs-key.json:/opt/airflow/gcs-key.json:ro

# Restart
docker-compose restart
```

### **Option B: Using GCP Compute Engine**

If deploying on a GCE VM, you can use the VM's service account:

```bash
# When creating the VM, attach the service account
gcloud compute instances create airflow-vm \
    --zone=us-central1-a \
    --machine-type=e2-medium \
    --service-account=airflow-self-hosted@trademark-daily-pipeline.iam.gserviceaccount.com \
    --scopes=https://www.googleapis.com/auth/cloud-platform

# No key file needed! The VM automatically has access.
```

---

## ✅ Test the Connection

### **Test Script**

Create `test_gcs.py`:

```python
from google.cloud import storage

def test_gcs_access():
    try:
        client = storage.Client(project='trademark-daily-pipeline')
        bucket = client.bucket('daily-file-staging')
        
        # List blobs
        blobs = list(bucket.list_blobs(max_results=5))
        print(f"✅ Success! Found {len(blobs)} objects")
        for blob in blobs:
            print(f"  - {blob.name}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_gcs_access()
```

### **Run Test**

```bash
# In Airflow container
docker-compose exec airflow-webserver python /opt/airflow/test_gcs.py
```

Expected output:
```
✅ Success! Found 5 objects
  - daily_xml_file/2025/12/15/apc20251215.xml
  - daily_final_result/2025/12/15/final_trademarks_20251215.csv
  ...
```

---

## 🔒 Security Best Practices

### **1. Restrict Key Permissions**

```bash
# Make key file read-only
chmod 400 gcs-key.json
```

### **2. Use Least Privilege**

The service account only has access to the specific bucket, not your entire GCP project.

### **3. Rotate Keys Regularly**

```bash
# Every 90 days, create new key
gcloud iam service-accounts keys create new-key.json \
    --iam-account=airflow-self-hosted@trademark-daily-pipeline.iam.gserviceaccount.com

# Update your deployment with new key
# Then delete old key
gcloud iam service-accounts keys delete OLD_KEY_ID \
    --iam-account=airflow-self-hosted@trademark-daily-pipeline.iam.gserviceaccount.com
```

### **4. Don't Commit Keys to Git**

Add to `.gitignore`:
```
gcs-key.json
*-key.json
*.json
```

---

## 📁 Where Your Data Goes

With this hybrid setup:

```
Cloud Storage (GCS)
└── gs://daily-file-staging/
    ├── daily_xml_file/
    │   └── 2025/12/17/
    │       └── apc20251217.xml
    └── daily_final_result/
        └── 2025/12/17/
            ├── parsed_trademarks_20251217.csv
            ├── scraped_trademarks_20251217.csv
            └── final_trademarks_20251217.csv  ← Your final output!
```

**Access your data:**
- Via Cloud Console: https://console.cloud.google.com/storage/browser/daily-file-staging
- Via gsutil: `gsutil ls gs://daily-file-staging/daily_final_result/`
- Via Python: Using `google-cloud-storage` library

---

## 💡 Why This Hybrid Approach?

| Component | What You Use | Cost | Benefit |
|-----------|-------------|------|---------|
| **Orchestration** | Self-Hosted Airflow | $25-50/month | Save $300/month |
| **Storage** | Google Cloud Storage | $1-5/month | Cloud backups, accessibility |
| **Total** | | **$26-55/month** | **vs $300+ for full Cloud Composer** |

**You save ~$250-275/month!** 💰

---

## 🆘 Troubleshooting

### **Error: "Could not automatically determine credentials"**

**Solution:** Set `GOOGLE_APPLICATION_CREDENTIALS` environment variable:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/gcs-key.json
```

### **Error: "Permission denied"**

**Solution:** Grant proper IAM role:
```bash
gsutil iam ch serviceAccount:airflow-self-hosted@trademark-daily-pipeline.iam.gserviceaccount.com:roles/storage.objectAdmin \
    gs://daily-file-staging
```

### **Error: "Key file not found"**

**Solution:** Check the file path and volume mount in docker-compose.yml:
```yaml
volumes:
  - ./gcs-key.json:/opt/airflow/gcs-key.json:ro
```

---

## ✅ Quick Checklist

Before running the pipeline:

- [ ] Service account created
- [ ] Storage permissions granted
- [ ] Key file downloaded
- [ ] Key file copied to server/project
- [ ] docker-compose.yml updated with credentials path
- [ ] Airflow restarted
- [ ] GCS access tested successfully
- [ ] Key file secured (chmod 400)
- [ ] Key file NOT committed to Git

---

## 🎯 Summary

You now have:
- ✅ Self-hosted Airflow (cheap orchestration)
- ✅ Google Cloud Storage (reliable cloud storage)
- ✅ Secure authentication
- ✅ Best of both worlds!

**Final output location:**  
`gs://daily-file-staging/daily_final_result/YYYY/MM/DD/final_trademarks_YYYYMMDD.csv`

---

**Next:** Follow `SELF_HOSTED_DEPLOYMENT.md` to deploy your server!

