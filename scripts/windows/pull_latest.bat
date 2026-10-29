@echo off
setlocal
cd /d "%~dp0..\.."
echo.
echo [Lucretia] Project root: %CD%
echo.
echo [1/3] Pull latest code
git pull --ff-only
if errorlevel 1 goto :err
echo.
echo [2/3] Install/update Lucretia package editable
python -m pip install -e .
if errorlevel 1 goto :err
echo.
echo [3/3] Local doctor
python scripts\local_doctor.py
echo.
echo Done.
pause
exit /b 0

:err
echo.
echo ERROR: command failed. Read the message above.
pause
exit /b 1
