@echo off
REM Build ClassEye.exe (run setup.bat first).
REM   build_exe.bat              -> dist\ClassEye\ClassEye.exe
REM   build_exe.bat --installer  -> also dist\ClassEye-Setup-<version>.exe + portable zip (needs Inno Setup 6)
cd /d "%~dp0"
call venv\Scripts\activate.bat
pip install -q pyinstaller || goto :fail
python tools\build.py %* || goto :fail
echo.
pause
exit /b 0
:fail
echo BUILD FAILED - send a screenshot.
pause
exit /b 1
