@echo off
rem Starts PaperAid locally: the API/worker on port 8000 and the website on http://localhost:5000.
rem First run installs everything (a few minutes). Close the two windows to stop PaperAid.
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo Setting up the Python backend...
  python -m venv backend\.venv || goto :error
  backend\.venv\Scripts\python -m pip install --quiet -e "backend[dev]" || goto :error
)
if not exist "web\node_modules" (
  echo Installing the website...
  pushd web
  call npm install || goto :error
  popd
)
if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul

rem The backend reads its AI keys from backend\.env. Clear any keys inherited from Windows settings
rem (another tool may have set an older one), or they would take priority over the .env file.
set "ANTHROPIC_API_KEY="
set "OPENAI_API_KEY="
start "PaperAid backend (port 8000)" /D "%~dp0backend" cmd /k .venv\Scripts\python -m uvicorn app.main:app --port 8000
start "PaperAid website (port 5000)" /D "%~dp0web" cmd /k npm run dev
echo Starting... PaperAid will open in your browser.
timeout /t 6 /nobreak >nul
start "" http://localhost:5000
exit /b 0

:error
echo.
echo Setup failed. Check that Python 3.12+ and Node.js 20+ are installed, then run this file again.
pause
exit /b 1
