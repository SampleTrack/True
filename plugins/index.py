import os
import re
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid, 
    UsernameInvalid, 
    UsernameNotModified
)
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIGURATION ---
from info import CHANNELS, ADMINS
from utils import temp

# TARGET CHANNEL FOR COPIED MEDIA
# Make sure the bot is an ADMIN in this channel
LOG_CHANNEL = -1001234567890 

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()

def get_ranges(id_list):
    if not id_list:
        return "None Found"
    id_list.sort()
    ranges = []
    start = id_list[0]
    for i in range(1, len(id_list)):
        if id_list[i] != id_list[i-1] + 1:
            ranges.append(f"{start} to {id_list[i-1]}" if start != id_list[i-1] else f"{start}")
            start = id_list[i]
    ranges.append(f"{start} to {id_list[-1]}" if start != id_list[-1] else f"{start}")
    return "\n".join(ranges)

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cᴀɴᴄᴇʟʟɪɴɢ Sᴄᴀɴ...", show_alert=True)
        
    data = query.data.split("#")
    chat = data[1]
    lst_msg_id = data[2]

    if lock.locked():
        return await query.answer('Wᴀɪᴛ Uɴᴛɪʟ Pʀᴇᴠɪᴏᴜs Pʀᴏᴄᴇss Cᴏᴍᴘʟᴇᴛᴇ', show_alert=True)
    
    msg = query.message
    button = InlineKeyboardMarkup([[InlineKeyboardButton('🚫 ᴄᴀɴᴄᴇʟ sᴄᴀɴ', "index_cancel")]])
    await msg.edit("sᴄᴀɴɴɪɴɢ ᴀɴᴅ ғᴏʀᴡᴀʀᴅɪɴɢ sᴛᴀʀᴛᴇᴅ ✨", reply_markup=button)                        
    
    try:
        chat_id = int(chat) if chat.strip("-").isnumeric() else chat
        await index_files_to_db(int(lst_msg_id), chat_id, msg, bot)
    except Exception as e:
        logger.exception(e)
        await msg.edit(f"Error: {e}")

@Client.on_message((filters.forwarded | (filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.text ) & filters.private & filters.incoming & filters.user(ADMINS))
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match: return
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric(): chat_id = int(("-100" + chat_id))
    elif message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.id
    else: return

    try: 
        await bot.get_chat(chat_id)
    except Exception as e: 
        return await message.reply(f'Errors - {e}')

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton('🚀 sᴛᴀʀᴛ ғᴏʀᴡᴀʀᴅɪɴɢ', callback_data=f'index#{chat_id}#{last_msg_id}'),
        InlineKeyboardButton('🚫 ᴄʟᴏsᴇ', callback_data='close_data')
    ]])               
    await message.reply(f'Index & Forward to Log Channel?\n\nSource: <code>{chat_id}</code>\nTarget: <code>{LOG_CHANNEL}</code>', reply_markup=buttons)

async def index_files_to_db(lst_msg_id, chat, msg, bot):
    logs = {"deleted": [], "unsupported": [], "media_found": []}
    total_found, deleted, no_media, unsupported = 0, 0, 0, 0
    current = 0
    batch_ids = [] # To store IDs for batch forwarding
    
    async with lock:
        try:
            temp.CANCEL = False
            async for message in bot.iter_messages(chat, lst_msg_id):
                if temp.CANCEL: break
                
                current += 1
                # Progress Update
                if current % 50 == 0:
                    try:
                        await msg.edit_text(
                            text=f"🔍 <b>Indexing...</b>\n\nProcessed: <code>{current}</code>\nFound & Sent: <code>{total_found}</code>",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🚫 ᴄᴀɴᴄᴇʟ', "index_cancel")]])
                        )       
                    except FloodWait as t:
                        await asyncio.sleep(t.value)
                    except: pass

                if message.empty:
                    logs["deleted"].append(message.id)
                    deleted += 1
                    continue
                
                if not message.media or message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    no_media += 1 if not message.media else 0
                    if message.media: 
                        unsupported += 1
                        logs["unsupported"].append(message.id)
                    continue

                # Valid Media Found - Add to batch
                total_found += 1
                logs["media_found"].append(message.id)
                batch_ids.append(message.id)

                # Forward in batches of 100 (Most efficient way)
                if len(batch_ids) >= 100:
                    try:
                        await bot.forward_messages(chat_id=LOG_CHANNEL, from_chat_id=chat, message_ids=batch_ids)
                        batch_ids = [] # Reset batch
                        await asyncio.sleep(1) # Cooldown to avoid flood
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                        await bot.forward_messages(LOG_CHANNEL, chat, batch_ids)
                        batch_ids = []
                    except Exception as e:
                        logger.error(f"Batch Forward Error: {e}")

            # Send remaining messages in the final batch
            if batch_ids:
                try:
                    await bot.forward_messages(LOG_CHANNEL, chat, batch_ids)
                except Exception as e:
                    logger.error(f"Final Batch Error: {e}")

            status_text = "CANCELLED" if temp.CANCEL else "COMPLETED"
            file_name = f"Report_{chat}.txt"
            
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(f"--- SCAN & FORWARD REPORT ---\nStatus: {status_text}\nSource: {chat}\nTarget: {LOG_CHANNEL}\n\n"
                        f"Media IDs:\n{get_ranges(logs['media_found'])}\n\n"
                        f"Deleted IDs:\n{get_ranges(logs['deleted'])}\n")

            await msg.edit(f"📊 <b>Scan {status_text}</b>\n\n📁 <b>Sent to Log:</b> <code>{total_found}</code>\n🗑️ <b>Deleted:</b> <code>{deleted}</code>")
            await msg.reply_document(file_name, caption=f"Detailed Report for {chat}")
            if os.path.exists(file_name): os.remove(file_name)

        except Exception as e:
            logger.exception(e)
            await msg.edit(f'❌ <b>Scan Error:</b>\n<code>{e}</code>')
