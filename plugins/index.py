import logging
import asyncio
import time
import re
from datetime import timedelta
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.file_id import FileId

from info import ADMINS, INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import Media, save_file # Importing Media collection directly for batching
from utils import temp

logger = logging.getLogger(__name__)
lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing...")
    
    _, raju, chat, lst_msg_id, from_user = query.data.split("#")
    
    if raju == 'reject':
        await query.message.delete()
        await bot.send_message(int(from_user), 'Your Submission has been declined.')
        return

    if lock.locked():
        return await query.answer('Wait until previous process completes.', show_alert=True)

    await query.answer('Processing...⏳', show_alert=True)
    
    msg = query.message
    await msg.edit(
        "<b>Checking for Resume State...</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
    )

    try:
        chat_id = int(chat) if chat.strip("-").isnumeric() else chat
        # Start the engine
        await index_files_to_db(int(lst_msg_id), chat_id, msg, bot)
    except Exception as e:
        logger.exception(e)
        await msg.edit(f"Error: {e}")

async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    current = 0
    batch = []
    start_time = time.time()
    
    # 1. Persistent Resume State: Check if we have a skip point in temp or DB
    # We use temp.CURRENT as the offset_id for pyrogram's iterator
    skip_id = temp.CURRENT 

    async with lock:
        try:
            temp.CANCEL = False
            
            # Using reverse=True and offset_id allows us to resume from the last saved message
            async for message in bot.iter_messages(chat, offset_id=skip_id, reverse=True):
                if temp.CANCEL:
                    break

                current += 1
                
                # Basic Filtering
                if message.empty or not message.media:
                    continue
                if message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    continue

                # 2. Strict Error Handling for File Decoding
                try:
                    media_type = message.media.value
                    media = getattr(message, media_type, None)
                    if not media:
                        continue

                    # 3. Optimized Duplicate Check & Smart Filtering
                    # Check if file_unique_id exists in DB before doing heavy processing
                    # This prevents RAM spikes by not loading duplicates into the batch list
                    exists = await Media.find_one({'file_unique_id': media.file_unique_id})
                    if exists:
                        duplicate += 1
                        continue

                    # Prepare for Batching
                    data = {
                        'file_name': getattr(media, 'file_name', 'None'),
                        'file_size': media.file_size,
                        'file_id': media.file_id,
                        'file_unique_id': media.file_unique_id,
                        'file_type': media_type,
                        'caption': message.caption or "",
                    }
                    batch.append(data)

                except Exception:
                    errors += 1
                    continue

                # 4. Batch Commits (Massive Speed Gain)
                if len(batch) >= 40:
                    try:
                        # insert_many is significantly faster than calling save_file 40 times
                        await Media.insert_many(batch, ordered=False)
                        total_files += len(batch)
                    except Exception as e:
                        # Handle cases where some might still be duplicates
                        errors += 1
                    
                    batch.clear()
                    
                    # Update Resume State
                    temp.CURRENT = message.id 
                    
                    # 5. Enhanced UI with ETA
                    elapsed = time.time() - start_time
                    files_per_sec = total_files / elapsed if elapsed > 0 else 0
                    remaining_msg = lst_msg_id - message.id
                    eta_sec = remaining_msg / files_per_sec if files_per_sec > 0 else 0
                    eta_str = str(timedelta(seconds=int(eta_sec)))

                    await msg.edit_text(
                        text=(f"<b>Indexing...</b>\n\n"
                              f"📂 Saved: <code>{total_files}</code>\n"
                              f"🔄 Duplicates: <code>{duplicate}</code>\n"
                              f"⏳ ETA: <code>{eta_str}</code>\n"
                              f"🚀 Last Msg ID: <code>{message.id}</code>"),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
                    )

            # Final flush for remaining files
            if batch:
                await Media.insert_many(batch, ordered=False)
                total_files += len(batch)

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.exception(e)
            await msg.edit(f"Critical Loop Error: {e}")
        finally:
            status = "Cancelled" if temp.CANCEL else "Completed"
            await msg.edit(
                f"<b>Indexing {status}!</b>\n\n"
                f"Total Saved: <code>{total_files}</code>\n"
                f"Duplicates Skipped: <code>{duplicate}</code>\n"
                f"Errors: <code>{errors}</code>"
            )
            # Reset skip point on completion
            if not temp.CANCEL:
                temp.CURRENT = 0
