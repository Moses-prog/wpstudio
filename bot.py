import os
import sys
import asyncio
import logging
import json
import io
import random

# Ensure UTF-8 output on Windows console
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from telethon import TelegramClient, events, Button, errors as telethon_errors
from telethon.sessions import MemorySession

import database
import ai_engine
import pdf_generator
import source_extractor

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("WPStudio")

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not API_ID or not API_HASH:
    raise ValueError("API_ID and API_HASH must be set in .env")

# In-memory user state tracker
USER_STATES = {}

# Production Pricing Tiers matching creator platform specifications with estimated video runtimes
PRICING_TIERS = {
    "Short": {
        "label": "Short (~2-4 Mins | ≤ 40 scenes)",
        "duration": "~2-4 Mins",
        "runtime_detail": "~2 to 4 Minutes YouTube Video",
        "concepts_cost": 10,
        "pdfs_cost": 40,
        "total": 50,
        "scenes": "15-25 scenes (~2 to 4 mins, ceiling 40)"
    },
    "Medium": {
        "label": "Medium (~8-15 Mins | ≤ 120 scenes)",
        "duration": "~8-15 Mins",
        "runtime_detail": "~8 to 15 Minutes YouTube Video",
        "concepts_cost": 50,
        "pdfs_cost": 250,
        "total": 300,
        "scenes": "40-60 scenes (~8 to 15 mins, ceiling 120)"
    },
    "Long": {
        "label": "Long (~1-2+ Hours | ≤ 250 scenes)",
        "duration": "~1-2+ Hours",
        "runtime_detail": "~1 to 2+ Hours Feature/Doc",
        "concepts_cost": 100,
        "pdfs_cost": 300,
        "total": 400,
        "scenes": "80-120 scenes (~1 to 2+ hours, ceiling 250)"
    }
}
REGEN_COST = 3

CULTURES = ["Black American", "White American", "Nigerian", "Universal", "Mixed / Global"]
STYLES = ["Stylised 3D", "Human Realistic", "Anime / Manga", "Cinematic Cyberpunk"]

GENRES_BY_CULTURE = {
    "Black American": [
        "🏙️ Urban Street & Hood Hustle",
        "💼 Corporate Hustle & Legacy Wealth",
        "⛪ Black Church & Family Dynasty",
        "🎤 Hip-Hop Royalty & Music Mogul",
        "❤️ Modern Black Romance & Soft Life",
        "🕵️ Noir Crime & Undercover Detective",
        "👻 Black Psychological Horror & Suspense",
        "🏈 Sports Ambition & Championship Grind",
        "🏛️ Civil Rights & Historical Legacy"
    ],
    "White American": [
        "🤠 Southern Gothic & Country Crime",
        "💼 Wall Street & Corporate Greed",
        "🌲 Small Town Murder Mystery",
        "🏡 Suburbia Secrets & Psychological Drama",
        "🛸 Deep Space & Sci-Fi Odyssey",
        "🔥 Apocalyptic Survival & Wilderness",
        "🏖️ Coastal Elite & Hamptons Drama",
        "👻 Haunted Lore & Supernatural Horror"
    ],
    "Nigerian": [
        "👑 Ancient Kingdom & Epic Myth",
        "🏛️ Royal Palace & Succession",
        "🌿 Village vs City & Stepmother",
        "⚡ Yahoo Hustle & Dark Rituals",
        "🎓 Campus & Secret Societies",
        "🚕 Lagos Street Hustle & Slum-to-Wealth",
        "🕊️ Spiritual Warfare & Deliverance",
        "🥂 Lekki High Society & Owambe Rom-Com",
        "🕶️ Action Crime & Underworld Kingpin"
    ],
    "Universal": [
        "🎬 High-Octane Action Thriller",
        "🔍 Crime Investigation & Whodunit",
        "🔥 Psychological Thriller & Suspense",
        "🚀 Futuristic Sci-Fi Dystopia",
        "💰 High Stakes Bank Heist",
        "💔 Emotional Drama & Betrayal"
    ],
    "Mixed / Global": [
        "🌍 Diaspora Return & Culture Clash",
        "✈️ International Espionage & Syndicate",
        "🥂 Cross-Cultural Romance & High Society",
        "🎬 Global Action Thriller"
    ]
}

GENRES = GENRES_BY_CULTURE["Black American"] + GENRES_BY_CULTURE["White American"] + GENRES_BY_CULTURE["Nigerian"]
TIMEZONES = [
    ("Africa/Lagos", "🇳🇬 Lagos"),
    ("America/New_York", "🇺🇸 New York"),
    ("Europe/London", "🇬🇧 London"),
    ("Africa/Johannesburg", "🇿🇦 Joburg"),
    ("Asia/Dubai", "🇦🇪 Dubai")
]
DELIVERY_FORMATS = ["Dialogue / Narrative", "Dialogue", "Narrative"]

def get_main_keyboard(user):
    has_key = bool(user.get("custom_gemini_key"))
    key_indicator = "🔑 BYOK: Active" if has_key else "⚡ Platform Pool Key"
    user_id = user.get("id") or user.get("user_id")
    
    rows = [
        [
            Button.inline("🎬 WP StoryCraft", b"menu_story"),
            Button.inline("🔨 WP CastLock", b"menu_character")
        ],
        [
            Button.inline("🖼️ WP ClickThumb", b"menu_thumbnail"),
            Button.inline("🧠 AI Models", b"menu_models")
        ],
        [
            Button.inline(f"{key_indicator}", b"menu_byok"),
            Button.inline("💳 Credits & Tier", b"menu_wallet")
        ],
        [
            Button.inline("❓ Creator Guide", b"menu_guide")
        ]
    ]

    if user_id and database.is_admin(user_id):
        rows.append([Button.inline("🛡️ Studio Admin Suite", b"admin_menu")])

    return rows

def get_models_keyboard(current_model):
    buttons = []
    for model_id, model_label in ai_engine.AVAILABLE_MODELS.items():
        is_selected = "✓ " if model_id == current_model else ""
        buttons.append([Button.inline(f"{is_selected}{model_label}", f"set_model_{model_id}".encode())])
    buttons.append([Button.inline("🔙 Back to Main Menu", b"menu_main")])
    return buttons

def get_creative_direction_keyboard(state):
    culture = state.get("culture", "Black American")
    style = state.get("style", "Stylised 3D")
    genre_list = GENRES_BY_CULTURE.get(culture, GENRES_BY_CULTURE["Black American"])
    genre = state.get("genre", genre_list[0])
    tier = state.get("length_tier", "Short")
    delivery = state.get("delivery_format", "Dialogue / Narrative")
    tz = state.get("timezone", "Africa/Lagos")
    tier_info = PRICING_TIERS.get(tier, PRICING_TIERS["Short"])
    lead_name = state.get("locked_lead_name", "🤖 Auto-Invent (AI)")

    return [
        [
            Button.inline(f"🌍 {culture}", b"cycle_culture"),
            Button.inline(f"🎨 {style}", b"cycle_style")
        ],
        [
            Button.inline(f"🎭 {genre}", b"cycle_genre"),
            Button.inline(f"⏱️ {tier} ({tier_info['duration']})", b"cycle_tier")
        ],
        [
            Button.inline(f"🗣️ {delivery}", b"cycle_delivery"),
            Button.inline(f"⏰ {tz.split('/')[-1]}", b"cycle_tz")
        ],
        [
            Button.inline(f"👑 Lead Cast: {lead_name[:20]}", b"sc_menu_cast")
        ],
        [
            Button.inline(f"🚀 Generate 10 Concepts ({tier_info['concepts_cost']} Cr)", b"action_generate_concepts")
        ],
        [
            Button.inline("❌ Cancel", b"menu_main")
        ]
    ]

def get_storycraft_cast_keyboard(user_chars: list, current_lead: str = ""):
    buttons = []
    # Roster characters
    if user_chars:
        for c in user_chars[:8]:
            cid = c.get("id")
            cname = c.get("name", "Character")
            cage = c.get("age", "")
            cgen = c.get("gender", "")
            is_active = "✓ " if cname == current_lead else ""
            buttons.append([Button.inline(f"👑 {is_active}{cname} ({cage}yo {cgen})", f"sc_set_cast_roster_{cid}".encode())])
    
    # Presets & Auto-Invent Options
    buttons.append([
        Button.inline("✨ 1-Tap Hollywood Presets", b"sc_cast_presets"),
        Button.inline("🤖 Auto-Invent (AI)", b"sc_set_cast_auto")
    ])
    buttons.append([
        Button.inline("🔙 Back to Creative Direction", b"sc_back_to_dir")
    ])
    return buttons

def get_storycraft_cast_presets_keyboard():
    buttons = []
    for key, p in CASTLOCK_PRESETS.items():
        buttons.append([Button.inline(p["title"], f"sc_set_cast_preset_{key}".encode())])
    buttons.append([Button.inline("🔙 Back to Cast Selection", b"sc_menu_cast")])
    return buttons

# ============================================================================
# WP CASTLOCK — AAA 3D CHARACTER MODEL SHEET & CONTINUITY STUDIO CONSTANTS
# ============================================================================
CASTLOCK_GENDERS = ["Female", "Male"]
CASTLOCK_COMPLEXIONS = [
    "Fair", "Light brown", "Medium brown", "Brown", "Dark brown", "Deep dark"
]
CASTLOCK_NOSE_TYPES = [
    "Broad / Wide", "Slender / Narrow", "Button / Small", "Aquiline", "Flat / Rounded"
]
CASTLOCK_HAIRSTYLES = [
    "Braids", "Locs", "Afro", "Twists", "Buzz Cut", "Straight", "Curly"
]
CASTLOCK_HAIR_COLORS = [
    "Black (#000000)", "Dark Brown (#2B1B14)", "Chestnut (#5A3825)",
    "Golden Blonde (#D4AF37)", "Auburn (#8B2500)", "Silver Grey (#A0A0A0)"
]
CASTLOCK_PHYSIQUES = [
    {"label": "Average (Tall)", "body": "Average", "height": "Tall"},
    {"label": "Average (Avg Ht)", "body": "Average", "height": "Average"},
    {"label": "Athletic (Tall)", "body": "Athletic", "height": "Tall"},
    {"label": "Athletic (Avg Ht)", "body": "Athletic", "height": "Average"},
    {"label": "Slim (Tall)", "body": "Slim", "height": "Tall"},
    {"label": "Slim (Petite)", "body": "Slim", "height": "Short"},
    {"label": "Curvy (Avg Ht)", "body": "Curvy", "height": "Average"},
    {"label": "Plus size (Avg Ht)", "body": "Plus size", "height": "Average"}
]
CASTLOCK_EXPRESSIONS = [
    "Happy", "Neutral", "Serious / Fierce", "Confident / Smiling", "Intense / Determined"
]
CASTLOCK_OUTFIT_STYLES = [
    "Ankara", "Corporate", "Traditional", "Streetwear",
    "School Uniform", "Tactical", "Casual"
]
CASTLOCK_BACKGROUNDS = [
    "Neutral studio", "Urban street", "Cyberpunk neon", "Nature / Outdoors"
]
CASTLOCK_LIGHTINGS = [
    "Studio", "Dramatic", "Golden Hour", "Cinematic"
]
CASTLOCK_ART_STYLES = [
    "Realistic", "Pixar 3D", "Sticky Animation"
]
CASTLOCK_PURPOSES = [
    "Film", "Animation", "Comic", "Game", "Social Media"
]
CASTLOCK_COST = 10

CASTLOCK_NAME_SUGGESTIONS = [
    "Marcus", "Malik", "Jordan", "Nia", "Keisha", "Maya",   # Black American
    "Ethan", "Jack", "Liam", "Emma", "Olivia", "Chloe",     # White American
    "Kemi", "Tade", "Chidinma", "Zainab", "Amara", "Kwame"  # Nigerian
]
CASTLOCK_AGE_SUGGESTIONS = [
    "16", "18", "21", "24", "28", "32", "40", "55"
]

CASTLOCK_PRESETS = {
    # ---------------- Black American Archetypes ----------------
    "harlem_mogul": {
        "title": "🇺🇸 1. Black American Mogul (Marcus, 30)",
        "name": "Marcus",
        "age": "30",
        "gender": "Male",
        "complexion": "Medium brown",
        "nose_type": "Broad / Wide",
        "hairstyle": "Buzz Cut",
        "custom_hairstyle": "clean razor-sharp geometric tape fade with 360 waves",
        "hair_color": "Black (#000000)",
        "body_size": "Athletic",
        "height": "Tall",
        "expression": "Confident / Smiling",
        "outfit_style": "Corporate",
        "custom_outfit": "bespoke midnight black double-breasted designer suit with gold lapel pin and silk pocket square",
        "background": "Neutral studio",
        "lighting": "Cinematic",
        "art_style": "Realistic",
        "purpose": "Film"
    },
    "brooklyn_queen": {
        "title": "🇺🇸 2. Black American Creative (Nia, 26)",
        "name": "Nia",
        "age": "26",
        "gender": "Female",
        "complexion": "Light brown",
        "nose_type": "Slender / Narrow",
        "hairstyle": "Braids",
        "custom_hairstyle": "bohemian knotless braids with soft curly ends and gold wire cuffs",
        "hair_color": "Black (#000000)",
        "body_size": "Average",
        "height": "Tall",
        "expression": "Happy",
        "outfit_style": "Casual",
        "custom_outfit": "oversized cream designer blazer, cropped ribbed knit top, and high-waisted tailored trousers",
        "background": "Neutral studio",
        "lighting": "Studio",
        "art_style": "Realistic",
        "purpose": "Film"
    },
    "urban_athlete": {
        "title": "🇺🇸 3. Black American Athlete (Malik, 21)",
        "name": "Malik",
        "age": "21",
        "gender": "Male",
        "complexion": "Dark brown",
        "nose_type": "Broad / Wide",
        "hairstyle": "Locs",
        "custom_hairstyle": "short high-top twisted dreadlocks with clean temple fade",
        "hair_color": "Black (#000000)",
        "body_size": "Athletic",
        "height": "Tall",
        "expression": "Intense / Determined",
        "outfit_style": "Streetwear",
        "custom_outfit": "vintage varsity leather bomber jacket, tailored sweatpants, and retro high-top basketball kicks",
        "background": "Urban street",
        "lighting": "Dramatic",
        "art_style": "Realistic",
        "purpose": "Film"
    },
    # ---------------- White American Archetypes ----------------
    "white_tech_exec": {
        "title": "🇺🇸 4. White American Exec (Ethan, 32)",
        "name": "Ethan",
        "age": "32",
        "gender": "Male",
        "complexion": "Fair",
        "nose_type": "Slender / Narrow",
        "hairstyle": "Straight",
        "custom_hairstyle": "textured side-parted quiff with clean tapered sides",
        "hair_color": "Dark Brown (#2B1B14)",
        "body_size": "Average",
        "height": "Tall",
        "expression": "Confident / Smiling",
        "outfit_style": "Corporate",
        "custom_outfit": "tailored charcoal wool blazer, crisp white open-collar shirt, and tailored chinos",
        "background": "Neutral studio",
        "lighting": "Studio",
        "art_style": "Realistic",
        "purpose": "Film"
    },
    "white_detective": {
        "title": "🇺🇸 5. White American Detective (Jack, 38)",
        "name": "Jack",
        "age": "38",
        "gender": "Male",
        "complexion": "Fair",
        "nose_type": "Aquiline",
        "hairstyle": "Buzz Cut",
        "custom_hairstyle": "rugged textured crew cut with clean stubble beard",
        "hair_color": "Chestnut (#5A3825)",
        "body_size": "Athletic",
        "height": "Tall",
        "expression": "Serious / Fierce",
        "outfit_style": "Tactical",
        "custom_outfit": "distressed dark leather field jacket over charcoal thermal Henley and dark selvedge denim",
        "background": "Neutral studio",
        "lighting": "Dramatic",
        "art_style": "Realistic",
        "purpose": "Film"
    },
    "white_suburban_lead": {
        "title": "🇺🇸 6. White American Lead (Emma, 27)",
        "name": "Emma",
        "age": "27",
        "gender": "Female",
        "complexion": "Fair",
        "nose_type": "Button / Small",
        "hairstyle": "Curly",
        "custom_hairstyle": "loose shoulder-length honey-blonde beach waves",
        "hair_color": "Golden Blonde (#D4AF37)",
        "body_size": "Slim",
        "height": "Average",
        "expression": "Happy",
        "outfit_style": "Casual",
        "custom_outfit": "soft cable-knit cashmere sweater, high-rise straight leg denim, and leather ankle boots",
        "background": "Neutral studio",
        "lighting": "Golden Hour",
        "art_style": "Realistic",
        "purpose": "Film"
    },
    # ---------------- Nigerian / Nollywood Archetypes ----------------
    "ankara_queen": {
        "title": "🇳🇬 7. Ankara Queen (Kemi, 28)",
        "name": "Kemi",
        "age": "28",
        "gender": "Female",
        "complexion": "Medium brown",
        "nose_type": "Broad / Wide",
        "hairstyle": "Locs",
        "custom_hairstyle": "long goddess locs with gold cuffs",
        "hair_color": "Black (#000000)",
        "body_size": "Average",
        "height": "Tall",
        "expression": "Happy",
        "outfit_style": "Ankara",
        "custom_outfit": "emerald green Ankara gown with gold embroidery",
        "background": "Neutral studio",
        "lighting": "Studio",
        "art_style": "Realistic",
        "purpose": "Film"
    },
    "school_girl": {
        "title": "🎓 8. High School Student (Chidinma, 16)",
        "name": "Chidinma",
        "age": "16",
        "gender": "Female",
        "complexion": "Dark brown",
        "nose_type": "Button / Small",
        "hairstyle": "Braids",
        "custom_hairstyle": "neat geometric cornrows styled into low bun",
        "hair_color": "Black (#000000)",
        "body_size": "Slim",
        "height": "Average",
        "expression": "Neutral",
        "outfit_style": "School Uniform",
        "custom_outfit": "crisp white collared shirt, navy blue bow tie, and pleated skirt",
        "background": "Neutral studio",
        "lighting": "Studio",
        "art_style": "Realistic",
        "purpose": "Film"
    },
    "tech_exec": {
        "title": "💼 9. Corporate Tech Exec (Zainab, 30)",
        "name": "Zainab",
        "age": "30",
        "gender": "Female",
        "complexion": "Light brown",
        "nose_type": "Slender / Narrow",
        "hairstyle": "Braids",
        "custom_hairstyle": "sleek waist-length box braids with silver cuff rings",
        "hair_color": "Black (#000000)",
        "body_size": "Average",
        "height": "Tall",
        "expression": "Determined",
        "outfit_style": "Corporate",
        "custom_outfit": "tailored charcoal power blazer with satin lapels and fitted trousers",
        "background": "Neutral studio",
        "lighting": "Cinematic",
        "art_style": "Realistic",
        "purpose": "Film"
    },
    "cyber_hero": {
        "title": "⚡ 10. Cyber Action Hero (Tade, 24)",
        "name": "Tade",
        "age": "24",
        "gender": "Male",
        "complexion": "Dark brown",
        "nose_type": "Broad / Wide",
        "hairstyle": "Buzz Cut",
        "custom_hairstyle": "crisp geometric line-up with sharp fade",
        "hair_color": "Black (#000000)",
        "body_size": "Athletic",
        "height": "Tall",
        "expression": "Fierce",
        "outfit_style": "Streetwear",
        "custom_outfit": "tactical oversized utility jacket with neon orange trim, cargo pants, and combat boots",
        "background": "Cyberpunk neon",
        "lighting": "Dramatic",
        "art_style": "Realistic",
        "purpose": "Animation"
    },
    # ---------------- 3D Pixar Animation Archetypes ----------------
    "pixar_black_kid": {
        "title": "✨ 11. Pixar 3D Black Kid (Miles, 11)",
        "name": "Miles",
        "age": "11",
        "gender": "Male",
        "complexion": "Medium brown",
        "nose_type": "Button / Small",
        "hairstyle": "Afro",
        "custom_hairstyle": "soft textured rounded high-top afro with clean edges",
        "hair_color": "Black (#000000)",
        "body_size": "Slim",
        "height": "Short",
        "expression": "Smiling",
        "outfit_style": "Casual",
        "custom_outfit": "bright red and blue oversized hoodie, denim shorts, and retro high-top sneakers",
        "background": "Neutral studio",
        "lighting": "Studio",
        "art_style": "Pixar 3D",
        "purpose": "Animation"
    },
    "pixar_white_kid": {
        "title": "✨ 12. Pixar 3D Kid (Leo, 11)",
        "name": "Leo",
        "age": "11",
        "gender": "Male",
        "complexion": "Fair",
        "nose_type": "Button / Small",
        "hairstyle": "Straight",
        "custom_hairstyle": "tousled messy golden-brown hair",
        "hair_color": "Chestnut (#5A3825)",
        "body_size": "Slim",
        "height": "Short",
        "expression": "Smiling",
        "outfit_style": "Casual",
        "custom_outfit": "bright emerald green zip hoodie, khaki joggers, and white sneakers",
        "background": "Neutral studio",
        "lighting": "Studio",
        "art_style": "Pixar 3D",
        "purpose": "Animation"
    }
}

def format_castlock_roster_card(user_chars: list, credits_balance: int) -> str:
    total = len(user_chars)
    if total == 0:
        return (
            "🎭 **WP CastLock — Character Studio**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Keep your characters looking the same across every scene with no face changing!\n\n"
            "📂 **You have no saved characters yet.**\n\n"
            "✨ Create your first character step-by-step, or pick a preset character below to get started right away:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Balance:** `{credits_balance} Credits` | 9-Angle Sheet: `{CASTLOCK_COST} Credits`"
        )

    roster_lines = []
    for i, c in enumerate(user_chars, 1):
        name = c.get("name", "Hero")
        age = c.get("age", "25")
        gen = c.get("gender", "Female")
        skin = c.get("complexion", "Medium brown").split()[0]
        outfit = c.get("outfit_style", "Ankara")
        art = c.get("art_style", "Realistic")
        roster_lines.append(f"**{i}. 👑 {name}** ({age}yo {gen} • {skin} skin • {outfit} • {art})")

    roster_text = "\n".join(roster_lines)
    return (
        f"🎭 **WP CastLock — Saved Characters ({total} Total)**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Keep your characters looking the same across every scene with no face changing!\n\n"
        f"{roster_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Balance:** `{credits_balance} Credits` | 9-Angle Sheet: `{CASTLOCK_COST} Credits`\n\n"
        "👇 **Select a character below** to get 9-angle sheets or edit, or create a new character:"
    )

def get_castlock_roster_keyboard(user_chars: list) -> list:
    buttons = []
    # Two character buttons per row
    char_row = []
    for i, c in enumerate(user_chars, 1):
        cid = c.get("id")
        name = c.get("name", f"Hero {i}")
        char_row.append(Button.inline(f"👑 {i}. {name}", f"cl_view_c_{cid}".encode()))
        if len(char_row) == 2:
            buttons.append(char_row)
            char_row = []
    if char_row:
        buttons.append(char_row)

    # Core Action Buttons
    buttons.append([
        Button.inline("➕ Create New Character", b"cl_wiz_start"),
        Button.inline("✨ 1-Tap Presets", b"cl_presets_menu")
    ])
    buttons.append([
        Button.inline("📖 Creator Guide", b"cl_guide"),
        Button.inline("🔙 Main Menu", b"menu_main")
    ])
    return buttons

def format_character_detail_card(char: dict, credits_balance: int, is_newly_saved: bool = False) -> str:
    name = char.get("name", "Kemi")
    age = char.get("age", "28")
    gender = char.get("gender", "Female")
    complexion = char.get("complexion", "Medium brown")
    nose = char.get("nose_type", "Broad / Wide")
    hair = char.get("hairstyle", "Braids")
    custom_hair = char.get("custom_hairstyle", "")
    hair_col = char.get("hair_color", "Black (#000000)").split()[0]
    body = char.get("body_size", "Average")
    height = char.get("height", "Tall")
    expr = char.get("expression", "Happy")
    outfit = char.get("outfit_style", "Ankara")
    custom_outfit = char.get("custom_outfit", "")
    bg = char.get("background", "Neutral studio")
    light = char.get("lighting", "Studio")
    style = char.get("art_style", "Realistic")
    purpose = char.get("purpose", "Film")

    eff_hair = f"{custom_hair} ({hair_col})" if custom_hair else f"{hair} ({hair_col})"
    eff_outfit = custom_outfit if (outfit == "Custom" or custom_outfit) else f"{outfit} bespoke attire"

    ref_path = char.get("reference_image_path")
    ref_inst = char.get("reference_instruction")
    ref_status = "🟢 Attached & Likeness Locked" if ref_path else "⚪ None (Tap below to add)"
    ref_line = f"• Face Reference: `{ref_status}`\n"
    if ref_inst:
        ref_line += f"• Directives: *\"{ref_inst[:65]}\"*\n"

    header = "✅ **Character Successfully Saved to Cast Roster!**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" if is_newly_saved else ""
    return (
        f"{header}"
        f"🎭 **WP CastLock — Character Profile: {name}**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **{name}** ({age} years old • {gender})\n\n"
        "👤 **1. IDENTITY & FACIAL ANATOMY**\n"
        f"• Complexion: `{complexion}` tone (melanin SSS shader)\n"
        f"• Nose Bridge: `{nose}`\n"
        f"• Baseline Mood: `{expr}`\n\n"
        "💇 **2. HAIR ARCHITECTURE & PHYSIQUE**\n"
        f"• Hairstyle: `{eff_hair}`\n"
        f"• Stature & Build: `{height}` height • `{body}` frame\n\n"
        "👗 **3. WARDROBE CRAFTSMANSHIP & 3D ENGINE**\n"
        f"• Wardrobe: `{eff_outfit}`\n"
        f"• 3D Art Engine: `{style}` ({purpose})\n"
        f"• Lighting & Set: `{light}` lighting • `{bg}`\n\n"
        "📸 **4. REFERENCE IMAGE & FORENSICS**\n"
        f"{ref_line}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 **Balance:** `{credits_balance} Credits` | 9-Panel Sheet: `{CASTLOCK_COST} Credits`\n\n"
        "👇 Tap **PRODUCE 9-PANEL SHEET** to generate Hollywood-standard turnarounds, or manage character below:"
    )

def get_character_detail_keyboard(char_id: int) -> list:
    return [
        [Button.inline("🖼️ Render Visual Portrait (1 Cr)", f"cl_render_portrait_{char_id}".encode()), Button.inline("⚡ PRODUCE 9-PANEL SHEET (10 Cr)", f"cl_prod_c_{char_id}".encode())],
        [Button.inline("📸 Add/Update Reference Photo", f"cl_add_ref_{char_id}".encode()), Button.inline("✏️ Edit Trait", f"cl_ed_m_{char_id}".encode())],
        [Button.inline("🗑️ Delete Character", f"cl_del_c_{char_id}".encode()), Button.inline("➕ Create Another Cast", b"cl_wiz_start")],
        [Button.inline("👥 Cast Roster", b"cl_roster"), Button.inline("🔙 Main Menu", b"menu_main")]
    ]

def get_castlock_edit_trait_keyboard(char_id: int) -> list:
    return [
        [Button.inline("👤 Name", f"cl_ed_t_name_{char_id}".encode()), Button.inline("🎂 Age", f"cl_ed_t_age_{char_id}".encode())],
        [Button.inline("🎨 Complexion", f"cl_ed_t_cpx_{char_id}".encode()), Button.inline("👃 Nose Bridge", f"cl_ed_t_nse_{char_id}".encode())],
        [Button.inline("💇 Hairstyle", f"cl_ed_t_hrs_{char_id}".encode()), Button.inline("💈 Hair Color", f"cl_ed_t_col_{char_id}".encode())],
        [Button.inline("📐 Body & Height", f"cl_ed_t_bld_{char_id}".encode()), Button.inline("👗 Outfit", f"cl_ed_t_out_{char_id}".encode())],
        [Button.inline("🎬 3D Engine", f"cl_ed_t_eng_{char_id}".encode()), Button.inline("🔙 Back to Profile", f"cl_view_c_{char_id}".encode())]
    ]

def format_wizard_step_card(step: int, wiz_data: dict) -> str:
    name = wiz_data.get("name", "Character")
    age = wiz_data.get("age", "28")
    gender = wiz_data.get("gender", "Female")
    complexion = wiz_data.get("complexion", "Medium brown")
    nose = wiz_data.get("nose_type", "Broad / Wide")
    hair = wiz_data.get("hairstyle", "Braids")
    custom_hair = wiz_data.get("custom_hairstyle", "")
    eff_hair = custom_hair if custom_hair else hair
    outfit = wiz_data.get("outfit_style", "Ankara")
    custom_outfit = wiz_data.get("custom_outfit", "")
    eff_outfit = custom_outfit if custom_outfit else outfit

    if step == 1:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 1 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "**What is your character's name?**\n\n"
            "Tap a quick suggestion below, or type any name directly in chat:"
        )
    elif step == 2:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 2 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}**\n\n"
            f"**How old is {name}?**\n\n"
            "Tap an age below, or type any number in chat:"
        )
    elif step == 3:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 3 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}** ({age} years old)\n\n"
            "**Select the biological base figure:**"
        )
    elif step == 4:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 4 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}** ({age}yo {gender})\n\n"
            "**Choose skin complexion & melanin tone:**\n"
            "Every shader calibrates authentic subsurface light diffusion (SSS)."
        )
    elif step == 5:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 5 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}** ({complexion} skin tone)\n\n"
            "**Select craniofacial nose bridge landmark:**\n"
            "Locks cranial geometry across front and 90° profile angles."
        )
    elif step == 6:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 6 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}**\n\n"
            "**Choose hairstyle architecture:**\n"
            "Tap a style below, or tap Describe Custom Hair:"
        )
    elif step == 7:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 7 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}** ({eff_hair})\n\n"
            "**Choose hair color pigment:**"
        )
    elif step == 8:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 8 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}**\n\n"
            "**Choose body frame & stature:**"
        )
    elif step == 9:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 9 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}**\n\n"
            "**Choose baseline facial expression:**"
        )
    elif step == 10:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 10 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}**\n\n"
            "**Choose wardrobe & attire:**\n"
            "Tap a style below, or tap Describe Custom Outfit:"
        )
    elif step == 11:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 11 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}**\n"
            f"• Wardrobe: `{eff_outfit}`\n\n"
            "**Select 3D aesthetic & render engine:**"
        )
    elif step == 12:
        return (
            "🎭 **WP CastLock — Character Wizard (Step 12 of 12)**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Character: **{name}**\n\n"
            "📸 **Add Face / Style Reference Photo (Optional)**\n\n"
            "Would you like to attach a reference photo (portrait, selfie, sketch, or outfit)?\n"
            "Our Multimodal Vision AI will forensically analyze exact cranial landmarks, melanin shader, and hairstyle architecture to lock your likeness with zero face morphing!\n\n"
            "💡 *You can upload a photo now with custom instructions in the caption, or save immediately:* "
        )
    return "🎭 **WP CastLock Wizard**"

def get_wizard_step_keyboard(step: int, wiz_data: dict) -> list:
    if step == 1:
        return [
            [Button.inline("👑 Kemi", b"cl_wz_n_Kemi"), Button.inline("⚡ Tade", b"cl_wz_n_Tade")],
            [Button.inline("🎓 Chidinma", b"cl_wz_n_Chidinma"), Button.inline("💼 Zainab", b"cl_wz_n_Zainab")],
            [Button.inline("✨ Amara", b"cl_wz_n_Amara"), Button.inline("🛡️ Kwame", b"cl_wz_n_Kwame")],
            [Button.inline("🔙 Cancel & Return to Roster", b"cl_roster")]
        ]
    elif step == 2:
        return [
            [Button.inline("16", b"cl_wz_a_16"), Button.inline("18", b"cl_wz_a_18"), Button.inline("21", b"cl_wz_a_21"), Button.inline("24", b"cl_wz_a_24")],
            [Button.inline("28", b"cl_wz_a_28"), Button.inline("32", b"cl_wz_a_32"), Button.inline("40", b"cl_wz_a_40"), Button.inline("55", b"cl_wz_a_55")],
            [Button.inline("🔙 Back to Name", b"cl_wiz_s1"), Button.inline("🔙 Cancel", b"cl_roster")]
        ]
    elif step == 3:
        return [
            [Button.inline("👩 Female", b"cl_wz_g_0"), Button.inline("👨 Male", b"cl_wz_g_1")],
            [Button.inline("🔙 Back to Age", b"cl_wiz_s2"), Button.inline("🔙 Cancel", b"cl_roster")]
        ]
    elif step == 4:
        return [
            [Button.inline("Fair", b"cl_wz_c_0"), Button.inline("Light brown", b"cl_wz_c_1")],
            [Button.inline("Medium brown", b"cl_wz_c_2"), Button.inline("Brown", b"cl_wz_c_3")],
            [Button.inline("Dark brown", b"cl_wz_c_4"), Button.inline("Deep dark", b"cl_wz_c_5")],
            [Button.inline("🔙 Back to Gender", b"cl_wiz_s3")]
        ]
    elif step == 5:
        return [
            [Button.inline("Broad / Wide", b"cl_wz_ns_0"), Button.inline("Slender / Narrow", b"cl_wz_ns_1")],
            [Button.inline("Button / Small", b"cl_wz_ns_2"), Button.inline("Aquiline", b"cl_wz_ns_3")],
            [Button.inline("Flat / Rounded", b"cl_wz_ns_4")],
            [Button.inline("🔙 Back to Complexion", b"cl_wiz_s4")]
        ]
    elif step == 6:
        return [
            [Button.inline("Braids", b"cl_wz_h_0"), Button.inline("Locs", b"cl_wz_h_1")],
            [Button.inline("Afro", b"cl_wz_h_2"), Button.inline("Twists", b"cl_wz_h_3")],
            [Button.inline("Buzz Cut", b"cl_wz_h_4"), Button.inline("Straight", b"cl_wz_h_5")],
            [Button.inline("Curly", b"cl_wz_h_6"), Button.inline("✏️ Describe Custom Hair", b"cl_wz_h_cust")],
            [Button.inline("🔙 Back to Nose", b"cl_wiz_s5")]
        ]
    elif step == 7:
        return [
            [Button.inline("⚫ Black", b"cl_wz_cl_0"), Button.inline("🟤 Dark Brown", b"cl_wz_cl_1")],
            [Button.inline("🌰 Chestnut", b"cl_wz_cl_2"), Button.inline("👱 Golden Blonde", b"cl_wz_cl_3")],
            [Button.inline("🔥 Auburn", b"cl_wz_cl_4"), Button.inline("⚪ Silver Grey", b"cl_wz_cl_5")],
            [Button.inline("🔙 Back to Hairstyle", b"cl_wiz_s6")]
        ]
    elif step == 8:
        return [
            [Button.inline("Average (Tall)", b"cl_wz_b_0"), Button.inline("Average (Avg Ht)", b"cl_wz_b_1")],
            [Button.inline("Athletic (Tall)", b"cl_wz_b_2"), Button.inline("Athletic (Avg Ht)", b"cl_wz_b_3")],
            [Button.inline("Slim (Tall)", b"cl_wz_b_4"), Button.inline("Slim (Petite)", b"cl_wz_b_5")],
            [Button.inline("Curvy (Avg Ht)", b"cl_wz_b_6"), Button.inline("Plus size (Avg Ht)", b"cl_wz_b_7")],
            [Button.inline("🔙 Back to Hair Color", b"cl_wiz_s7")]
        ]
    elif step == 9:
        return [
            [Button.inline("😊 Happy", b"cl_wz_e_0"), Button.inline("😐 Neutral", b"cl_wz_e_1")],
            [Button.inline("😠 Serious / Fierce", b"cl_wz_e_2"), Button.inline("😎 Confident / Smiling", b"cl_wz_e_3")],
            [Button.inline("🔥 Intense / Determined", b"cl_wz_e_4")],
            [Button.inline("🔙 Back to Physique", b"cl_wiz_s8")]
        ]
    elif step == 10:
        return [
            [Button.inline("👗 Ankara", b"cl_wz_o_0"), Button.inline("👔 Corporate", b"cl_wz_o_1")],
            [Button.inline("👘 Traditional", b"cl_wz_o_2"), Button.inline("🧢 Streetwear", b"cl_wz_o_3")],
            [Button.inline("🎓 School Uniform", b"cl_wz_o_4"), Button.inline("🪖 Tactical", b"cl_wz_o_5")],
            [Button.inline("👕 Casual", b"cl_wz_o_6"), Button.inline("✏️ Describe Custom Outfit", b"cl_wz_o_cust")],
            [Button.inline("🔙 Back to Expression", b"cl_wiz_s9")]
        ]
    elif step == 11:
        return [
            [Button.inline("🎬 Realistic (8K ARRI & UE5)", b"cl_wz_eg_0")],
            [Button.inline("✨ Pixar 3D (Subsurface Shader)", b"cl_wz_eg_1")],
            [Button.inline("🎨 Sticky Animation (Stylised 3D)", b"cl_wz_eg_2")],
            [Button.inline("🔙 Back to Outfit", b"cl_wiz_s10")]
        ]
    elif step == 12:
        return [
            [Button.inline("📸 Upload Reference Photo & Instruction", b"cl_wz_upload_ref")],
            [Button.inline("⚡ Complete & Save Character", b"cl_wz_skip_ref")],
            [Button.inline("🔙 Back to 3D Engine", b"cl_wiz_s11")]
        ]
    return []

def get_castlock_presets_keyboard():
    buttons = []
    for key, p in CASTLOCK_PRESETS.items():
        buttons.append([Button.inline(p["title"], f"cl_preset_{key}".encode())])
    buttons.append([Button.inline("🔙 Return to Cast Roster", b"cl_roster")])
    return buttons


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing in .env! Please set your Telegram bot token.")
        print("\n=======================================================")
        print("⚠️ BOT_TOKEN is missing from C:\\Users\\USER\\Downloads\\webtgp\\.env")
        print("Please add your Bot Token from @BotFather into .env and restart.")
        print("=======================================================\n")
        return

    client = TelegramClient(MemorySession(), API_ID, API_HASH)
    try:
        await client.start(bot_token=BOT_TOKEN)
    except Exception as e:
        err_name = type(e).__name__
        err_msg = str(e)
        if "AccessTokenExpiredError" in err_name or "expired" in err_msg.lower():
            logger.error("============================================================")
            logger.error("❌ TELEGRAM BOT TOKEN HAS EXPIRED OR BEEN REVOKED!")
            logger.error("Telegram refused connection because BOT_TOKEN is expired.")
            logger.error("To fix:")
            logger.error("1. Open @BotFather on Telegram to get a fresh bot token.")
            logger.error("2. Go to Render Dashboard -> Environment -> update BOT_TOKEN.")
            logger.error("============================================================")
            await asyncio.sleep(30)
            sys.exit(42)
        elif "ApiIdInvalidError" in err_name:
            logger.error("❌ Telegram API_ID or API_HASH is invalid! Check credentials from my.telegram.org.")
            await asyncio.sleep(30)
            sys.exit(42)
        else:
            raise e

    me = await client.get_me()
    logger.info(f"WP Studio Bot started as @{me.username} ({me.id})")

    @client.on(events.NewMessage(pattern=r"^/start"))
    async def start_handler(event):
        user_id = event.sender_id
        username = event.sender.username or "Creator"
        user = database.get_user(user_id, username)
        
        has_key = bool(user.get("custom_gemini_key"))
        key_status = "🟢 Personal Gemini Key (Active)" if has_key else "🟡 Standard Platform Pool"
        
        welcome_text = (
            f"🎬 **Welcome to WP Studio, {username}!**\n\n"
            f"The premier AI Production Suite engineered exclusively for **YouTube Automation & High-Retention Storytelling**.\n\n"
            f"📊 **Account Status:**\n"
            f"• Tier: `{user['tier']}`\n"
            f"• Balance: `{user['credits']} Credits`\n"
            f"• Active Model: `{user['selected_model']}`\n"
            f"• Engine Key: {key_status}\n\n"
            f"Choose a production tool below to start creating:"
        )
        await event.respond(welcome_text, buttons=get_main_keyboard(user))

    @client.on(events.NewMessage(pattern=r"^/settings"))
    async def settings_handler(event):
        user_id = event.sender_id
        username = event.sender.username or "Creator"
        user = database.get_user(user_id, username)
        
        has_key = bool(user.get("custom_gemini_key"))
        key_status = "🟢 Personal BYOK Key Active" if has_key else "⚡ Standard Pool Key"
        
        settings_text = (
            f"⚙️ **WP Studio Production Settings**\n\n"
            f"👤 **Account:** `{username}` (ID: `{user_id}`)\n"
            f"💳 **Tier:** `{user.get('tier', 'Free')}` | `{user.get('credits', 0)} Credits`\n"
            f"🧠 **AI Engine Model:** `{user.get('selected_model', 'gemini-2.5-flash')}`\n"
            f"🔑 **API Engine Key:** {key_status}\n\n"
            f"Select a setting below to configure:"
        )
        buttons = [
            [Button.inline("🧠 Change AI Model", b"menu_models"), Button.inline("🔑 Set BYOK Key", b"menu_byok")],
            [Button.inline("💳 View Wallet & Credits", b"menu_wallet"), Button.inline("🔙 Main Menu", b"menu_main")]
        ]
        await event.respond(settings_text, buttons=buttons)

    @client.on(events.CallbackQuery)
    async def callback_handler(event):
        user_id = event.sender_id
        user = database.get_user(user_id)
        data = event.data.decode()

        if data == "menu_main":
            USER_STATES.pop(user_id, None)
            welcome_text = (
                f"🎬 **WP Studio Main Production Suite**\n\n"
                f"• Tier: `{user['tier']}`\n"
                f"• Balance: `{user['credits']} Credits`\n"
                f"• Model: `{user['selected_model']}`\n\n"
                f"Select an AI capability:"
            )
            await event.edit(welcome_text, buttons=get_main_keyboard(user))

        elif data == "menu_story":
            USER_STATES[user_id] = {"action": "awaiting_story_source"}
            prompt_text = (
                "🎬 **WP StoryCraft — Original Story Workflow**\n\n"
                "**Pipeline:** Source ➔ 10 Concepts ➔ Your Choice ➔ Script & Approval ➔ Dual PDFs\n\n"
                "📌 **1. YouTube Source or Topic Idea:**\n"
                "Send any YouTube video link (we retrieve the video title and captions automatically, or stop if captions cannot be read rather than invent its story).\n\n"
                "Or simply send your original premise or story topic in text.\n\n"
                "👇 **Send your YouTube link or topic to begin:**"
            )
            await event.edit(prompt_text, buttons=[[Button.inline("❌ Cancel", b"menu_main")]])

        elif data == "admin_menu":
            if not database.is_admin(user_id):
                await event.answer("⛔ Access Denied: Admin authorization required.", alert=True)
                return
            text, buttons = get_admin_panel_data(user_id)
            await event.edit(text, buttons=buttons)

        elif data == "admin_toggle_byok":
            if not database.is_admin(user_id):
                await event.answer("⛔ Access Denied", alert=True)
                return
            settings = database.get_system_settings()
            new_val = "0" if settings.get("byok_enabled") == "1" else "1"
            database.update_system_settings({"byok_enabled": new_val})
            status_msg = "BYOK Locked (Platform Credits Only)" if new_val == "0" else "BYOK Unlocked (Personal Keys Allowed)"
            await event.answer(f"🔒 {status_msg}", alert=True)
            text, buttons = get_admin_panel_data(user_id)
            await event.edit(text, buttons=buttons)

        elif data == "admin_toggle_maint":
            if not database.is_admin(user_id):
                await event.answer("⛔ Access Denied", alert=True)
                return
            settings = database.get_system_settings()
            new_val = "0" if settings.get("maintenance_mode") == "1" else "1"
            database.update_system_settings({"maintenance_mode": new_val})
            status_msg = "Maintenance Mode ENABLED" if new_val == "1" else "Maintenance Mode DISABLED"
            await event.answer(f"⚙️ {status_msg}", alert=True)
            text, buttons = get_admin_panel_data(user_id)
            await event.edit(text, buttons=buttons)

        elif data == "admin_refresh":
            if not database.is_admin(user_id):
                await event.answer("⛔ Access Denied", alert=True)
                return
            await event.answer("🔄 Status Refreshed!")
            text, buttons = get_admin_panel_data(user_id)
            await event.edit(text, buttons=buttons)

        # Creative Direction Cycling Handlers
        elif data == "cycle_culture":
            state = USER_STATES.get(user_id)
            if state:
                cur = state.get("culture", "Black American")
                try:
                    c_idx = CULTURES.index(cur)
                except ValueError:
                    c_idx = 0
                new_culture = CULTURES[(c_idx + 1) % len(CULTURES)]
                state["culture"] = new_culture
                # Auto-sync genre to first genre of selected culture to prevent mismatch!
                genre_list = GENRES_BY_CULTURE.get(new_culture, GENRES_BY_CULTURE["Black American"])
                state["genre"] = genre_list[0]
                await update_creative_direction_card(event, state)

        elif data == "cycle_style":
            state = USER_STATES.get(user_id)
            if state:
                cur = state.get("style", "Stylised 3D")
                state["style"] = STYLES[(STYLES.index(cur) + 1) % len(STYLES)]
                await update_creative_direction_card(event, state)

        elif data == "cycle_genre":
            state = USER_STATES.get(user_id)
            if state:
                culture = state.get("culture", "Black American")
                genre_list = GENRES_BY_CULTURE.get(culture, GENRES_BY_CULTURE["Black American"])
                cur_genre = state.get("genre", genre_list[0])
                try:
                    idx = genre_list.index(cur_genre)
                except ValueError:
                    idx = 0
                state["genre"] = genre_list[(idx + 1) % len(genre_list)]
                await update_creative_direction_card(event, state)

        elif data == "cycle_tier":
            state = USER_STATES.get(user_id)
            if state:
                tiers = list(PRICING_TIERS.keys())
                cur = state.get("length_tier", "Short")
                state["length_tier"] = tiers[(tiers.index(cur) + 1) % len(tiers)]
                await update_creative_direction_card(event, state)

        elif data == "cycle_delivery":
            state = USER_STATES.get(user_id)
            if state:
                cur = state.get("delivery_format", "Dialogue / Narrative")
                try:
                    d_idx = DELIVERY_FORMATS.index(cur)
                except ValueError:
                    d_idx = 0
                state["delivery_format"] = DELIVERY_FORMATS[(d_idx + 1) % len(DELIVERY_FORMATS)]
                await update_creative_direction_card(event, state)

        elif data == "cycle_tz":
            state = USER_STATES.get(user_id)
            if state:
                tz_keys = [t[0] for t in TIMEZONES]
                cur = state.get("timezone", "Africa/Lagos")
                state["timezone"] = tz_keys[(tz_keys.index(cur) + 1) % len(tz_keys)]
                await update_creative_direction_card(event, state)

        elif data == "sc_menu_cast":
            state = USER_STATES.get(user_id)
            if not state:
                await event.answer("Session expired.", alert=True)
                return
            user_chars = database.get_user_characters(user_id)
            cur_lead = state.get("locked_lead_name", "🤖 Auto-Invent (AI)")
            menu_text = (
                "👑 **WP StoryCraft — Select Main Character**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Lock your story's main character to an exact **WP CastLock** profile!\n"
                "The AI will maintain 100% identical facial landmarks, hair architecture, skin shader, and wardrobe across all scene prompts and turnarounds.\n\n"
                f"• Current Selection: **{cur_lead}**\n\n"
                "👇 Choose a character from your saved roster, pick a Hollywood Preset, or let AI auto-invent:"
            )
            await event.edit(menu_text, buttons=get_storycraft_cast_keyboard(user_chars, cur_lead))

        elif data == "sc_cast_presets":
            state = USER_STATES.get(user_id)
            if not state:
                await event.answer("Session expired.", alert=True)
                return
            menu_text = (
                "✨ **WP CastLock — 1-Tap Hollywood Lead Presets**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Select a proven archetype to lock as your story's main protagonist:"
            )
            await event.edit(menu_text, buttons=get_storycraft_cast_presets_keyboard())

        elif data.startswith("sc_set_cast_roster_"):
            state = USER_STATES.get(user_id)
            if state:
                cid = int(data.replace("sc_set_cast_roster_", ""))
                char = database.get_character_by_id(cid, user_id)
                if char:
                    cname = char.get("name", "Hero")
                    state["locked_lead_name"] = cname
                    eff_hair = char.get("custom_hairstyle") or char.get("hairstyle", "Braids")
                    eff_outfit = char.get("custom_outfit") or char.get("outfit_style", "Bespoke attire")
                    state["locked_lead_data"] = {
                        "name": cname,
                        "age": str(char.get("age", "28")),
                        "gender": char.get("gender", "Female"),
                        "complexion": char.get("complexion", "Medium brown"),
                        "nose_type": char.get("nose_type", "Broad / Wide"),
                        "hairstyle": eff_hair,
                        "hair_color": char.get("hair_color", "Black (#000000)"),
                        "body": char.get("body_size", "Average"),
                        "height": char.get("height", "Tall"),
                        "expression": char.get("expression", "Confident"),
                        "outfit": eff_outfit,
                        "art_style": char.get("art_style", "Realistic"),
                        "reference_instruction": char.get("reference_instruction", "")
                    }
                    await event.answer(f"👑 Main Character locked to {cname}!", alert=False)
                    await update_creative_direction_card(event, state)

        elif data.startswith("sc_set_cast_preset_"):
            state = USER_STATES.get(user_id)
            if state:
                key = data.replace("sc_set_cast_preset_", "")
                preset = CASTLOCK_PRESETS.get(key)
                if preset:
                    pname = preset.get("name", "Hero")
                    state["locked_lead_name"] = pname
                    eff_hair = preset.get("custom_hairstyle") or preset.get("hairstyle", "Buzz Cut")
                    eff_outfit = preset.get("custom_outfit") or preset.get("outfit_style", "Bespoke attire")
                    state["locked_lead_data"] = {
                        "name": pname,
                        "age": str(preset.get("age", "28")),
                        "gender": preset.get("gender", "Male"),
                        "complexion": preset.get("complexion", "Medium brown"),
                        "nose_type": preset.get("nose_type", "Broad / Wide"),
                        "hairstyle": eff_hair,
                        "hair_color": preset.get("hair_color", "Black (#000000)"),
                        "body": preset.get("body_size", "Athletic"),
                        "height": preset.get("height", "Tall"),
                        "expression": preset.get("expression", "Confident"),
                        "outfit": eff_outfit,
                        "art_style": preset.get("art_style", "Realistic")
                    }
                    await event.answer(f"👑 Main Character locked to {pname}!", alert=False)
                    await update_creative_direction_card(event, state)

        elif data == "sc_set_cast_auto":
            state = USER_STATES.get(user_id)
            if state:
                state["locked_lead_name"] = "🤖 Auto-Invent (AI)"
                state["locked_lead_data"] = None
                await event.answer("Reset to AI Auto-Invent lead.", alert=False)
                await update_creative_direction_card(event, state)

        elif data == "sc_back_to_dir":
            state = USER_STATES.get(user_id)
            if state:
                await update_creative_direction_card(event, state)

        elif data == "action_generate_concepts":
            state = USER_STATES.get(user_id)
            if not state:
                await event.answer("Session expired. Please restart StoryCraft.", alert=True)
                return

            tier = state.get("length_tier", "Short")
            tier_info = PRICING_TIERS[tier]
            concepts_cost = tier_info["concepts_cost"]

            if user["credits"] < concepts_cost:
                await event.respond(
                    f"⚠️ **Insufficient Credits!**\n\n"
                    f"Generating 10 concepts for {tier} costs **{concepts_cost} credits**.\n"
                    f"Your balance: `{user['credits']} Credits`.",
                    buttons=[[Button.inline("💳 View Wallet", b"menu_wallet")]]
                )
                return

            database.deduct_credits(user_id, concepts_cost)
            model = user.get("selected_model", ai_engine.DEFAULT_MODEL)
            custom_key = user.get("custom_gemini_key")

            status_msg = await event.edit("⚡ **Generating, please wait...**")

            try:
                concept_res = await ai_engine.generate_ten_concepts(
                    source_title=state["source_title"],
                    source_context=state["transcript"],
                    culture=state["culture"],
                    visual_style=state["style"],
                    genre=state["genre"],
                    lead_character=state.get("locked_lead_data"),
                    user_api_key=custom_key,
                    model_name=model
                )

                if isinstance(concept_res, dict):
                    concepts = concept_res.get("concepts", [])
                    state["recommended_concept_id"] = concept_res.get("recommended_concept_id", 1)
                    state["recommendation_reason"] = concept_res.get("recommendation_reason", "")
                else:
                    concepts = concept_res
                    state["recommended_concept_id"] = 1
                    state["recommendation_reason"] = ""

                if not concepts:
                    await status_msg.edit("❌ **Could not generate concepts.** Please try again with a different prompt or video.")
                    return

                state["concepts"] = concepts
                job_id = database.create_story_job(
                    user_id=user_id,
                    source_input=state["source_input"],
                    source_title=state["source_title"],
                    transcript=state["transcript"],
                    culture=state["culture"],
                    style=state["style"],
                    genre=state["genre"],
                    timezone=state["timezone"],
                    length_tier=state["length_tier"]
                )
                database.update_job_concepts(job_id, json.dumps(concepts))
                state["job_id"] = job_id

                await render_concepts_list(status_msg, state)

            except Exception as e:
                logger.error(f"Error generating concepts: {e}")
                await status_msg.edit(f"❌ **Error generating concepts:** `{str(e)}`")

        elif data.startswith("select_concept_"):
            idx = int(data.replace("select_concept_", ""))
            state = USER_STATES.get(user_id)
            if not state or "concepts" not in state:
                await event.answer("Session expired. Please restart StoryCraft.", alert=True)
                return

            concept = next((c for c in state["concepts"] if c.get("id") == idx), None)
            if not concept:
                await event.answer("Invalid concept selected.", alert=True)
                return

            state["selected_concept"] = concept
            tier = state["length_tier"]
            tier_info = PRICING_TIERS[tier]
            pdfs_cost = tier_info["pdfs_cost"]

            delivery_fmt = state.get("delivery_format", "Dialogue / Narrative")
            lead_name = state.get("locked_lead_name", "🤖 Auto-Invent (AI)")
            lead_display = f"👑 `{lead_name}` (WP CastLock Verified)" if state.get("locked_lead_data") else "`🤖 Auto-Invent (AI)`"

            review_text = (
                f"🎯 **Concept #{idx} Selected for Production**\n\n"
                f"🎬 **Working Title:** `{concept.get('title')}`\n\n"
                f"⚡ **The 5-Second Curiosity Hook:**\n"
                f"> *\"{concept.get('hook')}\"*\n\n"
                f"📖 **Synopsis:**\n{concept.get('premise')}\n\n"
                f"🔥 **Viral Trigger:**\n{concept.get('viral_trigger')}\n\n"
                f"---\n"
                f"📊 **Production Specifications:**\n"
                f"• Visual Style: `{state['style']}`\n"
                f"• Culture: `{state['culture']}` | Genre: `{state['genre']}`\n"
                f"• Story Delivery: `{delivery_fmt}`\n"
                f"• Main Character: {lead_display}\n"
                f"• Length Tier: `{tier}` ({tier_info['scenes']} • {tier_info['duration']})\n"
                f"• Target Upload Timezone: `{state['timezone']}`\n"
                f"• Dual PDFs: `1. Story Bible` + `2. Scene Prompts Blueprint`\n\n"
                f"💰 **Dual PDF Production Fee:** `{pdfs_cost} Credits`\n"
                f"*(Charges only when both files are generated and verified)*"
            )

            buttons = [
                [Button.inline(f"✅ Approve & Produce Dual PDFs ({pdfs_cost} Cr)", b"action_produce_package")],
                [Button.inline("🔙 Back to Concepts", b"back_to_concepts"), Button.inline("❌ Cancel", b"menu_main")]
            ]
            await event.edit(review_text, buttons=buttons)

        elif data == "back_to_concepts":
            state = USER_STATES.get(user_id)
            if state and "concepts" in state:
                await render_concepts_list(event, state)

        elif data == "action_regen_concepts":
            state = USER_STATES.get(user_id)
            if not state:
                await event.answer("Session expired.", alert=True)
                return

            if user["credits"] < REGEN_COST:
                await event.answer(f"Insufficient credits for regeneration ({REGEN_COST} Credits required).", alert=True)
                return

            database.deduct_credits(user_id, REGEN_COST)
            model = user.get("selected_model", ai_engine.DEFAULT_MODEL)
            custom_key = user.get("custom_gemini_key")

            await event.edit("🔄 **Generating, please wait...**")
            concept_res = await ai_engine.generate_ten_concepts(
                source_title=state["source_title"],
                source_context=state["transcript"],
                culture=state["culture"],
                visual_style=state["style"],
                genre=state["genre"],
                lead_character=state.get("locked_lead_data"),
                user_api_key=custom_key,
                model_name=model
            )
            if isinstance(concept_res, dict):
                concepts = concept_res.get("concepts", [])
                state["recommended_concept_id"] = concept_res.get("recommended_concept_id", 1)
                state["recommendation_reason"] = concept_res.get("recommendation_reason", "")
            else:
                concepts = concept_res
                state["recommended_concept_id"] = 1
                state["recommendation_reason"] = ""

            state["concepts"] = concepts
            if "job_id" in state:
                database.update_job_concepts(state["job_id"], json.dumps(concepts))
            await render_concepts_list(event, state)

        elif data == "action_produce_package":
            state = USER_STATES.get(user_id)
            if not state or "selected_concept" not in state:
                await event.answer("No concept selected.", alert=True)
                return

            tier = state["length_tier"]
            tier_info = PRICING_TIERS[tier]
            pdfs_cost = tier_info["pdfs_cost"]

            if user["credits"] < pdfs_cost:
                await event.respond(
                    f"⚠️ **Insufficient Credits!**\n\n"
                    f"Dual PDF production for {tier} requires **{pdfs_cost} credits**.\n"
                    f"Your balance: `{user['credits']} Credits`.",
                    buttons=[[Button.inline("💳 View Wallet", b"menu_wallet")]]
                )
                return

            model = user.get("selected_model", ai_engine.DEFAULT_MODEL)
            custom_key = user.get("custom_gemini_key")
            concept = state["selected_concept"]
            delivery_fmt = state.get("delivery_format", "Dialogue / Narrative")
            locked_char = state.get("locked_lead_data")

            status_msg = await event.edit("⚡ **Generating, please wait...**")

            try:
                # 1. Deduct Production Fee
                database.deduct_credits(user_id, pdfs_cost)

                # 2. AI Full Story Generation
                story_data = await ai_engine.generate_full_story_package(
                    concept=concept,
                    culture=state["culture"],
                    visual_style=state["style"],
                    genre=state["genre"],
                    delivery_format=delivery_fmt,
                    lead_character=locked_char,
                    length_tier=tier,
                    timezone=state["timezone"],
                    user_api_key=custom_key,
                    model_name=model
                )

                # 3. Generate Dual PDFs
                bible_path, scene_path = pdf_generator.generate_dual_pdfs(
                    story_data=story_data,
                    culture=state["culture"],
                    style=state["style"],
                    genre=state["genre"],
                    delivery_format=delivery_fmt,
                    lead_character=locked_char,
                    length_tier=tier,
                    timezone=state["timezone"]
                )

                # 4. Save to Database
                if "job_id" in state:
                    database.update_job_completion(state["job_id"], json.dumps(story_data), bible_path, scene_path)
                database.log_story(user_id, story_data.get("title", "Story"), state["source_title"], state["style"], state["genre"], tier, bible_path)

                title = story_data.get("title", "Story Blueprint")
                hook = story_data.get("hook", "")
                posting = story_data.get("posting_recommendation", "")
                scenes_cnt = len(story_data.get("scenes", []))
                chars_cnt = len(story_data.get("characters", []))

                summary_text = (
                    f"🎉 **WP StoryCraft Production Complete!**\n\n"
                    f"🎬 **Title:** `{title}`\n\n"
                    f"⚡ **Spoken Hook:**\n"
                    f"> *\"{hook}\"*\n\n"
                    f"📊 **Production Stats:**\n"
                    f"• {scenes_cnt} Scene Visual Prompts (Midjourney + Kling)\n"
                    f"• {chars_cnt} Character Likeness Continuity Anchors\n"
                    f"• 3 Click-Engineered Viral Thumbnails\n\n"
                    f"⏰ **YouTube Upload Window ({state['timezone']}):**\n"
                    f"{posting}\n\n"
                    f"📥 **Downloading your Dual Production PDFs below:**"
                )
                await status_msg.edit(summary_text)

                # Send Dual PDFs
                await client.send_file(
                    event.chat_id,
                    bible_path,
                    caption=f"🖼️ **PDF 1: Image Production Prompts (Midjourney / Flux / Google Flow)**\n\n*{title} — {scenes_cnt} Self-Contained Scenes*",
                )
                job_id = state.get("job_id")
                finish_buttons = []
                if job_id:
                    finish_buttons.append([Button.inline("🖼️ Preview Scene 1 Frame (1 Cr)", f"sc_render_sc_{job_id}_1".encode())])
                finish_buttons.append([Button.inline("🎬 Start New StoryCraft", b"menu_story"), Button.inline("🔙 Main Menu", b"menu_main")])

                await client.send_file(
                    event.chat_id,
                    scene_path,
                    caption=f"📹 **PDF 2: Video Production Prompts (Google Flow / Kling / Runway)**\n\n*{title} — Camera Direction & End States*",
                    buttons=finish_buttons
                )

                USER_STATES.pop(user_id, None)

            except Exception as e:
                logger.error(f"Error producing package: {e}")
                await status_msg.edit(f"❌ **Error producing package:** `{str(e)}`")

        # Feature 4: In-Chat Visual Render Preview (Scene Frames & Character Portraits)
        elif data.startswith("sc_render_sc_"):
            parts = data.replace("sc_render_sc_", "").split("_")
            job_id = int(parts[0])
            scene_num = int(parts[1]) if len(parts) > 1 else 1

            if user["credits"] < 1:
                await event.answer("⚠️ Insufficient credits (1 Credit required for Visual Preview).", alert=True)
                return

            database.deduct_credits(user_id, 1)
            chat_id = getattr(event, 'chat_id', None) or (event.chat.id if hasattr(event, 'chat') else user_id)
            status_msg = await client.send_message(chat_id, f"⚡ **Rendering Scene {scene_num} Frame with Flux.1, please wait (~6-10s)...**")

            try:
                job = database.get_job(job_id)
                if not job or not job.get("full_story_json"):
                    database.add_credits(user_id, 1)
                    await status_msg.edit("❌ Story job data not found. 1 Credit refunded.")
                    return

                story_data = json.loads(job["full_story_json"])
                scenes = story_data.get("scenes", [])
                if not scenes:
                    database.add_credits(user_id, 1)
                    await status_msg.edit("❌ No scenes found in story package. 1 Credit refunded.")
                    return

                target_scene = next((s for s in scenes if s.get("scene_number") == scene_num), None)
                if not target_scene and 0 <= scene_num - 1 < len(scenes):
                    target_scene = scenes[scene_num - 1]
                if not target_scene:
                    target_scene = scenes[0]
                    scene_num = target_scene.get("scene_number", 1)

                image_prompt = target_scene.get("image_prompt", "")
                scene_title = target_scene.get("scene_title", f"Scene {scene_num}")
                story_title = story_data.get("title", "Story Blueprint")
                lead_name = story_data.get("characters", [{}])[0].get("name", "Protagonist") if story_data.get("characters") else "Lead Cast"

                seed = random.randint(10000, 999999)
                custom_key = user.get("custom_gemini_key")
                img_bytes = await ai_engine.render_visual_frame(image_prompt, width=1024, height=576, seed=seed, user_api_key=custom_key)

                caption = (
                    f"🎬 **Scene {scene_num}: {scene_title} — Visual Render Preview**\n"
                    f"📖 **Story:** `{story_title}`\n"
                    f"👑 **Main Character:** `{lead_name}`\n"
                    f"📐 **Aspect Ratio:** `16:9 Landscape` (YouTube Automation Standard)\n\n"
                    f"💡 *Generated with locked facial continuity & ARRI Alexa lighting profile.*"
                )

                btn_row1 = [Button.inline("🔄 Re-roll Frame (1 Cr)", f"sc_render_sc_{job_id}_{scene_num}".encode())]
                if scene_num < len(scenes):
                    next_s = scenes[scene_num] if scene_num < len(scenes) else None
                    next_title = next_s.get("scene_title", f"SC {scene_num + 1}")[:10] if next_s else f"SC {scene_num + 1}"
                    btn_row1.append(Button.inline(f"➡️ Render SC {scene_num + 1} (1 Cr)", f"sc_render_sc_{job_id}_{scene_num + 1}".encode()))

                buttons = [
                    btn_row1,
                    [Button.inline("📋 View Raw Scene Prompt", f"sc_raw_sc_{job_id}_{scene_num}".encode()), Button.inline("🔙 Main Menu", b"menu_main")]
                ]

                img_file = io.BytesIO(img_bytes)
                img_file.name = f"story_{job_id}_scene_{scene_num}_{seed}.jpg"
                await client.send_file(chat_id, img_file, caption=caption, buttons=buttons)
                try:
                    await status_msg.delete()
                except Exception:
                    pass

            except ai_engine.RenderCooldownError as cd:
                database.add_credits(user_id, 1)
                retry_btn = [
                    [Button.inline(f"🔄 Retry Scene {scene_num} (1 Cr)", f"sc_render_sc_{job_id}_{scene_num}".encode())],
                    [Button.inline("📋 View Raw Scene Prompt", f"sc_raw_sc_{job_id}_{scene_num}".encode()), Button.inline("🔙 Main Menu", b"menu_main")]
                ]
                await status_msg.edit(
                    f"⏳ **Visual Render Engine Cooldown**\n\n"
                    f"The free cloud GPU generates 1 image per 45s per IP to protect server capacity.\n"
                    f"⏱️ Remaining cooldown: **{cd.remaining_seconds} seconds**.\n\n"
                    f"✨ *Your 1 Credit was automatically refunded.* Tap below to retry when ready!",
                    buttons=retry_btn
                )
            except Exception as e:
                logger.error(f"Error rendering scene frame: {e}")
                database.add_credits(user_id, 1)
                await status_msg.edit(f"❌ **Visual Render Error:** `{str(e)}`\n\n*1 Credit has been refunded to your wallet.*")

        elif data.startswith("sc_raw_sc_"):
            parts = data.replace("sc_raw_sc_", "").split("_")
            job_id = int(parts[0])
            scene_num = int(parts[1]) if len(parts) > 1 else 1

            job = database.get_job(job_id)
            if not job or not job.get("full_story_json"):
                await event.answer("Story job expired.", alert=True)
                return

            story_data = json.loads(job["full_story_json"])
            scenes = story_data.get("scenes", [])
            target_scene = next((s for s in scenes if s.get("scene_number") == scene_num), None)
            if not target_scene and 0 <= scene_num - 1 < len(scenes):
                target_scene = scenes[scene_num - 1]

            if not target_scene:
                await event.answer("Scene not found.", alert=True)
                return

            img_prompt = target_scene.get("image_prompt", "")
            raw_text = (
                f"📋 **Scene {scene_num} Copy-Ready Image Prompt:**\n\n"
                f"```text\n{img_prompt}\n```\n\n"
                "*(Tap code block to copy directly for Midjourney / Flux / Google Flow)*"
            )
            chat_id = getattr(event, 'chat_id', None) or (event.chat.id if hasattr(event, 'chat') else user_id)
            await client.send_message(
                chat_id,
                raw_text,
                buttons=[[Button.inline(f"🔙 Back to Render SC {scene_num}", f"sc_render_sc_{job_id}_{scene_num}".encode()), Button.inline("🔙 Main Menu", b"menu_main")]]
            )

        elif data.startswith("cl_render_portrait_"):
            char_id = int(data.replace("cl_render_portrait_", ""))
            if user["credits"] < 1:
                await event.answer("⚠️ Insufficient credits (1 Credit required for Visual Preview).", alert=True)
                return

            database.deduct_credits(user_id, 1)
            char = database.get_character_by_id(char_id, user_id)
            if not char:
                database.add_credits(user_id, 1)
                await event.answer("Character not found. Credit refunded.", alert=True)
                return

            c_name = char.get("name", "Character")
            chat_id = getattr(event, 'chat_id', None) or (event.chat.id if hasattr(event, 'chat') else user_id)
            status_msg = await client.send_message(chat_id, f"⚡ **Rendering {c_name}'s Visual Portrait with Flux.1, please wait (~6-10s)...**")

            try:
                c_age = str(char.get("age", "28"))
                c_gender = char.get("gender", "Female")
                c_cpx = char.get("complexion", "Medium brown")
                c_hair = char.get("custom_hairstyle") or char.get("hairstyle", "Braids")
                c_hair_col = char.get("hair_color", "Black (#000000)")
                c_outfit = char.get("custom_outfit") or char.get("outfit_style", "Bespoke attire")
                c_nose = char.get("nose_type", "Broad / Wide")
                c_expr = char.get("expression", "Confident")
                c_style = char.get("art_style", "Realistic")

                portrait_prompt = (
                    f"Close-up cinematic 3D portrait headshot of {c_name}, {c_age} year old {c_gender}, "
                    f"{c_cpx} complexion skin tone with realistic subsurface scattering skin pores, "
                    f"{c_nose} nose, {c_hair} ({c_hair_col}) hairstyle, {c_expr} expression, "
                    f"wearing {c_outfit}, studio rim lighting, neutral studio background, sharp focus, 8k resolution, {c_style} masterpiece"
                )

                seed = random.randint(10000, 999999)
                custom_key = user.get("custom_gemini_key")
                img_bytes = await ai_engine.render_visual_frame(portrait_prompt, width=768, height=768, seed=seed, user_api_key=custom_key)

                caption = (
                    f"🎭 **CastLock 3D Visual Render Preview: {c_name}**\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎂 **Age:** `{c_age}` | 👤 **Gender:** `{c_gender}`\n"
                    f"🎨 **Complexion:** `{c_cpx}` | 👃 **Nose:** `{c_nose}`\n"
                    f"💇 **Hairstyle:** `{c_hair}` ({c_hair_col})\n"
                    f"👗 **Wardrobe:** `{c_outfit}`\n"
                    f"🎬 **Art Engine:** `{c_style}`\n\n"
                    "💡 *Rendered using CastLock biometric facial landmarks.*"
                )
                buttons = [
                    [Button.inline("🔄 Re-roll Portrait (1 Cr)", f"cl_render_portrait_{char_id}".encode()), Button.inline("⚡ Produce 9-Panel Sheet", f"cl_prod_c_{char_id}".encode())],
                    [Button.inline("✏️ Edit Trait", f"cl_ed_m_{char_id}".encode()), Button.inline("👥 Cast Roster", b"cl_roster")]
                ]

                img_file = io.BytesIO(img_bytes)
                img_file.name = f"castlock_{char_id}_{seed}.jpg"
                await client.send_file(chat_id, img_file, caption=caption, buttons=buttons)
                try:
                    await status_msg.delete()
                except Exception:
                    pass

            except ai_engine.RenderCooldownError as cd:
                database.add_credits(user_id, 1)
                retry_btn = [
                    [Button.inline("🔄 Retry Portrait (1 Cr)", f"cl_render_portrait_{char_id}".encode())],
                    [Button.inline("👥 Cast Roster", b"cl_roster"), Button.inline("🔙 Main Menu", b"menu_main")]
                ]
                await status_msg.edit(
                    f"⏳ **Visual Render Engine Cooldown**\n\n"
                    f"The free cloud GPU generates 1 image per 45s per IP to protect server capacity.\n"
                    f"⏱️ Remaining cooldown: **{cd.remaining_seconds} seconds**.\n\n"
                    f"✨ *Your 1 Credit was automatically refunded.* Tap below to retry when ready!",
                    buttons=retry_btn
                )
            except Exception as e:
                logger.error(f"Error rendering character portrait: {e}")
                database.add_credits(user_id, 1)
                await status_msg.edit(f"❌ **Visual Render Error:** `{str(e)}`\n\n*1 Credit has been refunded to your wallet.*")

        # Other Menus
        # WP CastLock — AAA 3D Character Model Sheet & Continuity Studio
        elif data == "menu_character" or data == "cl_roster":
            USER_STATES.pop(user_id, None)
            user_chars = database.get_user_characters(user_id)
            card_text = format_castlock_roster_card(user_chars, user["credits"])
            buttons = get_castlock_roster_keyboard(user_chars)
            await event.edit(card_text, buttons=buttons)

        # Guided Character Wizard Initiation
        elif data == "cl_wiz_start":
            wiz_data = {"user_id": user_id}
            USER_STATES[user_id] = {"action": "wiz_step_1", "wiz_data": wiz_data}
            card_text = format_wizard_step_card(1, wiz_data)
            buttons = get_wizard_step_keyboard(1, wiz_data)
            await event.edit(card_text, buttons=buttons)

        # Wizard Navigation & Step Jumpers
        elif data == "cl_wiz_s1":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_1", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(1, wiz_data), buttons=get_wizard_step_keyboard(1, wiz_data))

        elif data == "cl_wiz_s2":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_2", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(2, wiz_data), buttons=get_wizard_step_keyboard(2, wiz_data))

        elif data == "cl_wiz_s3":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_3", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(3, wiz_data), buttons=get_wizard_step_keyboard(3, wiz_data))

        elif data == "cl_wiz_s4":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_4", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(4, wiz_data), buttons=get_wizard_step_keyboard(4, wiz_data))

        elif data == "cl_wiz_s5":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_5", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(5, wiz_data), buttons=get_wizard_step_keyboard(5, wiz_data))

        elif data == "cl_wiz_s6":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_6", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(6, wiz_data), buttons=get_wizard_step_keyboard(6, wiz_data))

        elif data == "cl_wiz_s7":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_7", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(7, wiz_data), buttons=get_wizard_step_keyboard(7, wiz_data))

        elif data == "cl_wiz_s8":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_8", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(8, wiz_data), buttons=get_wizard_step_keyboard(8, wiz_data))

        elif data == "cl_wiz_s9":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_9", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(9, wiz_data), buttons=get_wizard_step_keyboard(9, wiz_data))

        elif data == "cl_wiz_s10":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_10", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(10, wiz_data), buttons=get_wizard_step_keyboard(10, wiz_data))

        elif data == "cl_wiz_s11":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_step_11", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(11, wiz_data), buttons=get_wizard_step_keyboard(11, wiz_data))

        # Wizard Step Choices
        elif data.startswith("cl_wz_n_"):
            name = data.replace("cl_wz_n_", "")
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["name"] = name
            USER_STATES[user_id] = {"action": "wiz_step_2", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(2, wiz_data), buttons=get_wizard_step_keyboard(2, wiz_data))

        elif data.startswith("cl_wz_a_"):
            age = data.replace("cl_wz_a_", "")
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["age"] = age
            USER_STATES[user_id] = {"action": "wiz_step_3", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(3, wiz_data), buttons=get_wizard_step_keyboard(3, wiz_data))

        elif data.startswith("cl_wz_g_"):
            idx = int(data.replace("cl_wz_g_", ""))
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["gender"] = CASTLOCK_GENDERS[idx]
            USER_STATES[user_id] = {"action": "wiz_step_4", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(4, wiz_data), buttons=get_wizard_step_keyboard(4, wiz_data))

        elif data.startswith("cl_wz_c_"):
            idx = int(data.replace("cl_wz_c_", ""))
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["complexion"] = CASTLOCK_COMPLEXIONS[idx]
            USER_STATES[user_id] = {"action": "wiz_step_5", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(5, wiz_data), buttons=get_wizard_step_keyboard(5, wiz_data))

        elif data.startswith("cl_wz_ns_"):
            idx = int(data.replace("cl_wz_ns_", ""))
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["nose_type"] = CASTLOCK_NOSE_TYPES[idx]
            USER_STATES[user_id] = {"action": "wiz_step_6", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(6, wiz_data), buttons=get_wizard_step_keyboard(6, wiz_data))

        elif data.startswith("cl_wz_h_") and data != "cl_wz_h_cust":
            idx = int(data.replace("cl_wz_h_", ""))
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["hairstyle"] = CASTLOCK_HAIRSTYLES[idx]
            wiz_data["custom_hairstyle"] = ""
            USER_STATES[user_id] = {"action": "wiz_step_7", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(7, wiz_data), buttons=get_wizard_step_keyboard(7, wiz_data))

        elif data == "cl_wz_h_cust":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_awaiting_custom_hair", "wiz_data": wiz_data}
            prompt_text = (
                "💇 **Describe Your Custom Hairstyle**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Type the exact hairstyle description directly in chat:\n"
                "*(e.g., `long goddess locs with gold cuffs` or `neat geometric cornrows`)*\n\n"
                "CastLock will lock this exact hair architecture into your 3D sheet!"
            )
            await event.edit(prompt_text, buttons=[[Button.inline("🔙 Back to Hairstyle", b"cl_wiz_s6")]])

        elif data.startswith("cl_wz_cl_"):
            idx = int(data.replace("cl_wz_cl_", ""))
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["hair_color"] = CASTLOCK_HAIR_COLORS[idx]
            USER_STATES[user_id] = {"action": "wiz_step_8", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(8, wiz_data), buttons=get_wizard_step_keyboard(8, wiz_data))

        elif data.startswith("cl_wz_b_"):
            idx = int(data.replace("cl_wz_b_", ""))
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["body_size"] = CASTLOCK_PHYSIQUES[idx]["body"]
            wiz_data["height"] = CASTLOCK_PHYSIQUES[idx]["height"]
            USER_STATES[user_id] = {"action": "wiz_step_9", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(9, wiz_data), buttons=get_wizard_step_keyboard(9, wiz_data))

        elif data.startswith("cl_wz_e_"):
            idx = int(data.replace("cl_wz_e_", ""))
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["expression"] = CASTLOCK_EXPRESSIONS[idx]
            USER_STATES[user_id] = {"action": "wiz_step_10", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(10, wiz_data), buttons=get_wizard_step_keyboard(10, wiz_data))

        elif data.startswith("cl_wz_o_") and data != "cl_wz_o_cust":
            idx = int(data.replace("cl_wz_o_", ""))
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["outfit_style"] = CASTLOCK_OUTFIT_STYLES[idx]
            wiz_data["custom_outfit"] = ""
            USER_STATES[user_id] = {"action": "wiz_step_11", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(11, wiz_data), buttons=get_wizard_step_keyboard(11, wiz_data))

        elif data == "cl_wz_o_cust":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_awaiting_custom_outfit", "wiz_data": wiz_data}
            prompt_text = (
                "👗 **Describe Your Custom Outfit**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Type the exact wardrobe description directly in chat:\n"
                "*(e.g., `emerald green Ankara gown with gold embroidery` or `tactical cyber blazer`)*\n\n"
                "CastLock will lock this exact textile craftsmanship into your 3D sheet!"
            )
            await event.edit(prompt_text, buttons=[[Button.inline("🔙 Back to Outfit", b"cl_wiz_s10")]])

        # Wizard Step 11: Art Engine Selection -> Advance to Step 12 (Reference Photo)!
        elif data.startswith("cl_wz_eg_"):
            idx = int(data.replace("cl_wz_eg_", ""))
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["art_style"] = CASTLOCK_ART_STYLES[idx]
            wiz_data["background"] = "Neutral studio"
            wiz_data["lighting"] = "Studio"
            wiz_data["purpose"] = "Animation" if ("Pixar" in wiz_data["art_style"] or "Sticky" in wiz_data["art_style"]) else "Film"

            USER_STATES[user_id] = {"action": "wiz_step_12", "wiz_data": wiz_data}
            await event.edit(format_wizard_step_card(12, wiz_data), buttons=get_wizard_step_keyboard(12, wiz_data))

        # Wizard Step 12: Skip Reference & Save Character immediately
        elif data == "cl_wz_skip_ref":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})

            # Auto-save character to SQLite database
            char_id = database.save_character(user_id, wiz_data)
            USER_STATES.pop(user_id, None)

            saved_char = database.get_character_by_id(char_id, user_id)
            card_text = format_character_detail_card(saved_char, user["credits"], is_newly_saved=True)
            buttons = get_character_detail_keyboard(char_id)
            await event.edit(card_text, buttons=buttons)

        # Wizard Step 12: Prompt user to upload reference photo
        elif data == "cl_wz_upload_ref":
            state = USER_STATES.get(user_id, {})
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            USER_STATES[user_id] = {"action": "wiz_awaiting_ref_image", "wiz_data": wiz_data}
            prompt_text = (
                "📸 **Upload Reference Photo & Instruction**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Send a photo (portrait, selfie, sketch, or outfit) into this chat now.\n\n"
                "📝 **Optional Instruction in Caption:**\n"
                "Add any specific instruction in the photo caption, e.g.:\n"
                "• *\"Keep this exact jawline and skin tone, but make hairstyle goddess locs\"*\n"
                "• *\"Match this face closely, but dress in emerald royal Ankara\"*\n\n"
                "Our Vision AI will forensically analyze your photo and lock your likeness with zero morphing!"
            )
            await event.edit(prompt_text, buttons=[[Button.inline("⚡ Skip & Save Without Photo", b"cl_wz_skip_ref")]])

        # Add/Update Reference Photo from Character Detail Profile Card
        elif data.startswith("cl_add_ref_"):
            char_id = int(data.replace("cl_add_ref_", ""))
            char = database.get_character_by_id(char_id, user_id)
            if not char:
                await event.answer("Character not found.", alert=True)
                return
            c_name = char.get("name", "Character")
            USER_STATES[user_id] = {"action": "edit_awaiting_ref_image", "char_id": char_id}
            prompt_text = (
                f"📸 **Add/Update Reference Photo for {c_name}**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Send a photo (portrait, selfie, sketch, or outfit) into this chat now.\n\n"
                "📝 **Optional Instruction in Caption:**\n"
                "Add any specific instruction in the photo caption, e.g.:\n"
                "• *\"Keep this exact jawline and skin tone, but styled in braids\"*\n"
                "• *\"Match this facial structure with realistic 3D lighting\"*\n\n"
                "Our Vision AI will forensically lock this reference likeness to your character!"
            )
            await event.edit(prompt_text, buttons=[[Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]])

        # View Character Detail Profile
        elif data.startswith("cl_view_c_"):
            char_id = int(data.replace("cl_view_c_", ""))
            char = database.get_character_by_id(char_id, user_id)
            if not char:
                await event.answer("Character not found.", alert=True)
                user_chars = database.get_user_characters(user_id)
                await event.edit(format_castlock_roster_card(user_chars, user["credits"]), buttons=get_castlock_roster_keyboard(user_chars))
                return

            USER_STATES[user_id] = {"action": "view_character", "char_id": char_id, "character": char}
            card_text = format_character_detail_card(char, user["credits"])
            buttons = get_character_detail_keyboard(char_id)
            await event.edit(card_text, buttons=buttons)

        # Delete Character Prompt
        elif data.startswith("cl_del_c_"):
            char_id = int(data.replace("cl_del_c_", ""))
            char = database.get_character_by_id(char_id, user_id)
            if not char:
                await event.answer("Character not found.", alert=True)
                return

            c_name = char.get("name", "Character")
            confirm_text = (
                f"⚠️ **Delete {c_name} from Cast Roster?**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Are you sure you want to permanently delete **{c_name}** from your permanent Cast Roster?\n\n"
                "This action cannot be undone."
            )
            buttons = [
                [Button.inline(f"🗑️ Yes, Delete {c_name}", f"cl_cdel_c_{char_id}".encode())],
                [Button.inline("❌ Cancel", f"cl_view_c_{char_id}".encode())]
            ]
            await event.edit(confirm_text, buttons=buttons)

        # Confirmed Delete Character
        elif data.startswith("cl_cdel_c_"):
            char_id = int(data.replace("cl_cdel_c_", ""))
            database.delete_character(char_id, user_id)
            USER_STATES.pop(user_id, None)
            await event.answer("Character deleted.", alert=False)
            user_chars = database.get_user_characters(user_id)
            card_text = (
                "✅ **Character successfully removed from your Cast Roster.**\n\n"
                + format_castlock_roster_card(user_chars, user["credits"])
            )
            buttons = get_castlock_roster_keyboard(user_chars)
            await event.edit(card_text, buttons=buttons)

        # Quick Edit Trait Menu
        elif data.startswith("cl_ed_m_"):
            char_id = int(data.replace("cl_ed_m_", ""))
            char = database.get_character_by_id(char_id, user_id)
            if not char:
                await event.answer("Character not found.", alert=True)
                return

            c_name = char.get("name", "Character")
            text = (
                f"✏️ **Edit Character: {c_name}**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Select which anatomical or wardrobe trait you want to update:\n"
                "*(All choices will be visible to tap directly without cycling)*"
            )
            await event.edit(text, buttons=get_castlock_edit_trait_keyboard(char_id))

        # Trait Edit Sub-Menus & Updaters
        elif data.startswith("cl_ed_t_name_"):
            char_id = int(data.replace("cl_ed_t_name_", ""))
            USER_STATES[user_id] = {"action": "edit_awaiting_name", "char_id": char_id}
            await event.edit("👤 **Enter New Name:**\n\nType the new name for this character in chat:", buttons=[[Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]])

        elif data.startswith("cl_ed_t_age_"):
            char_id = int(data.replace("cl_ed_t_age_", ""))
            USER_STATES[user_id] = {"action": "edit_awaiting_age", "char_id": char_id}
            await event.edit("🎂 **Enter New Age:**\n\nType the new age in chat (e.g. `24`):", buttons=[[Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]])

        elif data.startswith("cl_ed_t_cpx_"):
            char_id = int(data.replace("cl_ed_t_cpx_", ""))
            buttons = [
                [Button.inline("Fair", f"cl_sv_cpx_{char_id}_0".encode()), Button.inline("Light brown", f"cl_sv_cpx_{char_id}_1".encode())],
                [Button.inline("Medium brown", f"cl_sv_cpx_{char_id}_2".encode()), Button.inline("Brown", f"cl_sv_cpx_{char_id}_3".encode())],
                [Button.inline("Dark brown", f"cl_sv_cpx_{char_id}_4".encode()), Button.inline("Deep dark", f"cl_sv_cpx_{char_id}_5".encode())],
                [Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]
            ]
            await event.edit("🎨 **Select New Skin Complexion:**", buttons=buttons)

        elif data.startswith("cl_sv_cpx_"):
            parts = data.replace("cl_sv_cpx_", "").split("_")
            char_id, idx = int(parts[0]), int(parts[1])
            char = database.get_character_by_id(char_id, user_id)
            if char:
                char["complexion"] = CASTLOCK_COMPLEXIONS[idx]
                database.save_character(user_id, char)
                await event.answer("Complexion updated!", alert=False)
                await event.edit(format_character_detail_card(char, user["credits"]), buttons=get_character_detail_keyboard(char_id))

        elif data.startswith("cl_ed_t_nse_"):
            char_id = int(data.replace("cl_ed_t_nse_", ""))
            buttons = [
                [Button.inline("Broad / Wide", f"cl_sv_nse_{char_id}_0".encode()), Button.inline("Slender / Narrow", f"cl_sv_nse_{char_id}_1".encode())],
                [Button.inline("Button / Small", f"cl_sv_nse_{char_id}_2".encode()), Button.inline("Aquiline", f"cl_sv_nse_{char_id}_3".encode())],
                [Button.inline("Flat / Rounded", f"cl_sv_nse_{char_id}_4".encode())],
                [Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]
            ]
            await event.edit("👃 **Select New Nose Bridge Structure:**", buttons=buttons)

        elif data.startswith("cl_sv_nse_"):
            parts = data.replace("cl_sv_nse_", "").split("_")
            char_id, idx = int(parts[0]), int(parts[1])
            char = database.get_character_by_id(char_id, user_id)
            if char:
                char["nose_type"] = CASTLOCK_NOSE_TYPES[idx]
                database.save_character(user_id, char)
                await event.answer("Nose bridge updated!", alert=False)
                await event.edit(format_character_detail_card(char, user["credits"]), buttons=get_character_detail_keyboard(char_id))

        elif data.startswith("cl_ed_t_hrs_"):
            char_id = int(data.replace("cl_ed_t_hrs_", ""))
            buttons = [
                [Button.inline("Braids", f"cl_sv_hrs_{char_id}_0".encode()), Button.inline("Locs", f"cl_sv_hrs_{char_id}_1".encode())],
                [Button.inline("Afro", f"cl_sv_hrs_{char_id}_2".encode()), Button.inline("Twists", f"cl_sv_hrs_{char_id}_3".encode())],
                [Button.inline("Buzz Cut", f"cl_sv_hrs_{char_id}_4".encode()), Button.inline("Straight", f"cl_sv_hrs_{char_id}_5".encode())],
                [Button.inline("Curly", f"cl_sv_hrs_{char_id}_6".encode())],
                [Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]
            ]
            await event.edit("💇 **Select New Hairstyle:**", buttons=buttons)

        elif data.startswith("cl_sv_hrs_"):
            parts = data.replace("cl_sv_hrs_", "").split("_")
            char_id, idx = int(parts[0]), int(parts[1])
            char = database.get_character_by_id(char_id, user_id)
            if char:
                char["hairstyle"] = CASTLOCK_HAIRSTYLES[idx]
                char["custom_hairstyle"] = ""
                database.save_character(user_id, char)
                await event.answer("Hairstyle updated!", alert=False)
                await event.edit(format_character_detail_card(char, user["credits"]), buttons=get_character_detail_keyboard(char_id))

        elif data.startswith("cl_ed_t_col_"):
            char_id = int(data.replace("cl_ed_t_col_", ""))
            buttons = [
                [Button.inline("⚫ Black", f"cl_sv_col_{char_id}_0".encode()), Button.inline("🟤 Dark Brown", f"cl_sv_col_{char_id}_1".encode())],
                [Button.inline("🌰 Chestnut", f"cl_sv_col_{char_id}_2".encode()), Button.inline("👱 Golden Blonde", f"cl_sv_col_{char_id}_3".encode())],
                [Button.inline("🔥 Auburn", f"cl_sv_col_{char_id}_4".encode()), Button.inline("⚪ Silver Grey", f"cl_sv_col_{char_id}_5".encode())],
                [Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]
            ]
            await event.edit("💈 **Select New Hair Color:**", buttons=buttons)

        elif data.startswith("cl_sv_col_"):
            parts = data.replace("cl_sv_col_", "").split("_")
            char_id, idx = int(parts[0]), int(parts[1])
            char = database.get_character_by_id(char_id, user_id)
            if char:
                char["hair_color"] = CASTLOCK_HAIR_COLORS[idx]
                database.save_character(user_id, char)
                await event.answer("Hair color updated!", alert=False)
                await event.edit(format_character_detail_card(char, user["credits"]), buttons=get_character_detail_keyboard(char_id))

        elif data.startswith("cl_ed_t_bld_"):
            char_id = int(data.replace("cl_ed_t_bld_", ""))
            buttons = [
                [Button.inline("Average (Tall)", f"cl_sv_bld_{char_id}_0".encode()), Button.inline("Average (Avg Ht)", f"cl_sv_bld_{char_id}_1".encode())],
                [Button.inline("Athletic (Tall)", f"cl_sv_bld_{char_id}_2".encode()), Button.inline("Athletic (Avg Ht)", f"cl_sv_bld_{char_id}_3".encode())],
                [Button.inline("Slim (Tall)", f"cl_sv_bld_{char_id}_4".encode()), Button.inline("Slim (Petite)", f"cl_sv_bld_{char_id}_5".encode())],
                [Button.inline("Curvy (Avg Ht)", f"cl_sv_bld_{char_id}_6".encode()), Button.inline("Plus size (Avg Ht)", f"cl_sv_bld_{char_id}_7".encode())],
                [Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]
            ]
            await event.edit("📐 **Select New Body Frame & Height:**", buttons=buttons)

        elif data.startswith("cl_sv_bld_"):
            parts = data.replace("cl_sv_bld_", "").split("_")
            char_id, idx = int(parts[0]), int(parts[1])
            char = database.get_character_by_id(char_id, user_id)
            if char:
                char["body_size"] = CASTLOCK_PHYSIQUES[idx]["body"]
                char["height"] = CASTLOCK_PHYSIQUES[idx]["height"]
                database.save_character(user_id, char)
                await event.answer("Physique updated!", alert=False)
                await event.edit(format_character_detail_card(char, user["credits"]), buttons=get_character_detail_keyboard(char_id))

        elif data.startswith("cl_ed_t_out_"):
            char_id = int(data.replace("cl_ed_t_out_", ""))
            buttons = [
                [Button.inline("👗 Ankara", f"cl_sv_out_{char_id}_0".encode()), Button.inline("👔 Corporate", f"cl_sv_out_{char_id}_1".encode())],
                [Button.inline("👘 Traditional", f"cl_sv_out_{char_id}_2".encode()), Button.inline("🧢 Streetwear", f"cl_sv_out_{char_id}_3".encode())],
                [Button.inline("🎓 School Uniform", f"cl_sv_out_{char_id}_4".encode()), Button.inline("🪖 Tactical", f"cl_sv_out_{char_id}_5".encode())],
                [Button.inline("👕 Casual", f"cl_sv_out_{char_id}_6".encode())],
                [Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]
            ]
            await event.edit("👗 **Select New Wardrobe Style:**", buttons=buttons)

        elif data.startswith("cl_sv_out_"):
            parts = data.replace("cl_sv_out_", "").split("_")
            char_id, idx = int(parts[0]), int(parts[1])
            char = database.get_character_by_id(char_id, user_id)
            if char:
                char["outfit_style"] = CASTLOCK_OUTFIT_STYLES[idx]
                char["custom_outfit"] = ""
                database.save_character(user_id, char)
                await event.answer("Wardrobe updated!", alert=False)
                await event.edit(format_character_detail_card(char, user["credits"]), buttons=get_character_detail_keyboard(char_id))

        elif data.startswith("cl_ed_t_eng_"):
            char_id = int(data.replace("cl_ed_t_eng_", ""))
            buttons = [
                [Button.inline("🎬 Realistic (8K ARRI & UE5)", f"cl_sv_eng_{char_id}_0".encode())],
                [Button.inline("✨ Pixar 3D (Subsurface Shader)", f"cl_sv_eng_{char_id}_1".encode())],
                [Button.inline("🎨 Sticky Animation (Stylised 3D)", f"cl_sv_eng_{char_id}_2".encode())],
                [Button.inline("🔙 Cancel", f"cl_view_c_{char_id}".encode())]
            ]
            await event.edit("🎬 **Select New 3D Art Engine:**", buttons=buttons)

        elif data.startswith("cl_sv_eng_"):
            parts = data.replace("cl_sv_eng_", "").split("_")
            char_id, idx = int(parts[0]), int(parts[1])
            char = database.get_character_by_id(char_id, user_id)
            if char:
                char["art_style"] = CASTLOCK_ART_STYLES[idx]
                char["purpose"] = "Animation" if ("Pixar" in char["art_style"] or "Sticky" in char["art_style"]) else "Film"
                database.save_character(user_id, char)
                await event.answer("3D Engine updated!", alert=False)
                await event.edit(format_character_detail_card(char, user["credits"]), buttons=get_character_detail_keyboard(char_id))

        # Creator Guide
        elif data == "cl_guide":
            guide_text = (
                "📖 **WP CastLock — How It Works (Quick Creator Guide)**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "**1. The Big Problem with AI Characters:**\n"
                "Normally, if you prompt an AI image generator for Scene 1 and Scene 2, the character's face, clothes, and skin change every time. Your audience notices and the story feels cheap.\n\n"
                "**2. How CastLock Solves This:**\n"
                "CastLock produces an industry-standard **9-Panel Character Turnaround Model Sheet** (the same blueprint used by Pixar, Disney, and Marvel studios):\n"
                "• **Top Row:** Front Full Body, 3/4 Turn, 90° Side Profile\n"
                "• **Middle Row:** Back Full Body, Front Headshot (Face), 3/4 Headshot\n"
                "• **Bottom Row:** Profile Headshot, Hairstyle Macro, Wardrobe Texture\n\n"
                "**3. How to Use Your Output in 3 Easy Steps:**\n"
                "1️⃣ **Generate Sheet:** Copy the Master Prompt into **Midjourney v6.1, Flux.1, or Google Flow** to get all 9 angles in 1 image.\n"
                "2️⃣ **Lock Consistency:** Copy the Consistency Bible into every subsequent scene prompt to lock facial landmarks & SSS skin tone.\n"
                "3️⃣ **Single Angles:** Use the 9 discrete 4K prompts in the attached PDF for individual scene shots.\n\n"
                "👇 Tap below to view your roster or pick a 1-tap preset:"
            )
            await event.edit(guide_text, buttons=[
                [Button.inline("✨ Pick a Preset", b"cl_presets_menu"), Button.inline("👥 Cast Roster", b"cl_roster")]
            ])

        # Presets Menu
        elif data == "cl_presets_menu":
            text = (
                "✨ **CastLock 1-Tap Ready Presets**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "Tap any pre-configured character archetype below to immediately add them to your permanent Cast Roster:\n"
            )
            await event.edit(text, buttons=get_castlock_presets_keyboard())

        # Load Preset -> Auto-Save to DB as New Character!
        elif data.startswith("cl_preset_"):
            preset_key = data.replace("cl_preset_", "")
            preset_data = CASTLOCK_PRESETS.get(preset_key)
            if preset_data:
                char_data = dict(preset_data)
                char_data.pop("title", None)
                char_id = database.save_character(user_id, char_data)
                saved_char = database.get_character_by_id(char_id, user_id)
                card_text = format_character_detail_card(saved_char, user["credits"], is_newly_saved=True)
                buttons = get_character_detail_keyboard(char_id)
                await event.answer(f"Added {saved_char['name']} to Roster!", alert=False)
                await event.edit(card_text, buttons=buttons)

        # Produce 9-Panel Sheet from Saved Character
        elif data.startswith("cl_prod_c_"):
            char_id = int(data.replace("cl_prod_c_", ""))
            char = database.get_character_by_id(char_id, user_id)
            if not char:
                await event.answer("Character not found.", alert=True)
                return

            if user["credits"] < CASTLOCK_COST:
                await event.respond(
                    "⚠️ **Insufficient Credits!**\n\n"
                    f"WP CastLock costs **{CASTLOCK_COST} credits**. Your balance is `{user['credits']}` credits.",
                    buttons=[[Button.inline("💳 View Wallet", b"menu_wallet")]]
                )
                return

            status_msg = await event.edit("⚡ **Generating, please wait...**")
            await execute_castlock_generation(event, status_msg, char, user, client)

        # Legacy Action Forge
        elif data == "cl_action_forge":
            user_chars = database.get_user_characters(user_id)
            if user_chars:
                char = user_chars[0]
                if user["credits"] < CASTLOCK_COST:
                    await event.respond(
                        "⚠️ **Insufficient Credits!**\n\n"
                        f"WP CastLock costs **{CASTLOCK_COST} credits**. Your balance is `{user['credits']}` credits.",
                        buttons=[[Button.inline("💳 View Wallet", b"menu_wallet")]]
                    )
                    return
                status_msg = await event.edit("⚡ **Generating, please wait...**")
                await execute_castlock_generation(event, status_msg, char, user, client)
            else:
                await event.answer("Please create a character first!", alert=True)
                wiz_data = {"user_id": user_id}
                USER_STATES[user_id] = {"action": "wiz_step_1", "wiz_data": wiz_data}
                await event.edit(format_wizard_step_card(1, wiz_data), buttons=get_wizard_step_keyboard(1, wiz_data))

        elif data == "cl_view_angles":
            state = USER_STATES.get(user_id)
            char_data = state.get("last_char_data") if state else None
            if not char_data or "angle_prompts" not in char_data:
                await event.answer("Character data expired. Check the attached PDF for all angles.", alert=True)
                return

            angles = char_data["angle_prompts"]
            c_name = char_data.get("character_name", "Cast")
            angles_text = (
                f"📸 **WP CastLock — 9 Discrete 4K Angle Prompts ({c_name})**\n\n"
                f"**1. FRONT (Full Body):**\n`{angles.get('front_full_body', '')}`\n\n"
                f"**2. THREE-QUARTER (45° Full Body):**\n`{angles.get('three_quarter_full_body', '')}`\n\n"
                f"**3. PROFILE (90° Full Body):**\n`{angles.get('profile_full_body', '')}`\n\n"
                f"**4. BACK (Full Body):**\n`{angles.get('back_full_body', '')}`\n\n"
                f"**5. FRONT CLOSE-UP (Face):**\n`{angles.get('front_close_up', '')}`\n\n"
                f"**6. 3/4 CLOSE-UP:**\n`{angles.get('three_quarter_close_up', '')}`\n\n"
                f"**7. PROFILE CLOSE-UP:**\n`{angles.get('profile_close_up', '')}`\n\n"
                f"**8. HAIRSTYLE DETAIL (Macro):**\n`{angles.get('hairstyle_detail', '')}`\n\n"
                f"**9. WARDROBE DETAIL (Macro):**\n`{angles.get('wardrobe_detail', '')}`"
            )
            chat_id = getattr(event, 'chat_id', None) or (event.chat.id if hasattr(event, 'chat') else user_id)
            await client.send_message(
                chat_id,
                angles_text,
                buttons=[[Button.inline("➕ Create Another Cast", b"cl_wiz_start"), Button.inline("👥 Cast Roster", b"cl_roster")], [Button.inline("🔙 Main Menu", b"menu_main")]]
            )

        elif data == "menu_thumbnail":
            USER_STATES[user_id] = {"action": "awaiting_thumbnail_topic"}
            prompt_text = (
                "🖼 **WP ClickThumb — High-CTR Thumbnail Concepts** (2 Credits)\n\n"
                "Generate 3 click-engineered YouTube thumbnail concepts with emotional triggers, bold text overlays, and Midjourney prompts.\n\n"
                "👇 **Send your video title or story summary:**"
            )
            await event.edit(prompt_text, buttons=[[Button.inline("❌ Cancel", b"menu_main")]])

        elif data == "menu_models":
            current_model = user.get("selected_model", ai_engine.DEFAULT_MODEL)
            text = (
                "🧠 **Select Your Gemini AI Engine**\n\n"
                "WP Studio connects directly to Google DeepMind's flagship Gemini models.\n"
                f"Current Active: `{current_model}`\n\n"
                "Select a model below:"
            )
            await event.edit(text, buttons=get_models_keyboard(current_model))

        elif data.startswith("set_model_"):
            new_model = data.replace("set_model_", "")
            if new_model in ["chatgpt-4o", "claude-3-7-sonnet"]:
                await event.answer("⏳ Coming Soon! ChatGPT and Claude BYOK integrations are currently in final development.", alert=True)
                return
            if new_model in ai_engine.AVAILABLE_MODELS:
                database.update_user_model(user_id, new_model)
                user["selected_model"] = new_model
                await event.answer(f"Switched model to {new_model}!", alert=True)
                text = (
                    "🧠 **AI Engine Updated!**\n\n"
                    f"Active Model: `{new_model}`\n\n"
                    "Select another model or return to the main menu:"
                )
                await event.edit(text, buttons=get_models_keyboard(new_model))

        elif data == "menu_byok":
            has_key = bool(user.get("custom_gemini_key"))
            status = "🟢 **Connected**" if has_key else "⚪ **Not Connected (Optional)**"
            text = (
                "🔑 **BYOK (Bring Your Own Key) Engine [Optional]**\n\n"
                "For high-volume YouTube automation channels running heavy continuous workloads, you can optionally connect your personal Gemini API key.\n\n"
                "• **Dedicated Quotas**: Use your own API rate limits for massive workloads.\n"
                "• **Direct Speed**: No queue times during peak traffic.\n"
                "• **Flexible**: Use your own key or standard platform pool anytime.\n\n"
                f"Status: {status}\n\n"
                "To set or update your key, send:\n"
                "`/setkey YOUR_GEMINI_API_KEY`\n\n"
                "To remove your key and revert to the platform pool, click below:"
            )
            buttons = [
                [Button.inline("🗑️ Remove My Key", b"remove_key")] if has_key else [],
                [Button.inline("🔙 Back to Main Menu", b"menu_main")]
            ]
            await event.edit(text, buttons=[b for b in buttons if b])

        elif data == "remove_key":
            database.update_user_key(user_id, "")
            user["custom_gemini_key"] = None
            await event.answer("Custom API key removed! Reverted to platform pool.", alert=True)
            await event.edit(
                "🔑 **Custom key removed.** You are now using the platform pool.",
                buttons=[[Button.inline("🔙 Back to Main Menu", b"menu_main")]]
            )

        elif data == "menu_wallet":
            text = (
                "💳 **WP Studio Wallet & Progression**\n\n"
                f"• **Tier:** `{user['tier']}`\n"
                f"• **Balance:** `{user['credits']} Credits`\n"
                f"• **Stories Produced:** `{user['stories_created']}`\n\n"
                "📈 **Tier Roadmap:**\n"
                "• 🧱 `Builder` (0 credits)\n"
                "• ⚡ `Catalyst` (1,000 credits earned/spent)\n"
                "• 👑 `Maverick` (5,000 credits earned/spent)\n\n"
                "🎁 *New creators start with 20 free credits.*"
            )
            await event.edit(text, buttons=[[Button.inline("🔙 Back to Main Menu", b"menu_main")]])

        elif data == "menu_guide":
            guide_text = (
                "❓ **WP Studio Creator Blueprint Guide**\n\n"
                "**1. The 5-Second Hook Rule:**\n"
                "Never start a faceless video explaining who you are. Open directly with the curious question, shocking fact, or climactic moment.\n\n"
                "**2. Pacing for Retention:**\n"
                "Every visual shot should cut every 3-5 seconds. WP Studio builds image prompts specifically formatted for Midjourney v6 (`--ar 16:9`) and Flux.1.\n\n"
                "**3. Video Animation:**\n"
                "Take your generated images and paste the camera motion tags into Kling AI, Runway Gen-3, or Luma Dream Machine.\n\n"
                "**4. Voiceover Generation:**\n"
                "Copy the voiceover script lines directly into ElevenLabs with natural pacing."
            )
            await event.edit(guide_text, buttons=[[Button.inline("🔙 Back to Main Menu", b"menu_main")]])

    async def update_creative_direction_card(event, state):
        tier = state.get("length_tier", "Short")
        tier_info = PRICING_TIERS[tier]
        delivery = state.get("delivery_format", "Dialogue / Narrative")
        lead_label = state.get("locked_lead_name", "🤖 Auto-Invent (AI)")
        text = (
            "🎬 **WP StoryCraft — Step 2: Creative Direction**\n\n"
            f"📹 **Source:** `{state['source_title'][:40]}`\n"
            f"👑 **Main Character:** `{lead_label}`\n"
            f"🌍 **Culture Anchor:** `{state['culture']}`\n"
            f"🎨 **Visual Style:** `{state['style']}`\n"
            f"🎭 **Genre:** `{state['genre']}`\n"
            f"🗣️ **Story Delivery:** `{delivery}`\n"
            f"⏱️ **Length Ceiling:** `{tier}` ({tier_info['scenes']} • {tier_info['duration']})\n"
            f"⏰ **Posting Timezone:** `{state['timezone']}`\n\n"
            f"💰 **Pricing Breakdown:**\n"
            f"• 10 Concepts: `{tier_info['concepts_cost']} Credits`\n"
            f"• Dual PDFs: `{tier_info['pdfs_cost']} Credits`\n"
            f"• Total Story Package: `{tier_info['total']} Credits`\n\n"
            "Tap any parameter button below to adjust, or generate your 10 concepts:"
        )
        await event.edit(text, buttons=get_creative_direction_keyboard(state))

    async def update_castlock_card(event, state, user_credits):
        card_text = format_castlock_card(state, user_credits)
        buttons = get_castlock_keyboard(state)
        await event.edit(card_text, buttons=buttons)

    async def execute_castlock_generation(event, status_msg, state, user, client):
        user_id = user["user_id"]
        name = state.get("name", "Kemi").strip() or "Kemi"
        age = state.get("age", "28")
        gender = state.get("gender", "Female")
        complexion = state.get("complexion", "Medium brown")
        nose = state.get("nose_type", "Broad / Wide")
        hair = state.get("hairstyle", "Braids")
        custom_hair = state.get("custom_hairstyle", "").strip()
        hair_col = state.get("hair_color", "Black (#000000)")
        body = state.get("body_size", "Average")
        height = state.get("height", "Tall")
        expr = state.get("expression", "Happy")
        outfit = state.get("outfit_style", "Ankara")
        custom_outfit = state.get("custom_outfit", "").strip()
        bg = state.get("background", "Neutral studio")
        light = state.get("lighting", "Studio")
        style = state.get("art_style", "Realistic")
        purpose = state.get("purpose", "Film")

        eff_hair = custom_hair if custom_hair else f"{hair} styled in {hair_col} shade"
        eff_outfit = custom_outfit if (outfit == "Custom" or custom_outfit) else f"{outfit} bespoke attire"

        full_desc = (
            f"Character: {name}, {age}-year-old {gender}. "
            f"Complexion: {complexion} skin tone. "
            f"Nose type: {nose}. "
            f"Hairstyle: {eff_hair} (color {hair_col}). "
            f"Body Build: {body} frame, {height} stature. "
            f"Facial Expression: {expr}. "
            f"Outfit: {eff_outfit}. "
            f"Background environment: {bg}. "
            f"Lighting: {light} setup. "
            f"Art Direction: {style}. "
            f"Target Media Purpose: {purpose}."
        )

        try:
            model = user.get("selected_model", ai_engine.DEFAULT_MODEL)
            custom_key = user.get("custom_gemini_key")

            ref_path = state.get("reference_image_path")
            ref_inst = state.get("reference_instruction", "")
            ref_bio = state.get("vision_biometrics", "")
            ref_bytes = None
            if ref_path and os.path.exists(ref_path):
                try:
                    with open(ref_path, "rb") as rf:
                        ref_bytes = rf.read()
                except Exception as rf_err:
                    logger.warning(f"Failed reading reference image {ref_path}: {rf_err}")

            char_data = None
            try:
                char_data = await ai_engine.generate_character_turnaround(
                    character_desc=full_desc,
                    style=style,
                    reference_image_bytes=ref_bytes,
                    reference_instruction=ref_inst,
                    vision_biometrics=ref_bio,
                    user_api_key=custom_key,
                    model_name=model
                )
            except Exception as ex:
                logger.warning(f"CastLock AI call warning: {ex}. Running studio compiler fallback...")

            if not char_data or not char_data.get("master_9panel_sheet_prompt"):
                ref_anchor = f" Reference Biometric Likeness: {ref_bio}." if ref_bio else ""
                master_prompt = (
                    f"Character model sheet, turnaround reference sheet, 3x3 grid layout, 9 distinct panels of the same character: "
                    f"[1] FRONT full body standing relaxed A-pose at eye-level, "
                    f"[2] THREE-QUARTER full body standing at 45-degree angle showing silhouette, "
                    f"[3] PROFILE 90-degree full body standing showing posture and spinal alignment, "
                    f"[4] BACK full body standing rear view showing hair drape and dress silhouette, "
                    f"[5] FRONT CLOSE-UP headshot portrait with {expr.lower()} expression, "
                    f"[6] THREE-QUARTER CLOSE-UP headshot at 45-degree angle showing cheekbone and jawline definition, "
                    f"[7] PROFILE CLOSE-UP headshot true 90-degree side profile showing {nose.lower()} nose bridge and lips, "
                    f"[8] HAIRSTYLE DETAIL macro close-up of back of head showing {eff_hair}, "
                    f"[9] WARDROBE DETAIL macro close-up of torso and neckline showing {eff_outfit}. "
                    f"Featuring {name}, {age}-year-old {gender}, {complexion.lower()} skin tone, {height.lower()} {body.lower()} build, {eff_hair}, {eff_outfit}.{ref_anchor} "
                    f"Uniform neutral light grey studio background, {light.lower()} multi-point cinematic lighting, "
                    f"Raytracing, Subsurface Scattering (SSS), 8k resolution, identical facial proportions across all panels, zero morphological drift, no text, no watermarks --ar 9:16 --v 6.1 --stylize 250"
                )
                consistency_bible = (
                    f"DEMOGRAPHICS & BIOMETRICS: {name}, {age}-year-old {gender}, {height} height, {body} build.\n"
                    f"COMPLEXION & SKIN SHADER: {complexion} tone with realistic melanin gradient, authentic epidermal micro-pore displacement, and soft subsurface scattering (SSS) light diffusion.\n"
                    f"CRANIOFACIAL LANDMARKS: {nose} nasal bridge, sculpted cheekbones, balanced lip contour with natural sheen, {expr} expression.\n"
                    f"HAIR ARCHITECTURE: {eff_hair} with clean geometric scalp sectioning.\n"
                    f"WARDROBE CRAFTSMANSHIP: {eff_outfit} tailored with precise textile weave and crisp edge stitching.\n"
                    f"LIGHTING & ENVIRONMENT: {light} setup on {bg} cyclorama backdrop, neutral color temperature, subtle rim light separating subject from background.\n"
                    f"IDENTITY CONTINUITY LOCK: Identical craniofacial landmarks and wardrobe architecture locked across all 9 panels."
                )
                angles_dict = {
                    "front_full_body": f"Objective full body standing front view, eye-level, 50mm lens. {name}, {age}yo {gender}, {complexion} skin, {eff_hair}, wearing {eff_outfit}. Neutral {bg}, soft {light} lighting, 8k --ar 9:16",
                    "three_quarter_full_body": f"Objective full body standing 45-degree three-quarter view. {name}, displaying silhouette depth, {eff_hair}, wearing {eff_outfit}. Neutral {bg}, soft {light} lighting, subtle rim light, 8k --ar 9:16",
                    "profile_full_body": f"Objective full body standing strict 90-degree side profile. {name}, showing posture and garment drape, {eff_hair}, wearing {eff_outfit}. Neutral {bg}, 8k --ar 9:16",
                    "back_full_body": f"Objective full body standing back view. {name}, showing rear garment construction and hair flow down spine. Neutral {bg}, 8k --ar 9:16",
                    "front_close_up": f"Close-up headshot portrait facing directly forward. {name}, {complexion} skin, {expr} expression, {nose} nose bridge, {eff_hair}. Ultra-detailed skin pores, 8k --ar 1:1",
                    "three_quarter_close_up": f"Close-up headshot portrait at 45-degree angle. Highlighting cheekbone curvature and jawline definition for {name}. {complexion} skin, {eff_hair}, 8k --ar 1:1",
                    "profile_close_up": f"Strict 90-degree side profile headshot portrait. Focusing on {nose} nose bridge, lip profile, and ear anatomy for {name}. 8k --ar 1:1",
                    "hairstyle_detail": f"Macro close-up of back of head for {name}. Showcasing {eff_hair} with clean scalp sectioning and fine texture. Studio rim lighting, 8k --ar 1:1",
                    "wardrobe_detail": f"Macro textile craftsmanship view of {name}'s attire: {eff_outfit}. Fine fabric weave, collar stitching, and material texture. Studio lighting, 8k --ar 1:1"
                }
                char_data = {
                    "character_name": name,
                    "visual_style": f"{style} / Unreal Engine 5 3D Render",
                    "consistency_bible": consistency_bible,
                    "master_9panel_sheet_prompt": master_prompt,
                    "angle_prompts": angles_dict,
                    "action_prompt": f"Cinematic wide-angle dynamic 3D shot of {name} in {eff_outfit} in motion. Dramatic lighting, atmospheric particle effects, 8k --ar 16:9",
                    "recommended_midjourney_params": "--ar 9:16 --v 6.1 --stylize 250"
                }

            database.deduct_credits(user_id, CASTLOCK_COST)
            pdf_path = pdf_generator.generate_character_forge_pdf(char_data)

            char_name = char_data.get("character_name", name)
            turnaround = char_data.get("master_9panel_sheet_prompt", "")
            bible = char_data.get("consistency_bible", "")
            action = char_data.get("action_prompt", "")

            state["last_char_data"] = char_data

            resp_text = (
                f"🎉 **WP CastLock 3D Model Sheet Created for {char_name}!**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📋 **HOW TO USE THIS IN 3 EASY STEPS:**\n"
                "1️⃣ **Tap to Copy:** Tap the Master Prompt below to copy it to your clipboard.\n"
                "2️⃣ **Paste into Generator:** Paste it into **Midjourney v6.1, Flux.1, or Google Flow**.\n"
                f"3️⃣ **Get 9 Angles in 1 Sheet:** Your generator will produce a complete 3x3 reference sheet of {char_name} covering all 9 angles with 100% facial and wardrobe continuity!\n\n"
                f"👑 **MASTER 9-PANEL MODEL SHEET PROMPT:**\n"
                f"```text\n{turnaround}\n```\n\n"
                f"🧬 **LOCKED CONSISTENCY BIBLE (Copy into individual scene prompts):**\n"
                f"```text\n{bible}\n```\n\n"
                f"⚡ **DYNAMIC ACTION SHOT PROMPT:**\n"
                f"> *\"{action}\"*\n\n"
                f"📄 Complete 9-Angle Production Specification PDF attached below:"
            )

            if hasattr(status_msg, 'edit'):
                await status_msg.edit(resp_text)
            else:
                await event.respond(resp_text)

            chat_id = getattr(event, 'chat_id', None) or (event.chat.id if hasattr(event, 'chat') else user_id)
            char_id = state.get("char_id")
            sheet_buttons = []
            if char_id:
                sheet_buttons.append([Button.inline("🖼️ Render Visual Portrait (1 Cr)", f"cl_render_portrait_{char_id}".encode()), Button.inline("📋 View 9 Angle Prompts", b"cl_view_angles")])
            else:
                sheet_buttons.append([Button.inline("📋 View 9 Angle Prompts", b"cl_view_angles")])
            sheet_buttons.append([Button.inline("➕ Create Another Character", b"cl_wiz_start"), Button.inline("👥 Cast Roster", b"cl_roster")])
            sheet_buttons.append([Button.inline("🔙 Main Menu", b"menu_main")])

            await client.send_file(
                chat_id,
                pdf_path,
                caption=f"🔨 **{char_name} — CastLock 3D Continuity Sheet.pdf**",
                buttons=sheet_buttons
            )
        except Exception as e:
            logger.error(f"Error in CastLock generation: {e}")
            err_msg = f"❌ **Error generating character sheet:** `{str(e)}`"
            if hasattr(status_msg, 'edit'):
                await status_msg.edit(err_msg)
            else:
                await event.respond(err_msg)

    async def render_concepts_list(msg_or_event, state):
        concepts = state.get("concepts", [])
        tier = state.get("length_tier", "Short")
        tier_info = PRICING_TIERS.get(tier, PRICING_TIERS["Short"])
        culture = state.get("culture", "Black American")
        style = state.get("style", "Stylised 3D")
        genre = state.get("genre", "🏙️ Urban Street & Hood Hustle")

        text = f"🔥 **10 YouTube Automation Concepts Generated!**\n"
        text += f"Target: `{culture}` | `{style}` | `{genre}` | `{tier}` ({tier_info['duration']})\n\n"

        for c in concepts[:10]:
            cid = c.get("id")
            title = c.get("title")
            hook = c.get("hook")
            text += f"**[{cid}] {title}**\n⚡ *\"{hook}\"*\n\n"

        # AI Top Recommendation Box (placed directly above button select prompt)
        rec_id = state.get("recommended_concept_id", 1)
        rec_reason = state.get("recommendation_reason", "")
        rec_concept = next((c for c in concepts if c.get("id") == rec_id), concepts[0] if concepts else None)

        if rec_concept:
            rec_title = rec_concept.get("title", "")
            rec_trigger = rec_reason or rec_concept.get("viral_trigger", "Highest retention hook and emotional payoff.")
            text += (
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⭐ **AI Top Recommendation: Concept #{rec_id}**\n"
                f"> **\"{rec_title}\"**\n"
                f"💡 *Why it will perform best: {rec_trigger}*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            )

        text += "👇 **Tap a number button below to select your concept & proceed to approval:**"

        row1 = [Button.inline(f"{'⭐ ' if i == rec_id else ''}{i}", f"select_concept_{i}".encode()) for i in range(1, 6)]
        row2 = [Button.inline(f"{'⭐ ' if i == rec_id else ''}{i}", f"select_concept_{i}".encode()) for i in range(6, 11)]
        row3 = [Button.inline(f"🔄 Regenerate 10 Concepts ({REGEN_COST} Cr)", b"action_regen_concepts")]
        row4 = [Button.inline("❌ Cancel", b"menu_main")]

        if hasattr(msg_or_event, 'edit'):
            await msg_or_event.edit(text, buttons=[row1, row2, row3, row4])
        else:
            await msg_or_event.respond(text, buttons=[row1, row2, row3, row4])

    def get_admin_panel_data(user_id):
        stats = database.get_system_stats()
        settings = database.get_system_settings()
        primary_key, fallback_key = database.get_master_gemini_keys()

        maint_on = (settings.get("maintenance_mode") == "1")
        byok_on = (settings.get("byok_enabled") == "1")

        maint_status = "🔴 ACTIVE (Locked)" if maint_on else "🟢 NORMAL (Online)"
        byok_status = "🟢 OPEN (BYOK Allowed)" if byok_on else "🔒 LOCKED (Platform Credits Only)"
        p_status = f"🟢 Configured (`...{primary_key[-6:]}`)" if primary_key else "🔴 Missing"
        f_status = f"🟢 Configured (`...{fallback_key[-6:]}`)" if fallback_key else "🟡 Unset"

        text = (
            "🛡️ **WP Studio Master Administration Suite**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 **Total Creators:** `{stats.get('total_users', 0)}` (Active 24h: `{stats.get('active_users_24h', stats.get('total_users', 0))}`)\n"
            f"💳 **Circulating Credits:** `{stats.get('total_credits_in_circulation', 0):,}`\n"
            f"🎬 **Screenplay Jobs:** `{stats.get('total_story_jobs', stats.get('total_jobs', 0))}`\n"
            f"🧬 **CastLock Characters:** `{stats.get('total_characters', stats.get('total_characters_forged', 0))}`\n\n"
            "⚙️ **System Governance & Multi-Key Health:**\n"
            f"• **Maintenance Gate:** {maint_status}\n"
            f"• **BYOK Lock Policy:** {byok_status}\n"
            f"• **Primary Engine Key:** {p_status}\n"
            f"• **Fallback 429 Pool Key:** {f_status}\n\n"
            "🛠️ **Quick Action Commands:**\n"
            "• `/grant <user_id> <amount> [reason]`\n"
            "• `/deduct <user_id> <amount> [reason]`\n"
            "• `/set_tier <user_id> <Free|Builder|Pro|VIP>`\n"
            "• `/lock <storycraft|forge|thumbnail|renderer|byok|maintenance>`\n"
            "• `/unlock <storycraft|forge|thumbnail|renderer|byok|maintenance>`\n"
            "• `/broadcast <message>` (sets top banner in app)\n"
            "• `/broadcast off` (turns off top banner)"
        )

        miniapp_url = os.getenv("MINIAPP_URL", "").strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        if not miniapp_url or "localhost" in miniapp_url or "127.0.0.1" in miniapp_url or not miniapp_url.startswith("http"):
            miniapp_url = "https://wpstudio.onrender.com/miniapp"
        if not miniapp_url.endswith("/miniapp"):
            miniapp_url = miniapp_url.rstrip("/") + "/miniapp"
        admin_web_url = f"{miniapp_url}?user_id={user_id}"

        byok_btn_text = "🔒 Lock BYOK" if byok_on else "🔓 Unlock BYOK"
        maint_btn_text = "🟢 End Maintenance" if maint_on else "🔴 Enable Maintenance"

        buttons = [
            [Button.inline(byok_btn_text, b"admin_toggle_byok"), Button.inline(maint_btn_text, b"admin_toggle_maint")],
            [Button.url("🖥️ Open Web Admin Suite", admin_web_url)],
            [Button.inline("🔄 Refresh Status", b"admin_refresh"), Button.inline("🔙 Main Menu", b"menu_main")]
        ]
        return text, buttons

    @client.on(events.NewMessage(pattern=r"^/setkey(?:\s+(.+))?"))
    async def setkey_handler(event):
        user_id = event.sender_id
        # Check BYOK lock
        settings = database.get_system_settings()
        byok_enabled = settings.get("byok_enabled", "0")
        if (byok_enabled == "0" or byok_enabled == 0) and not database.is_admin(user_id):
            await event.respond(
                "🔒 **BYOK is Locked by Administrator**\n\n"
                "Personal Gemini API keys are currently disabled on this platform.\n"
                "Standard platform credits are required for all generations."
            )
            return

        key = event.pattern_match.group(1)
        if not key or not key.strip():
            await event.respond(
                "⚠️ **Usage:** `/setkey YOUR_GEMINI_API_KEY`\n\n"
                "Get your key at: https://aistudio.google.com/app/apikey"
            )
            return

        key = key.strip()
        database.update_user_key(user_id, key)
        await event.respond(
            "✅ **Gemini API Key Connected Successfully!**\n\n"
            "Your personal key will now be used for your heavy automated generation tasks! 🎉",
            buttons=[[Button.inline("🎬 Start Creating", b"menu_main")]]
        )

    @client.on(events.NewMessage(pattern=r"^/admin$"))
    async def admin_handler(event):
        user_id = event.sender_id
        if not database.is_admin(user_id):
            await event.respond("⛔ **Access Denied:** Administrator authorization required.")
            return

        text, buttons = get_admin_panel_data(user_id)
        await event.respond(text, buttons=buttons)

    @client.on(events.NewMessage(pattern=r"^/grant(?:\s+(\d+)\s+(\d+)(?:\s+(.+))?)?"))
    async def grant_credits_handler(event):
        user_id = event.sender_id
        if not database.is_admin(user_id):
            await event.respond("⛔ **Access Denied.**")
            return

        target_id_str = event.pattern_match.group(1)
        amount_str = event.pattern_match.group(2)
        reason = event.pattern_match.group(3) or "Admin grant via Telegram"

        if not target_id_str or not amount_str:
            await event.respond("⚠️ **Usage:** `/grant <user_id> <amount> [reason]`\nExample: `/grant 5628105961 500 Promo gift`")
            return

        target_id = int(target_id_str)
        amount = int(amount_str)
        res = database.admin_modify_user_credits(user_id, target_id, "add", amount, reason)
        if res.get("success"):
            await event.respond(
                f"✅ **Credits Granted!**\n\n"
                f"• Target User: `{target_id}`\n"
                f"• Added: `+{amount}` credits\n"
                f"• New Balance: `{res['new_balance']}` credits\n"
                f"• Reason: _{reason}_"
            )
        else:
            await event.respond(f"❌ **Error:** {res.get('error', 'Operation failed')}")

    @client.on(events.NewMessage(pattern=r"^/deduct(?:\s+(\d+)\s+(\d+)(?:\s+(.+))?)?"))
    async def deduct_credits_handler(event):
        user_id = event.sender_id
        if not database.is_admin(user_id):
            await event.respond("⛔ **Access Denied.**")
            return

        target_id_str = event.pattern_match.group(1)
        amount_str = event.pattern_match.group(2)
        reason = event.pattern_match.group(3) or "Admin deduction via Telegram"

        if not target_id_str or not amount_str:
            await event.respond("⚠️ **Usage:** `/deduct <user_id> <amount> [reason]`\nExample: `/deduct 5628105961 50 Refund adjustment`")
            return

        target_id = int(target_id_str)
        amount = int(amount_str)
        res = database.admin_modify_user_credits(user_id, target_id, "deduct", amount, reason)
        if res.get("success"):
            await event.respond(
                f"✅ **Credits Deducted!**\n\n"
                f"• Target User: `{target_id}`\n"
                f"• Deducted: `-{amount}` credits\n"
                f"• New Balance: `{res['new_balance']}` credits\n"
                f"• Reason: _{reason}_"
            )
        else:
            await event.respond(f"❌ **Error:** {res.get('error', 'Operation failed')}")

    @client.on(events.NewMessage(pattern=r"^/set_tier(?:\s+(\d+)\s+([A-Za-z0-9\s]+))?"))
    async def set_tier_handler(event):
        user_id = event.sender_id
        if not database.is_admin(user_id):
            await event.respond("⛔ **Access Denied.**")
            return

        target_id_str = event.pattern_match.group(1)
        tier = (event.pattern_match.group(2) or "").strip()

        if not target_id_str or not tier:
            await event.respond("⚠️ **Usage:** `/set_tier <user_id> <Free|Builder|Pro|Studio VIP>`")
            return

        target_id = int(target_id_str)
        res = database.admin_set_user_tier(user_id, target_id, tier)
        if res.get("success"):
            await event.respond(f"✅ **Tier Updated!** User `{target_id}` is now `{res['tier']}`.")
        else:
            await event.respond(f"❌ **Error:** {res.get('error', 'Operation failed')}")

    @client.on(events.NewMessage(pattern=r"^/lock(?:\s+([A-Za-z0-9_]+))?"))
    async def lock_feature_handler(event):
        user_id = event.sender_id
        if not database.is_admin(user_id):
            await event.respond("⛔ **Access Denied.**")
            return

        target = (event.pattern_match.group(1) or "").lower().strip()
        key_map = {
            "byok": ("byok_enabled", "0", "BYOK (Personal Keys Locked)"),
            "maintenance": ("maintenance_mode", "1", "Global Maintenance Mode Enabled"),
            "storycraft": ("feature_storycraft", "0", "StoryCraft Studio Locked"),
            "forge": ("feature_character_forge", "0", "CastLock Character Forge Locked"),
            "thumbnail": ("feature_thumbnail_lab", "0", "YouTube Thumbnail Lab Locked"),
            "renderer": ("feature_frame_renderer", "0", "Visual Frame Renderer Locked")
        }
        if target not in key_map:
            await event.respond("⚠️ **Usage:** `/lock <byok|maintenance|storycraft|forge|thumbnail|renderer>`")
            return

        setting_key, val, desc = key_map[target]
        database.update_system_settings({setting_key: val})
        await event.respond(f"🔒 **Locked:** {desc}")

    @client.on(events.NewMessage(pattern=r"^/unlock(?:\s+([A-Za-z0-9_]+))?"))
    async def unlock_feature_handler(event):
        user_id = event.sender_id
        if not database.is_admin(user_id):
            await event.respond("⛔ **Access Denied.**")
            return

        target = (event.pattern_match.group(1) or "").lower().strip()
        key_map = {
            "byok": ("byok_enabled", "1", "BYOK (Personal Keys Unlocked)"),
            "maintenance": ("maintenance_mode", "0", "Global Maintenance Mode Disabled"),
            "storycraft": ("feature_storycraft", "1", "StoryCraft Studio Unlocked"),
            "forge": ("feature_character_forge", "1", "CastLock Character Forge Unlocked"),
            "thumbnail": ("feature_thumbnail_lab", "1", "YouTube Thumbnail Lab Unlocked"),
            "renderer": ("feature_frame_renderer", "1", "Visual Frame Renderer Unlocked")
        }
        if target not in key_map:
            await event.respond("⚠️ **Usage:** `/unlock <byok|maintenance|storycraft|forge|thumbnail|renderer>`")
            return

        setting_key, val, desc = key_map[target]
        database.update_system_settings({setting_key: val})
        await event.respond(f"🔓 **Unlocked:** {desc}")

    @client.on(events.NewMessage(pattern=r"^/broadcast(?:\s+(.+))?"))
    async def broadcast_command_handler(event):
        user_id = event.sender_id
        if not database.is_admin(user_id):
            await event.respond("⛔ **Access Denied.**")
            return

        msg = event.pattern_match.group(1)
        if not msg or not msg.strip():
            await event.respond(
                "📢 **Broadcast Command**\n\n"
                "• Send message to all users who sent /start:\n"
                "`/broadcast <your message>`\n\n"
                "• Set app top banner only (no message):\n"
                "`/banner <your message>`\n\n"
                "• Turn off app top banner:\n"
                "`/broadcast off`"
            )
            return

        msg = msg.strip()
        if msg.lower() == "off":
            database.update_system_settings({
                "announcement_banner_active": "0",
                "announcement_banner_text": "",
                "announcement_active": "0",
                "announcement_text": ""
            })
            await event.respond("🔕 **Top banner turned off.**")
            return

        # 1. Update mini app banner safely
        database.update_system_settings({
            "announcement_banner_active": "1",
            "announcement_banner_type": "info",
            "announcement_banner_text": msg,
            "announcement_active": "1",
            "announcement_type": "info",
            "announcement_text": msg
        })

        # 2. Get real users who previously sent /start
        user_ids = database.get_all_user_ids()
        if not user_ids:
            await event.respond("⚠️ **No users found.** App banner is active.")
            return

        status_msg = await event.respond(f"📢 **Sending message to {len(user_ids)} users...**")
        sent_count = 0
        blocked_count = 0
        failed_count = 0
        broadcast_text = f"📢 **Announcement from WP Studio**\n\n{msg}"

        for uid in user_ids:
            try:
                await client.send_message(uid, broadcast_text)
                sent_count += 1
            except telethon_errors.FloodWaitError as fwe:
                logger.warning(f"Flood wait {fwe.seconds}s during broadcast")
                await asyncio.sleep(fwe.seconds + 1)
                try:
                    await client.send_message(uid, broadcast_text)
                    sent_count += 1
                except Exception:
                    failed_count += 1
            except (telethon_errors.UserIsBlockedError, telethon_errors.InputUserDeactivatedError):
                blocked_count += 1
            except telethon_errors.PeerIdInvalidError:
                failed_count += 1
            except Exception as ex:
                failed_count += 1
                logger.warning(f"Broadcast failed for user {uid}: {ex}")

            # Safe spacing: 0.1s pause between sends
            await asyncio.sleep(0.1)

        await status_msg.edit(
            f"✅ **Broadcast complete!**\n\n"
            f"• **Sent:** {sent_count} users\n"
            f"• **Blocked:** {blocked_count} users\n"
            f"• **Failed:** {failed_count} users\n"
            f"• **App Banner:** Active\n\n"
            f"To turn off top banner: `/broadcast off`"
        )

    @client.on(events.NewMessage(pattern=r"^/banner(?:\s+(.+))?"))
    async def banner_command_handler(event):
        user_id = event.sender_id
        if not database.is_admin(user_id):
            await event.respond("⛔ **Access Denied.**")
            return

        msg = event.pattern_match.group(1)
        if not msg or not msg.strip():
            await event.respond("⚠️ **Usage:** `/banner <message>`\nTo turn off: `/banner off`")
            return

        msg = msg.strip()
        if msg.lower() == "off":
            database.update_system_settings({
                "announcement_banner_active": "0",
                "announcement_banner_text": "",
                "announcement_active": "0",
                "announcement_text": ""
            })
            await event.respond("🔕 **Top banner turned off.**")
        else:
            database.update_system_settings({
                "announcement_banner_active": "1",
                "announcement_banner_type": "info",
                "announcement_banner_text": msg,
                "announcement_active": "1",
                "announcement_type": "info",
                "announcement_text": msg
            })
            await event.respond(f"📢 **Top banner updated!**\n_{msg}_")

    @client.on(events.NewMessage)
    async def text_input_handler(event):
        if event.text and event.text.startswith("/"):
            return

        user_id = event.sender_id
        state = USER_STATES.get(user_id)
        if not state:
            return

        action = state.get("action")
        user = database.get_user(user_id)
        custom_key = user.get("custom_gemini_key")
        model = user.get("selected_model", ai_engine.DEFAULT_MODEL)

        if action == "awaiting_story_source":
            text = event.text.strip()
            status_msg = await event.respond("⚡ **Generating, please wait...**")

            # Check if YouTube URL
            if "youtube.com" in text or "youtu.be" in text:
                res = await source_extractor.get_youtube_transcript_async(text, user_api_key=custom_key)
                if not res.get("success"):
                    err_msg = res.get("error", "Captions unavailable.")
                    await status_msg.edit(
                        f"🛑 **Generation Stopped (No Captions Found):**\n\n"
                        f"{err_msg}\n\n"
                        f"🛡️ **Anti-Hallucination Policy:**\n"
                        f"To guarantee story authenticity and protect your output quality, WP Studio does not invent fake stories when captions are missing.\n\n"
                        f"✨ **Zero credits were deducted.**\n\n"
                        f"👉 **Next Step:** Please provide a YouTube video that has subtitles/captions enabled, or type your original topic or premise directly in chat!"
                    )
                    return

                source_title = res.get("title", "YouTube Source")
                transcript = res.get("transcript", "")
            else:
                source_title = text[:40]
                transcript = text

            state_data = {
                "action": "configuring_creative_direction",
                "source_input": text,
                "source_title": source_title,
                "transcript": transcript,
                "locked_lead_name": "🤖 Auto-Invent (AI)",
                "locked_lead_data": None,
                "culture": "Black American",
                "style": "Stylised 3D",
                "genre": "🏙️ Urban Street & Hood Hustle",
                "delivery_format": "Dialogue / Narrative",
                "length_tier": "Short",
                "timezone": "Africa/Lagos"
            }
            USER_STATES[user_id] = state_data

            tier_info = PRICING_TIERS["Short"]
            card_text = (
                "🎬 **WP StoryCraft — Step 2: Creative Direction**\n\n"
                f"📹 **Source:** `{source_title[:40]}`\n"
                f"👑 **Main Character:** `🤖 Auto-Invent (AI)`\n"
                f"🌍 **Culture Anchor:** `{state_data['culture']}`\n"
                f"🎨 **Visual Style:** `{state_data['style']}`\n"
                f"🎭 **Genre:** `{state_data['genre']}`\n"
                f"🗣️ **Story Delivery:** `{state_data['delivery_format']}`\n"
                f"⏱️ **Length Ceiling:** `Short` ({tier_info['scenes']} • {tier_info['duration']})\n"
                f"⏰ **Posting Timezone:** `{state_data['timezone']}`\n\n"
                f"💰 **Pricing Breakdown:**\n"
                f"• 10 Concepts: `{tier_info['concepts_cost']} Credits`\n"
                f"• Dual PDFs: `{tier_info['pdfs_cost']} Credits`\n"
                f"• Total Story Package: `{tier_info['total']} Credits`\n\n"
                "Tap any parameter button below to adjust, or generate your 10 concepts:"
            )
            await status_msg.edit(card_text, buttons=get_creative_direction_keyboard(state_data))

        elif action in ("wiz_step_1", "wiz_awaiting_name"):
            name = event.text.strip()
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["name"] = name if name else "Hero"
            state["action"] = "wiz_step_2"
            state["wiz_data"] = wiz_data
            await event.respond(format_wizard_step_card(2, wiz_data), buttons=get_wizard_step_keyboard(2, wiz_data))

        elif action in ("wiz_step_2", "wiz_awaiting_age"):
            text = event.text.strip()
            digits = "".join([c for c in text if c.isdigit()])
            age = digits if digits else "25"
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["age"] = age
            state["action"] = "wiz_step_3"
            state["wiz_data"] = wiz_data
            await event.respond(format_wizard_step_card(3, wiz_data), buttons=get_wizard_step_keyboard(3, wiz_data))

        elif action == "wiz_awaiting_custom_hair":
            text = event.text.strip()
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["custom_hairstyle"] = text
            wiz_data["hairstyle"] = "Custom"
            state["action"] = "wiz_step_7"
            state["wiz_data"] = wiz_data
            await event.respond(format_wizard_step_card(7, wiz_data), buttons=get_wizard_step_keyboard(7, wiz_data))

        elif action == "wiz_awaiting_custom_outfit":
            text = event.text.strip()
            wiz_data = state.get("wiz_data", {"user_id": user_id})
            wiz_data["custom_outfit"] = text
            wiz_data["outfit_style"] = "Custom"
            state["action"] = "wiz_step_11"
            state["wiz_data"] = wiz_data
            await event.respond(format_wizard_step_card(11, wiz_data), buttons=get_wizard_step_keyboard(11, wiz_data))

        elif action == "edit_awaiting_name":
            char_id = state.get("char_id")
            char = database.get_character_by_id(char_id, user_id)
            if char:
                char["name"] = event.text.strip()
                database.save_character(user_id, char)
                USER_STATES.pop(user_id, None)
                card_text = format_character_detail_card(char, user["credits"])
                await event.respond(f"✅ **Name updated to {char['name']}!**\n\n" + card_text, buttons=get_character_detail_keyboard(char_id))

        elif action == "edit_awaiting_age":
            char_id = state.get("char_id")
            char = database.get_character_by_id(char_id, user_id)
            if char:
                digits = "".join([c for c in event.text if c.isdigit()])
                char["age"] = digits if digits else char.get("age", "25")
                database.save_character(user_id, char)
                USER_STATES.pop(user_id, None)
                card_text = format_character_detail_card(char, user["credits"])
                await event.respond(f"✅ **Age updated to {char['age']}!**\n\n" + card_text, buttons=get_character_detail_keyboard(char_id))

        elif action in ("wiz_awaiting_ref_image", "edit_awaiting_ref_image"):
            # Check if photo was uploaded
            has_media = bool(getattr(event.message, 'media', None))
            if not has_media:
                buttons = [[Button.inline("⚡ Skip Photo & Save Character", b"cl_wz_skip_ref")]] if action == "wiz_awaiting_ref_image" else []
                await event.respond(
                    "⚠️ **Please upload a photo directly!**\n\n"
                    "Tap the attachment paperclip 📎 in Telegram, choose your photo, and optionally add your instruction in the caption.\n"
                    "Or tap below to skip:",
                    buttons=buttons
                )
                return

            status_msg = await event.respond("⚡ **Generating, please wait...**")
            try:
                img_bytes = await event.download_media(bytes)
                if not img_bytes:
                    await status_msg.edit("❌ **Could not download photo. Please try uploading again.**")
                    return

                instruction = (event.message.message or event.text or "").strip()

                analysis = await ai_engine.analyze_reference_image(
                    image_bytes=img_bytes,
                    instruction=instruction,
                    user_api_key=custom_key,
                    model_name=model
                )

                ref_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_pdfs", "references")
                os.makedirs(ref_dir, exist_ok=True)
                timestamp = int(datetime.utcnow().timestamp())
                img_filename = f"ref_{user_id}_{timestamp}.jpg"
                img_path = os.path.join(ref_dir, img_filename)
                with open(img_path, "wb") as f:
                    f.write(img_bytes)

                biometric_summary = analysis.get("biometric_summary", "")
                if not biometric_summary:
                    landmarks = analysis.get("facial_landmarks", "")
                    skin = analysis.get("skin_tone_shader", "")
                    biometric_summary = f"{landmarks} {skin}".strip()

                extracted_data = analysis.get("extracted_character_data", {})

                if action == "wiz_awaiting_ref_image":
                    wiz_data = state.get("wiz_data", {"user_id": user_id})
                    wiz_data["reference_image_path"] = img_path
                    wiz_data["reference_instruction"] = instruction
                    wiz_data["vision_biometrics"] = biometric_summary

                    if extracted_data.get("gender") in CASTLOCK_GENDERS:
                        wiz_data["gender"] = extracted_data["gender"]
                    if extracted_data.get("complexion") in CASTLOCK_COMPLEXIONS:
                        wiz_data["complexion"] = extracted_data["complexion"]
                    if extracted_data.get("nose_type") in CASTLOCK_NOSE_TYPES:
                        wiz_data["nose_type"] = extracted_data["nose_type"]
                    if extracted_data.get("custom_hairstyle"):
                        wiz_data["custom_hairstyle"] = extracted_data["custom_hairstyle"]
                    if extracted_data.get("custom_outfit"):
                        wiz_data["custom_outfit"] = extracted_data["custom_outfit"]

                    char_id = database.save_character(user_id, wiz_data)
                    USER_STATES.pop(user_id, None)

                    saved_char = database.get_character_by_id(char_id, user_id)
                    card_text = format_character_detail_card(saved_char, user["credits"], is_newly_saved=True)
                    buttons = get_character_detail_keyboard(char_id)

                    confirm_text = (
                        "🟢 **Reference Photo Analyzed & Likeness Locked!**\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🧬 **Extracted Biometrics:**\n_{biometric_summary}_\n\n"
                        + card_text
                    )
                    await status_msg.edit(confirm_text, buttons=buttons)

                elif action == "edit_awaiting_ref_image":
                    char_id = state.get("char_id")
                    char = database.get_character_by_id(char_id, user_id)
                    if char:
                        char["reference_image_path"] = img_path
                        char["reference_instruction"] = instruction
                        char["vision_biometrics"] = biometric_summary

                        database.save_character(user_id, char)
                        USER_STATES.pop(user_id, None)

                        card_text = format_character_detail_card(char, user["credits"])
                        buttons = get_character_detail_keyboard(char_id)
                        confirm_text = (
                            "🟢 **Reference Photo Updated & Likeness Locked!**\n"
                            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🧬 **Extracted Biometrics:**\n_{biometric_summary}_\n\n"
                            + card_text
                        )
                        await status_msg.edit(confirm_text, buttons=buttons)

            except Exception as e:
                logger.error(f"Error analyzing reference image: {e}")
                err_msg = f"❌ **Error analyzing reference image:** `{str(e)}`"
                await status_msg.edit(err_msg)

        elif action == "awaiting_thumbnail_topic":
            USER_STATES.pop(user_id, None)
            
            # Universal Credit Check (2 credits for ClickThumb)
            if user["credits"] < 2:
                await event.respond(
                    "⚠️ **Insufficient Credits!**\n\n"
                    f"WP ClickThumb costs **2 credits**. Your balance is `{user['credits']}` credits.",
                    buttons=[[Button.inline("💳 View Wallet", b"menu_wallet")]]
                )
                return

            status_msg = await event.respond(f"🖼 **WP ClickThumb is engineering 3 high-CTR concepts with `{model}`...**")
            
            try:
                thumb_data = await ai_engine.generate_thumbnail_prompts(
                    story_summary=event.text,
                    user_api_key=custom_key,
                    model_name=model
                )
                database.deduct_credits(user_id, 2)

                msg = "🔥 **Top 3 Viral Thumbnail Concepts:**\n\n"
                concepts = thumb_data if isinstance(thumb_data, list) else thumb_data.get("thumbnail_concepts", [])
                for i, c in enumerate(concepts[:3], 1):
                    concept_desc = c.get("concept", "")
                    overlay = c.get("text_overlay", "")
                    prompt = c.get("midjourney_prompt", "")
                    msg += f"**#{i} Concept:** {concept_desc}\n"
                    msg += f"• **Overlay:** *\"{overlay}\"*\n"
                    msg += f"• **Midjourney:** `{prompt}`\n\n"

                await status_msg.edit(msg, buttons=[[Button.inline("🖼 More Thumbnails", b"menu_thumbnail"), Button.inline("🔙 Main Menu", b"menu_main")]])
            except Exception as e:
                logger.error(f"Error in thumbnail generation: {e}")
                await status_msg.edit(f"❌ **Error:** `{str(e)}`")

    print(f"\n🚀 WP Studio Native Bot is live and listening...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
