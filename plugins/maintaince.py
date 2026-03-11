import logging
from pyrogram import Client, enums, filters, StopPropagation
from info import ADMINS
from utils import temp
from database.users_chats_db import db

logger = logging.getLogger(__name__)

# THE INTERCEPTOR: Runs on Group -1 (Before your standard Group 0 plugins)
@Client.on_message(filters.incoming, group=-1)
async def maintenance_interceptor(client, message):
    if temp.MAINTENANCE_MODE:
        # 1. Allow admins to bypass
        if message.from_user and message.from_user.id in ADMINS:
            return 
        
        # 2. Only reply if the message is in a private chat (Bot PM)
        if message.chat.type == enums.ChatType.PRIVATE:
            try:
                await message.reply("⚙️ **maintenance on msg in bot**", quote=True)
            except Exception:
                pass
        
        # 3. Always stop propagation during maintenance to prevent other plugins from running
        raise StopPropagation

# THE TOGGLE: Admin command to switch it on or off
@Client.on_message(filters.command("maintenance") & filters.user(ADMINS))
async def toggle_maintenance(client, message):
    if len(message.command) < 2 or message.command[1].lower() not in ['on', 'off']:
        return await message.reply("⚠️ **Invalid Format.**\nUse: `/maintenance on` or `/maintenance off`")

    status = message.command[1].lower() == 'on'
    
    if temp.MAINTENANCE_MODE == status:
        return await message.reply(f"Maintenance mode is already **{'ON' if status else 'OFF'}**.")

    # Update cache and database
    temp.MAINTENANCE_MODE = status
    await db.set_maintenance(status)
    
    await message.reply(f"✅ **Maintenance mode has been turned {'ON' if status else 'OFF'}.**")
