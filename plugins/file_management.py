"""
Admin file management commands:
  /rename  <file_id> <new name>  — fix wrong file names in DB
  /fileinfo <name>               — show full stored metadata for a file
  /delfile  <name>               — delete wrong entry, admin reposts properly
  /searchadv                     — advanced search with language/year/quality filters
"""
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.ia_filterdb import Media, get_search_results
from database.users_chats_db import db
from info import ADMINS, LOG_CHANNEL
from utils import get_size, humanbytes

logger = logging.getLogger(__name__)


# ── /rename ───────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("rename") & filters.user(ADMINS))
async def rename_cmd(bot, message):
    """Usage: reply to a bot file message with /rename New File Name"""
    args = message.command[1:]
    if not args:
        return await message.reply(
            "Usage: /rename <new name>
"
            "Reply to the file message you want to rename."
        )
    if not message.reply_to_message:
        return await message.reply("Reply to a file message to rename it.")

    new_name = " ".join(args).strip()
    reply = message.reply_to_message
    media = (reply.document or reply.video or reply.audio
             or reply.animation or reply.voice)
    if not media:
        return await message.reply("That message has no media.")

    from database.ia_filterdb import unpack_new_file_id
    try:
        file_id, _ = unpack_new_file_id(media.file_id)
    except Exception:
        return await message.reply("Could not resolve file ID.")

    result = await Media.collection.update_one(
        {"_id": file_id},
        {"$set": {"file_name": new_name}}
    )
    if result.modified_count:
        await message.reply(f"✅ Renamed to: <code>{new_name}</code>")
        await bot.send_message(LOG_CHANNEL,
            f"#FileRenamed
"
            f"✏️ File renamed by {message.from_user.mention}
"
            f"New name: <code>{new_name}</code>")
    else:
        await message.reply("❌ File not found in database. It may not be indexed yet.")


# ── /fileinfo ─────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("fileinfo") & filters.user(ADMINS))
async def fileinfo_cmd(bot, message):
    """Show full stored metadata for a file."""
    args = message.command[1:]
    if not args:
        return await message.reply("Usage: /fileinfo <file name or part of name>")
    query = " ".join(args)
    files, _, total = await get_search_results(query, max_results=1)
    if not files:
        return await message.reply(f"No file found matching: <code>{query}</code>")

    f = files[0]
    langs = ", ".join(f.get("languages") or []) or "N/A"
    subs  = ", ".join(f.get("subtitles") or []) or "None"
    genres= ", ".join(f.get("genres") or []) or "N/A"

    text = (
        f"📂 <b>File Info</b>

"
        f"📝 Name: <code>{f.get('file_name')}</code>
"
        f"🎬 Title: <code>{f.get('title') or 'N/A'}</code>
"
        f"📅 Year: <code>{f.get('year') or 'N/A'}</code>
"
        f"🌐 Languages: <code>{langs}</code>
"
        f"📝 Subtitles: <code>{subs}</code>
"
        f"📺 Quality: <code>{f.get('quality') or 'N/A'}"
        f"{'| HDR' if f.get('is_hdr') else ''}</code>
"
        f"⚙️ Codec: <code>{f.get('codec') or 'N/A'}</code>
"
        f"🎵 Audio: <code>{f.get('audio_codec') or 'N/A'}</code>
"
        f"🎭 Genres: <code>{genres}</code>
"
        f"⭐ IMDb: <code>{f.get('imdb_rating') or 'N/A'}</code>
"
        f"🔖 IMDb ID: <code>{f.get('imdb_id') or 'N/A'}</code>
"
        f"📼 Type: <code>{f.get('file_type') or 'N/A'}</code>
"
        f"💾 Size: <code>{humanbytes(f.get('file_size', 0))}</code>
"
        f"🔁 Dubbed: <code>{'Yes' if f.get('is_dubbed') else 'No'}</code>
"
        f"📺 Series: <code>{'Yes' if f.get('is_series') else 'No'}</code>
"
        f"🎞 Episode: <code>{f.get('episode') or 'N/A'}</code>
"
        f"📐 Resolution: <code>"
        f"{f.get('width') or '?'}x{f.get('height') or '?'}</code>
"
    )
    await message.reply(text)


# ── /delfile ──────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("delfile") & filters.user(ADMINS))
async def delfile_cmd(bot, message):
    """Delete a wrong file entry from DB."""
    args = message.command[1:]
    if not args:
        return await message.reply("Usage: /delfile <file name or part of name>")
    query = " ".join(args)
    files, _, total = await get_search_results(query, max_results=5)
    if not files:
        return await message.reply(f"No file found matching: <code>{query}</code>")

    buttons = [[
        InlineKeyboardButton(
            f"🗑 {f.get('file_name', 'Unknown')[:40]}",
            callback_data=f"delfile_confirm#{f.get('_id') or f.pk}"
        )
    ] for f in files]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="delfile_cancel")])
    await message.reply(
        f"Found <b>{total}</b> file(s). Select which to delete:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@Client.on_callback_query(filters.regex(r"^delfile_confirm#") & filters.user(ADMINS))
async def delfile_confirm_cb(bot, query):
    await query.answer()
    file_id = query.data.split("#", 1)[1]
    result = await Media.collection.delete_one({"_id": file_id})
    if result.deleted_count:
        await query.message.edit_text("✅ File deleted from database.")
        await bot.send_message(LOG_CHANNEL,
            f"#FileDeleted
"
            f"🗑 File <code>{file_id[:20]}...</code> deleted by {query.from_user.mention}")
    else:
        await query.message.edit_text("❌ File not found or already deleted.")


@Client.on_callback_query(filters.regex(r"^delfile_cancel$") & filters.user(ADMINS))
async def delfile_cancel_cb(bot, query):
    await query.answer()
    await query.message.delete()


# ── /searchadv — advanced search with filters ─────────────────────────────────
@Client.on_message(filters.command("searchadv") & filters.private)
async def advanced_search_cmd(bot, message):
    """
    Advanced search with filters.
    Usage: /searchadv RRR lang:Hindi year:2022 quality:1080p
    """
    args_text = " ".join(message.command[1:])
    if not args_text:
        return await message.reply(
            "Advanced Search Usage:
"
            "/searchadv <title> lang:<language> year:<year> quality:<quality>

"
            "Examples:
"
            "/searchadv RRR lang:Hindi
"
            "/searchadv Avengers year:2019 quality:1080p
"
            "/searchadv Breaking Bad lang:English quality:720p"
        )

    # Parse filter flags out of args
    import re
    lang_match    = re.search(r'lang:(\w+)', args_text, re.IGNORECASE)
    year_match    = re.search(r'year:(\d{4})', args_text)
    quality_match = re.search(r'quality:(\w+)', args_text, re.IGNORECASE)

    language = lang_match.group(1).title() if lang_match else None
    year     = year_match.group(1) if year_match else None
    quality  = quality_match.group(1) if quality_match else None

    # Strip flags from query to get clean title
    clean_query = re.sub(r'(lang|year|quality):\S+', '', args_text).strip()

    await message.reply(
        f"🔍 Searching: <code>{clean_query}</code>"
        + (f"
🌐 Language: <code>{language}</code>" if language else "")
        + (f"
📅 Year: <code>{year}</code>" if year else "")
        + (f"
📺 Quality: <code>{quality}</code>" if quality else "")
    )

    files, _, total = await get_search_results(
        clean_query, max_results=10,
        language=language, year=year, quality=quality
    )

    if not files:
        return await message.reply(
            f"❌ No results found for your search.

"
            f"Try removing some filters or check the spelling."
        )

    buttons = []
    for f in files:
        name = f.get("file_name", "Unknown")
        size = humanbytes(f.get("file_size", 0))
        fid  = f.get("_id") or f.pk
        langs = "/".join(f.get("languages") or [])
        yr   = f.get("year") or ""
        qual = f.get("quality") or ""
        label = f"{name[:30]} | {qual} {yr} {langs}".strip()
        buttons.append([InlineKeyboardButton(label, callback_data=f"file#{fid}")])

    await message.reply(
        f"🔍 Found <b>{total}</b> result(s):",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
