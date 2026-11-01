import re
import json
import html
import asyncio
import urllib.request
import urllib.error
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from google.genai import types
import ai_engine

logger = logging.getLogger("WPStudio")

def extract_video_id(url: str) -> str:
    """Extract 11-character YouTube video ID from various URL formats."""
    if not url:
        return None
    url = url.strip()
    if re.match(r'^[0-9A-Za-z_-]{11}$', url):
        return url
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|embed\/|shorts\/|live\/)([0-9A-Za-z_-]{11})',
        r'([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_youtube_metadata(video_id: str) -> dict:
    """
    Fetches rich video metadata (title, author, full description, and keywords)
    using YouTube oEmbed, noembed fallback, and watch page HTML parsing.
    """
    title = ""
    author = ""
    description = ""
    keywords = []

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9'
    }

    # 1. Try YouTube oEmbed
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(oembed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode('utf-8', errors='replace'))
            title = data.get("title", "")
            author = data.get("author_name", "")
    except Exception:
        pass

    # 2. Try Noembed fallback if oEmbed failed
    if not title:
        try:
            noembed_url = f"https://noembed.com/embed?url=https://www.youtube.com/watch?v={video_id}"
            req = urllib.request.Request(noembed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode('utf-8', errors='replace'))
                title = data.get("title", "")
                author = author or data.get("author_name", "")
        except Exception:
            pass

    # 3. Scrape watch page HTML for full shortDescription, title, and keywords
    try:
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        req = urllib.request.Request(watch_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            page_html = response.read().decode('utf-8', errors='replace')

            if not title:
                t_match = re.search(r'<meta name="title" content="(.*?)">', page_html)
                if t_match:
                    title = html.unescape(t_match.group(1))
                else:
                    t2 = re.search(r'<title>(.*?)\s*-\s*YouTube</title>', page_html)
                    if t2:
                        title = html.unescape(t2.group(1))

            # Extract full shortDescription from ytInitialPlayerResponse
            desc_match = re.search(r'"shortDescription":"((?:\\.|[^"\\])*)"', page_html)
            if desc_match:
                try:
                    description = json.loads(f'"{desc_match.group(1)}"')
                except Exception:
                    description = desc_match.group(1).replace('\\n', '\n').replace('\\"', '"')
            else:
                meta_desc = re.search(r'<meta name="description" content="(.*?)">', page_html)
                if meta_desc:
                    description = html.unescape(meta_desc.group(1))

            kw_match = re.search(r'"keywords":\[(.*?)\]', page_html)
            if kw_match:
                try:
                    keywords = json.loads(f"[{kw_match.group(1)}]")
                except Exception:
                    pass
    except Exception as e:
        logger.info(f"Watch page metadata scrape notice for {video_id}: {e}")

    return {
        "title": title.strip() if title else f"YouTube Story ({video_id})",
        "author": author.strip() if author else "YouTube Creator",
        "description": description.strip() if description else "",
        "keywords": keywords if isinstance(keywords, list) else []
    }

def try_fetch_captions(video_id: str) -> str:
    """Fetches real video captions/subtitles using youtube-transcript-api with multi-dialect and auto-caption support."""
    try:
        api = YouTubeTranscriptApi()
        transcript_list = None

        # Method 1: Instance API (.list / .fetch)
        try:
            tl = api.list(video_id)
            chosen = None
            try:
                chosen = tl.find_transcript(['en', 'en-US', 'en-GB'])
            except Exception:
                pass
            if not chosen:
                try:
                    chosen = tl.find_generated_transcript(['en', 'en-US', 'en-GB'])
                except Exception:
                    pass
            if not chosen:
                for t in tl:
                    if getattr(t, 'language_code', '').startswith('en'):
                        chosen = t
                        break
            if not chosen:
                for t in tl:
                    chosen = t
                    break
            if chosen:
                transcript_list = chosen.fetch()
        except Exception:
            try:
                transcript_list = api.fetch(video_id, languages=['en', 'en-US', 'en-GB', 'a.en'])
            except Exception:
                pass

        # Method 2: Static get_transcript fallback (older youtube-transcript-api versions)
        if not transcript_list and hasattr(YouTubeTranscriptApi, 'get_transcript'):
            try:
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US', 'en-GB'])
            except Exception:
                pass

        if transcript_list:
            text_entries = []
            for entry in transcript_list:
                t = getattr(entry, 'text', None)
                if not t and isinstance(entry, dict):
                    t = entry.get('text', '')
                if t:
                    text_entries.append(t)
            full_text = " ".join(text_entries)
            full_text = re.sub(r'\[.*?\]', '', full_text)
            full_text = re.sub(r'\s+', ' ', full_text).strip()
            if len(full_text) > 40:
                return full_text
    except Exception as e:
        logger.info(f"Direct captions extraction failed for {video_id}: {e}")
    return None

async def get_youtube_transcript_async(url_or_id: str, user_api_key: str = None) -> dict:
    """
    4-Tier Bulletproof YouTube Ingestion:
    1. Official Captions / Subtitles extraction.
    2. Gemini Native Multimodal Video Intelligence (with automatic model & key fallback).
    3. Gemini Narrative Reconstruction from extracted Video Title, Description, Keywords & Channel.
    4. Metadata Synopsis Fallback so YouTube ingestion never fails.
    """
    video_id = extract_video_id(url_or_id) if ("http" in str(url_or_id) or "/" in str(url_or_id)) else str(url_or_id).strip()
    if not video_id:
        return {"success": False, "error": "Invalid YouTube URL format.", "video_id": None}

    meta = get_youtube_metadata(video_id)
    video_title = meta.get("title", f"YouTube Story ({video_id})")
    video_author = meta.get("author", "YouTube Creator")
    video_desc = meta.get("description", "")
    video_keywords = ", ".join(meta.get("keywords", [])[:20])
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Tier 1: Try direct captions API first
    transcript_text = try_fetch_captions(video_id)
    source_type = "official_captions"

    # Tier 2: Gemini Multimodal Video Intelligence (using generate_with_fallback for 503 resilience)
    if not transcript_text:
        logger.info(f"Direct captions unavailable for {video_id}. Activating Gemini Multimodal Video Intelligence...")
        try:
            client = ai_engine.get_client(user_api_key)
            gemini_res = ai_engine.generate_with_fallback(
                client=client,
                preferred_model=ai_engine.DEFAULT_MODEL,
                contents=[
                    types.Part.from_uri(file_uri=video_url, mime_type="video/*"),
                    (
                        f"Video Title: {video_title}\nChannel: {video_author}\n\n"
                        "Extract the full, detailed scene-by-scene narrative, spoken dialogue, character names, "
                        "locations, and storyline from this YouTube video. Be thorough and faithful to the story."
                    )
                ],
                user_api_key=user_api_key
            )
            if gemini_res and getattr(gemini_res, "text", None) and len(gemini_res.text.strip()) > 60:
                transcript_text = gemini_res.text.strip()
                source_type = "gemini_multimodal_video_analysis"
                logger.info(f"Gemini Video Intelligence extracted storyline for {video_id} ({len(transcript_text.split())} words)")
        except Exception as e:
            logger.warning(f"Gemini native video URI analysis notice for {video_id}: {e}")

    # Tier 3: Gemini Story Reconstruction from Video Title, Full Description & Channel Metadata
    if not transcript_text:
        logger.info(f"Activating Tier 3 metadata narrative expansion for {video_id} ('{video_title}')...")
        try:
            client = ai_engine.get_client(user_api_key)
            meta_prompt = (
                f"YouTube Video URL: {video_url}\n"
                f"Video Title: {video_title}\n"
                f"Channel / Creator: {video_author}\n"
                f"Video Description:\n{video_desc[:4000]}\n"
                f"Keywords / Tags: {video_keywords}\n\n"
                "Based on this YouTube video's title, description, channel style, and tags, reconstruct a comprehensive, "
                "high-retention story outline, character breakdown, core conflict, emotional hooks, and dramatic plot progression "
                "that captures the full essence of this video."
            )
            fallback_res = ai_engine.generate_with_fallback(
                client=client,
                preferred_model=ai_engine.DEFAULT_MODEL,
                contents=meta_prompt,
                user_api_key=user_api_key
            )
            if fallback_res and getattr(fallback_res, "text", None) and len(fallback_res.text.strip()) > 40:
                transcript_text = fallback_res.text.strip()
                source_type = "gemini_metadata_reconstruction"
                logger.info(f"Tier 3 metadata reconstruction succeeded for {video_id}")
        except Exception as e3:
            logger.warning(f"Tier 3 metadata reconstruction notice for {video_id}: {e3}")

    # Tier 4: Direct Metadata Synopsis Fallback (Guarantees 100% uptime)
    if not transcript_text:
        parts = [f"Video Title: {video_title}", f"Channel: {video_author}"]
        if video_desc:
            parts.append(f"Story Description:\n{video_desc}")
        if video_keywords:
            parts.append(f"Keywords: {video_keywords}")
        transcript_text = "\n\n".join(parts)
        source_type = "youtube_metadata_fallback"

    return {
        "success": True,
        "video_id": video_id,
        "title": video_title,
        "author": video_author,
        "transcript": transcript_text[:15000],
        "word_count": len(transcript_text.split()),
        "source_type": source_type
    }

def get_youtube_transcript(url_or_id: str, user_api_key: str = None) -> dict:
    """Thread-safe sync wrapper for Gunicorn worker threads."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(get_youtube_transcript_async(url_or_id, user_api_key))
    except Exception as e:
        logger.error(f"get_youtube_transcript fallback error: {e}")
        video_id = extract_video_id(url_or_id) if ("http" in str(url_or_id) or "/" in str(url_or_id)) else str(url_or_id).strip()
        if not video_id:
            return {"success": False, "error": "Please enter a valid YouTube link or story premise."}
        meta = get_youtube_metadata(video_id)
        title = meta.get("title", f"YouTube Video ({video_id})")
        desc = meta.get("description", "")
        combined = f"Title: {title}\nChannel: {meta.get('author', '')}\n{desc}".strip()
        return {
            "success": True,
            "video_id": video_id,
            "title": title,
            "author": meta.get("author", "YouTube"),
            "transcript": combined[:15000],
            "word_count": len(combined.split()),
            "source_type": "fallback_metadata"
        }
    finally:
        try:
            loop.close()
        except Exception:
            pass
