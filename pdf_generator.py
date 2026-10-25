import os
import re
from datetime import datetime
import fitz
from markdown_pdf import MarkdownPdf, Section

DARK_THEME_CSS = """
body {
    background-color: #0b0f19;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    font-size: 9.5pt;
    line-height: 1.5;
}

h1 {
    color: #ffffff;
    font-size: 18pt;
    font-weight: 800;
    letter-spacing: -0.3px;
    margin-top: 16pt;
    margin-bottom: 8pt;
    border-bottom: 1.5pt solid #1e293b;
    padding-bottom: 6pt;
}

h2 {
    color: #f1f5f9;
    font-size: 13pt;
    font-weight: 700;
    margin-top: 14pt;
    margin-bottom: 6pt;
}

h3 {
    color: #38bdf8;
    font-size: 11pt;
    font-weight: 700;
    margin-top: 12pt;
    margin-bottom: 4pt;
}

p {
    margin-top: 4pt;
    margin-bottom: 6pt;
    color: #cbd5e1;
}

strong {
    color: #ffffff;
    font-weight: 700;
}

em {
    color: #94a3b8;
}

blockquote {
    background-color: #111827;
    border-left: 3.5pt solid #0a84ff;
    color: #f8fafc;
    padding: 8pt 12pt;
    margin: 6pt 0 10pt 0;
    border-radius: 4pt;
}

code {
    background-color: #1e293b;
    color: #38bdf8;
    border: 0.5pt solid #334155;
    padding: 1.5pt 4pt;
    border-radius: 3pt;
    font-family: 'Courier New', monospace;
    font-size: 8.5pt;
}

hr {
    border: 0;
    border-top: 0.8pt solid #1e293b;
    margin: 14pt 0;
}

ul, ol {
    margin-top: 4pt;
    margin-bottom: 8pt;
    padding-left: 18pt;
    color: #cbd5e1;
}

li {
    margin-bottom: 3pt;
}
"""

def apply_dark_theme(pdf_path: str):
    """Paints a full-bleed dark background (#0b0f19) onto all pages of the generated PDF."""
    try:
        doc = fitz.open(pdf_path)
        bg = (11 / 255, 15 / 255, 25 / 255)  # #0b0f19 dark navy
        for page in doc:
            shape = page.new_shape()
            shape.draw_rect(page.rect)
            shape.finish(color=None, fill=bg)
            shape.commit(overlay=False)
        temp_path = f"{pdf_path}.tmp"
        doc.save(temp_path)
        doc.close()
        os.replace(temp_path, pdf_path)
    except Exception as e:
        print(f"Warning: Failed to apply full bleed dark theme background: {e}")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_\- ]', '', name)
    return cleaned.strip().replace(' ', '_')[:35] or "wp_studio"

def format_hashtags(tags: list) -> str:
    if not tags:
        return ""
    formatted = []
    for t in tags:
        t_clean = t.strip()
        if not t_clean.startswith("#"):
            t_clean = f"#{t_clean}"
        formatted.append(f"`{t_clean}`")
    return " ".join(formatted)

def generate_image_prompts_pdf(story_data: dict, culture="Universal", style="Stylised 3D", genre="Action Thriller", delivery_format="Dialogue / Narrative", lead_character=None, length_tier="Short", timezone="Africa/Lagos") -> str:
    """
    Master Production PDF 1: IMAGE PRODUCTION PROMPTS
    Includes Cover, Viral Hashtags, Posting Window, Creative Brief, Cast Likeness Bible,
    Location Worldbuilding Bible, and 100% Self-Contained Scene Image Prompts.
    """
    title = story_data.get("title", "WP Studio Production Package")
    genre = story_data.get("genre", genre)
    delivery = story_data.get("delivery_format", delivery_format)
    logline = story_data.get("logline", story_data.get("hook", ""))
    hook = story_data.get("hook", "")
    theme = story_data.get("theme_and_takeaway", "High-Retention Visual Storytelling")
    synopsis = story_data.get("synopsis", "")
    hashtags = story_data.get("hashtags", [])
    posting = story_data.get("posting_schedule", {})
    if isinstance(posting, dict):
        posting_text = f"- **TikTok:** {posting.get('tiktok', 'Prime evenings')}\n- **YouTube:** {posting.get('youtube', 'Peak browse hours')}\n- **Instagram:** {posting.get('instagram', 'Peak engagement slots')}"
    else:
        posting_text = str(posting)

    lead_section = ""
    if lead_character and isinstance(lead_character, dict):
        lead_name = lead_character.get("name", "Protagonist")
        lead_section = f"\n### 👑 Lead Protagonist (CastLock Continuity)\n**{lead_name}** *(👑 WP CastLock Verified Continuity Anchor)*\n"

    characters = story_data.get("characters", [])
    locations = story_data.get("locations", [])
    scenes = story_data.get("scenes", [])
    filter_lock = story_data.get("visual_filter_lock", f"Cinematic realism, shot on ARRI Alexa, {style} style.")

    safe_title = sanitize_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"WP_Studio_Image_Prompts_{safe_title}_{timestamp}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)

    runtime_lookup = {
        "Short": "~2 to 4 Mins",
        "Medium": "~8 to 15 Mins",
        "Long": "~1 to 2+ Hours"
    }
    est_runtime = story_data.get("runtime_detail") or story_data.get("estimated_runtime") or runtime_lookup.get(length_tier, "~2 to 4 Mins")

    md = f"""# WP STUDIO | AI STORY STUDIO
### STORY PACKAGE  |  IMAGE PRODUCTION PROMPTS
# 🎬 {title}
**{genre.upper()}**

> *"{logline}"*

---

### 🏷️ Viral Distribution Tags
{format_hashtags(hashtags)}

### ⏰ Best Time To Post ({timezone})
{posting_text}

> ⏱️ **ESTIMATED RUNTIME:** `{est_runtime}` &nbsp;&bull;&nbsp; 🎬 **SCENES:** `{len(scenes)}` &nbsp;&bull;&nbsp; 👥 **CHARACTERS:** `{len(characters)}` &nbsp;&bull;&nbsp; 📍 **LOCATIONS:** `{len(locations)}` &nbsp;&bull;&nbsp; 📅 **PRODUCTION DATE:** `{datetime.now().strftime('%B %d, %Y')}`

---

# 📖 CREATIVE BRIEF
### Story Delivery & Audio Format
**{delivery}**
{lead_section}
### Theme & Core Takeaway
**{theme}**

### Executive Synopsis
{synopsis}

### ⚡ 5-Second Retention Hook
> *"{hook}"*

### 💡 How To Use This Document
Every image prompt in this package is **fully self-contained**: copy it directly into your AI image generator (**Google Flow, Midjourney v6, Flux.1, DALL-E 3, Leonardo AI**). Character descriptions and facial structures are locked and repeated verbatim in every scene so faces and builds remain consistent. Add your preferred aspect ratio (`--ar 16:9` or `--ar 9:16`) when pasting into your generator.

---

# 👥 CAST & CONSISTENCY
### Character Bible
*Locked descriptions below must be reused verbatim in every prompt for visual consistency across AI-generated scenes.*

"""

    for char in characters:
        c_name = char.get("name", "Character")
        c_role = char.get("role", "SUPPORTING")
        is_castlock_lead = False
        if lead_character and isinstance(lead_character, dict):
            locked_name = lead_character.get("name", "").lower()
            if locked_name and (locked_name in c_name.lower() or c_name.lower() in locked_name or c_role.upper() == "PROTAGONIST"):
                is_castlock_lead = True

        lead_badge = " *(👑 WP CastLock Verified Lead)*" if is_castlock_lead else ""
        c_desc = char.get("locked_visual_description", "")
        c_expr = char.get("expression_keywords", "Controlled, story-appropriate")
        c_lock = char.get("identity_lock_statement", f"IDENTITY LOCK: {c_name}'s facial features, hairstyle, skin tone, build, and overall appearance must remain consistent.")

        md += f"""### {c_name}{lead_badge}
**ROLE:** `{c_role}`  
**HEAD-TO-TOE FULL BODY CHARACTER REFERENCE PROMPT:**  
> {c_desc}  

**EXPRESSION PROFILE:**  
Reflecting: *{c_expr}*.  

> **{c_lock}**

---
"""

    if locations:
        md += """# 🌍 WORLD BUILDING
### Location Bible
*Empty, unoccupied reference views establishing setting, lighting, and environmental texture with no people or characters.*

"""
        for loc in locations:
            l_name = loc.get("name", "Location")
            l_ref = loc.get("unoccupied_reference", "")
            md += f"""### 📍 {l_name}
{l_ref}

---
"""

    md += f"""# 🎥 PRODUCTION
### Scene-by-Scene Image Prompts
*{len(scenes)} scenes — each prompt is fully self-contained with locked character descriptions, lens choice, spatial staging, and negative prompt filtering.*

"""

    for s in scenes:
        s_num = s.get("scene_number", 1)
        s_title = s.get("scene_title", f"Scene {s_num}")
        s_type = s.get("scene_type", "Action")
        s_dur = s.get("duration", "5s")
        s_persp = s.get("camera_perspective", "objective")
        s_chars = ", ".join(s.get("characters_present", [])) or "None"
        s_loc = s.get("location", "Main Setting")
        s_narr = s.get("narration", "")
        s_prompt = s.get("image_prompt", "")

        md += f"""### SC {s_num} — {s_title}
`{s_type}` | `{s_dur}` | `{s_persp}`  
**CHARACTERS:** {s_chars}  
**LOCATION:** {s_loc}  

**🎙️ Spoken Line (Voiceover):**  
> *"{s_narr}"*

**🖼️ COPY-READY IMAGE PROMPT (Google Flow / Midjourney v6 / Flux):**  
> {s_prompt}

---
"""

    md += """*Prepared by WP Studio AI Story Studio — Flagship YouTube Automation Suite.*
"""

    pdf = MarkdownPdf(toc_level=2)
    pdf.add_section(Section(md), user_css=DARK_THEME_CSS)
    pdf.save(pdf_path)
    apply_dark_theme(pdf_path)
    return pdf_path

def generate_video_prompts_pdf(story_data: dict, culture="Universal", style="Stylised 3D", genre="Action Thriller", delivery_format="Dialogue / Narrative", lead_character=None, length_tier="Short", timezone="Africa/Lagos") -> str:
    """
    Master Production PDF 2: VIDEO PRODUCTION PROMPTS
    Engineered specifically for Google Flow / Veo, Kling AI, and Runway Gen-3.
    Includes Opening Frame Anchors, Physical Motion, End State, Embedded Dialogue, and Audio Constraints.
    """
    title = story_data.get("title", "WP Studio Production Package")
    genre = story_data.get("genre", genre)
    delivery = story_data.get("delivery_format", delivery_format)
    logline = story_data.get("logline", story_data.get("hook", ""))
    theme = story_data.get("theme_and_takeaway", "High-Retention Visual Storytelling")
    synopsis = story_data.get("synopsis", "")
    hashtags = story_data.get("hashtags", [])
    posting = story_data.get("posting_schedule", {})
    if isinstance(posting, dict):
        posting_text = f"- **TikTok:** {posting.get('tiktok', 'Prime evenings')}\n- **YouTube:** {posting.get('youtube', 'Peak browse hours')}\n- **Instagram:** {posting.get('instagram', 'Peak engagement slots')}"
    else:
        posting_text = str(posting)

    lead_section = ""
    if lead_character and isinstance(lead_character, dict):
        lead_name = lead_character.get("name", "Protagonist")
        lead_section = f"\n### 👑 Lead Protagonist (CastLock Continuity)\n**{lead_name}** *(👑 WP CastLock Verified Continuity Anchor)*\n"

    characters = story_data.get("characters", [])
    locations = story_data.get("locations", [])
    scenes = story_data.get("scenes", [])

    safe_title = sanitize_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"WP_Studio_Video_Prompts_{safe_title}_{timestamp}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)

    runtime_lookup = {
        "Short": "~2 to 4 Mins",
        "Medium": "~8 to 15 Mins",
        "Long": "~1 to 2+ Hours"
    }
    est_runtime = story_data.get("runtime_detail") or story_data.get("estimated_runtime") or runtime_lookup.get(length_tier, "~2 to 4 Mins")

    md = f"""# WP STUDIO | AI STORY STUDIO
### STORY PACKAGE  |  VIDEO PRODUCTION PROMPTS
# 🎬 {title}
**{genre.upper()}**

> *"{logline}"*

---

### 🏷️ Viral Distribution Tags
{format_hashtags(hashtags)}

### ⏰ Best Time To Post ({timezone})
{posting_text}

> ⏱️ **ESTIMATED RUNTIME:** `{est_runtime}` &nbsp;&bull;&nbsp; 🎬 **SCENES:** `{len(scenes)}` &nbsp;&bull;&nbsp; 👥 **CHARACTERS:** `{len(characters)}` &nbsp;&bull;&nbsp; 📍 **LOCATIONS:** `{len(locations)}` &nbsp;&bull;&nbsp; 📅 **PRODUCTION DATE:** `{datetime.now().strftime('%B %d, %Y')}`

---

# 📖 CREATIVE BRIEF
### Story Delivery & Audio Format
**{delivery}**
{lead_section}
### Theme & Core Takeaway
**{theme}**

### Executive Synopsis
{synopsis}

### 💡 How To Use This Document
Every video prompt in this package is **fully self-contained**: copy it directly into your AI video generator (**Google Flow, Kling AI, Runway Gen-3, Luma Dream Machine**). 
Each prompt begins with an **Opening Frame Anchor**, details **Chronological Physical Motion**, establishes a defined **End State**, and includes **Visual Filter Locks** and **Audio Constraints** to prevent distortion.

---

# 🎥 PRODUCTION
### Scene-by-Scene Video Prompts
*{len(scenes)} scenes — each prompt is fully self-contained with camera direction, physical movement, end state, and embedded dialogue.*

"""

    for s in scenes:
        s_num = s.get("scene_number", 1)
        s_title = s.get("scene_title", f"Scene {s_num}")
        s_type = s.get("scene_type", "Action")
        s_dur = s.get("duration", "5s")
        s_persp = s.get("camera_perspective", "objective")
        s_chars = ", ".join(s.get("characters_present", [])) or "None"
        s_loc = s.get("location", "Main Setting")
        s_dialogue = s.get("dialogue", "")
        s_narr = s.get("narration", "")
        s_video = s.get("video_prompt", "")

        md += f"""### SC {s_num} — {s_title}
`{s_type}` | `{s_dur}` | `{s_persp}`  
**CHARACTERS:** {s_chars}  
**LOCATION:** {s_loc}  

"""
        if s_dialogue and s_dialogue.strip():
            md += f"""**🗣️ DIALOGUE:**  
> **{s_dialogue}**  

"""

        if s_narr and s_narr.strip():
            md += f"""**🎙️ Spoken Line (Voiceover):**  
> *"{s_narr}"*

"""

        md += f"""**📹 COPY-READY VIDEO PROMPT (Google Flow / Kling / Runway):**  
> {s_video}

---
"""

    md += """*Prepared by WP Studio AI Story Studio — Flagship YouTube Automation Suite.*
"""

    pdf = MarkdownPdf(toc_level=2)
    pdf.add_section(Section(md), user_css=DARK_THEME_CSS)
    pdf.save(pdf_path)
    apply_dark_theme(pdf_path)
    return pdf_path

def generate_dual_pdfs(story_data: dict, culture="Universal", style="Stylised 3D", genre="Action Thriller", delivery_format="Dialogue / Narrative", lead_character=None, length_tier="Short", timezone="Africa/Lagos") -> tuple:
    """Generates both Master Image Prompts PDF and Master Video Prompts PDF."""
    image_pdf = generate_image_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    video_pdf = generate_video_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    return image_pdf, video_pdf

def generate_character_forge_pdf(char_data: dict, style="Stylised 3D") -> str:
    """Compiles a dedicated 9-Panel 3D Character Model Sheet & Turnaround PDF."""
    c_name = char_data.get("character_name", "Character")
    c_style = char_data.get("visual_style", style)
    c_bible = char_data.get("consistency_bible", "")
    c_master = char_data.get("master_9panel_sheet_prompt", char_data.get("turnaround_prompt", ""))
    angles = char_data.get("angle_prompts", {})
    c_action = char_data.get("action_prompt", "")
    params = char_data.get("recommended_midjourney_params", "--ar 9:16 --v 6.1 --stylize 250")

    safe_name = sanitize_filename(c_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"WP_CastLock_3D_ModelSheet_{safe_name}_{timestamp}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)

    md = f"""# WP STUDIO | CASTLOCK 3D CHARACTER MODEL SHEET
### AAA 3D PRODUCTION SPECIFICATION  |  9-PANEL TURNAROUND SUITE
# 🎭 {c_name}
**Visual Style:** `{c_style}`  
**Date:** {datetime.now().strftime('%B %d, %Y')}  
**Recommended Generation Aspect Ratio:** `{params}`

---

# 📋 1. Continuity & Anatomical Trait Bible
{c_bible}

---

# 🚀 2. MASTER 9-PANEL 3D TURNAROUND MODEL SHEET PROMPT
*Use this master prompt in Midjourney v6, Flux.1, or Google Flow to generate the complete 3x3 reference sheet (all corners, all faces, full body, close-ups, hairstyle, and uniform textures in a single image):*

> {c_master}

---

# 📸 3. INDIVIDUAL 4K ANGLE PROMPTS
*For generating individual high-resolution single-angle renders:*

### Panel 1: [FRONT] Full Body Standing
> {angles.get('front_full_body', 'Full body standing front view, neutral A-pose, uniform neutral studio background.')}

### Panel 2: [THREE-QUARTER] Full Body Standing
> {angles.get('three_quarter_full_body', 'Full body standing three-quarter 45-degree angle view, neutral studio background.')}

### Panel 3: [PROFILE] 90-Degree Side Profile Full Body
> {angles.get('profile_full_body', 'Full body standing 90-degree side profile view, neutral studio background.')}

### Panel 4: [BACK] Full Body Standing
> {angles.get('back_full_body', 'Full body standing back view showing hair and rear silhouette, neutral studio background.')}

### Panel 5: [FRONT CLOSE-UP] Headshot Portrait
> {angles.get('front_close_up', 'Close-up headshot portrait, direct eye contact, subsurface scattering skin shader, studio lighting.')}

### Panel 6: [THREE-QUARTER CLOSE-UP] Headshot Portrait
> {angles.get('three_quarter_close_up', 'Close-up headshot at 45-degree angle, cheekbone and jawline definition, studio lighting.')}

### Panel 7: [PROFILE CLOSE-UP] 90-Degree Side Headshot
> {angles.get('profile_close_up', 'Close-up 90-degree side profile headshot, ear, nose, and jawline detail, studio lighting.')}

### Panel 8: [HAIRSTYLE DETAIL] Back of Head Close-Up
> {angles.get('hairstyle_detail', 'Extreme close-up of the back of the head showing intricate braiding and grooming structure.')}

### Panel 9: [WARDROBE DETAIL] Torso & Fabric Texture Close-Up
> {angles.get('wardrobe_detail', 'Close-up of torso and garment construction showing collar, buttons, seams, and fabric weave.')}

---

# ⚡ 4. DYNAMIC ACTION PROMPT
*Showcase your character in full cinematic action inside their native environment:*

> {c_action}

---
*Generated by WP Studio CastLock 3D Engine — 100% Identical Continuity Across Every Animation & Scene.*
"""

    pdf = MarkdownPdf(toc_level=2)
    pdf.add_section(Section(md), user_css=DARK_THEME_CSS)
    pdf.save(pdf_path)
    apply_dark_theme(pdf_path)
    return pdf_path
