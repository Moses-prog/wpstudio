#!/bin/bash
# WP Studio Production Orchestration Runner
export PYTHONUNBUFFERED=1
export MALLOC_ARENA_MAX=2

cleanup() {
  echo "[WP STUDIO] SIGTERM/SIGINT received. Terminating all processes cleanly..."
  kill -TERM "$BOT_SUPERVISOR_PID" "$WEB_PID" "$PINGER_PID" 2>/dev/null
  wait "$BOT_SUPERVISOR_PID" "$WEB_PID" "$PINGER_PID" 2>/dev/null
  exit 0
}

trap cleanup SIGTERM SIGINT

PORT="${PORT:-8085}"

echo "=========================================================="
echo " Starting WP Studio Production Suite"
echo " Port: $PORT"
echo "=========================================================="

# 1. Start Web Studio & Mini App FIRST (Binds port immediately for Render health checks)
if command -v gunicorn >/dev/null 2>&1; then
  echo "[1/2] Starting Web Studio with Gunicorn WSGI on port $PORT..."
  gunicorn -w 2 -b "0.0.0.0:$PORT" --timeout 120 web_studio:app &
  WEB_PID=$!
else
  echo "[1/2] Starting Web Studio with Python standard server on port $PORT..."
  python web_studio.py &
  WEB_PID=$!
fi

# 2. Start Telegram Bot Daemon with auto-restart supervisor in parallel
(
  while true; do
    echo "[BOT SUPERVISOR] Launching bot.py..."
    python bot.py
    BOT_EXIT=$?
    echo "[BOT SUPERVISOR] bot.py stopped (exit code $BOT_EXIT). Restarting in 3 seconds..."
    sleep 3
  done
) &
BOT_SUPERVISOR_PID=$!
echo "[2/2] Telegram Bot Supervisor started (PID: $BOT_SUPERVISOR_PID)"

# 3. Background keepalive worker (pings public Render URL every 8 mins to prevent idle spin-down)
(
  while true; do
    sleep 480
    TARGET="${WEB_APP_URL:-http://127.0.0.1:$PORT/health}"
    if [[ "$TARGET" == *"onrender.com"* ]]; then
      curl -s -m 15 "$TARGET" >/dev/null 2>&1 || true
    fi
  done
) &
PINGER_PID=$!

echo "[WP STUDIO] Production services active."
wait $WEB_PID $BOT_SUPERVISOR_PID
cleanup
