@echo off
cd /d "%~dp0"

echo Starting Digital Sumud Flotilla Tracker...

:: Run the Python script that updates position and breadcrumbs
python update_breadcrumbs_loop.py

:: Add changes to Git
echo Adding files to Git...
git add position.json positions.json

:: Commit changes (if any)
echo Committing changes...
git commit -m "Auto-update position" || echo Nothing new to commit.

:: Push to GitHub
echo Pushing to GitHub...
git push

echo Done. Python script is now waiting 15 minutes before next update.
pause