"""Resolve bundled Playwright Chromium relative to PyInstaller runtime."""
import os
import sys
from pathlib import Path
if getattr(sys, "frozen", False):
    browser_dir = Path(sys._MEIPASS) / "playwright" / "driver" / "package" / ".local-browsers"
    if browser_dir.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
