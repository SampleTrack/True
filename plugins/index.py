import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database.ia_filterdb import Media, save_file
from info import ADMINS, LOG_CHANNEL
from utils import temp, get_size

# Temporary cache to store indexing details for confirmation
INDEX_DATA = {}

@Client.on_message(filters.group & filters.forwarded & filters.user(ADMINS))
async def forwarded_index_trigger(client, message):
    # Ensure the forward is from a channel
    if not message.forward_from_chat or message.forward_from_chat.type != enums.ChatType.CHANNEL:
        return

    chat_id = message.forward_from_chat.id
    chat_title = message.forward_from_chat.title
    
    # Estimate the total messages (from msg 1 to the forwarded message ID)
    last_msg_id = message.forward_from_message_id
    total_messages = last_msg_id

    # Store data for the callback session
    INDEX_DATA[message.from_user.id] = {
        "chat_id": chat_id,
        "last_id": last_msg_id
    }

    buttons = [
        [
            InlineKeyboardButton("✅ Start Adding", callback_data="confirm_bulk_index"),
            InlineKeyboardButton("❌ Cancel", callback_data="close_data")
        ]
    ]

    await message.reply_text(
        text=f"📑 **Bulk Indexing Detected**\n\n"
             f"📣 **Channel:** `{chat_title}`\n"
             f"🆔 **Channel ID:** `{chat_id}`\n"
             f"🔢 **Messages to Scan:** `1` to `{last_msg_id}`\n"
             f"📊 **Total Estimated:** `{total_messages}`\n\n"
             f"Do you want to index all media from this channel?",
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )

@Client.on_callback_query(filters.regex(r"^confirm_bulk_index") & filters.user(ADMINS))
async def start_indexing_callback(client, query: CallbackQuery):
    user_id = query.from_user.id
    data = INDEX_DATA.get(user_id)
    
    if not data:
        return await query.answer("Session Expired! Forward the message again.", show_alert=True)

    await query.message.edit_text("🚀 **Indexing Started...**\nProcessing messages from ID 1.")
    
    chat_id = data['chat_id']
    last_id = data['last_id']
    
    success = 0
    duplicates = 0
    errors = 0
    total_scanned = 0

    # Using the iter_messages method defined in bot.py
    async for message in client.iter_messages(chat_id, limit=last_id, offset=1):
        total_scanned += 1
        
        # Only process media types supported by your database
        if message.media in [enums.MessageMediaType.DOCUMENT, enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO]:
            media_type = message.media.value
            media = getattr(message, media_type)
            media.file_type = media_type
            media.caption = message.caption
            
            # Use the existing save_file function which handles duplicates
            status, code = await save_file(media)
            
            if status:
                success += 1
            elif code == 0: # 0 indicates DuplicateKeyError in your ia_filterdb.py
                duplicates += 1
            else:
                errors += 1
        else:
            errors += 1

        # Periodic status updates to avoid spamming the Telegram API
        if total_scanned % 50 == 0:
            try:
                await query.message.edit_text(
                    f"🔄 **Indexing Progress...**\n\n"
                    f"✅ Added: `{success}`\n"
                    f"⏩ Skipped (Duplicate): `{duplicates}`\n"
                    f"❌ Non-Media/Errors: `{errors}`\n"
                    f"📊 Scanned: `{total_scanned}` / `{last_id}`"
                )
            except:
                pass

    # Final Summary
    await query.message.reply_text(
        text=f"🏁 **Indexing Completed!**\n\n"
             f"✅ **Total Added:** `{success}`\n"
             f"⏩ **Duplicates Found:** `{duplicates}`\n"
             f"❌ **Invalid/Deleted:** `{errors}`\n"
             f"📦 **Final Count:** `{success + duplicates}`",
        quote=True
    )
    
    # Cleanup session
    INDEX_DATA.pop(user_id, None)
    await query.answer("Bulk indexing finished successfully!")
    
