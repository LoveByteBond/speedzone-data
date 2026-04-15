@echo off
REM ============================================================
REM  SpeedZonePro data scraper - Windows launcher
REM
REM  Double-click this file to:
REM    1. Install required Python packages (if missing)
REM    2. Run the scraper
REM    3. Commit the updated zones.json to Git
REM    4. Push to GitHub
REM
REM  First time only: make sure Python and Git are installed.
REM  See README.md for setup instructions.
REM ============================================================

cd /d "%~dp0"

echo.
echo === SpeedZonePro data scraper ===
echo.

REM Step 1: ensure dependencies
echo [setup] Checking Python packages...
python -m pip install --quiet --user requests beautifulsoup4
if errorlevel 1 (
    echo ERROR: pip install failed. Is Python installed?
    echo Download Python from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

REM Step 2: run scraper
echo.
echo [run] Scraping YolRadar and geocoding...
echo       This takes 5-20 minutes on first run.
echo       Subsequent runs use the geocode cache and complete in under 5 min.
echo.
python scraper.py %*
if errorlevel 1 (
    echo ERROR: scraper failed.
    pause
    exit /b 1
)

REM Step 3: commit + push (only if git is available and there are changes)
echo.
echo [git] Committing and pushing to GitHub...
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo       Not a git repository - skipping push.
    echo       See README.md for how to set up GitHub Pages.
    pause
    exit /b 0
)

git add zones.json geocode-cache.json
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Update zones.json"
    git push
    echo.
    echo Done. zones.json pushed to GitHub.
) else (
    echo       No changes - zones.json is already up to date.
)

echo.
pause
