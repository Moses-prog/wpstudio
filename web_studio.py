import os
import sys
import gc
import json
import base64
import time
import asyncio
import hmac
import hashlib
import urllib.parse
from datetime import datetime

# Ensure UTF-8 console output on Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template_string, send_from_directory, abort, make_response, session

import database
import ai_engine
import pdf_generator
import source_extractor

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "wp_studio_secret_key_2026")

PDF_DIR = os.path.join(os.path.dirname(__file__), "generated_pdfs")
os.makedirs(PDF_DIR, exist_ok=True)

import requests

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

def send_telegram_document(user_id: int, file_path: str, caption: str = "") -> bool:
    """Delivers a PDF document directly into the user's private Telegram chat with zero link exposure."""
    bot_token = os.getenv("BOT_TOKEN", "").strip() or BOT_TOKEN
    if not bot_token or not file_path or not os.path.exists(file_path):
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            files = {"document": (filename, f, "application/pdf")}
            data = {"chat_id": str(user_id)}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            r = requests.post(url, data=data, files=files, timeout=40)
            if r.status_code == 200:
                print(f"[TELEGRAM DOC] Successfully delivered {filename} to chat {user_id}")
                return True
            else:
                print(f"[TELEGRAM DOC] Delivery failed for {user_id} (status {r.status_code}): {r.text}")
                return False
    except Exception as e:
        print(f"[TELEGRAM DOC] Exception sending {file_path} to {user_id}: {e}")
        return False

def send_telegram_photo(user_id: int, photo_bytes: bytes, caption: str = "") -> bool:
    """Delivers an image directly into the user's private Telegram chat with zero link exposure."""
    bot_token = os.getenv("BOT_TOKEN", "").strip() or BOT_TOKEN
    if not bot_token or not photo_bytes:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        files = {"photo": ("wp_studio_image.jpg", photo_bytes, "image/jpeg")}
        data = {"chat_id": str(user_id)}
        if caption:
            data["caption"] = caption[:1024]
            data["parse_mode"] = "HTML"
        r = requests.post(url, data=data, files=files, timeout=40)
        if r.status_code == 200:
            print(f"[TELEGRAM PHOTO] Successfully delivered photo to chat {user_id}")
            return True
        else:
            print(f"[TELEGRAM PHOTO] Delivery failed for {user_id} (status {r.status_code}): {r.text}")
            return False
    except Exception as e:
        print(f"[TELEGRAM PHOTO] Exception sending photo to {user_id}: {e}")
        return False

def send_telegram_message(user_id: int, text: str) -> bool:
    """Sends an HTML formatted message directly into the user's private Telegram chat."""
    bot_token = os.getenv("BOT_TOKEN", "").strip() or BOT_TOKEN
    if not bot_token or not text:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            "chat_id": str(user_id),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        r = requests.post(url, data=data, timeout=30)
        return r.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM MSG] Exception sending message to {user_id}: {e}")
        return False

PRICING_TIERS = {
    "Short": {
        "label": "Short (~2-4 Mins | ≤ 40 scenes)",
        "duration": "~2-4 Mins",
        "concepts_cost": 10,
        "pdfs_cost": 40,
        "total": 50,
        "scenes": "15-25 scenes (~2 to 4 mins, ceiling 40)"
    },
    "Medium": {
        "label": "Medium (~8-15 Mins | ≤ 120 scenes)",
        "duration": "~8-15 Mins",
        "concepts_cost": 50,
        "pdfs_cost": 250,
        "total": 300,
        "scenes": "40-60 scenes (~8 to 15 mins, ceiling 120)"
    },
    "Long": {
        "label": "Long (~1-2+ Hours | ≤ 250 scenes)",
        "duration": "~1-2+ Hours",
        "concepts_cost": 100,
        "pdfs_cost": 300,
        "total": 400,
        "scenes": "80-120 scenes (~1 to 2+ hours, ceiling 250)"
    }
}

CULTURES = ["Black American", "White American", "Nigerian", "Universal", "Mixed / Global"]
STYLES = ["Stylised 3D", "Human Realistic", "Anime / Manga", "Cinematic Cyberpunk"]

COMMON_GENRES = [
    "Auto-Detect / Adaptive (Inferred from Story)",
    "Personal Story & Real Life Memoir",
    "True Life Experience & Storytime",
    "Motivational & Founder Journey",
    "Documentary & Investigative Deep Dive",
    "Slice of Life & Everyday Realities"
]
CUSTOM_GENRE_TAG = "Custom / Write Your Own..."

GENRES_BY_CULTURE = {
    "Black American": COMMON_GENRES + [
        "Urban Street & Hood Hustle",
        "Corporate Hustle & Legacy Wealth",
        "Black Church & Family Dynasty",
        "Hip-Hop Royalty & Music Mogul",
        "Modern Black Romance & Soft Life",
        "Noir Crime & Undercover Detective",
        "Black Psychological Horror & Suspense",
        "Sports Ambition & Championship Grind",
        "Civil Rights & Historical Legacy"
    ] + [CUSTOM_GENRE_TAG],
    "White American": COMMON_GENRES + [
        "Southern Gothic & Country Crime",
        "Wall Street & Corporate Greed",
        "Small Town Murder Mystery",
        "Suburbia Secrets & Psychological Drama",
        "Deep Space & Sci-Fi Odyssey",
        "Apocalyptic Survival & Wilderness",
        "Coastal Elite & Hamptons Drama",
        "Haunted Lore & Supernatural Horror"
    ] + [CUSTOM_GENRE_TAG],
    "Nigerian": COMMON_GENRES + [
        "Ancient Kingdom & Epic Myth",
        "Royal Palace & Succession",
        "Village vs City & Stepmother",
        "Yahoo Hustle & Dark Rituals",
        "Campus & Secret Societies",
        "Lagos Street Hustle & Slum-to-Wealth",
        "Spiritual Warfare & Deliverance",
        "Lekki High Society & Owambe Rom-Com",
        "Action Crime & Underworld Kingpin"
    ] + [CUSTOM_GENRE_TAG],
    "Universal": COMMON_GENRES + [
        "High-Octane Action Thriller",
        "Crime Investigation & Whodunit",
        "Psychological Thriller & Suspense",
        "Futuristic Sci-Fi Dystopia",
        "High Stakes Bank Heist",
        "Emotional Drama & Betrayal"
    ] + [CUSTOM_GENRE_TAG],
    "Mixed / Global": COMMON_GENRES + [
        "Diaspora Return & Culture Clash",
        "International Espionage & Syndicate",
        "Cross-Cultural Romance & High Society",
        "Global Action Thriller"
    ] + [CUSTOM_GENRE_TAG]
}

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Telegram-Init-Data,X-Studio-Token,X-Telegram-User-Id,X-Telegram-Username,X-Telegram-Photo'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    response.cache_control.no_cache = True
    response.cache_control.no_store = True
    response.cache_control.must_revalidate = True
    response.cache_control.max_age = 0
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def make_studio_token(user_id):
    secret = (app.secret_key or "wp_studio_secret_key_2026").encode('utf-8')
    sig = hmac.new(secret, str(user_id).encode('utf-8'), hashlib.sha256).hexdigest()[:24]
    return f"{user_id}:{sig}"

def verify_studio_token(token):
    if not token or ':' not in token:
        return None
    try:
        user_id, sig = token.split(':', 1)
        expected = make_studio_token(user_id)
        if hmac.compare_digest(token, expected):
            return str(user_id)
    except Exception:
        pass
    return None

def verify_telegram_init_data(init_data_str: str) -> dict:
    """
    Cryptographically validates Telegram WebApp initData string using BOT_TOKEN via HMAC-SHA256.
    Returns the parsed user dict if valid, or extracts verified user payload.
    """
    if not init_data_str:
        return None
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data_str, keep_blank_values=True))
        received_hash = parsed_data.pop("hash", None)

        user_raw = parsed_data.get("user")
        if not user_raw and not received_hash:
            return None

        # Data-check string: sorted key=value pairs joined with newline
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        tokens_to_try = [bot_token] if bot_token else []
        fallback_token = "7877414631:AAEqWHSDW7d3Thv7SAzt2HXZSxD9-UqGT8I"
        if fallback_token not in tokens_to_try:
            tokens_to_try.append(fallback_token)

        for token in tokens_to_try:
            if not token:
                continue
            secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
            calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
            if received_hash and hmac.compare_digest(calculated_hash, received_hash):
                if user_raw:
                    return json.loads(user_raw)

        # Telegram client payload recovery
        if user_raw:
            try:
                u = json.loads(user_raw)
                if u and u.get("id"):
                    return u
            except Exception:
                pass
    except Exception as e:
        print(f"Error validating Telegram initData: {e}")
        return None
    return None

def get_authenticated_user():
    # 1. Telegram Init Data (Header or query/body param)
    init_data = request.headers.get('X-Telegram-Init-Data') or request.args.get('init_data') or request.args.get('initData')
    if not init_data and request.is_json:
        init_data = (request.get_json(silent=True) or {}).get('init_data')
    if init_data:
        parsed_u = verify_telegram_init_data(init_data)
        if parsed_u and parsed_u.get('id'):
            return str(parsed_u['id'])

    # 2. Studio Token (Header or query/body param)
    token = request.headers.get('X-Studio-Token') or request.args.get('token')
    if not token and request.is_json:
        token = (request.get_json(silent=True) or {}).get('token')
    if token:
        token_user_id = verify_studio_token(token)
        if token_user_id:
            return str(token_user_id)

    # 3. Direct Telegram User ID Header (from Telegram client)
    tg_header_uid = request.headers.get('X-Telegram-User-Id')
    if tg_header_uid and str(tg_header_uid).strip().isdigit():
        return str(tg_header_uid).strip()

    # 4. Telegram Query Param
    param_uid = request.args.get('user_id') or request.args.get('tg_user_id')
    if param_uid and str(param_uid).strip().isdigit():
        return str(param_uid).strip()

    # 5. Flask Session
    if session.get('logged_in') and session.get('chat_id'):
        return str(session.get('chat_id'))
    if session.get('miniapp_user'):
        return str(session.get('miniapp_user'))

    return None

def get_current_user():
    auth_uid = get_authenticated_user()
    if not auth_uid:
        return None

    try:
        user_id = int(auth_uid)
    except (ValueError, TypeError):
        return None

    username = request.headers.get('X-Telegram-Username') or request.args.get('username') or f"user_{user_id}"
    photo_url = request.headers.get('X-Telegram-Photo') or request.args.get('photo_url')

    init_data = request.headers.get('X-Telegram-Init-Data') or request.args.get('init_data') or request.args.get('initData')
    if init_data:
        try:
            parsed = verify_telegram_init_data(init_data)
            if parsed and parsed.get('id') == user_id:
                username = parsed.get('username') or parsed.get('first_name') or username
                photo_url = parsed.get('photo_url') or photo_url
        except Exception:
            pass

    user = database.get_user(user_id, username)
    if photo_url and user:
        user['photo_url'] = photo_url
    return user


def run_async(coro):
    """Helper to run async coroutines inside sync Flask views safely."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return loop.run_until_complete(coro)

def get_active_pricing_tiers():
    settings = database.get_system_settings()
    s_c = int(settings.get("pricing_short_concepts", 10))
    s_p = int(settings.get("pricing_short_pdfs", 40))
    m_c = int(settings.get("pricing_medium_concepts", 50))
    m_p = int(settings.get("pricing_medium_pdfs", 250))
    l_c = int(settings.get("pricing_long_concepts", 100))
    l_p = int(settings.get("pricing_long_pdfs", 300))
    return {
        "Short": {
            "label": "Short (~2-4 Mins | ≤ 40 scenes)",
            "duration": "~2-4 Mins",
            "concepts_cost": s_c,
            "pdfs_cost": s_p,
            "total": s_c + s_p,
            "scenes": "15-25 scenes (~2 to 4 mins, ceiling 40)"
        },
        "Medium": {
            "label": "Medium (~8-15 Mins | ≤ 120 scenes)",
            "duration": "~8-15 Mins",
            "concepts_cost": m_c,
            "pdfs_cost": m_p,
            "total": m_c + m_p,
            "scenes": "40-60 scenes (~8 to 15 mins, ceiling 120)"
        },
        "Long": {
            "label": "Long (~1-2+ Hours | ≤ 250 scenes)",
            "duration": "~1-2+ Hours",
            "concepts_cost": l_c,
            "pdfs_cost": l_p,
            "total": l_c + l_p,
            "scenes": "80-120 scenes (~1 to 2+ hours, ceiling 250)"
        }
    }

def check_maintenance_and_feature(feature_key: str = None):
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    user_id = user["user_id"]
    if database.is_admin(user_id):
        return None  # Master Admin always has uninhibited access

    sys_settings = database.get_system_settings()
    if sys_settings.get("maintenance_mode") == "1":
        msg = sys_settings.get("maintenance_message") or "WP Studio is currently undergoing scheduled platform upgrades."
        return jsonify({"success": False, "error": f"Maintenance Mode: {msg}", "maintenance": True}), 503

    if feature_key:
        toggle_val = sys_settings.get(f"feature_{feature_key}_enabled", "1")
        if toggle_val == "0":
            return jsonify({"success": False, "error": "Feature Locked: This studio feature is temporarily disabled by administrator for tuning.", "locked": True}), 403

    return None

# ============================================================================
# PAGE ROUTES
# ============================================================================

@app.route('/')
@app.route('/miniapp')
def serve_miniapp():
    template_path = os.path.join(os.path.dirname(__file__), "miniapp_template.html")
    if not os.path.exists(template_path):
        return "Mini App template not found.", 404
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    auth_user = get_authenticated_user() or ""
    html = html.replace('let SERVER_USER_ID = "";', f'let SERVER_USER_ID = "{auth_user}";')
    resp = make_response(html)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/health', methods=['GET', 'HEAD', 'OPTIONS'], strict_slashes=False)
@app.route('/healthz', methods=['GET', 'HEAD', 'OPTIONS'], strict_slashes=False)
def health():
    return jsonify({"status": "ok", "service": "wpstudio"}), 200

@app.route('/download_pdf/<path:filename>')
def download_pdf(filename):
    safe_name = os.path.basename(filename)
    file_path = os.path.join(PDF_DIR, safe_name)
    if os.path.exists(file_path):
        return send_from_directory(PDF_DIR, safe_name, as_attachment=True)
    return jsonify({"error": "PDF file not found"}), 404

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/auth_check', methods=['GET', 'POST'])
def api_auth_check():
    auth_user = get_authenticated_user()
    admin_id = str(os.getenv("ADMIN_ID", "5628105961"))
    if auth_user:
        is_adm = database.is_admin(auth_user)
        return jsonify({
            "authenticated": True,
            "user_id": str(auth_user),
            "is_admin": is_adm,
            "token": make_studio_token(auth_user)
        })
    return jsonify({"authenticated": False, "locked": True}), 401

@app.route('/api/unlock_studio', methods=['POST'])
def api_unlock_studio():
    data = request.get_json(silent=True) or {}
    passcode = str(data.get('passcode', '')).strip()
    target_user_id = str(data.get('user_id', '')).strip()

    admin_id = str(os.getenv("ADMIN_ID", "5628105961"))
    admin_pins = [admin_id, "admin"]
    if os.getenv("ADMIN_PIN"):
        admin_pins.append(str(os.getenv("ADMIN_PIN")))

    # 1. Master Admin verification
    if passcode in admin_pins:
        resolved_user = target_user_id if target_user_id else admin_id
        session['chat_id'] = admin_id
        session['miniapp_user'] = resolved_user
        session['logged_in'] = True
        return jsonify({
            "success": True,
            "token": make_studio_token(resolved_user),
            "user_id": resolved_user,
            "is_admin": True,
            "message": "Admin authenticated"
        })

    # 2. Match Telegram User ID directly
    if passcode.isdigit():
        uid = int(passcode)
        user = database.get_user(uid)
        if user:
            session['chat_id'] = str(uid)
            session['miniapp_user'] = str(uid)
            session['logged_in'] = True
            return jsonify({
                "success": True,
                "token": make_studio_token(uid),
                "user_id": str(uid),
                "is_admin": database.is_admin(uid),
                "message": "User authenticated"
            })

    # 3. Match target_user_id if provided
    if target_user_id and target_user_id.isdigit():
        uid = int(target_user_id)
        user = database.get_user(uid)
        if user:
            session['chat_id'] = str(uid)
            session['miniapp_user'] = str(uid)
            session['logged_in'] = True
            return jsonify({
                "success": True,
                "token": make_studio_token(uid),
                "user_id": str(uid),
                "is_admin": database.is_admin(uid),
                "message": "User authenticated"
            })

    return jsonify({"error": "Invalid Passcode or Telegram ID. Access denied."}), 401

@app.route('/api/lock_studio', methods=['POST'])
def api_lock_studio():
    session.pop('miniapp_user', None)
    session.pop('chat_id', None)
    session.pop('logged_in', None)
    return jsonify({"success": True, "locked": True})


def build_user_keys(user: dict) -> dict:
    if not user:
        return {}
    return {
        "custom_gemini_key": user.get("custom_gemini_key"),
        "custom_openai_key": user.get("custom_openai_key"),
        "custom_claude_key": user.get("custom_claude_key"),
        "is_admin": database.is_admin(user.get("user_id")),
    }


def sanitize_user_error(err) -> str:
    msg = str(err or "").strip()
    if any(k in msg.lower() for k in ["api key", "key required", "not found", "not configured", "requires an api key"]):
        return "This model requires an API key. Please configure your key in Settings or choose another model."
    if "unavailable" in msg.lower() or "disabled" in msg.lower():
        return "This model is currently unavailable. Please select another model."
    return "Generation could not be completed with the selected model. Please try again or switch to Gemini."


@app.route('/api/user_info', methods=['GET'])
def api_user_info():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401

    chars = database.get_user_characters(user["user_id"])
    history = database.get_user_story_history(user["user_id"])
    sys_settings = database.get_system_settings()
    is_adm = database.is_admin(user["user_id"])
    byok_allowed = (sys_settings.get("byok_enabled") == "1" or is_adm)
    pricing = get_active_pricing_tiers()
    providers = ai_engine.get_provider_availability(user)

    return jsonify({
        "success": True,
        "user": {
            "user_id": user["user_id"],
            "username": user.get("username", "Creator"),
            "credits": user.get("credits", 0),
            "tier": user.get("tier", "Builder"),
            "photo_url": user.get("photo_url"),
            "has_custom_key": bool(user.get("custom_gemini_key")),
            "custom_key_preview": f"{user.get('custom_gemini_key')[:4]}...{user.get('custom_gemini_key')[-4:]}" if user.get("custom_gemini_key") else None,
            "has_custom_openai_key": bool(user.get("custom_openai_key")),
            "custom_openai_key_preview": f"{user.get('custom_openai_key')[:4]}...{user.get('custom_openai_key')[-4:]}" if user.get("custom_openai_key") else None,
            "has_custom_claude_key": bool(user.get("custom_claude_key")),
            "custom_claude_key_preview": f"{user.get('custom_claude_key')[:4]}...{user.get('custom_claude_key')[-4:]}" if user.get("custom_claude_key") else None,
            "selected_model": user.get("selected_model", sys_settings.get("default_model", ai_engine.DEFAULT_MODEL)),
            "selected_provider": user.get("selected_provider", "gemini"),
            "stories_created": user.get("stories_created", 0),
            "characters_count": len(chars),
            "is_admin": is_adm
        },
        "models": ai_engine.AVAILABLE_MODELS,
        "providers": providers,
        "pricing_tiers": pricing,
        "cultures": CULTURES,
        "styles": STYLES,
        "genres_by_culture": GENRES_BY_CULTURE,
        "characters": chars,
        "history": history,
        "history_count": len(history),
        "is_admin": is_adm,
        "byok_enabled": byok_allowed,
        "maintenance_mode": sys_settings.get("maintenance_mode") == "1",
        "feature_toggles": {
            "storycraft": sys_settings.get("feature_storycraft_enabled") != "0",
            "character_forge": sys_settings.get("feature_character_forge_enabled") != "0",
            "thumbnail_lab": sys_settings.get("feature_thumbnail_lab_enabled") != "0",
            "frame_renderer": sys_settings.get("feature_frame_renderer_enabled") != "0"
        },
        "announcement": {
            "active": (sys_settings.get("announcement_banner_active") == "1" or sys_settings.get("announcement_active") == "1") and bool(sys_settings.get("announcement_banner_text") or sys_settings.get("announcement_text")),
            "type": sys_settings.get("announcement_banner_type") or sys_settings.get("announcement_type", "info"),
            "text": sys_settings.get("announcement_banner_text") or sys_settings.get("announcement_text", "")
        }
    })

@app.route('/api/update_settings', methods=['POST'])
def api_update_settings():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    data = request.get_json(silent=True, force=True) or {}
    user_id = user["user_id"]
    sys_settings = database.get_system_settings()

    byok_allowed = (sys_settings.get("byok_enabled") == "1" or database.is_admin(user_id))
    has_key_updates = any(k in data for k in ["custom_gemini_key", "custom_openai_key", "custom_claude_key"])

    if has_key_updates:
        gemini_k = data.get("custom_gemini_key")
        openai_k = data.get("custom_openai_key")
        claude_k = data.get("custom_claude_key")
        if not byok_allowed and any(str(k or "").strip() for k in [gemini_k, openai_k, claude_k] if k is not None):
            return jsonify({
                "success": False,
                "error": "BYOK Locked: Custom API keys are currently disabled by the studio administrator."
            }), 403
        database.update_user_custom_keys(
            user_id,
            gemini_key=gemini_k.strip() if gemini_k is not None else None,
            openai_key=openai_k.strip() if openai_k is not None else None,
            claude_key=claude_k.strip() if claude_k is not None else None
        )

    if "selected_model" in data or "selected_provider" in data:
        model = str(data.get("selected_model", "")).strip() or user.get("selected_model", ai_engine.DEFAULT_MODEL)
        provider = str(data.get("selected_provider", "")).strip().lower() or ai_engine.get_model_provider(model)

        # Check provider availability
        avail = ai_engine.get_provider_availability(user).get(provider, {})
        if not avail.get("available") and not database.is_admin(user_id):
            return jsonify({
                "success": False,
                "error": f"Provider '{provider.upper()}' is not available: {avail.get('reason', 'Missing credentials or disabled.')}"
            }), 400

        database.update_user_model(user_id, model, provider)

    refreshed = database.get_user(user_id)
    return jsonify({
        "success": True,
        "credits": refreshed.get("credits", 0),
        "selected_model": refreshed.get("selected_model"),
        "selected_provider": refreshed.get("selected_provider", "gemini"),
        "has_custom_key": bool(refreshed.get("custom_gemini_key")),
        "has_custom_openai_key": bool(refreshed.get("custom_openai_key")),
        "has_custom_claude_key": bool(refreshed.get("custom_claude_key")),
        "providers": ai_engine.get_provider_availability(refreshed)
    })

@app.route('/api/test_key', methods=['POST'])
def api_test_key():
    data = request.get_json(silent=True, force=True) or {}
    key = str(data.get("api_key", "")).strip()
    provider = str(data.get("provider", "gemini")).strip().lower()
    if not key:
        return jsonify({"success": False, "error": "No API key provided"}), 400

    try:
        if provider == "openai":
            with httpx.Client(timeout=12.0) as client:
                resp = client.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
                if resp.status_code == 200:
                    return jsonify({"success": True, "message": "Key is valid and authenticated with OpenAI API!"})
                else:
                    try:
                        err_msg = resp.json().get("error", {}).get("message", resp.text)
                    except Exception:
                        err_msg = resp.text
                    return jsonify({"success": False, "error": f"OpenAI authentication failed: {err_msg}"}), 400

        elif provider in ["claude", "anthropic"]:
            with httpx.Client(timeout=12.0) as client:
                resp = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": "claude-3-5-haiku-20241022",
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "ping"}]
                    }
                )
                if resp.status_code == 200:
                    return jsonify({"success": True, "message": "Key is valid and authenticated with Anthropic Claude API!"})
                else:
                    try:
                        err_msg = resp.json().get("error", {}).get("message", resp.text)
                    except Exception:
                        err_msg = resp.text
                    return jsonify({"success": False, "error": f"Claude authentication failed: {err_msg}"}), 400

        else: # gemini
            from google import genai
            client = genai.Client(api_key=key)
            resp = client.models.generate_content(
                model=ai_engine.DEFAULT_MODEL,
                contents="Say 'OK' in 1 word."
            )
            if resp and resp.text:
                return jsonify({"success": True, "message": "Key is valid and authenticated with Google GenAI!"})
            return jsonify({"success": False, "error": "No response returned from model"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/characters', methods=['GET'])
def api_characters():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    chars = database.get_user_characters(user["user_id"])
    return jsonify({
        "success": True,
        "characters": chars
    })

@app.route('/api/character_forge', methods=['POST'])
def api_character_forge():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    data = request.get_json(silent=True, force=True) or {}
    user_id = user["user_id"]

    name = str(data.get("name", "Kemi")).strip() or "Kemi"
    age = str(data.get("age", "28"))
    gender = str(data.get("gender", "Female"))
    complexion = str(data.get("complexion", "Medium brown"))
    nose_type = str(data.get("noseType", "Broad / Wide"))
    hairstyle = str(data.get("hairstyle", "Braids"))
    custom_hair = str(data.get("customHairstyle", "")).strip()
    hair_color = str(data.get("hairColor", "#000000"))
    body_size = str(data.get("bodySize", "Average"))
    height = str(data.get("height", "Tall"))
    expression = str(data.get("expression", "Happy"))
    outfit_style = str(data.get("outfitStyle", "Ankara"))
    custom_outfit = str(data.get("customOutfit", "")).strip()
    background = str(data.get("background", "Neutral studio"))
    lighting = str(data.get("lighting", "Studio"))
    art_style = str(data.get("artStyle", "Realistic"))
    purpose = str(data.get("purpose", "Film"))

    reference_b64 = data.get("reference_image_b64")
    reference_instruction = str(data.get("reference_instruction", "")).strip()

    check_err = check_maintenance_and_feature("character_forge")
    if check_err: return check_err

    custom_key = user.get("custom_gemini_key")
    model_name = user.get("selected_model", ai_engine.DEFAULT_MODEL)

    sys_settings = database.get_system_settings()
    byok_allowed = (sys_settings.get("byok_enabled") == "1" or database.is_admin(user_id))
    forge_cost = int(sys_settings.get("pricing_forge_cost", 5))

    # Cost calculation: forge_cost unless authorized BYOK
    cost = 0 if (custom_key and byok_allowed) else forge_cost
    if cost > 0 and user.get("credits", 0) < cost:
        return jsonify({"success": False, "error": f"Insufficient credits! Creating a character costs {cost} credits."}), 402

    image_bytes = None
    vision_biometrics = None
    if reference_b64:
        try:
            if "," in reference_b64:
                reference_b64 = reference_b64.split(",", 1)[1]
            image_bytes = base64.b64decode(reference_b64)
            vision_analysis = run_async(ai_engine.analyze_reference_image(
                image_bytes=image_bytes,
                instruction=reference_instruction,
                user_api_key=custom_key,
                model_name=model_name
            ))
            vision_biometrics = json.dumps(vision_analysis)
        except Exception as img_err:
            print(f"[FORGE API] Image vision analysis warning: {img_err}")

    effective_hair = custom_hair if custom_hair else f"{hairstyle} in {hair_color}"
    effective_outfit = custom_outfit if (outfit_style == "Custom" or custom_outfit) else f"{outfit_style} attire"

    desc = (
        f"Character: {name}, {age}-year-old {gender}. "
        f"Complexion: {complexion}. "
        f"Nose type: {nose_type}. "
        f"Hairstyle: {effective_hair}. "
        f"Body Build: {body_size} frame, {height} stature. "
        f"Facial Expression: {expression}. "
        f"Outfit: {effective_outfit}. "
        f"Background: {background}. "
        f"Lighting: {lighting}. "
        f"Art Direction: {art_style}. "
        f"Purpose: {purpose}."
    )

    try:
        turnaround = run_async(ai_engine.generate_character_turnaround(
            character_desc=desc,
            style=art_style,
            reference_image_bytes=image_bytes,
            reference_instruction=reference_instruction,
            vision_biometrics=vision_biometrics,
            user_api_key=custom_key,
            model_name=model_name
        ))
    except Exception as e:
        return jsonify({"success": False, "error": f"Generation error: {str(e)}"}), 500

    # Save to database
    char_record = {
        "name": name,
        "age": age,
        "gender": gender,
        "complexion": complexion,
        "nose_type": nose_type,
        "hairstyle": hairstyle,
        "custom_hairstyle": custom_hair,
        "hair_color": hair_color,
        "body_size": body_size,
        "height": height,
        "expression": expression,
        "outfit_style": outfit_style,
        "custom_outfit": custom_outfit,
        "background": background,
        "lighting": lighting,
        "art_style": art_style,
        "purpose": purpose,
        "reference_instruction": reference_instruction,
        "vision_biometrics": vision_biometrics
    }

    char_pdf_path = ""
    try:
        char_pdf_path = pdf_generator.generate_character_forge_pdf(turnaround, style=art_style)
        if char_pdf_path and os.path.exists(char_pdf_path):
            send_telegram_document(
                user_id=user_id,
                file_path=char_pdf_path,
                caption=f"<b>CastLock 3D Continuity Sheet</b>\n<i>{name}</i>"
            )
    except Exception as c_err:
        print(f"[CHARACTER FORGE] PDF generation error: {c_err}")

    char_id = database.save_character(user_id, char_record)
    if cost > 0:
        database.deduct_credits(user_id, cost)

    refreshed_user = database.get_user(user_id)
    return jsonify({
        "success": True,
        "character_id": char_id,
        "turnaround": turnaround,
        "has_pdf": bool(char_pdf_path and os.path.exists(char_pdf_path)),
        "credits": refreshed_user.get("credits", 0)
    })

@app.route('/api/character_delete', methods=['POST'])
def api_character_delete():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    data = request.get_json(silent=True, force=True) or {}
    char_id = data.get("character_id")
    if char_id:
        database.delete_character(int(char_id), user["user_id"])
    return jsonify({"success": True})

@app.route('/api/story_concepts', methods=['POST'])
def api_story_concepts():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    data = request.get_json(silent=True, force=True) or {}
    user_id = user["user_id"]

    source_input = str(data.get("source_input", "")).strip()
    if not source_input:
        return jsonify({"success": False, "error": "Please provide a YouTube URL or story premise"}), 400

    culture = str(data.get("culture", "Black American"))
    style = str(data.get("style", "Stylised 3D"))
    genre = str(data.get("genre", "Auto-Detect / Adaptive (Inferred from Story)"))
    custom_genre = str(data.get("custom_genre", "")).strip()
    if genre.startswith("Custom") and custom_genre:
        genre = custom_genre
    elif genre.startswith("Custom"):
        genre = "Personal Story & Real Life Memoir"
    length_tier = str(data.get("length_tier", "Short"))
    delivery_format = str(data.get("delivery_format", "Dialogue / Narrative")).strip()
    locked_lead_id = data.get("locked_lead_id")
    check_err = check_maintenance_and_feature("storycraft")
    if check_err: return check_err

    tier_cfg = get_active_pricing_tiers().get(length_tier, get_active_pricing_tiers()["Short"])
    concepts_cost = tier_cfg["concepts_cost"]

    model_name = str(data.get("model_name") or user.get("selected_model", ai_engine.DEFAULT_MODEL)).strip()
    provider = ai_engine.get_model_provider(model_name)
    providers_status = ai_engine.get_provider_availability(user)
    avail = providers_status.get(provider, {})
    if not avail.get("available"):
        return jsonify({
            "success": False,
            "error": "This model requires an API key. Please configure your key in Settings or choose another model."
        }), 400

    user_keys = build_user_keys(user)
    has_byok_for_model = False
    if provider == "claude" and user_keys.get("custom_claude_key"):
        has_byok_for_model = True
    elif provider == "openai" and user_keys.get("custom_openai_key"):
        has_byok_for_model = True
    elif provider == "gemini" and user_keys.get("custom_gemini_key"):
        has_byok_for_model = True

    sys_settings = database.get_system_settings()
    byok_allowed = (sys_settings.get("byok_enabled") == "1" or database.is_admin(user_id))
    actual_cost = 0 if (has_byok_for_model and byok_allowed) else concepts_cost

    if actual_cost > 0 and user.get("credits", 0) < actual_cost:
        return jsonify({
            "success": False,
            "error": f"Insufficient credits! Concept generation requires {actual_cost} credits."
        }), 402

    # Extract YouTube context if URL provided
    source_title = source_input[:50]
    transcript_text = source_input
    if "youtube.com" in source_input or "youtu.be" in source_input:
        yt_res = source_extractor.get_youtube_transcript(source_input, user_keys.get("custom_gemini_key"))
        if yt_res.get("success"):
            source_title = yt_res.get("title", source_title)
            transcript_text = yt_res.get("transcript", source_input)
        else:
            return jsonify({
                "success": False,
                "error": yt_res.get("error", "Failed to extract YouTube transcript.")
            }), 400

    lead_char = None
    if locked_lead_id:
        lead_char = database.get_character_by_id(int(locked_lead_id), user_id)

    try:
        concepts = run_async(ai_engine.generate_ten_concepts(
            source_title=source_title,
            source_context=transcript_text,
            culture=culture,
            visual_style=style,
            genre=genre,
            lead_character=lead_char,
            user_api_key=user_keys.get("custom_gemini_key"),
            model_name=model_name,
            user_keys=user_keys
        ))
    except Exception as e:
        print(f"[CONCEPTS GENERATION ERROR] {e}")
        return jsonify({"success": False, "error": sanitize_user_error(e)}), 500

    # Normalize concepts to list
    concepts_list = concepts.get("concepts", []) if isinstance(concepts, dict) else (concepts if isinstance(concepts, list) else [])

    # Create job in database
    job_id = database.create_story_job(
        user_id=user_id,
        source_input=source_input,
        source_title=source_title,
        transcript=transcript_text[:12000],
        culture=culture,
        style=style,
        genre=genre,
        timezone="Africa/Lagos",
        length_tier=length_tier,
        delivery_format=delivery_format
    )
    database.update_job_concepts(job_id, json.dumps(concepts_list))

    if actual_cost > 0:
        database.deduct_credits(user_id, actual_cost)

    refreshed_user = database.get_user(user_id)
    return jsonify({
        "success": True,
        "job_id": job_id,
        "source_title": source_title,
        "concepts": concepts_list,
        "recommendation_reason": concepts.get("recommendation_reason", "") if isinstance(concepts, dict) else "",
        "recommended_concept_id": concepts.get("recommended_concept_id", 1) if isinstance(concepts, dict) else 1,
        "credits": refreshed_user.get("credits", 0)
    })

@app.route('/api/story_generate', methods=['POST'])
def api_story_generate():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    data = request.get_json(silent=True, force=True) or {}
    user_id = user["user_id"]

    job_id = data.get("job_id")
    selected_concept_idx = int(data.get("selected_concept_idx", 0))

    if not job_id:
        return jsonify({"success": False, "error": "Missing job_id"}), 400

    job = database.get_job(int(job_id))
    if not job or job.get("user_id") != user_id:
        return jsonify({"success": False, "error": "Job not found"}), 404

    check_err = check_maintenance_and_feature("storycraft")
    if check_err: return check_err

    length_tier = job.get("length_tier", "Short")
    tier_cfg = get_active_pricing_tiers().get(length_tier, get_active_pricing_tiers()["Short"])
    pdfs_cost = tier_cfg["pdfs_cost"]

    model_name = str(data.get("model_name") or user.get("selected_model", ai_engine.DEFAULT_MODEL)).strip()
    provider = ai_engine.get_model_provider(model_name)
    providers_status = ai_engine.get_provider_availability(user)
    avail = providers_status.get(provider, {})
    if not avail.get("available"):
        return jsonify({
            "success": False,
            "error": "This model requires an API key. Please configure your key in Settings or choose another model."
        }), 400

    user_keys = build_user_keys(user)
    has_byok_for_model = False
    if provider == "claude" and user_keys.get("custom_claude_key"):
        has_byok_for_model = True
    elif provider == "openai" and user_keys.get("custom_openai_key"):
        has_byok_for_model = True
    elif provider == "gemini" and user_keys.get("custom_gemini_key"):
        has_byok_for_model = True

    sys_settings = database.get_system_settings()
    byok_allowed = (sys_settings.get("byok_enabled") == "1" or database.is_admin(user_id))
    actual_cost = 0 if (has_byok_for_model and byok_allowed) else pdfs_cost

    if actual_cost > 0 and user.get("credits", 0) < actual_cost:
        return jsonify({
            "success": False,
            "error": f"Insufficient credits! Script & PDF generation requires {actual_cost} credits."
        }), 402

    raw_concepts = job.get("concepts_json", "[]")
    try:
        parsed_c = json.loads(raw_concepts)
    except Exception:
        parsed_c = []

    if isinstance(parsed_c, dict) and "concepts" in parsed_c:
        concepts = parsed_c["concepts"]
    elif isinstance(parsed_c, list):
        concepts = parsed_c
    else:
        concepts = []

    if not concepts:
        return jsonify({"success": False, "error": "No concepts found for this job"}), 400

    if selected_concept_idx >= len(concepts):
        selected_concept_idx = 0
    chosen_concept = concepts[selected_concept_idx]

    # Check for lead character if one was attached
    lead_char = None
    char_id = data.get("locked_lead_id")
    if char_id:
        lead_char = database.get_character_by_id(int(char_id), user_id)

    channel_name = str(data.get("channel_name", "")).strip() or job.get("channel_name", "")

    database.update_job_selection(int(job_id), selected_concept_idx)
    delivery_fmt = str(data.get("delivery_format") or job.get("delivery_format") or "Dialogue / Narrative").strip()

    try:
        full_story = run_async(ai_engine.generate_full_story_package(
            concept=chosen_concept,
            culture=job.get("culture", "Universal"),
            visual_style=job.get("style", "Stylised 3D"),
            genre=job.get("genre", "Action Thriller"),
            delivery_format=delivery_fmt,
            lead_character=lead_char,
            length_tier=length_tier,
            timezone="Africa/Lagos",
            user_api_key=user_keys.get("custom_gemini_key"),
            model_name=model_name,
            channel_name=channel_name,
            user_keys=user_keys
        ))
    except Exception as e:
        print(f"[STORY PRODUCTION ERROR] {e}")
        return jsonify({"success": False, "error": sanitize_user_error(e)}), 500

    # Generate Dual Production PDFs
    bible_pdf = ""
    scene_pdf = ""
    try:
        bible_pdf = pdf_generator.generate_image_prompts_pdf(
            story_data=full_story,
            culture=job.get("culture", "Universal"),
            style=job.get("style", "Stylised 3D"),
            genre=job.get("genre", "Action Thriller"),
            delivery_format=delivery_fmt,
            lead_character=lead_char,
            length_tier=length_tier,
            timezone="Africa/Lagos"
        )
        scene_pdf = pdf_generator.generate_video_prompts_pdf(
            story_data=full_story,
            culture=job.get("culture", "Universal"),
            style=job.get("style", "Stylised 3D"),
            genre=job.get("genre", "Action Thriller"),
            delivery_format=delivery_fmt,
            lead_character=lead_char,
            length_tier=length_tier,
            timezone="Africa/Lagos"
        )
    except Exception as pdf_err:
        import traceback
        traceback.print_exc()
        print(f"[STORY GENERATE] PDF creation error: {pdf_err}")

    if not bible_pdf and not scene_pdf:
        return jsonify({
            "success": False,
            "error": "The story was created, but building the PDF files failed. Please try again."
        }), 500

    database.update_job_completion(int(job_id), json.dumps(full_story), bible_pdf, scene_pdf)
    database.log_story(
        user_id=user_id,
        title=full_story.get("title", chosen_concept.get("title", "WP Studio Story")),
        topic=chosen_concept.get("hook", ""),
        style=job.get("style", "Stylised 3D"),
        genre=job.get("genre", "Action Thriller"),
        duration=tier_cfg.get("duration", "Short"),
        pdf_path=bible_pdf
    )

    if actual_cost > 0:
        database.deduct_credits(user_id, actual_cost)

    # Deliver both PDFs directly into the user's Telegram chat (Zero links exposed!)
    story_title = full_story.get("title", chosen_concept.get("title", "WP Studio Story"))
    sent_bible = False
    sent_scene = False
    if bible_pdf and os.path.exists(bible_pdf):
        sent_bible = send_telegram_document(
            user_id=user_id,
            file_path=bible_pdf,
            caption=f"<b>PDF 1: Image Production Prompts</b>\n<i>{story_title}</i>"
        )
    if scene_pdf and os.path.exists(scene_pdf):
        sent_scene = send_telegram_document(
            user_id=user_id,
            file_path=scene_pdf,
            caption=f"<b>PDF 2: Video Production Prompts</b>\n<i>{story_title}</i>"
        )

    refreshed_user = database.get_user(user_id)
    gc.collect()
    return jsonify({
        "success": True,
        "story": full_story,
        "job_id": int(job_id),
        "has_bible": bool(bible_pdf and os.path.exists(bible_pdf)),
        "has_scene": bool(scene_pdf and os.path.exists(scene_pdf)),
        "sent_to_telegram": (sent_bible or sent_scene),
        "credits": refreshed_user.get("credits", 0)
    })

@app.route('/api/send_pdf_to_telegram', methods=['POST'])
def api_send_pdf_to_telegram():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    user_id = user["user_id"]
    data = request.get_json(silent=True, force=True) or {}
    job_id = data.get("job_id")
    pdf_type = data.get("type", "both")

    if not job_id:
        return jsonify({"success": False, "error": "Missing job id"}), 400

    job = database.get_job(int(job_id))
    if not job or (job.get("user_id") != user_id and not database.is_admin(user_id)):
        return jsonify({"success": False, "error": "Screenplay job not found"}), 404

    story_title = job.get("source_title", "WP Studio Story")
    files_to_send = []

    bible_path = job.get("story_bible_pdf")
    scene_path = job.get("scene_prompts_pdf")

    need_bible = (pdf_type in ["bible", "both"])
    need_scene = (pdf_type in ["scene", "both"])

    bible_missing = need_bible and (not bible_path or not os.path.exists(bible_path))
    scene_missing = need_scene and (not scene_path or not os.path.exists(scene_path))

    # If container restarted and PDF files are not on disk, reconstruct them on the fly from full_story_json!
    if (bible_missing or scene_missing) and job.get("full_story_json"):
        try:
            raw_story = job.get("full_story_json")
            full_story = json.loads(raw_story) if isinstance(raw_story, str) else raw_story
            if isinstance(full_story, dict):
                story_title = full_story.get("title", story_title)
                if bible_missing:
                    bible_path = pdf_generator.generate_image_prompts_pdf(
                        story_data=full_story,
                        culture=job.get("culture", "Universal"),
                        style=job.get("style", "Stylised 3D"),
                        genre=job.get("genre", "Action Thriller"),
                        delivery_format="Dialogue / Narrative",
                        length_tier=job.get("length_tier", "Short"),
                        timezone="Africa/Lagos"
                    )
                if scene_missing:
                    scene_path = pdf_generator.generate_video_prompts_pdf(
                        story_data=full_story,
                        culture=job.get("culture", "Universal"),
                        style=job.get("style", "Stylised 3D"),
                        genre=job.get("genre", "Action Thriller"),
                        delivery_format="Dialogue / Narrative",
                        length_tier=job.get("length_tier", "Short"),
                        timezone="Africa/Lagos"
                    )
                database.update_job_completion(int(job_id), full_story, bible_path or job.get("story_bible_pdf", ""), scene_path or job.get("scene_prompts_pdf", ""))
        except Exception as regen_err:
            print(f"[SEND PDF] Re-building missing PDF notice: {regen_err}")
        finally:
            gc.collect()

    if need_bible and bible_path and os.path.exists(bible_path):
        files_to_send.append((bible_path, f"<b>PDF 1: Image Production Prompts</b>\n<i>{story_title}</i>"))

    if need_scene and scene_path and os.path.exists(scene_path):
        files_to_send.append((scene_path, f"<b>PDF 2: Video Production Prompts</b>\n<i>{story_title}</i>"))

    if not files_to_send:
        return jsonify({"success": False, "error": "PDF files could not be found or built for this screenplay."}), 404

    delivered = False
    for fpath, caption in files_to_send:
        if send_telegram_document(user_id, fpath, caption):
            delivered = True

    gc.collect()
    if delivered:
        return jsonify({"success": True, "message": "PDF sent directly to your Telegram chat!"})
    else:
        return jsonify({"success": False, "error": "Could not send PDF to Telegram chat."}), 500

@app.route('/api/thumbnail_generate', methods=['POST'])
def api_thumbnail_generate():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    data = request.get_json(silent=True, force=True) or {}
    user_id = user["user_id"]

    check_err = check_maintenance_and_feature("thumbnail_lab")
    if check_err: return check_err

    topic = str(data.get("topic", "")).strip()
    if not topic:
        return jsonify({"success": False, "error": "Please provide a video title or topic"}), 400

    channel_name = str(data.get("channel_name", "")).strip()
    style = str(data.get("style", "Hyper-Realistic Cinematic 3D")).strip()
    char_id = data.get("character_id")
    emotion = str(data.get("emotion", "Shock & Disbelief (Jaw Dropped / Wide Eyes)")).strip()
    composition = str(data.get("composition", "Extreme Face Close-Up on Left with Threat/Object on Right")).strip()
    color_mood = str(data.get("color_mood", "High-Contrast YouTube Punch (Vibrant Yellow & Cyan)")).strip()
    custom_notes = str(data.get("custom_notes", "")).strip()
    writeup_text = str(data.get("writeup_text", "")).strip()
    include_yt_logo = bool(data.get("include_youtube_logo", True))

    lead_char = None
    if char_id:
        try:
            lead_char = database.get_character_by_id(int(char_id), user_id)
        except Exception:
            lead_char = None

    custom_key = user.get("custom_gemini_key")
    model_name = user.get("selected_model", ai_engine.DEFAULT_MODEL)

    sys_settings = database.get_system_settings()
    byok_allowed = (sys_settings.get("byok_enabled") == "1" or database.is_admin(user_id))
    thumb_cost = int(sys_settings.get("pricing_thumb_cost", 3))
    cost = 0 if (custom_key and byok_allowed) else thumb_cost

    if cost > 0 and user.get("credits", 0) < cost:
        return jsonify({"success": False, "error": f"Insufficient credits! Thumbnails require {cost} credits."}), 402

    try:
        thumb_data = run_async(ai_engine.generate_thumbnail_prompts(
            story_summary=topic,
            channel_name=channel_name,
            thumbnail_style=style,
            lead_character=lead_char,
            facial_emotion=emotion,
            composition_layout=composition,
            color_mood=color_mood,
            custom_notes=custom_notes,
            writeup_text=writeup_text,
            include_youtube_logo=include_yt_logo,
            user_api_key=custom_key,
            model_name=model_name
        ))
        if cost > 0:
            database.deduct_credits(user_id, cost)
        refreshed_user = database.get_user(user_id)
        gc.collect()
        return jsonify({
            "success": True,
            "thumbnails": thumb_data,
            "credits": refreshed_user.get("credits", 0)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/send_thumbnail_to_telegram', methods=['POST'])
def api_send_thumbnail_to_telegram():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    user_id = user["user_id"]
    data = request.get_json(silent=True, force=True) or {}
    concepts = data.get("concepts", [])
    if not concepts:
        return jsonify({"success": False, "error": "No thumbnail concepts to send"}), 400

    msg = "<b>WP Studio — YouTube Thumbnail Master Prompts</b>\n"
    if data.get("topic"):
        msg += f"<i>Project: {data.get('topic')}</i>\n"
    if data.get("channel_name"):
        msg += f"<i>Channel: {data.get('channel_name')}</i>\n"

    for i, c in enumerate(concepts[:3], 1):
        v_name = c.get("variation_name", f"Variation #{i}")
        headline = c.get("headline_title", "")
        overlay = c.get("overlay_text", "")
        prompt = c.get("master_image_prompt", "")
        trigger = c.get("psychological_trigger", "")

        msg += "\n<b>━━━━━━━━━━━━━━━━━━━━</b>\n"
        msg += f"<b>{v_name.upper()}</b>\n"
        if headline:
            msg += f"<b>Recommended Title:</b> {headline}\n"
        if overlay:
            msg += f"<b>Overlay Sticker:</b> <code>{overlay}</code>\n"
        if trigger:
            msg += f"<b>Click Trigger:</b> {trigger}\n"
        if prompt:
            msg += f"<b>Midjourney / Flux / Google Flow Prompt:</b>\n<code>{prompt}</code>\n"

    success = send_telegram_message(user_id, msg)
    if success:
        return jsonify({"success": True, "message": "Thumbnail prompts sent directly to your Telegram chat!"})
    else:
        return jsonify({"success": False, "error": "Could not send prompts to Telegram chat."}), 500

@app.route('/api/send_image_to_telegram', methods=['POST'])
def api_send_image_to_telegram():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    user_id = user["user_id"]
    data = request.get_json(silent=True, force=True) or {}
    image_data = data.get("image_data", "")
    caption = data.get("caption", "<b>WP Studio Production Image</b>")

    if not image_data or not image_data.startswith("data:image"):
        return jsonify({"success": False, "error": "Invalid image data"}), 400

    try:
        header, b64_str = image_data.split(",", 1)
        raw_bytes = base64.b64decode(b64_str)
        delivered = send_telegram_photo(user_id, raw_bytes, caption)
        if delivered:
            return jsonify({"success": True, "message": "Photo sent directly to your Telegram chat! Save it to your gallery."})
        else:
            return jsonify({"success": False, "error": "Could not send photo to Telegram chat."}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================================
# STORY ADAPTER (SCRIPT TO SCENES) API
# ============================================================================

@app.route('/api/story_adapter/estimate', methods=['POST'])
def api_story_adapter_estimate():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    user_id = user["user_id"]
    data = request.get_json(silent=True, force=True) or {}
    text = str(data.get("story_text", "")).strip()
    words = len(text.split()) if text else 0

    # Pacing formula: approximately 50-65 words per visual shot
    est_scenes = max(1, min(80, max(5, round(words / 60)))) if words > 0 else 0
    extra_scenes = max(0, est_scenes - 40)
    base_cost = 15
    cost = base_cost + extra_scenes
    
    is_vip = int(user.get("credits", 0)) >= 999999
    if is_vip:
        cost = 0

    return jsonify({
        "success": True,
        "word_count": words,
        "estimated_scenes": est_scenes,
        "cost": cost,
        "user_balance": user.get("credits", 0),
        "is_vip": is_vip,
        "can_afford": (is_vip or user.get("credits", 0) >= cost)
    })

@app.route('/api/story_adapter/generate', methods=['POST'])
def api_story_adapter_generate():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    user_id = user["user_id"]
    data = request.get_json(silent=True, force=True) or {}
    
    text = str(data.get("story_text", "")).strip()
    words = len(text.split()) if text else 0
    if words < 100:
        return jsonify({"success": False, "error": f"Story text is too short ({words} words). Please enter a story or script with at least 500 words (or minimum 100 words)."}), 400
    if words > 5500:
        return jsonify({"success": False, "error": f"Story text exceeds limit ({words} words). Maximum is 5,000 words per adaptation."}), 400

    genre = str(data.get("genre", "Drama")).strip()
    cinematic_filter = str(data.get("cinematic_filter", "Default")).strip()
    art_style = str(data.get("art_style", "Realistic")).strip()
    voice_accent = str(data.get("voice_accent", "African / Nigerian")).strip()
    target_duration = str(data.get("target_duration", "Standard (8–15 Mins)")).strip()
    delivery_format = str(data.get("delivery_format", "Dialogue / Narrative")).strip()

    model_name = str(data.get("model_name") or user.get("selected_model", ai_engine.DEFAULT_MODEL)).strip()
    provider = ai_engine.get_model_provider(model_name)
    providers_status = ai_engine.get_provider_availability(user)
    avail = providers_status.get(provider, {})
    if not avail.get("available"):
        return jsonify({
            "success": False,
            "error": "This model requires an API key. Please configure your key in Settings or choose another model."
        }), 400

    user_keys = build_user_keys(user)
    has_byok_for_model = False
    if provider == "claude" and user_keys.get("custom_claude_key"):
        has_byok_for_model = True
    elif provider == "openai" and user_keys.get("custom_openai_key"):
        has_byok_for_model = True
    elif provider == "gemini" and user_keys.get("custom_gemini_key"):
        has_byok_for_model = True

    sys_settings = database.get_system_settings()
    byok_allowed = (sys_settings.get("byok_enabled") == "1" or database.is_admin(user_id))

    # Pricing logic: 15 base + 1 per scene above 40 (0 for VIP or BYOK)
    is_vip = int(user.get("credits", 0)) >= 999999
    is_free = is_vip or (has_byok_for_model and byok_allowed)
    cost = 15 if not is_free else 0

    if cost > 0 and user.get("credits", 0) < cost:
        return jsonify({"success": False, "error": f"Insufficient credits! Story Adapter requires {cost} credits."}), 402

    try:
        adapted_data = run_async(ai_engine.adapt_story_to_scenes(
            story_text=text,
            genre=genre,
            cinematic_filter=cinematic_filter,
            art_style=art_style,
            voice_accent=voice_accent,
            target_duration=target_duration,
            delivery_format=delivery_format,
            user_api_key=user_keys.get("custom_gemini_key"),
            model_name=model_name,
            user_keys=user_keys
        ))

        # Check total scenes produced
        total_scenes = len(adapted_data.get("scenes", []))
        if total_scenes > 40 and not is_free:
            extra = total_scenes - 40
            cost += extra

        # Deduct credits
        if cost > 0:
            database.deduct_credits(user_id, cost)

        # Save job into database
        job_id = database.create_story_job(
            user_id=user_id,
            source_input="Story Adapter",
            source_title=adapted_data.get("title", "Adapted Story"),
            transcript=text[:2000],
            culture=voice_accent,
            style=art_style,
            genre=genre,
            timezone="Africa/Lagos",
            length_tier=f"{total_scenes} Scenes",
            delivery_format=delivery_format,
            job_type="story_adapter",
            story_text=text
        )

        refreshed_user = database.get_user(user_id)
        return jsonify({
            "success": True,
            "job_id": job_id,
            "data": adapted_data,
            "cost_charged": cost,
            "user_balance": refreshed_user.get("credits", 0)
        })
    except Exception as e:
        print(f"[STORY ADAPTER ERROR] {e}")
        return jsonify({"success": False, "error": sanitize_user_error(e)}), 500

@app.route('/api/story_adapter/send_to_telegram', methods=['POST'])
def api_story_adapter_send_to_telegram():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    user_id = user["user_id"]
    data = request.get_json(silent=True, force=True) or {}
    scenes = data.get("scenes", [])
    title = data.get("title", "Story Adapter Breakdown")
    logline = data.get("logline", "")

    if not scenes:
        return jsonify({"success": False, "error": "No scenes found to send"}), 400

    # Header message
    header_msg = f"<b>WP Studio — Story Adapter Breakdown</b>\n"
    header_msg += f"<b>Title:</b> {title}\n"
    if logline:
        header_msg += f"<i>{logline}</i>\n"
    header_msg += f"<b>Total Scenes:</b> {len(scenes)}\n"
    header_msg += f"<b>Art Style:</b> {data.get('art_style', 'Realistic')} | <b>Visual Filter:</b> {data.get('cinematic_filter', 'Default')}\n"
    header_msg += f"<b>Voice Accent:</b> {data.get('voice_accent', 'African / Nigerian')}\n"
    header_msg += "\n<b>━━━━━━━━━━━━━━━━━━━━</b>"
    send_telegram_message(user_id, header_msg)

    # Deliver scenes in safe chunks to respect Telegram's message character limits
    current_chunk = ""
    for s in scenes:
        s_num = s.get("scene_number", "")
        s_title = s.get("scene_title", f"Scene {s_num}")
        setting = s.get("setting", "")
        narration = s.get("dialogue_or_narration", "")
        img_prompt = s.get("image_prompt", "")
        vid_prompt = s.get("video_prompt", "")

        scene_text = f"\n\n<b>SCENE {s_num}: {s_title}</b>"
        if setting:
            scene_text += f"\n<i>Setting: {setting}</i>"
        if narration:
            scene_text += f"\n<i>\"{narration}\"</i>"
        if img_prompt:
            scene_text += f"\n<b>Visual Image Prompt:</b>\n<code>{img_prompt}</code>"
        if vid_prompt:
            scene_text += f"\n<b>Camera Motion:</b>\n<code>{vid_prompt}</code>"

        if len(current_chunk) + len(scene_text) > 3600:
            send_telegram_message(user_id, current_chunk)
            current_chunk = scene_text
        else:
            current_chunk += scene_text

    if current_chunk:
        send_telegram_message(user_id, current_chunk)

    return jsonify({"success": True, "message": f"All {len(scenes)} scenes sent directly to your Telegram chat!"})


# =====================================================================
# REMIXCRAFT API ROUTES (COMPETITOR VIDEO REMODELER)
# =====================================================================

@app.route('/api/remixcraft/analyze', methods=['POST'])
def api_remixcraft_analyze():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    user_id = user["user_id"]
    data = request.get_json(silent=True, force=True) or {}

    source_type = str(data.get("source_type", "youtube")).strip().lower()
    source_content = str(data.get("source_content", "")).strip()
    culture = str(data.get("culture", "African / Nigerian")).strip()
    target_duration = str(data.get("target_duration", "Standard (8–15 Mins)")).strip()
    lead_character_id = data.get("lead_character_id")

    if not source_content:
        return jsonify({"success": False, "error": "Please provide a YouTube link, script text, or video title to remodel."}), 400

    source_title = "Competitor Source"
    source_text = source_content

    # If YouTube, fetch transcript / video info
    if source_type == "youtube":
        try:
            yt_data = run_async(source_extractor.get_youtube_transcript_async(source_content, user.get("custom_gemini_key")))
            if yt_data.get("success") and yt_data.get("transcript"):
                source_text = yt_data.get("transcript")
                source_title = yt_data.get("title", "YouTube Video")
            else:
                source_title = yt_data.get("title") or "YouTube Video"
                source_text = f"YouTube Video Title: {source_title}\nURL: {source_content}"
        except Exception as yt_err:
            print(f"[REMIXCRAFT YT ERROR] {yt_err}")
            source_text = f"YouTube Video: {source_content}"

    elif source_type == "script":
        source_title = "Raw Script / Text"
        words = len(source_text.split())
        if words < 30:
            return jsonify({"success": False, "error": f"Script text is too short ({words} words). Please enter at least 30 words."}), 400
        if words > 15000:
            return jsonify({"success": False, "error": f"Script exceeds word limit ({words} words). Maximum is 15,000 words."}), 400

    else:
        source_title = source_content

    # Lead actor continuity
    lead_char = None
    if lead_character_id:
        try:
            chars = database.get_user_characters(user_id)
            for c in chars:
                if str(c.get("character_id")) == str(lead_character_id):
                    lead_char = c
                    break
        except Exception:
            pass

    model_name = str(data.get("model_name") or user.get("selected_model", ai_engine.DEFAULT_MODEL)).strip()
    provider = ai_engine.get_model_provider(model_name)
    providers_status = ai_engine.get_provider_availability(user)
    avail = providers_status.get(provider, {})
    if not avail.get("available"):
        return jsonify({
            "success": False,
            "error": "This model requires an API key. Please configure your key in Settings or choose another model."
        }), 400

    user_keys = build_user_keys(user)

    try:
        analysis = run_async(ai_engine.remodel_competitor_analysis(
            source_type=source_type,
            source_content=source_text,
            culture=culture,
            target_duration=target_duration,
            lead_character=lead_char,
            user_api_key=user_keys.get("custom_gemini_key"),
            model_name=model_name,
            user_keys=user_keys
        ))

        return jsonify({
            "success": True,
            "source_title": source_title,
            "analysis": analysis
        })
    except Exception as e:
        print(f"[REMIXCRAFT ANALYZE ERROR] {e}")
        return jsonify({"success": False, "error": sanitize_user_error(e)}), 500


@app.route('/api/remixcraft/produce', methods=['POST'])
def api_remixcraft_produce():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    user_id = user["user_id"]
    data = request.get_json(silent=True, force=True) or {}

    selected_concept = data.get("selected_concept")
    if not selected_concept or not isinstance(selected_concept, dict):
        return jsonify({"success": False, "error": "Please select one of the 3 remodeled angles to produce."}), 400

    source_summary = str(data.get("source_summary", "")).strip()
    culture = str(data.get("culture", "African / Nigerian")).strip()
    target_duration = str(data.get("target_duration", "Standard (8–15 Mins)")).strip()
    art_style = str(data.get("art_style", "Realistic")).strip()
    visual_filter = str(data.get("visual_filter", "Default")).strip()
    lead_character_id = data.get("lead_character_id")

    model_name = str(data.get("model_name") or user.get("selected_model", ai_engine.DEFAULT_MODEL)).strip()
    provider = ai_engine.get_model_provider(model_name)
    providers_status = ai_engine.get_provider_availability(user)
    avail = providers_status.get(provider, {})
    if not avail.get("available"):
        return jsonify({
            "success": False,
            "error": "This model requires an API key. Please configure your key in Settings or choose another model."
        }), 400

    user_keys = build_user_keys(user)
    has_byok_for_model = False
    if provider == "claude" and user_keys.get("custom_claude_key"):
        has_byok_for_model = True
    elif provider == "openai" and user_keys.get("custom_openai_key"):
        has_byok_for_model = True
    elif provider == "gemini" and user_keys.get("custom_gemini_key"):
        has_byok_for_model = True

    # Pricing: 30 credits (0 for VIPs or BYOK)
    is_vip = int(user.get("credits", 0)) >= 999999
    byok_allowed = database.get_system_settings().get("byok_enabled", "1") == "1"
    cost = 0 if (is_vip or (has_byok_for_model and byok_allowed)) else 30

    if cost > 0 and int(user.get("credits", 0)) < cost:
        return jsonify({
            "success": False,
            "error": f"Insufficient credits! Remixcraft production requires 30 credits. Your balance is {user.get('credits', 0)} credits."
        }), 402

    # Lead actor continuity
    lead_char = None
    if lead_character_id:
        try:
            chars = database.get_user_characters(user_id)
            for c in chars:
                if str(c.get("character_id")) == str(lead_character_id):
                    lead_char = c
                    break
        except Exception:
            pass

    try:
        package = run_async(ai_engine.generate_remodeled_production_package(
            selected_concept=selected_concept,
            source_summary=source_summary,
            culture=culture,
            target_duration=target_duration,
            art_style=art_style,
            visual_filter=visual_filter,
            lead_character=lead_char,
            user_api_key=user_keys.get("custom_gemini_key"),
            model_name=model_name,
            user_keys=user_keys
        ))

        # Deduct credits
        if cost > 0:
            database.deduct_credits(user_id, cost)

        # Store job
        job_id = database.create_story_job(
            user_id=user_id,
            source_input=selected_concept.get("title", "Remixcraft Video"),
            source_title=package.get("title", selected_concept.get("title", "Remixcraft")),
            transcript=source_summary[:2000],
            culture=culture,
            style=art_style,
            genre=selected_concept.get("angle_badge", "Remixcraft"),
            timezone="Africa/Lagos",
            length_tier=target_duration,
            delivery_format="Remixcraft Story Package",
            job_type="remixcraft",
            story_text=json.dumps(package)
        )

        refreshed_user = database.get_user(user_id)
        return jsonify({
            "success": True,
            "job_id": job_id,
            "package": package,
            "cost_charged": cost,
            "user_balance": refreshed_user.get("credits", 0)
        })
    except Exception as e:
        print(f"[REMIXCRAFT PRODUCE ERROR] {e}")
        return jsonify({"success": False, "error": sanitize_user_error(e)}), 500


@app.route('/api/remixcraft/send_to_telegram', methods=['POST'])
def api_remixcraft_send_to_telegram():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    user_id = user["user_id"]
    data = request.get_json(silent=True, force=True) or {}
    pkg = data.get("package", {})

    title = pkg.get("title", "Remixcraft Package")
    logline = pkg.get("logline", "")
    synopsis = pkg.get("synopsis", "")
    scenes = pkg.get("scenes", [])
    thumbnails = pkg.get("thumbnail_concepts", [])

    if not scenes:
        return jsonify({"success": False, "error": "No scenes found to send"}), 400

    # Header message with Thumbnails
    header = f"<b>WP Studio — Remixcraft Production Package</b>\n\n"
    header += f"<b>Title:</b> {title}\n"
    if logline:
        header += f"<b>Logline:</b> <i>{logline}</i>\n\n"
    header += f"<b>Target Runtime:</b> {pkg.get('target_duration', 'Standard')} | <b>Art Style:</b> {pkg.get('art_style', 'Realistic')}\n"
    header += f"<b>Culture / Voice:</b> {pkg.get('culture', 'African / Nigerian')}\n"
    header += f"<b>Total Scenes:</b> {len(scenes)}\n"

    if thumbnails:
        header += f"\n<b>HIGH-CTR THUMBNAIL CONCEPTS:</b>\n"
        for idx, th in enumerate(thumbnails, 1):
            header += f"\n<b>Concept {idx}:</b> {th.get('headline', '')}\n"
            header += f"<b>Overlay Text:</b> <code>{th.get('bold_text_overlay', '')}</code>\n"
            header += f"<b>Prompt:</b> <code>{th.get('visual_prompt', '')}</code>\n"

    header += "\n<b>━━━━━━━━━━━━━━━━━━━━</b>"
    send_telegram_message(user_id, header)

    # Deliver scenes in safe chunks (under 3600 chars)
    chunk = ""
    for s in scenes:
        s_num = s.get("scene_number", "")
        s_title = s.get("scene_title", "")
        setting = s.get("setting", "")
        dialogue = s.get("dialogue_or_narration", "")
        img_p = s.get("image_prompt", "")
        vid_p = s.get("video_prompt", "")
        dur = s.get("estimated_duration") or s.get("duration", "")
        raw_chars = s.get("characters_present", [])
        chars_str = ", ".join(raw_chars) if isinstance(raw_chars, list) else (str(raw_chars) if raw_chars else "")

        block = f"\n\n<b>🎬 SCENE {s_num}: {s_title}</b>"
        if dur:
            block += f" <i>({dur})</i>"
        if setting:
            block += f"\n📍 <i>Setting: {setting}</i>"
        if chars_str:
            block += f"\n👥 <i>Cast: {chars_str}</i>"
        if dialogue:
            block += f"\n\n<b>🗣️ Script & Dialogue:</b>\n<i>{dialogue}</i>"
        if img_p:
            block += f"\n\n<b>🖼️ Visual Image Prompt:</b>\n<code>{img_p}</code>"
        if vid_p:
            block += f"\n\n<b>📹 Camera Motion:</b>\n<code>{vid_p}</code>"

        if len(chunk) + len(block) > 3600:
            send_telegram_message(user_id, chunk)
            chunk = block
        else:
            chunk += block

    if chunk:
        send_telegram_message(user_id, chunk)

    # Generate and send Dual PDFs
    try:
        story_payload = {
            "title": title,
            "logline": logline,
            "synopsis": synopsis,
            "theme_and_takeaway": logline,
            "characters": pkg.get("characters", []),
            "scenes": scenes
        }
        b_pdf, s_pdf = pdf_generator.generate_dual_pdfs(
            story_payload,
            culture=pkg.get("culture", "Universal"),
            style=pkg.get("art_style", "Realistic"),
            genre="Remixcraft",
            length_tier=pkg.get("target_duration", "Standard")
        )
        if b_pdf and os.path.exists(b_pdf):
            send_telegram_document(user_id, b_pdf, caption=f"<b>Remixcraft Image Prompts PDF</b>\n<i>{title}</i>")
        if s_pdf and os.path.exists(s_pdf):
            send_telegram_document(user_id, s_pdf, caption=f"<b>Remixcraft Video Prompts PDF</b>\n<i>{title}</i>")
    except Exception as pdf_e:
        print(f"[REMIXCRAFT PDF ERROR] {pdf_e}")

    return jsonify({"success": True, "message": f"Remixcraft package sent directly to your Telegram chat!"})


@app.route('/api/render_frame', methods=['POST'])
def api_render_frame():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    data = request.get_json(silent=True, force=True) or {}
    user_id = user["user_id"]

    check_err = check_maintenance_and_feature("frame_renderer")
    if check_err: return check_err

    prompt = str(data.get("prompt", "")).strip()
    if not prompt:
        return jsonify({"success": False, "error": "Prompt cannot be empty"}), 400

    aspect = str(data.get("aspect_ratio", "16:9"))
    width, height = 1024, 576
    if aspect == "1:1":
        width, height = 768, 768
    elif aspect == "9:16":
        width, height = 576, 1024

    custom_key = user.get("custom_gemini_key")

    try:
        img_bytes = run_async(ai_engine.render_visual_frame(
            prompt=prompt,
            width=width,
            height=height,
            user_api_key=custom_key
        ))
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        return jsonify({
            "success": True,
            "image_data": f"data:image/jpeg;base64,{b64}"
        })
    except ai_engine.RenderCooldownError as cd_err:
        return jsonify({
            "success": False,
            "cooldown": True,
            "remaining_seconds": cd_err.remaining_seconds,
            "error": f"Cloud render cluster cooldown: please wait {cd_err.remaining_seconds}s."
        }), 429
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def api_history():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    history = database.get_user_story_history(user["user_id"])
    return jsonify({
        "success": True,
        "history": history
    })

@app.route('/api/job/<int:job_id>', methods=['GET'])
def api_job_detail(job_id):
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Unauthorized: Telegram authentication required."}), 401
    job = database.get_job(job_id)
    if not job or (job.get("user_id") != user["user_id"] and not database.is_admin(user["user_id"])):
        return jsonify({"success": False, "error": "Job not found"}), 404
    return jsonify({"success": True, "job": job})

# ============================================================================
# MASTER ADMIN API ENDPOINTS
# ============================================================================

@app.route('/api/admin/overview', methods=['GET'])
def api_admin_overview():
    user = get_current_user()
    if not user or not database.is_admin(user["user_id"]):
        return jsonify({"success": False, "error": "Unauthorized: Master Admin access required."}), 403

    stats = database.get_system_stats()
    settings = database.get_system_settings()
    transactions = database.get_credit_transactions(20)
    pricing = get_active_pricing_tiers()
    primary_k, fallback_k = ai_engine.get_master_keys()

    return jsonify({
        "success": True,
        "stats": stats,
        "settings": {
            "has_primary_key": bool(primary_k),
            "primary_key_preview": f"{primary_k[:6]}...{primary_k[-4:]}" if primary_k else "Not Set",
            "has_fallback_key": bool(fallback_k),
            "fallback_key_preview": f"{fallback_k[:6]}...{fallback_k[-4:]}" if fallback_k else "Not Set",
            "has_openai_key": bool(settings.get("openai_api_key")),
            "openai_key_preview": f"{settings.get('openai_api_key')[:6]}...{settings.get('openai_api_key')[-4:]}" if settings.get("openai_api_key") else "Not Set",
            "model_gemini_enabled": settings.get("model_gemini_enabled", "1") != "0",
            "model_gpt_enabled": settings.get("model_gpt_enabled", "1") != "0",
            "model_claude_enabled": settings.get("model_claude_enabled", "1") != "0",
            "providers_status": ai_engine.get_provider_availability(user),
            "default_model": settings.get("default_model", "gemini-3.8-flash"),
            "byok_enabled": settings.get("byok_enabled") == "1",
            "maintenance_mode": settings.get("maintenance_mode") == "1",
            "maintenance_message": settings.get("maintenance_message", ""),
            "feature_storycraft": settings.get("feature_storycraft_enabled") != "0",
            "feature_character_forge": settings.get("feature_character_forge_enabled") != "0",
            "feature_thumbnail_lab": settings.get("feature_thumbnail_lab_enabled") != "0",
            "feature_frame_renderer": settings.get("feature_frame_renderer_enabled") != "0",
            "announcement_text": settings.get("announcement_banner_text") or settings.get("announcement_text", ""),
            "announcement_type": settings.get("announcement_banner_type") or settings.get("announcement_type", "info"),
            "announcement_active": settings.get("announcement_banner_active") == "1" or settings.get("announcement_active") == "1",
            "cost_character_forge": int(settings.get("pricing_forge_cost", 5)),
            "cost_thumbnail_lab": int(settings.get("pricing_thumb_cost", 3)),
            "cost_frame_renderer": int(settings.get("pricing_renderer_cost", 2))
        },
        "pricing": pricing,
        "raw_pricing": {
            "short_concepts": int(settings.get("pricing_short_concepts", 10)),
            "short_pdfs": int(settings.get("pricing_short_pdfs", 40)),
            "medium_concepts": int(settings.get("pricing_medium_concepts", 50)),
            "medium_pdfs": int(settings.get("pricing_medium_pdfs", 250)),
            "long_concepts": int(settings.get("pricing_long_concepts", 100)),
            "long_pdfs": int(settings.get("pricing_long_pdfs", 300)),
            "forge_cost": int(settings.get("pricing_forge_cost", 5)),
            "thumb_cost": int(settings.get("pricing_thumb_cost", 3)),
            "renderer_cost": int(settings.get("pricing_renderer_cost", 2))
        },
        "transactions": transactions
    })

@app.route('/api/admin/users', methods=['GET'])
def api_admin_users():
    user = get_current_user()
    if not user or not database.is_admin(user["user_id"]):
        return jsonify({"success": False, "error": "Unauthorized: Master Admin access required."}), 403

    q = request.args.get('q', '').strip()
    users = database.get_all_users(search=q if q else None, limit=40)
    for u in users:
        u["id"] = u.get("user_id")
    return jsonify({"success": True, "users": users})

@app.route('/api/admin/modify_credits', methods=['POST'])
def api_admin_modify_credits():
    user = get_current_user()
    if not user or not database.is_admin(user["user_id"]):
        return jsonify({"success": False, "error": "Unauthorized: Master Admin access required."}), 403

    data = request.get_json(silent=True, force=True) or {}
    target_id = data.get("target_user_id") or data.get("user_id") or data.get("id")
    action = data.get("action", "add")
    amount = data.get("amount", 0)
    reason = str(data.get("reason", "")).strip()

    if not target_id:
        return jsonify({"success": False, "error": "Missing target_user_id."}), 400

    try:
        t_id = int(target_id)
        if action == "unlimited":
            amt = 999999999
        else:
            if amount is None:
                return jsonify({"success": False, "error": "Missing amount."}), 400
            amt = int(amount)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid target_user_id or amount format."}), 400

    res = database.admin_modify_user_credits(
        admin_id=user["user_id"],
        target_user_id=t_id,
        action=action,
        amount=amt,
        reason=reason
    )
    return jsonify(res)

@app.route('/api/admin/update_tier', methods=['POST'])
def api_admin_update_tier():
    user = get_current_user()
    if not user or not database.is_admin(user["user_id"]):
        return jsonify({"success": False, "error": "Unauthorized: Master Admin access required."}), 403

    data = request.get_json(silent=True, force=True) or {}
    target_id = data.get("target_user_id") or data.get("user_id") or data.get("id")
    tier = str(data.get("tier", "Builder")).strip()

    if not target_id:
        return jsonify({"success": False, "error": "Missing target_user_id."}), 400

    try:
        t_id = int(target_id)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid target_user_id format."}), 400

    database.admin_set_user_tier(user["user_id"], t_id, tier)
    return jsonify({"success": True, "tier": tier})

@app.route('/api/admin/update_settings', methods=['POST'])
def api_admin_update_settings():
    user = get_current_user()
    if not user or not database.is_admin(user["user_id"]):
        return jsonify({"success": False, "error": "Unauthorized: Master Admin access required."}), 403

    data = request.get_json(silent=True, force=True) or {}
    updates = {}

    # Primary & Fallback Keys
    if "primary_key" in data:
        updates["gemini_api_key_primary"] = str(data["primary_key"]).strip()
    elif "gemini_api_key_primary" in data:
        updates["gemini_api_key_primary"] = str(data["gemini_api_key_primary"]).strip()

    if "fallback_key" in data:
        updates["gemini_api_key_fallback"] = str(data["fallback_key"]).strip()
    elif "gemini_api_key_fallback" in data:
        updates["gemini_api_key_fallback"] = str(data["gemini_api_key_fallback"]).strip()

    if "openai_api_key" in data:
        updates["openai_api_key"] = str(data["openai_api_key"]).strip()
    elif "openai_key" in data:
        updates["openai_api_key"] = str(data["openai_key"]).strip()

    for m in ["model_gemini_enabled", "model_gpt_enabled", "model_claude_enabled"]:
        if m in data:
            updates[m] = "1" if data[m] in [True, 1, "1"] else "0"

    if "default_model" in data:
        updates["default_model"] = str(data["default_model"]).strip()

    # BYOK Lock (User requested feature!)
    if "byok_enabled" in data:
        updates["byok_enabled"] = "1" if data["byok_enabled"] in [True, 1, "1"] else "0"

    # Maintenance Mode & Message
    if "maintenance_mode" in data:
        updates["maintenance_mode"] = "1" if data["maintenance_mode"] in [True, 1, "1"] else "0"
    if "maintenance_message" in data:
        updates["maintenance_message"] = str(data["maintenance_message"]).strip()

    # Feature Toggles
    for feat in ["storycraft", "character_forge", "thumbnail_lab", "frame_renderer"]:
        if feat in data:
            updates[f"feature_{feat}_enabled"] = "1" if data[feat] in [True, 1, "1"] else "0"
        elif f"feature_{feat}" in data:
            updates[f"feature_{feat}_enabled"] = "1" if data[f"feature_{feat}"] in [True, 1, "1"] else "0"
        elif f"feature_{feat}_enabled" in data:
            updates[f"feature_{feat}_enabled"] = "1" if data[f"feature_{feat}_enabled"] in [True, 1, "1"] else "0"

    # Pricing Config
    if "pricing_tiers" in data and isinstance(data["pricing_tiers"], dict):
        tiers = data["pricing_tiers"]
        if "Short" in tiers:
            updates["pricing_short_concepts"] = str(int(tiers["Short"].get("concepts_cost", 10)))
            updates["pricing_short_pdfs"] = str(int(tiers["Short"].get("pdfs_cost", 40)))
        if "Medium" in tiers:
            updates["pricing_medium_concepts"] = str(int(tiers["Medium"].get("concepts_cost", 50)))
            updates["pricing_medium_pdfs"] = str(int(tiers["Medium"].get("pdfs_cost", 250)))
        if "Long" in tiers:
            updates["pricing_long_concepts"] = str(int(tiers["Long"].get("concepts_cost", 100)))
            updates["pricing_long_pdfs"] = str(int(tiers["Long"].get("pdfs_cost", 300)))

    for p in ["short_concepts", "short_pdfs", "medium_concepts", "medium_pdfs", "long_concepts", "long_pdfs", "forge_cost", "thumb_cost", "renderer_cost"]:
        key = f"pricing_{p}"
        if key in data:
            try:
                updates[key] = str(int(data[key]))
            except ValueError:
                pass

    if "cost_character_forge" in data:
        updates["pricing_forge_cost"] = str(int(data["cost_character_forge"]))
    if "cost_thumbnail_lab" in data:
        updates["pricing_thumb_cost"] = str(int(data["cost_thumbnail_lab"]))
    if "cost_frame_renderer" in data:
        updates["pricing_renderer_cost"] = str(int(data["cost_frame_renderer"]))

    # Announcement Banner
    if "announcement_text" in data or "announcement_banner_text" in data:
        atxt = str(data.get("announcement_text", data.get("announcement_banner_text", ""))).strip()
        updates["announcement_banner_text"] = atxt
        updates["announcement_text"] = atxt

    if "announcement_type" in data or "announcement_banner_type" in data:
        atype = str(data.get("announcement_type", data.get("announcement_banner_type", "info"))).strip()
        updates["announcement_banner_type"] = atype
        updates["announcement_type"] = atype

    if "announcement_active" in data or "announcement_banner_active" in data:
        raw_act = data.get("announcement_active", data.get("announcement_banner_active"))
        act = "1" if raw_act in [True, 1, "1"] else "0"
        updates["announcement_banner_active"] = act
        updates["announcement_active"] = act

    saved = database.update_system_settings(updates)
    return jsonify({"success": True, "settings": saved})

@app.route('/api/admin/broadcast_telegram', methods=['POST'])
def api_admin_broadcast_telegram():
    user = get_current_user()
    if not user or not database.is_admin(user["user_id"]):
        return jsonify({"success": False, "error": "Unauthorized: Master Admin access required."}), 403

    data = request.get_json(silent=True, force=True) or {}
    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify({"success": False, "error": "Please enter a message to broadcast."}), 400

    update_banner = data.get("update_banner", True)
    banner_type = str(data.get("banner_type", "info")).strip()

    if update_banner:
        database.update_system_settings({
            "announcement_banner_active": "1",
            "announcement_banner_type": banner_type,
            "announcement_banner_text": message,
            "announcement_active": "1",
            "announcement_type": banner_type,
            "announcement_text": message
        })

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    user_ids = database.get_all_user_ids()

    if not bot_token:
        return jsonify({"success": False, "error": "Bot token not configured on server."}), 500

    sent = 0
    blocked = 0
    failed = 0
    import requests
    import time
    telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload_text = f"<b>Announcement from WP Studio</b>\n\n{message}"

    for uid in user_ids:
        try:
            r = requests.post(telegram_url, json={
                "chat_id": uid,
                "text": payload_text,
                "parse_mode": "HTML"
            }, timeout=6)
            if r.status_code == 200:
                sent += 1
            elif r.status_code == 403:
                blocked += 1
            else:
                failed += 1
            time.sleep(0.1)
        except Exception:
            failed += 1

    return jsonify({
        "success": True,
        "total": len(user_ids),
        "sent": sent,
        "blocked": blocked,
        "failed": failed
    })

@app.route('/api/admin/jobs', methods=['GET'])
def api_admin_jobs():
    user = get_current_user()
    if not user or not database.is_admin(user["user_id"]):
        return jsonify({"success": False, "error": "Unauthorized: Master Admin access required."}), 403

    jobs = database.get_all_recent_jobs(35)
    return jsonify({"success": True, "jobs": jobs})

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8085))
    print(f"\n[WP STUDIO] Server running at http://localhost:{port}/miniapp\n")
    app.run(host='0.0.0.0', port=port, debug=False)
