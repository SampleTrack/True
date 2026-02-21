import logging
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
)
from info import ADMINS, INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Global Lock to prevent database corruption during heavy writes
lock = asyncio.Lock()

# Simple state management to avoid global 'temp' conflicts
class IndexStatus:
    def __init__(self):
        self.CANCEL = False
        self.CURRENT = 0

index_status = IndexStatus()

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        index_status.CANCEL = True
        return await query.answer("Cancelling Indexing...", show_alert=True)
    
    # Data format: index#accept#chat_id#last_msg_id#user_id
    params = query.data.split("#")
    if len(params) < 5:
        return await query.answer("Invalid Callback Data", show_alert=True)
        
    _, action, chat, lst_msg_id, from_user = params

    if action == 'reject':
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f'Your submission for indexing {chat} was declined.',
            reply_to_message_id=int(lst_msg_id)
        )
        return

    if lock.locked():
        return await query.answer('Another indexing process is running. Wait.', show_alert=True)

    await query.answer('Starting Indexing...', show_alert=True)
    
    if int(from_user) not in ADMINS:
        await bot.send_message(int(from_user), "Your request was accepted and indexing has started.")

    await query.message.edit(
        "**Indexing Started...**",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton('Cancel', callback_data='index_cancel')]]
        )
    )
    
    # Ensure chat is handled as int or str (username)
    target_chat = int(chat) if chat.strip('-').isnumeric() else chat
    await index_files_to_db(int(lst_msg_id), target_chat, query.message, bot)


@Client.on_message((filters.forwarded | filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.private)
async def send_for_index(bot, message):
    if message.text:
        regex = r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
        match = re.search(regex, message.text)
        if not match:
            return
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.id
    else:
        return

    # Verify Bot Permissions
    try:
        await bot.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"Error: {e}. Make sure I am an admin in that chat.")

    buttons = [
        [InlineKeyboardButton('Accept Index', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
        [InlineKeyboardButton('Reject Index', callback_data=f'index#reject#{chat_id}#{message.id}#{message.from_user.id}')]
    ]
    
    if message.from_user.id in ADMINS:
        await message.reply(f"Index this chat?\nID: `{chat_id}`", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await bot.send_message(LOG_CHANNEL, f"New Index Request from {message.from_user.mention}", reply_markup=InlineKeyboardMarkup(buttons))
        await message.reply("Request sent to moderators.")


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    
    async with lock:
        try:
            index_status.CANCEL = False
            # Pyrogram uses get_chat_history, NOT iter_messages
            # We fetch 'lst_msg_id' number of messages starting from the most recent
            async for message in bot.get_chat_history(chat, limit=lst_msg_id):
                if index_status.CANCEL:
                    break

                if not message.media or message.media not in [
                    enums.MessageMediaType.VIDEO, 
                    enums.MessageMediaType.DOCUMENT, 
                    enums.MessageMediaType.AUDIO
                ]:
                    continue

                media = getattr(message, message.media.value, None)
                if not media:
                    continue
                
                # Metadata injection for your DB save_file function
                media.file_type = message.media.value
                media.caption = message.caption
                
                # CRITICAL: Ensure save_file is an ASYNC function in your DB file
                success, status = await save_file(media)
                
                if success:
                    total_files += 1
                elif status == 0:
                    duplicate += 1
                elif status == 2:
                    errors += 1

                # Update UI every 50 files to avoid FloodWait
                if total_files % 50 == 0:
                    try:
                        await msg.edit_text(f"Indexing... \nSaved: `{total_files}`\nDuplicates: `{duplicate}`")
                        await asyncio.sleep(1) 
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                    except:
                        pass

        except Exception as e:
            logger.exception(e)
            await msg.edit(f"Fatal Error: {e}")
        finally:
            final_text = "Indexing Complete!" if not index_status.CANCEL else "Indexing Cancelled!"
            await msg.edit(f"{final_text}\n\nTotal Saved: `{total_files}`\nDuplicates: `{duplicate}`\nErrors: `{errors}`")

@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    try:
        _, skip = message.text.split(" ")
        index_status.CURRENT = int(skip)
        await message.reply(f"Skip set to {skip}")
    except:
        await message.reply("Usage: /setskip 100")
