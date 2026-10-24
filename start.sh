#!/bin/bash
# WP Studio Production Orchestration Runner
export PYTHONUNBUFFERED=1
export MALLOC_ARENA_MAX=2

cleanup() {
  echo "[WP STUDIO] SIGTERM/SIGINT received. Terminating all processes cleanly..."
  kill -TERM "$BOT_PID" "$WEB_PID" 2>/dev/null
  wait "$BOT_PID" "$WEB_PID" 2>/dev/null
  exit 0
}

trap cleanup SIGTERM SIGINT

PORT="${PORT:-8085}"

echo "=========================================================="
echo " Starting WP Studio Production Suite"
echo " Port: $PORT"
echo "=========================================================="

# 1. Start Telegram Bot Daemon
python bot.py &
BOT_PID=$!
echo "[1/2] Telegram Bot Daemon started (PID: $BOT_PID)"

# 2. Start Web Studio & Mini App (Gunicorn if available, fallback to python)
if command -v gunicorn >/dev/null 2>&1; then
  echo "[2/2] Starting Web Studio with Gunicorn WSGI on port $PORT..."
  gunicorn -w 2 -b "0.0.0.0:$PORT" --timeout 120 web_studio:app &
  WEB_PID=$!
else
  echo "[2/2] Starting Web Studio with Python standard server on port $PORT..."
  python web_studio.py &
  WEB_PID=$!
fi

echo "[WP STUDIO] Production services active."
wait $WEB_PID $BOT_PID
cleanup
