import sqlite3
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("WPStudio")

DB_PATH = os.path.join(os.path.dirname(__file__), "wp_studio.db")

# Supabase Cloud Client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase_client = None

if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Connected to Supabase Cloud as Master Database.")
    except Exception as e:
        logger.warning(f"Supabase connection warning: {e}")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        credits INTEGER DEFAULT 20,
        tier TEXT DEFAULT 'Builder',
        custom_gemini_key TEXT,
        selected_model TEXT DEFAULT 'gemini-3.8-flash',
        stories_created INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS story_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        topic TEXT,
        style TEXT,
        genre TEXT,
        duration TEXT,
        pdf_path TEXT,
        created_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS story_jobs (
        job_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        source_input TEXT,
        source_title TEXT,
        transcript TEXT,
        culture TEXT DEFAULT 'Universal',
        style TEXT DEFAULT 'Stylised 3D',
        genre TEXT DEFAULT 'Action Thriller',
        timezone TEXT DEFAULT 'Africa/Lagos',
        length_tier TEXT DEFAULT 'Short',
        concepts_json TEXT,
        selected_concept_idx INTEGER,
        full_story_json TEXT,
        story_bible_pdf TEXT,
        scene_prompts_pdf TEXT,
        status TEXT DEFAULT 'draft',
        created_at TEXT,
        updated_at TEXT
    )
    """)
    try:
        cursor.execute("ALTER TABLE story_jobs ADD COLUMN delivery_format TEXT DEFAULT 'Dialogue / Narrative'")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE story_jobs ADD COLUMN job_type TEXT DEFAULT 'storycraft'")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE story_jobs ADD COLUMN story_text TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN custom_openai_key TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN custom_claude_key TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN selected_provider TEXT DEFAULT 'gemini'")
    except Exception:
        pass
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cast_characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        age TEXT,
        gender TEXT,
        complexion TEXT,
        nose_type TEXT,
        hairstyle TEXT,
        custom_hairstyle TEXT,
        hair_color TEXT,
        body_size TEXT,
        height TEXT,
        expression TEXT,
        outfit_style TEXT,
        custom_outfit TEXT,
        background TEXT DEFAULT 'Neutral studio',
        lighting TEXT DEFAULT 'Studio',
        art_style TEXT DEFAULT 'Realistic',
        purpose TEXT DEFAULT 'Film',
        reference_image_path TEXT,
        reference_instruction TEXT,
        vision_biometrics TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS credit_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        target_user_id INTEGER,
        action TEXT,
        amount INTEGER,
        previous_balance INTEGER,
        new_balance INTEGER,
        reason TEXT,
        created_at TEXT
    )
    """)

    # Seed default system settings if not exists
    default_settings = {
        "gemini_api_key_primary": os.getenv("GEMINI_API_KEY", ""),
        "gemini_api_key_fallback": "",
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "model_gemini_enabled": "1",
        "model_gpt_enabled": "1",
        "model_claude_enabled": "1",
        "default_provider": "gemini",
        "default_model": "gemini-3.8-flash",
        "byok_enabled": "1",  # Enabled for users by default
        "maintenance_mode": "0",
        "maintenance_message": "WP Studio is currently undergoing scheduled platform upgrades. All features will resume shortly.",
        "feature_storycraft_enabled": "1",
        "feature_character_forge_enabled": "1",
        "feature_thumbnail_lab_enabled": "1",
        "feature_frame_renderer_enabled": "1",
        "pricing_short_concepts": "10",
        "pricing_short_pdfs": "40",
        "pricing_medium_concepts": "50",
        "pricing_medium_pdfs": "250",
        "pricing_long_concepts": "100",
        "pricing_long_pdfs": "300",
        "pricing_forge_cost": "5",
        "pricing_thumb_cost": "3",
        "announcement_banner_text": "",
        "announcement_banner_active": "0"
    }
    now_ts = datetime.utcnow().isoformat()
    for k, v in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO system_settings (key, value, updated_at) VALUES (?, ?, ?)", (k, str(v), now_ts))
    cursor.execute("UPDATE system_settings SET value = '1' WHERE key = 'byok_enabled' AND value = '0'")

    # Migration safeguard for existing tables
    try:
        cursor.execute("PRAGMA table_info(cast_characters)")
        c_names = [row[1] for row in cursor.fetchall()]
        for col in ["reference_image_path", "reference_instruction", "vision_biometrics"]:
            if col not in c_names:
                cursor.execute(f"ALTER TABLE cast_characters ADD COLUMN {col} TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()
    # Always sync all creators from Supabase into local SQLite so admin is never wiped on restart
    sync_users_from_supabase()

def sync_users_from_supabase():
    """
    Syncs all creators from Supabase cloud into the local SQLite database.
    Prevents creators from ever disappearing when Render restarts or container redeploys.
    """
    if not supabase_client:
        return
    try:
        res = supabase_client.table("wp_studio_users").select("*").execute()
        if res.data:
            conn = get_connection()
            cursor = conn.cursor()
            for u in res.data:
                uid = u.get("user_id")
                if not uid:
                    continue
                username = u.get("username") or "Creator"
                credits = int(u.get("credits", 20))
                tier = u.get("tier", "Builder")
                custom_key = u.get("custom_gemini_key")
                selected_model = u.get("selected_model", "gemini-3.8-flash")
                stories_created = int(u.get("stories_created", 0))
                created_at = u.get("created_at") or datetime.utcnow().isoformat()
                updated_at = u.get("updated_at") or datetime.utcnow().isoformat()
                cursor.execute("""
                    INSERT INTO users (user_id, username, credits, tier, custom_gemini_key, selected_model, stories_created, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username=excluded.username,
                        credits=excluded.credits,
                        tier=excluded.tier,
                        custom_gemini_key=COALESCE(excluded.custom_gemini_key, users.custom_gemini_key),
                        selected_model=excluded.selected_model,
                        stories_created=excluded.stories_created,
                        updated_at=excluded.updated_at
                """, (uid, username, credits, tier, custom_key, selected_model, stories_created, created_at, updated_at))
            conn.commit()
            conn.close()
            logger.info(f"[DB SYNC] Successfully loaded {len(res.data)} creators from Supabase Cloud.")
    except Exception as e:
        logger.warning(f"[DB SYNC] Notice during Supabase user sync: {e}")


def get_user(user_id: int, username: str = None) -> dict:
    """
    Cloud-First: Reads directly from Supabase so any balance edits in the Supabase dashboard
    immediately reflect in Telegram. Falls back to local SQLite if offline.
    """
    now = datetime.utcnow().isoformat()
    user = None

    # 1. Read from Supabase first (Master Authority)
    if supabase_client:
        try:
            res = supabase_client.table("wp_studio_users").select("*").eq("user_id", user_id).execute()
            if res.data and len(res.data) > 0:
                user = res.data[0]
            else:
                new_user = {
                    "user_id": user_id,
                    "username": username or "Creator",
                    "credits": 20,
                    "tier": "Builder",
                    "custom_gemini_key": None,
                    "selected_model": "gemini-3.8-flash",
                    "stories_created": 0,
                    "created_at": now,
                    "updated_at": now
                }
                supabase_client.table("wp_studio_users").insert(new_user).execute()
                user = new_user
        except Exception as e:
            logger.warning(f"Supabase read notice, falling back to local cache: {e}")

    # 2. Sync to local SQLite cache
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if user:
        if row:
            row_d = dict(row)
            if not user.get("custom_openai_key") and row_d.get("custom_openai_key"):
                user["custom_openai_key"] = row_d.get("custom_openai_key")
            if not user.get("custom_claude_key") and row_d.get("custom_claude_key"):
                user["custom_claude_key"] = row_d.get("custom_claude_key")
            if not user.get("selected_provider") and row_d.get("selected_provider"):
                user["selected_provider"] = row_d.get("selected_provider")

            cursor.execute("""
                UPDATE users SET username=?, credits=?, tier=?, custom_gemini_key=?, custom_openai_key=COALESCE(?, custom_openai_key), custom_claude_key=COALESCE(?, custom_claude_key), selected_model=?, selected_provider=COALESCE(?, selected_provider), stories_created=?, updated_at=?
                WHERE user_id=?
            """, (user.get("username"), user["credits"], user.get("tier"), user.get("custom_gemini_key"), user.get("custom_openai_key"), user.get("custom_claude_key"), user.get("selected_model"), user.get("selected_provider", "gemini"), user.get("stories_created", 0), now, user_id))
        else:
            cursor.execute("""
                INSERT INTO users (user_id, username, credits, tier, custom_gemini_key, custom_openai_key, custom_claude_key, selected_model, selected_provider, stories_created, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, user.get("username"), user["credits"], user.get("tier"), user.get("custom_gemini_key"), user.get("custom_openai_key"), user.get("custom_claude_key"), user.get("selected_model"), user.get("selected_provider", "gemini"), user.get("stories_created", 0), now, now))
        conn.commit()
        conn.close()
        return user

    if not row:
        cursor.execute("""
            INSERT INTO users (user_id, username, credits, tier, custom_gemini_key, selected_model, stories_created, created_at, updated_at)
            VALUES (?, ?, 20, 'Builder', NULL, 'gemini-3.8-flash', 0, ?, ?)
        """, (user_id, username, now, now))
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

    user = dict(row)
    conn.close()
    return user

def deduct_credits(user_id: int, cost: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False

    # VIP / Admin Unlimited Credits: Never deplete balance
    if int(user.get("credits", 0)) >= 999999:
        return True

    if user["credits"] < cost:
        return False

    new_credits = user["credits"] - cost
    now = datetime.utcnow().isoformat()

    # 1. Deduct in Supabase
    if supabase_client:
        try:
            supabase_client.table("wp_studio_users").update({
                "credits": new_credits,
                "stories_created": user.get("stories_created", 0) + 1,
                "updated_at": now
            }).eq("user_id", user_id).execute()
        except Exception as e:
            logger.warning(f"Supabase deduct error: {e}")

    # 2. Deduct in local cache
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET credits = ?, stories_created = stories_created + 1, updated_at = ?
        WHERE user_id = ?
    """, (new_credits, now, user_id))
    conn.commit()
    conn.close()
    return True

def add_credits(user_id: int, amount: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    new_credits = user.get("credits", 0) + amount
    now = datetime.utcnow().isoformat()
    if supabase_client:
        try:
            supabase_client.table("wp_studio_users").update({
                "credits": new_credits,
                "updated_at": now
            }).eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"Error adding credits in Supabase: {e}")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET credits = ?, updated_at = ? WHERE user_id = ?", (new_credits, now, user_id))
    conn.commit()
    conn.close()
    return True

def update_user_key(user_id: int, api_key: str):
    update_user_custom_keys(user_id, gemini_key=api_key)

def update_user_custom_keys(user_id: int, gemini_key: str = None, openai_key: str = None, claude_key: str = None):
    now = datetime.utcnow().isoformat()
    clean_gem = gemini_key.strip() if (gemini_key is not None and gemini_key.strip()) else (None if gemini_key is not None else None)
    clean_gpt = openai_key.strip() if (openai_key is not None and openai_key.strip()) else (None if openai_key is not None else None)
    clean_claude = claude_key.strip() if (claude_key is not None and claude_key.strip()) else (None if claude_key is not None else None)

    if supabase_client:
        try:
            update_data = {"updated_at": now}
            if gemini_key is not None:
                update_data["custom_gemini_key"] = clean_gem
            if openai_key is not None:
                update_data["custom_openai_key"] = clean_gpt
            if claude_key is not None:
                update_data["custom_claude_key"] = clean_claude
            supabase_client.table("wp_studio_users").update(update_data).eq("user_id", user_id).execute()
        except Exception:
            pass

    conn = get_connection()
    cursor = conn.cursor()
    updates = []
    params = []
    if gemini_key is not None:
        updates.append("custom_gemini_key = ?")
        params.append(clean_gem)
    if openai_key is not None:
        updates.append("custom_openai_key = ?")
        params.append(clean_gpt)
    if claude_key is not None:
        updates.append("custom_claude_key = ?")
        params.append(clean_claude)
    updates.append("updated_at = ?")
    params.append(now)
    params.append(user_id)

    sql = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
    cursor.execute(sql, tuple(params))
    conn.commit()
    conn.close()

def update_user_model(user_id: int, model_name: str, provider: str = None):
    now = datetime.utcnow().isoformat()
    if supabase_client:
        try:
            up_dict = {"selected_model": model_name, "updated_at": now}
            if provider:
                up_dict["selected_provider"] = provider
            supabase_client.table("wp_studio_users").update(up_dict).eq("user_id", user_id).execute()
        except Exception:
            pass

    conn = get_connection()
    cursor = conn.cursor()
    if provider:
        cursor.execute("UPDATE users SET selected_model = ?, selected_provider = ?, updated_at = ? WHERE user_id = ?", (model_name, provider, now, user_id))
    else:
        cursor.execute("UPDATE users SET selected_model = ?, updated_at = ? WHERE user_id = ?", (model_name, now, user_id))
    conn.commit()
    conn.close()

def log_story(user_id: int, title: str, topic: str, style: str, genre: str, duration: str, pdf_path: str = None):
    now = datetime.utcnow().isoformat()
    if supabase_client:
        try:
            supabase_client.table("wp_studio_story_history").insert({
                "user_id": user_id,
                "title": title,
                "topic": topic,
                "style": style,
                "genre": genre,
                "duration": duration,
                "pdf_path": pdf_path,
                "created_at": now
            }).execute()
        except Exception:
            pass

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO story_history (user_id, title, topic, style, genre, duration, pdf_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, title, topic, style, genre, duration, pdf_path, now))
    conn.commit()
    conn.close()

def create_story_job(user_id: int, source_input: str, source_title: str, transcript: str, culture: str, style: str, genre: str, timezone: str, length_tier: str, delivery_format: str = "Dialogue / Narrative", job_type: str = "storycraft", story_text: str = "") -> int:
    now = datetime.utcnow().isoformat()
    highest_id = 0

    # 1. Fetch highest job_id from Supabase to prevent duplicate primary key errors across container restarts
    if supabase_client:
        try:
            res = supabase_client.table("wp_studio_jobs").select("job_id").order("job_id", desc=True).limit(1).execute()
            if res.data and len(res.data) > 0 and res.data[0].get("job_id"):
                highest_id = max(highest_id, int(res.data[0]["job_id"]))
        except Exception as e:
            logger.warning(f"Supabase max job_id lookup error: {e}")

    # 2. Check highest job_id in local SQLite
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(job_id) FROM story_jobs")
    row = cursor.fetchone()
    if row and row[0]:
        highest_id = max(highest_id, int(row[0]))

    new_job_id = highest_id + 1

    # 3. Insert into SQLite
    cursor.execute("""
        INSERT INTO story_jobs (job_id, user_id, source_input, source_title, transcript, culture, style, genre, timezone, length_tier, delivery_format, job_type, story_text, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
    """, (new_job_id, user_id, source_input, source_title, transcript, culture, style, genre, timezone, length_tier, delivery_format, job_type, story_text, now, now))
    conn.commit()
    conn.close()

    # 4. Insert into Supabase Master Database
    if supabase_client:
        try:
            job_payload = {
                "job_id": new_job_id,
                "user_id": user_id,
                "source_input": source_input,
                "source_title": source_title,
                "transcript": transcript,
                "culture": culture,
                "style": style,
                "genre": genre,
                "timezone": timezone,
                "length_tier": length_tier,
                "status": "draft",
                "created_at": now,
                "updated_at": now
            }
            if delivery_format:
                job_payload["delivery_format"] = delivery_format
            try:
                supabase_client.table("wp_studio_jobs").insert(job_payload).execute()
            except Exception as se:
                if "delivery_format" in str(se):
                    job_payload.pop("delivery_format", None)
                    supabase_client.table("wp_studio_jobs").insert(job_payload).execute()
                else:
                    raise se
        except Exception as e:
            logger.warning(f"Supabase insert job notice: {e}")

    return new_job_id

def update_job_concepts(job_id: int, concepts_json):
    now = datetime.utcnow().isoformat()
    c_str = json.dumps(concepts_json) if not isinstance(concepts_json, str) else concepts_json
    c_parsed = json.loads(concepts_json) if isinstance(concepts_json, str) else concepts_json

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE story_jobs SET concepts_json = ?, status = 'concepts_ready', updated_at = ? WHERE job_id = ?", (c_str, now, job_id))
    conn.commit()
    conn.close()

    if supabase_client:
        try:
            supabase_client.table("wp_studio_jobs").update({
                "concepts_json": c_parsed,
                "status": "concepts_ready",
                "updated_at": now
            }).eq("job_id", job_id).execute()
        except Exception as e:
            logger.warning(f"Supabase update concepts notice: {e}")

def update_job_selection(job_id: int, selected_idx: int):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE story_jobs SET selected_concept_idx = ?, status = 'concept_selected', updated_at = ? WHERE job_id = ?", (selected_idx, now, job_id))
    conn.commit()
    conn.close()

    if supabase_client:
        try:
            supabase_client.table("wp_studio_jobs").update({
                "selected_concept_idx": selected_idx,
                "status": "concept_selected",
                "updated_at": now
            }).eq("job_id", job_id).execute()
        except Exception as e:
            logger.warning(f"Supabase update selection notice: {e}")

def update_job_completion(job_id: int, full_story_json, bible_pdf: str, scene_pdf: str):
    now = datetime.utcnow().isoformat()
    s_str = json.dumps(full_story_json) if not isinstance(full_story_json, str) else full_story_json
    s_parsed = json.loads(full_story_json) if isinstance(full_story_json, str) else full_story_json

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE story_jobs SET full_story_json = ?, story_bible_pdf = ?, scene_prompts_pdf = ?, status = 'completed', updated_at = ? WHERE job_id = ?", (s_str, bible_pdf, scene_pdf, now, job_id))
    conn.commit()
    conn.close()

    if supabase_client:
        try:
            supabase_client.table("wp_studio_jobs").update({
                "full_story_json": s_parsed,
                "story_bible_pdf": bible_pdf,
                "scene_prompts_pdf": scene_pdf,
                "status": "completed",
                "updated_at": now
            }).eq("job_id", job_id).execute()
        except Exception as e:
            logger.warning(f"Supabase update completion notice: {e}")

def get_job(job_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM story_jobs WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()

    # If already found locally with full story, return immediately
    if row and row["full_story_json"]:
        return dict(row)

    # If missing locally or after container restart, fetch from Supabase Master DB
    if supabase_client:
        try:
            res = supabase_client.table("wp_studio_jobs").select("*").eq("job_id", job_id).execute()
            if res.data and len(res.data) > 0:
                s_job = res.data[0]
                c_json = s_job.get("concepts_json")
                if isinstance(c_json, (list, dict)):
                    c_json = json.dumps(c_json)
                f_json = s_job.get("full_story_json")
                if isinstance(f_json, (list, dict)):
                    f_json = json.dumps(f_json)

                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO story_jobs (
                        job_id, user_id, source_input, source_title, transcript,
                        culture, style, genre, timezone, length_tier,
                        concepts_json, selected_concept_idx, full_story_json,
                        story_bible_pdf, scene_prompts_pdf, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        source_input = excluded.source_input,
                        source_title = excluded.source_title,
                        transcript = excluded.transcript,
                        culture = excluded.culture,
                        style = excluded.style,
                        genre = excluded.genre,
                        timezone = excluded.timezone,
                        length_tier = excluded.length_tier,
                        concepts_json = excluded.concepts_json,
                        selected_concept_idx = excluded.selected_concept_idx,
                        full_story_json = excluded.full_story_json,
                        story_bible_pdf = excluded.story_bible_pdf,
                        scene_prompts_pdf = excluded.scene_prompts_pdf,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                """, (
                    s_job.get("job_id"),
                    s_job.get("user_id"),
                    s_job.get("source_input"),
                    s_job.get("source_title"),
                    s_job.get("transcript"),
                    s_job.get("culture", "Universal"),
                    s_job.get("style", "Stylised 3D"),
                    s_job.get("genre", "Action Thriller"),
                    s_job.get("timezone", "Africa/Lagos"),
                    s_job.get("length_tier", "Short"),
                    c_json,
                    s_job.get("selected_concept_idx"),
                    f_json,
                    s_job.get("story_bible_pdf"),
                    s_job.get("scene_prompts_pdf"),
                    s_job.get("status", "draft"),
                    s_job.get("created_at"),
                    s_job.get("updated_at")
                ))
                conn.commit()
                conn.close()

                s_job["concepts_json"] = c_json
                s_job["full_story_json"] = f_json
                return s_job
        except Exception as e:
            logger.warning(f"Supabase get_job notice: {e}")

    return dict(row) if row else None

def get_user_story_history(user_id: int) -> list:
    now = datetime.utcnow().isoformat()

    # 1. Fetch from Supabase Cloud first (Master Authority across container restarts)
    if supabase_client:
        try:
            res = supabase_client.table("wp_studio_jobs").select("*").eq("user_id", user_id).order("job_id", desc=True).limit(50).execute()
            if res.data:
                conn = get_connection()
                cursor = conn.cursor()
                for row in res.data:
                    c_json = row.get("concepts_json")
                    if isinstance(c_json, (list, dict)):
                        c_json = json.dumps(c_json)
                    f_json = row.get("full_story_json")
                    if isinstance(f_json, (list, dict)):
                        f_json = json.dumps(f_json)

                    cursor.execute("""
                        INSERT INTO story_jobs (
                            job_id, user_id, source_input, source_title, transcript,
                            culture, style, genre, timezone, length_tier,
                            concepts_json, selected_concept_idx, full_story_json,
                            story_bible_pdf, scene_prompts_pdf, status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(job_id) DO UPDATE SET
                            source_input = excluded.source_input,
                            source_title = excluded.source_title,
                            transcript = excluded.transcript,
                            culture = excluded.culture,
                            style = excluded.style,
                            genre = excluded.genre,
                            timezone = excluded.timezone,
                            length_tier = excluded.length_tier,
                            concepts_json = excluded.concepts_json,
                            selected_concept_idx = excluded.selected_concept_idx,
                            full_story_json = excluded.full_story_json,
                            story_bible_pdf = excluded.story_bible_pdf,
                            scene_prompts_pdf = excluded.scene_prompts_pdf,
                            status = excluded.status,
                            updated_at = excluded.updated_at
                    """, (
                        row.get("job_id"),
                        row.get("user_id"),
                        row.get("source_input"),
                        row.get("source_title"),
                        row.get("transcript"),
                        row.get("culture", "Universal"),
                        row.get("style", "Stylised 3D"),
                        row.get("genre", "Action Thriller"),
                        row.get("timezone", "Africa/Lagos"),
                        row.get("length_tier", "Short"),
                        c_json,
                        row.get("selected_concept_idx"),
                        f_json,
                        row.get("story_bible_pdf"),
                        row.get("scene_prompts_pdf"),
                        row.get("status", "draft"),
                        row.get("created_at") or now,
                        row.get("updated_at") or now
                    ))
                conn.commit()
                conn.close()
        except Exception as e:
            logger.warning(f"Supabase fetch story history notice: {e}")

    # 2. Return all screenplays from local synced cache
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT job_id, user_id, source_input, source_title, culture, style, genre, length_tier,
               concepts_json, selected_concept_idx, full_story_json, story_bible_pdf, scene_prompts_pdf, status, created_at
        FROM story_jobs
        WHERE user_id = ?
        ORDER BY job_id DESC
        LIMIT 50
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ============================================================================
# WP CASTLOCK — CHARACTER PERSISTENCE & ROSTER ENGINE
# ============================================================================
def save_character(user_id: int, char_data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    char_id = char_data.get("id")

    if char_id:
        cursor.execute("""
        UPDATE cast_characters SET
            name = ?, age = ?, gender = ?, complexion = ?, nose_type = ?,
            hairstyle = ?, custom_hairstyle = ?, hair_color = ?, body_size = ?,
            height = ?, expression = ?, outfit_style = ?, custom_outfit = ?,
            background = ?, lighting = ?, art_style = ?, purpose = ?,
            reference_image_path = ?, reference_instruction = ?, vision_biometrics = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """, (
            char_data.get("name", "Kemi"), str(char_data.get("age", "28")), char_data.get("gender", "Female"),
            char_data.get("complexion", "Medium brown"), char_data.get("nose_type", "Broad / Wide"),
            char_data.get("hairstyle", "Braids"), char_data.get("custom_hairstyle", ""),
            char_data.get("hair_color", "Black (#000000)"), char_data.get("body_size", "Average"),
            char_data.get("height", "Tall"), char_data.get("expression", "Happy"),
            char_data.get("outfit_style", "Ankara"), char_data.get("custom_outfit", ""),
            char_data.get("background", "Neutral studio"), char_data.get("lighting", "Studio"),
            char_data.get("art_style", "Realistic"), char_data.get("purpose", "Film"),
            char_data.get("reference_image_path"), char_data.get("reference_instruction"), char_data.get("vision_biometrics"),
            now, char_id, user_id
        ))
    else:
        cursor.execute("""
        INSERT INTO cast_characters (
            user_id, name, age, gender, complexion, nose_type,
            hairstyle, custom_hairstyle, hair_color, body_size,
            height, expression, outfit_style, custom_outfit,
            background, lighting, art_style, purpose,
            reference_image_path, reference_instruction, vision_biometrics, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, char_data.get("name", "Kemi"), str(char_data.get("age", "28")), char_data.get("gender", "Female"),
            char_data.get("complexion", "Medium brown"), char_data.get("nose_type", "Broad / Wide"),
            char_data.get("hairstyle", "Braids"), char_data.get("custom_hairstyle", ""),
            char_data.get("hair_color", "Black (#000000)"), char_data.get("body_size", "Average"),
            char_data.get("height", "Tall"), char_data.get("expression", "Happy"),
            char_data.get("outfit_style", "Ankara"), char_data.get("custom_outfit", ""),
            char_data.get("background", "Neutral studio"), char_data.get("lighting", "Studio"),
            char_data.get("art_style", "Realistic"), char_data.get("purpose", "Film"),
            char_data.get("reference_image_path"), char_data.get("reference_instruction"), char_data.get("vision_biometrics"),
            now, now
        ))
        char_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return char_id

def get_user_characters(user_id: int) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cast_characters WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_character_by_id(char_id: int, user_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cast_characters WHERE id = ? AND user_id = ?", (char_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_character(char_id: int, user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cast_characters WHERE id = ? AND user_id = ?", (char_id, user_id))
    conn.commit()
    conn.close()

# ============================================================================
# MASTER ADMIN GOVERNANCE & AUDIT ENGINE
# ============================================================================
ADMIN_ID = int(os.getenv("ADMIN_ID", 5628105961))

def is_admin(user_id) -> bool:
    try:
        return int(user_id or 0) == ADMIN_ID
    except (ValueError, TypeError):
        return False

def get_system_settings() -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM system_settings")
    rows = cursor.fetchall()
    conn.close()
    settings = {r["key"]: r["value"] for r in rows}
    # Ensure fallbacks if table was just created
    if "byok_enabled" not in settings:
        settings["byok_enabled"] = "0"
    if "maintenance_mode" not in settings:
        settings["maintenance_mode"] = "0"
    return settings

def get_master_gemini_keys() -> tuple:
    """
    Returns (primary_key, fallback_key) from dynamic system_settings or environment.
    """
    primary_key = ""
    fallback_key = ""
    try:
        settings = get_system_settings()
        primary_key = (settings.get("gemini_api_key_primary") or "").strip()
        fallback_key = (settings.get("gemini_api_key_fallback") or "").strip()
    except Exception:
        pass
    if not primary_key:
        primary_key = os.getenv("DEFAULT_GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    return primary_key, fallback_key

def update_system_settings(new_settings: dict) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    now_ts = datetime.utcnow().isoformat()
    for k, v in new_settings.items():
        cursor.execute("""
        INSERT INTO system_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (str(k), str(v), now_ts))
    conn.commit()
    conn.close()
    return get_system_settings()

def get_all_users(search: str = None, limit: int = 50) -> list:
    # Ensure fresh sync from Supabase cloud
    sync_users_from_supabase()
    conn = get_connection()
    cursor = conn.cursor()
    if search:
        s = f"%{search.strip()}%"
        cursor.execute("""
        SELECT user_id, username, credits, tier, custom_gemini_key IS NOT NULL as has_custom_key,
               stories_created, created_at, updated_at
        FROM users
        WHERE username LIKE ? OR CAST(user_id AS TEXT) LIKE ?
        ORDER BY credits DESC, updated_at DESC LIMIT ?
        """, (s, s, limit))
    else:
        cursor.execute("""
        SELECT user_id, username, credits, tier, custom_gemini_key IS NOT NULL as has_custom_key,
               stories_created, created_at, updated_at
        FROM users
        ORDER BY updated_at DESC, credits DESC LIMIT ?
        """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_user_ids() -> list:
    """Returns all unique real Telegram user IDs registered in SQLite and Supabase."""
    user_ids = set()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT user_id FROM users WHERE user_id > 1000000")
        for r in cursor.fetchall():
            if r["user_id"]:
                try:
                    user_ids.add(int(r["user_id"]))
                except (ValueError, TypeError):
                    pass
        conn.close()
    except Exception as e:
        logger.error(f"Error getting SQLite user IDs: {e}")

    if supabase_client:
        try:
            res = supabase_client.table("wp_studio_users").select("user_id").gt("user_id", 1000000).execute()
            if res.data:
                for row in res.data:
                    uid = row.get("user_id")
                    if uid:
                        try:
                            user_ids.add(int(uid))
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.warning(f"Error getting Supabase user IDs: {e}")

    return sorted(list(user_ids))

def admin_modify_user_credits(admin_id: int, target_user_id: int, action: str, amount: int, reason: str = "") -> dict:
    try:
        target_user_id = int(target_user_id)
        amount = int(amount)
        admin_id = int(admin_id)
    except (ValueError, TypeError):
        return {"success": False, "error": "Invalid target_user_id or amount format."}

    target_user = get_user(target_user_id)
    if not target_user:
        return {"success": False, "error": f"User ID {target_user_id} not found."}

    prev_balance = int(target_user.get("credits", 0))

    if action == "unlimited":
        new_balance = 999999999
        amount = 999999999
    elif action == "add":
        new_balance = prev_balance + amount
    elif action == "deduct":
        new_balance = max(0, prev_balance - amount)
    elif action == "set":
        new_balance = max(0, amount)
    else:
        return {"success": False, "error": "Invalid action. Use 'add', 'deduct', 'set', or 'unlimited'."}

    now_ts = datetime.utcnow().isoformat()

    # 1. Update SQLite
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET credits = ?, updated_at = ? WHERE user_id = ?", (new_balance, now_ts, target_user_id))
    cursor.execute("""
    INSERT INTO credit_transactions (admin_id, target_user_id, action, amount, previous_balance, new_balance, reason, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (admin_id, target_user_id, action, amount, prev_balance, new_balance, reason or "Admin manual adjustment", now_ts))
    conn.commit()
    conn.close()

    # 2. Sync to Supabase if active
    if supabase_client:
        try:
            supabase_client.table("wp_studio_users").update({"credits": new_balance, "updated_at": now_ts}).eq("user_id", target_user_id).execute()
        except Exception as se:
            logger.warning(f"Supabase balance sync warning: {se}")

    refreshed = get_user(target_user_id)
    return {
        "success": True,
        "previous_balance": prev_balance,
        "new_balance": new_balance,
        "user": refreshed,
        "action": action,
        "amount": amount
    }

def admin_set_user_tier(admin_id: int, target_user_id: int, tier: str) -> bool:
    try:
        target_user_id = int(target_user_id)
        admin_id = int(admin_id)
    except (ValueError, TypeError):
        return False
    now_ts = datetime.utcnow().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tier = ?, updated_at = ? WHERE user_id = ?", (tier, now_ts, target_user_id))
    conn.commit()
    conn.close()
    if supabase_client:
        try:
            supabase_client.table("wp_studio_users").update({"tier": tier, "updated_at": now_ts}).eq("user_id", target_user_id).execute()
        except Exception:
            pass
    return True

def get_credit_transactions(limit: int = 30) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT t.*, u.username as target_username
    FROM credit_transactions t
    LEFT JOIN users u ON t.target_user_id = u.user_id
    ORDER BY t.id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_system_stats() -> dict:
    sync_users_from_supabase()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COALESCE(SUM(credits), 0) FROM users")
    total_credits = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM story_jobs WHERE status = 'completed'")
    total_stories = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM cast_characters")
    total_chars = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM story_jobs")
    total_jobs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM users WHERE custom_gemini_key IS NOT NULL AND custom_gemini_key != ''")
    byok_users = cursor.fetchone()[0]

    conn.close()
    return {
        "total_users": total_users,
        "active_users_24h": total_users,
        "total_credits_in_circulation": total_credits,
        "total_stories_produced": total_stories,
        "total_story_jobs": total_jobs,
        "total_characters": total_chars,
        "total_characters_forged": total_chars,
        "total_jobs": total_jobs,
        "byok_users_count": byok_users
    }

def get_all_recent_jobs(limit: int = 30) -> list:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT j.job_id, j.user_id, u.username, j.source_title, j.culture, j.style, j.genre,
           j.length_tier, j.story_bible_pdf, j.scene_prompts_pdf, j.status, j.created_at
    FROM story_jobs j
    LEFT JOIN users u ON j.user_id = u.user_id
    ORDER BY j.job_id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Initialize on import
init_db()
