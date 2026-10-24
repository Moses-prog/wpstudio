# Deploying WP Studio to Render

This guide provides instructions for deploying WP Studio to Render using the GitHub repository:
https://github.com/Moses-prog/wpstudio

---

## 1. Quick Overview

WP Studio runs both the **Web Studio & Mini App** (`web_studio.py`) and the **Telegram Native Bot** (`bot.py`) inside a unified container orchestrated by `start.sh`. Render dynamically provisions the `$PORT` environment variable and routes public HTTPS traffic to your Mini App.

---

## 2. Deployment Method A: Render Blueprint (Recommended)

Render natively supports the included `render.yaml` blueprint:

1. Log into your Render dashboard: https://dashboard.render.com
2. Click **New +** in the top navigation bar and select **Blueprint**.
3. Connect your GitHub account and select repository: `Moses-prog/wpstudio`.
4. Render will parse `render.yaml` and display the environment variable fields.
5. Populate the environment variables (see Section 4 below).
6. Click **Apply**. Render will automatically build the container and deploy the service.

---

## 3. Deployment Method B: Manual Web Service

If you prefer setting up manually without the Blueprint:

1. Go to https://dashboard.render.com -> Click **New +** -> **Web Service**.
2. Select your repository: `Moses-prog/wpstudio`.
3. Configure the following service settings:
   - **Name**: `wpstudio`
   - **Language / Runtime**: `Python 3`
   - **Branch**: `main`
   - **Region**: `Oregon (US West)` or `Frankfurt (EU Central)`
   - **Build Command**:
     ```bash
     pip install --upgrade pip && pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     ./start.sh
     ```
   - **Plan**: `Free` or `Starter`
4. Expand **Advanced** -> Click **Add Environment Variable** to add the required keys (see Section 4).
5. Click **Create Web Service**.

---

## 4. Required Environment Variables on Render

Configure the following variables in **Environment** settings on Render:

| Variable Name | Description | Example / Source |
|---|---|---|
| `PYTHON_VERSION` | Python runtime version | `3.11.9` |
| `SUPABASE_URL` | Supabase Cloud Database URL | `https://your-id.supabase.co` |
| `SUPABASE_KEY` | Supabase Service Role / Anon API Key | `eyJhbGci...` |
| `DEFAULT_GEMINI_API_KEY` | Primary Google Gemini Flash/Pro Key | `AIzaSy...` |
| `API_ID` | Telegram MTProto Client API ID | From https://my.telegram.org |
| `API_HASH` | Telegram MTProto Client API Hash | From https://my.telegram.org |
| `BOT_TOKEN` | Telegram Bot Token from @BotFather | `7877414631:AAEq...` |
| `WEB_APP_URL` | Public Render HTTPS Mini App URL | `https://wpstudio.onrender.com/miniapp` |

---

## 5. Linking Mini App to Telegram Bot

Once Render completes the deployment:

1. Copy your public service URL from the Render dashboard (e.g., `https://wpstudio.onrender.com`).
2. Open Telegram and message **@BotFather**:
   - Send `/setmenubutton`.
   - Select your bot.
   - Enter button title: `Open Studio`.
   - Enter Web App URL: `https://wpstudio.onrender.com/miniapp`.
3. In @BotFather, optionally configure `/newapp` or update existing app settings with the same URL.

---

## 6. Verifying the Deployment

1. **Web Mini App Check**: Open `https://your-service.onrender.com/miniapp` in any browser or Telegram client. Verify the frosted glass loading HUD, StoryCraft Studio, CastLock character roster, and Admin Suite load cleanly.
2. **Bot Health Check**: Send `/start` to your bot in Telegram to verify the native inline keyboard menus respond.
3. **Log Monitoring**: View the real-time build and application logs under the **Logs** tab in Render to confirm both `bot.py` and Gunicorn WSGI workers are active.
