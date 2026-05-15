import os
import logging
import random
import asyncio
import re
import json
import base64
from datetime import datetime, timedelta, date, time
import pytz

from Script import script

from pyrogram import Client, filters, enums
from pyrogram.errors import ChatAdminRequired, FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.ia_filterdb import Media, get_file_details, unpack_new_file_id
from database.users_chats_db import db
from database.connections_mdb import active_connection

from info import (
    CHANNELS, ADMINS, AUTH_CHANNEL, UPDATE_CHANNEL,
    SUPPORT_CHAT, LOG_CHANNEL, PICS,
    BATCH_FILE_CAPTION, CUSTOM_FILE_CAPTION,
    PROTECT_CONTENT, IS_VERIFY, HOW_TO_VERIFY
)

from utils import (
    add_new_user, get_settings, get_size, is_subscribed,
    save_group_settings, temp, verify_user, check_token,
    check_verification, get_token, get_verify_status
)

logger = logging.getLogger(__name__)

# Standard regex for link detection
LINK_PATTERN = r"(https?://|t\.me/|telegram\.me/|telegram\.dog/|www\.)\S+"



BATCH_FILES = {}

@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    if not await db.is_user_exist(message.from_user.id):
        await add_new_user(client, message.from_user)
    if len(message.command) != 2:
        buttons = [[
            InlineKeyboardButton('➕ Add Me To Your Groups ➕', url=f'http://t.me/{temp.U_NAME}?startgroup=true')
        ],[
            InlineKeyboardButton('ℹ️ Help', callback_data='help'),
            InlineKeyboardButton('😊 About', callback_data='about')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_photo(
            photo=random.choice(PICS),
            caption=script.START_TXT.format(message.from_user.mention, temp.U_NAME, temp.B_NAME),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return
    # Optimized start function snippet
    if AUTH_CHANNEL and not await is_subscribed(client, message):
        try:
            # Convert AUTH_CHANNEL to int if possible, else keep as string/username
            channel_id = int(AUTH_CHANNEL) if str(AUTH_CHANNEL).replace("-", "").isdigit() else AUTH_CHANNEL
            invite_link_obj = await client.create_chat_invite_link(channel_id)
            invite_link = invite_link_obj.invite_link
        except ChatAdminRequired:
            logger.error("❌ CRITICAL: Bot must be Admin in the ForceSub channel!")
            return
        except Exception as e:
            logger.error(f"Error creating invite link: {e}")
            return
    
        # Professional Button Layout
        btn = [
            [
                InlineKeyboardButton("🎁 Jᴏɪɴ & Gᴇᴛ 1 Mᴏɴᴛʜ Fʀᴇᴇ", url=invite_link)
            ]
        ]
    
        # Dynamic "Try Again" / Verification Logic
        if len(message.command) > 1:
            try:
                # Handling file-specific data
                data = message.command[1]
                pre = 'checksubp' if data.startswith('filep_') else 'checksub'
                file_id = data.split("_", 1)[1] if "_" in data else data
                
                btn.append([InlineKeyboardButton("✅ Cʟᴀɪᴍ Aᴄᴄᴇss", callback_data=f"{pre}#{file_id}")])
            except Exception:
                btn.append([InlineKeyboardButton("🔄 Tʀʏ Aɢᴀɪɴ", url=f"https://t.me/{temp.U_NAME}?start={message.command[1]}")])
        else:
            # Standard verification if no file is linked
            btn.append([InlineKeyboardButton("✅ Cʟᴀɪᴍ Aᴄᴄᴇss", callback_data="checksub_start")])
    # Sending the message
        try:
            await client.send_message(
                chat_id=message.from_user.id,
                text=script.FORCE_SUB_TEXT,
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
            return
        except Exception as e:
            logger.error(f"Force Sub Display Error: {e}")
            # Secondary fallback to hardcoded script text
            await client.send_message(
                chat_id=message.from_user.id,
                text="⚠️ **Join our channel to continue using this bot.**",
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
    
    if len(message.command) == 2 and message.command[1] in ["subscribe", "error", "okay", "help"]:
        buttons = [[
            InlineKeyboardButton('➕ Add Me To Your Groups ➕', url=f'http://t.me/{temp.U_NAME}?startgroup=true')
            ],[
            InlineKeyboardButton('ℹ️ Help', callback_data='help'),
            InlineKeyboardButton('😊 About', callback_data='about')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await message.reply_photo(
            photo=random.choice(PICS),
            caption=script.START_TXT.format(message.from_user.mention, temp.U_NAME, temp.B_NAME),
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return
    data = message.command[1]
    try:
        pre, file_id = data.split('_', 1)
    except:
        file_id = data
        pre = ""
    if data.split("-", 1)[0] == "BATCH":
        sts = await message.reply("Please wait")
        file_id = data.split("-", 1)[1]
        msgs = BATCH_FILES.get(file_id)
        if not msgs:
            file = await client.download_media(file_id)
            try: 
                with open(file) as file_data:
                    msgs=json.loads(file_data.read())
            except:
                await sts.edit("FAILED")
                return await client.send_message(LOG_CHANNEL, "UNABLE TO OPEN FILE.")
            os.remove(file)
            BATCH_FILES[file_id] = msgs
        for msg in msgs:
            title = msg.get("title")
            size=get_size(int(msg.get("size", 0)))
            f_caption=msg.get("caption", "")
            if BATCH_FILE_CAPTION:
                try:
                    f_caption=BATCH_FILE_CAPTION.format(file_name= '' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
                except Exception as e:
                    logger.exception(e)
                    f_caption=f_caption
            if f_caption is None:
                f_caption = f"{title}"
            try:
                await client.send_cached_media(
                    chat_id=message.from_user.id,
                    file_id=msg.get("file_id"),
                    caption=f_caption,
                    protect_content=msg.get('protect', False),
                )
            except FloodWait as e:
                await asyncio.sleep(e.x)
                logger.warning(f"Floodwait of {e.x} sec.")
                await client.send_cached_media(
                    chat_id=message.from_user.id,
                    file_id=msg.get("file_id"),
                    caption=f_caption,
                    protect_content=msg.get('protect', False),
                )
            except Exception as e:
                logger.warning(e, exc_info=True)
                continue
            await asyncio.sleep(1) 
        await sts.delete()
        return
    elif data.split("-", 1)[0] == "DSTORE":
        sts = await message.reply("Please wait")
        b_string = data.split("-", 1)[1]
        decoded = (base64.urlsafe_b64decode(b_string + "=" * (-len(b_string) % 4))).decode("ascii")
        try:
            f_msg_id, l_msg_id, f_chat_id, protect = decoded.split("_", 3)
        except:
            f_msg_id, l_msg_id, f_chat_id = decoded.split("_", 2)
            protect = "/pbatch" if PROTECT_CONTENT else "batch"
        diff = int(l_msg_id) - int(f_msg_id)
        async for msg in client.iter_messages(int(f_chat_id), int(l_msg_id), int(f_msg_id)):
            if msg.media:
                media = getattr(msg, msg.media)
                if BATCH_FILE_CAPTION:
                    try:
                        f_caption=BATCH_FILE_CAPTION.format(file_name=getattr(media, 'file_name', ''), file_size=getattr(media, 'file_size', ''), file_caption=getattr(msg, 'caption', ''))
                    except Exception as e:
                        logger.exception(e)
                        f_caption = getattr(msg, 'caption', '')
                else:
                    media = getattr(msg, msg.media)
                    file_name = getattr(media, 'file_name', '')
                    f_caption = getattr(msg, 'caption', file_name)
                try:
                    await msg.copy(message.chat.id, caption=f_caption, protect_content=True if protect == "/pbatch" else False)
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    await msg.copy(message.chat.id, caption=f_caption, protect_content=True if protect == "/pbatch" else False)
                except Exception as e:
                    logger.exception(e)
                    continue
            elif msg.empty:
                continue
            else:
                try:
                    await msg.copy(message.chat.id, protect_content=True if protect == "/pbatch" else False)
                except FloodWait as e:
                    await asyncio.sleep(e.x)
                    await msg.copy(message.chat.id, protect_content=True if protect == "/pbatch" else False)
                except Exception as e:
                    logger.exception(e)
                    continue
            await asyncio.sleep(1) 
        return await sts.delete()

    elif data.split("-", 1)[0] == "verify":
        userid = data.split("-", 2)[1]
        token = data.split("-", 3)[2]
        fileid = data.split("-", 3)[3]
        if str(message.from_user.id) != str(userid):
            return await message.reply_text(
                text="<b>Invalid or Expired Link!</b>",
                protect_content=True if PROTECT_CONTENT else False
            )
        is_valid = await check_token(client, userid, token)
        if is_valid:
            await message.reply_text(
                text=script.VERIFY_SUC.format(a=message.from_user.mention),
                protect_content=True if PROTECT_CONTENT else False,
                reply_markup=InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton("Other Bots", url='https://t.me/BraveBots/6')
                    ]]
                )
            )
            await verify_user(client, userid, token)
            return
        else:
            return await message.reply_text(
                text="<b>Invalid or Expired Link!</b>",
                protect_content=True if PROTECT_CONTENT else False
            )
            
    if IS_VERIFY and not await check_verification(client, message.from_user.id):
        kk, file_id = message.command[1].split("_", 1)
        btn = [[
            InlineKeyboardButton(f"Verify", url=await get_token(client, message.from_user.id, f"https://telegram.me/{temp.U_NAME}?start=", file_id)),
            InlineKeyboardButton("How To Verify", url=HOW_TO_VERIFY)
        ]]
        await client.send_message(
            chat_id=message.from_user.id,
            text=script.VERIFY_MSG.format(a=message.from_user.mention),
            protect_content=True if kk == 'checksubp' else False,
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(btn)
        )
        return 
    files_ = await get_file_details(file_id)           
    if not files_:
        pre, file_id = ((base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))).decode("ascii")).split("_", 1)
        try:
            msg = await client.send_cached_media(
                chat_id=message.from_user.id,
                file_id=file_id,
                protect_content=True if pre == 'filep' else False,
            )
            filetype = msg.media
            file = getattr(msg, filetype)
            title = file.file_name
            size=get_size(file.file_size)
            f_caption = f"<code>{title}</code>"
            if CUSTOM_FILE_CAPTION:
                try:
                    f_caption=CUSTOM_FILE_CAPTION.format(file_name= '' if title is None else title, file_size='' if size is None else size, file_caption='')
                except:
                    return
            await msg.edit_caption(f_caption)
            return
        except:
            pass
        return await message.reply('No such file exist.')
    files = files_[0]
    title = files.file_name
    size=get_size(files.file_size)
    f_caption=files.caption
    if CUSTOM_FILE_CAPTION:
        try:
            f_caption=CUSTOM_FILE_CAPTION.format(file_name= '' if title is None else title, file_size='' if size is None else size, file_caption='' if f_caption is None else f_caption)
        except Exception as e:
            logger.exception(e)
            f_caption=f_caption
    if f_caption is None:
        f_caption = f"{files.file_name}"
    await client.send_cached_media(
        chat_id=message.from_user.id,
        file_id=file_id,
        caption=f_caption,
        protect_content=True if pre == 'filep' else False,
                )
                    
@Client.on_message(filters.command("verification") & filters.private)
async def verification(client, message):
    userid = message.from_user.id

    verify_status = await get_verify_status(userid)
    last_short = verify_status["short"]
    expire_date = verify_status["date"]
    expire_time = verify_status["time"]
    
    if await check_verification(client, userid):
        text = "Status: Verified ☑\n\n"
        text += f"Verified Short: {last_short}\n"
        text += f"Expire Date: {expire_date}\n"
        text += f"Expire Time: {expire_time}\n\n"
    else:
        text = "Status: Not Verified ❌\n"
        text += f"Expired Short: {last_short}\n"
        text += f"Expired on: {expire_date} {expire_time}"
    
    await message.reply_text(text)
    
    
@Client.on_message(filters.command('channel') & filters.user(ADMINS))
async def channel_info(bot, message):
    try:
        if isinstance(CHANNELS, (int, str)):
            channels = [CHANNELS]
        elif isinstance(CHANNELS, list):
            channels = CHANNELS
        else:
            raise ValueError("Unexpected type of CHANNELS")

        if not channels:
            await message.reply("No channels or groups found in CHANNELS variable.")
            return

        text = '📑 **Indexed channels/groups**\n'
        for channel in channels:
            chat = await bot.get_chat(channel)
            text += f'\n👥 **Title:** {chat.title or chat.first_name}'
            text += f'\n🆔 **ID:** {chat.id}'
            
            if chat.username:
                text += f'\n🌐 **Username:** @{chat.username}\n'
            else:
                invite_link = await bot.export_chat_invite_link(chat.id)
                text += f'\n🔗 **Invite:** {invite_link}\n'
                
        text += f'**Total:** {len(channels)}'

        if len(text) < 4096:
            await message.reply(text, disable_web_page_preview=True)
        else:
            file = 'Indexed_channels.txt'
            with open(file, 'w') as f:
                f.write(text)
            await message.reply_document(file, disable_web_page_preview=True)
            os.remove(file)
    except Exception as e:
        await message.reply(f"An error occurred: {str(e)}")


@Client.on_message(filters.command('logs') & filters.user(ADMINS))
async def log_file(bot, message):
    """Send log file"""
    try:
        await message.reply_document('TelegramBot.log')
    except Exception as e:
        await message.reply(str(e))


@Client.on_message(filters.command('delete') & filters.user(ADMINS))
async def delete(bot, message):
    """Delete file from database"""
    reply = message.reply_to_message
    if reply and reply.media:
        msg = await message.reply("Processing...⏳", quote=True)
    else:
        await message.reply('Reply to file with /delete which you want to delete', quote=True)
        return

    for file_type in ("document", "video", "audio"):
        media = getattr(reply, file_type, None)
        if media is not None:
            break
    else:
        await msg.edit('This is not supported file format')
        return
    
    file_id, file_ref = unpack_new_file_id(media.file_id)

    result = await Media.collection.delete_one({
        '_id': file_id,
    })
    if result.deleted_count:
        await msg.edit('File is successfully deleted from database')
    else:
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        result = await Media.collection.delete_many({
            'file_name': file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
            })
        if result.deleted_count:
            await msg.edit('File is successfully deleted from database')
        else:
            # files indexed before https://github.com/EvamariaTG/EvaMaria/commit/f3d2a1bcb155faf44178e5d7a685a1b533e714bf#diff-86b613edf1748372103e94cacff3b578b36b698ef9c16817bb98fe9ef22fb669R39 
            # have original file name.
            result = await Media.collection.delete_many({
                'file_name': media.file_name,
                'file_size': media.file_size,
                'mime_type': media.mime_type
            })
            if result.deleted_count:
                await msg.edit('File is successfully deleted from database')
            else:
                await msg.edit('File not found in database')


        
