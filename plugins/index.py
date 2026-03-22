import logging, re, asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from info import CHANNELS, LOG_CHANNEL, ADMINS
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp

logger = logging.getLogger(__name__)
lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing...", show_alert=True)
        
    _, chat, lst_msg_id = query.data.split("#")
    if lock.locked():
        return await query.answer('Wait for the previous process to finish!', show_alert=True)
    
    msg = query.message
    button = InlineKeyboardMarkup([[
        InlineKeyboardButton('🚫 CANCEL', "index_cancel")
    ]])
    await msg.edit("<b>Indexing Started...</b> ✨", reply_markup=button)                        
    
    # Ensure chat ID is handled correctly (numeric or username)
    try:
        chat = int(chat)
    except ValueError:
        pass
        
    await index_files_to_db(int(lst_msg_id), chat, msg, bot)


@Client.on_message((filters.forwarded | (filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.text ) & filters.private & filters.user(ADMINS))
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match: return await message.reply('Invalid link')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric(): 
            chat_id = int(("-100" + chat_id))
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else: 
        return

    try: 
        await bot.get_chat(chat_id)
    except Exception as e: 
        return await message.reply(f'Error accessing chat: {e}')

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton('✨ START INDEXING', callback_data=f'index#{chat_id}#{last_msg_id}')],
        [InlineKeyboardButton('🚫 CLOSE', callback_data='close_data')]
    ])               
    await message.reply(f'<b>Index Request:</b>\n\nChat: <code>{chat_id}</code>\nLast ID: <code>{last_msg_id}</code>', reply_markup=buttons)

async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    
    async with lock:
        try:
            current = temp.CURRENT # Using your global skip value
            temp.CANCEL = False
            
            # Use offset to actually skip the messages you want to avoid
            async for message in bot.iter_messages(chat, offset_id=lst_msg_id, offset=current):
                if temp.CANCEL:
                    break
                
                current += 1
                if current % 20 == 0: # Update UI more frequently for better feedback
                    try:
                        await msg.edit_text(
                            text=f"<b>Status:</b> Indexing...\n"
                                 f"Fetched: <code>{current}</code>\n"
                                 f"Saved: <code>{total_files}</code>\n"
                                 f"Duplicates: <code>{duplicate}</code>\n"
                                 f"Skipped: <code>{no_media + unsupported}</code>",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
                        )
                    except FloodWait as t:
                        await asyncio.sleep(t.value)
                    except Exception:
                        pass

                if not message or message.empty:
                    deleted += 1
                    continue
                
                # Check for relevant media types
                if not message.media or message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    no_media += 1
                    continue
                
                media = getattr(message, message.media.value, None)
                if not media:
                    unsupported += 1
                    continue

                # Prepare media data for DB
                media.file_type = message.media.value
                media.caption = message.caption
                
                # Critical: save_file MUST check for file_unique_id
                success, status = await save_file(media)
                
                if success:
                    total_files += 1
                elif status == 0: # Logic for Duplicate
                    duplicate += 1
                elif status == 2: # Logic for Error
                    errors += 1
                    
        except Exception as e:
            logger.exception(e)
            await msg.edit(f'Fatal Error: {e}')
        else:
            final_text = (f"<b>Indexing Finished!</b>\n\n"
                          f"✅ Saved: <code>{total_files}</code>\n"
                          f"🔁 Duplicates: <code>{duplicate}</code>\n"
                          f"🗑 Deleted/Empty: <code>{deleted}</code>\n"
                          f"🚫 Unsupported: <code>{no_media + unsupported}</code>\n"
                          f"⚠️ Errors: <code>{errors}</code>")
            await msg.edit(final_text)

