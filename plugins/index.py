import logging
import re
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid, 
    ChatAdminRequired, 
    UsernameInvalid, 
    UsernameNotModified
)
from info import CHANNELS, LOG_CHANNEL, ADMINS
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp

# Setup Logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Global lock to prevent concurrent indexing processes
indexing_lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^index'))
async def handle_index_callbacks(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling indexing process...", show_alert=True)
        
    _, chat_id, last_msg_id = query.data.split("#")
    
    if indexing_lock.locked():
        return await query.answer('Another indexing process is already running.', show_alert=True)
    
    cancel_button = InlineKeyboardMarkup([[
        InlineKeyboardButton('🚫 CANCEL', "index_cancel")
    ]])
    
    await query.message.edit("✨ Indexing started...", reply_markup=cancel_button)
    
    # Ensure chat_id is handled as int if numeric string
    formatted_chat_id = int(chat_id) if chat_id.strip("-").isnumeric() else chat_id
    
    await start_indexing_logic(int(last_msg_id), formatted_chat_id, query.message, bot)


@Client.on_message(filters.private & filters.incoming & filters.user(ADMINS) & 
                  (filters.forwarded | filters.regex(r"(https://)?(t\.me/|telegram\.me/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")))
async def validate_index_request(bot, message):
    if message.text:
        regex = r"(https://)?(t\.me/|telegram\.me/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
        match = re.search(regex, message.text)
        if not match:
            return await message.reply('Invalid Telegram link.')
        
        raw_chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        
        # Convert private channel IDs to Telegram format
        chat_id = int(f"-100{raw_chat_id}") if raw_chat_id.isnumeric() else raw_chat_id
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return

    try:
        chat_info = await bot.get_chat(chat_id)
        # Verify access/permissions
        await bot.get_messages(chat_id, last_msg_id)
    except ChannelInvalid:
        return await message.reply('I cannot access this chat. Make sure I am an admin there.')
    except Exception as e:
        return await message.reply(f'Access Error: {e}')

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton('✨ START INDEX', callback_data=f'index#{chat_id}#{last_msg_id}')],
        [InlineKeyboardButton('🚫 CLOSE', callback_data='close_data')]
    ])
    
    await message.reply(
        f"**Index Request Received**\n\n"
        f"Target Chat: `{chat_id}`\n"
        f"Last Message: `{last_msg_id}`\n\n"
        "Do you want to proceed?",
        reply_markup=buttons
    )


async def start_indexing_logic(last_msg_id, chat_id, status_msg, bot):
    stats = {
        "total": 0,
        "duplicates": 0,
        "errors": 0,
        "deleted": 0,
        "no_media": 0,
        "unsupported": 0
    }
    
    async with indexing_lock:
        try:
            current_count = temp.CURRENT
            temp.CANCEL = False
            
            async for message in bot.iter_messages(chat_id, last_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    break
                
                current_count += 1
                
                # Update UI every 100 messages
                if current_count % 100 == 0:
                    await update_status(status_msg, current_count, stats, is_cancelled=False)

                if message.empty:
                    stats["deleted"] += 1
                    continue
                
                if not message.media or message.media not in [
                    enums.MessageMediaType.VIDEO, 
                    enums.MessageMediaType.AUDIO, 
                    enums.MessageMediaType.DOCUMENT
                ]:
                    stats["no_media"] += 1
                    continue

                # Extract media object safely
                media_obj = getattr(message, message.media.value, None)
                if not media_obj:
                    stats["unsupported"] += 1
                    continue

                media_obj.file_type = message.media.value
                media_obj.caption = message.caption
                
                # Logic: is_saved (bool), status_code (int)
                is_saved, status_code = await save_file(media_obj)
                
                if is_saved:
                    stats["total"] += 1
                elif status_code == 0:
                    stats["duplicates"] += 1
                elif status_code == 2:
                    stats["errors"] += 1

            # Final status update
            await update_status(status_msg, current_count, stats, is_cancelled=temp.CANCEL)

        except Exception as e:
            logger.exception("Indexing failed")
            await status_msg.edit(f"**Critical Error:** `{e}`")


async def update_status(msg, current, stats, is_cancelled):
    text = (
        f"{'❌ Indexing Cancelled' if is_cancelled else '🔄 Indexing in Progress...'}\n\n"
        f"Fetched: `{current}`\n"
        f"Saved: `{stats['total']}`\n"
        f"Duplicates: `{stats['duplicates']}`\n"
        f"Deleted: `{stats['deleted']}`\n"
        f"Skipped/Other: `{stats['no_media'] + stats['unsupported']}`\n"
        f"Errors: `{stats['errors']}`"
    )
    
    reply_markup = None if is_cancelled else InlineKeyboardMarkup([[
        InlineKeyboardButton('Cancel', callback_data='index_cancel')
    ]])

    try:
        await msg.edit_text(text, reply_markup=reply_markup)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await msg.edit_text(text, reply_markup=reply_markup)
    except Exception:
        pass
