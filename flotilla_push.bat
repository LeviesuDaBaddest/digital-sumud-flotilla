@echo off
cd /d "%~dp0"
echo 🌊 Starting Digital Sumud Flotilla Tracker...

REM Run the Python script
python update_breadcrumbs_loop.py

REM Always add files to Git (even if unchanged)
echo 📝 Forcing Git add...
git add -A

REM Always try to commit, ignore if nothing changed
echo 📦 Committing...
git commit -m "Auto-update position (forced)" || echo ⚠️ Nothing to commit.

REM Push regardless
echo 🚀 Pushing to GitHub...
git push

REM Log the time
echo [%date% %time%] ✔ Update cycle completed >> log.txt

echo 🟢 Done. Tracker now sleeping 15 minutes...
REM Wait 15 minutes before next cycle
ping 127.0.0.1 -n 901 >nul

REM Loop again
call "%~f0"
