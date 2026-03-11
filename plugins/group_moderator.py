import re
import asyncio
from pyrogram import Client, filters, enums
from info import ADMINS, LOG_CHANNEL
from database.users_chats_db import db

# Patterns to detect any form of link or promotion
LINK_PATTERN = r"(https?://|t\.me/|telegram\.me/|telegram\.dog/|www\.)\S+"

@Client.on_message(filters.group & ~filters.service, group=-2)
async def link_and_forward_protector(client, message):
    # 1. Bypass check: Allow Bot Admins and Group Admins
    if message.from_user:
        st = await client.get_chat_member(message.chat.id, message.from_user.id)
        if st.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER] or message.from_user.id in ADMINS:
            return

    # 2. Check for Links in text or caption
    has_link = False
    if message.text and re.search(LINK_PATTERN, message.text, re.IGNORECASE):
        has_link = True
    elif message.caption and re.search(LINK_PATTERN, message.caption, re.IGNORECASE):
        has_link = True
    
    # 3. Check for Links in Inline Buttons (if any)
    if message.reply_markup:
        for row in message.reply_markup.inline_keyboard:
            for btn in row:
                if btn.url:
                    has_link = True

    # 4. Check for Forwarded Content (Strict Restriction)
    is_forwarded = message.forward_from or message.forward_from_chat

    if has_link or is_forwarded:
        try:
            await message.delete()
            # Optional: Warning message that auto-deletes
            warn = await message.reply(f"⚠️ {message.from_user.mention}, links and forwards are not allowed here!")
            await asyncio.sleep(2)
            await warn.delete()
        except Exception:
            pass




