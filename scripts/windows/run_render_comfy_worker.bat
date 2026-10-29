@echo off
setlocal
cd /d "%~dp0\..\.."
if exist ".git" (
  git pull --ff-only
  if errorlevel 1 goto :err
)
if "%LUCRETIA_WORKER_TOKEN%"=="" (
  set /p LUCRETIA_WORKER_TOKEN=Render worker token: 
)
set LUCRETIA_COMFY_MODE=external
set LUCRETIA_COMFY_URL=http://127.0.0.1:8188
set PY_CMD=python
where python >nul 2>&1
if errorlevel 1 set PY_CMD=py
%PY_CMD% -m pip install -e .
if errorlevel 1 goto :err
%PY_CMD% scripts\comfy_render_worker.py --root .
exit /b 0

:err
echo.
echo Lucretia Render worker failed to start.
pause
exit /b 1
