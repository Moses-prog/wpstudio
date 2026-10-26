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

DEFAULT_MODEL = "gemini-3.8-flash"

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
FALLBACK_CHAIN = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"]

def clean_json_loads(text: str):
    """Safely extracts and parses JSON even if wrapped in markdown code fences or with trailing text."""
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
            # Pause between retries to let Google Cloud load balancer clear
            if "503" in err_str or "429" in err_str:
                time.sleep(1.5)
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
            "temperature": temperature
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        with httpx.Client(timeout=120.0) as http_client:
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
            "max_tokens": 4096,
            "system": sys_prompt,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature
        }

        with httpx.Client(timeout=120.0) as http_client:
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
            "temperature": temperature
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
    - Short: 15-30 scenes (ceiling 40)
    - Medium: 45-75 scenes (ceiling 120)
    - Long: 90-150 scenes (ceiling 250)
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL

    scene_targets = {
        "Short": "12 to 16 scenes (fast, complete 2 to 4 minutes story, ceiling 20)",
        "Medium": "25 to 35 scenes (complete 8 to 12 minutes story, ceiling 50)",
        "Long": "45 to 60 scenes (extended 20 to 30+ minutes story, ceiling 80)"
    }
    target_scenes = scene_targets.get(length_tier, "12 to 16 scenes")

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

2. WORLD BUILDING (LOCATION BIBLE):
Provide 3 to 5 distinct story locations. For each location, provide an "Empty, unoccupied reference view with no people or characters" detailing architecture, ground, lighting, practical props, material textures, and depth.

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
- If "{delivery_format}" == "Dialogue":
  The story is driven strictly by spoken conversations between characters like a screenplay. In every scene, script authentic, emotionally charged back-and-forth spoken lines in "dialogue" with speaker names (e.g. 'Marcus: "I told you never to come back here." / Elena: "You don\\'t own this city, Marcus."'). Narration voiceover should be empty string ("").
- If "{delivery_format}" == "Narrative":
  The story is told entirely through third-person or first-person narrator voiceover (optimized for ElevenLabs). In every scene, write gripping, high-retention spoken voiceover in "narration". Characters do NOT speak on-camera lines (set "dialogue" to an empty string "").
- If "{delivery_format}" == "Dialogue / Narrative":
  Cinematic hybrid format. Every scene contains compelling voiceover narration in "narration" setting tension/atmosphere, PLUS authentic on-camera spoken dialogue lines between characters in "dialogue".

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
            "unoccupied_reference": "Empty, unoccupied reference view with no people or characters. A modern luxury penthouse with floor-to-ceiling glass windows overlooking the Manhattan skyline... practical props, textures, foreground and background depth."
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
            "duration": "5s",
            "camera_perspective": "objective",
            "characters_present": ["Character Name"],
            "location": "Location Name from Location Bible",
            "dialogue": "Speaker: \\"Spoken line\\"",
            "narration": "Spoken voiceover line for ElevenLabs",
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
    user_api_key: str = None,
    model_name: str = None,
    user_keys: dict = None
) -> dict:
    """
    Story Adapter (Script to Scenes):
    Faithfully adapts a user's original written story or screenplay (500–5,000 words) into 
    exact, shot-by-shot cinematic scene prompts (1–80 scenes).
    
    STRICT GOVERNING RULES:
    1. ZERO PLOT/CHARACTER ALTERATIONS: Retains all original character names, relationships,
       locations, chronology, narrative pacing, dialogue, and ending 100% faithful to the source.
    2. SCENE SEGMENTATION: Natural pacing into 1-80 coherent scenes tailored to target duration.
    3. CINEMATIC VISUAL FILTER: Locks consistent color grading, lighting, and camera treatment.
    4. ART STYLE: Realistic 8K photorealism or 3D Animated Pixar/Disney.
    5. VOICE FLAVOR: Infuses dialogue tags / narration pacing with the chosen accent flavor.
    6. DELIVERY FORMAT: Prioritizes character dialogue, narrator voiceover, or a balanced blend.
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
        delivery_treatment = "DIALOGUE FOCUSED: Prioritize character dialogue and spoken character interactions for each scene."
    elif "Narrative" in delivery_format and "Dialogue" not in delivery_format:
        delivery_treatment = "NARRATIVE / VOICE-OVER FOCUSED: Prioritize rich voiceover narration and descriptive storytelling lines for each scene (ideal for faceless YouTube narrators)."
    else:
        delivery_treatment = "BALANCED DIALOGUE & NARRATION: Deliver a balanced blend of spoken character dialogue and narrator voiceover lines across scenes."

    system_instruction = f"""
You are the Master Storyboard Director & Visual Prompt Engineer at WP Studio.
Your mission is to adapt the creator's original written story into a complete, shot-by-shot cinematic production breakdown.

CRITICAL NON-NEGOTIABLE LAWS:
1. GOSPEL FAITHFULNESS: Do NOT invent new characters, do NOT change names, do NOT change relationships, locations, plot events, sequence, or the ending. The source story is 100% sacred.
2. NATURAL SCENE LOAD & PACING: Break the story down into a natural sequence of 1 to 80 scenes paced specifically for a {target_duration} video. Shorter targets produce compact scenes; longer targets produce granular shots. NEVER artificially pad or stretch scenes with empty fluff.
3. TIGHT & GRIPPING DIALOGUE: Spoken lines and narration must be punchy, emotional, and authentic. No robotic or filler lines.
4. VISUAL LOOK LOCK: Every image prompt must strictly adhere to the chosen Cinematic Filter and Art Style.
5. IMAGE PROMPTS (MIDJOURNEY / FLUX): Each prompt must be ultra-descriptive, specifying shot size (Wide shot, Medium shot, Close-up), camera lens (35mm, 50mm, 85mm), lighting, characters present with facial consistency and clothing, exact physical action, and render style. No text, captions, or watermarks.
6. VIDEO MOTION PROMPTS: Provide precise camera movement (e.g. slow push in, low-angle gimbal track, crane tilt) and subject action for video AI (Runway Gen-3, Luma Dream Machine, Pika).

CONFIGURATION:
- Tone / Genre: {genre} (Pacing and intensity only)
- Cinematic Filter: {cinematic_filter} ({filter_treatment})
- Art Style: {art_style} ({art_treatment})
- Voice / Accent Flavor: {voice_accent} ({voice_treatment})
- Target Runtime / Scope: {target_duration}
- Delivery Format: {delivery_format} ({delivery_treatment})

OUTPUT SCHEMA: Return ONLY valid JSON with this exact structure:
{{
    "title": "Title of the Story",
    "logline": "Compelling 1-sentence logline summarizing the source story",
    "total_scenes": 24,
    "genre": "{genre}",
    "cinematic_filter": "{cinematic_filter}",
    "art_style": "{art_style}",
    "voice_accent": "{voice_accent}",
    "delivery_format": "{delivery_format}",
    "characters": [
        {{
            "name": "Character Name",
            "role": "Role (e.g. Protagonist / Antagonist / Mentor)",
            "visual_description": "Precise facial features, skin tone, hair, signature wardrobe for prompt consistency"
        }}
    ],
    "scenes": [
        {{
            "scene_number": 1,
            "scene_title": "Descriptive Scene Heading",
            "setting": "Interior/Exterior location and time of day",
            "dialogue_or_narration": "Exact spoken line or narration excerpt for this shot",
            "image_prompt": "Ultra-detailed Midjourney/Flux prompt with camera angle, lighting, character details, action, style. No captions, no text, no split screens.",
            "video_prompt": "Cinematic camera movement and character action prompt for Runway/Luma/Pika."
        }}
    ]
}}
"""

    prompt = f"""CREATOR'S SOURCE STORY:
{story_text}

Adapt this exact story into chronological scene-by-scene prompts following all the rules above."""

    raw_response = generate_ai_completion(
        preferred_model=model,
        system_instruction=system_instruction,
        prompt=prompt,
        temperature=0.6,
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
3. SCENE BREAKDOWN FOR {target_duration}:
   - For Short (3–5 Mins): 10 to 14 scenes.
   - For Standard (8–15 Mins): 18 to 26 scenes.
   - For Deep Dive (30–60 Mins): 28 to 40 scenes.
   - For Feature Movie (1–2+ Hours): 45 to 60 scenes.
4. MIDJOURNEY / FLUX IMAGE PROMPTS: Every scene prompt must be completely standalone. Include shot angle (Wide shot, Close-up, Over-the-shoulder), lighting, characters present with clothes and facial expressions, action, and the art style: {art_treatment}. Strictly NO text, captions, logos, or split screens.
5. VIDEO MOTION PROMPTS: Specify exact camera movements (slow push-in, low-angle track, drone orbit, subtle handheld shake) and subject movement for Runway Gen-3 / Luma Dream Machine.
6. 3 HIGH-CTR THUMBNAIL CONCEPTS: Provide 3 high-contrast, clickable thumbnail prompts with 3-5 bold punchy overlay words.
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
    "characters": [
        {{
            "name": "Character Name",
            "role": "Role (e.g. Lead Protagonist, Antagonist, Loyal Friend)",
            "visual_description": "Detailed description of their face, skin tone, hair, and clothing for visual consistency"
        }}
    ],
    "scenes": [
        {{
            "scene_number": 1,
            "scene_title": "Descriptive Scene Heading",
            "setting": "INT. or EXT. Location - Time of Day",
            "dialogue_or_narration": "Spoken voiceover or character dialogue for this scene",
            "image_prompt": "Ultra-detailed Midjourney/Flux prompt with camera lens, lighting, character details, action, style",
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


