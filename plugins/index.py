import logging
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, ChatAdminRequired, ChannelInvalid, UsernameInvalid, UsernameNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from utils import temp

# Setup Logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing...", show_alert=True)

    # Logic: Securely unpack the callback data
    try:
        data = query.data.split("#")
        # index#accept#{chat_id}#{last_msg_id}#{from_user_id}
        action = data[1]
        chat = data[2]
        lst_msg_id = int(data[3])
        from_user = int(data[4])
    except (IndexError, ValueError) as e:
        logger.error(f"Callback data error: {e}")
        return await query.answer("Malformed callback data.", show_alert=True)

    if action == 'reject':
        await query.message.delete()
        await bot.send_message(from_user, "Your submission for indexing has been declined.")
        return

    if lock.locked():
        return await query.answer('Another indexing process is already running!', show_alert=True)

    await query.answer('Starting Process... ⏳', show_alert=True)
    
    if from_user not in ADMINS:
        await bot.send_message(from_user, "Your request was accepted and indexing has started.")

    await query.message.edit(
        "**Indexing Started...**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
    )

    # Convert chat to int if it's a numeric ID
    try:
        chat = int(chat)
    except ValueError:
        pass 

    await index_files_to_db(lst_msg_id, chat, query.message, bot)

@Client.on_message((filters.forwarded | filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.private)
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match:
            return
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
        chat_info = await bot.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"Error accessing chat: {e}")

    # Generate Buttons
    if message.from_user.id in ADMINS:
        buttons = [[InlineKeyboardButton('Start Indexing', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')]]
        return await message.reply(f"Admin indexing request for `{chat_id}`", reply_markup=InlineKeyboardMarkup(buttons))

    # User Request Logic
    buttons = [
        [InlineKeyboardButton('Accept', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
        [InlineKeyboardButton('Reject', callback_data=f'index#reject#{chat_id}#{message.id}#{message.from_user.id}')]
    ]
    await bot.send_message(LOG_CHANNEL, f"Index Request from {message.from_user.mention}\nChat: `{chat_id}`", reply_markup=InlineKeyboardMarkup(buttons))
    await message.reply("Request sent to moderators.")

async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    
    async with lock:
        try:
            temp.CANCEL = False
            # Standard Pyrogram Method: get_chat_history
            async for message in bot.get_chat_history(chat, limit=lst_msg_id):
                if temp.CANCEL:
                    break
                
                if message.empty:
                    deleted += 1
                    continue
                if not message.media:
                    no_media += 1
                    continue
                
                # Check for specific media types
                media_type = message.media.value
                if media_type not in ['video', 'audio', 'document']:
                    continue

                media = getattr(message, media_type, None)
                if not media:
                    continue

                media.file_type = media_type
                media.caption = message.caption
                
                success, status = await save_file(media)
                if success:
                    total_files += 1
                elif status == 0:
                    duplicate += 1
                elif status == 2:
                    errors += 1

                # Update Progress every 20 files
                if (total_files + duplicate + deleted + no_media) % 20 == 0:
                    try:
                        await msg.edit_text(
                            f"**Indexing Status**\nSaved: `{total_files}`\nDuplicates: `{duplicate}`\nSkipped: `{no_media}`",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
                        )
                    except:
                        pass

        except Exception as e:
            logger.exception(e)
            await msg.edit(f"Critical Error: {e}")
        finally:
            final_text = f"**Indexing Complete**\nTotal Saved: `{total_files}`\nDuplicates: `{duplicate}`\nErrors: `{errors}`"
            await msg.edit(final_text)

@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    try:
        skip = int(message.command[1])
        temp.CURRENT = skip
        await message.reply(f"Skip set to {skip}")
    except:
        await message.reply("Usage: /setskip 100")
