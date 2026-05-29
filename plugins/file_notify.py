"""
Feature: Auto Notification for New Files
- Per-user on/off toggle stored in MongoDB
- /notify on  — subscribe to new file alerts
- /notify off — unsubscribe
- /notify     — check current status
- Batched digest every 30 min via scheduler (not per-file spam)
- Admin can broadcast a file notification manually: /notifyfile <file_id>
"""
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users_chats_db import db
from info import ADMINS, LOG_CHANNEL
from utils import temp

logger = logging.getLogger(__name__)

# In-memory queue — new file names accumulate here between scheduler runs
NEW_FILES_QUEUE: list = []


def queue_new_file(file_name: str, file_id: str):
    """Called from channel.py / save_file() after a new file is indexed."""
    NEW_FILES_QUEUE.append({"name": file_name, "id": file_id})


async def flush_new_file_notifications(bot):
    """
    Called by scheduler every 30 min.
    Sends a digest of all queued new files to subscribed users.
    Clears the queue after sending.
    """
    if not NEW_FILES_QUEUE:
        return

    files = NEW_FILES_QUEUE.copy()
    NEW_FILES_QUEUE.clear()

    subscribers = await db.get_notify_subscribers()
    if not subscribers:
        return

    # Build digest message
    if len(files) == 1:
        text = (
            f"🆕 <b>New file added!</b>

"
            f"📂 <code>{files[0]['name']}</code>

"
            f"Search it now or tap /off to turn off notifications."
        )
    else:
        lines = "
".join(f"  • <code>{f['name']}</code>" for f in files[:15])
        more = f"
  <i>...and {len(files)-15} more</i>" if len(files) > 15 else ""
        text = (
            f"🆕 <b>{len(files)} new files added!</b>

"
            f"{lines}{more}

"
            f"Search them now or use /notify off to unsubscribe."
        )

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔕 Turn Off", callback_data="notify_off"),
        InlineKeyboardButton("🔍 Search Now", switch_inline_query="")
    ]])

    sent, failed = 0, 0
    for user_id in subscribers:
        try:
            await bot.send_message(user_id, text, reply_markup=buttons)
            sent += 1
            await asyncio.sleep(0.05)   # flood prevention
        except Exception:
            failed += 1

    logger.info(f"File notify digest: {len(files)} files → {sent} sent, {failed} failed")
    try:
        await bot.send_message(
            LOG_CHANNEL,
            f"#FileNotifyDigest
"
            f"📤 Sent digest of {len(files)} new files
"
            f"👥 Subscribers notified: <code>{sent}</code>
"
            f"❌ Failed: <code>{failed}</code>"
        )
    except Exception:
        pass


# ── /notify command ───────────────────────────────────────────────────────────
@Client.on_message(filters.command("notify") & filters.private)
async def notify_cmd(bot, message):
    user_id = message.from_user.id
    args = message.command[1:]

    if not args:
        status = await db.get_notify_status(user_id)
        emoji = "🔔" if status else "🔕"
        await message.reply(
            f"{emoji} New file notifications are currently "
            f"<b>{'ON' if status else 'OFF'}</b> for you.

"
            f"Use /notify on or /notify off to change.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🔕 Turn Off" if status else "🔔 Turn On",
                    callback_data="notify_off" if status else "notify_on"
                )
            ]])
        )
        return

    action = args[0].lower()
    if action == "on":
        await db.set_notify_status(user_id, True)
        await message.reply(
            "🔔 <b>Notifications ON!</b>

"
            "You'll get a digest whenever new files are added to the database.
"
            "Use /notify off to stop anytime."
        )
    elif action == "off":
        await db.set_notify_status(user_id, False)
        await message.reply(
            "🔕 <b>Notifications OFF.</b>

"
            "You won't receive new file alerts anymore.
"
            "Use /notify on to re-subscribe anytime."
        )
    else:
        await message.reply("Usage: /notify on | /notify off | /notify")


# ── inline toggle callbacks ────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex("^notify_on$"))
async def notify_on_cb(bot, query):
    await query.answer()
    await db.set_notify_status(query.from_user.id, True)
    await query.message.edit_text(
        "🔔 <b>Notifications ON!</b>

"
        "You'll receive a digest when new files are indexed.
"
        "Use /notify off to stop anytime.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔕 Turn Off", callback_data="notify_off")
        ]])
    )


@Client.on_callback_query(filters.regex("^notify_off$"))
async def notify_off_cb(bot, query):
    await query.answer()
    await db.set_notify_status(query.from_user.id, False)
    await query.message.edit_text(
        "🔕 <b>Notifications OFF.</b>

"
        "You won't receive new file alerts.
"
        "Use /notify on to re-subscribe.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔔 Turn On", callback_data="notify_on")
        ]])
    )


# ── admin: manual file notification blast ─────────────────────────────────────
@Client.on_message(filters.command("notifyfile") & filters.user(ADMINS))
async def notify_file_cmd(bot, message):
    """Force-send a single file notification to all subscribers immediately."""
    args = message.command[1:]
    if not args:
        return await message.reply("Usage: /notifyfile <file_name>")
    file_name = " ".join(args)
    queue_new_file(file_name, "manual")
    await flush_new_file_notifications(bot)
    await message.reply(f"✅ Notification sent for: <code>{file_name}</code>")
