@echo off
setlocal
cd /d "%~dp0..\.."

echo.
echo [Lucretia] Clone/update ComfyUI into vendor\ComfyUI
echo.
python scripts\setup_comfyui.py
if errorlevel 1 goto :err
python scripts\local_doctor.py
pause
exit /b 0

:err
echo.
echo ERROR: ComfyUI setup failed. Check Git/Python and the message above.
pause
exit /b 1
