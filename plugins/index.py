import logging
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS
from info import INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file

logger = logging.getLogger(__name__)

# Track active tasks
indexing_locks = {}
active_cancellations = set()

def get_lock(chat_id):
    if chat_id not in indexing_locks:
        indexing_locks[chat_id] = asyncio.Lock()
    return indexing_locks[chat_id]

@Client.on_callback_query(filters.regex(r"^i"))
async def index_files(bot, query):
    # Data Formats:
    # Accept/Reject: i#action#chat_id#msg_id#user_id (5 parts)
    # Cancel: i#c#chat_id (3 parts)
    data = query.data.split("#")
    action = data[1]

    # 1. Handle Cancel (requires only 3 data points)
    if action == "c":
        chat_to_cancel = data[2]
        active_cancellations.add(str(chat_to_cancel))
        return await query.answer("Cancelling... 🛑", show_alert=True)

    # 2. Validation: Ensure we have enough data for Accept/Reject
    if len(data) < 5:
        return await query.answer("❌ Error: Invalid button data.", show_alert=True)

    _, _, chat_id, last_msg_id, user_id = data

    # 3. Handle Reject
    if action == "r":
        await query.message.delete()
        return await query.answer("Request Rejected.")

    # 4. Handle Accept
    if action == "a":
        # Convert chat_id to int for Pyrogram compatibility
        try:
            target_chat = int(chat_id)
        except ValueError:
            target_chat = chat_id

        lock = get_lock(target_chat)
        if lock.locked():
            return await query.answer("⚠️ This chat is already being indexed!", show_alert=True)

        await query.answer("Starting Indexing... ⏳")
        
        await query.message.edit(
            f"**Indexing Chat:** `{target_chat}`\n**Status:** Processing...",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Stop Indexing", callback_data=f"i#c#{target_chat}")
            ]])
        )

        try:
            await index_files_to_db(int(last_msg_id), target_chat, query.message, bot)
        except Exception as e:
            logger.error(f"Index Error: {e}")
            await query.message.edit(f"❌ Critical Error: {e}")

@Client.on_message(filters.private & (filters.forwarded | filters.regex(r"t\.me/(c/)?(?P<g>\d+|[a-zA-Z_0-9]+)/(?P<id>\d+)")))
async def send_for_index(bot, message):
    if message.matches:
        match = message.matches[0]
        chat_id = match.group("g")
        last_msg_id = int(match.group("id"))
        if chat_id.isnumeric(): 
            chat_id = int("-100" + chat_id)
    elif message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        last_msg_id = message.forward_from_message_id
    else:
        return

    try:
        chat_info = await bot.get_chat(chat_id)
        chat_id = chat_info.id
    except Exception as e:
        return await message.reply(f"❌ Error: {e}")

    # Keep callback data short to stay under 64-byte Telegram limit
    btns = [[
        InlineKeyboardButton("✅ Accept", callback_data=f"i#a#{chat_id}#{last_msg_id}#{message.from_user.id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"i#r#{chat_id}#{last_msg_id}#{message.from_user.id}")
    ]]

    if message.from_user.id in ADMINS:
        await message.reply(f"**Admin Tool**\nIndex: `{chat_info.title}`\nID: `{chat_id}`", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await bot.send_message(LOG_CHANNEL, f"**New Request**\nFrom: {message.from_user.mention}\nChat: `{chat_info.title}`\nID: `{chat_id}`", reply_markup=InlineKeyboardMarkup(btns))
        await message.reply("✅ Your request has been sent for approval.")

async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total = 0
    scanned = 0
    chat_str = str(chat)
    
    if chat_str in active_cancellations:
        active_cancellations.remove(chat_str)

    async with get_lock(chat):
        try:
            async for message in bot.get_chat_history(chat, offset_id=lst_msg_id + 1):
                # Check for cancellation signal
                if chat_str in active_cancellations:
                    active_cancellations.remove(chat_str)
                    await msg.edit(f"🛑 **Cancelled!**\nFiles Saved: `{total}`")
                    return

                scanned += 1
                
                # Update UI every 20 messages
                if scanned % 20 == 0:
                    try:
                        await msg.edit_text(
                            f"**Indexing...**\n\nScanned: `{scanned}`\nSaved: `{total}`",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Stop", callback_data=f"i#c#{chat}") ]])
                        )
                    except: 
                        pass

                # Filter media types
                if message.media and message.media in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.DOCUMENT, enums.MessageMediaType.AUDIO]:
                    media = getattr(message, message.media.name.lower(), None)
                    if media:
                        # Required metadata for database
                        media.file_type = message.media.name.lower()
                        media.caption = message.caption or ""
                        success, status = await save_file(media)
                        if success: 
                            total += 1
                
                # Small sleep to prevent FloodWait
                await asyncio.sleep(0.05) 

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"Indexing Error: {e}")
            await msg.edit(f"❌ Error occurred: {e}")
            return

        await msg.edit(f"✅ **Indexing Finished!**\n\nTotal Files: `{total}`\nTotal Scanned: `{scanned}`")

