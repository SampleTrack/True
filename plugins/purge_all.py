import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, MessageDeleteForbidden

@Client.on_message(filters.command("purgeall") & filters.group)
async def manual_purge_all(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # 1. Authority Check
    member = await client.get_chat_member(chat_id, user_id)
    if member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
        return await message.reply("❌ Only Admins can nuke the chat.")

    status_msg = await message.reply("💣 **Mass Purge Started...**\nFetching actual messages to avoid API errors.")

    # 2. Start the background task properly
    asyncio.create_task(execute_smart_purge(client, chat_id, status_msg))

async def execute_smart_purge(client, chat_id, status_msg):
    messages_to_delete = []
    count = 0

    try:
        # Fetch ONLY messages that actually exist
        async for msg in client.get_chat_history(chat_id):
            messages_to_delete.append(msg.id)
            count += 1

            # Delete in chunks of 100 (Telegram Limit)
            if len(messages_to_delete) == 100:
                try:
                    await client.delete_messages(chat_id, messages_to_delete)
                    messages_to_delete = []
                    await asyncio.sleep(1.5) # Prevent FloodWait
                except MessageDeleteForbidden:
                    await status_msg.edit("❌ **Error:** I don't have 'Delete Messages' permission!")
                    return
                except FloodWait as e:
                    await asyncio.sleep(e.value)

        # Delete any remaining messages
        if messages_to_delete:
            await client.delete_messages(chat_id, messages_to_delete)

        await status_msg.edit(f"✅ **Purge Complete!**\nCleaned `{count}` messages.")

    except Exception as e:
        print(f"Purge Error: {e}")
        await status_msg.edit("❌ **Purge Failed:** Unknown error occurred.")
