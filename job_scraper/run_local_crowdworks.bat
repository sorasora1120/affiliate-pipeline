@echo off
cd /d "%~dp0"
set PLATFORMS=crowdworks
if not exist logs mkdir logs
"C:\Users\優空\AppData\Local\Programs\Python\Python312\python.exe" main.py >> "logs\crowdworks_%date:~-4%-%date:~4,2%-%date:~7,2%.log" 2>&1
