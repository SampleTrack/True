import logging
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from info import ADMINS
from info import INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()

def get_status_text():
    """Returns a status string based on whether the lock is active."""
    return "⚠️ System Busy (Index Active)" if lock.locked() else "✅ System Ready"

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing... please wait.", show_alert=True)
    
    _, raju, chat, lst_msg_id, from_user = query.data.split("#")
    
    if raju == 'reject':
        await query.message.delete()
        await bot.send_message(int(from_user),
                               f'Your Submission for indexing {chat} has been declined by our moderators.',
                               reply_to_message_id=int(lst_msg_id))
        return

    if lock.locked():
        return await query.answer(f"Status: BUSY\nAnother indexing process is currently running. Please wait.", show_alert=True)

    await query.answer('Processing...⏳', show_alert=True)
    msg = query.message

    if int(from_user) not in ADMINS:
        await bot.send_message(int(from_user),
                               f'Your Submission for indexing {chat} has been accepted and added to the queue.',
                               reply_to_message_id=int(lst_msg_id))

    await msg.edit(
        f"**Indexing Started**\nStatus: 🟢 Active",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton('🛑 Stop Indexing', callback_data='index_cancel')]]
        )
    )
    
    try:
        chat_id = int(chat) if chat.strip("-").isdigit() else chat
        await index_files_to_db(int(lst_msg_id), chat_id, msg, bot)
    except Exception as e:
        logger.exception(e)
        await msg.edit(f"Critical Error: {e}")

@Client.on_message((filters.forwarded | (filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$") & filters.text)) & filters.private & filters.incoming)
async def send_for_index(bot, message):
    # Logic for extracting chat_id and last_msg_id
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match:
            return await message.reply('Invalid link')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int(("-100" + chat_id))
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return

    # Check bot permissions
    try:
        await bot.get_chat(chat_id)
        k = await bot.get_messages(chat_id, last_msg_id)
        if k.empty:
            return await message.reply('Cannot access messages. Make sure I am an admin.')
    except Exception as e:
        return await message.reply(f"Permission Error: {e}")

    # Dynamic UI status
    is_busy = lock.locked()
    status_emoji = "🔴" if is_busy else "🟢"
    status_label = "System Busy" if is_busy else "Start Index"

    buttons = [
        [InlineKeyboardButton(f"{status_emoji} {status_label}", callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
        [InlineKeyboardButton('🗑️ Close', callback_data='close_data')]
    ]

    if message.from_user.id in ADMINS:
        return await message.reply(
            f"**Index Request**\n\nTarget: ` {chat_id} `\nStatus: {get_status_text()}",
            reply_markup=InlineKeyboardMarkup(buttons))

    # Log for non-admins
    log_buttons = [
        [InlineKeyboardButton(f"{status_emoji} Accept Request", callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
        [InlineKeyboardButton("❌ Reject", callback_data=f'index#reject#{chat_id}#{message.id}#{message.from_user.id}')]
    ]
    
    await bot.send_message(LOG_CHANNEL, 
                           f"#IndexRequest\nFrom: {message.from_user.mention}\nChat: `{chat_id}`\n{get_status_text()}",
                           reply_markup=InlineKeyboardMarkup(log_buttons))
    await message.reply('Request sent to moderators.')

async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files, duplicate, errors, deleted, no_media, unsupported = 0, 0, 0, 0, 0, 0
    
    async with lock:
        try:
            current = temp.CURRENT
            temp.CANCEL = False
            async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    break
                
                current += 1
                if current % 20 == 0:
                    await msg.edit_text(
                        text=f"**Indexing In Progress...**\n\nFetched: `{current}`\nSaved: `{total_files}`\nDuplicates: `{duplicate}`\nErrors: `{errors}`",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🛑 Stop Indexing', callback_data='index_cancel')]]))

                if message.empty:
                    deleted += 1
                elif not message.media or message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    no_media += 1
                else:
                    media = getattr(message, message.media.value, None)
                    if media:
                        media.file_type = message.media.value
                        media.caption = message.caption
                        aynav, vnay = await save_file(media)
                        if aynav: total_files += 1
                        elif vnay == 0: duplicate += 1
                        elif vnay == 2: errors += 1

            status_msg = "✅ Completed" if not temp.CANCEL else "🛑 Cancelled"
            await msg.edit(f"**Indexing {status_msg}**\n\nTotal Saved: `{total_files}`\nDuplicates: `{duplicate}`\nErrors: `{errors}`")
            
        except Exception as e:
            logger.exception(e)
            await msg.edit(f'Error occurred: {e}')

