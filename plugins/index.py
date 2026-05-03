import logging
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from utils import temp

logger = logging.getLogger(__name__)
lock = asyncio.Lock()

# --- CALLBACK HANDLERS ---

@Client.on_callback_query(filters.regex(r'^idx_cancel'))
async def cancel_indexing(bot, query):
    temp.CANCEL = True
    await query.answer("Stop signal sent. Finishing current batch...", show_alert=True)

@Client.on_callback_query(filters.regex(r'^idx'))
async def handle_index_request(bot, query):
    # Format: idx:action:chat_id:last_msg_id:user_id
    data = query.data.split(":")
    action = data[1]
    chat_id = data[2]
    last_msg_id = int(data[3])
    from_user_id = int(data[4])

    if action == "reject":
        await query.message.delete()
        await bot.send_message(
            from_user_id,
            "Your indexing request has been declined by moderators.",
            reply_to_message_id=last_msg_id
        )
        return

    if lock.locked():
        return await query.answer("An indexing process is already running. Wait!", show_alert=True)

    if from_user_id not in ADMINS:
        await bot.send_message(
            from_user_id,
            "Your request was accepted. Indexing starting now...",
            reply_to_message_id=last_msg_id
        )

    await query.message.edit(
        "**Indexing Started...**",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🛑 Stop Indexing", callback_data="idx_cancel")
        ]])
    )
    
    # Run indexing
    await index_files_to_db(last_msg_id, chat_id, query.message, bot)

# --- MESSAGE HANDLERS ---

@Client.on_message(filters.private & filters.incoming & (filters.forwarded | filters.text))
async def process_index_link(bot, message):
    chat_id, last_msg_id = None, None

    if message.text:
        regex = r"(https://)?(t\.me/|telegram\.me/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
        match = re.search(regex, message.text)
        if not match:
            return 
        
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int(f"-100{chat_id}")
    
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        chat_id = message.forward_from_chat.id
        last_msg_id = message.forward_from_message_id

    if not chat_id:
        return

    try:
        chat = await bot.get_chat(chat_id)
        # Check if bot can access messages
        await bot.get_messages(chat_id, last_msg_id)
    except Exception as e:
        return await message.reply(f"**Error:** Ensure I am an admin in {chat_id}.\n`{e}`")

    # Generate Buttons (idx:action:chat_id:last_msg_id:user_id)
    keyboard = [
        [InlineKeyboardButton("✅ Accept", callback_data=f"idx:accept:{chat_id}:{last_msg_id}:{message.from_user.id}")],
        [InlineKeyboardButton("❌ Reject", callback_data=f"idx:reject:{chat_id}:{message.id}:{message.from_user.id}")]
    ]

    if message.from_user.id in ADMINS:
        await message.reply(f"Index this chat?\n`{chat_id}`", reply_markup=InlineKeyboardMarkup(keyboard[:1]))
    else:
        await bot.send_message(
            LOG_CHANNEL,
            f"#IndexRequest from {message.from_user.mention}\nChat: `{chat_id}`",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await message.reply("Request sent to moderators.")

# --- CORE LOGIC ---

async def index_files_to_db(lst_msg_id, chat, msg, bot):
    stats = {"total": 0, "dup": 0, "err": 0, "skip": 0}
    temp.CANCEL = False
    
    async with lock:
        try:
            current_count = 0
            # Use try-except chat conversion
            chat_target = int(chat) if str(chat).replace("-", "").isnumeric() else chat

            async for message in bot.iter_messages(chat_target, lst_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    break
                
                current_count += 1
                if current_count % 20 == 0:
                    await msg.edit_text(
                        f"**Indexing...**\nProcessed: `{current_count}`\nSaved: `{stats['total']}`",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Stop", callback_data="idx_cancel")]])
                    )

                if not message or message.empty or not message.media:
                    stats["skip"] += 1
                    continue

                media_type = message.media.value
                if media_type not in ["video", "audio", "document"]:
                    stats["skip"] += 1
                    continue

                media = getattr(message, media_type, None)
                if media:
                    media.file_type = media_type
                    media.caption = message.caption
                    
                    success, res_code = await save_file(media)
                    if success:
                        stats["total"] += 1
                    elif res_code == 0:
                        stats["dup"] += 1
                    else:
                        stats["err"] += 1

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.exception(e)
            return await msg.edit(f"Critical Error: `{e}`")

        final_text = (
            f"✅ **Indexing {'Cancelled' if temp.CANCEL else 'Completed'}**\n\n"
            f"📂 Saved: `{stats['total']}`\n"
            f"👯 Duplicates: `{stats['dup']}`\n"
            f"🚫 Skipped/Non-Media: `{stats['skip']}`\n"
            f"⚠️ Errors: `{stats['err']}`"
        )
        await msg.edit(final_text)
