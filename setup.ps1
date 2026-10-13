# Run this ONCE after unzipping the project, from inside the policing-ai-system folder.
Write-Host "== Step 1: creating the private environment (venv) ==" -ForegroundColor Cyan
py -3.13 -m venv venv
if (!(Test-Path ".\venv\Scripts\Activate.ps1")) {
    python -m venv venv
}
.\venv\Scripts\Activate.ps1

Write-Host "== Step 2: installing all required packages ==" -ForegroundColor Cyan
pip install --upgrade pip
pip install -r requirements.txt

Write-Host "== Step 3: downloading the English language model for spaCy ==" -ForegroundColor Cyan
python -m spacy download en_core_web_sm

if (!(Test-Path ".env")) {
    Write-Host "== Step 4: creating your .env file from .env.example ==" -ForegroundColor Cyan
    Copy-Item .env.example .env
    Write-Host "IMPORTANT: open .env in VS Code now and set PGPASSWORD to your real PostgreSQL password." -ForegroundColor Yellow
} else {
    Write-Host "== Step 4: .env already exists, leaving it as is ==" -ForegroundColor Cyan
}

Write-Host "== Step 5: creating the database tables and loading data ==" -ForegroundColor Cyan
python -m scripts.seed

Write-Host ""
Write-Host "SETUP COMPLETE. Next time, just run: .\run.ps1" -ForegroundColor Green
