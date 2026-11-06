@echo off
REM Build ClassEye.exe (run setup.bat first)
cd /d "%~dp0"
call venv\Scripts\activate.bat
pip install -q pyinstaller || goto :fail
pyinstaller --noconfirm --clean --windowed --name ClassEye ^
  --collect-binaries onnxruntime --hidden-import pygrabber.dshow_graph ^
  --exclude-module torch --exclude-module ultralytics --exclude-module matplotlib ^
  --exclude-module pandas --exclude-module scipy --exclude-module tkinter ^
  --exclude-module onnxruntime.quantization --exclude-module onnxruntime.transformers ^
  --exclude-module onnxruntime.tools app.py || goto :fail
xcopy /E /I /Y models dist\ClassEye\models >nul
if exist data xcopy /E /I /Y data dist\ClassEye\data >nul
echo.
echo  Done: dist\ClassEye\ClassEye.exe
pause
exit /b 0
:fail
echo BUILD FAILED - send a screenshot.
pause
exit /b 1
