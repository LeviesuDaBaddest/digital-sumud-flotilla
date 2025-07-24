@echo off
cd /d "%~dp0"
git add position.json
git commit -m "Update position"
git push