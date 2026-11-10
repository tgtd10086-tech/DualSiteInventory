@echo off
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt
py -3 -m PyInstaller --noconfirm --clean --windowed --onedir --name DualSiteInventory --hidden-import playwright.sync_api app.py
if errorlevel 1 pause
