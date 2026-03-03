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

# Ensure these imports match your repository structure
from info import CHANNELS, ADMINS
from utils import temp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()

# --- HELPER FUNCTION: Groups individual IDs into readable ranges (e.g., 100 to 280) ---
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

# --- CALLBACK: Triggers the Indexing Process ---
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
    button = InlineKeyboardMarkup([[
        InlineKeyboardButton('🚫 ᴄᴀɴᴄᴇʟ sᴄᴀɴ', "index_cancel")
    ]])
    await msg.edit("sᴄᴀɴɴɪɴɢ ɪs sᴛᴀʀᴛᴇᴅ ✨", reply_markup=button)                        
    
    try:
        chat_id = int(chat) if chat.strip("-").isnumeric() else chat
        await index_files_to_db(int(lst_msg_id), chat_id, msg, bot)
    except Exception as e:
        await msg.edit(f"Error: {e}")

# --- HANDLER: Link Parser for ADMINS ---
@Client.on_message((filters.forwarded | (filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.text ) & filters.private & filters.incoming & filters.user(ADMINS))
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match: 
            return await message.reply('Invalid link')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric(): 
            chat_id = int(("-100" + chat_id))
    elif message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else: 
        return

    try: 
        await bot.get_chat(chat_id)
    except (ChannelInvalid, UsernameInvalid, UsernameNotModified): 
        return await message.reply('Invalid Channel or Bot is not Admin.')
    except Exception as e: 
        return await message.reply(f'Errors - {e}')

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton('✨ sᴛᴀʀᴛ sᴄᴀɴ', callback_data=f'index#{chat_id}#{last_msg_id}'),
        InlineKeyboardButton('🚫 ᴄʟᴏsᴇ', callback_data='close_data')
    ]])               
    await message.reply(f'Do you want to scan this channel?\n\nChat: <code>{chat_id}</code>\nLast ID: <code>{last_msg_id}</code>', reply_markup=buttons)

# --- MAIN SCANNING LOGIC ---
async def index_files_to_db(lst_msg_id, chat, msg, bot):
    logs = {
        "deleted": [],
        "unsupported": [],
        "media_found": []
    }
    
    total_found = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    
    async with lock:
        try:
            current = temp.CURRENT
            temp.CANCEL = False
            
            async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    break
                
                current += 1
                if current % 100 == 0:
                    try:
                        await msg.edit_text(
                            text=f"🔍 <b>Scanning...</b>\n\n"
                                 f"Processed: <code>{current}</code>\n"
                                 f"Media Found: <code>{total_found}</code>",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🚫 ᴄᴀɴᴄᴇʟ', "index_cancel")]])
                        )       
                    except FloodWait as t:
                        await asyncio.sleep(t.value)

                if message.empty:
                    logs["deleted"].append(message.id)
                    deleted += 1
                    continue
                
                elif not message.media:
                    no_media += 1
                    continue
                
                elif message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    logs["unsupported"].append(message.id)
                    unsupported += 1
                    continue

                # Valid Media Found
                total_found += 1
                logs["media_found"].append(message.id)

            # --- REPORT GENERATION ---
            status_text = "CANCELLED" if temp.CANCEL else "COMPLETED"
            file_name = f"Scan_{chat}.txt"
            
            report_content = (
                f"--- CHANNEL SCAN REPORT ({status_text}) ---\n"
                f"Target Chat: {chat}\n"
                f"Total Messages Checked: {current}\n"
                f"Valid Media Found: {total_found}\n\n"
                f"MEDIA MESSAGE IDS:\n{get_ranges(logs['media_found'])}\n\n"
                f"DELETED/EMPTY MESSAGE IDS:\n{get_ranges(logs['deleted'])}\n\n"
                f"UNSUPPORTED MEDIA IDS:\n{get_ranges(logs['unsupported'])}\n"
            )

            with open(file_name, "w", encoding="utf-8") as f:
                f.write(report_content)

            final_summary = (
                f"📊 <b>Scan {status_text}</b>\n\n"
                f"📁 <b>Media Found:</b> <code>{total_found}</code>\n"
                f"🗑️ <b>Deleted:</b> <code>{deleted}</code>\n"
                f"🚫 <b>Non-Media:</b> <code>{no_media}</code>\n\n"
                f"<i>Note: No data was saved to database.</i>"
            )

            await msg.edit(final_summary)
            await msg.reply_document(file_name, caption=f"Scan Report: {chat}")
            
            if os.path.exists(file_name):
                os.remove(file_name)

        except Exception as e:
            logger.exception(e)
            await msg.edit(f'❌ <b>Scan Error:</b>\n<code>{e}</code>')
