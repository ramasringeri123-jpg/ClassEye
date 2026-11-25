@echo off
cd /d "%~dp0"
if not exist venv (echo Run setup.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
REM Quietly add any library a new version needs (a second or two; skipped when offline)
python -m pip install -q --disable-pip-version-check -r requirements.txt >nul 2>&1 || echo  (Could not check for new libraries - starting anyway)
python app.py
if errorlevel 1 pause
