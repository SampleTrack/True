import logging, re, asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from info import CHANNELS, LOG_CHANNEL, ADMINS
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()


@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing...", show_alert=True)
        
    _, chat, lst_msg_id = query.data.split("#")
    
    if lock.locked():
        return await query.answer('Wait until the previous process completes.', show_alert=True)
        
    msg = query.message
    button = InlineKeyboardMarkup([[
        InlineKeyboardButton('🚫 Cancel', callback_data="index_cancel")
    ]])
    await msg.edit("Indexing started ✨", reply_markup=button)                        
    
    try: 
        chat = int(chat)
    except ValueError: 
        pass # Leave it as a string if it's a username
        
    await index_files_to_db(int(lst_msg_id), chat, msg, bot)


@Client.on_message((filters.forwarded | (filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.text ) & filters.private & filters.incoming & filters.user(ADMINS))
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match: 
            return await message.reply('Invalid link')
            
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric(): 
            chat_id = int("-100" + chat_id)
            
    elif message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else: 
        return
        
    try: 
        await bot.get_chat(chat_id)
    except ChannelInvalid: 
        return await message.reply('This may be a private channel/group. Make me an admin over there to index the files.')
    except (UsernameInvalid, UsernameNotModified): 
        return await message.reply('Invalid Link specified.')
    except Exception as e: 
        logger.exception(f"Error getting chat {chat_id}: {e}")
        return await message.reply(f'Errors - {e}')
        
    try: 
        k = await bot.get_messages(chat_id, last_msg_id)
    except Exception as e:
        logger.exception(f"Error fetching message ID {last_msg_id} from {chat_id}: {e}")
        return await message.reply('Make sure I am an admin in the channel if it is private.')
        
    if k.empty: 
        return await message.reply('This may be a group and I am not an admin.')
        
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton('✨ Yes', callback_data=f'index#{chat_id}#{last_msg_id}')
        ],[
        InlineKeyboardButton('🚫 Close', callback_data='close_data')
    ]])               
    await message.reply(f'Do you want to index this Channel/Group?\n\nChat ID/Username: <code>{chat_id}</code>\nLast Message ID: <code>{last_msg_id}</code>', reply_markup=buttons)
    

@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    if len(message.command) == 2:
        try: 
            skip = int(message.text.split(" ", 1)[1])
        except ValueError: 
            return await message.reply("Skip Number must be an integer.")
            
        await message.reply(f"Successfully set skip number as {skip}")
        temp.CURRENT = skip
    else:
        await message.reply("Give me a skip number.")


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
            async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    await msg.edit(f"Successfully Cancelled!!\n\nSaved <code>{total_files}</code> files to database!\nDuplicate Files Skipped: <code>{duplicate}</code>\nDeleted Messages Skipped: <code>{deleted}</code>\nNon-Media messages skipped: <code>{no_media + unsupported}</code>(Unsupported Media - `{unsupported}`)\nErrors Occurred: <code>{errors}</code>")
                    break
                    
                current += 1
                if current % 100 == 0:
                    can = [[InlineKeyboardButton('Cancel', callback_data='index_cancel')]]
                    reply = InlineKeyboardMarkup(can)
                    text = f"Total Messages Fetched: <code>{current}</code>\nTotal Messages Saved: <code>{total_files}</code>\nDuplicate Files Skipped: <code>{duplicate}</code>\nDeleted Messages Skipped: <code>{deleted}</code>\nNon-Media messages skipped: <code>{no_media + unsupported}</code>(Unsupported Media - `{unsupported}`)\nErrors Occurred: <code>{errors}</code>"
                    
                    try:
                        await msg.edit_text(text=text, reply_markup=reply)       
                    except FloodWait as t:
                        await asyncio.sleep(t.value)
                        await msg.edit_text(text=text, reply_markup=reply)                          
                
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
                
                # Handling standard string returns instead of random integers
                status = await save_file(media)
                if status == "SAVED":
                    total_files += 1
                elif status == "DUPLICATE":
                    duplicate += 1
                elif status == "ERROR":
                    errors += 1       
                    
        except Exception as e:
            logger.exception(e)
            await msg.edit(f'Error: {e}')
        else:
            if not temp.CANCEL:
                await msg.edit(f'Successfully Saved <code>{total_files}</code> To Database!\nDuplicate Files Skipped: <code>{duplicate}</code>\nDeleted Messages Skipped: <code>{deleted}</code>\nNon-Media Messages Skipped: <code>{no_media + unsupported}</code>(Unsupported Media - `{unsupported}`)\nErrors Occurred: <code>{errors}</code>')





