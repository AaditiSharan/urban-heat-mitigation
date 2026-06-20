Write-Host "Generating Delhi grid data..."
python scripts/generate_delhi_data.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Training model and generating dashboard JSON..."
python scripts/train_and_simulate.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Start dashboard with:"
Write-Host "  cd dashboard"
Write-Host "  npm install"
Write-Host "  npm run dev"
