import logging
import re
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from info import CHANNELS, LOG_CHANNEL, ADMINS
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()

# Separate the cancel callback from the start callback for cleaner logic
@Client.on_callback_query(filters.regex(r'^index_cancel$'))
async def cancel_indexing(bot, query):
    temp.CANCEL = True
    await query.answer("Cancelling Indexing...", show_alert=True)

@Client.on_callback_query(filters.regex(r'^index#'))
async def index_files(bot, query):
    if lock.locked():
        return await query.answer('Wait until the previous process completes.', show_alert=True)
    
    _, chat, lst_msg_id = query.data.split("#")
    
    # Properly handle integer vs string (username) casting
    try:
        chat = int(chat)
    except ValueError:
        pass # It's a string username, which Pyrogram handles fine

    msg = query.message
    button = InlineKeyboardMarkup([[
        InlineKeyboardButton('🚫 Cancel', callback_data="index_cancel")
    ]])
    
    await msg.edit("Indexing has started ✨", reply_markup=button)                        
    await index_files_to_db(int(lst_msg_id), chat, msg, bot)


@Client.on_message(
    (filters.forwarded | filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & 
    filters.text & 
    filters.private & 
    filters.incoming & 
    filters.user(ADMINS)
)
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match:
            return await message.reply('Invalid link format.')
        
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        
        # Prevent appending "-100" if it already exists
        if chat_id.isnumeric() and not chat_id.startswith("-100"): 
            chat_id = int("-100" + chat_id)
        elif chat_id.lstrip('-').isnumeric():
            chat_id = int(chat_id)

    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return

    # Verify access to the chat
    try:
        await bot.get_chat(chat_id)
    except ChannelInvalid:
        return await message.reply('This may be a private channel/group. Make me an admin there to index files.')
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply('Invalid Link specified.')
    except Exception as e:
        logger.error(f"Error fetching chat: {e}")
        return await message.reply(f'Error fetching chat: {e}')

    # Verify message existence / admin rights
    try:
        k = await bot.get_messages(chat_id, last_msg_id)
        if k.empty:
            return await message.reply('This may be a group and I am not an admin.')
    except Exception as e:
        logger.error(f"Error fetching messages: {e}")
        return await message.reply('Make sure I am an admin in the channel if it is private.')

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton('✨ Yes', callback_data=f'index#{chat_id}#{last_msg_id}')],
        [InlineKeyboardButton('🚫 Close', callback_data='close_data')]
    ])               
    await message.reply(
        f'Do you want to index this Channel/Group?\n\n'
        f'Chat ID/Username: <code>{chat_id}</code>\n'
        f'Last Message ID: <code>{last_msg_id}</code>', 
        reply_markup=buttons
    )
    

@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    if len(message.command) == 2:
        try:
            # Don't split strings manually when Pyrogram provides command lists
            skip = int(message.command[1])
        except ValueError:
            return await message.reply("Skip number must be an integer.")
        
        temp.CURRENT = skip
        await message.reply(f"Successfully set skip number to {skip}")
    else:
        await message.reply("Provide a skip number. Usage: /setskip [number]")


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    
    async with lock:
        try:
            current = temp.CURRENT
            temp.CANCEL = False
            
            # Note: iter_messages is deprecated in Pyrogram v2. 
            # If using v2+, replace this with `async for message in bot.get_chat_history(chat, offset_id=lst_msg_id):`
            # and adapt the loop logic to handle message IDs manually if needed.
            async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    await msg.edit(
                        f"Successfully Cancelled!\n\n"
                        f"Saved <code>{total_files}</code> files to database!\n"
                        f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
                        f"Deleted Messages Skipped: <code>{deleted}</code>\n"
                        f"Non-Media messages skipped: <code>{no_media + unsupported}</code> "
                        f"(Unsupported Media - <code>{unsupported}</code>)\n"
                        f"Errors Occurred: <code>{errors}</code>"
                    )
                    break
                
                current += 1
                
                # Update status message every 100 iterations
                if current % 100 == 0:
                    reply = InlineKeyboardMarkup(
                        [[InlineKeyboardButton('Cancel', callback_data='index_cancel')]]
                    )
                    text = (
                        f"Total Messages Fetched: <code>{current}</code>\n"
                        f"Total Messages Saved: <code>{total_files}</code>\n"
                        f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
                        f"Deleted Messages Skipped: <code>{deleted}</code>\n"
                        f"Non-Media messages skipped: <code>{no_media + unsupported}</code> "
                        f"(Unsupported Media - <code>{unsupported}</code>)\n"
                        f"Errors Occurred: <code>{errors}</code>"
                    )
                    try:
                        await msg.edit_text(text=text, reply_markup=reply)       
                    except FloodWait as t:
                        await asyncio.sleep(t.value)
                        await msg.edit_text(text=text, reply_markup=reply)                          
                
                # Message parsing logic
                if message.empty:
                    deleted += 1
                    continue
                
                if not message.media:
                    no_media += 1
                    continue
                
                if message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    unsupported += 1
                    continue
                
                media = getattr(message, message.media.value, None)
                if not media:
                    unsupported += 1
                    continue
                
                media.file_type = message.media.value
                media.caption = message.caption
                
                # DB insertion
                aynav, vnay = await save_file(media)
                if aynav:
                    total_files += 1
                elif vnay == 0:
                    duplicate += 1
                elif vnay == 2:
                    errors += 1       
                    
        except Exception as e:
            logger.exception("Error during file indexing")
            await msg.edit(f'Critical Error occurred: {e}')
        else:
            if not temp.CANCEL:
                await msg.edit(
                    f"Successfully Saved <code>{total_files}</code> To Database!\n"
                    f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
                    f"Deleted Messages Skipped: <code>{deleted}</code>\n"
                    f"Non-Media Messages Skipped: <code>{no_media + unsupported}</code> "
                    f"(Unsupported Media - <code>{unsupported}</code>)\n"
                    f"Errors Occurred: <code>{errors}</code>"
    )
