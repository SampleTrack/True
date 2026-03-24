import asyncio
import re
import time
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database.ia_filterdb import Media, save_file
from info import ADMINS, LOG_CHANNEL
from utils import temp, get_size

# Temporary storage for index data to handle callbacks
INDEX_CONFIRM = {}

@Client.on_message(filters.command("index") & filters.user(ADMINS))
async def index_start(client, message):
    if len(message.command) < 3:
        return await message.reply("<b>Format:</b> `/index [Channel ID/Username] [Start ID]`\nExample: `/index -1001234567 1`")

    chat_id = message.command[1]
    try:
        chat_id = int(chat_id)
    except:
        pass
    
    start_id = int(message.command[2])
    
    try:
        chat = await client.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"Error accessing chat: {e}")

    # Estimate logic: Get the last message ID
    last_msg_id = message.id if chat_id == message.chat.id else (await client.get_messages(chat_id, 1)).id
    total_files = last_msg_id - start_id
    
    # Store data for callback
    INDEX_CONFIRM[message.from_user.id] = {
        "chat_id": chat_id,
        "start": start_id,
        "last": last_msg_id
    }

    buttons = [
        [InlineKeyboardButton("✅ START INDEXING", callback_data="start_bulk_index")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="close_data")]
    ]

    await message.reply_text(
        f"📑 **Bulk Indexing Request**\n\n"
        f"📍 **Source:** `{chat.title}`\n"
        f"🔢 **Start ID:** `{start_id}`\n"
        f"🏁 **End ID:** `{last_msg_id}`\n"
        f"📦 **Estimated Messages:** `{total_files}`\n\n"
        f"Estimated time: ~{total_files // 10} seconds (excluding FloodWaits).",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex("start_bulk_index") & filters.user(ADMINS))
async def run_bulk_index(client, query: CallbackQuery):
    data = INDEX_CONFIRM.get(query.from_user.id)
    if not data:
        return await query.answer("Session expired, try command again.", show_alert=True)

    await query.message.edit_text("🚀 **Indexing Started...** Check progress below.")
    
    chat_id = data['chat_id']
    start = data['start']
    last = data['last']
    
    success = 0
    duplicates = 0
    errors = 0
    deleted = 0
    total_processed = 0
    
    progress_msg = await client.send_message(query.message.chat.id, "Starting processing...")

    # Iterate through message range using your bot's iter_messages (from bot.py)
    async for message in client.iter_messages(chat_id, last, start):
        total_processed += 1
        
        if message.empty:
            deleted += 1
        elif not message.media or message.media not in [enums.MessageMediaType.DOCUMENT, enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO]:
            errors += 1
        else:
            # Extract media object
            media_type = message.media.value
            media = getattr(message, media_type, None)
            
            if media:
                media.file_type = media_type
                media.caption = message.caption
                # Using save_file from database/ia_filterdb.py
                # It returns (Status, Code). 1=Success, 0=Duplicate
                sts, code = await save_file(media)
                if sts:
                    success += 1
                elif code == 0:
                    duplicates += 1
                else:
                    errors += 1
        
        # Update status every 20 messages to avoid spamming API
        if total_processed % 20 == 0:
            try:
                await progress_msg.edit(
                    f"🔄 **Indexing in Progress...**\n\n"
                    f"✅ Saved: `{success}`\n"
                    f"⏩ Duplicates: `{duplicates}`\n"
                    f"🗑 Deleted/Empty: `{deleted}`\n"
                    f"❌ Non-Media: `{errors}`\n"
                    f"📊 Total Processed: `{total_processed}`"
                )
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception:
                pass

    await progress_msg.edit(
        f"🏁 **Indexing Completed!**\n\n"
        f"✅ Total Saved: `{success}`\n"
        f"⏩ Duplicates Skipped: `{duplicates}`\n"
        f"🗑 Deleted Messages: `{deleted}`\n"
        f"❌ Non-Media Skipped: `{errors}`\n"
        f"📦 Total Scanned: `{total_processed}`"
    )
    
    # Cleanup session
    INDEX_CONFIRM.pop(query.from_user.id, None)
    await query.answer("Bulk Indexing Finished!", show_alert=True)
