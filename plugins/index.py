import logging, re, asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from info import CHANNELS, LOG_CHANNEL, ADMINS
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()


@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cᴀɴᴄᴇʟʟɪɴɢ Iɴᴅᴇxɪɴɢ", show_alert=True)
        
    perfx, chat, lst_msg_id = query.data.split("#")
    if lock.locked():
        return await query.answer('Wᴀɪᴛ Uɴᴛɪʟ Pʀᴇᴠɪᴏᴜs Pʀᴏᴄᴇss Cᴏᴍᴘʟᴇᴛᴇ', show_alert=True)
    msg = query.message
    button = InlineKeyboardMarkup([[
        InlineKeyboardButton('🚫 ᴄᴀɴᴄᴇʟʟ', "index_cancel")
    ]])
    await msg.edit("ɪɴᴅᴇxɪɴɢ ɪs sᴛᴀʀᴛᴇᴅ ✨", reply_markup=button)                        
    try: chat = int(chat)
    except: chat = chat
    await index_files_to_db(int(lst_msg_id), chat, msg, bot)


@Client.on_message((filters.forwarded | (filters.regex("(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.text ) & filters.private & filters.incoming & filters.user(ADMINS))
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile("(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match: return await message.reply('Invalid link')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric(): chat_id  = int(("-100" + chat_id))
    elif message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else: return
    try: await bot.get_chat(chat_id)
    except ChannelInvalid: return await message.reply('This may be a private channel / group. Make me an admin over there to index the files.')
    except (UsernameInvalid, UsernameNotModified): return await message.reply('Invalid Link specified.')
    except Exception as e: return await message.reply(f'Errors - {e}')
    try: k = await bot.get_messages(chat_id, last_msg_id)
    except: return await message.reply('Make Sure That Iam An Admin In The Channel, if channel is private')
    if k.empty: return await message.reply('This may be group and iam not a admin of the group.')
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton('✨ ʏᴇꜱ', callback_data=f'index#{chat_id}#{last_msg_id}')
        ],[
        InlineKeyboardButton('🚫 ᴄʟᴏꜱᴇ', callback_data='close_data')
    ]])               
    await message.reply(f'Do You Want To Index This Channel/ Group ?\n\nChat ID/ Username: <code>{chat_id}</code>\nLast Message ID: <code>{last_msg_id}</code>', reply_markup=buttons)
    

@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    if len(message.command) == 2:
        try: skip = int(message.text.split(" ", 1)[1])
        except: return await message.reply("Skip Number Should Be An Integer.")
        await message.reply(f"Successfully Set Skip Number As {skip}")
        temp.CURRENT = int(skip)
    else:
        await message.reply("Give Me A Skip Number")


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    batch = []
    total_files, duplicate, errors, deleted, no_media, unsupported = 0, 0, 0, 0, 0, 0
    last_ui_update = time.time()

    async with lock:
        try:
            temp.CANCEL = False
            # iter_messages is already a generator, which is good.
            async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                if temp.CANCEL: break

                # 1. Validation Logic (Fast Skip)
                if message.empty: 
                    deleted += 1
                    continue
                if not message.media or message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    no_media += 1
                    continue
                
                media = getattr(message, message.media.value, None)
                if not media: continue
                
                media.file_type = message.media.value
                media.caption = message.caption
                batch.append(media)

                # 2. Batch Processing (The Speed Secret)
                if len(batch) >= 100:
                    inserted, dups = await save_batch_to_db(batch)
                    total_files += inserted
                    duplicate += dups
                    batch = [] # Clear buffer

                # 3. UI Updates (Time-based, not count-based)
                if time.time() - last_ui_update > 5: # Update every 5 seconds
                    status_text = f"🚀 **Indexing...**\n\nSaved: `{total_files}`\nDuplicates: `{duplicate}`\nSkipped: `{no_media + deleted}`"
                    try:
                        await msg.edit_text(status_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🚫 CANCEL', "index_cancel")]]))
                        last_ui_update = time.time()
                    except FloodWait as e:
                        await asyncio.sleep(e.value)

            # Final push for remaining items in batch
            if batch:
                inserted, dups = await save_batch_to_db(batch)
                total_files += inserted
                duplicate += dups

        except Exception as e:
            logger.exception(e)
            await msg.edit(f"Fatal Error: {e}")
        finally:
            await msg.edit(f"✅ **Indexing Complete**\nTotal Saved: `{total_files}`\nDuplicates: `{duplicate}`")
            
