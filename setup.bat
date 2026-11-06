@echo off
REM ClassEye - one-time setup on Windows (needs internet, ~10 minutes)
cd /d "%~dp0"
where python >nul 2>&1 || (echo Python is not installed or not on PATH. Install Python 3.12 and tick "Add to PATH". & pause & exit /b 1)

if not exist venv python -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :fail

REM YOLO export needs PyTorch: do it in a separate environment so the app stays light
if not exist models\yolov8n-pose.onnx (
    if not exist venv_models python -m venv venv_models
    venv_models\Scripts\python -m pip install -q --upgrade pip
    venv_models\Scripts\python tools\get_models.py || goto :fail
) else (
    python tools\get_models.py --faces || goto :fail
)

echo.
echo  Setup complete. Start ClassEye with run.bat
pause
exit /b 0
:fail
echo.
echo  SETUP FAILED - send a screenshot of this window.
pause
exit /b 1
