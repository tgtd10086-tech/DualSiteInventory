@echo off
chcp 65001 >nul
py -3 -m pip install -r requirements.txt
if errorlevel 1 pause & exit /b 1
py -3 -m playwright install chromium
pause
