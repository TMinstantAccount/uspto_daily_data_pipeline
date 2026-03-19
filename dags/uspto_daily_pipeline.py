"""
USPTO Daily Trademark Data Pipeline - Airflow DAG (Self-Hosted Version)

This DAG runs daily to:
1. Wait for USPTO data to become available (sensor)
2. Download latest USPTO XML file
3. Parse XML and extract trademark data
4. Scrape attorney/correspondent emails and prosecution history
5. Merge all data and save to local storage
6. Normalize emails (one row per case, comma-separated emails)
7. Ingest data into Azure SQL Database
8. Write daily pipeline summary to dbo.uspto_pipeline_daily_summary

Schedule: Daily at 4:00 AM CST (10:00 UTC)
USPTO publishes each day's XML data feed around 12:00 AM EST.

Manual override:
    Set Airflow Variable  manual_target_date = "YYYY-MM-DD"  then trigger the DAG.
    Clear the variable (set to "" or delete it) to resume normal scheduled runs.
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.python import PythonSensor
from airflow.models import Variable
from airflow.utils.trigger_rule import TriggerRule
import pendulum
import sys
import os
import logging

logger = logging.getLogger(__name__)

EST = pendulum.timezone("America/New_York")

# Add scripts directory to Python path
dag_folder = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(dag_folder)
sys.path.insert(0, project_root)

from scripts import download_xml, parse_xml, scrape_emails, merge_data, normalize_emails, ingest_to_database

try:
    notification_email = Variable.get('notification_email', default_var='account@tminstant.com')
except Exception:
    notification_email = 'account@tminstant.com'

default_args = {
    'owner': 'trademark-pipeline',
    'depends_on_past': False,
    'email': [notification_email],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(hours=2),
}

dag = DAG(
    'uspto_daily_trademark_pipeline',
    default_args=default_args,
    description='Daily USPTO trademark data extraction and processing (Self-Hosted)',
    schedule_interval='0 10 * * *',  # 4:00 AM CST = 10:00 UTC
    start_date=datetime(2025, 12, 1, tzinfo=EST),
    catchup=False,
    tags=['uspto', 'trademark', 'daily', 'self-hosted'],
    max_active_runs=1,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_FORMATS = ['%Y-%m-%d', '%m-%d-%Y', '%m/%d/%Y', '%Y/%m/%d']


def _get_manual_date():
    """Return a datetime if the Airflow Variable 'manual_target_date' is set, else None.

    Accepts formats: YYYY-MM-DD, MM-DD-YYYY, MM/DD/YYYY, YYYY/MM/DD.
    """
    try:
        raw = Variable.get('manual_target_date', default_var='')
        if not raw or not raw.strip():
            return None
        value = raw.strip()
        for fmt in _DATE_FORMATS:
            try:
                dt = datetime.strptime(value, fmt)
                logger.info(f"Manual override active — target date: {dt.strftime('%Y-%m-%d')}")
                return dt
            except ValueError:
                continue
        logger.warning(
            f"Invalid manual_target_date '{value}'. "
            f"Use YYYY-MM-DD (e.g. 2026-03-05) or MM-DD-YYYY (e.g. 3-05-2026)."
        )
    except Exception:
        pass
    return None


def _resolve_target_date(context):
    """Return the manual date if set, otherwise the Airflow execution_date."""
    manual = _get_manual_date()
    if manual:
        return manual
    return context['execution_date']


def _get_xml_file_date(context):
    """Pull the XML file date from XCom (set by download task) and parse it."""
    ti = context['task_instance']
    xml_file_date_str = ti.xcom_pull(task_ids='download_xml', key='xml_file_date')
    if xml_file_date_str:
        return datetime.strptime(xml_file_date_str, '%Y-%m-%d')
    return _resolve_target_date(context)


def _get_max_rows():
    """Return row limit from Airflow Variable 'max_rows', or None for no limit.

    Set max_rows to a number (e.g. 10) for testing. Clear it or set to 0 for production.
    """
    try:
        raw = Variable.get('max_rows', default_var='')
        if raw and raw.strip():
            value = int(raw.strip())
            if value > 0:
                logger.info(f"TEST MODE: max_rows={value}")
                return value
    except (ValueError, Exception):
        pass
    return None


# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------

def check_data_availability(**context):
    """Sensor callable: return True when USPTO data is available for the target date."""
    target_date = _resolve_target_date(context)
    file_info = download_xml.get_latest_file_info(target_date)
    if file_info:
        logger.info(f"USPTO data available: {file_info.get('fileName')}")
        return True
    logger.info(f"USPTO data not yet available for {target_date.strftime('%Y-%m-%d')}, will retry...")
    return False


def download_xml_task(**context):
    """Task: Download USPTO XML file"""
    target_date = _resolve_target_date(context)

    result = download_xml.main(target_date=target_date, **context)

    ti = context['task_instance']
    ti.xcom_push(key='gcs_xml_path', value=result['gcs_path'])
    ti.xcom_push(key='file_name', value=result['file_name'])
    ti.xcom_push(key='xml_file_date', value=result['xml_file_date'])

    return result


def parse_xml_task(**context):
    """Task: Parse XML file"""
    ti = context['task_instance']
    gcs_xml_path = ti.xcom_pull(task_ids='download_xml', key='gcs_xml_path')

    if not gcs_xml_path:
        raise ValueError("No XML path received from download task")

    target_date = _get_xml_file_date(context)
    max_rows = _get_max_rows()

    result = parse_xml.main(gcs_xml_path=gcs_xml_path, target_date=target_date, max_rows=max_rows, **context)

    ti.xcom_push(key='gcs_parsed_csv', value=result['gcs_csv_path'])
    ti.xcom_push(key='record_count', value=result['record_count'])

    return result


def scrape_emails_task(**context):
    """Task: Scrape emails and prosecution history"""
    ti = context['task_instance']
    gcs_parsed_csv = ti.xcom_pull(task_ids='parse_xml', key='gcs_parsed_csv')

    if not gcs_parsed_csv:
        raise ValueError("No parsed CSV path received from parse task")

    target_date = _get_xml_file_date(context)
    max_rows = _get_max_rows()

    result = scrape_emails.main(
        gcs_parsed_csv_path=gcs_parsed_csv,
        target_date=target_date,
        max_rows=max_rows,
        **context
    )

    ti.xcom_push(key='gcs_scraped_csv', value=result['gcs_csv_path'])
    ti.xcom_push(key='scrape_stats', value={
        'total': result['total_urls'],
        'successful': result['successful'],
        'failed': result['failed'],
        'success_rate': result['success_rate']
    })

    return result


def merge_data_task(**context):
    """Task: Merge all data"""
    ti = context['task_instance']
    gcs_parsed_csv = ti.xcom_pull(task_ids='parse_xml', key='gcs_parsed_csv')
    gcs_scraped_csv = ti.xcom_pull(task_ids='scrape_emails', key='gcs_scraped_csv')

    if not gcs_parsed_csv or not gcs_scraped_csv:
        raise ValueError("Missing CSV paths from previous tasks")

    target_date = _get_xml_file_date(context)

    result = merge_data.main(
        gcs_parsed_csv_path=gcs_parsed_csv,
        gcs_scraped_csv_path=gcs_scraped_csv,
        target_date=target_date,
        **context
    )

    ti.xcom_push(key='gcs_final_path', value=result['gcs_final_path'])
    ti.xcom_push(key='metrics', value=result['metrics'])

    return result


def normalize_emails_task(**context):
    """Task: Normalize emails - split all_emails into individual rows"""
    ti = context['task_instance']
    gcs_final_csv = ti.xcom_pull(task_ids='merge_data', key='gcs_final_path')

    if not gcs_final_csv:
        raise ValueError("No final CSV path received from merge task")

    target_date = _get_xml_file_date(context)

    result = normalize_emails.main(gcs_final_csv_path=gcs_final_csv, target_date=target_date, **context)

    ti.xcom_push(key='gcs_normalized_csv', value=result['gcs_csv_path'])
    ti.xcom_push(key='normalize_stats', value={
        'input_rows': result['input_rows'],
        'output_rows': result['output_rows'],
        'total_emails': result['total_emails'],
        'refresh_date': result['refresh_date']
    })

    return result


def ingest_to_database_task(**context):
    """Task: Ingest normalized data into Azure SQL Database"""
    ti = context['task_instance']
    gcs_normalized_csv = ti.xcom_pull(task_ids='normalize_emails', key='gcs_normalized_csv')

    if not gcs_normalized_csv:
        raise ValueError("No normalized CSV path received from normalize_emails task")

    target_date = _get_xml_file_date(context)

    result = ingest_to_database.main(gcs_normalized_csv_path=gcs_normalized_csv, target_date=target_date, **context)

    ti.xcom_push(key='db_stats', value={
        'total_rows': result['total_rows'],
        'inserted': result['inserted'],
        'skipped_duplicates': result['skipped_duplicates'],
        'errors': result['errors'],
        'refresh_date': result['refresh_date']
    })

    return result


def pipeline_summary_task(**context):
    """
    Final task: write one summary row to dbo.uspto_pipeline_daily_summary.

    Runs with trigger_rule='all_done' so it executes even when upstream tasks
    fail, capturing the pipeline status (SUCCESS / FAILED / PARTIAL).
    """
    ti = context['task_instance']

    # ---- resolve data_fetch_date ----
    xml_file_date_str = ti.xcom_pull(task_ids='download_xml', key='xml_file_date')
    if xml_file_date_str:
        from datetime import datetime as _dt
        data_fetch_date = _dt.strptime(xml_file_date_str, '%Y-%m-%d').date()
    else:
        data_fetch_date = _resolve_target_date(context).date()

    # ---- resolve rows_processed from ingest XCom ----
    db_stats = ti.xcom_pull(task_ids='ingest_to_database', key='db_stats') or {}
    rows_processed = db_stats.get('total_rows', 0)

    # ---- determine overall pipeline status ----
    upstream_task_ids = [
        'download_xml', 'parse_xml', 'scrape_emails',
        'merge_data', 'normalize_emails', 'ingest_to_database',
    ]
    failed_tasks = [
        tid for tid in upstream_task_ids
        if ti.xcom_pull(task_ids=tid) is None
        and context['dag_run'].get_task_instance(tid).state not in ('success', 'skipped')
    ]

    if not failed_tasks:
        status = 'SUCCESS'
        error_message = None
    elif rows_processed > 0:
        status = 'PARTIAL'
        error_message = f"Failed tasks: {', '.join(failed_tasks)}"
    else:
        status = 'FAILED'
        error_message = f"Failed tasks: {', '.join(failed_tasks)}"

    dag_run_id = context['dag_run'].run_id

    logger.info(
        f"Writing pipeline summary — date={data_fetch_date} "
        f"rows={rows_processed} status={status} dag_run_id={dag_run_id}"
    )

    ingest_to_database.write_pipeline_summary(
        data_fetch_date=data_fetch_date,
        rows_processed=rows_processed,
        status=status,
        dag_run_id=dag_run_id,
        error_message=error_message,
    )


# Define tasks
task_0_sensor = PythonSensor(
    task_id='wait_for_data',
    python_callable=check_data_availability,
    poke_interval=600,        # Check every 10 minutes
    timeout=7200,             # Wait up to 2 hours for data to appear
    mode='poke',
    dag=dag,
)

task_1_download = PythonOperator(
    task_id='download_xml',
    python_callable=download_xml_task,
    provide_context=True,
    retries=4,
    retry_delay=timedelta(minutes=10),
    dag=dag,
)

task_2_parse = PythonOperator(
    task_id='parse_xml',
    python_callable=parse_xml_task,
    provide_context=True,
    dag=dag,
)

task_3_scrape = PythonOperator(
    task_id='scrape_emails',
    python_callable=scrape_emails_task,
    provide_context=True,
    dag=dag,
)

task_4_merge = PythonOperator(
    task_id='merge_data',
    python_callable=merge_data_task,
    provide_context=True,
    dag=dag,
)

task_5_normalize = PythonOperator(
    task_id='normalize_emails',
    python_callable=normalize_emails_task,
    provide_context=True,
    dag=dag,
)

task_6_ingest_db = PythonOperator(
    task_id='ingest_to_database',
    python_callable=ingest_to_database_task,
    provide_context=True,
    dag=dag,
)

task_7_summary = PythonOperator(
    task_id='write_pipeline_summary',
    python_callable=pipeline_summary_task,
    provide_context=True,
    trigger_rule=TriggerRule.ALL_DONE,  # runs even if upstream tasks fail
    dag=dag,
)

# Define task dependencies
task_0_sensor >> task_1_download >> task_2_parse >> task_3_scrape >> task_4_merge >> task_5_normalize >> task_6_ingest_db >> task_7_summary
