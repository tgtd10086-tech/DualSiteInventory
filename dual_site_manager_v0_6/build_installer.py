"""Build Windows executable and bundle Chromium; run only on Windows after deps installation."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
subprocess.run([sys.executable, '-m','playwright','install','chromium'], check=True, env={**os.environ, 'PLAYWRIGHT_BROWSERS_PATH':'0'})
import playwright
pdir = Path(playwright.__file__).resolve().parent
browserdir = pdir / 'driver' / 'package' / '.local-browsers'
if not browserdir.is_dir():
    raise RuntimeError('Chromium browser bundle missing: '+str(browserdir))
args = [sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir',
        '--name','DualSiteInventory','--collect-all','playwright','--hidden-import','tkinter',
        '--runtime-hook',str(root/'runtime_hook.py'),
        '--add-data',str(browserdir)+';playwright/driver/package/.local-browsers', str(root/'app.py')]
subprocess.run(args, check=True, cwd=root)
print('Windows app built in',root/'dist'/'DualSiteInventory')
