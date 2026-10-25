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
    "gemini-3.8-flash": "Gemini 3.8 Flash (Cinematic Pacing & Fast)",
    "gemini-3.5-flash": "Gemini 3.5 Flash (Ultra-Stable)",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite (Fast)",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro (BYOK High-Tier)",
    "chatgpt-4o": "ChatGPT (GPT-4o) [Coming Soon 🔒]",
    "claude-3-7-sonnet": "Claude 3.7 Sonnet [Coming Soon 🔒]"
}


DEFAULT_MODEL = "gemini-3.8-flash"

# Fallback chain excluding Pro to prevent free-tier 429 quota limits
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

async def generate_ten_concepts(source_title: str, source_context: str, culture: str = "Universal", visual_style: str = "Stylised 3D", genre: str = "Action Thriller", lead_character: dict = None, user_api_key: str = None, model_name: str = None) -> list:
    """
    Step 1 of WP StoryCraft:
    Generates 10 distinct, high-CTR, original YouTube story concepts based on the source.
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL
    client = get_client(user_api_key)

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
        genre_spec = "- Genre / Narrative Mode: AUTO-DETECT / ADAPTIVE. Deeply examine the user's source input. If it describes a personal life experience, true memoir, career journey, or real-life storytime, preserve authentic emotional vulnerability, personal stakes, and relatability—do NOT force synthetic Hollywood tropes. If it describes fiction or a cinematic premise, dynamically apply the most compelling dramatic genre."
    elif any(k in genre_lower for k in ["personal", "memoir", "true life", "life", "storytime", "biograph", "founder", "documentary", "slice of life", "real"]):
        genre_spec = f"- Genre / Narrative Mode: {genre} (REAL-LIFE / PERSONAL MEMOIR). Focus on authentic human vulnerability, pivotal personal decisions, relatable emotional struggles, hard-won lessons, and genuine stakes rather than forced Hollywood fantasy tropes."
    else:
        genre_spec = f"- Genre: {genre}"

    system_instruction = f"""
You are the Executive Showrunner at WP Studio, engineering viral YouTube Automation story concepts.
Analyze the provided source material and generate 10 DISTINCT, ORIGINAL, HIGH-CTR concepts.
Evaluate all 10 concepts and choose the SINGLE BEST ONE that will perform best on YouTube (highest curiosity gap, CTR, and watch-time retention).

CREATIVE DIRECTION:
- Culture Anchor: {culture}
- Visual Style: {visual_style}
{genre_spec}
{char_clause}
RULES FOR YOUTUBE AUTOMATION VIRALITY:
1. Each concept must have a 0-5s curiosity hook that makes viewers stop scrolling.
2. Provide a unique angle/twist on the original source so it is completely fresh and not a duplicate.
3. Highlight the viral trigger (why faceless channel audiences will click and watch to completion).
4. Identify which concept is the #1 Top Recommendation and provide the concise strategic reason why.

Return JSON matching this exact schema:
{{
    "recommended_concept_id": 1,
    "recommendation_reason": "Clear explanation of why this concept will perform best on YouTube, hook retention, and emotional viral trigger.",
    "concepts": [
        {{
            "id": 1,
            "title": "High CTR Click-Worthy Title",
            "hook": "Irresistible first 5 seconds spoken hook",
            "premise": "2-sentence synopsis and narrative twist",
            "viral_trigger": "Psychological curiosity trigger that hooks YouTube audiences"
        }}
    ]
}}
"""

    prompt = f"SOURCE TITLE: {source_title}\n\nSOURCE MATERIAL / TRANSCRIPT CONTEXT:\n{source_context[:6000]}\n\nGenerate exactly 10 distinct viral concepts and select the top recommended one."

    response = generate_with_fallback(
        client=client,
        preferred_model=model,
        contents=prompt,
        config={
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "temperature": 0.8
        },
        user_api_key=user_api_key
    )
    data = clean_json_loads(response.text)
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

async def generate_full_story_package(concept: dict, culture: str = "Universal", visual_style: str = "Stylised 3D", genre: str = "Action Thriller", delivery_format: str = "Dialogue / Narrative", lead_character: dict = None, length_tier: str = "Short", timezone: str = "Africa/Lagos", user_api_key: str = None, model_name: str = None) -> dict:
    """
    Step 2 of WP StoryCraft:
    Generates the complete Story Bible + Scene Prompts Blueprint up to the chosen length ceiling.
    - Short: 15-30 scenes (ceiling 40)
    - Medium: 45-75 scenes (ceiling 120)
    - Long: 90-150 scenes (ceiling 250)
    """
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL
    client = get_client(user_api_key)

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
    "title": "Final YouTube Video Title",
    "genre": "{genre}",
    "delivery_format": "{delivery_format}",
    "logline": "One-sentence high-stakes quotation logline",
    "hook": "0-5s spoken hook line",
    "theme_and_takeaway": "Core moral and psychological theme",
    "synopsis": "Full narrative story arc synopsis (150-250 words)",
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
    data = clean_json_loads(response.text)
    if isinstance(data, dict):
        data["delivery_format"] = data.get("delivery_format", delivery_format)
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

async def generate_thumbnail_prompts(story_summary, user_api_key=None, model_name=None):
    """Generates 3 viral YouTube thumbnail concepts with high CTR."""
    model = model_name if model_name in AVAILABLE_MODELS else DEFAULT_MODEL
    client = get_client(user_api_key)

    prompt = f"Generate 3 viral, high-CTR YouTube thumbnail concepts with text overlays and Midjourney prompts for this story:\n\n{story_summary}"
    
    response = generate_with_fallback(
        client=client,
        preferred_model=model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
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
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model=flux&nologo=true"
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
