import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from info import ADMINS, LOG_CHANNEL
from database.ia_filterdb import Media

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("backup_db") & filters.user(ADMINS))
async def backup_files(bot, message):
    """
    Sends all files indexed in the database to the Log Channel as a backup.
    """
    sts = await message.reply("📑 **Starting Database Backup...**\nFetching all file records.")
    
    total_files = await Media.count_documents({})
    if total_files == 0:
        return await sts.edit("❌ No files found in the database to backup.")

    await sts.edit(f"📂 **Found {total_files} files.**\nSending to Log Channel... This may take a while due to Telegram flood limits.")

    count = 0
    failed = 0
    
    # Iterate through all files in the Media collection
    async for file in Media.find({}):
        try:
            # Send the file using its cached file_id
            await bot.send_cached_media(
                chat_id=LOG_CHANNEL,
                file_id=file.file_id,
                caption=f"📦 **Backup**\n\n**Name:** `{file.file_name}`\n**Size:** `{file.file_size}`"
            )
            count += 1
            
            # Update progress every 20 files to avoid hitting edit limits
            if count % 20 == 0:
                await sts.edit(f"📊 **Backup Progress:**\n\n✅ Sent: `{count}`\n❌ Failed: `{failed}`\nRemaining: `{total_files - (count + failed)}`")
            
            # Small delay to prevent aggressive flood triggers
            await asyncio.sleep(0.5)

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"Backup failed for {file.file_name}: {e}")
            failed += 1

    await sts.edit(f"✅ **Backup Complete!**\n\n📂 Total Files: `{total_files}`\n📤 Successfully Sent: `{count}`\n⚠️ Failed: `{failed}`")
