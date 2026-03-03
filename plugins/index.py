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
import os
import time
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait

# Ensure these imports match your repository structure
from info import CHANNELS, ADMINS, LOG_CHANNEL 
from utils import temp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()

logger = logging.getLogger(__name__)

def format_time(seconds):
    return time.strftime("%H:%M:%S", time.gmtime(seconds))

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    data = query.data.split("#")
    source_chat = int(data[1]) if data[1].strip("-").isnumeric() else data[1]
    last_id = int(data[2])

    msg = query.message
    await msg.edit("🚀 **Starting Pure Media Transfer...**")
    
    start_time = time.time()
    total_found = 0
    processed = 0
    
    # We use a list to keep track of IDs for the final report
    media_ids = []

    try:
        # get_chat_history is more stable for this task
        async for message in bot.get_chat_history(source_chat, limit=last_id):
            processed += 1
            
            # 1. STRICT FILTER: Only Media (Video, Document, Audio)
            # This automatically skips deleted, empty, and text messages
            if message.media and message.media in [
                enums.MessageMediaType.VIDEO, 
                enums.MessageMediaType.DOCUMENT, 
                enums.MessageMediaType.AUDIO
            ]:
                try:
                    # 2. COPY TO LOG CHANNEL
                    await message.copy(LOG_CHANNEL)
                    total_found += 1
                    media_ids.append(message.id)
                    
                    # 3. ANTI-FLOOD: Small delay for stability
                    await asyncio.sleep(0.5) 
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await message.copy(LOG_CHANNEL)
                except Exception as e:
                    logger.error(f"Failed to copy {message.id}: {e}")

            # 4. LIVE STATUS UPDATE (Every 20 messages)
            if processed % 20 == 0:
                elapsed = format_time(time.time() - start_time)
                await msg.edit(
                    f"📂 **Transferring Media...**\n\n"
                    f"✅ Media Sent: `{total_found}`\n"
                    f"🔍 Checked: `{processed}`\n"
                    f"⏱️ Time Elapsed: `{elapsed}`"
                )

        # --- FINALIZATION ---
        end_time = format_time(time.time() - start_time)
        report_name = f"Report_{source_chat}.txt"
        
        with open(report_name, "w") as f:
            f.write(f"MEDIA TRANSFER REPORT\n"
                    f"Source: {source_chat}\n"
                    f"Total Media Found & Sent: {total_found}\n"
                    f"Total Messages Scanned: {processed}\n"
                    f"Time Taken: {end_time}\n\n"
                    f"Message IDs Sent:\n{media_ids}")

        final_text = (
            "✅ **Task Completed Successfully!**\n\n"
            f"📊 **Total Media:** `{total_found}`\n"
            f"⏱️ **Total Time:** `{end_time}`\n\n"
            "*No deleted or unsupported files were processed.*"
        )
        
        await msg.edit(final_text)
        await msg.reply_document(report_name, caption="📜 Detailed Media Log")
        os.remove(report_name)

    except Exception as e:
        await msg.edit(f"❌ **Fatal Error:** `{e}`")


