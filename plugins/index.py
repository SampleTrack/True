import time
import logging
import asyncio
from datetime import timedelta
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from pyrogram.file_id import FileId

from database.ia_filterdb import batch_save_files, get_index_state, update_index_state, Media
from utils import temp
from info import ADMINS

logger = logging.getLogger(__name__)
lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing...")

    data = query.data.split("#")
    if len(data) < 5:
        return await query.answer("Invalid Data")
        
    _, action, chat, lst_msg_id, from_user = data
    
    if action == 'reject':
        await query.message.delete()
        return await bot.send_message(int(from_user), "Indexing request declined.")

    if lock.locked():
        return await query.answer('Another indexing process is currently running.', show_alert=True)

    await query.answer('Starting Engine... 🚀', show_alert=True)
    
    # Check for resume state
    saved_id = await get_index_state(chat)
    skip_id = saved_id if saved_id > 0 else 0
    
    await query.message.edit(
        f"Indexing Started from: {skip_id if skip_id else 'Beginning'}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
    )
    
    try:
        chat_id = int(chat) if chat.strip('-').isdigit() else chat
        await index_files_to_db(int(lst_msg_id), chat_id, query.message, bot, skip_id)
    except Exception as e:
        logger.exception(e)
        await query.message.edit(f"Fatal Error: {e}")

async def index_files_to_db(lst_msg_id, chat, msg, bot, skip_id):
    total_files = 0
    duplicate = 0
    errors = 0
    current = 0
    batch = []
    start_time = time.time()
    
    async with lock:
        try:
            temp.CANCEL = False
            # Using iter_messages with offset_id for resume support
            async for message in bot.iter_messages(chat, offset_id=skip_id, reverse=True):
                if temp.CANCEL:
                    break
                
                current += 1
                
                # Basic validation
                if message.empty or not message.media:
                    continue
                
                if message.media not in [enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT]:
                    continue

                try:
                    media_type = message.media.value
                    media = getattr(message, media_type, None)
                    if not media: continue

                    # Smart Filtering: Check uniqueness before processing
                    # We use file_unique_id to solve the "Forwarded Duplicate" problem
                    exists = await Media.find_one({'file_unique_id': media.file_unique_id})
                    if exists:
                        duplicate += 1
                        continue

                    # Prepare document for batch
                    file_data = {
                        'file_name': getattr(media, 'file_name', 'No Name'),
                        'file_size': media.file_size,
                        'file_id': media.file_id,
                        'file_unique_id': media.file_unique_id,
                        'file_type': media_type,
                        'caption': message.caption or "",
                        'chat_id': chat,
                        'msg_id': message.id
                    }
                    batch.append(file_data)

                except Exception:
                    # Wraps decoding logic so one bad file doesn't kill the loop
                    errors += 1
                    continue

                # Batch Commit Logic (50 files for massive speed)
                if len(batch) >= 50:
                    inserted, dups = await batch_save_files(batch)
                    total_files += inserted
                    duplicate += dups
                    batch.clear()
                    
                    # Persistent State: Save checkpoint
                    await update_index_state(chat, message.id)
                    
                    # UI: Calculated ETA
                    elapsed = time.time() - start_time
                    speed = total_files / elapsed if elapsed > 0 else 0
                    remaining = lst_msg_id - message.id
                    eta_sec = remaining / speed if speed > 0 else 0
                    eta_str = str(timedelta(seconds=int(eta_sec)))

                    await msg.edit_text(
                        text=(f"<b>Indexing Chat:</b> <code>{chat}</code>\n\n"
                              f"✅ Saved: <code>{total_files}</code>\n"
                              f"🔄 Duplicates: <code>{duplicate}</code>\n"
                              f"⚠️ Errors: <code>{errors}</code>\n"
                              f"⏳ ETA: <code>{eta_str}</code>"),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
                    )

            # Final flush for the last batch
            if batch:
                inserted, dups = await batch_save_files(batch)
                total_files += inserted
                duplicate += dups
                await update_index_state(chat, lst_msg_id)

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.exception(e)
            await msg.edit(f"Loop Error: {e}")
        finally:
            status = "CANCELLED" if temp.CANCEL else "COMPLETED"
            await msg.edit(
                f"<b>Indexing {status}</b>\n\n"
                f"Total Files: <code>{total_files}</code>\n"
                f"Duplicates: <code>{duplicate}</code>\n"
                f"Errors: <code>{errors}</code>"
            )
