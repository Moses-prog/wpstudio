web: gunicorn -w 1 --threads 4 --max-requests 50 --max-requests-jitter 10 -b 0.0.0.0:$PORT --timeout 360 web_studio:app
worker: python bot.py
