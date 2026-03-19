# 🏠 USPTO Pipeline - Self-Hosted Deployment Guide

This guide covers deploying the USPTO trademark pipeline on your own server instead of Google Cloud Composer.

---

## 💰 Cost Savings

**Google Cloud Composer:** ~$300-350/month  
**Self-Hosted:** ~$25-50/month (depending on server choice)

**Savings:** ~$275-325/month! 🎉

---

## 🎯 Deployment Options

### **Option 1: Current Docker Compose Setup (Easiest)**

What you're already running locally works for production!

**Pros:**
- ✅ Already set up and running
- ✅ Easy to deploy (just move to a server)
- ✅ Built-in database (PostgreSQL)
- ✅ No complex configuration

**Cons:**
- ⚠️ Need to manage server updates
- ⚠️ Single point of failure

**Best for:** Small-medium workloads, getting started quickly

---

### **Option 2: VPS/Cloud VM**

Deploy to a cloud virtual machine.

**Providers:**
- **DigitalOcean** - $25/month (4GB RAM, 2 CPU)
- **Linode** - $24/month (4GB RAM, 2 CPU)
- **AWS EC2** - ~$30/month (t3.medium)
- **Azure VM** - ~$35/month (B2s)
- **Google Cloud** - ~$30/month (e2-medium) - Use your credits!

**Best for:** Reliable, managed infrastructure

---

### **Option 3: On-Premises Server**

Run on your own hardware.

**Requirements:**
- 4GB+ RAM
- 2+ CPU cores
- 50GB+ disk space
- Ubuntu/Debian Linux

**Cost:** $0 (using existing hardware)

**Best for:** Maximum control, zero cloud costs

---

## 🚀 Quick Start: Deploy Current Setup to Server

### **Step 1: Choose a Server**

For this guide, we'll use a VPS (works the same for any option):

```bash
# Example: DigitalOcean Droplet
# - Size: Basic (4GB RAM, 2 vCPU)
# - Image: Ubuntu 22.04 LTS
# - Cost: $24/month
```

### **Step 2: Install Docker on Server**

SSH into your server:

```bash
ssh root@your-server-ip
```

Install Docker:

```bash
# Update packages
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose -y

# Verify installation
docker --version
docker-compose --version
```

### **Step 3: Transfer Your Code**

From your local machine:

```bash
# Create tarball of your project
cd C:\Legal\Legal_AI
tar -czf uspto_pipeline.tar.gz uspto_airflow_pipeline/

# Upload to server (using SCP)
scp uspto_pipeline.tar.gz root@your-server-ip:/root/

# Or use SFTP, FileZilla, or Git
```

On the server:

```bash
# Extract files
cd /root
tar -xzf uspto_pipeline.tar.gz
cd uspto_airflow_pipeline
```

### **Step 4: Set Environment Variables**

Create `.env` file on server:

```bash
cat > .env << 'EOF'
AIRFLOW_UID=50000
USPTO_API_KEY=your_actual_api_key_here
NOTIFICATION_EMAIL=your-email@example.com
EOF
```

### **Step 5: Create Data Directory**

```bash
# Create persistent data storage
mkdir -p data

# Set permissions
chmod -R 777 data logs
```

### **Step 6: Start Airflow**

```bash
# Start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### **Step 7: Access Airflow UI**

```bash
# Get your server's public IP
curl ifconfig.me

# Open in browser:
# http://your-server-ip:8080
# Username: admin
# Password: admin
```

🎉 **That's it! Your pipeline is now running!**

---

## 🔒 Security (Important!)

### **1. Change Default Passwords**

```bash
# Connect to airflow-webserver container
docker-compose exec airflow-webserver airflow users create \
    --username yourusername \
    --firstname Your \
    --lastname Name \
    --role Admin \
    --email your@email.com

# Delete default admin user
docker-compose exec airflow-webserver airflow users delete --username admin
```

### **2. Set Up Firewall**

```bash
# Install UFW (Ubuntu Firewall)
apt install ufw -y

# Allow SSH
ufw allow 22/tcp

# Allow Airflow UI (only from your IP if possible)
ufw allow from YOUR_IP_ADDRESS to any port 8080

# Or allow from anywhere (less secure)
# ufw allow 8080/tcp

# Enable firewall
ufw enable

# Check status
ufw status
```

### **3. Set Up SSL/HTTPS (Recommended)**

Use Nginx as reverse proxy with Let's Encrypt:

```bash
# Install Nginx
apt install nginx certbot python3-certbot-nginx -y

# Create Nginx config
cat > /etc/nginx/sites-available/airflow << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

# Enable site
ln -s /etc/nginx/sites-available/airflow /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx

# Get SSL certificate
certbot --nginx -d your-domain.com
```

Now access via: `https://your-domain.com`

---

## 📂 Data Storage

All data is stored locally in the `data/` directory:

```
data/
├── xml_files/          # Downloaded XML files
│   └── YYYY/MM/DD/
│       └── apc*.xml
├── parsed_csv/         # Parsed trademark data
│   └── YYYY/MM/DD/
│       └── parsed_*.csv
├── scraped_csv/        # Scraped emails
│   └── YYYY/MM/DD/
│       └── scraped_*.csv
└── final_results/      # Final merged data
    └── YYYY/MM/DD/
        └── final_*.csv
```

### **Backup Strategy**

```bash
# Daily backup script
cat > /root/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/root/backups"
DATE=$(date +%Y%m%d)

mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/uspto_data_$DATE.tar.gz \
    /root/uspto_airflow_pipeline/data/final_results/

# Keep only last 30 days
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
EOF

chmod +x /root/backup.sh

# Add to crontab (runs daily at 3 AM)
(crontab -l 2>/dev/null; echo "0 3 * * * /root/backup.sh") | crontab -
```

---

## 🔄 Updates & Maintenance

### **Update Pipeline Code**

```bash
# On your local machine, make changes
# Then transfer updated files

# On server:
cd /root/uspto_airflow_pipeline

# Restart Airflow to pick up changes
docker-compose restart
```

### **View Logs**

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f airflow-scheduler
docker-compose logs -f airflow-webserver
```

### **Restart Services**

```bash
docker-compose restart
```

### **Stop Services**

```bash
docker-compose down
```

### **Update Docker Images**

```bash
docker-compose pull
docker-compose up -d
```

---

## 📊 Monitoring

### **Basic Monitoring**

```bash
# Check disk space
df -h

# Check memory usage
free -h

# Check Docker stats
docker stats
```

### **Set Up Email Alerts**

Notifications go to **account@tminstant.com** (Gmail). Configure the following.

**1. Airflow Variable (optional – this is already the default):**
- In Airflow UI: **Admin** → **Variables** → add `notification_email` = `account@tminstant.com`

**2. Gmail App Password (required for send to work):**

Gmail requires an **App Password**, not your normal account password.

1. For account@tminstant.com, enable 2-Step Verification: [Google Account Security](https://myaccount.google.com/security).
2. Create an App Password: [App Passwords](https://myaccount.google.com/apppasswords) (or search “App passwords” in your Google account).
3. Set it on the server so the pipeline can send mail. Either:

**Option A – Environment variable (recommended):**

Create or edit `.env` in the project root (same folder as `docker-compose.yml`):

```bash
AIRFLOW_SMTP_PASSWORD=your-16-char-app-password
```

Then ensure docker-compose uses it (it already references `AIRFLOW_SMTP_PASSWORD`).

**Option B – In docker-compose.yml (less secure):**

Replace the line:
`AIRFLOW__SMTP__SMTP_PASSWORD: ${AIRFLOW_SMTP_PASSWORD:-}`
with:
`AIRFLOW__SMTP__SMTP_PASSWORD: 'xxxx xxxx xxxx xxxx'`  
(use your real Gmail App Password).

**3. SMTP settings (already in docker-compose.yml for account@tminstant.com):**
- Host: smtp.gmail.com, Port: 587, STARTTLS: true
- User/From: account@tminstant.com
- Password: Gmail App Password (see above)

If the send-email task still fails, check Airflow logs for the `send_summary_email` task and confirm `AIRFLOW_SMTP_PASSWORD` is set and the App Password is correct.

---

## 🔧 Troubleshooting

### **Pipeline Not Running**

```bash
# Check DAG is active
docker-compose exec airflow-webserver airflow dags list

# Check for errors
docker-compose logs airflow-scheduler | grep ERROR

# Manually trigger
docker-compose exec airflow-webserver airflow dags trigger uspto_daily_trademark_pipeline
```

### **Out of Disk Space**

```bash
# Check usage
du -sh data/*

# Clean old files (keep last 30 days)
find data/xml_files/ -mtime +30 -type f -delete
find data/parsed_csv/ -mtime +30 -type f -delete
find data/scraped_csv/ -mtime +30 -type f -delete
```

### **High Memory Usage**

```bash
# Reduce number of parallel scrapes
# Edit config/config.py:
SCRAPE_BATCH_SIZE = 25  # Reduce from 50
```

### **Container Crashes**

```bash
# Increase server resources
# Or reduce Airflow workers in docker-compose.yml
```

---

## 📈 Scaling

### **For Larger Workloads:**

1. **Increase Server Size**
   - Upgrade to 8GB RAM, 4 vCPU
   - Cost: ~$48/month (DigitalOcean)

2. **Use External Database**
   - Replace SQLite/PostgreSQL with managed database
   - AWS RDS, DigitalOcean Managed Database

3. **Add Workers**
   - Use CeleryExecutor instead of LocalExecutor
   - Add worker containers

---

## ✅ Production Checklist

Before going live:

- [ ] Server has adequate resources (4GB+ RAM)
- [ ] Docker and Docker Compose installed
- [ ] Code transferred to server
- [ ] USPTO_API_KEY set in .env
- [ ] Data directory created with proper permissions
- [ ] Airflow started and accessible
- [ ] DAG appears in UI and is enabled
- [ ] Test run completed successfully
- [ ] Default admin password changed
- [ ] Firewall configured
- [ ] SSL/HTTPS set up (optional but recommended)
- [ ] Backup script configured
- [ ] Email notifications configured
- [ ] Monitoring in place

---

## 💡 Tips

1. **Use a domain name** instead of IP address (easier to remember)
2. **Set up automated backups** to S3/Dropbox/Google Drive
3. **Monitor disk usage** - XML files can grow large
4. **Keep Docker images updated** for security patches
5. **Use persistent volumes** for data (already configured)

---

## 🆚 vs. Google Cloud Composer

| Feature | Self-Hosted | Cloud Composer |
|---------|------------|----------------|
| **Cost** | $25-50/month | $300-350/month |
| **Setup** | 30 minutes | 15 minutes |
| **Maintenance** | You manage | Fully managed |
| **Scalability** | Manual | Automatic |
| **Reliability** | Your responsibility | 99.9% SLA |
| **Control** | Full control | Limited |

---

## 📞 Support

**Common Issues:**
- Check logs: `docker-compose logs -f`
- Restart services: `docker-compose restart`
- Check disk space: `df -h`
- Verify DAG syntax: `python dags/uspto_daily_pipeline.py`

---

## 🎉 You're All Set!

Your USPTO pipeline is now running on your own server, saving you hundreds of dollars per month while maintaining full control!

**Access your Airflow UI:**
```
http://your-server-ip:8080
or
https://your-domain.com
```

**Your data is stored at:**
```
/root/uspto_airflow_pipeline/data/final_results/
```

---

**Need help?** Check the logs or review the documentation files in this repository.

**Happy self-hosting! 🚀**

