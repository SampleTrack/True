from pyrogram import Client, filters
import time
import asyncio
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users_chats_db import db
from info import ADMINS
from utils import temp

lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^broadcast_cancel'))
async def broadcast_cancel(bot, query):
    _, ident = query.data.split("#")
    if ident == 'users':
        await query.message.edit("Trying to cancel users broadcasting...")
        temp.USERS_CANCEL = True
    elif ident == 'groups':
        await query.message.edit("Trying to cancel groups broadcasting...")
        temp.GROUPS_CANCEL = True

@Client.on_message(filters.command(["broadcast", "pinbroadcast"]) & filters.user(ADMINS) & filters.reply)
async def users_broadcast(bot, message):
    if lock.locked():
        return await message.reply('Currently broadcasting is in progress. Please wait until it is completed.')
    
    pin = message.command[0] == 'pinbroadcast'
    users = await db.get_all_users()
    b_msg = message.reply_to_message
    b_sts = await message.reply_text(text='Broadcasting your message to users...')
    start_time = time.time()
    total_users = await db.total_users_count()
    done, failed, success = 0, 0, 0
    # FIX: initialise time_taken so final edit works even if cursor is empty
    time_taken = "0s"

    async with lock:
        async for user in users:
            time_taken = get_readable_time(time.time() - start_time)
            if temp.USERS_CANCEL:
                temp.USERS_CANCEL = False
                await b_sts.edit(f"Users broadcast cancelled!\nCompleted in {time_taken}\n\nTotal Users: <code>{total_users}</code>\nCompleted: <code>{done} / {total_users}</code>\nSuccess: <code>{success}</code>")
                return
            
            sts = await broadcast_messages(int(user['id']), b_msg, pin)
            if sts == 'Success':
                success += 1
            else:
                failed += 1
            done += 1
            
            if done % 20 == 0:
                btn = [[InlineKeyboardButton('CANCEL', callback_data='broadcast_cancel#users')]]
                await b_sts.edit(f"Users broadcast in progress...\n\nTotal Users: <code>{total_users}</code>\nCompleted: <code>{done} / {total_users}</code>\nSuccess: <code>{success}</code>", reply_markup=InlineKeyboardMarkup(btn))
        
        await b_sts.edit(f"Users broadcast completed.\nCompleted in {time_taken}\n\nTotal Users: <code>{total_users}</code>\nCompleted: <code>{done} / {total_users}</code>\nSuccess: <code>{success}</code>")

@Client.on_message(filters.command(["grp_broadcast", "pin_grp_broadcast"]) & filters.user(ADMINS) & filters.reply)
async def groups_broadcast(bot, message):
    if lock.locked():
        return await message.reply('Currently broadcasting is in progress. Please wait until it is completed.')
    
    pin = message.command[0] == 'pin_grp_broadcast'
    chats = await db.get_all_chats()
    b_msg = message.reply_to_message
    b_sts = await message.reply_text(text='Broadcasting your message to groups...')
    start_time = time.time()
    total_chats = await db.total_chat_count()
    done, failed, success = 0, 0, 0
    # FIX: initialise time_taken so final edit works even if cursor is empty
    time_taken = "0s"

    async with lock:
        async for chat in chats:
            time_taken = get_readable_time(time.time() - start_time)
            if temp.GROUPS_CANCEL:
                temp.GROUPS_CANCEL = False
                await b_sts.edit(f"Groups broadcast cancelled!\nCompleted in {time_taken}\n\nTotal Groups: <code>{total_chats}</code>\nCompleted: <code>{done} / {total_chats}</code>\nSuccess: <code>{success}</code>\nFailed: <code>{failed}</code>")
                return
            
            sts = await groups_broadcast_messages(int(chat['id']), b_msg, pin)
            if sts == 'Success':
                success += 1
            else:
                failed += 1
            done += 1
            
            if done % 20 == 0:
                btn = [[InlineKeyboardButton('CANCEL', callback_data='broadcast_cancel#groups')]]
                await b_sts.edit(f"Groups broadcast in progress...\n\nTotal Groups: <code>{total_chats}</code>\nCompleted: <code>{done} / {total_chats}</code>\nSuccess: <code>{success}</code>\nFailed: <code>{failed}</code>", reply_markup=InlineKeyboardMarkup(btn))
        
        await b_sts.edit(f"Groups broadcast completed.\nCompleted in {time_taken}\n\nTotal Groups: <code>{total_chats}</code>\nCompleted: <code>{done} / {total_chats}</code>\nSuccess: <code>{success}</code>\nFailed: <code>{failed}</code>")

async def broadcast_messages(user_id, message, pin):
    try:
        m = await message.copy(chat_id=user_id)
        if pin:
            await m.pin(both_sides=True)
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message, pin)
    except Exception:
        return "Error"

async def groups_broadcast_messages(chat_id, message, pin):
    try:
        k = await message.copy(chat_id=chat_id)
        if pin:
            try:
                await k.pin()
            except:
                pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await groups_broadcast_messages(chat_id, message, pin)
    except Exception:
        return "Error"

def get_readable_time(seconds):
    periods = [('d', 86400), ('h', 3600), ('m', 60), ('s', 1)]
    result = ''
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f'{int(period_value)}{period_name}'
    return result or '0s'
