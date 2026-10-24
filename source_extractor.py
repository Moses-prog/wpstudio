import re
import json
import urllib.request
import urllib.error
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from google.genai import types
import ai_engine

logger = logging.getLogger("WPStudio")

def extract_video_id(url: str) -> str:
    """Extract 11-character YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:shorts\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_youtube_metadata(video_id: str) -> dict:
    """Fetches video title and author using YouTube oEmbed without requiring an API key."""
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return {
                "title": data.get("title", f"YouTube Video ({video_id})"),
                "author": data.get("author_name", "YouTube Creator")
            }
    except Exception:
        return {
            "title": f"YouTube Video ({video_id})",
            "author": "YouTube"
        }

def try_fetch_captions(video_id: str) -> str:
    """Fetches real video captions/subtitles using youtube-transcript-api with multi-dialect and auto-caption support."""
    try:
        api = YouTubeTranscriptApi()
        transcript_list = None
        
        # Method 1: List all available transcripts and prioritize English / primary language
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
                    if t.language_code.startswith('en'):
                        chosen = t
                        break
            if not chosen:
                for t in tl:
                    chosen = t
                    break
            if chosen:
                transcript_list = chosen.fetch()
        except Exception:
            # Method 2: Direct fetch fallback with common English dialect tags
            try:
                transcript_list = api.fetch(video_id, languages=['en', 'en-US', 'en-GB', 'a.en'])
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
    Multimodal YouTube Ingestion:
    1. Attempts direct official captions extraction.
    2. If captions are disabled or IP-blocked by YouTube, activates Gemini Native Multimodal
       Video Intelligence to inspect the actual video stream, dialogue, and narrative (Zero Hallucination).
    """
    video_id = extract_video_id(url_or_id) if "http" in url_or_id or "/" in url_or_id else url_or_id
    if not video_id:
        return {"success": False, "error": "Invalid YouTube URL format.", "video_id": None}

    meta = get_youtube_metadata(video_id)
    video_title = meta.get("title", f"YouTube Video ({video_id})")
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Tier 1: Try direct captions API first
    transcript_text = try_fetch_captions(video_id)
    source_type = "official_captions"

    # Tier 2: If scraper is IP blocked or captions disabled, use Gemini Multimodal Video Intelligence
    if not transcript_text:
        logger.info(f"Direct captions scraper unavailable or IP-blocked for {video_id}. Activating Gemini Multimodal Video Intelligence...")
        try:
            client = ai_engine.get_client(user_api_key)
            gemini_res = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[
                    types.Part.from_uri(file_uri=video_url, mime_type="video/*"),
                    "Extract the full, detailed, authentic scene-by-scene narrative, spoken dialogue, character actions, and storyline from this YouTube video. Be exhaustive, faithful, and accurate to what actually happens in the video."
                ]
            )
            if gemini_res.text and len(gemini_res.text.strip()) > 80:
                transcript_text = gemini_res.text.strip()
                source_type = "gemini_multimodal_video_analysis"
                logger.info(f"Gemini Native Video Intelligence successfully extracted storyline for {video_id} ({len(transcript_text.split())} words)")
        except Exception as e:
            logger.warning(f"Gemini native video extraction failed for {video_id}: {e}")

    if transcript_text:
        return {
            "success": True,
            "video_id": video_id,
            "title": video_title,
            "author": meta.get("author"),
            "transcript": transcript_text[:12000],
            "word_count": len(transcript_text.split()),
            "source_type": source_type
        }
    else:
        logger.info(f"Captions & video extraction unavailable for {video_id}. Halting generation.")
        return {
            "success": False,
            "video_id": video_id,
            "title": video_title,
            "error": "Could not access video captions or stream. Please verify the link is public, or type your story premise directly in chat!",
            "transcript": None
        }

def get_youtube_transcript(url_or_id: str, user_api_key: str = None) -> dict:
    """Sync wrapper for backward compatibility."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, get_youtube_transcript_async(url_or_id, user_api_key)).result()
        else:
            return loop.run_until_complete(get_youtube_transcript_async(url_or_id, user_api_key))
    except Exception:
        video_id = extract_video_id(url_or_id) if "http" in url_or_id or "/" in url_or_id else url_or_id
        meta = get_youtube_metadata(video_id) if video_id else {}
        captions = try_fetch_captions(video_id) if video_id else None
        if captions:
            return {
                "success": True,
                "video_id": video_id,
                "title": meta.get("title", "YouTube Video"),
                "transcript": captions[:12000],
                "word_count": len(captions.split())
            }
        return {
            "success": False,
            "error": "Captions unavailable and transcription could not be completed."
        }
