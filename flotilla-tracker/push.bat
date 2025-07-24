@echo off
cd /d "%~dp0"
python update_breadcrumbs_loop.py
git add position.json positions.json
git commit -m "Auto-update position"
git push
pause