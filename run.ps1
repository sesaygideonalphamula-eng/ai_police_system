# Run this every time you want to start the system.
.\venv\Scripts\Activate.ps1
Write-Host "Starting the server... open http://127.0.0.1:8000 in your browser." -ForegroundColor Green
uvicorn app.main:app --reload
