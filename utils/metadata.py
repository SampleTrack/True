"""
Smart Metadata Extraction Pipeline

Layer 1 — Free, instant, zero downloads:
  • Telegram built-in fields (duration, width, height, audio title/performer)
  • Smart regex on filename + caption
    (year, quality, language, codec, audio, season/episode)
  • Caption cleaner (strips emojis, @tags, channel links)
  • Generic filename detector (falls back to caption if name is useless)
  • IMDb verification to get official title, rating, genres

Layer 2 — Partial download (first 5 MB only):
  • Streams first 5MB of file from Telegram
  • Runs ffprobe on partial data
  • Extracts: audio track languages, subtitle languages, codec, HDR info
  • Deletes temp file immediately after
  • Disabled automatically if ffprobe not installed
  • Can be disabled via ENABLE_METADATA_DOWNLOAD=False env var

Result: every file saved with accurate title, year, language list,
        quality, codec, subtitles, IMDb data — making search precise.
"""
import re
import os
import json
import logging
import asyncio
import tempfile
import subprocess
from imdb import IMDb
from info import ENABLE_METADATA_DOWNLOAD

logger = logging.getLogger(__name__)
imdb_client = IMDb()

# ── Regex Patterns ────────────────────────────────────────────────────────────
YEAR_RE     = re.compile(r'\b(19[5-9]\d|20[0-3]\d)\b')
QUALITY_RE  = re.compile(
    r'\b(4K|2160p|1080p|720p|480p|360p|240p|HDR10?\+?|SDR|Blu-?Ray|BRRip|BDRip'    r'|WEB-?DL|WEBRip|HDTV|DVDRip|DVDScr|CAMRip|\bTS\b|HDCAM|HQ)\b', re.IGNORECASE)
LANGUAGE_RE = re.compile(
    r'\b(Hindi|Tamil|Telugu|Malayalam|Kannada|Bengali|Punjabi|Marathi|Gujarati'    r'|English|Korean|Japanese|Chinese|Mandarin|Spanish|French|German|Italian'    r'|Russian|Arabic|Turkish|Dubbed|Dual[\s\-]?Audio|Multi[\s\-]?Audio'    r'|ORG|Original)\b', re.IGNORECASE)
CODEC_RE    = re.compile(
    r'\b(x264|x265|HEVC|AVC|H\.?264|H\.?265|VP9|AV1|XviD|DivX)\b', re.IGNORECASE)
AUDIO_RE    = re.compile(
    r'\b(AAC|AC3|\bDD\b|DTS|Dolby|Atmos|EAC3|MP3|FLAC|5\.1|7\.1|2\.0)\b', re.IGNORECASE)
EPISODE_RE  = re.compile(
    r'\b(S\d{1,2}E\d{1,2}|S\d{1,2}|Season\s?\d+|Episode\s?\d+|Ep\s?\d+)\b', re.IGNORECASE)
JUNK_RE     = re.compile(r'@\w+|https?://\S+|t\.me/\S+')
EMOJI_RE    = re.compile(
    "[\U00010000-\U0010ffff"
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F9FF"
    "\u2600-\u26FF\u2700-\u27BF]+",
    flags=re.UNICODE)

# Filenames so generic they tell us nothing
GENERIC_NAMES = {
    'movie', 'video', 'file', 'upload', 'unknown', 'untitled',
    'sample', 'test', 'clip', 'trailer', 'teaser', 'scene'
}


# ── Layer 1 helpers ───────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Remove emojis, @mentions, URLs, extra symbols."""
    text = JUNK_RE.sub(' ', text)
    text = EMOJI_RE.sub(' ', text)
    text = re.sub(r'[^\w\s\.\-\(\)\[\]]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def is_generic(name: str) -> bool:
    """Returns True if the filename is too generic to be useful."""
    if not name:
        return True
    stem = re.sub(r'\.[a-z0-9]{2,4}$', '', name.lower()).strip()
    stem_clean = re.sub(r'[^a-z]', '', stem)
    return stem_clean in GENERIC_NAMES or len(stem_clean) < 3


def parse_tags(text: str) -> dict:
    """Extract structured tags from any text string."""
    years     = YEAR_RE.findall(text)
    qualities = QUALITY_RE.findall(text)
    languages = [m.title() for m in LANGUAGE_RE.findall(text)]
    codecs    = CODEC_RE.findall(text)
    audios    = AUDIO_RE.findall(text)
    episodes  = EPISODE_RE.findall(text)
    is_dubbed = bool(re.search(r'\b(dubbed|dual|multi)\b', text, re.IGNORECASE))
    is_series = bool(episodes)
    return {
        'year'      : years[0] if years else None,
        'quality'   : qualities[0].upper() if qualities else None,
        'languages' : list(dict.fromkeys(languages)),   # deduplicated
        'codec'     : codecs[0].upper() if codecs else None,
        'audio'     : audios[0].upper() if audios else None,
        'episode'   : episodes[0].upper() if episodes else None,
        'is_dubbed' : is_dubbed,
        'is_series' : is_series,
    }


def extract_clean_title(text: str) -> str:
    """
    Strip all known tags from text to get the bare movie/show title.
    e.g. "RRR.2022.Hindi.1080p.x265.mkv" → "RRR"
    """
    text = re.sub(r'\.[a-z0-9]{2,4}$', '', text, flags=re.IGNORECASE)  # extension
    text = re.sub(r'[_\.]', ' ', text)                                   # separators
    for pattern in [YEAR_RE, QUALITY_RE, LANGUAGE_RE, CODEC_RE,
                    AUDIO_RE, EPISODE_RE]:
        text = pattern.sub('', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove common junk words
    for word in ['bluray', 'webrip', 'webdl', 'hdrip', 'dvdrip',
                 'proper', 'repack', 'extended', 'theatrical',
                 'directors', 'cut', 'unrated', 'rip']:
        text = re.sub(rf'\b{word}\b', '', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text).strip().title()


# ── Layer 1 — IMDb verification ───────────────────────────────────────────────

async def verify_with_imdb(title: str, year: str = None) -> dict:
    """Search IMDb for the title and return enriched data if found."""
    if not title or len(title) < 2:
        return {}
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: imdb_client.search_movie(title, results=5)
        )
        if not results:
            return {}
        # Filter by year if we have it
        if year:
            filtered = [r for r in results if str(r.get('year', '')) == str(year)]
            results = filtered if filtered else results

        best = results[0]
        movie_id = best.movieID
        movie = await loop.run_in_executor(
            None, lambda: imdb_client.get_movie(movie_id)
        )
        genres = movie.get('genres', [])
        rating = str(movie.get('rating', ''))
        languages = movie.get('languages', [])
        return {
            'imdb_id'     : f"tt{movie_id}",
            'imdb_title'  : movie.get('title', title),
            'imdb_year'   : str(movie.get('year', year or '')),
            'imdb_rating' : rating,
            'genres'      : genres[:5],
            'imdb_languages': [l.title() for l in languages[:5]],
        }
    except Exception as e:
        logger.debug(f"IMDb lookup failed for '{title}': {e}")
        return {}


# ── Layer 2 — Partial download + ffprobe ──────────────────────────────────────

def ffprobe_available() -> bool:
    try:
        subprocess.run(['ffprobe', '-version'],
                       capture_output=True, timeout=3)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


async def extract_ffprobe_metadata(bot, message) -> dict:
    """
    Download first 5 MB of the file and run ffprobe on it.
    Returns audio languages, subtitle languages, codec details.
    Falls back gracefully if ffprobe not installed or download fails.
    """
    if not ENABLE_METADATA_DOWNLOAD:
        return {}
    if not ffprobe_available():
        logger.debug("ffprobe not found — skipping Layer 2")
        return {}

    tmp_path = None
    try:
        # Stream first 5 MB only
        MAX_BYTES = 5 * 1024 * 1024
        data = b""
        async for chunk in bot.stream_media(message):
            data += chunk
            if len(data) >= MAX_BYTES:
                break

        if len(data) < 4096:   # too small to be useful
            return {}

        # Write to temp file
        suffix = '.mkv' if 'matroska' in (getattr(message, 'mime_type', '') or '') else '.mp4'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(data)
            tmp_path = f.name

        # Run ffprobe
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams', '-show_format',
            tmp_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {}

        probe = json.loads(result.stdout)
        streams = probe.get('streams', [])
        fmt     = probe.get('format', {})
        tags    = fmt.get('tags', {})

        audio_langs = []
        sub_langs   = []
        video_codec = None
        is_hdr      = False

        for s in streams:
            stype = s.get('codec_type', '')
            slang = s.get('tags', {}).get('language', '').lower()
            codec = s.get('codec_name', '')

            if stype == 'video':
                video_codec = codec.upper() if codec else None
                color_space = s.get('color_space', '')
                color_transfer = s.get('color_transfer', '')
                if 'bt2020' in color_space or 'smpte2084' in color_transfer:
                    is_hdr = True

            elif stype == 'audio' and slang:
                lang_map = {
                    'hin': 'Hindi',  'tam': 'Tamil',  'tel': 'Telugu',
                    'mal': 'Malayalam', 'kan': 'Kannada', 'ben': 'Bengali',
                    'eng': 'English', 'jpn': 'Japanese', 'kor': 'Korean',
                    'zho': 'Chinese', 'spa': 'Spanish', 'fra': 'French',
                    'ara': 'Arabic',  'rus': 'Russian', 'tur': 'Turkish',
                }
                mapped = lang_map.get(slang[:3], slang.title())
                if mapped not in audio_langs:
                    audio_langs.append(mapped)

            elif stype == 'subtitle' and slang:
                lang_map = {
                    'eng': 'English', 'hin': 'Hindi', 'tam': 'Tamil',
                    'tel': 'Telugu',  'ara': 'Arabic', 'fra': 'French',
                }
                mapped = lang_map.get(slang[:3], slang.title())
                if mapped not in sub_langs:
                    sub_langs.append(mapped)

        # Embedded title tag (some encoders set this correctly)
        embedded_title = tags.get('title', '') or tags.get('TITLE', '')

        return {
            'audio_languages'   : audio_langs,
            'subtitle_languages': sub_langs,
            'ffprobe_codec'     : video_codec,
            'is_hdr'            : is_hdr,
            'embedded_title'    : embedded_title.strip() if embedded_title else '',
        }

    except Exception as e:
        logger.warning(f"ffprobe extraction failed: {e}")
        return {}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def build_file_metadata(bot, message) -> dict:
    """
    Main entry point. Returns the richest possible metadata dict.
    Combines Layer 1 (free) + Layer 2 (optional partial download).
    """
    # ── Step 1: get raw text sources ──────────────────────────────────────────
    media = (message.document or message.video or message.audio
             or message.animation or message.voice or message.photo)

    raw_filename = getattr(media, 'file_name', None) or ''
    raw_caption  = (message.caption.text if message.caption else '') or ''
    file_size    = getattr(media, 'file_size', 0) or 0
    mime_type    = getattr(media, 'mime_type', '') or ''
    duration     = getattr(media, 'duration', None)
    width        = getattr(media, 'width', None)
    height       = getattr(media, 'height', None)

    # Telegram reads ID3 tags for audio automatically
    audio_title     = getattr(media, 'title', '') or ''
    audio_performer = getattr(media, 'performer', '') or ''

    clean_filename = clean_text(raw_filename)
    clean_caption  = clean_text(raw_caption)

    # ── Step 2: decide best text source for tagging ───────────────────────────
    # Priority: audio_title > caption (if not generic) > filename (if not generic) > caption
    if audio_title:
        best_text = f"{audio_title} {audio_performer}"
    elif clean_caption and not is_generic(clean_caption):
        best_text = clean_caption
    elif clean_filename and not is_generic(clean_filename):
        best_text = clean_filename
    elif clean_caption:
        best_text = clean_caption
    else:
        best_text = f"unknown_{message.id}"

    # ── Step 3: parse tags from best_text ─────────────────────────────────────
    tags = parse_tags(best_text)
    raw_title = extract_clean_title(best_text)

    # ── Step 4: build display name (what gets saved as file_name in DB) ───────
    # This is what users search for — make it clean and consistent
    parts = [raw_title]
    if tags['year']:      parts.append(tags['year'])
    if tags['languages']: parts.append(' '.join(tags['languages'][:2]))
    if tags['quality']:   parts.append(tags['quality'])
    if tags['episode']:   parts.append(tags['episode'])
    display_name = ' '.join(parts) if raw_title else best_text[:100]

    # ── Step 5: IMDb verification (Layer 1) ───────────────────────────────────
    imdb_data = {}
    if raw_title and len(raw_title) > 2 and not tags['is_series']:
        imdb_data = await verify_with_imdb(raw_title, tags['year'])

    # ── Step 6: ffprobe partial download (Layer 2, optional) ─────────────────
    ffprobe_data = {}
    if message.video or message.document:
        ffprobe_data = await extract_ffprobe_metadata(bot, message)

    # ── Step 7: merge language data (regex + ffprobe + IMDb) ──────────────────
    all_languages = list(tags['languages'])
    for lang in ffprobe_data.get('audio_languages', []):
        if lang not in all_languages:
            all_languages.append(lang)
    # IMDb languages are original — less useful for dubbed content, use as fallback
    if not all_languages:
        all_languages = imdb_data.get('imdb_languages', [])

    # ── Step 8: resolve codec ─────────────────────────────────────────────────
    codec = (ffprobe_data.get('ffprobe_codec')
             or tags['codec']
             or ('HEVC' if '265' in mime_type else None))

    # ── Step 9: use embedded title if our parse looks wrong ──────────────────
    embedded = ffprobe_data.get('embedded_title', '')
    if embedded and len(embedded) > 2 and not is_generic(embedded):
        better_tags = parse_tags(embedded)
        if better_tags['year'] or not tags['year']:   # embedded title looks richer
            title_to_use = extract_clean_title(embedded) or raw_title
        else:
            title_to_use = raw_title
    else:
        title_to_use = imdb_data.get('imdb_title', raw_title)

    # ── Step 10: quality from height if not found in text ────────────────────
    if not tags['quality'] and height:
        if height >= 2160:   tags['quality'] = '4K'
        elif height >= 1080: tags['quality'] = '1080p'
        elif height >= 720:  tags['quality'] = '720p'
        elif height >= 480:  tags['quality'] = '480p'
        else:                tags['quality'] = f'{height}p'

    return {
        # ── Core search fields ────────────────────────────────────────────────
        'file_name'         : display_name,          # cleaned, structured name
        'title'             : title_to_use,           # bare title only
        'year'              : tags['year'] or imdb_data.get('imdb_year', ''),
        'languages'         : all_languages,          # ["Hindi", "Tamil"]
        'quality'           : tags['quality'],        # "1080p"
        'codec'             : codec,                  # "HEVC"
        'audio_codec'       : tags['audio'],          # "AAC"
        'is_dubbed'         : tags['is_dubbed'],
        'is_series'         : tags['is_series'],
        'episode'           : tags['episode'],        # "S01E01"
        'subtitles'         : ffprobe_data.get('subtitle_languages', []),
        'is_hdr'            : ffprobe_data.get('is_hdr', False),
        # ── IMDb data ─────────────────────────────────────────────────────────
        'imdb_id'           : imdb_data.get('imdb_id', ''),
        'imdb_rating'       : imdb_data.get('imdb_rating', ''),
        'genres'            : imdb_data.get('genres', []),
        # ── Technical ─────────────────────────────────────────────────────────
        'duration'          : duration,
        'width'             : width,
        'height'            : height,
        'mime_type'         : mime_type,
    }
