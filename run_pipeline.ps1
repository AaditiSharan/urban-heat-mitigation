Write-Host "Fetching real Landsat 8 + Sentinel-2 satellite data..."
python scripts/fetch_real_satellite_data.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Validating LST against CPCB stations and UHI benchmarks..."
python scripts/validate_lst.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Training model and generating dashboard JSON..."
python scripts/train_and_simulate.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Start dashboard with:"
Write-Host "  cd dashboard"
Write-Host "  npm install"
Write-Host "  npm run dev"
