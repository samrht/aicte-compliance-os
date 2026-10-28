# Starts the API (port 8000) and the web app (port 5173) in two windows.
# First run: creates the Python venv and installs both sides' dependencies.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path "$root\backend\.venv")) {
    py -3.14 -m venv "$root\backend\.venv"
    & "$root\backend\.venv\Scripts\pip" install fastapi "uvicorn[standard]" sqlmodel lightgbm numpy scikit-learn pillow imagehash pypdf python-multipart cryptography fpdf2 pytest httpx
}
if (-not (Test-Path "$root\frontend\node_modules")) {
    Push-Location "$root\frontend"; npm install; Pop-Location
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npx vite --port 5173"
Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"
