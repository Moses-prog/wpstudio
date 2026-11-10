import os
import re
import gc
from datetime import datetime
from markdown_pdf import MarkdownPdf, Section
import fitz  # PyMuPDF

# Executive Dark Mode CSS for PDF Generation (Obsidian & Champagne Gold Studio Design System)
DARK_THEME_CSS = """
@page {
    size: A4;
    margin: 32pt 36pt 42pt 36pt;
    background-color: #0b0e14;
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    background-color: #0b0e14;
    color: #e2e8f0;
    line-height: 1.55;
    font-size: 9.5pt;
    margin: 0;
    padding: 0;
}

h1 {
    color: #ffffff;
    font-size: 16pt;
    font-weight: 800;
    margin-top: 8pt;
    margin-bottom: 6pt;
    letter-spacing: -0.3pt;
    text-transform: uppercase;
}

h2 {
    color: #d4af37;
    font-size: 11.5pt;
    font-weight: 700;
    margin-top: 12pt;
    margin-bottom: 5pt;
    text-transform: uppercase;
    letter-spacing: 0.8pt;
}

h3 {
    color: #f8fafc;
    font-size: 10pt;
    font-weight: 700;
    margin-top: 8pt;
    margin-bottom: 4pt;
}

p {
    color: #cbd5e1;
    margin-top: 3pt;
    margin-bottom: 6pt;
}

strong {
    color: #ffffff;
    font-weight: 700;
}

em {
    color: #94a3b8;
}

/* Executive Studio Header Card */
.studio-header {
    background-color: #121622;
    border: 0.8pt solid #222b3d;
    border-top: 2.5pt solid #d4af37;
    border-radius: 4pt;
    padding: 10pt 14pt;
    margin-bottom: 12pt;
}

.studio-title {
    font-size: 15pt;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.2pt;
    margin-bottom: 4pt;
}

.studio-subtitle {
    font-size: 8pt;
    font-weight: 700;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 1pt;
    margin-bottom: 6pt;
}

.meta-grid {
    margin-top: 6pt;
    padding-top: 6pt;
    border-top: 0.6pt solid #1e2638;
}

.meta-pill {
    display: inline-block;
    background-color: #171d2b;
    border: 0.5pt solid #2c374d;
    color: #d4af37;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 2pt 6pt;
    border-radius: 3pt;
    margin-right: 4pt;
    margin-bottom: 3pt;
}

.meta-pill-slate {
    display: inline-block;
    background-color: #171d2b;
    border: 0.5pt solid #2c374d;
    color: #94a3b8;
    font-size: 7.5pt;
    font-weight: 600;
    padding: 2pt 6pt;
    border-radius: 3pt;
    margin-right: 4pt;
    margin-bottom: 3pt;
}

/* Executive Scene & Section Cards */
.scene-card {
    background-color: #10141f;
    border: 0.8pt solid #1f2738;
    border-radius: 4pt;
    padding: 9pt 12pt;
    margin-top: 8pt;
    margin-bottom: 10pt;
}

.scene-title {
    color: #ffffff;
    font-size: 10.5pt;
    font-weight: 800;
    margin-bottom: 4pt;
}

/* Dedicated Prompt Vault Containers */
.prompt-vault {
    background-color: #07090d;
    border: 0.8pt solid #222b3e;
    border-left: 2.5pt solid #38bdf8;
    border-radius: 3.5pt;
    padding: 7pt 10pt;
    font-family: 'Courier New', monospace;
    font-size: 8pt;
    color: #e2e8f0;
    line-height: 1.45;
    margin-top: 5pt;
    margin-bottom: 6pt;
}

.prompt-vault-video {
    background-color: #07090d;
    border: 0.8pt solid #222b3e;
    border-left: 2.5pt solid #d4af37;
    border-radius: 3.5pt;
    padding: 7pt 10pt;
    font-family: 'Courier New', monospace;
    font-size: 8pt;
    color: #e2e8f0;
    line-height: 1.45;
    margin-top: 5pt;
    margin-bottom: 6pt;
}

.prompt-label {
    font-size: 7pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8pt;
    margin-bottom: 3pt;
    display: block;
}

.prompt-label-blue {
    color: #38bdf8;
    font-size: 7pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8pt;
    margin-bottom: 3pt;
    display: block;
}

.prompt-label-gold {
    color: #d4af37;
    font-size: 7pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.8pt;
    margin-bottom: 3pt;
    display: block;
}

/* Script Dialogue Formatting */
.dialogue-card {
    background-color: #0d111a;
    border-left: 2pt solid #475569;
    padding: 6pt 10pt;
    margin: 4pt 0 6pt 6pt;
    border-radius: 0 3pt 3pt 0;
}

.speaker-tag {
    font-size: 8pt;
    font-weight: 800;
    color: #d4af37;
    text-transform: uppercase;
    letter-spacing: 0.5pt;
}

.delivery-cue {
    font-size: 7.5pt;
    font-style: italic;
    color: #94a3b8;
    margin-left: 4pt;
}

.dialogue-text {
    font-size: 9pt;
    color: #f1f5f9;
    margin-top: 2pt;
    line-height: 1.45;
}

blockquote {
    background-color: #121622;
    border-left: 3pt solid #d4af37;
    color: #f8fafc;
    padding: 7pt 11pt;
    margin: 6pt 0 8pt 0;
    border-radius: 3pt;
}

code {
    background-color: #171d2b;
    color: #38bdf8;
    border: 0.5pt solid #2c374d;
    padding: 1.5pt 3.5pt;
    border-radius: 2.5pt;
    font-family: 'Courier New', monospace;
    font-size: 8pt;
}

hr {
    border: 0;
    border-top: 0.6pt solid #1e2638;
    margin: 10pt 0;
}

ul, ol {
    margin-top: 3pt;
    margin-bottom: 6pt;
    padding-left: 16pt;
    color: #cbd5e1;
}

li {
    margin-bottom: 2.5pt;
}
"""

def apply_dark_theme(pdf_path: str, doc_category: str = "PRODUCTION SPECIFICATION"):
    """
    Paints a full-bleed executive dark background (#0b0e14) onto all pages of the generated PDF,
    with top gold hairline rules, running headers on continuation pages, and running footers with Page X of Y.
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        bg = (11 / 255, 14 / 255, 20 / 255)       # #0b0e14 obsidian dark
        gold = (212 / 255, 175 / 255, 55 / 255)   # #d4af37 champagne gold
        border = (31 / 255, 39 / 255, 56 / 255)   # #1f2738 subtle border
        slate = (148 / 255, 163 / 255, 184 / 255) # #94a3b8 slate
        dim = (100 / 255, 116 / 255, 139 / 255)   # #64748b dim

        for idx, page in enumerate(doc, 1):
            # 1. Full bleed background
            shape = page.new_shape()
            shape.draw_rect(page.rect)
            shape.finish(color=None, fill=bg)
            shape.commit(overlay=False)

            w = page.rect.width
            h = page.rect.height

            # 2. Top gold hairline accent rule on all pages
            top_shape = page.new_shape()
            top_shape.draw_line(fitz.Point(36, 26), fitz.Point(w - 36, 26))
            top_shape.finish(color=gold, width=0.8)
            top_shape.commit(overlay=True)

            # 3. Running header text on continuation pages
            if idx > 1:
                page.insert_text(
                    fitz.Point(36, 21),
                    f"WP STUDIO CREATIVE PRODUCTION PIPELINE  |  {doc_category.upper()}",
                    fontsize=6.8,
                    color=slate,
                    fontname="helv"
                )

            # 4. Bottom subtle border rule on all pages
            bot_shape = page.new_shape()
            bot_shape.draw_line(fitz.Point(36, h - 30), fitz.Point(w - 36, h - 30))
            bot_shape.finish(color=border, width=0.6)
            bot_shape.commit(overlay=True)

            # 5. Running footer left
            page.insert_text(
                fitz.Point(36, h - 18),
                f"WP STUDIO  -  CONFIDENTIAL  -  {doc_category.upper()}",
                fontsize=6.5,
                color=dim,
                fontname="helv"
            )

            # 6. Running footer right: Page X of Y in gold
            page_str = f"Page {idx} of {total_pages}"
            text_w = fitz.get_text_length(page_str, fontname="helv", fontsize=7)
            page.insert_text(
                fitz.Point(w - 36 - text_w, h - 18),
                page_str,
                fontsize=7,
                color=gold,
                fontname="helv"
            )

        temp_path = f"{pdf_path}.tmp"
        doc.save(temp_path)
        doc.close()
        os.replace(temp_path, pdf_path)
    except Exception as e:
        print(f"Warning: Failed to apply executive theme decoration: {e}")
    finally:
        gc.collect()

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_\- ]', '', str(name or "wp_studio"))
    return cleaned.strip().replace(' ', '_')[:35] or "wp_studio"

def format_hashtags(tags: list) -> str:
    if not tags:
        return ""
    formatted = []
    for t in tags:
        t_clean = str(t).strip()
        if not t_clean:
            continue
        if not t_clean.startswith("#"):
            t_clean = f"#{t_clean}"
        formatted.append(f"`{t_clean}`")
    return " ".join(formatted)


def _normalize_characters_and_locations(story_data: dict, style: str = "Realistic") -> tuple:
    """
    Guarantees that:
    1. Every character has a complete Full-Body Head-to-Toe Character Sheet Prompt.
    2. Every location (especially locations appearing in multiple scenes) has a complete
       Unoccupied Location Consistency Prompt and a list of scenes where it appears.
    """
    scenes = story_data.get("scenes", []) or []
    raw_chars = story_data.get("characters", []) or []
    raw_locs = story_data.get("locations", []) or []

    # 1. Normalize Characters
    normalized_chars = []
    for char in raw_chars:
        if not isinstance(char, dict):
            continue
        c_name = char.get("name", "Character")
        c_orig = char.get("original_name", "")
        c_role = char.get("role", "SUPPORTING")
        c_locked = char.get("locked_visual_description") or char.get("visual_lock") or ""
        c_vis = char.get("visual_description") or char.get("visual_lock") or ""
        if not c_locked and c_vis:
            c_locked = (
                f"Full-length standing shot, complete head-to-toe uncropped full body view showing entire figure "
                f"from shoes on the floor to top of head, eye-level angle. {c_name}: {c_vis}. "
                f"Standing in relaxed posture facing camera on a neutral grey seamless studio background, "
                f"soft studio lighting, {style} cinematic render, sharp focus head-to-toe. "
                f"No cut off legs, no cut off shoes, no text, no watermarks."
            )
        elif not c_locked:
            c_locked = (
                f"Full-length standing shot, complete head-to-toe uncropped full body view showing entire figure "
                f"from shoes on the floor to top of head, eye-level angle. {c_name} ({c_role}), "
                f"standing in relaxed posture facing camera on a neutral grey seamless studio background, "
                f"soft studio lighting, {style} cinematic render. No cut off legs, no cut off shoes, no text."
            )
        normalized_chars.append({
            "name": c_name,
            "original_name": c_orig,
            "role": c_role,
            "locked_visual_description": c_locked,
            "visual_description": c_vis or c_locked,
            "expression_keywords": char.get("expression_keywords", "Natural, expressive, story-appropriate"),
            "wardrobe_lock": char.get("wardrobe_lock", ""),
            "identity_lock_statement": char.get(
                "identity_lock_statement",
                f"IDENTITY LOCK: {c_name}'s facial features, hairstyle, skin tone, build, and wardrobe must remain consistent across all scenes."
            )
        })

    # 2. Map scene locations to track recurring locations (locations appearing more than once)
    scene_loc_map = {}
    stop_words = {"the", "a", "an", "in", "at", "of", "on", "to", "and", "room", "area", "interior", "exterior", "int", "ext", "day", "night", "evening", "morning"}

    def _clean_base_loc(raw_label: str) -> str:
        cleaned = re.sub(r'^(INT\.|EXT\.|INT/EXT\.|INTERIOR|EXTERIOR)\s*[-:]?\s*', '', raw_label, flags=re.IGNORECASE)
        cleaned = re.split(r'\s*[-—–]\s*(DAY|NIGHT|MORNING|EVENING|DUSK|DAWN|LATER|CONTINUOUS|AFTERNOON|SUNSET|MIDNIGHT).*$', cleaned, flags=re.IGNORECASE)[0].strip()
        return cleaned or raw_label.strip()

    def _loc_tokens(label: str) -> set:
        words = re.findall(r'[a-z0-9]+', label.lower())
        return {w for w in words if len(w) > 2 and w not in stop_words}

    for s in scenes:
        if not isinstance(s, dict):
            continue
        s_num = s.get("scene_number", 1)
        loc_label = (s.get("location") or s.get("setting") or "").strip()
        if not loc_label:
            continue
        base_loc = _clean_base_loc(loc_label)
        key = re.sub(r'^the\s+', '', base_loc.lower()).strip()
        tokens = _loc_tokens(base_loc)

        # Check if this location matches an already-seen location key by exact key or strong token overlap
        matched_key = None
        if key in scene_loc_map:
            matched_key = key
        else:
            for existing_k, existing_v in scene_loc_map.items():
                if key in existing_k or existing_k in key:
                    matched_key = existing_k
                    break
                existing_tokens = existing_v["tokens"]
                if tokens and existing_tokens and len(tokens & existing_tokens) >= 2:
                    matched_key = existing_k
                    break

        target_key = matched_key or key
        if target_key not in scene_loc_map:
            scene_loc_map[target_key] = {
                "display_name": base_loc,
                "scene_nums": [],
                "tokens": tokens,
                "sample_prompt": s.get("image_prompt", "")
            }
        scene_loc_map[target_key]["scene_nums"].append(s_num)

    # 3. Normalize Locations (merge AI-provided locations + auto-detected recurring locations)
    normalized_locs = []
    seen_loc_keys = set()

    for loc in raw_locs:
        if not isinstance(loc, dict):
            continue
        l_name = (loc.get("name") or loc.get("setting") or "Story Location").strip()
        l_ref = (
            loc.get("unoccupied_reference")
            or loc.get("locked_environment_description")
            or loc.get("visual_description")
            or loc.get("prompt")
            or loc.get("description")
            or ""
        ).strip()
        raw_used = loc.get("scenes_used") or ""
        if isinstance(raw_used, list):
            l_scenes = ", ".join([str(x) for x in raw_used])
        else:
            l_scenes = str(raw_used).strip()

        # Match with scene_loc_map
        matched_nums = []
        l_tokens = _loc_tokens(l_name)
        for k, v in scene_loc_map.items():
            if k in l_name.lower() or l_name.lower() in k or (l_tokens and v["tokens"] and len(l_tokens & v["tokens"]) >= 2):
                matched_nums.extend(v["scene_nums"])
                seen_loc_keys.add(k)

        unique_nums = sorted(list(set(matched_nums)))
        if unique_nums:
            l_scenes = ", ".join([f"Scene {n}" for n in unique_nums])
            count = len(unique_nums)
        else:
            # Count scenes mentioned in l_scenes string
            found_nums = re.findall(r'\d+', l_scenes)
            count = len(set(found_nums)) if found_nums else (2 if "," in l_scenes else 1)

        if not l_ref:
            l_ref = (
                f"Empty, unoccupied reference view with no people or characters. Wide establishing shot, 24mm anamorphic lens. "
                f"{l_name}, consistent architectural layout, natural and practical lighting fixtures, rich environmental textures, "
                f"foreground and background depth, {style} cinematic style. Use this background reference across {l_scenes or 'all matching scenes'} "
                f"so the movie environment looks realistic and identical. No people, no text, no watermarks."
            )

        normalized_locs.append({
            "name": l_name,
            "scenes_used": l_scenes or "Multiple Scenes",
            "appearance_count": count,
            "is_recurring": count >= 2 or ("," in l_scenes),
            "unoccupied_reference": l_ref
        })

    # Add all auto-detected locations from scenes that weren't in raw_locs
    for k, v in scene_loc_map.items():
        if k in seen_loc_keys:
            continue
        unique_nums = sorted(list(set(v["scene_nums"])))
        count = len(unique_nums)
        # Always include every location that appears more than once (count >= 2), plus top single locations
        if count >= 2 or len(normalized_locs) < 8:
            loc_name = v["display_name"]
            scenes_str = ", ".join([f"Scene {n}" for n in unique_nums])
            ref_prompt = (
                f"Empty, unoccupied reference view with no people or characters. Wide establishing shot, 24mm anamorphic lens. "
                f"{loc_name}, consistent architectural layout, atmospheric lighting, detailed walls, flooring, and practical props, "
                f"deep cinematic perspective, {style} render style. Master location reference for visual consistency across {scenes_str}. "
                f"No people, no characters, no text, no watermarks."
            )
            normalized_locs.append({
                "name": loc_name,
                "scenes_used": scenes_str,
                "appearance_count": count,
                "is_recurring": count >= 2,
                "unoccupied_reference": ref_prompt
            })

    # Sort so recurring locations (appearing more than once) come first, ordered by appearance_count descending
    normalized_locs.sort(key=lambda x: (1 if x.get("is_recurring") else 0, x.get("appearance_count", 1)), reverse=True)

    return normalized_chars, normalized_locs


def _extract_scene_script_text(s: dict, delivery_format: str = "Dialogue / Narrative") -> tuple:
    """
    Extracts clean (narration_text, dialogue_text, combined_text) for a scene.
    """
    narr = (s.get("narration") or "").strip()
    dial = (s.get("dialogue") or "").strip()
    comb = (s.get("dialogue_or_narration") or s.get("voiceover_and_dialogue") or s.get("voiceover") or "").strip()
    song = (s.get("song_lyrics") or "").strip()
    inter = (s.get("interactive_cue") or "").strip()

    if not narr and not dial and comb:
        if "Narrative" in delivery_format and "Dialogue" not in delivery_format:
            narr = comb
        elif "Dialogue" in delivery_format and "Narrative" not in delivery_format:
            dial = comb
        else:
            comb_lines = [ln.strip() for ln in comb.split("\n") if ln.strip()]
            has_speaker = any(":" in ln[:35] for ln in comb_lines)
            if has_speaker:
                dial = comb
            else:
                narr = comb

    parts = []
    if narr:
        parts.append(narr)
    if dial and dial != narr:
        parts.append(dial)
    if song and song not in (narr + dial + comb):
        parts.append(f"[SONG / RHYME]:\n{song}")
    if inter and inter not in (narr + dial + comb):
        parts.append(inter)
    full_scene_script = "\n\n".join(parts) if parts else comb
    return narr, dial, full_scene_script


def generate_voiceover_script_pdf(
    story_data: dict,
    culture="Universal",
    style="Stylised 3D",
    genre="Action Thriller",
    delivery_format="Dialogue / Narrative",
    lead_character=None,
    length_tier="Short",
    timezone="Africa/Lagos"
) -> str:
    """
    Individual Production PDF 1: FULL VOICEOVER & SCREENPLAY SCRIPT PDF
    Dedicated strictly to the spoken narrator voiceover and character script (zero image/camera prompts mixed in),
    ready to read or paste directly into ElevenLabs / TTS voiceover generators.
    """
    title = story_data.get("title", "WP Studio Screenplay")
    genre_val = story_data.get("genre", genre)
    delivery = story_data.get("delivery_format", delivery_format)
    logline = story_data.get("logline", story_data.get("hook", ""))
    hook = story_data.get("hook", "")
    synopsis = story_data.get("synopsis", "")
    hashtags = story_data.get("hashtags", [])
    scenes = story_data.get("scenes", []) or []
    name_changes = story_data.get("name_changes", []) or []

    safe_title = sanitize_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"WP_Studio_Voiceover_Script_{safe_title}_{timestamp}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)

    runtime_lookup = {
        "Short": "~3 to 5 Mins",
        "Medium": "~10 to 15 Mins",
        "Long": "~1 to 2+ Hours"
    }
    est_runtime = (
        story_data.get("runtime_detail")
        or story_data.get("target_duration")
        or story_data.get("estimated_runtime")
        or runtime_lookup.get(length_tier, "~8 to 15 Mins")
    )
    channel_name = story_data.get("channel_name") or "WP Studio Production"
    youtube_desc = story_data.get("youtube_description") or story_data.get("video_description") or ""
    if not youtube_desc:
        youtube_desc = f"{logline}\n\n{synopsis}\n\nSubscribe to {channel_name} for more stories!\n\n{format_hashtags(hashtags)}"

    md = f"""# WP STUDIO | NARRATOR VOICEOVER & SCREENPLAY SCRIPT
### INDIVIDUAL SCRIPT PDF  |  READY FOR VOICEOVER & AUDIO GENERATION
# {title}
**GENRE:** `{genre_val.upper()}`  |  **FORMAT:** `{delivery}`  |  **RUNTIME:** `{est_runtime}`  |  **SCENES:** `{len(scenes)}`

> *"{logline}"*

---
"""

    if hook:
        md += f"""### Opening 5-Second Hook
> *"{hook}"*

"""

    if name_changes:
        md += """### Copyright-Safe Remodeled Names & Locations
"""
        for nc in name_changes:
            if isinstance(nc, dict):
                orig = nc.get("original", "")
                new_val = nc.get("new", "")
                nc_type = nc.get("type", "Remodeled")
                if orig and new_val:
                    md += f"- **{orig}** changed to **{new_val}** *({nc_type})*\n"
        md += "\n---\n"

    # Section 1: Continuous Voiceover Script (Copy-Paste Ready for ElevenLabs / TTS)
    md += """# PART 1: CONTINUOUS FULL VOICEOVER SCRIPT
*Copy and paste this continuous script directly into ElevenLabs or your voiceover generator, or read it straight through.*

"""
    continuous_blocks = []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        _, _, full_text = _extract_scene_script_text(s, delivery)
        if full_text:
            continuous_blocks.append(full_text)

    if continuous_blocks:
        md += "\n\n".join(continuous_blocks) + "\n\n---\n"
    else:
        md += "*No spoken script lines found.*\n\n---\n"

    # Section 2: Scene-by-Scene Timed Voiceover & Dialogue Script
    md += f"""# PART 2: SCENE-BY-SCENE TIMED SCRIPT ({len(scenes)} SCENES)
*Use this section while editing your video to match each voiceover paragraph to its exact scene number.*

"""
    for s in scenes:
        if not isinstance(s, dict):
            continue
        s_num = s.get("scene_number", 1)
        s_title = s.get("scene_title", f"Scene {s_num}")
        s_dur = s.get("estimated_duration") or s.get("duration", "1m 30s")
        s_loc = s.get("location") or s.get("setting") or "Main Setting"
        narr, dial, full_text = _extract_scene_script_text(s, delivery)

        md += f"""### SCENE {s_num}: {s_title}
**SETTING:** `{s_loc}`  |  **DURATION:** `{s_dur}`

"""
        if narr:
            narr_md = "\n> ".join(narr.split("\n"))
            md += f"""**Narrator Voiceover:**
> {narr_md}

"""
        if dial and dial != narr:
            dial_md = "\n> ".join(dial.split("\n"))
            md += f"""**Character Dialogue:**
> {dial_md}

"""
        if not narr and not dial and full_text:
            ft_md = "\n> ".join(full_text.split("\n"))
            md += f"""> {ft_md}

"""
        md += "---\n"

    # Section 3: YouTube Packaging & Description
    md += f"""# PART 3: YOUTUBE DESCRIPTION & TAGS
### Channel
**{channel_name}**

### Ready-to-Copy YouTube Description
{youtube_desc}

### Viral Tags
{format_hashtags(hashtags)}

---
*Prepared by WP Studio — Individual Voiceover & Screenplay Script PDF.*
"""

    pdf = MarkdownPdf(toc_level=0)
    pdf.add_section(Section(md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf.save(pdf_path)
    apply_dark_theme(pdf_path)
    del pdf
    gc.collect()
    return pdf_path


def generate_character_prompts_pdf(
    story_data: dict,
    culture="Universal",
    style="Stylised 3D",
    genre="Action Thriller",
    delivery_format="Dialogue / Narrative",
    lead_character=None,
    length_tier="Short",
    timezone="Africa/Lagos"
) -> str:
    """
    Individual Production PDF: CHARACTER SHEET PROMPTS PDF
    Dedicated strictly to full-body character reference prompts so every character looks identical across the movie.
    """
    title = story_data.get("title", "WP Studio Production Package")
    genre_val = story_data.get("genre", genre)
    logline = story_data.get("logline", story_data.get("hook", ""))
    scenes = story_data.get("scenes", []) or []

    characters, _ = _normalize_characters_and_locations(story_data, style=style)

    safe_title = sanitize_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"WP_Studio_Character_Sheet_Prompts_{safe_title}_{timestamp}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)

    runtime_lookup = {
        "Short": "~3 to 5 Mins",
        "Medium": "~10 to 15 Mins",
        "Long": "~1 to 2+ Hours"
    }
    est_runtime = (
        story_data.get("runtime_detail")
        or story_data.get("target_duration")
        or story_data.get("estimated_runtime")
        or runtime_lookup.get(length_tier, "~8 to 15 Mins")
    )

    md = f"""# WP STUDIO | CHARACTER SHEET PROMPTS
### INDIVIDUAL CHARACTER CONSISTENCY BIBLE  |  FULL-BODY VISUAL LOCK
# {title}
**GENRE:** `{genre_val.upper()}`  |  **STYLE:** `{style}`  |  **RUNTIME:** `{est_runtime}`  |  **CHARACTERS:** `{len(characters)}`

> *"{logline}"*

---

# CHARACTER SHEET PROMPTS ({len(characters)} CHARACTERS)
*Generate these character sheets first so every character keeps the exact same face, skin tone, hair, build, and outfit throughout your movie.*

"""

    if characters:
        for idx, char in enumerate(characters, 1):
            c_name = char.get("name", f"Character {idx}")
            c_orig = char.get("original_name", "")
            c_role = char.get("role", "SUPPORTING")
            c_desc = char.get("locked_visual_description", "")
            c_lock = char.get("identity_lock_statement", "")
            orig_tag = f" *(Remodeled from: {c_orig})*" if (c_orig and c_orig.lower() != c_name.lower()) else ""

            # Find scenes where this character appears
            char_scenes = []
            for s in scenes:
                if not isinstance(s, dict):
                    continue
                s_num = s.get("scene_number", 1)
                raw_cp = s.get("characters_present", [])
                cp_str = ", ".join(raw_cp) if isinstance(raw_cp, list) else str(raw_cp)
                if c_name.lower() in cp_str.lower() or c_name.split()[0].lower() in cp_str.lower():
                    char_scenes.append(f"Scene {s_num}")
            scenes_tag = ", ".join(char_scenes) if char_scenes else "Main Cast"

            md += f"""### CHARACTER {idx}: {c_name}{orig_tag}
**ROLE:** `{c_role}`  |  **APPEARS IN:** `{scenes_tag}`

**COPY-READY CHARACTER SHEET PROMPT:**
> {c_desc}

*{c_lock}*

---
"""
    else:
        md += "*No separate character list found.*\n\n---\n"

    md += """*Prepared by WP Studio — Individual Character Sheet Prompts PDF.*
"""

    pdf = MarkdownPdf(toc_level=0)
    pdf.add_section(Section(md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf.save(pdf_path)
    apply_dark_theme(pdf_path)
    del pdf
    gc.collect()
    return pdf_path


def generate_location_prompts_pdf(
    story_data: dict,
    culture="Universal",
    style="Stylised 3D",
    genre="Action Thriller",
    delivery_format="Dialogue / Narrative",
    lead_character=None,
    length_tier="Short",
    timezone="Africa/Lagos"
) -> str:
    """
    Individual Production PDF: RECURRING LOCATION CONSISTENCY PROMPTS PDF
    Dedicated strictly to location generation prompts—especially locations that appear more than once—so the
    creator can generate master background plates and keep rooms, houses, offices, and streets 100% consistent.
    """
    title = story_data.get("title", "WP Studio Production Package")
    genre_val = story_data.get("genre", genre)
    logline = story_data.get("logline", story_data.get("hook", ""))
    scenes = story_data.get("scenes", []) or []

    _, locations = _normalize_characters_and_locations(story_data, style=style)

    recurring_locs = [loc for loc in locations if loc.get("is_recurring") or loc.get("appearance_count", 1) >= 2]
    single_locs = [loc for loc in locations if loc not in recurring_locs]

    safe_title = sanitize_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"WP_Studio_Location_Consistency_Prompts_{safe_title}_{timestamp}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)

    runtime_lookup = {
        "Short": "~3 to 5 Mins",
        "Medium": "~10 to 15 Mins",
        "Long": "~1 to 2+ Hours"
    }
    est_runtime = (
        story_data.get("runtime_detail")
        or story_data.get("target_duration")
        or story_data.get("estimated_runtime")
        or runtime_lookup.get(length_tier, "~8 to 15 Mins")
    )

    md = f"""# WP STUDIO | RECURRING LOCATION CONSISTENCY PROMPTS
### INDIVIDUAL LOCATION REFERENCE BIBLE  |  REALISTIC MOVIE ENVIRONMENT CONTINUITY
# {title}
**GENRE:** `{genre_val.upper()}`  |  **STYLE:** `{style}`  |  **RUNTIME:** `{est_runtime}`
**RECURRING LOCATIONS (2+ SCENES):** `{len(recurring_locs)}`  |  **TOTAL LOCATIONS:** `{len(locations)}`  |  **SCENES:** `{len(scenes)}`

> *"{logline}"*

---

# PART 1: RECURRING LOCATIONS (APPEAR MORE THAN ONCE)
*These locations appear in multiple scenes across your story. Generate these unoccupied location reference backgrounds first so the room layout, furniture, lighting, and architecture stay 100% realistic and identical every time the story returns to that setting.*

"""

    if recurring_locs:
        for idx, loc in enumerate(recurring_locs, 1):
            l_name = loc.get("name", f"Recurring Location {idx}")
            l_scenes = loc.get("scenes_used", "Multiple Scenes")
            l_count = loc.get("appearance_count", 2)
            l_ref = loc.get("unoccupied_reference", "")

            md += f"""### RECURRING LOCATION {idx}: {l_name} (Appears in {l_count} Scenes)
**SCENES USING THIS LOCATION:** `{l_scenes}`

**COPY-READY LOCATION REFERENCE PROMPT (Unoccupied Master Background):**
> {l_ref}

---
"""
    else:
        md += "*All story locations are listed below with their scene numbers and master reference prompts.*\n\n---\n"

    if single_locs:
        md += f"""# PART 2: ADDITIONAL STORY LOCATIONS ({len(single_locs)} LOCATIONS)
*Single-scene settings with complete environmental reference prompts for visual consistency.*

"""
        for idx, loc in enumerate(single_locs, 1):
            l_name = loc.get("name", f"Location {idx}")
            l_scenes = loc.get("scenes_used", "Scene")
            l_ref = loc.get("unoccupied_reference", "")

            md += f"""### LOCATION {idx}: {l_name}
**SCENE:** `{l_scenes}`

**COPY-READY LOCATION REFERENCE PROMPT:**
> {l_ref}

---
"""

    md += """*Prepared by WP Studio — Individual Recurring Location Consistency Prompts PDF.*
"""

    pdf = MarkdownPdf(toc_level=0)
    pdf.add_section(Section(md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf.save(pdf_path)
    apply_dark_theme(pdf_path)
    del pdf
    gc.collect()
    return pdf_path


def generate_image_prompts_pdf(
    story_data: dict,
    culture="Universal",
    style="Stylised 3D",
    genre="Action Thriller",
    delivery_format="Dialogue / Narrative",
    lead_character=None,
    length_tier="Short",
    timezone="Africa/Lagos"
) -> str:
    """
    Individual Production PDF: SCENE-BY-SCENE IMAGE PROMPTS PDF
    Contains standalone copy-paste scene image prompts for Midjourney / Flux / Google Flow,
    plus a quick reference summary of characters and recurring locations.
    """
    title = story_data.get("title", "WP Studio Production Package")
    genre_val = story_data.get("genre", genre)
    logline = story_data.get("logline", story_data.get("hook", ""))
    scenes = story_data.get("scenes", []) or []

    characters, locations = _normalize_characters_and_locations(story_data, style=style)

    safe_title = sanitize_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"WP_Studio_Scene_Image_Prompts_{safe_title}_{timestamp}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)

    runtime_lookup = {
        "Short": "~3 to 5 Mins",
        "Medium": "~10 to 15 Mins",
        "Long": "~1 to 2+ Hours"
    }
    est_runtime = (
        story_data.get("runtime_detail")
        or story_data.get("target_duration")
        or story_data.get("estimated_runtime")
        or runtime_lookup.get(length_tier, "~8 to 15 Mins")
    )

    md = f"""# WP STUDIO | SCENE-BY-SCENE IMAGE PROMPTS
### INDIVIDUAL SCENE IMAGE PROMPTS PDF  |  SHOT-BY-SHOT VISUAL STORYBOARD
# {title}
**GENRE:** `{genre_val.upper()}`  |  **STYLE:** `{style}`  |  **RUNTIME:** `{est_runtime}`  |  **SCENES:** `{len(scenes)}`

> *"{logline}"*

---

# SCENE-BY-SCENE IMAGE PROMPTS ({len(scenes)} SCENES)
*Each scene prompt below is 100% self-contained with camera angle, recurring location lighting, character likeness in parentheses, wardrobe, and physical action.*

"""

    for s in scenes:
        if not isinstance(s, dict):
            continue
        s_num = s.get("scene_number", 1)
        s_title = s.get("scene_title", f"Scene {s_num}")
        s_dur = s.get("estimated_duration") or s.get("duration", "1m 30s")
        raw_chars = s.get("characters_present", [])
        if isinstance(raw_chars, list):
            s_chars = ", ".join(raw_chars) or "None"
        else:
            s_chars = str(raw_chars) or "None"
        s_loc = s.get("location") or s.get("setting") or "Main Setting"
        s_prompt = s.get("image_prompt", "")

        md += f"""### SCENE {s_num} — {s_title}
**LOCATION:** `{s_loc}`  |  **CHARACTERS:** `{s_chars}`  |  **DURATION:** `{s_dur}`

**COPY-READY SCENE IMAGE PROMPT (Midjourney / Flux / Google Flow):**
> {s_prompt}

---
"""

    md += """*Prepared by WP Studio — Individual Scene-by-Scene Image Prompts PDF.*
"""

    pdf = MarkdownPdf(toc_level=0)
    pdf.add_section(Section(md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf.save(pdf_path)
    apply_dark_theme(pdf_path)
    del pdf
    gc.collect()
    return pdf_path


def generate_video_prompts_pdf(
    story_data: dict,
    culture="Universal",
    style="Stylised 3D",
    genre="Action Thriller",
    delivery_format="Dialogue / Narrative",
    lead_character=None,
    length_tier="Short",
    timezone="Africa/Lagos"
) -> str:
    """
    Individual Production PDF: VIDEO CAMERA & MOTION PROMPTS
    Engineered specifically for Google Flow / Veo, Kling AI, Luma, and Runway Gen-3.
    """
    title = story_data.get("title", "WP Studio Production Package")
    genre_val = story_data.get("genre", genre)
    logline = story_data.get("logline", story_data.get("hook", ""))
    scenes = story_data.get("scenes", []) or []

    safe_title = sanitize_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"WP_Studio_Video_Motion_Prompts_{safe_title}_{timestamp}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)

    runtime_lookup = {
        "Short": "~3 to 5 Mins",
        "Medium": "~10 to 15 Mins",
        "Long": "~1 to 2+ Hours"
    }
    est_runtime = (
        story_data.get("runtime_detail")
        or story_data.get("target_duration")
        or story_data.get("estimated_runtime")
        or runtime_lookup.get(length_tier, "~8 to 15 Mins")
    )

    md = f"""# WP STUDIO | VIDEO CAMERA & MOTION PROMPTS
### SCENE-BY-SCENE ANIMATION & MOTION DIRECTIVES
# {title}
**GENRE:** `{genre_val.upper()}`  |  **STYLE:** `{style}`  |  **RUNTIME:** `{est_runtime}`  |  **SCENES:** `{len(scenes)}`

> *"{logline}"*

---

# SCENE-BY-SCENE VIDEO MOTION PROMPTS ({len(scenes)} SCENES)
*Paste each prompt below alongside your generated scene image into Kling AI, Google Flow / Veo, Runway Gen-3, or Luma Dream Machine.*

"""

    for s in scenes:
        if not isinstance(s, dict):
            continue
        s_num = s.get("scene_number", 1)
        s_title = s.get("scene_title", f"Scene {s_num}")
        s_dur = s.get("estimated_duration") or s.get("duration", "1m 30s")
        raw_chars = s.get("characters_present", [])
        if isinstance(raw_chars, list):
            s_chars = ", ".join(raw_chars) or "None"
        else:
            s_chars = str(raw_chars) or "None"
        s_loc = s.get("location") or s.get("setting") or "Main Setting"
        s_video = s.get("video_prompt", "")

        md += f"""### SCENE {s_num} — {s_title}
**LOCATION:** `{s_loc}`  |  **CHARACTERS:** `{s_chars}`  |  **DURATION:** `{s_dur}`

**COPY-READY VIDEO MOTION PROMPT (Kling / Runway / Veo / Flow):**
> {s_video}

---
"""

    md += """*Prepared by WP Studio — Individual Video Camera & Motion Prompts PDF.*
"""

    pdf = MarkdownPdf(toc_level=0)
    pdf.add_section(Section(md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf.save(pdf_path)
    apply_dark_theme(pdf_path)
    del pdf
    gc.collect()
    return pdf_path


def generate_dual_pdfs(story_data: dict, culture="Universal", style="Stylised 3D", genre="Action Thriller", delivery_format="Dialogue / Narrative", lead_character=None, length_tier="Short", timezone="Africa/Lagos") -> tuple:
    """Generates both Master Image Prompts PDF and Master Video Prompts PDF."""
    image_pdf = generate_image_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    video_pdf = generate_video_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    return image_pdf, video_pdf


def generate_triple_pdfs(story_data: dict, culture="Universal", style="Stylised 3D", genre="Action Thriller", delivery_format="Dialogue / Narrative", lead_character=None, length_tier="Short", timezone="Africa/Lagos") -> tuple:
    """
    Generates 3 PDFs (Script, Scene Image, Video). For full 5 individual PDFs including Character & Location PDFs,
    use generate_all_production_pdfs.
    """
    script_pdf = generate_voiceover_script_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    image_pdf = generate_image_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    video_pdf = generate_video_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    return script_pdf, image_pdf, video_pdf


def generate_all_production_pdfs(story_data: dict, culture="Universal", style="Stylised 3D", genre="Action Thriller", delivery_format="Dialogue / Narrative", lead_character=None, length_tier="Short", timezone="Africa/Lagos") -> tuple:
    """
    Generates all 5 Individual Production PDFs for Creators:
    1. script_pdf: Full Narrator Voiceover & Screenplay Script PDF (for voiceover recording)
    2. char_pdf: Character Sheet Prompts PDF (full-body visual consistency lock)
    3. loc_pdf: Recurring Location Consistency Prompts PDF (locations appearing 2+ times + all settings)
    4. image_pdf: Scene-by-Scene Image Prompts PDF
    5. video_pdf: Scene-by-Scene Video Motion Prompts PDF
    """
    script_pdf = generate_voiceover_script_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    char_pdf = generate_character_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    loc_pdf = generate_location_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    image_pdf = generate_image_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    video_pdf = generate_video_prompts_pdf(story_data, culture, style, genre, delivery_format, lead_character, length_tier, timezone)
    return script_pdf, char_pdf, loc_pdf, image_pdf, video_pdf


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
# {c_name}
**Visual Style:** `{c_style}`  
**Date:** {datetime.now().strftime('%B %d, %Y')}  
**Recommended Generation Aspect Ratio:** `{params}`

---

# 1. Continuity & Anatomical Trait Bible
{c_bible}

---

# 2. MASTER 9-PANEL 3D TURNAROUND MODEL SHEET PROMPT
*Use this master prompt in Midjourney v6, Flux.1, or Google Flow to generate the complete 3x3 reference sheet (all corners, all faces, full body, close-ups, hairstyle, and uniform textures in a single image):*

> {c_master}

---

# 3. INDIVIDUAL 4K ANGLE PROMPTS
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

# 4. DYNAMIC ACTION PROMPT
*Showcase your character in full cinematic action inside their native environment:*

> {c_action}

---
*Generated by WP Studio CastLock 3D Engine — 100% Identical Continuity Across Every Animation & Scene.*
"""

    pdf = MarkdownPdf(toc_level=0)
    pdf.add_section(Section(md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf.save(pdf_path)
    apply_dark_theme(pdf_path)
    del pdf
    gc.collect()
    return pdf_path


def generate_podcast_pdfs(podcast_data: dict, timezone: str = "Africa/Lagos") -> tuple:
    """
    Generates the executive 3-PDF Production Suite for Podcast Studio:
    1. Screenplay & Spoken Dialogue Script PDF (Viral hook, multi-cam dialogue lines, delivery cues, audio sound effects)
    2. Scene Multi-Cam Prompts PDF (Standalone image prompts & video camera motion prompts with studio lighting and host consistency)
    3. Host Character Bible & Studio Branding PDF (Complete host profiles, vocal delivery specs, studio architecture, channel branding watermarks)
    Returns: (script_pdf_path, prompts_pdf_path, bible_pdf_path)
    """
    title = podcast_data.get("title", "WP Studio Podcast Episode")
    category = podcast_data.get("category", "General")
    hook = podcast_data.get("hook", "")
    dynamic = podcast_data.get("discussion_dynamic", "Heated Debate")
    studio_set = podcast_data.get("studio_archetype", "Dark Moody / Slate Acoustic")
    visual_style = podcast_data.get("visual_style", "Human Realistic")
    aspect_ratio = podcast_data.get("aspect_ratio", "9:16 Vertical")
    channel_name = podcast_data.get("channel_name", "WP Studio Network")
    host_format = podcast_data.get("host_format", "Two Hosts")
    studio_env = podcast_data.get("studio_environment", "Professional acoustic studio setup.")
    branding_desc = podcast_data.get("channel_branding", "Branded studio props.")
    hosts = podcast_data.get("hosts", []) or []
    scenes = podcast_data.get("scenes", []) or []
    runtime = podcast_data.get("runtime_detail", f"{len(scenes)} Scenes (~60-90s)")

    safe_title = sanitize_filename(title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # -------------------------------------------------------------
    # 1. Screenplay & Dialogue Script PDF
    # -------------------------------------------------------------
    script_filename = f"WP_Studio_Podcast_Screenplay_{safe_title}_{timestamp}.pdf"
    script_path = os.path.join(OUTPUT_DIR, script_filename)

    script_md = f"""<div class="studio-header">
  <div class="studio-subtitle">WP STUDIO CREATIVE SUITE | PODCAST SCREENPLAY &amp; DIALOGUE SCRIPT</div>
  <div class="studio-title">{title}</div>
  <div class="meta-grid">
    <span class="meta-pill">CATEGORY: {category.upper()}</span>
    <span class="meta-pill">FORMAT: {host_format.upper()}</span>
    <span class="meta-pill">DYNAMIC: {dynamic.upper()}</span>
    <span class="meta-pill">CHANNEL: {channel_name.upper()}</span>
    <span class="meta-pill-slate">RUNTIME: {runtime}</span>
    <span class="meta-pill-slate">SCENES: {len(scenes)}</span>
  </div>
</div>

<div class="scene-card" style="border-left: 3pt solid #d4af37;">
  <span class="prompt-label-gold">THE 3-SECOND BOMBSHELL VIRAL HOOK</span>
  <p style="font-size: 11pt; color: #ffffff; font-weight: 700; margin-top: 4pt;">"{hook}"</p>
  <p style="font-size: 8pt; color: #94a3b8; margin-top: 2pt;">Delivery Note: Unresolved high-tension hook engineered to stop the viewer scroll in under 3 seconds before the podcast audio sting.</p>
</div>

<h2>EPISODE SCENE &amp; DIALOGUE STORYBOARD ({len(scenes)} CUTS)</h2>
"""

    for s in scenes:
        if not isinstance(s, dict):
            continue
        s_num = s.get("scene_number", 1)
        cam = s.get("camera_shot", "CAM A")
        speaker = s.get("speaker", "Host 1")
        cues = s.get("delivery_cues", "Direct delivery")
        dialogue = s.get("dialogue", "")
        audio = s.get("audio_cues", "Studio acoustic ambiance")
        dur = s.get("estimated_duration", "7s")

        script_md += f"""<div class="scene-card">
  <div class="scene-title">CUT {s_num:02d} &bull; {cam}</div>
  <span class="meta-pill-slate">SPEAKER: {speaker}</span>
  <span class="meta-pill-slate">DURATION: {dur}</span>

  <div class="dialogue-card">
    <span class="speaker-tag">{speaker}</span> <span class="delivery-cue">({cues})</span>
    <div class="dialogue-text">"{dialogue}"</div>
  </div>

  <p style="font-size: 8pt; color: #94a3b8; margin-top: 5pt; margin-bottom: 0;"><strong>Audio &amp; SFX:</strong> {audio}</p>
</div>
"""

    script_md += f"""<br>
<p style="font-size: 7.5pt; color: #64748b; text-align: center;">Official Production Asset &bull; Generated by WP Studio Podcast Engine &bull; Ready for ElevenLabs / TTS Synthesis</p>
"""

    pdf1 = MarkdownPdf(toc_level=0)
    pdf1.add_section(Section(script_md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf1.save(script_path)
    apply_dark_theme(script_path, doc_category="PODCAST SCREENPLAY & DIALOGUE")
    del pdf1
    gc.collect()

    # -------------------------------------------------------------
    # 2. Scene Multi-Cam Prompts PDF
    # -------------------------------------------------------------
    prompts_filename = f"WP_Studio_Podcast_Scene_Prompts_{safe_title}_{timestamp}.pdf"
    prompts_path = os.path.join(OUTPUT_DIR, prompts_filename)

    prompts_md = f"""<div class="studio-header">
  <div class="studio-subtitle">WP STUDIO CREATIVE SUITE | MULTI-CAM IMAGE &amp; VIDEO PROMPTS</div>
  <div class="studio-title">{title}</div>
  <div class="meta-grid">
    <span class="meta-pill">SET ARCHETYPE: {studio_set.upper()}</span>
    <span class="meta-pill">ASPECT RATIO: {aspect_ratio}</span>
    <span class="meta-pill">STYLE: {visual_style.upper()}</span>
    <span class="meta-pill">BRANDING: {channel_name.upper()}</span>
  </div>
</div>

<h2>SHOT-BY-SHOT MULTI-CAMERA PROMPT SPECIFICATION ({len(scenes)} SCENES)</h2>
<p style="color: #94a3b8; font-size: 8.5pt;">Copy-ready image prompts for Midjourney / Flux and video camera motion prompts for Kling / Runway Gen-3 with locked studio lighting and host consistency.</p>
"""

    for s in scenes:
        if not isinstance(s, dict):
            continue
        s_num = s.get("scene_number", 1)
        cam = s.get("camera_shot", "CAM A")
        speaker = s.get("speaker", "Host")
        dur = s.get("estimated_duration", "7s")
        img_p = s.get("image_prompt", "")
        vid_p = s.get("video_prompt", "")

        prompts_md += f"""<div class="scene-card">
  <div class="scene-title">SCENE {s_num:02d} &bull; {cam}</div>
  <span class="meta-pill-slate">TARGET SUBJECT: {speaker}</span>
  <span class="meta-pill-slate">EST. DURATION: {dur}</span>

  <div class="prompt-vault">
    <span class="prompt-label-blue">MIDJOURNEY / FLUX SCENE IMAGE PROMPT (85MM / 4K PHOTOREALISTIC)</span>
    {img_p}
  </div>

  <div class="prompt-vault-video">
    <span class="prompt-label-gold">KLING / RUNWAY / LUMA VIDEO MOTION PROMPT (MICRO-EXPRESSIONS &amp; CAMERA PAN)</span>
    {vid_p}
  </div>
</div>
"""

    prompts_md += f"""<br>
<p style="font-size: 7.5pt; color: #64748b; text-align: center;">Official Production Asset &bull; Generated by WP Studio Podcast Engine &bull; Ready for Midjourney, Flux, Kling, Runway</p>
"""

    pdf2 = MarkdownPdf(toc_level=0)
    pdf2.add_section(Section(prompts_md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf2.save(prompts_path)
    apply_dark_theme(prompts_path, doc_category="MULTI-CAM PROMPT SPECIFICATION")
    del pdf2
    gc.collect()

    # -------------------------------------------------------------
    # 3. Host Character Bible & Studio Branding PDF
    # -------------------------------------------------------------
    bible_filename = f"WP_Studio_Podcast_Production_Bible_{safe_title}_{timestamp}.pdf"
    bible_path = os.path.join(OUTPUT_DIR, bible_filename)

    bible_md = f"""<div class="studio-header">
  <div class="studio-subtitle">WP STUDIO CREATIVE SUITE | HOST CHARACTER &amp; STUDIO BRANDING BIBLE</div>
  <div class="studio-title">{channel_name} &bull; {title}</div>
  <div class="meta-grid">
    <span class="meta-pill">TOTAL HOSTS: {len(hosts)}</span>
    <span class="meta-pill">STUDIO SET: {studio_set.upper()}</span>
    <span class="meta-pill">VISUAL STYLE: {visual_style.upper()}</span>
    <span class="meta-pill-slate">ASPECT RATIO: {aspect_ratio}</span>
  </div>
</div>

<div class="scene-card">
  <div class="scene-title">1. STUDIO SET ARCHITECTURE &amp; LIGHTING SPECIFICATION</div>
  <p style="color: #f1f5f9; font-size: 9pt;">{studio_env}</p>
  <span class="prompt-label-blue" style="margin-top: 6pt;">CHANNEL BRANDING WATERMARK INTEGRATION:</span>
  <p style="color: #cbd5e1; font-size: 8.5pt;">{branding_desc}</p>
</div>

<h2>2. HOST CHARACTER IDENTITY &amp; VOCAL PROFILES ({len(hosts)} HOSTS)</h2>
"""

    for idx, h in enumerate(hosts, 1):
        if not isinstance(h, dict):
            continue
        h_name = h.get("name", f"Host {idx}")
        h_role = h.get("role", "Podcast Host")
        h_gender = h.get("gender", "Unspecified")
        h_ethnicity = h.get("ethnicity", "Unspecified")
        h_accent = h.get("accent", "Standard English")
        h_wardrobe = h.get("wardrobe_lock", "Modern studio attire")
        h_vis = h.get("locked_visual_description", "")
        h_vocal = h.get("vocal_profile", "Natural expressive vocal delivery")

        bible_md += f"""<div class="scene-card">
  <div class="scene-title">{h_name.upper()} &bull; {h_role.upper()}</div>
  <div style="margin-bottom: 6pt;">
    <span class="meta-pill">GENDER: {h_gender.upper()}</span>
    <span class="meta-pill">ETHNICITY: {h_ethnicity.upper()}</span>
    <span class="meta-pill">ACCENT: {h_accent.upper()}</span>
  </div>

  <p style="color: #cbd5e1; font-size: 8.5pt; margin-bottom: 4pt;"><strong>Wardrobe Continuity Lock:</strong> {h_wardrobe}</p>
  <p style="color: #cbd5e1; font-size: 8.5pt; margin-bottom: 6pt;"><strong>Vocal Delivery Profile (TTS/ElevenLabs):</strong> {h_vocal}</p>

  <div class="prompt-vault">
    <span class="prompt-label-blue">CHARACTER REFERENCE PROMPT &bull; FACIAL IDENTITY LOCK</span>
    {h_vis}
  </div>
</div>
"""

    bible_md += f"""<br>
<p style="font-size: 7.5pt; color: #64748b; text-align: center;">Official Production Asset &bull; Generated by WP Studio Podcast Engine &bull; Continuity Locked Across All Episodes</p>
"""

    pdf3 = MarkdownPdf(toc_level=0)
    pdf3.add_section(Section(bible_md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf3.save(bible_path)
    apply_dark_theme(bible_path, doc_category="HOST & STUDIO PRODUCTION BIBLE")
    del pdf3
    gc.collect()

    return script_path, prompts_path, bible_path


def generate_ugc_pdfs(ugc_data: dict, timezone: str = "Africa/Lagos") -> tuple:
    """
    Generates the executive 2-PDF Production Suite for UGC Content:
    1. Video Script & Director Blueprint PDF (Hooks, spoken scripts, creator actions, on-screen text, audio cues)
    2. AI Video & Image Prompts PDF (Midjourney/Flux keyframe prompts & Kling/Runway video motion prompts)
    Returns: (script_pdf_path, prompts_pdf_path)
    """
    campaign_title = ugc_data.get("campaign_title", "WP Studio UGC Commercial")
    brand = ugc_data.get("brand_or_product", "Brand")
    target_audience = ugc_data.get("target_audience", "Digital Consumers")
    hooks = ugc_data.get("hook_variations", []) or []
    clips = ugc_data.get("clips", []) or []
    full_script = ugc_data.get("full_voiceover_script", "")
    tips = ugc_data.get("performance_tips", "")

    safe_title = sanitize_filename(campaign_title)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Video Script & Director Blueprint PDF
    script_filename = f"WP_Studio_UGC_Script_{safe_title}_{timestamp}.pdf"
    script_path = os.path.join(OUTPUT_DIR, script_filename)

    script_md = f"""<div class="studio-header">
  <div class="studio-subtitle">WP STUDIO CREATIVE SUITE | UGC VIDEO AD SCRIPT &amp; DIRECTOR BLUEPRINT</div>
  <div class="studio-title">{campaign_title}</div>
  <div class="meta-grid">
    <span class="meta-pill">BRAND: {brand.upper()}</span>
    <span class="meta-pill">FORMAT: 9:16 VERTICAL</span>
    <span class="meta-pill">CLIPS: 6 VIRAL CUTS</span>
    <span class="meta-pill">AUDIENCE: {target_audience.upper()[:30]}</span>
  </div>
</div>

<div class="concept-card">
  <div class="concept-header">
    <span class="concept-badge">SCROLL-STOPPING 3-SECOND HOOK VARIATIONS (A/B TESTING)</span>
  </div>
  <p style="font-size: 8.5pt; color: #cbd5e1; margin-bottom: 6pt;">Test these three opening hooks across ad sets to find your highest CTR winner:</p>
"""
    for i, h in enumerate(hooks):
        script_md += f"""  <div style="margin-bottom: 4pt; font-size: 8.5pt; color: #f3f4f6;"><strong>Option {i+1}:</strong> &ldquo;{h}&rdquo;</div>\n"""
    script_md += f"""</div>

<h2>6-CLIP VERTICAL COMMERCIAL STORYBOARD</h2>
"""

    for c in clips:
        if not isinstance(c, dict): continue
        c_num = c.get("clip_number", 1)
        c_title = c.get("title", f"Clip {c_num}")
        dur = c.get("duration", "0:00 - 0:05")
        spoken = c.get("spoken_script", "")
        action = c.get("creator_action", "")
        overlay = c.get("on_screen_text", "")
        audio = c.get("audio_foley", "")

        script_md += f"""<div class="scene-card">
  <div class="scene-title">CLIP {c_num:02d} &bull; {c_title.upper()}</div>
  <span class="meta-pill-slate">TIMESTAMP: {dur}</span>
  <span class="meta-pill-slate">ASPECT: 9:16 VERTICAL</span>

  <div class="dialogue-card">
    <span class="speaker-tag">CREATOR SPOKEN SCRIPT</span>
    <div class="dialogue-text">&ldquo;{spoken}&rdquo;</div>
  </div>

  <p style="font-size: 8pt; color: #e5a93c; margin-top: 5pt; margin-bottom: 3pt;"><strong>On-Screen Text Overlay:</strong> [ {overlay} ]</p>
  <p style="font-size: 8pt; color: #cbd5e1; margin-top: 0; margin-bottom: 3pt;"><strong>Visual &amp; Camera Action:</strong> {action}</p>
  <p style="font-size: 8pt; color: #94a3b8; margin-top: 0; margin-bottom: 0;"><strong>Audio / SFX Cue:</strong> {audio}</p>
</div>
"""

    if full_script:
        script_md += f"""<h2>FULL CONTINUOUS VOICEOVER SCRIPT</h2>
<div class="concept-card">
  <div style="font-size: 8.5pt; color: #f3f4f6; line-height: 1.6;">{full_script}</div>
</div>
"""

    if tips:
        script_md += f"""<h2>CREATOR PERFORMANCE &amp; PACING TIPS</h2>
<div class="concept-card">
  <p style="font-size: 8.5pt; color: #cbd5e1;">{tips}</p>
</div>
"""

    script_md += f"""<br>
<p style="font-size: 7.5pt; color: #64748b; text-align: center;">Official Production Asset &bull; Generated by WP Studio UGC Commercial Engine &bull; TikTok / Reels / Shorts Ready</p>
"""

    pdf1 = MarkdownPdf(toc_level=0)
    pdf1.add_section(Section(script_md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf1.save(script_path)
    apply_dark_theme(script_path, doc_category="UGC VIDEO AD SCRIPT")
    del pdf1
    gc.collect()

    # 2. AI Video & Image Prompts PDF
    prompts_filename = f"WP_Studio_UGC_Prompts_{safe_title}_{timestamp}.pdf"
    prompts_path = os.path.join(OUTPUT_DIR, prompts_filename)

    prompts_md = f"""<div class="studio-header">
  <div class="studio-subtitle">WP STUDIO CREATIVE SUITE | UGC AI VIDEO &amp; IMAGE PROMPT SUITE</div>
  <div class="studio-title">{campaign_title}</div>
  <div class="meta-grid">
    <span class="meta-pill">BRAND: {brand.upper()}</span>
    <span class="meta-pill">PLATFORMS: MIDJOURNEY / KLING / RUNWAY</span>
    <span class="meta-pill">FORMAT: 9:16 VERTICAL</span>
  </div>
</div>

<h2>SCENE-BY-SCENE AI PROMPTS ({len(clips)} CLIPS)</h2>
"""

    for c in clips:
        if not isinstance(c, dict): continue
        c_num = c.get("clip_number", 1)
        c_title = c.get("title", f"Clip {c_num}")
        img_p = c.get("image_prompt", "")
        vid_p = c.get("video_motion_prompt", "")

        prompts_md += f"""<div class="scene-card">
  <div class="scene-title">CLIP {c_num:02d} &bull; {c_title.upper()}</div>

  <div style="background: rgba(229,169,60,0.06); border-left: 2px solid #e5a93c; padding: 6pt; margin-bottom: 6pt; border-radius: 0 4pt 4pt 0;">
    <div style="font-size: 7.5pt; font-weight: bold; color: #e5a93c; margin-bottom: 2pt;">KEYFRAME IMAGE PROMPT (MIDJOURNEY v6.1 / FLUX.1)</div>
    <div style="font-family: monospace; font-size: 7.5pt; color: #cbd5e1; line-height: 1.4;">{img_p}</div>
  </div>

  <div style="background: rgba(56,189,248,0.06); border-left: 2px solid #38bdf8; padding: 6pt; border-radius: 0 4pt 4pt 0;">
    <div style="font-size: 7.5pt; font-weight: bold; color: #38bdf8; margin-bottom: 2pt;">VIDEO MOTION PROMPT (KLING 1.5 / RUNWAY GEN-3 / SORA)</div>
    <div style="font-family: monospace; font-size: 7.5pt; color: #cbd5e1; line-height: 1.4;">{vid_p}</div>
  </div>
</div>
"""

    prompts_md += f"""<br>
<p style="font-size: 7.5pt; color: #64748b; text-align: center;">Official Production Asset &bull; Generated by WP Studio UGC Commercial Engine &bull; 9:16 Vertical Video Production</p>
"""

    pdf2 = MarkdownPdf(toc_level=0)
    pdf2.add_section(Section(prompts_md, borders=(36, 36, -36, -36)), user_css=DARK_THEME_CSS)
    pdf2.save(prompts_path)
    apply_dark_theme(prompts_path, doc_category="UGC AI PROMPTS SUITE")
    del pdf2
    gc.collect()

    return (script_path, prompts_path)
