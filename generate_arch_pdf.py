import os
from datetime import datetime
from markdown_pdf import MarkdownPdf, Section

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)
pdf_path = os.path.join(OUTPUT_DIR, "WP_Studio_System_Architecture_Comprehensive.pdf")

md_content = f"""# WP STUDIO | ENTERPRISE SYSTEM ARCHITECTURE
**Document Title:** Comprehensive Technical & Production Architecture Blueprint  
**Brand Identity:** WP Studio | APK UNLIMITED / Webpro MK  
**Target Ecosystem:** YouTube Automation & High-Retention Storytelling  
**Publication Date:** {datetime.now().strftime('%B %d, %Y')}  
**Version:** 2.0 (Production-Ready)

---

## 1. Executive Summary & Brand Family

WP Studio is the flagship AI content generation suite engineered exclusively for **YouTube Automation Creators, Faceless Channel Operators, and Animated Storytellers**. It bridges the gap between high-level creative ideation and technical video production by automatically converting raw ideas or YouTube source videos into complete, production-grade story bibles, voiceover narration scripts, character continuity turnarounds, and visual/motion prompts.

### The APK UNLIMITED Ecosystem
- **WP Relay (formerly WebTGF):** Multi-tenant Telegram channel forwarder and broadcast manager.
- **WP Assistant (formerly WebTGR):** AI personal assistant and voice DM responder.
- **WP Studio (formerly WebTGP):** Specialized AI production studio for YouTube creators.

---

## 2. High-Level System Architecture & Flow

```
[ User on Telegram / Mini App ]
               │
               ▼
   [ bot.py / Telethon ] ─── (RAM / MemorySession)
               │
   ┌───────────┼──────────────────────────┐
   ▼           ▼                          ▼
[ source_extractor ]   [ database.py ]    [ ai_engine.py ]
   │ (Captions/oEmbed)    │ (SQLite WAL)     │ (Gemini 3.8/3.1/BYOK)
   │                      │                  │
   └───────────┬──────────┴──────────────────┘
               ▼
      [ pdf_generator.py ] ─── (markdown_pdf / PyMuPDF)
               │
         ┌─────┴────────────────┐
         ▼                      ▼
  [ PDF 1: Story Bible ]  [ PDF 2: Scene Prompts ]
```

---

## 3. Core Software Modules & Technical Specifications

### 3.1 Native Telegram Bot (`bot.py`)
- **Engine:** Telethon async framework.
- **Session Architecture:** Uses `MemorySession()` in RAM. This prevents SQLite file-lock corruption and insulates the bot from old disk session bans.
- **State Machine:** In-memory user state dictionary (`USER_STATES`) tracking interactive parameter cycling (Culture, Style, Genre, Tier, Timezone) and multi-step approval workflows.

### 3.2 YouTube Source Ingestion (`source_extractor.py`)
- **Metadata Fetching:** Resolves video title and author via YouTube oEmbed without requiring YouTube Data API v3 quotas.
- **Captions Retrieval:** Utilizes `youtube_transcript_api` to extract full timestamped captions.
- **Hallucination Prevention Rule:** If captions are unavailable or disabled, the pipeline halts gracefully and prompts the user rather than inventing false storylines.

### 3.3 AI Intelligence Engine & BYOK (`ai_engine.py`)
- **Dynamic Client Resolution:** Routes requests through either the platform default pool key or the user's personal **BYOK (Bring Your Own Key)** Gemini key.
- **Model Arsenal:**
  - `gemini-3.8-flash`: High-velocity cinematic pacing (Recommended default).
  - `gemini-3.1-pro-preview`: Deep multi-layered storytelling.
  - `gemini-3.7-flash`: Advanced reasoning and scene rhythm.
  - `gemini-3.5-flash`: Lightweight high-efficiency generation.
  - `gemini-flash-latest` & `gemini-pro-latest`: Always up-to-date bleeding-edge endpoints.
- **Structured JSON Output:** Strict schema enforcement ensures deterministic extraction of hooks, character likeness anchors, ElevenLabs scripts, and Midjourney/Flux parameters.

### 3.4 Creator Database & Ledger (`database.py`)
- **Storage Engine:** SQLite with Write-Ahead Logging (WAL) for sub-millisecond local reads and zero cloud-database connection dropouts.
- **Relational Tables:**
  - `users`: Tracks `user_id`, `credits`, `tier`, `custom_gemini_key`, `selected_model`, and lifetime stories created.
  - `story_history`: Comprehensive log of all generated story packages.
  - `story_jobs`: Tracks active creation jobs, source transcripts, 10 concepts, user selections, and Dual PDF paths.
- **Universal Credit Charging:** Credits are deducted universally for platform features. BYOK keys serve to provide personal Google Cloud quotas for heavy tasks without bypassing platform fees.

### 3.5 Dual PDF Production Engine (`pdf_generator.py`)
- **Compiler:** `markdown_pdf` powered by PyMuPDF (`fitz`).
- **UTF-8 & Styling:** Full Unicode and emoji support, clean tables, blockquotes, and executive typography.
- **Dual Outputs:** Compiles both the **Story Bible** and **Scene Prompts Blueprint** as separate, professional PDFs.

---

## 4. The 5-Step StoryCraft Production Pipeline

1. **Source Ingestion:** User inputs a YouTube URL or original story concept. The system extracts captions and video title.
2. **Creative Direction Configuration:** Creator customizes:
   - **Culture:** Universal, Nigerian, American, Mixed.
   - **Visual Style:** Stylised 3D (Pixar/Disney), Human Realistic, Anime / Manga, Cinematic Cyberpunk.
   - **Genre:** Action Thriller, Crime / Mystery, Horror, Drama / Romance, Sci-Fi / Fantasy, Inspirational Drama, Comedy.
   - **Length Ceiling:** Short (≤ 40 scenes), Medium (≤ 120 scenes), Long (≤ 250 scenes).
   - **Posting Timezone:** Africa/Lagos, America/New_York, Europe/London, Africa/Johannesburg, Asia/Dubai.
3. **10 Viral Concepts Generation (Step A Charge):** AI computes 10 distinct, high-CTR angles featuring 0-5s spoken curiosity hooks, core narrative twists, and psychological audience triggers.
4. **Creator Review & Selection:** Creator reviews all 10 concepts and selects their preferred direction with a single tap, or triggers a 10-concept regeneration for 3 credits.
5. **Dual PDF Production (Step B Charge):** The system generates the complete narrative, character consistency bible, voiceover script, and scene-by-scene prompts, delivering **Dual PDFs** directly in Telegram.

---

## 5. Economic Model & Credit Pricing Matrix

| Production Tier | Scene Ceiling | Concept Generation | Dual PDFs Production | Total Package |
| :--- | :---: | :---: | :---: | :---: |
| **Short** | **40 Scenes** (15-25 scenes) | 10 Credits | 40 Credits *(20 cr/PDF)* | **50 Credits** |
| **Medium** | **120 Scenes** (40-60 scenes) | 50 Credits | 250 Credits *(125 cr/PDF)* | **300 Credits** |
| **Long** | **250 Scenes** (80-120 scenes) | 100 Credits | 300 Credits *(150 cr/PDF)* | **400 Credits** |

### Additional Capabilities
- **Regenerate 10 Concepts:** 3 Credits.
- **WP CastLock (Character Consistency Forge):** 3 Credits.
- **WP ClickThumb (3 High-CTR Thumbnails):** 2 Credits.

### Creator Tier Roadmap
- 🧱 **Builder:** Initial tier (0 credits spent/earned).
- ⚡ **Catalyst:** Unlocks at 1,000 credits.
- 👑 **Maverick:** Unlocks at 5,000 credits.

---

## 6. YouTube Automation Production Standards

To ensure videos generated with WP Studio maximize YouTube's algorithm:
1. **The 5-Second Curiosity Hook:** The spoken opening line never introduces the creator; it immediately presents an unanswered question or high-stakes crisis.
2. **Scene Pacing:** Visual cuts are calibrated every 3 to 5 seconds to preserve high audience retention.
3. **Voiceover Narration:** Formatted specifically for ElevenLabs text-to-speech with natural cadence tags.
4. **Image Prompts:** Formatted for Midjourney v6 (`--ar 16:9`) and Flux.1, specifying 35mm lens, volumetric lighting, and exact character continuity hex codes.
5. **Camera Motion Tags:** Written for Kling AI and Runway Gen-3 with explicit camera direction (e.g. `[slow dolly zoom, cinematic tracking, 4k 60fps]`).

---

## 7. Roadmap & Next Phases

- **Phase 1 (Completed):** Native Telegram Bot, Telethon MemorySession, BYOK Gemini Engine, Dual PDF Generation, and SQLite WAL ledger.
- **Phase 2 (Next):** Telegram Mini App (HTML5 / Tailwind CSS) with visual story cards, live waveform audio previews, and one-click prompt copying.
- **Phase 3:** Automated direct API rendering connectors for Kling AI and ElevenLabs.

---
*WP Studio Enterprise System Architecture — Engineered by APK UNLIMITED / Webpro MK.*
"""

pdf = MarkdownPdf(toc_level=2)
pdf.add_section(Section(md_content))
pdf.save(pdf_path)
print("COMPREHENSIVE_PDF_GENERATED_AT:", pdf_path)
