import logging
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, LOG_CHANNEL
from database.ia_filterdb import save_file

logger = logging.getLogger(__name__)

# Lock dictionary to prevent multiple indexing tasks on the same chat
indexing_locks = {}
active_cancellations = set()

def get_lock(chat_id):
    if chat_id not in indexing_locks:
        indexing_locks[chat_id] = asyncio.Lock()
    return indexing_locks[chat_id]

@Client.on_callback_query(filters.regex(r"^i"))
async def index_callback_handler(bot, query):
    data = query.data.split("#")
    action = data[1]

    # Handle Cancellation
    if action == "c":
        chat_to_cancel = data[2]
        active_cancellations.add(str(chat_to_cancel))
        return await query.answer("Stopping... 🛑", show_alert=True)

    # Validate data length for Accept/Reject
    if len(data) < 4:
        return await query.answer("Invalid request data.")

    chat_id = int(data[2])
    last_msg_id = int(data[3])

    if action == "r":
        await query.message.delete()
        return await query.answer("Request Rejected.")

    # Get lock and check if already running
    lock = get_lock(chat_id)
    if lock.locked():
        return await query.answer("This chat is already being indexed!", show_alert=True)

    await query.answer("Indexing Started...")
    
    await query.message.edit(
        f"**Indexing Chat:** `{chat_id}`\n**Status:** Running...",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Stop Indexing", callback_data=f"i#c#{chat_id}")
        ]])
    )

    # Launch actual indexing
    await index_files_to_db(last_msg_id, chat_id, query.message, bot)

@Client.on_message(filters.private & (filters.forwarded | filters.regex(r"t\.me/(c/)?(?P<g>\d+|[a-zA-Z_0-9]+)/(?P<id>\d+)")))
async def send_for_index(bot, message):
    if message.matches:
        match = message.matches[0]
        chat_id = match.group("g")
        last_msg_id = int(match.group("id"))
        if chat_id.isnumeric(): chat_id = int("-100" + chat_id)
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

    # Callback data kept short to avoid Pyrogram 64-byte limit
    btns = [[
        InlineKeyboardButton("✅ Accept", callback_data=f"i#a#{chat_id}#{last_msg_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"i#r#{chat_id}#{last_msg_id}")
    ]]

    if message.from_user.id in ADMINS:
        await message.reply(f"**Admin Tool**\nChat: `{chat_info.title}`\nID: `{chat_id}`", reply_markup=InlineKeyboardMarkup(btns))
    else:
        await bot.send_message(LOG_CHANNEL, f"**Request**\nFrom: {message.from_user.mention}\nChat: `{chat_info.title}`", reply_markup=InlineKeyboardMarkup(btns))
        await message.reply("✅ Request sent for approval.")

async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total = 0
    scanned = 0
    chat_str = str(chat)
    
    if chat_str in active_cancellations:
        active_cancellations.remove(chat_str)

    async with get_lock(chat):
        try:
            # Iterating through history from last_msg_id downwards
            async for message in bot.get_chat_history(chat, offset_id=lst_msg_id + 1):
                if chat_str in active_cancellations:
                    active_cancellations.remove(chat_str)
                    await msg.edit(f"🛑 **Cancelled!**\nSaved: `{total}`")
                    return

                scanned += 1
                if scanned % 20 == 0:
                    try:
                        await msg.edit_text(
                            f"**Indexing...**\n\nScanned: `{scanned}`\nSaved: `{total}`",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Stop", callback_data=f"i#c#{chat}") ]])
                        )
                    except: pass

                if message.media:
                    # Filter for specific media types
                    m_type = message.media.name.lower()
                    if m_type in ['video', 'document', 'audio']:
                        media = getattr(message, m_type, None)
                        if media:
                            media.file_type = m_type
                            media.caption = message.caption or ""
                            success, _ = await save_file(media)
                            if success: total += 1
                
                await asyncio.sleep(0.05) # Yield to event loop

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"Indexing Error: {e}")
            await msg.edit(f"❌ Error: {e}")
            return

        await msg.edit(f"✅ **Finished!**\n\nTotal Files: `{total}`\nTotal Scanned: `{scanned}`")
