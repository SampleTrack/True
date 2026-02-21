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
    data = query.data.split("#")
    action = data[0]

    if action == "index_cancel":
        # Extract chat_id from the cancel callback
        chat_to_cancel = data[1]
        active_cancellations.add(chat_to_cancel)
        return await query.answer("Cancelling Indexing...", show_alert=True)

    # Standard indexing flow: index#accept#chat_id#msg_id#user_id
    _, status, chat, lst_msg_id, from_user = data

    if status == "reject":
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f"Your submission for indexing {chat} was declined.",
            reply_to_message_id=int(lst_msg_id),
        )
        return

    chat_lock = get_lock(chat)
    if chat_lock.locked():
        return await query.answer("An indexing process is already running for this chat.", show_alert=True)

    await query.answer("Starting... ⏳", show_alert=True)

    if int(from_user) not in ADMINS:
        await bot.send_message(
            int(from_user),
            f"Your indexing request for {chat} has been accepted.",
            reply_to_message_id=int(lst_msg_id),
        )

    await query.message.edit(
        f"Indexing Chat: {chat}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Cancel", callback_data=f"index_cancel#{chat}")]]
        ),
    )

    # Run indexing
    await index_files_to_db(int(lst_msg_id), chat, query.message, bot)


@Client.on_message(
    (filters.forwarded | filters.regex(r"(t\.me/(c/)?(?P<group>\d+|[a-zA-Z_0-9]+)/(?P<id>\d+))"))
    & filters.private
)
async def send_for_index(bot, message):
    chat_id = None
    last_msg_id = None

    if message.regex:
        chat_id = message.matches[0].group("group")
        last_msg_id = int(message.matches[0].group("id"))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        chat_id = message.forward_from_chat.id
        last_msg_id = message.forward_from_message_id
    else:
        return

    try:
        chat_info = await bot.get_chat(chat_id)
        chat_id = chat_info.id # Normalize to ID
    except Exception as e:
        return await message.reply(f"Error accessing chat: {e}")

    # Simplified button creation to save callback bytes
    btn = [[
        InlineKeyboardButton("Accept", callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}"),
        InlineKeyboardButton("Reject", callback_data=f"index#reject#{chat_id}#{last_msg_id}#{message.from_user.id}")
    ]]

    if message.from_user.id in ADMINS:
        await message.reply(f"Index this chat?\nID: `{chat_id}`", reply_markup=InlineKeyboardMarkup(btn))
    else:
        await bot.send_message(
            LOG_CHANNEL, 
            f"Request from {message.from_user.mention}\nChat: `{chat_id}`", 
            reply_markup=InlineKeyboardMarkup(btn)
        )
        await message.reply("Request sent to moderators.")


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    current_count = 0
    
    chat_str = str(chat)
    if chat_str in active_cancellations:
        active_cancellations.remove(chat_str)

    async with get_lock(chat):
        try:
            # We use a simple loop and pyrogram's iterator
            # Fetching messages from last_msg_id downwards (newest to oldest)
            async for message in bot.get_chat_history(chat, offset_id=lst_msg_id + 1):
                
                # Check for per-chat cancellation
                if chat_str in active_cancellations:
                    active_cancellations.remove(chat_str)
                    await msg.edit("Indexing cancelled by user.")
                    return

                current_count += 1
                
                # Update UI every 20 messages
                if current_count % 20 == 0:
                    try:
                        await msg.edit_text(
                            f"Progress: `{current_count}` messages scanned...\nSaved: `{total_files}`",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("Cancel", callback_data=f"index_cancel#{chat}")
                            ]])
                        )
                    except Exception: pass

                if message.empty:
                    deleted += 1
                    continue
                if not message.media:
                    no_media += 1
                    continue
                
                media_type = message.media
                if media_type not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    unsupported += 1
                    continue

                media = getattr(message, media_type.name.lower(), None)
                if not media:
                    continue

                media.file_type = media_type.name.lower()
                media.caption = message.caption or ""

                try:
                    success, result_code = await save_file(media)
                    if success: total_files += 1
                    elif result_code == 0: duplicate += 1
                    else: errors += 1
                except Exception as e:
                    errors += 1
                    logger.error(f"Save Error: {e}")

                # Small sleep to prevent instant flood
                await asyncio.sleep(0.05)

        except FloodWait as e:
            await asyncio.sleep(e.value)
            # After sleeping, you can resume logic or let the user restart
            await msg.edit(f"FloodWait hit. Paused for {e.value}s. Please restart from msg ID {message.id}")
            return
        except Exception as e:
            logger.exception(e)
            await msg.edit(f"Critical Error: {e}")
            return

        await msg.edit(
            f"**Indexing Complete**\n\n"
            f"Files Saved: `{total_files}`\n"
            f"Duplicates: `{duplicate}`\n"
            f"Non-Media: `{no_media}`"
        )
