"""
Auto-save files from indexed channels with full metadata extraction.
Every file posted by admin gets:
  - Smart name resolution (caption > filename > fallback)
  - Language, year, quality, codec parsed from name/caption
  - IMDb verification for official title + rating
  - ffprobe partial download for actual audio/subtitle tracks (if enabled)
  - Duplicate detection via content hash
  - Detailed LOG_CHANNEL notification
  - Admin warned if file saved with suspicious/fallback name
"""
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from database.ia_filterdb import Media, save_file
from database.users_chats_db import db
from info import CHANNELS, LOG_CHANNEL, INDEX_REQ_CHANNEL
from utils import temp, get_size
from utils.metadata import build_file_metadata, is_generic

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = ("document", "video", "audio", "animation", "voice", "photo")


async def save_media(bot, message: Message):
    """
    Core save function. Called from:
      - on_message handler (auto-index on new post)
      - auto_index_task (scheduler)
      - /index command
    Returns (saved: bool, status_code: int)
    """
    # Find the media object
    media = None
    file_type = None
    for t in SUPPORTED_TYPES:
        obj = getattr(message, t, None)
        if obj:
            media = obj
            file_type = t
            break

    if not media:
        return False, -1

    # ── Run full metadata pipeline ────────────────────────────────────────────
    try:
        meta = await build_file_metadata(bot, message)
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        # Fallback: use raw fields
        raw_name = getattr(media, "file_name", None) or ""
        caption  = (message.caption.text if message.caption else "") or ""
        meta = {
            "file_name" : raw_name or caption or f"{file_type}_{message.id}",
            "title"     : None, "year": None, "languages": [],
            "quality"   : None, "codec": None, "audio_codec": None,
            "subtitles" : [], "is_dubbed": False, "is_series": False,
            "episode"   : None, "is_hdr": False, "duration": None,
            "width"     : None, "height": None, "imdb_id": None,
            "imdb_rating": None, "genres": [], "mime_type": "",
        }

    # ── Attach metadata to media object for save_file() ──────────────────────
    media.file_name  = meta["file_name"]
    media.file_size  = getattr(media, "file_size", 0) or 0
    media.file_type  = file_type
    media.mime_type  = meta.get("mime_type") or getattr(media, "mime_type", "")
    media.caption    = message.caption

    for field in ("title", "year", "languages", "quality", "codec",
                  "audio_codec", "subtitles", "is_dubbed", "is_series",
                  "episode", "is_hdr", "duration", "width", "height",
                  "imdb_id", "imdb_rating", "genres"):
        setattr(media, field, meta.get(field))

    saved, status = await save_file(media)

    if saved:
        # Update last indexed msg id for scheduler
        await db.set_last_indexed_msg_id(message.chat.id, message.id)

    return saved, status


# ── Handler: fires on every new post in indexed channels ─────────────────────
@Client.on_message(filters.channel & filters.incoming)
async def channel_post_handler(bot, message: Message):
    if message.chat.id not in CHANNELS:
        return

    saved, status = await save_media(bot, message)

    if not saved:
        if status == 0:
            # Duplicate — silent, no log needed
            return
        elif status == -1:
            # No media in message — ignore (text post)
            return
        else:
            # Validation error — alert admin
            await bot.send_message(
                LOG_CHANNEL,
                f"#IndexError
"
                f"❌ Failed to save file from {message.chat.title}
"
                f"Message ID: <code>{message.id}</code>
"
                f"Status: <code>{status}</code>"
            )
        return

    # ── Build rich log message ────────────────────────────────────────────────
    media = (message.document or message.video or message.audio
             or message.animation or message.voice or message.photo)
    file_name   = getattr(media, "file_name", "Unknown")
    file_size   = get_size(getattr(media, "file_size", 0))
    title       = getattr(media, "title", None)
    year        = getattr(media, "year", None)
    languages   = getattr(media, "languages", [])
    quality     = getattr(media, "quality", None)
    codec       = getattr(media, "codec", None)
    subtitles   = getattr(media, "subtitles", [])
    imdb_id     = getattr(media, "imdb_id", None)
    imdb_rating = getattr(media, "imdb_rating", None)
    genres      = getattr(media, "genres", [])
    is_hdr      = getattr(media, "is_hdr", False)
    is_dubbed   = getattr(media, "is_dubbed", False)
    episode     = getattr(media, "episode", None)

    # Warn admin if name still looks generic
    name_warning = ""
    if is_generic(file_name):
        name_warning = (
            "

⚠️ <b>Warning:</b> File saved with a generic name. "
            "Please use /rename to correct it."
        )

    lang_str = ", ".join(languages) if languages else "Unknown"
    sub_str  = ", ".join(subtitles) if subtitles else "None"
    genre_str = ", ".join(genres[:3]) if genres else "N/A"
    hdr_str  = " | HDR" if is_hdr else ""
    dub_str  = " | Dubbed" if is_dubbed else ""

    log_text = (
        f"#NewFile ✅

"
        f"📂 <b>{file_name}</b>

"
        f"🎬 Title: <code>{title or 'N/A'}</code>
"
        f"📅 Year: <code>{year or 'N/A'}</code>
"
        f"🌐 Languages: <code>{lang_str}</code>{dub_str}
"
        f"📺 Quality: <code>{quality or 'N/A'}{hdr_str}</code>
"
        f"⚙️ Codec: <code>{codec or 'N/A'}</code>
"
        f"📝 Subtitles: <code>{sub_str}</code>
"
        f"🎭 Genres: <code>{genre_str}</code>
"
        f"⭐ IMDb: <code>{imdb_rating or 'N/A'}</code>"
        + (f" | <a href='https://www.imdb.com/title/{imdb_id}'>View</a>" if imdb_id else "")
        + (f"
🎞 Episode: <code>{episode}</code>" if episode else "")
        + f"
💾 Size: <code>{file_size}</code>"
        + f"
📢 Channel: {message.chat.title}"
        + name_warning
    )

    await bot.send_message(LOG_CHANNEL, log_text,
                           disable_web_page_preview=True)
