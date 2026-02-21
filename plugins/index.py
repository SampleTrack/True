import logging
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid,
    ChatAdminRequired,
    UsernameInvalid,
    UsernameNotModified,
)
from info import ADMINS
from info import INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Per-chat locking and cancellation tracking
indexing_locks = {}
active_cancellations = set()

def get_lock(chat_id):
    if chat_id not in indexing_locks:
        indexing_locks[chat_id] = asyncio.Lock()
    return indexing_locks[chat_id]

@Client.on_callback_query(filters.regex(r"^index"))
async def index_files(bot, query):
    """Handle index callback queries."""
    data = query.data.split("#")
    action = data[0]

    if action == "index_cancel":
        chat_to_cancel = data[1]
        active_cancellations.add(chat_to_cancel)
        return await query.answer("Cancelling Indexing...", show_alert=True)

    # Expected: index#accept#chat_id#msg_id#user_id
    if len(data) < 5:
        return await query.answer("Invalid Data", show_alert=True)

    _, status, chat, lst_msg_id, from_user = data

    if status == "reject":
        await query.message.delete()
        try:
            await bot.send_message(
                int(from_user),
                f"Your submission for indexing {chat} was declined.",
            )
        except: pass
        return

    chat_lock = get_lock(chat)
    if chat_lock.locked():
        return await query.answer("Wait! A process is already running for this chat.", show_alert=True)

    await query.answer("Starting Indexing... ⏳", show_alert=True)

    if int(from_user) not in ADMINS:
        try:
            await bot.send_message(
                int(from_user),
                f"Your indexing request for {chat} has been accepted and is starting.",
            )
        except: pass

    await query.message.edit(
        f"**Indexing Started**\nChat: `{chat}`",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Cancel", callback_data=f"index_cancel#{chat}")]]
        ),
    )

    await index_files_to_db(int(lst_msg_id), chat, query.message, bot)


@Client.on_message(
    (filters.forwarded | filters.regex(r"(t\.me/(c/)?(?P<group>\d+|[a-zA-Z_0-9]+)/(?P<id>\d+))"))
    & filters.private
)
async def send_for_index(bot, message):
    """Handle the indexing request."""
    chat_id = None
    last_msg_id = None

    # Fix: Access regex matches via message.matches
    if message.matches:
        match = message.matches[0]
        chat_id = match.group("group")
        last_msg_id = int(match.group("id"))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        chat_id = message.forward_from_chat.id
        last_msg_id = message.forward_from_message_id
    else:
        return

    try:
        chat_info = await bot.get_chat(chat_id)
        chat_id = chat_info.id # Normalize to integer ID
    except Exception as e:
        return await message.reply(f"Error accessing chat: {e}")

    # Ensure buttons don't exceed 64 byte limit
    btn = [[
        InlineKeyboardButton("Accept", callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}"),
        InlineKeyboardButton("Reject", callback_data=f"index#reject#{chat_id}#{last_msg_id}#{message.from_user.id}")
    ]]

    if message.from_user.id in ADMINS:
        await message.reply(
            f"**Admin Direct Index**\n\n**Chat:** `{chat_info.title}`\n**ID:** `{chat_id}`", 
            reply_markup=InlineKeyboardMarkup(btn)
        )
    else:
        await bot.send_message(
            LOG_CHANNEL, 
            f"#IndexRequest\n\n**By:** {message.from_user.mention}\n**Chat:** `{chat_info.title}`\n**ID:** `{chat_id}`", 
            reply_markup=InlineKeyboardMarkup(btn)
        )
        await message.reply("✅ Your contribution request has been sent to moderators.")


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    """Core indexing logic with loop-based FloodWait handling."""
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    current_count = 0
    
    chat_str = str(chat)
    # Reset cancellation state for this chat
    if chat_str in active_cancellations:
        active_cancellations.remove(chat_str)

    async with get_lock(chat):
        try:
            # We use get_chat_history to iterate backwards from the last_msg_id
            async for message in bot.get_chat_history(chat, offset_id=lst_msg_id + 1):
                
                # Check for per-chat cancellation
                if chat_str in active_cancellations:
                    active_cancellations.remove(chat_str)
                    await msg.edit(f"❌ Indexing Cancelled!\nSaved: `{total_files}` files.")
                    return

                current_count += 1
                
                # Update progress every 20 messages
                if current_count % 20 == 0:
                    try:
                        await msg.edit_text(
                            f"**Indexing in Progress...**\n\n"
                            f"Scanned: `{current_count}`\n"
                            f"Saved: `{total_files}`\n"
                            f"Duplicates: `{duplicate}`",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("Cancel", callback_data=f"index_cancel#{chat}")
                            ]])
                        )
                    except: pass

                if message.empty:
                    deleted += 1
                    continue
                if not message.media:
                    no_media += 1
                    continue
                
                m_type = message.media
                if m_type not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    unsupported += 1
                    continue

                media = getattr(message, m_type.name.lower(), None)
                if not media:
                    continue

                media.file_type = m_type.name.lower()
                media.caption = message.caption or ""

                try:
                    success, result_code = await save_file(media)
                    if success: total_files += 1
                    elif result_code == 0: duplicate += 1
                    else: errors += 1
                except Exception as e:
                    errors += 1
                    logger.error(f"DB Error: {e}")

                # Avoid hitting rate limits immediately
                await asyncio.sleep(0.1)

        except FloodWait as e:
            await msg.edit(f"⚠️ FloodWait: Sleeping for {e.value}s...")
            await asyncio.sleep(e.value)
            # Recursion is avoided; you'd manually restart or wrap in a while loop
            await msg.edit("FloodWait finished. Please click 'Accept' again to resume from where it stopped.")
            return
        except Exception as e:
            logger.exception(e)
            await msg.edit(f"❌ Critical Error: `{e}`")
            return

        await msg.edit(
            f"**✅ Indexing Complete**\n\n"
            f"Total Files Saved: `{total_files}`\n"
            f"Duplicates Skipped: `{duplicate}`\n"
            f"Empty/Deleted: `{deleted}`\n"
            f"Non-Media: `{no_media + unsupported}`"
        )
