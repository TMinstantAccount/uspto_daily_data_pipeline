# Database Setup Guide

This guide explains how to set up the Azure SQL Database table and configure Airflow Variables for the email normalization and database ingestion steps.

## Table Schema

Create the following table in your Azure SQL Database:

```sql
CREATE TABLE uspto_trademark_emails (
    serial_number VARCHAR(50) NOT NULL,
    status_code VARCHAR(10) NOT NULL,
    -- One email per row (same serial_number can repeat for multiple emails)
    email_r_to_sent VARCHAR(2000) NOT NULL,
    refresh_date DATE NOT NULL,
    
    filing_date DATE,
    status_description VARCHAR(500),
    attorney_name VARCHAR(500),
    attorney_email VARCHAR(255),
    correspondent_name VARCHAR(500),
    correspondent_email VARCHAR(500),
    prosecution_date VARCHAR(100),
    prosecution_description VARCHAR(1000),
    url VARCHAR(1000),
    correspondent_address VARCHAR(1000),
    owner_name VARCHAR(500),
    owner_address VARCHAR(1000),
    most_recent_status_date DATE,
    
    created_at DATETIME2 DEFAULT GETDATE(),
    
    PRIMARY KEY (serial_number, status_code, email_r_to_sent)
);
```

### Primary Key Explanation

- **Primary Key**: `serial_number` + `status_code` + `email_r_to_sent` (one row per case per email; same serial_number can repeat for different emails)
- **One row per email**: Each row has a single email in `email_r_to_sent`; the same serial_number can appear multiple rows (one per email).
- **Daily refresh**: Same case can be inserted on different days (different `refresh_date`).
- **Duplicate prevention**: Pipeline checks `serial_number + status_code + email_r_to_sent + refresh_date` to skip duplicates on same day.

### Example Data Structure (one row per email)

```
serial_number | status_code | email_r_to_sent           | refresh_date
--------------|-------------|---------------------------|-------------
12345678      | 630         | attorney@example.com      | 2025-01-15
12345678      | 630         | client@example.com        | 2025-01-15
87654321      | 640         | paralegal@example.com     | 2025-01-15
```

**Note**: If you run the pipeline twice on the same day for the same case and email, the second insert will be skipped (duplicate).

### Migrating from old schema (one row per case)

If your table was created with the previous primary key `(serial_number, status_code)`:

```sql
-- Find current PK name: SELECT name FROM sys.key_constraints WHERE type = 'PK' AND parent_object_id = OBJECT_ID('uspto_trademark_emails');
ALTER TABLE uspto_trademark_emails DROP CONSTRAINT <your_pk_name>;
ALTER TABLE uspto_trademark_emails ADD PRIMARY KEY (serial_number, status_code, email_r_to_sent);
```

**Note:** After migrating, re-run the pipeline so data is re-ingested with one row per email. You may need to clear or backfill existing comma-separated rows.

## Airflow Variables Configuration

Set the following Airflow Variables in your Airflow UI or via CLI:

### Required Variables

1. **Azure SQL Server**
   - Variable Key: `azure_sql_server`
   - Value: Your Azure SQL server name (e.g., `tminstant-sqlserver.database.windows.net`)

2. **Azure SQL Database**
   - Variable Key: `azure_sql_database`
   - Value: Your database name (e.g., `TMinstantSales`)

3. **Authentication Method**
   - Variable Key: `azure_sql_auth_method`
   - Value: Either `sql_server` or `azure_ad`

### For SQL Server Authentication

4. **SQL Server Username**
   - Variable Key: `azure_sql_username`
   - Value: Your SQL Server username

5. **SQL Server Password**
   - Variable Key: `azure_sql_password`
   - Value: Your SQL Server password

### For Azure AD Authentication

4. **Azure AD Account** (Optional)
   - Variable Key: `azure_sql_account`
   - Value: Your Azure AD email (e.g., `account@tminstant.com`)
   - Note: If not provided, you'll be prompted during connection

## Setting Variables via Airflow UI

1. Go to **Admin** → **Variables**
2. Click **+** to add a new variable
3. Enter the Key and Value
4. Click **Save**

## Setting Variables via CLI

### For Self-Hosted Airflow:

```bash
# Set Azure SQL connection variables
airflow variables set azure_sql_server "tminstant-sqlserver.database.windows.net"
airflow variables set azure_sql_database "TMinstantSales"
airflow variables set azure_sql_auth_method "azure_ad"
airflow variables set azure_sql_account "account@tminstant.com"

# Or for SQL Server auth:
airflow variables set azure_sql_auth_method "sql_server"
airflow variables set azure_sql_username "your_username"
airflow variables set azure_sql_password "your_password"
```

### For GCP Composer:

```bash
gcloud composer environments run COMPOSER_ENV \
    --location COMPOSER_LOCATION \
    variables set -- azure_sql_server "tminstant-sqlserver.database.windows.net"

gcloud composer environments run COMPOSER_ENV \
    --location COMPOSER_LOCATION \
    variables set -- azure_sql_database "TMinstantSales"

gcloud composer environments run COMPOSER_ENV \
    --location COMPOSER_LOCATION \
    variables set -- azure_sql_auth_method "azure_ad"

gcloud composer environments run COMPOSER_ENV \
    --location COMPOSER_LOCATION \
    variables set -- azure_sql_account "account@tminstant.com"
```

## Pipeline Flow

The updated pipeline now includes these steps:

1. **download_xml**: Download USPTO XML file
2. **parse_xml**: Parse XML and extract trademark data
3. **scrape_emails**: Scrape emails and prosecution history
4. **merge_data**: Merge parsed and scraped data
5. **normalize_emails**: Split `all_emails` column into individual rows
   - Creates one row per email in `email_r_to_sent` column
   - Adds `refresh_date` column
6. **ingest_to_database**: Insert normalized data into Azure SQL Database
   - Checks for duplicates (same serial_number + status_code + email_r_to_sent + refresh_date)
   - Skips duplicates to prevent re-insertion
   - Returns insertion statistics
7. **generate_summary**: Generate email summary
8. **send_summary_email**: Send email notification with pipeline results

## Email Notification

The email notification now includes:
- Pipeline summary (records extracted, scraping success rate)
- Email extraction results
- Email normalization statistics (input rows, output rows, total emails)
- Database ingestion statistics (rows inserted, skipped duplicates, errors)
- Output file location

## Troubleshooting

### Connection Issues

1. **ODBC Driver**: Make sure ODBC Driver 17 or 18 for SQL Server is installed
   - Windows: Download from Microsoft
   - Linux: Install `unixodbc-dev` and `odbcinst1debian2` packages

2. **Firewall Rules**: Ensure your Airflow server's IP is allowed in Azure SQL firewall rules

3. **Authentication**: For Azure AD, complete MFA authentication when prompted

### Duplicate Handling

The pipeline checks for duplicates using:
- `serial_number` + `status_code` + `email_r_to_sent` + `refresh_date`

If a record with this combination already exists, it will be skipped (not inserted again).

### Testing

You can test the database connection independently:

```python
from scripts.azure_sql_connection import AzureSQLConnection

db = AzureSQLConnection(
    server="your-server.database.windows.net",
    database="your-database",
    auth_method="azure_ad",
    azure_account="your-email@domain.com"
)

if db.connect():
    db.test_connection()
    db.close()
```

## Dependencies

Make sure `pyodbc` is installed:

```bash
pip install pyodbc==5.0.1
```

Or it will be installed automatically from `requirements.txt`.

