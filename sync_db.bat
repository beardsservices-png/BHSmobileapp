@echo off
REM sync_db.bat — Pull the live Railway database before pushing code.
REM Run this BEFORE "git push" so your new commits include the latest live data.
REM
REM Requirements:
REM   1. Set RAILWAY_URL in this file (your Railway app URL, no trailing slash)
REM   2. Set ADMIN_KEY in this file (same value as ADMIN_KEY env var on Railway)
REM
REM Usage:  sync_db.bat

set RAILWAY_URL=https://YOUR-APP.up.railway.app
set ADMIN_KEY=YOUR_ADMIN_KEY_HERE

echo Downloading live database from Railway...
curl -f -H "X-Admin-Key: %ADMIN_KEY%" "%RAILWAY_URL%/api/admin/backup-db" -o "data\beard_business.db"

if %ERRORLEVEL% neq 0 (
    echo ERROR: Could not download database. Check RAILWAY_URL and ADMIN_KEY above.
    pause
    exit /b 1
)

echo Done! data\beard_business.db is now up to date.
echo.
echo Next steps:
echo   git add data\beard_business.db
echo   git commit -m "sync: pull live DB before deploy"
echo   git push
echo.
pause
