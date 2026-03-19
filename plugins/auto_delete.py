import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, MessageDeleteForbidden
from utils import get_settings, save_group_settings
from info import ADMINS

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 1. THE WATCHER: Captures messages and schedules their deletion
# ------------------------------------------------------------------
# We use group=5 to ensure this runs independently and after 
# important plugins (like filters or indexing) have processed the message.
@Client.on_message(filters.group, group=5)
async def auto_delete_watcher(client, message):
    # Ignore service messages if you only want user chats deleted.
    # Remove this check if you want literally everything deleted.
    if message.service:
        return

    chat_id = message.chat.id
    settings = await get_settings(chat_id)
    
    # Check if the feature is turned on for this specific group
    if settings.get("auto_delete", False):
        # 600 seconds = 10 minutes
        asyncio.create_task(delete_after_delay(message, 600))

async def delete_after_delay(message, delay: int):
    """Background task that waits, then deletes the message."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except FloodWait as e:
        # If Telegram says we are deleting too fast, wait and try one more time
        await asyncio.sleep(e.value)
        try:
            await message.delete()
        except Exception:
            pass
    except MessageDeleteForbidden:
        # Bot lacks admin rights to delete messages
        pass
    except Exception as e:
        # Message was likely already deleted manually by a user or admin
        pass

# ------------------------------------------------------------------
# 2. THE CONTROLLER: Toggle the system ON or OFF for a specific group
# ------------------------------------------------------------------
@Client.on_message(filters.command("autodelete") & filters.group)
async def toggle_auto_delete(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Strict Authorization: Only Group Admins, Owners, or Bot Admins
    st = await client.get_chat_member(chat_id, user_id)
    if st.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER] and user_id not in ADMINS:
        return await message.reply("❌ You do not have permission to use this command.")

    if len(message.command) < 2 or message.command[1].lower() not in ['on', 'off']:
        return await message.reply("⚠️ **Invalid format.**\nUse: `/autodelete on` or `/autodelete off`")
        
    status = message.command[1].lower() == 'on'
    
    # Save the setting using your existing utils function
    await save_group_settings(chat_id, 'auto_delete', status)
    
    state_text = "ENABLED ✅" if status else "DISABLED ❌"
    await message.reply(
        f"⏱ **10-Minute Auto-Delete System**\n\n"
        f"Status: **{state_text}** for this group.\n"
        f"*(Note: Existing messages won't be deleted. Only new messages sent from this point forward will be affected.)*"
  )
  
