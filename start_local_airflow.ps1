# PowerShell script to start local Airflow for testing
# This provides a simple interface to run Airflow locally

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "USPTO Pipeline - Local Airflow Starter" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    $dockerVersion = docker version 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker not running"
    }
    Write-Host "✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker is not running!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please start Docker Desktop and try again." -ForegroundColor Yellow
    Write-Host "Download Docker Desktop: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "Setting up environment..." -ForegroundColor Yellow

# Create .env file if it doesn't exist
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file..." -ForegroundColor Yellow
    "AIRFLOW_UID=50000" | Out-File -FilePath .env -Encoding ASCII
    Write-Host "✓ .env file created" -ForegroundColor Green
} else {
    Write-Host "✓ .env file exists" -ForegroundColor Green
}

# Create required directories
$dirs = @("logs", "plugins", "test_data")
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "✓ Created $dir directory" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Starting Airflow containers..." -ForegroundColor Yellow
Write-Host "(This may take 2-3 minutes on first run)" -ForegroundColor Cyan
Write-Host ""

docker-compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "Airflow Started Successfully!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Waiting for Airflow to initialize..." -ForegroundColor Yellow
    Write-Host "(This takes about 30-60 seconds)" -ForegroundColor Cyan
    
    # Wait a bit for services to start
    Start-Sleep -Seconds 10
    
    Write-Host ""
    Write-Host "Checking service health..." -ForegroundColor Yellow
    docker-compose ps
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "NEXT STEPS:" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Wait 1-2 minutes for full initialization" -ForegroundColor White
    Write-Host ""
    Write-Host "2. Open Airflow UI in your browser:" -ForegroundColor White
    Write-Host "   http://localhost:8080" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "3. Login with:" -ForegroundColor White
    Write-Host "   Username: admin" -ForegroundColor Yellow
    Write-Host "   Password: admin" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "4. Find your DAG:" -ForegroundColor White
    Write-Host "   Look for: uspto_daily_trademark_pipeline" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "5. Click on the DAG name and select 'Graph' view" -ForegroundColor White
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "USEFUL COMMANDS:" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "View logs:" -ForegroundColor White
    Write-Host "  docker-compose logs -f" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Stop Airflow:" -ForegroundColor White
    Write-Host "  docker-compose down" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Restart Airflow:" -ForegroundColor White
    Write-Host "  docker-compose restart" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Check status:" -ForegroundColor White
    Write-Host "  docker-compose ps" -ForegroundColor Gray
    Write-Host ""
    
    # Optionally open browser
    Write-Host "Would you like to open the Airflow UI now? (Y/N)" -ForegroundColor Yellow
    $response = Read-Host
    if ($response -eq 'Y' -or $response -eq 'y') {
        Start-Sleep -Seconds 15  # Give it a bit more time
        Start-Process "http://localhost:8080"
        Write-Host "✓ Opening browser..." -ForegroundColor Green
    }
    
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Error Starting Airflow" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check the error messages above." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Common issues:" -ForegroundColor Yellow
    Write-Host "1. Docker Desktop not running" -ForegroundColor White
    Write-Host "2. Port 8080 already in use" -ForegroundColor White
    Write-Host "3. Insufficient memory (need 8GB)" -ForegroundColor White
    Write-Host ""
    Write-Host "For help, see: LOCAL_TESTING_GUIDE.md" -ForegroundColor Yellow
}

