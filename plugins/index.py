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

# Global counters for high-speed tracking
class Stats:
    def __init__(self):
        self.total_files = 0
        self.duplicate = 0
        self.errors = 0
        self.deleted = 0
        self.no_media = 0
        self.unsupported = 0

async def fast_save(media, stats):
    """Worker function to handle individual saves concurrently"""
    try:
        aynav, vnay = await save_file(media)
        if aynav:
            stats.total_files += 1
        elif vnay == 0:
            stats.duplicate += 1
        elif vnay == 2:
            stats.errors += 1
    except Exception:
        stats.errors += 1

async def index_files_to_db(lst_msg_id, chat, msg, bot):
    stats = Stats()
    # Semaphore prevents overwhelming the database/Telegram (Limit to 20 concurrent saves)
    sem = asyncio.Semaphore(20)
    tasks = []
    
    async with lock:
        try:
            current = temp.CURRENT
            temp.CANCEL = False
            
            # Use a faster iteration strategy
            async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    break
                
                current += 1
                
                # Update UI every 200 messages to reduce overhead
                if current % 200 == 0:
                    status_text = (
                        f"⚡️ **Fast Indexing...**\n"
                        f"Fetched: `{current}`\nSaved: `{stats.total_files}`\n"
                        f"Duplicates: `{stats.duplicate}`\nErrors: `{stats.errors}`"
                    )
                    try:
                        await msg.edit_text(status_text, reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton('🚫 CANCEL', callback_data='index_cancel')
                        ]]))
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                    except Exception:
                        pass

                if message.empty:
                    stats.deleted += 1
                    continue
                
                if not message.media or message.media not in [
                    enums.MessageMediaType.VIDEO, 
                    enums.MessageMediaType.AUDIO, 
                    enums.MessageMediaType.DOCUMENT
                ]:
                    stats.no_media += 1
                    continue

                media = getattr(message, message.media.value, None)
                if not media:
                    continue
                
                media.file_type = message.media.value
                media.caption = message.caption

                # Create concurrent task
                async def tasked_save(m):
                    async with sem:
                        await fast_save(m, stats)
                
                tasks.append(asyncio.create_task(tasked_save(media)))

                # To prevent memory leaks on massive channels, wait for tasks in chunks
                if len(tasks) >= 100:
                    await asyncio.gather(*tasks)
                    tasks = []

            # Clean up remaining tasks
            if tasks:
                await asyncio.gather(*tasks)

        except Exception as e:
            logger.exception(e)
            await msg.edit(f'Error: {e}')
        finally:
            final_text = (
                f"✅ **Indexing Complete**\n\n"
                f"📂 Total Saved: `{stats.total_files}`\n"
                f"⏩ Duplicates: `{stats.duplicate}`\n"
                f"🗑 Deleted/Empty: `{stats.deleted}`\n"
                f"❌ Errors: `{stats.errors}`"
            )
            await msg.edit(final_text)
            
