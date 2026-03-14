import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, MessageDeleteForbidden

@Client.on_message(filters.command("purge") & filters.group)
async def purge_messages(client, message):
    # 1. Authorization: Only Admins/Owners should use this
    st = await client.get_chat_member(message.chat.id, message.from_user.id)
    if st.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
        return await message.reply("You don't have permission to do this.")

    # 2. Logic Check: Must reply to a message to set the starting point
    if not message.reply_to_message:
        return await message.reply("Logic flaw: You must reply to a message to define where the purge starts.")

    start_message_id = message.reply_to_message.id
    end_message_id = message.id
    
    # Calculate total messages to delete
    message_ids = list(range(start_message_id, end_message_id + 1))
    total_messages = len(message_ids)

    # Prevent massive accidental purges that trigger floodwaits
    if total_messages > 1000:
        return await message.reply("Too many messages. Purge limit is 1000 at a time to prevent API throttling.")

    status_msg = await message.reply(f"🗑 Purging {total_messages} messages...")
    deleted_count = 0

    # 3. Execution: Telegram allows deleting up to 100 messages per API call
    for i in range(0, total_messages, 100):
        batch = message_ids[i:i + 100]
        try:
            await client.delete_messages(
                chat_id=message.chat.id,
                message_ids=batch,
                revoke=True # Deletes for everyone
            )
            deleted_count += len(batch)
            await asyncio.sleep(1) # Breathe to avoid flood limits
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except MessageDeleteForbidden:
            await status_msg.edit("I don't have the right permissions to delete messages here.")
            return
        except Exception:
            continue # Skip messages that might already be deleted or inaccessible

    # 4. Cleanup
    try:
        final_status = await message.reply(f"✅ Purge complete. {deleted_count} messages deleted.")
        await asyncio.sleep(3)
        await status_msg.delete()
        await final_status.delete()
    except Exception:
        pass
