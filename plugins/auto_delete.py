import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, MessageDeleteForbidden
from utils import get_settings, save_group_settings
from info import ADMINS, LOG_CHANNEL

# 1. THE WATCHER
@Client.on_message(filters.group, group=5)
async def auto_delete_watcher(client, message):
    if message.service:
        return

    chat_id = message.chat.id
    settings = await get_settings(chat_id)
    
    if settings.get("auto_delete", False):
        # 600 seconds = 10 minutes
        asyncio.create_task(delete_after_delay(client, message, 600))

async def delete_after_delay(client, message, delay: int):
    await asyncio.sleep(delay)
    try:
        await message.delete()
        # The logging mechanism you asked for. This will cause API throttling if abused.
        await client.send_message(
            LOG_CHANNEL, 
            f"🗑 **Auto-Delete Success**\nGroup: `{message.chat.title}`\nMessage ID: `{message.id}`"
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        try:
            await message.delete()
            await client.send_message(
                LOG_CHANNEL, 
                f"🗑 **Auto-Delete Success (After FloodWait)**\nGroup: `{message.chat.title}`\nMessage ID: `{message.id}`"
            )
        except Exception:
            pass
    except MessageDeleteForbidden:
        pass
    except Exception:
        pass

# 2. THE CONTROLLER
@Client.on_message(filters.command("autodelete") & filters.group)
async def toggle_auto_delete(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    st = await client.get_chat_member(chat_id, user_id)
    if st.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER] and user_id not in ADMINS:
        return await message.reply("❌ You do not have permission to use this command.")

    if len(message.command) < 2 or message.command[1].lower() not in ['on', 'off']:
        return await message.reply("⚠️ **Invalid format.**\nUse: `/autodelete on` or `/autodelete off`")
        
    status = message.command[1].lower() == 'on'
    
    await save_group_settings(chat_id, 'auto_delete', status)
    
    state_text = "ENABLED ✅" if status else "DISABLED ❌"
    await message.reply(
        f"⏱ **10-Minute Auto-Delete System**\n\n"
        f"Status: **{state_text}** for this group."
    )
    
