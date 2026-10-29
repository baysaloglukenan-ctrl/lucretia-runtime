@echo off
setlocal
cd /d "%~dp0..\.."

set LUCRETIA_ACCESS_TOKEN=local
set LUCRETIA_COMFY_MODE=managed
set LUCRETIA_COMFY_ROOT=vendor\ComfyUI
set LUCRETIA_COMFY_URL=http://127.0.0.1:8188
set LUCRETIA_COMFY_HOST=127.0.0.1
set LUCRETIA_COMFY_PORT=8188
set LUCRETIA_COMFY_PYTHON=python
set LUCRETIA_COMFY_WORKFLOW=workflows\comfy\ltx23_i2v_api.json
set LUCRETIA_COMFY_AUTO_START=true

echo.
echo [Lucretia] Starting local runtime
echo URL: http://127.0.0.1:8787/?token=local
echo.
python -m pip install -e .
if errorlevel 1 goto :err
echo.
python -m lucretia_runtime.cli serve --host 127.0.0.1 --port 8787
exit /b 0

:err
echo.
echo ERROR: install/start failed. Run scripts\windows\pull_latest.bat first.
pause
exit /b 1
