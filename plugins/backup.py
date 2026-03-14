import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, LOG_CHANNEL
from database.ia_filterdb import Media

logger = logging.getLogger(__name__)

# Control how many concurrent requests are sent to Telegram
MAX_CONCURRENT_REQUESTS = 10 

# State tracker for the backup process
BACKUP_STATE = {
    "is_running": False,
    "cancel": False
}

async def send_single_backup(bot, file, semaphore, status_tracker):
    """Worker function to send a single media file with flood protection and cancellation check."""
    if BACKUP_STATE["cancel"]:
        return

    async with semaphore:
        # Check again after waiting for the semaphore
        if BACKUP_STATE["cancel"]:
            return
            
        try:
            await bot.send_cached_media(
                chat_id=LOG_CHANNEL,
                file_id=file.file_id,
                caption=f"📦 **Advanced Backup**\n\n**Name:** `{file.file_name}`\n**Size:** `{file.file_size}`"
            )
            status_tracker["success"] += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            # Retry once after the wait
            return await send_single_backup(bot, file, semaphore, status_tracker)
        except Exception as e:
            logger.error(f"Backup failed for {file.file_name}: {e}")
            status_tracker["failed"] += 1

@Client.on_message(filters.command("backup_db") & filters.user(ADMINS))
async def backup_files_advanced(bot, message):
    if BACKUP_STATE["is_running"]:
        return await message.reply("⚠️ **A backup is already in progress.** Stop it first if you want to start a new one.")

    # Reset states
    BACKUP_STATE["is_running"] = True
    BACKUP_STATE["cancel"] = False
    
    sts = await message.reply("🚀 **Initializing High-Speed Backup...**")
    
    # Fetch all records at once into memory
    all_files = await Media.find({}).to_list(length=None) 
    total_files = len(all_files)
    
    if total_files == 0:
        BACKUP_STATE["is_running"] = False
        return await sts.edit("❌ Database is empty.")

    # Create the Stop Button
    stop_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛑 STOP BACKUP", callback_data="stop_backup_process")]]
    )

    await sts.edit(
        f"📂 **Total Files:** `{total_files}`\n⚡ **Mode:** Concurrent Asynchronous\nProcessing...",
        reply_markup=stop_markup
    )

    status_tracker = {"success": 0, "failed": 0}
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    # Create tasks for all files
    tasks = [send_single_backup(bot, file, semaphore, status_tracker) for file in all_files]
    
    # Start background task to update the UI periodically
    async def progress_updater():
        while (status_tracker["success"] + status_tracker["failed"]) < total_files:
            if BACKUP_STATE["cancel"]:
                break
                
            done = status_tracker["success"] + status_tracker["failed"]
            try:
                await sts.edit(
                    f"📊 **Live Backup Progress**\n\n"
                    f"✅ Success: `{status_tracker['success']}`\n"
                    f"❌ Failed: `{status_tracker['failed']}`\n"
                    f"🔄 Progress: `{done}/{total_files}`",
                    reply_markup=stop_markup
                )
            except:
                pass
            await asyncio.sleep(10) # Update UI every 10 seconds to avoid edit limits

    updater_task = asyncio.create_task(progress_updater())

    # Execute all tasks concurrently
    await asyncio.gather(*tasks)
    
    # Cleanup
    updater_task.cancel()
    BACKUP_STATE["is_running"] = False
    
    # Final Status Report
    if BACKUP_STATE["cancel"]:
        await sts.edit(
            f"🛑 **Backup Forcefully Stopped**\n\n"
            f"📦 Processed Before Stop: `{status_tracker['success'] + status_tracker['failed']}` / `{total_files}`\n"
            f"📤 Sent to Logs: `{status_tracker['success']}`\n"
            f"⚠️ Errors: `{status_tracker['failed']}`"
        )
    else:
        await sts.edit(
            f"🏁 **Backup Completed Successfully**\n\n"
            f"📦 Total Processed: `{total_files}`\n"
            f"📤 Sent to Logs: `{status_tracker['success']}`\n"
            f"⚠️ Errors: `{status_tracker['failed']}`"
        )

@Client.on_callback_query(filters.regex("^stop_backup_process$") & filters.user(ADMINS))
async def stop_backup_callback(bot, query):
    if not BACKUP_STATE["is_running"]:
        return await query.answer("No backup is currently running.", show_alert=True)
        
    BACKUP_STATE["cancel"] = True
    await query.answer("Halting backup process... Please wait a few seconds for active uploads to drop.", show_alert=True)
    
