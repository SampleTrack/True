import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, MessageDeleteForbidden
from info import ADMINS

@Client.on_message(filters.command("purgeall") & filters.group)
async def manual_purge_all(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Strict Authorization: Only the Group Owner or Bot Admins should have this power.
    # Allowing standard admins to nuke the whole group is a massive security risk.
    st = await client.get_chat_member(chat_id, user_id)
    if st.status != enums.ChatMemberStatus.OWNER and user_id not in ADMINS:
        return await message.reply("❌ Permission Denied: Only the Group Owner or Bot Admins can use this nuclear option.")

    latest_msg_id = message.id
    
    # Acknowledge the command immediately
    status_msg = await message.reply(
        f"⚠️ **MASS PURGE INITIATED**\n\n"
        f"Target: ID `1` to `{latest_msg_id}`\n"
        f"This is running in the background. It will take a significant amount of time due to API limits. Expect delays."
    )

    # Push the heavy lifting to the background
    asyncio.create_task(execute_mass_purge(client, chat_id, latest_msg_id, status_msg))

async def execute_mass_purge(client, chat_id, latest_msg_id, status_msg):
    # Telegram allows a maximum of 100 message IDs per deletion call
    chunk_size = 100
    
    for start_id in range(1, latest_msg_id + 1, chunk_size):
        # Create a list of 100 IDs to delete simultaneously
        end_id = min(start_id + chunk_size, latest_msg_id + 1)
        message_ids_to_delete = list(range(start_id, end_id))
        
        try:
            await client.delete_messages(chat_id, message_ids_to_delete, revoke=True)
            # Mandatory sleep to prevent instant API throttling
            await asyncio.sleep(1.5)
            
        except FloodWait as e:
            # If Telegram limits the bot, respect the timeout exactly
            await asyncio.sleep(e.value)
            try:
                await client.delete_messages(chat_id, message_ids_to_delete, revoke=True)
            except Exception:
                pass # Move on if it fails again
                
        except MessageDeleteForbidden:
            # Stop the loop if the bot suddenly loses admin rights
            try:
                await status_msg.edit("❌ **Purge Halted:** Bot lacks admin rights to delete messages.")
            except Exception:
                pass
            return
            
        except Exception:
            # Ignore random exceptions (e.g., all 100 messages were already deleted)
            pass

    # Update the status when completely finished
    try:
        await status_msg.edit(f"✅ **MASS PURGE COMPLETE**\nProcessed all IDs up to `{latest_msg_id}`.")
    except Exception:
        pass
        
