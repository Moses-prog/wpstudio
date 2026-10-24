# WP Studio Deployment Guide

This document outlines the step-by-step procedures for deploying WP Studio in a production environment.

---

## 1. Architecture Overview

WP Studio consists of two concurrent processes:
1. **Web Studio & Mini App (`web_studio.py`)**:
   - High-performance Flask application serving the Telegram Mini App frontend, StoryCraft Studio, CastLock character roster, ClickThumb thumbnail generator, and the Studio Master Administration Suite.
   - Default Port: `8085` (configurable via `PORT` environment variable).
   - Production WSGI runner: `gunicorn -w 2 -b 0.0.0.0:8085 --timeout 120 web_studio:app`.
2. **Telegram Native Bot (`bot.py`)**:
   - MTProto client powered by Telethon handling Telegram commands, inline keyboard menus, photo upload biometrics extraction, and credit wallet workflows.

---

## 2. Pre-Deployment Configuration

### Step 1: Environment Variables
Copy `.env.example` to `.env` on your server and populate your production secrets:

```bash
cp .env.example .env
nano .env
```

Required variables:
- `SUPABASE_URL`: Your Supabase cloud project URL.
- `SUPABASE_KEY`: Your Supabase API service role or anon key.
- `DEFAULT_GEMINI_API_KEY`: Primary Google Gemini API key.
- `API_ID`: Telegram API ID from https://my.telegram.org.
- `API_HASH`: Telegram API Hash from https://my.telegram.org.
- `BOT_TOKEN`: Bot token from @BotFather.
- `PORT`: Web server port (default: `8085`).
- `WEB_APP_URL`: The public HTTPS URL where your Mini App is hosted (e.g., `https://studio.yourdomain.com/miniapp`).

---

## 3. Deployment Options

### Option A: Standard Linux VPS (Ubuntu / Debian)

1. **Clone or copy project files to your server:**
   ```bash
   cd /var/www/webtgp
   ```

2. **Install Python 3.10+ and virtual environment:**
   ```bash
   sudo apt update && sudo apt install -y python3 python3-pip python3-venv
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Make the runner executable:**
   ```bash
   chmod +x start.sh
   ```

4. **Run using Systemd for automatic restart on reboot:**

   Create service file `/etc/systemd/system/wpstudio.service`:
   ```ini
   [Unit]
   Description=WP Studio Production Service
   After=network.target

   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/var/www/webtgp
   EnvironmentFile=/var/www/webtgp/.env
   ExecStart=/var/www/webtgp/start.sh
   Restart=always
   RestartSec=5
   KillMode=mixed
   TimeoutStopSec=10

   [Install]
   WantedBy=multi-user.target
   ```

   Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable wpstudio
   sudo systemctl start wpstudio
   sudo systemctl status wpstudio
   ```

---

### Option B: Docker Container

1. **Build the container image:**
   ```bash
   docker build -t wp-studio:latest .
   ```

2. **Run the container:**
   ```bash
   docker run -d \
     --name wp-studio \
     --restart unless-stopped \
     -p 8085:8085 \
     --env-file .env \
     wp-studio:latest
   ```

---

### Option C: Platform-as-a-Service (Railway / Render)

1. Push code to your Git repository.
2. In Railway or Render:
   - Select **New Web Service**.
   - Build Command: `pip install -r requirements.txt`.
   - Start Command: `./start.sh` or use the provided `Procfile`.
   - Add all environment variables from `.env.example` in the dashboard settings.

---

## 4. Nginx Reverse Proxy & SSL Configuration

Telegram Mini Apps strictly require **HTTPS**. Use Nginx as a reverse proxy with Let's Encrypt SSL:

```nginx
server {
    server_name studio.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8085;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts for heavy GenAI operations
        proxy_connect_timeout 180s;
        proxy_send_timeout 180s;
        proxy_read_timeout 180s;
    }
}
```

Obtain free SSL certificates using Certbot:
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d studio.yourdomain.com
```

---

## 5. Connecting Mini App to Telegram Bot

1. Open Telegram and message **@BotFather**.
2. Run `/myapps` -> Choose your bot (or `/newapp` to create a dedicated web app shortcut).
3. Set Web App URL to:
   `https://studio.yourdomain.com/miniapp`
4. Set Menu Button:
   - Send `/setmenubutton`.
   - Choose your bot.
   - Enter button title: `Open Studio`.
   - Enter URL: `https://studio.yourdomain.com/miniapp`.

---

## 6. Verification Checklist

- [ ] Web app reachable via HTTPS (`https://studio.yourdomain.com/miniapp`).
- [ ] Studio Admin accessible by authorized admin user IDs.
- [ ] CastLock character creation and image uploads functional.
- [ ] StoryCraft generates 10 adaptive concepts with progress gauge.
- [ ] Dual PDFs (Production Bible & Screenplay) download properly from `/generated_pdfs/`.
