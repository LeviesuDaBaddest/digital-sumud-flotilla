@echo off
cd /d "C:\Users\Aiden\flotilla-tracker"
echo 🌊 Starting Digital Sumud Flotilla Tracker...

REM Run Python script which handles all logic (connect, update, push, wait)
python update_breadcrumbs_loop.py

echo 🔁 Python script ended. Restarting...

REM Loop again
call "%~f0"
