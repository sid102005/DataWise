# DataWise — start backend + frontend (uses .venv)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Missing .venv. Run: python -m venv .venv ; .venv\Scripts\Activate.ps1 ; pip install -r requirements.txt"
}

Write-Host "[DataWise] Backend  -> http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "[DataWise] Frontend -> http://localhost:8501" -ForegroundColor Cyan
Write-Host "[DataWise] Press Ctrl+C in either window to stop that process." -ForegroundColor DarkGray

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$PSScriptRoot'; & '$py' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1"
)

Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$PSScriptRoot'; & '$py' -m streamlit run frontend/app.py --server.port 8501"
)

Write-Host "[DataWise] Launched two terminals. Open http://localhost:8501 when Streamlit is ready." -ForegroundColor Green
