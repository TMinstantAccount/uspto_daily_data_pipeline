# PowerShell script to stop local Airflow

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Stopping Local Airflow" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

docker-compose down

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✓ Airflow stopped successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "To start again, run: .\start_local_airflow.ps1" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "✗ Error stopping Airflow" -ForegroundColor Red
    Write-Host ""
    Write-Host "Try: docker-compose down -v" -ForegroundColor Yellow
    Write-Host "(This will also remove volumes)" -ForegroundColor Gray
}

