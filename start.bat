@echo off
setlocal
echo ==========================================================
echo  Starting WP Studio Production Suite (Windows)
echo ==========================================================

set PORT=8085

echo [1/2] Starting Telegram Bot in background...
start /b python bot.py

echo [2/2] Starting Web Studio on port %PORT%...
python web_studio.py

pause
