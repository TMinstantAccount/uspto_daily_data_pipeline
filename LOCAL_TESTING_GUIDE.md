# 🧪 Local Airflow Testing Guide

This guide shows you how to run and visualize your Airflow DAG locally before deploying to Google Cloud Composer.

---

## 🎯 Why Test Locally?

- ✅ **See the DAG visualization** - View task dependencies and flow
- ✅ **Test DAG syntax** - Catch errors before deployment
- ✅ **Debug tasks** - Test individual components
- ✅ **Faster iteration** - No waiting for Cloud Composer updates
- ✅ **Free** - No GCP costs during development

---

## 🚀 Option 1: Docker Compose (Recommended)

### Prerequisites

- **Docker Desktop** installed ([Download here](https://www.docker.com/products/docker-desktop))
- **8GB RAM** minimum (preferably 16GB)
- **10GB free disk space**

### Quick Start (5 minutes)

**Step 1: Start Docker Desktop**
- Open Docker Desktop
- Wait until it shows "Docker Desktop is running"

**Step 2: Navigate to Project**
```powershell
cd C:\Legal\Legal_AI\uspto_airflow_pipeline
```

**Step 3: Set Environment (Windows)**
```powershell
# Create .env file for Windows
$env:AIRFLOW_UID=50000
echo "AIRFLOW_UID=50000" | Out-File -FilePath .env -Encoding ASCII
```

**Step 4: Start Airflow**
```powershell
docker-compose up -d
```

**Step 5: Wait for Initialization** (~2 minutes)
```powershell
# Check status
docker-compose ps

# Wait until all services show "healthy"
# Watch logs
docker-compose logs -f airflow-webserver
# Press Ctrl+C when you see "Airflow is ready"
```

**Step 6: Open Airflow UI**
- Open browser: http://localhost:8080
- **Username:** `admin`
- **Password:** `admin`

🎉 **Done!** You should see the Airflow UI.

---

## 📊 Viewing Your DAG

### In the Airflow UI:

1. **DAGs List View**
   - You should see: `uspto_daily_trademark_pipeline`
   - If it's paused (gray), toggle it ON (click the toggle)

2. **Graph View** (Best for Visualization)
   - Click on the DAG name
   - Click **"Graph"** tab at the top
   - You'll see:
     ```
     [download_xml] → [parse_xml] → [scrape_emails] → [merge_data] → [generate_summary] → [send_email]
     ```

3. **Other Useful Views**
   - **Tree View** - Historical runs
   - **Calendar View** - Run schedule
   - **Code View** - See the DAG code

---

## ⚠️ Important Notes for Local Testing

### What Works Locally:
✅ DAG visualization (main goal)  
✅ DAG syntax validation  
✅ Task dependency flow  
✅ Airflow UI navigation  
✅ Schedule configuration viewing  

### What Won't Work Without Modification:
❌ **GCS Access** - No credentials configured  
❌ **USPTO API calls** - Need real API key  
❌ **Email sending** - SMTP not configured  
❌ **Actual task execution** - Will fail due to missing GCS credentials  

**This is OK!** The main goal is to **visualize the DAG structure**.

---

## 🧪 Testing Strategies

### Strategy 1: Visual Inspection Only (Easiest)

Just view the DAG graph to verify:
- Task order is correct
- Dependencies make sense
- No syntax errors
- Schedule is correct

**Steps:**
1. Start Airflow with Docker Compose
2. Open http://localhost:8080
3. View the DAG in Graph View
4. Check task connections
5. Done! ✅

---

### Strategy 2: Test with Mock Data (Advanced)

If you want to actually run tasks locally, create mock functions:

**Create:** `test_data/mock_helpers.py`
```python
"""Mock helpers for local testing"""

def mock_download_xml(**context):
    """Mock download - returns fake GCS path"""
    print("MOCK: Downloading XML...")
    fake_path = "gs://test-bucket/test.xml"
    context['task_instance'].xcom_push(key='gcs_xml_path', value=fake_path)
    return {'gcs_path': fake_path, 'file_name': 'test.xml'}

def mock_parse_xml(**context):
    """Mock parse - returns fake results"""
    print("MOCK: Parsing XML...")
    fake_csv = "gs://test-bucket/parsed.csv"
    context['task_instance'].xcom_push(key='gcs_parsed_csv', value=fake_csv)
    return {'gcs_csv_path': fake_csv, 'record_count': 100}

# etc...
```

**Then modify DAG for local testing:**
```python
import os

# At top of DAG file
IS_LOCAL = os.getenv('AIRFLOW__CORE__EXECUTOR') == 'LocalExecutor'

if IS_LOCAL:
    from test_data.mock_helpers import mock_download_xml as download_xml_task
else:
    # Use real functions
    from scripts import download_xml
```

---

### Strategy 3: Test Individual Scripts (Recommended)

Test Python scripts independently without Airflow:

```powershell
# Activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Test download script (will fail without credentials, but validates syntax)
python scripts/download_xml.py

# Test with local XML file
# Download a sample XML first, then:
python scripts/parse_xml.py test_data/sample.xml
```

---

## 🛠️ Common Commands

### Start Airflow
```powershell
docker-compose up -d
```

### Stop Airflow
```powershell
docker-compose down
```

### View Logs
```powershell
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f airflow-webserver
docker-compose logs -f airflow-scheduler
```

### Restart Airflow (after code changes)
```powershell
docker-compose restart
```

### Clean Everything (fresh start)
```powershell
# WARNING: This deletes all data
docker-compose down -v
docker-compose up -d
```

### Check Status
```powershell
docker-compose ps
```

---

## 🎨 Customizing Local Setup

### Change Airflow UI Port

Edit `docker-compose.yml`:
```yaml
airflow-webserver:
  ports:
    - "8080:8080"  # Change 8080 to any port
```

### Add Python Packages

Edit `docker-compose.yml`, add under `airflow-common`:
```yaml
environment:
  _PIP_ADDITIONAL_REQUIREMENTS: 'beautifulsoup4==4.12.2 lxml==5.1.0'
```

Then restart:
```powershell
docker-compose down
docker-compose up -d
```

### Set Environment Variables

Edit `docker-compose.yml`, add under `airflow-common-env`:
```yaml
USPTO_API_KEY: 'your-real-key-here'
NOTIFICATION_EMAIL: 'your@email.com'
```

---

## 🐛 Troubleshooting

### DAG Not Showing Up

**Solution 1: Wait and Refresh**
- Wait 30 seconds
- Refresh browser
- Check "Auto-refresh" is ON in Airflow UI

**Solution 2: Check for Errors**
```powershell
docker-compose logs airflow-scheduler | Select-String -Pattern "ERROR"
```

**Solution 3: Validate DAG Syntax**
```powershell
docker-compose exec airflow-webserver airflow dags list
```

---

### Import Errors

**Problem:** `ModuleNotFoundError: No module named 'scripts'`

**Solution:** Ensure PYTHONPATH is set in docker-compose.yml:
```yaml
environment:
  PYTHONPATH: /opt/airflow
```

Then restart:
```powershell
docker-compose restart
```

---

### Port Already in Use

**Problem:** Port 8080 already in use

**Solution 1:** Stop other services on port 8080
```powershell
# Find process using port 8080
netstat -ano | findstr :8080

# Kill process (replace PID with actual number)
taskkill /F /PID <PID>
```

**Solution 2:** Use different port (edit docker-compose.yml)

---

### Docker Out of Memory

**Problem:** Containers keep restarting

**Solution:** Increase Docker memory
1. Open Docker Desktop
2. Settings → Resources
3. Increase Memory to 8GB or more
4. Click "Apply & Restart"

---

## 📸 What You'll See

### Airflow UI Home Page
```
┌─────────────────────────────────────────────────┐
│  Apache Airflow                        [admin ▼]│
├─────────────────────────────────────────────────┤
│  DAGs (1)                    🔍 Search          │
├─────────────────────────────────────────────────┤
│  ⏸ uspto_daily_trademark_pipeline              │
│     Schedule: 0 7 * * *     [▶] [📊] [📅]      │
│     Last Run: Not run yet                       │
└─────────────────────────────────────────────────┘
```

### Graph View
```
┌─────────────────────────────────────────────────┐
│  uspto_daily_trademark_pipeline                 │
│  Graph | Tree | Calendar | Code | Details       │
├─────────────────────────────────────────────────┤
│                                                  │
│    ┌──────────────┐                            │
│    │download_xml  │                            │
│    └──────┬───────┘                            │
│           │                                     │
│           ▼                                     │
│    ┌──────────────┐                            │
│    │  parse_xml   │                            │
│    └──────┬───────┘                            │
│           │                                     │
│           ▼                                     │
│    ┌──────────────┐                            │
│    │scrape_emails │                            │
│    └──────┬───────┘                            │
│           │                                     │
│           ▼                                     │
│    ┌──────────────┐                            │
│    │ merge_data   │                            │
│    └──────┬───────┘                            │
│           │                                     │
│           ▼                                     │
│    ┌──────────────┐                            │
│    │generate_summ │                            │
│    └──────┬───────┘                            │
│           │                                     │
│           ▼                                     │
│    ┌──────────────┐                            │
│    │send_summary  │                            │
│    └──────────────┘                            │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## 🎯 Recommended Workflow

### For Visualization Only (Easiest)

1. **Start Airflow:**
   ```powershell
   docker-compose up -d
   ```

2. **Open UI:** http://localhost:8080

3. **View DAG Graph**

4. **Check:**
   - ✅ All tasks appear
   - ✅ Connections are correct
   - ✅ Schedule is right
   - ✅ No import errors

5. **Stop Airflow:**
   ```powershell
   docker-compose down
   ```

6. **Deploy to GCP** with confidence! 🚀

---

### For Full Testing (Advanced)

1. Set up local testing environment
2. Create mock data/functions
3. Test individual scripts
4. Test in local Airflow
5. Deploy to GCP

---

## 📚 Additional Resources

- [Airflow Docker Documentation](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html)
- [Airflow UI Guide](https://airflow.apache.org/docs/apache-airflow/stable/ui.html)
- [Testing Airflow DAGs](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html#testing)

---

## ✅ Success Checklist

Before deploying to GCP, verify locally:

- [ ] Docker Compose starts without errors
- [ ] Airflow UI loads at http://localhost:8080
- [ ] DAG appears in DAGs list
- [ ] No import errors shown
- [ ] Graph view shows all 6 tasks
- [ ] Task dependencies are correct:
  - [ ] download_xml → parse_xml
  - [ ] parse_xml → scrape_emails
  - [ ] scrape_emails → merge_data
  - [ ] merge_data → generate_summary
  - [ ] generate_summary → send_summary_email
- [ ] Schedule shows `0 7 * * *`
- [ ] No red error messages

✅ **Ready to deploy to Cloud Composer!**

---

## 🔄 After Testing

When satisfied with local testing:

1. **Stop local Airflow:**
   ```powershell
   docker-compose down
   ```

2. **Deploy to GCP:**
   ```powershell
   .\deploy.ps1
   ```

3. **Verify in Cloud Composer**

---

## 💡 Pro Tips

1. **Keep Docker Running** while developing - faster iterations
2. **Use Graph View** - best for understanding flow
3. **Check Scheduler Logs** if DAG doesn't appear
4. **Don't worry about task failures** - focus on visualization
5. **Take screenshots** of graph view for documentation

---

**🎉 You're now ready to visualize your Airflow DAG locally!**

**Quick Start:** `docker-compose up -d` → Open http://localhost:8080 → View Graph

