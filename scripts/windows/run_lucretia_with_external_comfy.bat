@echo off
setlocal
cd /d "%~dp0..\.."

set LUCRETIA_ACCESS_TOKEN=local
set LUCRETIA_COMFY_MODE=external
set LUCRETIA_COMFY_URL=http://127.0.0.1:8188
set LUCRETIA_COMFY_WORKFLOW=workflows\comfy\ltx23_i2v_api.json
set LOG_DIR=data\generated\local_logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set LOG_FILE=%LOG_DIR%\lucretia_local_start.log

echo.
echo [Lucretia] Starting runtime for already-running ComfyUI
echo ComfyUI expected at: %LUCRETIA_COMFY_URL%
echo Lucretia URL: http://127.0.0.1:8787/?token=local
echo Log file: %LOG_FILE%
echo.

echo ===== Lucretia local start ===== > "%LOG_FILE%"
echo Folder: %CD% >> "%LOG_FILE%"
python --version >> "%LOG_FILE%" 2>&1
python -m pip install -e . >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :err

python scripts\local_doctor.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :err

echo.
echo Starting server. Keep this window open.
echo If it works, browser opens at: http://127.0.0.1:8787/?token=local
echo.
python -m lucretia_runtime.cli serve --host 127.0.0.1 --port 8787 >> "%LOG_FILE%" 2>&1
goto :err

:err
echo.
echo Lucretia did not stay open.
echo Open this log file and send me its last lines:
echo %CD%\%LOG_FILE%
echo.
type "%LOG_FILE%"
echo.
pause
exit /b 1
