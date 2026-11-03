import os
import re
import json
import time
import logging
import asyncio
import urllib.parse
import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
logger = logging.getLogger("WPStudio")

DEFAULT_KEY = os.getenv("DEFAULT_GEMINI_API_KEY", "")

# Available AI Models for YouTube Automation Creators
AVAILABLE_MODELS = {
    # Google Gemini Models
    "gemini-3.8-flash": "Gemini 3.8 Flash (Cinematic & Fast)",
    "gemini-3.5-flash": "Gemini 3.5 Flash (Ultra-Stable)",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite (Fast)",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro (Deep Reasoning)",
    # OpenAI ChatGPT Models
    "gpt-4o": "ChatGPT GPT-4o (High-Intelligence Scripting)",
    "gpt-4o-mini": "ChatGPT GPT-4o Mini (Fast & Efficient)",
    "chatgpt-4o": "ChatGPT GPT-4o (High-Intelligence Scripting)",
    # Anthropic Claude Models (BYOK Only)
    "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet (Narrative Depth & Rich Dialogue)",
    "claude-3-5-haiku-20241022": "Claude 3.5 Haiku (Ultra-Fast Scripting)",
    "claude-3-7-sonnet": "Claude 3.5 Sonnet (Narrative Depth & Rich Dialogue)"
}

DEFAULT_MODEL = "gemini-3.5-flash-lite"

def get_model_provider(model_name: str) -> str:
    """Returns 'gemini', 'gpt', or 'claude' based on the requested model name."""
    if not model_name:
        return "gemini"
    m = model_name.lower()
    if "claude" in m:
        return "claude"
    if "gpt" in m or "openai" in m or "chatgpt" in m:
        return "gpt"
    return "gemini"

def get_provider_availability(user_dict=None) -> dict:
    """
    Evaluates availability for Gemini, GPT, and Claude:
    - Gemini: Available if platform primary key or user BYOK key is set.
    - GPT: Available if server key or user BYOK key is set. Otherwise marked unavailable.
    - Claude: Strictly requires user personal custom key.
    - Respects administrator toggles for each provider.
    """
    try:
        import database
        settings = database.get_system_settings()
    except Exception:
        settings = {}

    is_admin = bool(user_dict and user_dict.get("is_admin"))
    byok_allowed = (str(settings.get("byok_enabled", "1")).lower() not in ("0", "false") or is_admin)

    # 1. Gemini
    gem_primary, _ = get_master_keys()
    user_gem = (user_dict.get("custom_gemini_key") or "").strip() if user_dict else ""
    gem_has_key = bool(gem_primary or (user_gem and byok_allowed))
    gem_admin = str(settings.get("model_gemini_enabled", "1")).lower() not in ("0", "false")
    gem_avail = gem_has_key and gem_admin
    gem_reason = "" if gem_avail else ("Temporarily unavailable" if not gem_admin else "API key required")

    # 2. GPT (OpenAI)
    server_gpt = (settings.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")).strip()
    user_gpt = (user_dict.get("custom_openai_key") or "").strip() if user_dict else ""
    gpt_has_key = bool(server_gpt or (user_gpt and byok_allowed))
    gpt_admin = str(settings.get("model_gpt_enabled", "1")).lower() not in ("0", "false")
    gpt_avail = gpt_has_key and gpt_admin
    gpt_reason = ""
    if not gpt_admin:
        gpt_reason = "Temporarily unavailable"
    elif not gpt_has_key:
        gpt_reason = "API key required"

    # 3. Claude (Anthropic) - strictly requires user custom key
    user_claude = (user_dict.get("custom_claude_key") or "").strip() if user_dict else ""
    claude_has_key = bool(user_claude and byok_allowed)
    claude_admin = str(settings.get("model_claude_enabled", "1")).lower() not in ("0", "false")
    claude_avail = claude_has_key and claude_admin
    claude_reason = ""
    if not claude_admin:
        claude_reason = "Temporarily unavailable"
    elif not claude_has_key:
        claude_reason = "API key required"

    return {
        "gemini": {
            "provider": "gemini",
            "name": "Google Gemini",
            "available": gem_avail,
            "models": ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro-preview"],
            "default_model": "gemini-3.8-flash",
            "has_key": gem_has_key,
            "has_user_byok": bool(user_gem and byok_allowed),
            "admin_enabled": gem_admin,
            "reason": gem_reason
        },
        "gpt": {
            "provider": "gpt",
            "name": "OpenAI ChatGPT",
            "available": gpt_avail,
            "models": ["gpt-4o", "gpt-4o-mini"],
            "default_model": "gpt-4o",
            "has_key": gpt_has_key,
            "has_user_byok": bool(user_gpt and byok_allowed),
            "admin_enabled": gpt_admin,
            "reason": gpt_reason
        },
        "claude": {
            "provider": "claude",
            "name": "Anthropic Claude",
            "available": claude_avail,
            "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
            "default_model": "claude-3-5-sonnet-20241022",
            "has_key": claude_has_key,
            "has_user_byok": bool(user_claude and byok_allowed),
            "admin_enabled": claude_admin,
            "reason": claude_reason
        }
    }

# Fallback chain for Gemini
FALLBACK_CHAIN = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"]

def clean_json_loads(text: str):
    """Safely extracts and parses JSON even if wrapped in markdown code fences, with trailing text, or truncated mid-stream."""
    if not text:
        return {}
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except Exception:
        start_obj = clean.find("{")
        end_obj = clean.rfind("}")
        if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
            try:
                return json.loads(clean[start_obj:end_obj+1])
            except Exception:
                pass
        start_arr = clean.find("[")
        end_arr = clean.rfind("]")
        if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
            try:
                return json.loads(clean[start_arr:end_arr+1])
            except Exception:
                pass

        # Automatic Truncated JSON Recovery (if output hit token ceiling mid-scene)
        if start_obj != -1:
            sub = clean[start_obj:]
            search_pos = len(sub)
            for _ in range(50):
                brace_idx = sub.rfind("}", 0, search_pos)
                if brace_idx == -1:
                    break
                candidate_base = sub[:brace_idx + 1]
                for suffix in ("]}", "}", "]]}", "]"):
                    try:
                        parsed = json.loads(candidate_base + suffix)
                        if isinstance(parsed, (dict, list)):
                            logger.warning(f"Recovered truncated JSON cleanly at char {brace_idx} using suffix '{suffix}'")
                            return parsed
                    except Exception:
                        pass
                search_pos = brace_idx
        raise

def get_master_keys():
    """Fetches master primary and fallback keys from dynamic settings or environment."""
    primary_key = ""
    fallback_key = ""
    try:
        import database
        settings = database.get_system_settings()
        primary_key = (settings.get("gemini_api_key_primary") or "").strip()
        fallback_key = (settings.get("gemini_api_key_fallback") or "").strip()
    except Exception:
        pass
    if not primary_key:
        primary_key = os.getenv("DEFAULT_GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    return primary_key, fallback_key

def get_client(user_api_key=None, use_fallback_key=False):
    """Returns a GenAI client using user's key if allowed, else platform master primary/fallback."""
    primary_key, fallback_key = get_master_keys()

    # Check if BYOK is globally allowed
    effective_user_key = user_api_key
    if user_api_key and user_api_key.strip():
        try:
            import database
            settings = database.get_system_settings()
            if settings.get("byok_enabled") != "1":
                effective_user_key = None
        except Exception:
            pass

    if effective_user_key and effective_user_key.strip():
        key = effective_user_key.strip()
    elif use_fallback_key and fallback_key:
        key = fallback_key
    else:
        key = primary_key

    if not key:
        raise ValueError("No Gemini API Key available! Please configure your master key in Admin Settings.")
    return genai.Client(api_key=key.strip())

def generate_with_fallback(client, preferred_model, contents, config, user_api_key=None):
    """
    Executes generation with automatic fallback if Google Cloud experiences temporary traffic spikes.
    Includes exponential pause to bypass 503 spikes safely, plus multi-key failover if primary key quota is hit.
    """
    models_to_try = [preferred_model]
    for m in FALLBACK_CHAIN:
        if m not in models_to_try:
            models_to_try.append(m)

    # Only include pro if user supplied their own paid/byok key
    if user_api_key and "gemini-3.1-pro-preview" not in models_to_try:
        models_to_try.append("gemini-3.1-pro-preview")

    last_err = None
    for attempt, m in enumerate(models_to_try, 1):
        try:
            return client.models.generate_content(model=m, contents=contents, config=config)
        except Exception as e:
            err_str = str(e)
            if "max_output_tokens" in err_str.lower() and isinstance(config, dict) and "max_output_tokens" in config:
                try:
                    fallback_cfg = {k: v for k, v in config.items() if k != "max_output_tokens"}
                    return client.models.generate_content(model=m, contents=contents, config=fallback_cfg)
                except Exception as inner_e:
                    e = inner_e
                    err_str = str(e)
            logger.warning(f"Model {m} failed ({err_str[:120]}...), trying fallback (attempt {attempt}/{len(models_to_try)})...")
            last_err = e
            # If rate limit or quota exceeded and we have a secondary key, attempt failover
            if ("429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str) and not user_api_key:
                primary_k, fallback_k = get_master_keys()
                if fallback_k and fallback_k != primary_k:
                    try:
                        logger.info("Attempting GenAI auto-failover to secondary Master API key...")
                        fallback_client = get_client(use_fallback_key=True)
                        return fallback_client.models.generate_content(model=m, contents=contents, config=config)
                    except Exception as fe:
                        logger.warning(f"Fallback key also failed: {fe}")
            # Switch to alternate fallback model immediately without blocking
            if "429" in err_str:
                time.sleep(1.0)
            continue
    raise last_err

def generate_ai_completion(
    preferred_model: str,
    system_instruction: str,
    prompt: str,
    temperature: float = 0.7,
    json_mode: bool = True,
    user_keys: dict = None,
    user_api_key: str = None
) -> str:
    """
    Unified multi-provider AI completion engine:
    - Gemini: Uses Google GenAI client with fallback chain.
    - GPT: Uses OpenAI REST API via httpx (respects server key or user BYOK key).
    - Claude: Uses Anthropic REST API via httpx (strictly requires user BYOK key).
    """
    keys = {}
    if isinstance(user_keys, dict):
        keys = dict(user_keys)
    elif user_api_key:
        keys = {"custom_gemini_key": user_api_key}

    provider = get_model_provider(preferred_model)

    import database
    settings = database.get_system_settings()
    is_admin = bool(keys.get("is_admin"))
    byok_allowed = (settings.get("byok_enabled") == "1" or is_admin)

    # 1. GPT (OpenAI)
    if provider == "gpt":
        if settings.get("model_gpt_enabled", "1") == "0":
            raise ValueError("This model is currently unavailable. Please select another model.")

        key = ""
        user_gpt = keys.get("custom_openai_key")
        if user_gpt and byok_allowed:
            key = user_gpt.strip()
        if not key:
            key = (settings.get("openai_api_key") or os.getenv("OPENAI_API_KEY", "")).strip()

        if not key:
            raise ValueError("This model requires an API key. Please configure your key in Settings or choose another model.")

        actual_model = "gpt-4o"
        if "mini" in preferred_model.lower():
            actual_model = "gpt-4o-mini"

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ]
        payload = {
            "model": actual_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 16384
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=180.0) as http_client:
            resp = http_client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)

        if resp.status_code != 200:
            err_msg = resp.text
            try:
                err_data = resp.json().get("error", {})
                err_msg = err_data.get("message", err_msg)
            except Exception:
                pass
            print(f"[GPT API ERROR] ({resp.status_code}): {err_msg}")
            raise ValueError("The selected model could not process your request. Please verify your API key in Settings or choose another model.")

        data = resp.json()
        return data["choices"][0]["message"]["content"]

    # 2. Claude (Anthropic)
    elif provider == "claude":
        if settings.get("model_claude_enabled", "1") == "0":
            raise ValueError("This model is currently unavailable. Please select another model.")

        key = ""
        user_claude = keys.get("custom_claude_key")
        if user_claude and byok_allowed:
            key = user_claude.strip()

        if not key:
            server_claude = (settings.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")).strip()
            if server_claude and is_admin:
                key = server_claude

        if not key:
            raise ValueError("This model requires an API key. Please configure your key in Settings or choose another model.")

        actual_model = "claude-3-5-sonnet-20241022"
        if "haiku" in preferred_model.lower():
            actual_model = "claude-3-5-haiku-20241022"

        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        sys_prompt = system_instruction
        if json_mode:
            sys_prompt += "\n\nCRITICAL: Return ONLY valid, parseable JSON conforming strictly to the requested schema. No conversational prose or markdown code fences outside the JSON object."

        payload = {
            "model": actual_model,
            "max_tokens": 8192,
            "system": sys_prompt,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }

        with httpx.Client(timeout=180.0) as http_client:
            resp = http_client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)

        if resp.status_code != 200:
            err_msg = resp.text
            try:
                err_data = resp.json().get("error", {})
                err_msg = err_data.get("message", err_msg)
            except Exception:
                pass
            print(f"[CLAUDE API ERROR] ({resp.status_code}): {err_msg}")
            raise ValueError("The selected model could not process your request. Please verify your API key in Settings or choose another model.")

        data = resp.json()
        content_blocks = data.get("content", [])
        return "".join([b.get("text", "") for b in content_blocks if b.get("type") == "text"])

    # 3. Google Gemini
    else:
        if settings.get("model_gemini_enabled", "1") == "0":
            raise ValueError("This model is currently unavailable. Please select another model.")

        gem_key = keys.get("custom_gemini_key")
        client = get_client(user_api_key=gem_key)
        config = {
            "system_instruction": system_instruction,
            "temperature": temperature,
            "max_output_tokens": 65536
        }
        if json_mode:
            config["response_mime_type"] = "application/json"

        response = generate_with_fallback(
            client=client,
            preferred_model=preferred_model,
            contents=prompt,
            config=config,
            user_api_key=gem_key
        )
        return response.text

async def generate_ten_concepts(source_title: str, source_context: str, culture: str = "Universal", visual_style: str = "Stylised 3D", genre: str = "Action Thriller", lead_character: dict = None, user_api_key: str = None, model_name: str = None, user_keys: dict = None) -> list:
    """
    Step 1 of WP StoryCraft:
    Generates 10 distinct, high-CTR, original YouTube story concepts with tightened viral pacing.
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL

    char_clause = ""
    if lead_character and isinstance(lead_character, dict):
        c_name = lead_character.get("name", "Protagonist")
        c_gender = lead_character.get("gender", "")
        c_age = lead_character.get("age", "")
        c_complexion = lead_character.get("complexion", "")
        c_hair = lead_character.get("hairstyle", "")
        c_outfit = lead_character.get("outfit", "")
        char_clause = f"""
LOCKED LEAD PROTAGONIST (WP CastLock IP Continuity):
- Protagonist Name: {c_name}
- Biometrics: {c_age} years old, {c_gender}, {c_complexion} skin tone
- Signature Look: {c_hair} hairstyle, {c_outfit}
MANDATE: Every single one of the 10 viral concepts MUST center on {c_name} as the main character / lead protagonist. Adapt the plot twists, conflicts, and hooks around this exact protagonist.
"""

    genre_lower = (genre or "").lower()
    if "auto-detect" in genre_lower or "adaptive" in genre_lower:
        genre_spec = "- Genre / Narrative Mode: AUTO-DETECT / ADAPTIVE. Deeply examine the user's source input. If it describes a personal life experience, true memoir, career journey, or real-life storytime, preserve authentic emotional vulnerability, personal stakes, and relatability. If it describes fiction or a cinematic premise, dynamically apply high dramatic tension."
    elif any(k in genre_lower for k in ["personal", "memoir", "true life", "life", "storytime", "biograph", "founder", "documentary", "slice of life", "real"]):
        genre_spec = f"- Genre / Narrative Mode: {genre} (REAL-LIFE / PERSONAL MEMOIR). Focus on authentic human vulnerability, pivotal decisions, emotional struggles, hard-won lessons, and genuine stakes."
    else:
        genre_spec = f"- Genre: {genre}"

    system_instruction = f"""
You are the Executive Showrunner & Master Story Architect at WP Studio.
Your mission is to engineer 10 DISTINCT, HIGH-STAKES, IRRESISTIBLY INTERESTING YouTube story concepts based on the source.
Evaluate all 10 concepts and select the #1 Top Recommendation that will generate the highest watch time and viewer retention.

CREATIVE DIRECTION:
- Culture Anchor: {culture} (Infuse authentic speech cadence and cultural setting)
- Visual Style: {visual_style}
{genre_spec}
{char_clause}

CRITICAL RULES FOR HIGH-RETENTION, INTERESTING STORIES:
1. 0-3 SECOND CURIOSITY HOOK: The opening hook line must make the viewer immediately ask 'What happens next?!' It must present a burning question, high stakes, or a shocking life-altering dilemma.
2. ESCALATING TENSION & TIGHT PACING: The story premise must have real stakes: secrets, rivalries, unexpected betrayal, desperate gambles, or underdog survival. Never write generic, flat, or predictable filler.
3. SURPRISING CLIMAX TWIST: Every concept must build toward a genuine plot twist near the finale that rewards the viewer for watching.
4. SIMPLE, NATURAL LANGUAGE: Write dialogue and premise in clear, everyday conversational words. Avoid big words, stiff jargon, or robotic phrasing.

Return JSON matching this exact schema:
{{
    "recommended_concept_id": 1,
    "recommendation_reason": "Clear explanation of why this concept will perform best on YouTube, hook retention, and emotional viral trigger.",
    "concepts": [
        {{
            "id": 1,
            "title": "High CTR Click-Worthy Title",
            "hook": "Irresistible first 5 seconds spoken hook line",
            "premise": "2-sentence synopsis detailing the inciting incident, escalating tension, and unexpected twist",
            "viral_trigger": "Psychological curiosity trigger that hooks YouTube audiences"
        }}
    ]
}}
"""

    prompt = f"SOURCE TITLE: {source_title}\n\nSOURCE MATERIAL / TRANSCRIPT CONTEXT:\n{source_context[:6000]}\n\nGenerate exactly 10 distinct, tightly paced viral concepts and select the top recommended one."

    raw_response = generate_ai_completion(
        preferred_model=model,
        system_instruction=system_instruction,
        prompt=prompt,
        temperature=0.8,
        json_mode=True,
        user_keys=user_keys,
        user_api_key=user_api_key
    )
    data = clean_json_loads(raw_response)
    if isinstance(data, dict):
        return {
            "concepts": data.get("concepts", []),
            "recommended_concept_id": data.get("recommended_concept_id", 1),
            "recommendation_reason": data.get("recommendation_reason", "")
        }
    elif isinstance(data, list):
        return {
            "concepts": data,
            "recommended_concept_id": 1,
            "recommendation_reason": ""
        }
    return {"concepts": [], "recommended_concept_id": 1, "recommendation_reason": ""}

async def generate_full_story_package(concept: dict, culture: str = "Universal", visual_style: str = "Stylised 3D", genre: str = "Action Thriller", delivery_format: str = "Dialogue / Narrative", lead_character: dict = None, length_tier: str = "Short", timezone: str = "Africa/Lagos", user_api_key: str = None, model_name: str = None, channel_name: str = "", user_keys: dict = None) -> dict:
    """
    Step 2 of WP StoryCraft:
    Generates the complete Story Bible + Scene Prompts Blueprint up to the chosen length ceiling.
    - Short: 8-12 scenes
    - Medium: 18-26 scenes
    - Long: 50-60 scenes
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL

    scene_targets = {
        "Short": "10 to 14 complete dramatic scenes (fast, punchy 3 to 5 minutes YouTube story, ceiling 15)",
        "Medium": "22 to 30 complete dramatic scenes (fully developed 10 to 15 minutes YouTube story, ceiling 32)",
        "Long": "65 to 85 deep cinematic sequence scenes (MINIMUM 60 SCENES REQUIRED — do NOT stop at 35 or 40 scenes! Complete 1 to 2+ hour feature movie screenplay structured across Act 1, Act 2A, Midpoint Twist, Act 2B, and Act 3 Finale, each scene fully developed with substantial multi-character dialogues, dramatic tension, detailed blocking, and camera directives)"
    }
    target_scenes = scene_targets.get(length_tier, "10 to 14 complete dramatic scenes")

    char_clause = ""
    if lead_character and isinstance(lead_character, dict):
        c_name = lead_character.get("name", "Protagonist")
        c_gender = lead_character.get("gender", "Female")
        c_age = str(lead_character.get("age", "28"))
        c_complexion = lead_character.get("complexion", "Medium brown")
        c_hair = lead_character.get("hairstyle", "Braids")
        c_hair_col = lead_character.get("hair_color", "Black (#000000)")
        c_body = lead_character.get("body", "Average")
        c_height = lead_character.get("height", "Tall")
        c_nose = lead_character.get("nose_type", "Broad / Wide")
        c_expression = lead_character.get("expression", "Confident")
        c_outfit = lead_character.get("outfit", "Bespoke attire")

        char_clause = f"""
WP CASTLOCK VERIFIED CONTINUITY MANDATE:
The lead protagonist of this entire story package IS PERMANENTLY LOCKED to the following verified IP character:
- Character Name: {c_name}
- Role: PROTAGONIST (MUST be Character #1 in the "characters" list)
- Demographics: {c_age} years old, {c_gender}, {c_complexion} skin tone, {c_body} build, {c_height} height, {c_nose} nose
- Hairstyle & Grooming: {c_hair} ({c_hair_col})
- Signature Wardrobe & Shoes: {c_outfit}
- Signature Expression: {c_expression}

STRICT IP CONTINUITY RULES:
1. Character #1 in the "characters" bible MUST have name "{c_name}" and role "PROTAGONIST".
2. In all "scenes", wherever the protagonist appears, their likeness in parentheses MUST be based on these exact biometrics: "({c_name}: {c_complexion} complexion, {c_nose} nose, {c_hair} hairstyle, {c_body} build)".
3. Their wardrobe across scene prompts must be consistent with or an organic narrative progression of "{c_outfit}".
4. Under NO circumstances rename or replace the protagonist.
"""

    genre_lower = (genre or "").lower()
    if "auto-detect" in genre_lower or "adaptive" in genre_lower:
        genre_spec = "- Story Genre / Mode: AUTO-DETECT / ADAPTIVE. Maintain authenticity, emotional stakes, personal growth, and human relatability if rooted in real life, or rich cinematic depth if fictional."
    elif any(k in genre_lower for k in ["personal", "memoir", "true life", "life", "storytime", "biograph", "founder", "documentary", "slice of life", "real"]):
        genre_spec = f"- Story Genre / Mode: {genre} (REAL-LIFE / PERSONAL MEMOIR). Focus on authentic human vulnerability, pivotal personal decisions, relatable emotional struggles, hard-won lessons, and genuine stakes rather than forced Hollywood fantasy tropes."
    else:
        genre_spec = f"- Story Genre: {genre}"

    system_instruction = f"""
You are the Executive Showrunner & Lead Creative Director at WP Studio. Transform the selected concept into an exhaustive, Hollywood-grade YouTube Automation Story Package matching the highest industry standard (Infoxchange / StoryLab tier).

CREATIVE PRODUCTION SPECIFICATIONS:
- YouTube Channel Name: {channel_name or "WP Studio Production"}
- Visual Art Style: {visual_style}
{genre_spec}
- Cultural Anchor: {culture} (Reflect authentic cultural nuance, speech cadence, and settings)
- Story Delivery & Audio Format: {delivery_format}
- Length Ceiling: {length_tier} ({target_scenes})
- Target Timezone: {timezone}
{char_clause}
CORE ARCHITECTURE REQUIREMENTS:
1. VISUAL FILTER LOCK:
Define a master camera profile & lighting style tag locking the aesthetic (e.g. "Photorealistic cinematic live-action treatment with real human characters. Cinematic realism, high contrast, warm earth tones, fine film grain, deep shadows, shot on ARRI Alexa.").

2. WORLD BUILDING (LOCATION CONSISTENCY BIBLE — CRITICAL FOR RECURRING LOCATIONS):
Identify EVERY major location in the story (especially locations that appear in more than one scene!).
For each location, provide:
- "name": Exact Location Name used in the scenes.
- "scenes_used": Which scenes take place here (e.g. "Scenes 1, 4, 8, 15").
- "unoccupied_reference": A complete, copy-paste Midjourney / Flux / Google Flow Location Reference Prompt starting with "Empty, unoccupied reference view with no people or characters. Wide establishing shot, 24mm lens..." detailing exact room/exterior architecture, walls, flooring, lighting fixtures, color palette, practical props, material textures, and foreground/background depth so every scene in this location looks 100% consistent and realistic.

3. CAST & CONSISTENCY (CHARACTER BIBLE) — CRITICAL: COMPLETE FULL-BODY HEAD-TO-TOE STANDING REFERENCES:
For each character (Protagonist, Antagonist, Supporting):
- CRITICAL: Character references MUST BE COMPLETE UNRECROPPED HEAD-TO-TOE FULL BODY STANDING SHOTS. NEVER generate close-up headshots or tight portraits. Both feet and shoes touching the floor, body build, and full wardrobe MUST be 100% visible:
  "Full-length standing shot, complete head-to-toe uncropped full body view showing entire figure from shoes on the floor to top of head, eye-level angle, uncropped vertical composition. [Name] has an oval face shape, [complexion] skin tone, [eyes], [hair architecture], [build: athletic/tall/slender]. Standing in relaxed posture facing camera, wearing [complete signature wardrobe, detailed fabric weave/textures, and footwear clearly visible touching the ground]. Neutral grey seamless studio cyclorama background, soft studio lighting, subtle rim light separating subject from background, photorealistic live-action character reference, sharp focus head-to-toe, cinematic realism. No cut off legs, no cut off shoes, no tight crop, no watermarks, no text."
- Story-appropriate expression keywords.
- Signature wardrobe & footwear lock.
- IDENTITY LOCK statement.

4. SCENE-BY-SCENE IMAGE PROMPTS (Strict Self-Contained High-Detail Architecture):
Every image prompt in the production grid MUST be completely self-contained, richly narrative, and copy-ready for Google Flow, Midjourney v6, and Flux.1:
- [Camera Lens & Perspective]: e.g., "Objective wide establishing shot, eye-level angle, 35mm lens." or "Objective dramatic two-shot, eye-level, 50mm lens, shallow depth of field."
- [Location & Atmospheric Lighting]: Name specific location from Location Bible and describe lighting fixtures, ambient mood, practical props, textures, and depth.
- [Realistic Spatial Staging & Physical Blocking]: Explicitly position characters relative to the room, furniture, threshold, and other characters (e.g., "In the right midground, Marcus sits behind a heavy mahogany desk leaning forward. In the center foreground, Clara stands tall near the doorway, arms folded firmly across her chest, backlit by Manhattan evening skyline glass windows").
- [Character Biometric Likeness in Parentheses]: Always embed character's facial likeness in parentheses: "(Clara: sculpted cheekbones, light brown mixed complexion, intense focused hazel eyes)".
- [Scene-Specific Wardrobe & Footwear]: Explicitly describe what EACH character present is wearing down to fabrics, colors, cut, and shoes (e.g., "Clara wearing a tailored charcoal double-breasted power blazer, silk camisole, fitted trousers, and black pointed-toe stiletto pumps; Marcus wearing a bespoke navy chalk-stripe wool suit, crisp white dress shirt with gold cufflinks, and polished black Oxford shoes").
- [Scene-Specific Hairstyle & Grooming]: Explicitly describe each character's hair (e.g., "Clara's hair styled in a sleek, low braided bun with gold pins; Marcus's hair neatly groomed with a classic silver-temple side-part fade").
- [Concrete Dynamic Narrative Action]: Concretely describe the physical action taking place in the scene (e.g., "Marcus angrily slamming the legal severance document onto the polished mahogany desk, papers scattering across the wood, while Clara refuses to look down, holding unyielding eye contact").
- [Visual Filter Lock]: Append the visual filter lock.
- [Negative Constraints]: Append "No captions, subtitles, slogans, watermarks, written dialogue, cropped legs, or floating text."

5. SCENE-BY-SCENE VIDEO PROMPTS (Google Flow / Kling AI / Runway Architecture):
Every video prompt MUST be engineered for AI motion generators:
- [Opening Anchor]: Always start with: "Starting from the exact opening frame at [Location], the camera [pans / pushes in / tracks / holds steady] on [Character]..."
- [Chronological Physical Action]: Concrete actions described second-by-second.
- [Crucial End State Anchor]: Always include: "End state: [Exact concluding posture, frozen pose, or action resolution]."
- [Wardrobe & Hair Lock]: Repeated wardrobe, footwear, and hairstyle description.
- [Visual Filter Lock]: Append the visual filter lock.
- [Embedded Dialogue]: If spoken line exists, append: 'Spoken dialogue exactly: [Speaker]: "[Line]"'.
- [Audio & Negative Constraints]: Append: "No music, instrumentals, ambient audio, or sound effects. Use only the explicitly scripted spoken dialogue, if any. No captions, subtitles, text, slogans, watermarks, or written dialogue."

6. STORY DELIVERY & AUDIO SCRIPTING FORMAT ("{delivery_format.upper()}"):
CRITICAL FILMMAKING CONTINUITY MANDATE (NO SCATTERED SINGLE-LINE SCENES):
- A SCENE is defined by one continuous location and dramatic beat (Location from Location Bible).
- Under NO circumstances split an ongoing conversation across multiple scenes!
- If multiple characters are present in a location, their complete back-and-forth dialogue exchange, reactions, and conflicts MUST take place together within that SAME scene.
- FEATURE MOVIE / LONG SCOPE MANDATE (NO SHORT CUT-SCENES):
  For Long / 1-2 hour movie packages, every single scene must be substantial, deep, and fully developed. Absolutely NO rushed or cut-short 10-second scenes. Write genuine cinematic screenplay depth: authentic multi-turn character conversations, distinct character voices, emotional stakes, underlying motives, physical character actions, and meaningful plot progression. Treat this as a full, immersive feature film.
- If "{delivery_format}" == "Dialogue":
  The story is driven strictly by spoken conversations between characters like a screenplay. In every scene, script authentic, emotionally charged back-and-forth spoken lines in "dialogue" with speaker names across multiple turns (e.g. 'Marcus: "I told you never to come back here."\nElena: "You don\'t own this city, Marcus."\nMarcus: "Then why are you shaking, Elena?"'). Narration voiceover should be empty string (""). Never write only one solitary line of dialogue for an entire scene!
- If "{delivery_format}" == "Narrative":
  The story is told entirely through third-person or first-person narrator voiceover (optimized for ElevenLabs). In every scene, write gripping, high-retention spoken voiceover in "narration" (2 to 4 rich sentences that build tension and advance the story). Characters do NOT speak on-camera lines (set "dialogue" to an empty string "").
- If "{delivery_format}" == "Dialogue / Narrative":
  Cinematic hybrid format. Every scene contains compelling voiceover narration in "narration" setting tension/atmosphere, PLUS authentic on-camera spoken multi-line dialogue between characters in "dialogue".

7. VIRAL MARKETING MATRIX:
- 15-20 viral hashtags tailored to the story and genre.
- Platform-specific best posting times for {timezone} (TikTok, YouTube, Instagram).

Return strictly structured JSON:
{{
    "channel_name": "{channel_name or 'WP Studio Production'}",
    "title": "Final YouTube Video Title",
    "genre": "{genre}",
    "delivery_format": "{delivery_format}",
    "logline": "One-sentence high-stakes quotation logline",
    "hook": "0-5s spoken hook line",
    "theme_and_takeaway": "Core moral and psychological theme",
    "synopsis": "Full narrative story arc synopsis (150-250 words)",
    "youtube_description": "Comprehensive YouTube video description formatted with hook, 3-paragraph synopsis, chapter timestamps, call to action, and hashtags",
    "cultural_nuance": "How {culture} cultural flavor and authenticity are integrated",
    "hashtags": ["#Tag1", "#Tag2", "#Tag3"],
    "posting_schedule": {{
        "tiktok": "e.g. Tuesdays and Thursdays at 7:30 PM {timezone}",
        "youtube": "e.g. Wednesdays at 4:00 PM and Saturdays at 11:00 AM {timezone}",
        "instagram": "e.g. Mondays and Fridays at 6:00 PM {timezone}"
    }},
    "visual_filter_lock": "Photorealistic cinematic live-action treatment with real human characters. Cinematic realism, high contrast, warm earth tones, fine film grain, deep shadows, shot on ARRI Alexa.",
    "locations": [
        {{
            "name": "Location Name (e.g. Vance Manhattan Penthouse - Grand Foyer & Living Salon)",
            "scenes_used": "Scenes 1, 4, 9, 14",
            "unoccupied_reference": "Empty, unoccupied reference view with no people or characters. Wide establishing shot, 24mm lens. A modern luxury penthouse with floor-to-ceiling glass windows overlooking the Manhattan skyline, polished dark walnut floors, warm recessed amber ceiling lights, plush cream leather sofa, glass coffee table, realistic architectural textures, cinematic depth. No people, no text, no watermarks."
        }}
    ],
    "characters": [
        {{
            "name": "Character Name",
            "role": "PROTAGONIST / ANTAGONIST / SUPPORTING",
            "locked_visual_description": "Full-length standing shot, complete head-to-toe uncropped full body view showing entire figure from shoes on the floor to top of head, eye-level angle, uncropped vertical composition. [Name] has an oval face shape, [complexion] skin tone, [eyes], [hair architecture], [build]. Standing in relaxed posture facing camera, wearing [complete signature wardrobe, detailed fabric weave/textures, and footwear clearly visible touching the ground]. Neutral grey seamless studio cyclorama background, soft studio lighting, subtle rim light separating subject from background, photorealistic live-action character reference, sharp focus head-to-toe, cinematic realism. No cut off legs, no cut off shoes, no tight crop, no watermarks, no text.",
            "expression_keywords": "Resilient, authoritative, dignified",
            "wardrobe_lock": "complete signature wardrobe and shoes",
            "identity_lock_statement": "IDENTITY LOCK: [Name]'s facial features, hairstyle, skin tone, build, and overall appearance must remain consistent."
        }}
    ],
    "scenes": [
        {{
            "scene_number": 1,
            "scene_title": "Descriptive Scene Title",
            "scene_type": "Establishing / Action / Dialogue / Reaction / Climax / Resolution",
            "duration": "90s",
            "camera_perspective": "objective",
            "characters_present": ["Character Name 1", "Character Name 2"],
            "location": "Location Name from Location Bible",
            "dialogue": "Character 1: \\"First spoken line...\\"\\nCharacter 2: \\"Reply line...\\"\\nCharacter 1: \\"Follow up line...\\"",
            "narration": "Rich spoken voiceover paragraph for ElevenLabs",
            "image_prompt": "Objective wide establishing shot, eye-level angle, 35mm lens. [Location with lighting, props and depth]. [Realistic spatial staging with exact character placement in room]. [Character likeness in parentheses]. [Specific wardrobe and shoes for each character]. [Specific hairstyle for each character]. [Concrete narrative action taking place]. [Visual filter lock]. No captions, subtitles, slogans, watermarks, written dialogue, cropped legs, or floating text.",
            "video_prompt": "Starting from the exact opening frame at [Location], the camera [motion] on [Character]. [Action sequence]. End state: [Ending pose]. [Wardrobe and hair]. Visual filter lock: [Filter]. No music, instrumentals, ambient audio, or sound effects. Use only the explicitly scripted spoken dialogue, if any. No captions, subtitles, text, slogans, watermarks, or written dialogue."
        }}
    ],
    "thumbnail_concepts": [
        {{
            "concept": "Emotional climax / shock element",
            "text_overlay": "3-4 punchy words on thumbnail",
            "midjourney_prompt": "Midjourney prompt for the thumbnail graphic"
        }}
    ]
}}
"""

    prompt = f"""SELECTED CONCEPT:
Title: {concept.get('title')}
Hook: {concept.get('hook')}
Premise: {concept.get('premise')}
Viral Trigger: {concept.get('viral_trigger')}

Generate the complete production package with {target_scenes}."""

    raw_response = generate_ai_completion(
        preferred_model=model,
        system_instruction=system_instruction,
        prompt=prompt,
        temperature=0.7,
        json_mode=True,
        user_keys=user_keys,
        user_api_key=user_api_key
    )
    data = clean_json_loads(raw_response)
    if isinstance(data, dict):
        data["delivery_format"] = data.get("delivery_format", delivery_format)
        data["channel_name"] = channel_name or data.get("channel_name", "WP Studio Production")
        if not data.get("youtube_description"):
            data["youtube_description"] = f"{data.get('logline', '')}\n\n{data.get('synopsis', '')}\n\nSubscribe to {data['channel_name']} for more cinematic stories!\n\n" + " ".join(data.get("hashtags", []))
    return data

async def generate_character_turnaround(character_desc, style="Stylised 3D", reference_image_bytes=None, reference_instruction=None, vision_biometrics=None, user_api_key=None, model_name=None):
    """
    Generates an extreme high-intelligence 9-panel 3D character turnaround & model sheet prompt suite
    (matching professional Hollywood & AAA game studio character design specifications):
    - Master 9-Panel 3x3 Model Sheet Grid Prompt (Front, 3/4, Profile, Back, Front Close-Up, 3/4 Close-Up, Profile Close-Up, Hairstyle Detail, Wardrobe Detail)
    - 9 Individual 4K Angle Prompts
    - 3D Engine Specification (Subsurface scattering SSS, Unreal Engine 5, Octane Render)
    - Multimodal Reference Image Analysis Integration (if provided)
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL
    client = get_client(user_api_key)

    system_instruction = f"""
You are the Principal 3D Character Designer & LookDev Lead at WP Studio (specializing in AAA 3D character pipelines, Unreal Engine 5 Metahumans, Pixar/Disney 3D animation, and Hollywood production model sheets).

Your mission is to engineer an EXTREME HIGH-INTELLIGENCE 3D CHARACTER MODEL SHEET & TURNAROUND PROMPT SUITE based on the character description and any attached reference image.

CORE 9-PANEL TURNAROUND ARCHITECTURE (Based on standard studio model sheets):
The model sheet must capture the character from every angle across a seamless 3x3 reference grid against a uniform neutral light-grey studio background:
- Panel 1: [FRONT] Full body standing upright, neutral A-pose/relaxed pose, eye-level angle, 50mm lens.
- Panel 2: [THREE-QUARTER] Full body standing at 45-degree angle showing depth, silhouette, and posture.
- Panel 3: [PROFILE] Full body standing at true 90-degree side profile showing posture, skull depth, and heel-to-toe line.
- Panel 4: [BACK] Full body standing back view showing rear silhouette, spinal posture, and garment drapery.
- Panel 5: [FRONT CLOSE-UP] Close-up headshot portrait, direct eye contact, neutral focused expression, microscopic facial skin pore texture.
- Panel 6: [THREE-QUARTER CLOSE-UP] Close-up headshot at 45-degree angle showing cheekbone definition and jawline curvature.
- Panel 7: [PROFILE CLOSE-UP] True 90-degree side profile headshot showing nose bridge, ear anatomy, and jawline definition.
- Panel 8: [HAIRSTYLE DETAIL] Extreme close-up of the back of head showing intricate hair braiding/parting/grooming structure.
- Panel 9: [WARDROBE DETAIL] Close-up of torso/garment construction showing collar, buttons, seams, fabric weave, and tailored details.

HIGH-INTELLIGENCE 3D ENGINE TOKENS TO MANDATE:
- 3D Style: Stylized 3D CGI / Unreal Engine 5 Metahuman / Pixar-grade stylized 3D.
- Shading & Subsurface Scattering (SSS): Soft translucent skin shader with subsurface light scattering along ear rims and nose.
- Lighting: Professional multi-point studio lighting, soft key light, gentle ambient occlusion, subtle crisp rim light separating subject from background.
- Garment Engineering: Explicit fabric textures (woven cotton, knife-pleated wool, silk ribbons, polished leather shoes).
- Grid Layout Anchor: "3x3 character model sheet, 9-panel reference grid layout, multiple angles of the same character... --ar 9:16".
- Continuity & Negative Anchors: "identical facial proportions across all panels, zero morphological drift, uniform neutral studio grey background, clean symmetrical line-up, no text, no watermarks, no distortion."
- Reference Fidelity: If biometric anchors or a reference photo are provided, strictly match the craniofacial landmarks, skin undertones, and hair architecture.

Return strictly structured JSON:
{{
    "character_name": "Character Name",
    "visual_style": "{style} / Unreal Engine 5 3D Render",
    "consistency_bible": "Exhaustive trait breakdown: head-to-body ratio, skin tone hex, eye details, facial landmarks, exact hairstyle architecture, and complete garment/footwear construction.",
    "master_9panel_sheet_prompt": "Master 9-panel 3x3 character model sheet prompt ready for Midjourney v6 / Flux.1 / Google Flow: 'Character model sheet, turnaround reference sheet, 3x3 grid layout, 9 distinct panels of the same character: [1] FRONT full body, [2] THREE-QUARTER full body, [3] PROFILE 90-degree full body, [4] BACK full body, [5] FRONT CLOSE-UP headshot, [6] THREE-QUARTER CLOSE-UP headshot, [7] PROFILE CLOSE-UP headshot, [8] HAIRSTYLE DETAIL back view, [9] WARDROBE DETAIL torso close-up. [Deep anatomical & wardrobe details]. Uniform neutral light grey studio background, soft cinematic studio lighting, subsurface scattering SSS, 3D CGI stylized animation, Unreal Engine 5 render, 8k resolution, identical character continuity across all panels --ar 9:16'",
    "angle_prompts": {{
        "front_full_body": "Detailed individual prompt for Panel 1",
        "three_quarter_full_body": "Detailed individual prompt for Panel 2",
        "profile_full_body": "Detailed individual prompt for Panel 3",
        "back_full_body": "Detailed individual prompt for Panel 4",
        "front_close_up": "Detailed individual prompt for Panel 5",
        "three_quarter_close_up": "Detailed individual prompt for Panel 6",
        "profile_close_up": "Detailed individual prompt for Panel 7",
        "hairstyle_detail": "Detailed individual prompt for Panel 8",
        "wardrobe_detail": "Detailed individual prompt for Panel 9"
    }},
    "action_prompt": "Cinematic dynamic 3D action shot prompt showing the character in motion within a rich 3D environment",
    "recommended_midjourney_params": "--ar 9:16 --v 6.1 --stylize 250"
}}
"""

    prompt_text = f"Design an extreme high-intelligence 9-panel 3D character turnaround model sheet for:\n{character_desc}"
    if reference_instruction:
        prompt_text += f"\n\nUSER REFERENCE INSTRUCTION: {reference_instruction}"
    if vision_biometrics:
        prompt_text += f"\n\nLOCKED REFERENCE BIOMETRIC ANCHORS: {vision_biometrics}"

    contents = []
    if reference_image_bytes:
        try:
            image_part = types.Part.from_bytes(data=reference_image_bytes, mime_type="image/jpeg")
            contents.append(image_part)
        except Exception as img_err:
            logger.warning(f"Failed to attach image part: {img_err}")
    contents.append(prompt_text)

    response = generate_with_fallback(
        client=client,
        preferred_model=model,
        contents=contents if len(contents) > 1 else prompt_text,
        config={
            "system_instruction": system_instruction,
            "response_mime_type": "application/json"
        },
        user_api_key=user_api_key
    )
    return clean_json_loads(response.text)

async def analyze_reference_image(image_bytes: bytes, instruction: str = "", user_api_key: str = None, model_name: str = None) -> dict:
    """
    Multimodal Vision Analysis:
    Inspects user's uploaded reference image with extreme high intelligence to extract:
    - Craniofacial landmarks (jawline, cheekbones, nose bridge, eye shape, lip fullness)
    - Melanin skin tone shader & undertones
    - Hairstyle texture, parting, and color
    - Wardrobe construction & textile patterns
    - Applies custom user instruction
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL
    client = get_client(user_api_key)

    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    system_instruction = """
You are the Lead Visual Forensic & Biometrics Character Artist at WP Studio.
Your mission is to perform an EXTREME HIGH-INTELLIGENCE FORENSIC VISUAL ANALYSIS of the provided reference image.
Extract exact physiological, cranial, and stylistic markers to ensure zero morphological drift in 3D turnaround model sheets.

ANALYTICAL DIMENSIONS TO EXTRACT:
1. Craniofacial Anatomy:
   - Facial structure: Oval / Diamond / Square / Heart / Oblong.
   - Cranial bone landmarks: High cheekbone prominence, jawline definition (sharp chisel vs soft taper), chin cleft.
   - Orbital and Nasal: Eye tilt (almond, hooded, deep-set), iris color depth, nose bridge width (broad wide, slender aquiline, button), nostril flare.
   - Lips: Upper vs lower lip ratio, cupid's bow definition.
2. Melanin & Epidermal Light Scattering:
   - Skin tone classification: Fair, Light brown, Medium brown, Rich bronze, Dark brown, Deep dark espresso.
   - Undertones: Warm golden / Cool neutral / Red mahogany / Olive.
   - Epidermal shader: Micro-texture, pore visibility, natural subsurface scattering (SSS) radiance.
3. Hair Architecture & Scalp Topology:
   - Style: Braids (box/knotless), locs, afro, twists, sharp fade line-up, straight, wavy.
   - Pigment & Sheen: Root-to-tip pigment, highlights, accessories (cuffs, beads, rings).
4. Wardrobe & Material Craftsmanship:
   - Silhouette, garment cuts, neckline, textile weave (Ankara print, lace, velvet, tactical nylon, wool).
5. User Instruction Synthesis:
   - CRITICAL: Apply the user's specific instruction to the extracted analysis (e.g., if user says "change hair to braids" or "make into Pixar 3D style", synthesize that directly).

Return strictly structured JSON:
{
    "biometric_summary": "2-sentence high-density biometric description ready for AI generation",
    "facial_landmarks": "Detailed breakdown of cheekbones, jawline, eye shape, nose bridge, and lip contour",
    "skin_tone_shader": "Exact melanin classification, undertone, and SSS diffusion notes",
    "hair_specification": "Hair architecture and pigment notes",
    "wardrobe_specification": "Garment silhouette, fabric, and color notes",
    "extracted_character_data": {
        "gender": "Female or Male",
        "complexion": "Fair / Light brown / Medium brown / Brown / Dark brown / Deep dark",
        "nose_type": "Broad / Wide / Slender / Narrow / Button / Small / Aquiline / Flat / Rounded",
        "hairstyle": "Braids / Locs / Afro / Twists / Buzz Cut / Straight / Curly / Custom",
        "custom_hairstyle": "Detailed custom hair description",
        "hair_color": "Hair color hex/name",
        "expression": "Extracted mood",
        "outfit_style": "Ankara / Corporate / Traditional / Streetwear / School Uniform / Tactical / Casual / Custom",
        "custom_outfit": "Detailed outfit notes"
    }
}
"""

    user_prompt = f"Perform forensic biometric and stylistic analysis on this reference image.\nUSER INSTRUCTION: {instruction if instruction else 'Extract full authentic likeness and character continuity markers.'}"

    response = generate_with_fallback(
        client=client,
        preferred_model=model,
        contents=[image_part, user_prompt],
        config={
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "temperature": 0.4
        },
        user_api_key=user_api_key
    )
    return clean_json_loads(response.text)

async def generate_thumbnail_prompts(
    story_summary: str,
    channel_name: str = "",
    thumbnail_style: str = "Hyper-Realistic Cinematic 3D",
    lead_character: dict = None,
    facial_emotion: str = "Shock & Disbelief (Jaw Dropped / Wide Eyes)",
    composition_layout: str = "Extreme Face Close-Up on Left with Threat/Object on Right",
    color_mood: str = "High-Contrast YouTube Punch (Vibrant Yellow & Cyan)",
    custom_notes: str = "",
    writeup_text: str = "",
    include_youtube_logo: bool = True,
    user_api_key: str = None,
    model_name: str = None
):
    """
    Master YouTube Packaging & CTR Engine:
    Intelligently polishes user's rough input, anchors character continuity,
    and engineers 3 elite YouTube thumbnail prompt packages copy-ready for Midjourney/Flux/Google Flow.
    Guarantees embedded bold writeup typography and official 3D YouTube logo badging directly in the prompts.
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL
    client = get_client(user_api_key)

    char_clause = ""
    if lead_character and isinstance(lead_character, dict):
        c_name = lead_character.get("name", "Protagonist")
        c_gender = lead_character.get("gender", "Character")
        c_age = str(lead_character.get("age", "28"))
        c_complexion = lead_character.get("complexion", "Medium brown")
        c_hair = lead_character.get("hairstyle", "Braids")
        c_body = lead_character.get("body_size") or lead_character.get("body", "Average")
        c_outfit = lead_character.get("outfit_style") or lead_character.get("outfit", "Signature wardrobe")
        char_clause = f"""
CHARACTER CONTINUITY MANDATE:
The thumbnail MUST feature the following recurring character as the central visual focal subject:
- Name: {c_name} ({c_age}y/o {c_gender}, {c_complexion} skin, {c_hair} hairstyle, {c_body} build, wearing {c_outfit}).
- Embed their exact biometric likeness and expression into the master image generation prompt.
"""

    notes_clause = f"\nCUSTOM ELEMENTS TO EMPHASIZE: {custom_notes}\n" if custom_notes else ""
    writeup_clause = f"\nUSER PREFERRED WRITEUP TEXT: Incorporate \"{writeup_text}\" (or its sharpest viral variation) as the text writeup.\n" if writeup_text else ""
    logo_instruction = "- YouTube Logo Badge: MANDATORY. Include a glossy 3D red YouTube play button logo badge emblem floating in the upper or lower corner." if include_youtube_logo else "- YouTube Logo Badge: None."

    system_instruction = f"""
You are the World's #1 YouTube Packaging & Click-Through-Rate (CTR) Specialist at WP Studio (producing thumbnails on par with MrBeast, Vox, MagnatesMedia, and Film Cooper).
Your mission is to take ANY input from the user (even a rough, messy, or short thought), automatically POLISH and elevate it into a viral, emotionally charged visual concept, and engineer 3 ELITE YouTube Thumbnail Prompt Packages.

CREATIVE THUMBNAIL SPECIFICATIONS:
- Aesthetic Art Style: {thumbnail_style}
- YouTube Channel Name: {channel_name or "WP Studio Creator"}
- Key Emotional Reaction: {facial_emotion}
- Spatial Framing / Composition: {composition_layout}
- Color Palette & Lighting Mood: {color_mood}
{logo_instruction}
{char_clause}
{notes_clause}
{writeup_clause}

CRITICAL RULES FOR CLICK-GENERATING YOUTUBE THUMBNAILS:
1. THE 3-SECOND RULE: Viewers decide to click in 0.5s on mobile. Thumbnails must have ONE clear focal point, extreme contrast, high visual hierarchy, and instant emotional punch.
2. BOLD TEXT OVERLAY WRITEUP: Top viral YouTube thumbnails ALWAYS have large, punchy 2-4 word writeups (e.g. "I QUIT!", "$10,000,000 MISTAKE", "DO NOT CLICK", "THEY LIED", "IT'S OVER", "HACKED!"). Never repeat the video title.
3. 3D YOUTUBE LOGO BADGE: Viral thumbnails feature an iconic, glossy 3D red YouTube play button logo emblem with specular reflections to trigger instant platform recognition.
4. MANDATORY MASTER IMAGE PROMPT REQUIREMENTS:
   The master_image_prompt MUST be 100% self-contained and copy-paste ready for Midjourney v6.1, Flux.1, and Google Flow.
   CRITICAL: The prompt MUST explicitly instruct the AI image generator to physically paint and render:
   a) The EXACT bold writeup text in double quotation marks with typography style (e.g. 'incorporating prominent bold 3D typography that reads "HACKED!" in oversized vibrant yellow block letters with thick black outline and red drop shadow in the upper left corner')
   {"b) The glossy 3D red YouTube play button logo badge emblem floating in the opposite corner with neon rim reflections" if include_youtube_logo else ""}
   c) Camera lens (e.g. "Extreme close-up 35mm lens, dynamic low angle")
   d) Exact lighting (e.g. "cinematic volumetric rim lighting, intense warm amber key light contrasting with deep teal shadows")
   e) Biometrics and locked character traits (if character provided)
   f) Background depth, glowing particles, sparks, or subtle depth of field
   g) Strict parameters: "--ar 16:9 --style raw --v 6.1"

Generate 3 DISTINCT high-CTR concepts:
1. Concept #1: "The Extreme Reaction Hook" (Highest CTR, huge expressive face, shock, foreground focal point)
2. Concept #2: "The High-Stakes Action / Dilemma" (Tense cinematic climax, high danger or conflict, movie-poster scale)
3. Concept #3: "The Curiosity Gap / Dark Secret" (Bizarre hidden detail, forbidden door, glowing anomaly, mystery)

Return strictly structured JSON:
{{
    "polished_topic": "Cleaned up, emotionally charged premise engineered from user input",
    "channel_name": "{channel_name or 'WP Studio Creator'}",
    "concepts": [
        {{
            "variation_name": "Variation 1: The Extreme Reaction Hook",
            "is_top_pick": true,
            "headline_title": "Irresistible Viral YouTube Title Suggestion",
            "overlay_text": "2-4 PUNCHY WORDS (e.g. HACKED!)",
            "overlay_style": "Style & typography recommendation (e.g. Slanted bold Bebas Neue yellow font with heavy black stroke and red drop shadow)",
            "overlay_placement": "Placement coordinates (e.g. Upper Left corner, angled at 7 degrees)",
            "youtube_logo_placement": "Upper Right corner floating 3D badge",
            "master_image_prompt": "Complete Midjourney/Flux prompt with explicit instructions painting the writeup text in quotes, the 3D red YouTube logo badge, subject, camera, lighting, and --ar 16:9 --style raw --v 6.1",
            "visual_composition": {{
                "foreground": "What is closest to camera",
                "midground_subject": "Main character pose, expression, and action",
                "background": "Setting, lighting fixtures, environmental atmosphere",
                "color_palette": "Dominant colors and contrast pairing (e.g. Vibrant Golden Yellow against Midnight Navy)"
            }},
            "psychological_trigger": "Why viewers are psychologically compelled to click (e.g. Curiosity gap + extreme shock reaction trigger)"
        }}
    ]
}}
"""

    prompt = f"""USER INPUT STORY PREMISE / ROUGH IDEA:
"{story_summary}"

Polish this idea into 3 master-level YouTube thumbnail concepts with exhaustive Midjourney prompts according to the creative specifications above."""

    response = generate_with_fallback(
        client=client,
        preferred_model=model,
        contents=prompt,
        config={
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "temperature": 0.7
        },
        user_api_key=user_api_key
    )
    return clean_json_loads(response.text)

class RenderCooldownError(Exception):
    def __init__(self, remaining_seconds: int):
        self.remaining_seconds = remaining_seconds
        super().__init__(f"Visual engine cooldown: {remaining_seconds}s remaining.")

async def render_visual_frame(prompt: str, width: int = 1024, height: int = 576, seed: int = None, user_api_key: str = None) -> bytes:
    """
    Renders an in-chat visual preview frame using Flux.1 / fast cloud generation.
    Returns raw image bytes (JPEG). Automatically waits & retries if cooldown is short.
    """
    clean_p = prompt
    for neg_phrase in [
        "No captions, subtitles, slogans, watermarks, written dialogue, cropped legs, or floating text.",
        "No music, instrumentals, ambient audio, or sound effects.",
        "No captions, subtitles, text, slogans, watermarks, or written dialogue."
    ]:
        clean_p = clean_p.replace(neg_phrase, "")
    clean_p = clean_p.strip()

    encoded = urllib.parse.quote(clean_p[:800])
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model=turbo&nologo=true"
    if seed:
        url += f"&seed={seed}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    pollen_key = user_api_key or os.getenv("POLLEN_API_KEY", "")
    if pollen_key and pollen_key.strip():
        headers["Authorization"] = f"Bearer {pollen_key.strip()}"

    async with httpx.AsyncClient(timeout=45.0) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
            return resp.content
        elif resp.status_code == 402:
            try:
                err_data = resp.json()
                msg = err_data.get("error", {}).get("message", "")
            except Exception:
                msg = resp.text

            # Check for cooldown seconds in message, e.g. "Retry after 1s"
            match = re.search(r'Retry after (\d+)s', msg)
            if match:
                secs = int(match.group(1))
                # Auto-wait & retry if cooldown is 15s or less!
                if secs <= 15:
                    logger.info(f"Visual engine cooldown active ({secs}s). Auto-waiting {secs + 1.5}s before retry...")
                    await asyncio.sleep(secs + 1.5)
                    retry_resp = await client.get(url, headers=headers)
                    if retry_resp.status_code == 200 and retry_resp.headers.get("content-type", "").startswith("image/"):
                        return retry_resp.content

                raise RenderCooldownError(secs)
            else:
                raise RenderCooldownError(20)
        else:
            raise RuntimeError(f"Visual rendering service returned HTTP {resp.status_code}")

async def adapt_story_to_scenes(
    story_text: str,
    genre: str = "Drama",
    cinematic_filter: str = "Default",
    art_style: str = "Realistic",
    voice_accent: str = "African / Nigerian",
    target_duration: str = "Standard (8–15 Mins)",
    delivery_format: str = "Dialogue / Narrative",
    remodel_names: bool = True,
    user_api_key: str = None,
    model_name: str = None,
    user_keys: dict = None
) -> dict:
    """
    Story Adapter (Script to Scenes):
    Adapts a written story or script into shot-by-shot cinematic scene prompts,
    complete with Character Sheet Prompts, Recurring Location Consistency Prompts,
    and clean Voiceover/Dialogue scripting.
    By default (remodel_names=True), remodels all character names, location names,
    and phrasing for 100% YouTube copyright safety while keeping the core story arc intact.
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL

    # Filter definitions
    filter_map = {
        "Default": "35mm anamorphic film lens, realistic studio lighting, cinematic dynamic range, true-to-life colors.",
        "Horror": "Prestige dread grade, deep gloomy shadows, desaturated cool tones, eerie chiaroscuro lighting, volumetric atmospheric mist.",
        "Romance": "Warm honey-rose golden hour glow, soft mist diffusion filter, creamy bokeh, intimate warm amber rim lighting.",
        "Action": "High-contrast dynamic punch, saturated primaries, vivid motion blur, dramatic specular highlights, high shutter angle.",
        "Drama": "Naturalistic prestige cinematic lighting, subtle earthy tones, gentle directional window light, deep emotional contrast.",
        "Thriller": "Cold steel tension grade, cyan-tinted low-key lighting, harsh sharp shadows, claustrophobic framing, high tension.",
        "Sci-Fi": "Cyber-teal and vivid neon specular backlight, atmospheric damp fog reflections, anamorphic blue horizontal lens flares."
    }
    filter_treatment = filter_map.get(cinematic_filter, filter_map["Default"])

    # Art style definitions
    if "3D" in art_style or "Animated" in art_style:
        art_treatment = "Pixar / Disney 3D high-end animation style, expressive stylized 3D character design, soft subsurface scattering (SSS), vibrant animated feature color palette, Octane 3D render."
    else:
        art_treatment = "8K hyper-detailed cinematic movie still, shot on ARRI Alexa 35mm, real human skin pores, photorealistic textures, photorealistic studio lighting."

    # Voice flavor
    if "African" in voice_accent or "Nigerian" in voice_accent:
        voice_treatment = "Authentic Nigerian English / Nollywood dramatic cadence, culturally rich emotional phrasing in dialogue and narration."
    elif "Black American" in voice_accent:
        voice_treatment = "Authentic Black American cultural cadence, soulful urban and African American expressive vernacular and rhythm in dialogue and narration."
    elif "British" in voice_accent:
        voice_treatment = "Refined British English cadence, measured storytelling delivery and polished dramatic tone."
    else:
        voice_treatment = "Modern cinematic American pacing, conversational natural flow in voiceover and dialogue."

    # Delivery format treatment
    if "Dialogue" in delivery_format and "Narrative" not in delivery_format:
        delivery_treatment = "DIALOGUE FOCUSED: Prioritize spoken character dialogue interactions for each scene. Populate 'dialogue' with the full multi-turn conversation and leave 'narration' empty."
    elif "Narrative" in delivery_format and "Dialogue" not in delivery_format:
        delivery_treatment = "NARRATIVE / VOICE-OVER FOCUSED: Write a rich, continuous narrator voiceover script across 'narration' in every scene (ideal for ElevenLabs / faceless YouTube narrators). Leave 'dialogue' empty."
    else:
        delivery_treatment = "BALANCED DIALOGUE & NARRATION: Deliver both gripping narrator voiceover in 'narration' AND spoken character lines in 'dialogue' for each scene."

    if remodel_names:
        copyright_law = f"""1. 100% YOUTUBE COPYRIGHT-SAFE REMODELING (CHANGE ALL NAMES & LOCATIONS):
   - You MUST change EVERY character's name (first and last name) and EVERY location/city/venue/company name in the story to fresh, realistic names that fit the {voice_accent} cultural setting.
   - NEVER keep the original character names or original location names from the pasted text!
   - Rephrase all sentences, narration, and dialogue in simple, natural, everyday words so YouTube will NEVER flag the video for copyright or reused content.
   - Keep the core plot, emotional twists, character relationships, dramatic conflict, and ending 100% intact!"""
    else:
        copyright_law = """1. FAITHFUL CHARACTER & PLOT CONTINUITY:
   - Keep the user's character names, relationships, locations, and storyline intact while adapting it into full cinematic scenes."""

    if "Feature" in target_duration or "1–2" in target_duration or "1-2" in target_duration or "Hour" in target_duration:
        scene_load_rule = "MINIMUM 60 TO 80 SCENES REQUIRED (Feature Movie 1–2+ Hours): Do NOT stop at 30 or 40 scenes! Expand and pace the story into 65 to 80 deep, richly developed cinematic scenes with full multi-line dialogue or rich multi-sentence voiceover narration in every single scene."
    elif "Long" in target_duration or "30–60" in target_duration or "30-60" in target_duration:
        scene_load_rule = "35 to 48 extended scenes (Deep Dive 30–60 Mins) with full dialogue and rich narration."
    elif "Standard" in target_duration or "8–15" in target_duration or "8-15" in target_duration:
        scene_load_rule = "20 to 30 complete scenes (YouTube Standard 8–15 Mins) with full dialogue and rich narration."
    else:
        scene_load_rule = "10 to 15 complete scenes (Short 3–5 Mins) with punchy pacing."

    system_instruction = f"""
You are the Master Storyboard Director & Visual Prompt Engineer at WP Studio.
Your mission is to adapt and remodel the creator's pasted story into a complete, copyright-safe, shot-by-shot cinematic production package.

CRITICAL NON-NEGOTIABLE LAWS:
{copyright_law}
2. NATURAL SCENE LOAD & PACING FOR {target_duration}:
   {scene_load_rule}
3. RECURRING LOCATION CONSISTENCY PROMPTS ("locations" array):
   - Every location that appears in the story (especially locations that appear more than once!) MUST be listed in the "locations" Bible with an "unoccupied_reference" prompt:
     "Empty, unoccupied reference view with no people or characters. Wide establishing shot, 24mm lens, [exact architectural layout, walls, lighting, colors, furniture/props, textures, and mood]. {art_treatment}. No people, no text, no watermarks."
   - Also list which scenes use that location in "scenes_used" (e.g. "Scenes 1, 3, 7, 12").
4. FULL-BODY CHARACTER SHEET PROMPTS ("characters" array):
   - Every character MUST have a complete head-to-toe full-body standing character sheet prompt in "locked_visual_description":
     "Full-length standing shot, complete head-to-toe uncropped full body view showing entire figure from shoes on the floor to top of head, eye-level angle. [New Name] has [face shape], [skin tone], [eyes], [hairstyle], [body build]. Standing in relaxed posture facing camera, wearing [exact signature outfit and shoes touching the floor]. Neutral grey seamless studio background, soft studio lighting, {art_treatment}. No cut off legs, no cut off shoes, no text."
5. SCENE CONTINUITY (NO SPLIT-UP CONVERSATIONS):
   - A SCENE is defined by one continuous location and dramatic beat. If two or more characters are talking in that location, their entire conversation belongs together within that SAME scene.
6. CLEAN SEPARATE VOICEOVER & DIALOGUE SCRIPTING:
   - Write in simple, natural, everyday words.
   - Populate "narration" with the clean narrator voiceover paragraph for that scene.
   - Populate "dialogue" with the clean spoken character conversation for that scene.
   - Populate "dialogue_or_narration" with the complete spoken script of that scene ready to read or generate voiceover.
7. SELF-CONTAINED SCENE IMAGE PROMPTS & VIDEO MOTION PROMPTS:
   - Each "image_prompt" must specify shot size, camera lens, the exact location details, every character present with their facial/hair/outfit details in parentheses, concrete physical action, and {art_treatment} + {filter_treatment}. No text or watermarks.
   - Each "video_prompt" must specify camera movement and physical action from opening frame to end state.

CONFIGURATION:
- Tone / Genre: {genre}
- Cinematic Filter: {cinematic_filter} ({filter_treatment})
- Art Style: {art_style} ({art_treatment})
- Voice / Accent Flavor: {voice_accent} ({voice_treatment})
- Target Runtime / Scope: {target_duration}
- Delivery Format: {delivery_format} ({delivery_treatment})

OUTPUT SCHEMA: Return ONLY valid JSON with this exact structure:
{{
    "title": "Fresh, High-CTR Copyright-Safe Title of the Story",
    "logline": "Compelling 1-sentence logline summarizing the remodeled story",
    "synopsis": "2-paragraph summary of the complete story arc",
    "total_scenes": 30,
    "genre": "{genre}",
    "cinematic_filter": "{cinematic_filter}",
    "art_style": "{art_style}",
    "voice_accent": "{voice_accent}",
    "delivery_format": "{delivery_format}",
    "name_changes": [
        {{
            "original": "Original Name or Location",
            "new": "New Copyright-Safe Name or Location",
            "type": "Character / Location"
        }}
    ],
    "locations": [
        {{
            "name": "Remodeled Location Name (e.g. Sterling Grand Ballroom)",
            "scenes_used": "Scenes 1, 2, 5, 11",
            "unoccupied_reference": "Empty, unoccupied reference view with no people or characters. Wide establishing shot, 24mm lens, grand high-ceiling ballroom with crystal chandeliers, warm golden lighting, polished marble floor, velvet drapes... {art_treatment}. No people, no text, no watermarks."
        }}
    ],
    "characters": [
        {{
            "name": "Remodeled Character Name",
            "original_name": "Original Character Name",
            "role": "Protagonist / Antagonist / Supporting",
            "visual_description": "Concise summary of face, skin tone, hair, build, and signature outfit",
            "locked_visual_description": "Full-length standing shot, complete head-to-toe uncropped full body view showing entire figure from shoes on the floor to top of head, eye-level angle. [Character Name] has [face, skin tone, eyes, hair, build], wearing [complete signature outfit and footwear]. Neutral grey studio background, soft studio lighting, {art_treatment}. No cut off legs, no cut off shoes, no text.",
            "wardrobe_lock": "Exact signature outfit and footwear"
        }}
    ],
    "scenes": [
        {{
            "scene_number": 1,
            "scene_title": "Descriptive Scene Heading",
            "setting": "Location Name from Location Bible - Time of Day",
            "location": "Location Name from Location Bible",
            "estimated_duration": "1m 30s",
            "characters_present": ["Character Name 1", "Character Name 2"],
            "narration": "Clean narrator voiceover paragraph for this scene (for ElevenLabs / narrator voiceover)",
            "dialogue": "Character 1: \\"Spoken line...\\"\\nCharacter 2: \\"Reply line...\\"",
            "dialogue_or_narration": "Complete narrator voiceover and/or character dialogue for this scene",
            "image_prompt": "Ultra-detailed Midjourney/Flux prompt with camera angle, lighting, recurring location details, character biometric likeness in parentheses, wardrobe, action, style. No captions, no text.",
            "video_prompt": "Starting from the exact opening frame at [Location], camera movement and character physical action prompt for Kling/Runway/Veo. End state: [concluding pose]."
        }}
    ]
}}
"""

    prompt = f"""CREATOR'S SOURCE STORY:
{story_text}

Adapt and remodel this story into chronological scene-by-scene prompts, full-body character sheet prompts, and recurring location consistency prompts following all rules above."""

    raw_response = generate_ai_completion(
        preferred_model=model,
        system_instruction=system_instruction,
        prompt=prompt,
        temperature=0.65,
        json_mode=True,
        user_keys=user_keys,
        user_api_key=user_api_key
    )

    data = clean_json_loads(raw_response)
    return data


# =====================================================================
# REMIXCRAFT: COMPETITOR VIDEO REMODELER ENGINE
# =====================================================================

async def remodel_competitor_analysis(
    source_type: str,
    source_content: str,
    culture: str = "African / Nigerian",
    target_duration: str = "Standard (8–15 Mins)",
    lead_character: dict = None,
    user_api_key: str = None,
    model_name: str = None,
    user_keys: dict = None
) -> dict:
    """
    Stage 1: Deconstructs a competitor video, raw script, or movie premise into viral DNA,
    and returns 3 fresh, copyright-safe remodeled angles.
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL

    lead_context = ""
    if lead_character and isinstance(lead_character, dict):
        lead_context = f"\nLEAD ACTOR (CASTLOCK CONTINUITY): {lead_character.get('name', 'Main Protagonist')} - {lead_character.get('visual_summary', '') or lead_character.get('prompt', '')}"

    system_instruction = f"""
You are the Chief Viral Strategist & Story Architect at WP Studio.
Your job is to study a competitor video, script, or movie idea and create 3 fresh, original, copyright-safe story angles for our creator's YouTube channel.

CRITICAL RULES FOR HIGH-RETENTION, INTERESTING STORIES:
1. USE SIMPLE, EVERYDAY WORDS: Do not use complicated jargon or big words. Write in plain, clear, engaging language.
2. 100% ORIGINAL & COPYRIGHT-SAFE: Keep the emotional hook and viral engine of the original, but rewrite the characters, setting, and plot twists so it is completely fresh and safe from copyright strikes.
3. CULTURE TASTE: Infuse the dialogue and tone with the chosen culture: {culture}.
4. TARGET VIDEO RUNTIME: Tailor the pacing and tension curve for a {target_duration} video.
5. 3 DISTINCT REMODELED ANGLES:
   - Angle 1: High Tension / Thriller Angle (High stakes, dangerous secrets, ticking clock)
   - Angle 2: Emotional Drama / Relatable Conflict Angle (Family loyalty, betrayal, personal struggle, heart)
   - Angle 3: Fast-Paced Mystery / Plot Twist Angle (Unexpected reveals, hidden identities, shocking turn)

OUTPUT FORMAT: Return ONLY valid JSON with this exact structure:
{{
    "source_summary": "Short 2-3 sentence summary of what the competitor story was about in plain words.",
    "viral_dna": {{
        "hook_analysis": "Why this video idea hooks viewers in the first 5 seconds.",
        "psychological_trigger": "The main feeling that makes people watch (curiosity, fear of missing out, revenge, shock, or hope).",
        "opportunity": "What we can do better than the competitor to get more watch time and comments."
    }},
    "concepts": [
        {{
            "id": 1,
            "angle_badge": "High Tension Thriller",
            "title": "A punchy, click-worthy YouTube title",
            "logline": "1 clear sentence explaining the remodeled story hook",
            "hook_line": "The exact opening voiceover line spoken in the first 5 seconds to hook viewers",
            "twist": "The shocking twist that happens near the climax",
            "why_it_goes_viral": "Why people will watch to the end and comment"
        }},
        {{
            "id": 2,
            "angle_badge": "Emotional Drama & Conflict",
            "title": "A punchy, click-worthy YouTube title",
            "logline": "1 clear sentence explaining the remodeled story hook",
            "hook_line": "The exact opening voiceover line spoken in the first 5 seconds to hook viewers",
            "twist": "The shocking twist that happens near the climax",
            "why_it_goes_viral": "Why people will watch to the end and comment"
        }},
        {{
            "id": 3,
            "angle_badge": "Mystery & Sudden Reversal",
            "title": "A punchy, click-worthy YouTube title",
            "logline": "1 clear sentence explaining the remodeled story hook",
            "hook_line": "The exact opening voiceover line spoken in the first 5 seconds to hook viewers",
            "twist": "The shocking twist that happens near the climax",
            "why_it_goes_viral": "Why people will watch to the end and comment"
        }}
    ]
}}
"""

    prompt = f"""SOURCE TYPE: {source_type}
CULTURE: {culture}
TARGET RUNTIME: {target_duration}{lead_context}

COMPETITOR CONTENT / PREMISE:
{source_content[:15000]}

Analyze this source and generate the viral DNA plus 3 distinct remodeled concepts."""

    raw_response = generate_ai_completion(
        preferred_model=model,
        system_instruction=system_instruction,
        prompt=prompt,
        temperature=0.7,
        json_mode=True,
        user_keys=user_keys,
        user_api_key=user_api_key
    )

    data = clean_json_loads(raw_response)
    return data


async def generate_remodeled_production_package(
    selected_concept: dict,
    source_summary: str = "",
    culture: str = "African / Nigerian",
    target_duration: str = "Standard (8–15 Mins)",
    art_style: str = "Realistic",
    visual_filter: str = "Default",
    lead_character: dict = None,
    user_api_key: str = None,
    model_name: str = None,
    user_keys: dict = None
) -> dict:
    """
    Stage 2: Takes the selected remodeled angle and builds a complete, production-ready screenplay,
    shot-by-shot visual scene prompts, video camera motion prompts, and 3 high-CTR thumbnail ideas.
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL

    # Filter definitions
    filter_map = {
        "Default": "35mm anamorphic film lens, realistic studio lighting, cinematic dynamic range, true-to-life colors.",
        "Horror": "Prestige dread grade, deep gloomy shadows, desaturated cool tones, eerie chiaroscuro lighting, volumetric atmospheric mist.",
        "Romance": "Warm honey-rose golden hour glow, soft mist diffusion filter, creamy bokeh, intimate warm amber rim lighting.",
        "Action": "High-contrast dynamic punch, saturated primaries, vivid motion blur, dramatic specular highlights, high shutter angle.",
        "Drama": "Naturalistic prestige cinematic lighting, subtle earthy tones, gentle directional window light, deep emotional contrast.",
        "Thriller": "Cold steel tension grade, cyan-tinted low-key lighting, harsh sharp shadows, claustrophobic framing, high tension.",
        "Sci-Fi": "Cyber-teal and vivid neon specular backlight, atmospheric damp fog reflections, anamorphic blue horizontal lens flares."
    }
    filter_treatment = filter_map.get(visual_filter, filter_map["Default"])

    # Art style definitions
    if "3D" in art_style or "Animated" in art_style:
        art_treatment = "Pixar / Disney 3D high-end animation style, expressive stylized 3D character design, soft subsurface scattering (SSS), vibrant animated feature color palette, Octane 3D render."
    else:
        art_treatment = "8K hyper-detailed cinematic movie still, shot on ARRI Alexa 35mm, real human skin pores, photorealistic textures, photorealistic studio lighting."

    # Voice flavor
    if "African" in culture or "Nigerian" in culture:
        voice_treatment = "Authentic Nigerian English / Nollywood dramatic cadence, culturally rich emotional phrasing in dialogue and narration."
    elif "Black American" in culture:
        voice_treatment = "Authentic Black American cultural cadence, soulful urban and African American expressive vernacular and rhythm in dialogue and narration."
    elif "British" in culture:
        voice_treatment = "Refined British English cadence, measured storytelling delivery and polished dramatic tone."
    else:
        voice_treatment = "Modern cinematic American pacing, conversational natural flow in voiceover and dialogue."

    lead_actor_instructions = ""
    if lead_character and isinstance(lead_character, dict):
        lead_name = lead_character.get("name", "Protagonist")
        lead_desc = lead_character.get("visual_summary", "") or lead_character.get("prompt", "")
        lead_actor_instructions = f"""
CASTLOCK LEAD ACTOR MANDATE:
The lead character MUST be named "{lead_name}".
Their visual appearance in EVERY scene where they appear must maintain exact continuity:
{lead_desc}
"""

    system_instruction = f"""
You are the Executive Showrunner & Visual Director at WP Studio.
Your mission is to write a complete, viral YouTube screenplay and production package based on the chosen remodeled story concept.

CRITICAL RULES FOR HIGH-RETENTION, INTERESTING STORIES:
1. USE SIMPLE, CLEAR WORDS: Write dialog and narration in easy, natural, conversational words. Avoid big, awkward, or dictionary-sounding words.
2. RETENTION ENGINE: Start with an explosive hook in Scene 1. Maintain high tension, fast pacing, and deliver an unforgettable twist before the finale.
3. SCENE BREAKDOWN & RUNTIME DEPTH FOR {target_duration}:
   - For Short (3–5 Mins): 10 to 14 fully developed scenes (each ~30–45s).
   - For Standard (8–15 Mins): 20 to 30 rich scenes (each ~1–2 mins of dialogue).
   - For Deep Dive (30–60 Mins): 35 to 48 extended scenes (each ~2–3 mins of dialogue/dramatics).
   - For Feature Movie (1–2+ Hours): MINIMUM 60 TO 80 DEEP SCENES REQUIRED (do NOT stop at 35 or 40 scenes! Write 65 to 80 major cinematic sequence scenes, each ~2–3 mins with substantial multi-character dialogues, dramatic conflicts, plot twists, emotional stakes, and full sequence progression. Absolutely NO cut-short or rushed scenes!).

4. RECURRING LOCATION CONSISTENCY PROMPTS ("locations" array):
   - Identify every location in the story (especially locations that appear more than once!).
   - Provide an "unoccupied_reference" prompt for each location ("Empty, unoccupied reference view with no people or characters. Wide establishing shot, 24mm lens...") and list "scenes_used" (e.g. "Scenes 1, 3, 8") so the creator can generate consistent location backgrounds.

5. FULL-BODY CHARACTER SHEET PROMPTS ("characters" array):
   - Provide a full-body head-to-toe character reference prompt in "locked_visual_description" for every character so their face, hair, skin tone, and outfit stay consistent.

4. CRITICAL SCREENPLAY & SCENE CONTINUITY (NO ISOLATED SINGLE-LINE SCENES):
   - A SCENE is defined by one continuous location and dramatic beat (e.g. INT. ATLANTA GRAND BALLROOM - NIGHT).
   - Under NO circumstances split a continuous conversation across multiple scenes!
   - If two or more characters are present in a scene (e.g. Marcus and his wife Victoria at the wedding), their complete back-and-forth interaction, conversation, and reactions MUST happen together within that SAME scene.
   - NEVER create a new scene just for another character to reply.
   - "dialogue_or_narration" MUST contain the FULL multi-turn screenplay conversation for that scene formatted with speaker names, for example:
     MARCUS: (Whispering, transfixed) That chord... nobody plays that bridge except Keisha. Nobody.
     VICTORIA: (Tugging his arm firmly) Marcus, honey, you're staring. That little girl is just hired entertainment. Let's get back to our table.
     MARCUS: You don't understand, Victoria. That song was never published. Keisha only played it for me before she died.
   - If a scene is narration-based, write a rich, multi-sentence spoken voiceover paragraph (not just one sentence!).

5. MIDJOURNEY / FLUX IMAGE PROMPTS: Every scene prompt must be completely standalone. Include camera lens & shot angle (Objective wide shot, Two-shot, Over-the-shoulder, Dramatic close-up), lighting, all characters present with spatial staging, clothes, facial expressions, concrete action, and the art style: {art_treatment}. Strictly NO text, captions, logos, or split screens.
6. VIDEO MOTION PROMPTS: Specify exact camera movements (slow push-in, low-angle track, drone orbit, subtle handheld shake) and subject movement for Runway Gen-3 / Luma Dream Machine.
7. 3 HIGH-CTR THUMBNAIL CONCEPTS: Provide 3 high-contrast, clickable thumbnail prompts with 3-5 bold punchy overlay words.
{lead_actor_instructions}
- Tone & Voice: {culture} ({voice_treatment})
- Visual Filter: {visual_filter} ({filter_treatment})
- Art Style: {art_style} ({art_treatment})

OUTPUT SCHEMA: Return ONLY valid JSON with this exact structure:
{{
    "title": "{selected_concept.get('title', 'Remodeled Story')}",
    "logline": "{selected_concept.get('logline', '')}",
    "synopsis": "A detailed 2-3 paragraph summary of the entire remodeled screenplay, explaining the full journey and twist.",
    "culture": "{culture}",
    "target_duration": "{target_duration}",
    "art_style": "{art_style}",
    "visual_filter": "{visual_filter}",
    "locations": [
        {{
            "name": "Location Name (e.g. Lekki Waterfront Villa - Living Room)",
            "scenes_used": "Scenes 1, 4, 9, 15",
            "unoccupied_reference": "Empty, unoccupied reference view with no people or characters. Wide establishing shot, 24mm lens, [detailed architecture, walls, floor, lighting, props, colors, and atmosphere]. {art_treatment}. No people, no text, no watermarks."
        }}
    ],
    "characters": [
        {{
            "name": "Character Name",
            "role": "Role (e.g. Lead Protagonist, Antagonist, Loyal Friend)",
            "visual_description": "Detailed description of their face, skin tone, hair, and clothing for visual consistency",
            "locked_visual_description": "Full-length standing shot, complete head-to-toe uncropped full body view showing entire figure from shoes on the floor to top of head, eye-level angle. [Character Name] has [face, skin tone, eyes, hair, build], wearing [complete signature outfit and footwear]. Neutral grey studio background, soft studio lighting, {art_treatment}. No cut off legs, no cut off shoes, no text."
        }}
    ],
    "scenes": [
        {{
            "scene_number": 1,
            "scene_title": "Descriptive Scene Heading",
            "setting": "INT. or EXT. Location - Time of Day",
            "location": "Location Name from Location Bible",
            "estimated_duration": "2m 30s",
            "characters_present": ["Character 1", "Character 2"],
            "narration": "Clean narrator voiceover paragraph for this scene",
            "dialogue": "Character 1: \\"Spoken line...\\"\\nCharacter 2: \\"Reply line...\\"",
            "dialogue_or_narration": "Full multi-turn screenplay conversation with character names or deep spoken voiceover paragraph",
            "image_prompt": "Ultra-detailed Midjourney/Flux prompt with camera lens, lighting, location details, character biometric likeness in parentheses, action, style",
            "video_prompt": "Cinematic camera movement and character motion for Runway/Luma/Pika"
        }}
    ],
    "thumbnail_concepts": [
        {{
            "concept_number": 1,
            "headline": "Core visual focus (e.g. The Shocking Discovery)",
            "visual_prompt": "Midjourney prompt for an eye-catching YouTube thumbnail image with high contrast and intense facial expression",
            "bold_text_overlay": "3-5 BOLD WORDS (e.g. HE LIED TO HER!)",
            "emotional_trigger": "Why viewers will click this thumbnail immediately"
        }},
        {{
            "concept_number": 2,
            "headline": "Core visual focus",
            "visual_prompt": "Midjourney prompt for an eye-catching YouTube thumbnail image",
            "bold_text_overlay": "3-5 BOLD WORDS",
            "emotional_trigger": "Why viewers will click this thumbnail immediately"
        }},
        {{
            "concept_number": 3,
            "headline": "Core visual focus",
            "visual_prompt": "Midjourney prompt for an eye-catching YouTube thumbnail image",
            "bold_text_overlay": "3-5 BOLD WORDS",
            "emotional_trigger": "Why viewers will click this thumbnail immediately"
        }}
    ]
}}
"""

    prompt = f"""SELECTED REMODELED ANGLE:
Title: {selected_concept.get('title')}
Angle: {selected_concept.get('angle_badge')}
Logline: {selected_concept.get('logline')}
Hook Line: {selected_concept.get('hook_line')}
Twist: {selected_concept.get('twist')}
Why It Goes Viral: {selected_concept.get('why_it_goes_viral')}

ORIGINAL CONTEXT:
{source_summary}

Write the complete shot-by-shot screenplay, Midjourney visual prompts, video motion prompts, and 3 thumbnail concepts following all instructions above."""

    raw_response = generate_ai_completion(
        preferred_model=model,
        system_instruction=system_instruction,
        prompt=prompt,
        temperature=0.65,
        json_mode=True,
        user_keys=user_keys,
        user_api_key=user_api_key
    )

    data = clean_json_loads(raw_response)
    return data




# ==============================================================================
# TOONCRAFT: 3D KIDS CARTOON & ANIMATION PRODUCTION SUITE
# ==============================================================================

async def generate_tooncraft_story_package(
    length_tier: str = "5 min",
    topic_mode: str = "ai_invents",
    custom_topic: str = "",
    character_type: str = "Kids",
    age_band: str = "4–7",
    genre: str = "Adventure & Quest",
    tone: str = "Playful & Cheerful",
    has_songs: bool = True,
    has_dance: bool = True,
    has_interactive: bool = True,
    lead_character: str = None,
    user_api_key: str = None,
    model_name: str = None,
    user_keys: dict = None
) -> dict:
    """
    ToonCraft 3D Kids Cartoon Production Engine:
    Generates a complete kids animation package with:
    - 3D Pixar & DreamWorks CGI styling with Octane renders and subsurface scattering (SSS).
    - Age-appropriate developmental storytelling and vocabulary for the selected Age Band.
    - Fast, child-retention pacing (scenes strictly <= 15 seconds each).
    - Catchy nursery rhymes / musical songs with melodic cues.
    - Dance break choreography cues.
    - 4th-wall interactive viewer pauses for audience participation.
    - Master Character Sheet prompts (visual locks).
    - Recurring Location Consistency Prompts (unoccupied background references).
    - Scene-by-scene 3D Image Prompts & Video Motion Prompts.
    """
    model = model_name or DEFAULT_MODEL
    length_str = str(length_tier).lower()
    
    if "20" in length_str:
        target_scenes = 40
        min_scenes = 36
        max_scenes = 45
        runtime_label = "20 min (~40 scenes, <=15s segments)"
    elif "15" in length_str:
        target_scenes = 30
        min_scenes = 26
        max_scenes = 35
        runtime_label = "15 min (~30 scenes, <=15s segments)"
    elif "10" in length_str:
        target_scenes = 20
        min_scenes = 18
        max_scenes = 24
        runtime_label = "10 min (~20 scenes, <=15s segments)"
    else:
        target_scenes = 12
        min_scenes = 10
        max_scenes = 14
        runtime_label = "5 min (~12 scenes, <=15s segments)"

    # Age band styling guidelines
    age_str = str(age_band)
    if "2" in age_str or "3" in age_str:
        age_guideline = (
            "Target Audience: Toddlers & Preschoolers (Ages 2-4). Use simple, repetitive words, joyful rhymes, "
            "gentle reassuring conflicts, bright primary colors, friendly smiles, and clear emotional expressions."
        )
    elif "8" in age_str or "9" in age_str or "10" in age_str or "11" in age_str:
        age_guideline = (
            "Target Audience: Older Kids (Ages 8-11). Use witty dialogue, inventive quests, teamwork, clever solutions, "
            "playful humor, and exciting dynamic challenges."
        )
    else:
        age_guideline = (
            "Target Audience: Early Elementary Kids (Ages 4-7). Use playful curiosity, preschool problem-solving, "
            "teamwork, sharing, funny antics, wonder, and encouraging positive reinforcement."
        )

    # Character world instructions
    char_type_lower = str(character_type).lower()
    if "fruit" in char_type_lower:
        char_rules = (
            "Characters must be anthropomorphic talking fruits and vegetables (e.g. golden mango, red apple, sweet strawberry, "
            "dancing banana, friendly broccoli) with expressive cartoon eyes, beaming open-mouth smiles, cute white cartoon gloves, "
            "and colorful sneakers in 3D Pixar animation style."
        )
    elif "animal" in char_type_lower:
        char_rules = (
            "Characters must be cute anthropomorphic talking animals (e.g. fluffy puppy, curious lion cub, playful bunny, friendly bear) "
            "with soft 3D stylized fur, upright posture, cute bright kid outfits, and large sparkling cartoon eyes."
        )
    elif "vehicle" in char_type_lower:
        char_rules = (
            "Characters must be anthropomorphic talking vehicles (e.g. friendly fire truck, cheerful delivery car, playful airplane) "
            "with big expressive windshield eyes, smiling front bumpers, and glossy Pixar Cars aesthetic."
        )
    elif "object" in char_type_lower:
        char_rules = (
            "Characters must be anthropomorphic talking everyday objects (e.g. playful pencil, smiling clock, bouncy soccer ball, "
            "talking paintbrush) with cute cartoon faces and energetic limbs in Pixar Toy Story style."
        )
    elif "mixed" in char_type_lower:
        char_rules = (
            "Cast must feature a human child protagonist paired with an adorable talking animal, fruit, or vehicle best friend."
        )
    else:
        char_rules = (
            "Characters must be stylized 3D human kids with oversized expressive eyes, cute cartoon hairstyles, joyful smiles, "
            "and bright modern colorful kid clothes in 3D Pixar and Disney CGI animation style."
        )

    # Audio extras instructions
    song_rule = (
        "CATCHY SONGS: Include 1 to 3 catchy rhyming song / nursery rhyme verses in the story. "
        "Format with [SONG / RHYME - Melody: Upbeat & Cheerful]: four-line rhyming lyrics that kids love to sing along to."
        if has_songs else "No full songs needed, focus on spoken dialogue and narration."
    )
    dance_rule = (
        "DANCE BREAKS: In 2 to 3 scenes, include joyful dance choreography cues in the script and motion prompts, "
        "e.g. [DANCE BREAK: character does the wiggle dance and spins around cheerfully!]."
        if has_dance else ""
    )
    inter_rule = (
        "4TH-WALL INTERACTIVE PARTICIPATION: Include 2 to 4 interactive audience engagement pauses where a character "
        "breaks the fourth wall, looks directly into the camera, asks the viewer a simple question, pauses, and praises them. "
        "Format: [INTERACTIVE PAUSE - 3 SECONDS: Character points to screen: \'Can you find the yellow star? There it is! Good job!\']."
        if has_interactive else ""
    )

    topic_instruction = (
        f"USER SPECIFIED TOPIC / PREMISE:\n{custom_topic}"
        if (topic_mode != "ai_invents" and custom_topic.strip())
        else "AI INVENTED TOPIC: Invent an original, heartwarming, educational, and fun kids animation story premise that perfectly fits the genre, tone, cast, and age band."
    )

    system_instruction = f"""You are the Lead Creative Director and Animation Screenplay Master at a world-class 3D animation studio (Pixar, Disney, DreamWorks, Cocomelon).
You specialize in creating hit animated cartoons for kids YouTube channels with massive audience retention, educational value, and visual delight.

STRICT CARTOON SPECIFICATIONS:
1. AGE & DEVELOPMENTAL FIT:
{age_guideline}

2. CAST WORLD & VISUAL LOCKS:
{char_rules}
Invent a memorable cast of 2 to 5 characters. Every character must have a permanent full-body 3D Pixar visual lock description.

3. SCENE TIMING & PACING:
- Produce EXACTLY {target_scenes} scenes (minimum {min_scenes}, maximum {max_scenes}).
- Every single scene MUST be strictly 10 to 15 seconds in duration (<=15s). This matches toddler and child attention spans.
- Each scene must be punchy, visually dynamic, and have clear character actions.

4. SCRIPT & AUDIO:
- Warm, cheerful narrator voiceover and joyful character dialogue.
- {song_rule}
- {dance_rule}
- {inter_rule}

5. TIGHT & ACCURATE IMAGE PROMPTS (MIDJOURNEY / FLUX):
Every scene image prompt MUST follow this strict 3D Pixar CGI aesthetic:
"3D Pixar and Disney animation style, Octane 3D render, smooth stylized skin with soft subsurface scattering (SSS), large expressive sparkling eyes, joyful facial expression, vibrant warm studio lighting, playful pastel and primary color palette, child-safe whimsical background, clean CGI aesthetic, cinematic depth of field, 8K ultra detail --ar 16:9"
Negative guardrails: Strictly NO photorealism, NO skin pores, NO sharp scary teeth, NO dark gloomy shadows, NO violence, NO menacing expressions.

6. DYNAMIC VIDEO MOTION PROMPTS (KLING / RUNWAY / GOOGLE FLOW):
Every video motion prompt must specify fluid animated camera motion:
"Gentle bouncy camera track, cheerful character head tilt, playful camera zoom-in on smiling face, smooth Pixar motion dynamics, fluid 3D cartoon animation physics, warm ambient glow"

7. RECURRING LOCATION CONSISTENCY:
Identify all recurring locations that appear more than once (e.g. Preschool Classroom, Sunny Hill, Treehouse, Garden).
For every recurring location, provide an unoccupied wide background establishing prompt with zero characters, so the setting looks 100% consistent throughout the movie.

OUTPUT FORMAT:
You MUST respond with valid JSON ONLY, strictly following this schema:
{{
  "title": "Fun Catchy Kids Story Title",
  "logline": "1-sentence uplifting logline",
  "moral_lesson": "Core positive lesson (e.g. sharing brings happiness, teamwork solves big problems)",
  "target_duration": "{runtime_label}",
  "age_band": "{age_band}",
  "genre": "{genre}",
  "tone": "{tone}",
  "character_type": "{character_type}",
  "youtube_description": "SEO-optimized YouTube video description with kid-friendly hashtags and chapter timestamps",
  "characters": [
    {{
      "name": "Character Name",
      "role": "Lead Protagonist / Best Friend / Mentor",
      "character_type": "{character_type}",
      "visual_lock": "Full-body 3D Pixar visual description for Midjourney/Flux including colors, facial features, eyes, and clothes --ar 16:9",
      "wardrobe_lock": "Specific consistent outfit or features"
    }}
  ],
  "locations": [
    {{
      "name": "Location Name",
      "scenes_used": "Scene 1, Scene 3, Scene 7",
      "master_location_prompt": "Unoccupied wide establishing shot of the location with no characters present, 3D Pixar aesthetic, Octane render --ar 16:9"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "scene_title": "Scene Name",
      "duration": "12s",
      "setting": "Location Name",
      "characters_present": ["Character Name"],
      "narration": "Warm cheerful narrator line",
      "dialogue": "Character dialogue line",
      "dialogue_or_narration": "Full combined script text for this scene including songs or interactive pauses if present",
      "song_lyrics": "Rhyming song lyrics if this scene includes singing, else empty string",
      "interactive_cue": "Interactive 4th-wall pause if present, else empty string",
      "dance_cue": "Dance choreography cue if present, else empty string",
      "image_prompt": "3D Pixar and Disney animation style, Octane 3D render... full scene image prompt --ar 16:9",
      "video_prompt": "Camera motion prompt for Kling/Runway with smooth cartoon motion physics"
    }}
  ]
}}
"""

    prompt = f"""GENERATE TOONCRAFT 3D KIDS CARTOON PACKAGE:
Length Tier: {length_tier} (Generate exactly {target_scenes} scenes, strictly <=15s per cut)
Character Type: {character_type}
Age Band: {age_band}
Genre: {genre}
Tone: {tone}
Catchy Songs: {'Yes' if has_songs else 'No'}
Dance Breaks: {'Yes' if has_dance else 'No'}
Interactive 4th-Wall Pauses: {'Yes' if has_interactive else 'No'}

{topic_instruction}

Ensure every scene image prompt uses the tight 3D Pixar CGI formula with subsurface scattering, Octane render, and playful colors. Return valid JSON only."""

    raw_response = generate_ai_completion(
        preferred_model=model,
        system_instruction=system_instruction,
        prompt=prompt,
        temperature=0.65,
        json_mode=True,
        user_keys=user_keys,
        user_api_key=user_api_key
    )

    data = clean_json_loads(raw_response)
    if not isinstance(data, dict):
        data = {"title": "Kids Cartoon Adventure", "scenes": []}
    return data


async def generate_podcast_package(
    category: str = "Motivational Quotes",
    topic_mode: str = "ai_idea",
    custom_topic: str = "",
    user_perspective: str = "",
    host_format: str = "two_host",
    visual_style: str = "human_realistic",
    discussion_dynamic: str = "heated_debate",
    studio_archetype: str = "dark_acoustic",
    aspect_ratio: str = "9:16",
    channel_name: str = "Real Talk Africa",
    host_1: dict = None,
    host_2: dict = None,
    user_api_key: str = None,
    model_name: str = None,
    user_keys: dict = None
) -> dict:
    """
    Podcast Studio Production Engine:
    Generates a complete viral video podcast episode package with:
    - 3-Second explosive viral hook engineered for short-form retention.
    - Host continuity and facial identity lock specifications.
    - Studio environment styling with user's exact channel branding on neon signs, mugs, and mic clips.
    - Multi-camera director switching ([CAM A: Host 1 Close-Up], [CAM B: Host 2 Reaction Cutaway], [CAM C: Wide Two-Shot], [SPLIT SCREEN]).
    - Dynamic back-and-forth dialogue with emotional delivery cues and TTS-ready performance notes.
    - Standalone image prompts (Midjourney/Flux) and video camera motion prompts (Kling/Runway Gen-3).
    """
    model = model_name or DEFAULT_MODEL

    h1 = host_1 or {}
    h2 = host_2 or {}

    h1_gender = h1.get("gender", "Male")
    h1_eth = h1.get("ethnicity", "Black")
    h1_custom_accent = h1.get("custom_accent", "").strip()
    h1_accent = h1_custom_accent if (h1.get("accent") == "Custom" and h1_custom_accent) else h1.get("accent", "Nigerian English")
    h1_has_portrait = bool(h1.get("has_portrait", False))
    h1_desc_raw = h1.get("description", "").strip()
    if h1_has_portrait:
        h1_portrait_lock = "[IDENTITY LOCK: Character reference portrait provided. Lock facial structure, facial features, and skin tone to reference. Consistent studio hairstyle, wardrobe, and grooming.]"
        h1_desc = f"{h1_portrait_lock} {h1_desc_raw}" if h1_desc_raw else f"{h1_portrait_lock} {h1_eth} {h1_gender.lower()} in modern tailored minimalist attire"
    else:
        h1_desc = h1_desc_raw or f"{h1_eth} {h1_gender.lower()} in modern tailored minimalist attire"

    is_two_host = (host_format != "single_host")

    h2_gender = h2.get("gender", "Female") if is_two_host else "None"
    h2_eth = h2.get("ethnicity", "Black") if is_two_host else "None"
    h2_custom_accent = h2.get("custom_accent", "").strip() if is_two_host else ""
    h2_accent = h2_custom_accent if (h2.get("accent") == "Custom" and h2_custom_accent) else h2.get("accent", "American English") if is_two_host else "None"
    h2_has_portrait = bool(h2.get("has_portrait", False)) if is_two_host else False
    h2_desc_raw = h2.get("description", "").strip() if is_two_host else ""
    if is_two_host:
        if h2_has_portrait:
            h2_portrait_lock = "[IDENTITY LOCK: Character reference portrait provided. Lock facial structure, facial features, and skin tone to reference. Consistent studio hairstyle, wardrobe, and grooming.]"
            h2_desc = f"{h2_portrait_lock} {h2_desc_raw}" if h2_desc_raw else f"{h2_portrait_lock} {h2_eth} {h2_gender.lower()} in stylish studio wardrobe"
        else:
            h2_desc = h2_desc_raw or f"{h2_eth} {h2_gender.lower()} in stylish studio wardrobe"
    else:
        h2_desc = "None"

    # Studio Archetype Mapping
    archetype_map = {
        "dark_acoustic": "Dark Moody / Slate Acoustic studio with warm oak vertical wood slats, amber rim lighting, Shure SM7B microphones on black articulated boom arms, frosted glass table, and soft cyan neon background bokeh.",
        "neon_cyber": "Late Night Cyber Lounge with raw dark industrial brick wall, custom vibrant neon sign displaying the channel name, velvet armchairs, moody purple and cyan ambient lighting.",
        "luxury_penthouse": "High-End Executive Penthouse with floor-to-ceiling glass windows overlooking a nighttime city skyline, minimalist smoked glass desk, designer leather chairs, warm architectural downlights.",
        "cozy_loft": "Intimate Bohemian Loft with exposed red brick, lush green indoor plants, warm incandescent floor lamps, rustic wooden table, relaxed cozy coffeehouse aesthetic.",
        "pixar_studio": "3D Stylized Pixar Broadcast Desk with bold vibrant colors, oversized cartoon condenser microphones, playful geometric acoustic wall panels, glossy Octane 3D lighting."
    }
    studio_desc = archetype_map.get(studio_archetype, archetype_map["dark_acoustic"])

    # Discussion Dynamic Mapping
    dynamic_map = {
        "heated_debate": "High-intensity intellectual clash. Host 1 takes a polarizing, provocative stance. Host 2 challenges assumptions with hard counter-arguments, spicy rebuttals, and passionate pushback. Respectful but high tension.",
        "interviewer_expert": "Mastermind interview. Host 1 asks penetrating, uncomfortable questions that cut through surface fluff. Host 2 shares deep, vulnerable stories, tactical secrets, and revelatory insights.",
        "unfiltered_banter": "Raw, funny, authentic chemistry. Casual storytelling, witty banter, interruptions, genuine laughter, playful roasting, and relatable admissions.",
        "philosophical_chill": "Deep reflective late-night exploration. Thought-provoking questions on human nature, consciousness, ambition, and life lessons with calm, mesmerizing pacing."
    }
    dynamic_desc = dynamic_map.get(discussion_dynamic, dynamic_map["heated_debate"])

    # Topic Setup
    if topic_mode == "custom" and custom_topic:
        topic_spec = f"TOPIC: {custom_topic}\n"
        if user_perspective:
            topic_spec += f"CREATOR'S PERSPECTIVE / ANGLE: {user_perspective}\n(Preserve this exact perception as the core thesis of the episode.)\n"
    else:
        topic_spec = f"CATEGORY: {category}\nTASK: Invent an original, highly polarizing, viral podcast topic from this category that immediately sparks curiosity and strong opinions.\n"

    target_aspect = "9:16 vertical split/portrait" if "9:16" in str(aspect_ratio) else "16:9 widescreen"

    system_instruction = f"""You are the Executive Showrunner and Lead Multi-Cam Director for elite short-form video podcasts (specializing in TikTok, YouTube Shorts, and Reels viral formats).
Your job is to generate a complete, studio-grade video podcast episode package.

CRITICAL PRODUCTION RULES:
1. THE 3-SECOND BOMBSHELL HOOK:
   - Scene 1 MUST open with an explosive, high-tension statement or unresolved provocative question.
   - Zero boring pleasantries ('welcome back guys', 'today we talk about'). Jump straight into the conflict.
2. DYNAMIC & PACING:
   - {dynamic_desc}
   - Pacing must be punchy: 8 to 12 scenes total, each scene representing a fast 5 to 10 second camera cut.
3. MULTI-CAMERA SWITCHING:
   - Explicitly label every scene with camera view:
     - [CAM A: Host 1 Tight Close-Up] (Speaking, intense direct delivery or microphone lean)
     - [CAM B: Host 2 Reaction Cutaway] (Listening, nodding, smirking, shocked eye contact, incredulous objection)
     - [CAM C: Studio Wide Two-Shot] (Establishing both hosts, table, microphones, and studio ambiance)
     - [SPLIT SCREEN: Vertical Multi-Cam] (Simultaneous Host 1 speaking / Host 2 reacting)
4. BRANDING WATERMARK:
   - Naturally integrate the channel name '{channel_name}' into the background studio set: glowing neon sign, coffee mugs, or microphone flag clips.
5. VOICE & AUDIO PERFORMANCE NOTES:
   - Include vocal delivery notes in parentheses for every spoken line (e.g., '(leaning into microphone, quiet intense cadence)').
   - Include ambient audio cues (e.g., '[Audio: Deep sub-bass hit, soft mic breath, distant studio acoustic decay]').
6. VISUAL STYLE:
   - Visual Style: {'Human Photorealistic (85mm f/1.8 lens, 8k, cinematic rim lighting)' if visual_style == 'human_realistic' else '3D Pixar and Disney animation CGI render, Octane render, subsurface scattering'}.
   - Aspect Ratio: {target_aspect}.

STRICT JSON OUTPUT FORMAT ONLY:
{{
  "title": "Short punchy viral episode title",
  "category": "{category}",
  "hook": "The exact 3-second opening hook line",
  "discussion_dynamic": "{discussion_dynamic}",
  "studio_archetype": "{studio_archetype}",
  "visual_style": "{visual_style}",
  "aspect_ratio": "{aspect_ratio}",
  "channel_name": "{channel_name}",
  "host_format": "{host_format}",
  "studio_environment": "{studio_desc}",
  "channel_branding": "Exact description of how '{channel_name}' is integrated across neon sign, mugs, and mic clips",
  "runtime_detail": "8-12 Multi-Cam Scenes (~60-90s Short)",
  "hosts": [
    {{
      "name": "Host 1 (Lead Host)",
      "role": "Host 1 role description",
      "gender": "{h1_gender}",
      "ethnicity": "{h1_eth}",
      "accent": "{h1_accent}",
      "wardrobe_lock": "Detailed description of exact outfit, accessories, and grooming",
      "locked_visual_description": "Full-body and portrait identity prompt for Host 1 locking face, hair, and build",
      "vocal_profile": "Vocal pitch, cadence, and delivery guide for ElevenLabs / TTS"
    }}
    {f''',
    {{
      "name": "Host 2 (Co-Host / Guest)",
      "role": "Host 2 counterpoint role description",
      "gender": "{h2_gender}",
      "ethnicity": "{h2_eth}",
      "accent": "{h2_accent}",
      "wardrobe_lock": "Detailed description of exact outfit, accessories, and grooming",
      "locked_visual_description": "Full-body and portrait identity prompt for Host 2 locking face, hair, and build",
      "vocal_profile": "Vocal pitch, cadence, and delivery guide for ElevenLabs / TTS"
    }}''' if is_two_host else ''}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "camera_shot": "CAM A: Host 1 Tight Close-Up",
      "speaker": "Host 1",
      "delivery_cues": "leaning into mic, intense gaze, deliberate cadence",
      "dialogue": "Spoken dialogue for scene 1",
      "audio_cues": "Deep sub-bass impact, soft room decay",
      "estimated_duration": "7s",
      "image_prompt": "Photorealistic or 3D scene prompt with exact camera view, host likeness, and studio backdrop with channel neon sign --ar {aspect_ratio.replace(' Vertical', '').replace(' Widescreen', '')}",
      "video_prompt": "Camera motion prompt for Kling/Runway with speech gestures, head tilts, and micro-expressions"
    }}
  ]
}}
"""

    prompt = f"""GENERATE PODCAST STUDIO PRODUCTION PACKAGE:
{topic_spec}
Host Format: {'Two Hosts (Banter, debate, reaction cutaways)' if is_two_host else 'Single Host (Direct address, camera punch-ins)'}
Visual Style: {visual_style}
Studio Archetype: {studio_archetype}
Aspect Ratio: {aspect_ratio}
Channel Name: {channel_name}
Host 1 Identity: {h1_desc} | Accent: {h1_accent}
{'Host 2 Identity: ' + h2_desc + ' | Accent: ' + h2_accent if is_two_host else ''}

Generate exactly 8 to 12 fast-paced multi-camera scenes. Ensure every scene has distinct copy-ready image and video motion prompts. Return valid JSON only."""

    raw_response = generate_ai_completion(
        preferred_model=model,
        system_instruction=system_instruction,
        prompt=prompt,
        temperature=0.65,
        json_mode=True,
        user_keys=user_keys,
        user_api_key=user_api_key
    )

    data = clean_json_loads(raw_response)
    if not isinstance(data, dict):
        data = {
            "title": "Podcast Episode",
            "scenes": [],
            "hosts": []
        }
    return data
