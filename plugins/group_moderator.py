# Create/Update a file like plugins/group_moderator.py

import re
from pyrogram import Client, filters, enums
from info import LOG_CHANNEL, ADMINS

# Configuration
BANNED_WORDS = ["porn"] # Add your list here
WARN_LIMIT = 3
user_warns = {} # In-memory warning tracker (reset on restart)

# RegEx Patterns
PROMO_LINK_PATTERN = r"(https?://|t\.me/|telegram\.me/)\S+"
PHONE_PATTERN = r"\+?\d{10,12}"
EMAIL_PATTERN = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

@Client.on_message(filters.group & ~filters.service)
async def group_moderator(client, message):
    if not message.text or (message.from_user and message.from_user.id in ADMINS):
        return

    text = message.text.lower()
    content_violation = False
    reason = ""

    # Check Banned Words
    if any(word in text for word in BANNED_WORDS):
        content_violation = True
        reason = "Banned words/language"
    
    # Check Links, Mobile, and Email
    elif re.search(PROMO_LINK_PATTERN, text):
        content_violation = True
        reason = "Promotion links"
    elif re.search(PHONE_PATTERN, text):
        content_violation = True
        reason = "Mobile number"
    elif re.search(EMAIL_PATTERN, text):
        content_violation = True
        reason = "Email ID"

    if content_violation:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Increment Warning
        user_warns[user_id] = user_warns.get(user_id, 0) + 1
        current_warns = user_warns[user_id]

        # Auto Delete
        await message.delete()

        if current_warns >= WARN_LIMIT:
            # Ban User
            await client.ban_chat_member(chat_id, user_id)
            log_text = (f"🚫 **User Banned**\n\n"
                        f"**User:** {message.from_user.mention} (`{user_id}`)\n"
                        f"**Chat:** {message.chat.title}\n"
                        f"**Reason:** Reached 3 warnings for {reason}")
            
            await client.send_message(LOG_CHANNEL, log_text)
            await client.send_message(chat_id, f"❌ {message.from_user.mention} has been banned for repeated violations.")
            del user_warns[user_id] # Reset after ban
        else:
            # Warn User
            warn_msg = await message.reply(
                f"⚠️ {message.from_user.mention}, your message was deleted for {reason}.\n"
                f"Warning: {current_warns}/{WARN_LIMIT}. 3 strikes = Ban."
            )
            # Optional: Delete warning message after 10 seconds
            await asyncio.sleep(10)
            await warn_msg.delete()
          
