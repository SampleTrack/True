import logging
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from utils import temp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()

TELEGRAM_LINK_REGEX = re.compile(
    r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
)
SUPPORTED_MEDIA = {enums.MessageMediaType.VIDEO, enums.MessageMediaType.AUDIO, enums.MessageMediaType.DOCUMENT}


@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing")
    _, action, chat, lst_msg_id, from_user = query.data.split("#")
    if action == 'reject':
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f'Your submission for indexing {chat} has been declined by our moderators.',
            reply_to_message_id=int(lst_msg_id)
        )
        return
    if lock.locked():
        return await query.answer('Wait until the previous process completes.', show_alert=True)
    await query.answer('Processing...⏳', show_alert=True)
    if int(from_user) not in ADMINS:
        await bot.send_message(
            int(from_user),
            f'Your submission for indexing {chat} has been accepted by our moderators and will be added soon.',
            reply_to_message_id=int(lst_msg_id)
        )
    await query.message.edit(
        "Starting Indexing",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
    )
    try:
        chat = int(chat)
    except ValueError:
        pass
    await index_files_to_db(int(lst_msg_id), chat, query.message, bot)


@Client.on_message(
    (filters.forwarded | (filters.regex(TELEGRAM_LINK_REGEX) & filters.text)) &
    filters.private & filters.incoming
)
async def send_for_index(bot, message):
    chat_id = None
    last_msg_id = None
    if message.text:
        match = TELEGRAM_LINK_REGEX.match(message.text)
        if not match:
            return await message.reply('Invalid link.')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return
    try:
        await bot.get_chat(chat_id)
    except ChannelInvalid:
        return await message.reply('This may be a private channel/group. Make me an admin there to index files.')
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply('Invalid link specified.')
    except Exception as e:
        logger.exception(e)
        return await message.reply(f'Error: {e}')
    try:
        k = await bot.get_messages(chat_id, last_msg_id)
    except Exception:
        return await message.reply('Make sure I am an admin in the channel if it is private.')
    if k.empty:
        return await message.reply('This may be a group and I am not an admin of the group.')
    if message.from_user.id in ADMINS:
        buttons = [
            [InlineKeyboardButton('Yes', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
            [InlineKeyboardButton('Close', callback_data='close_data')]
        ]
        return await message.reply(
            f'Do you want to index this channel/group?\n\nChat ID/Username: <code>{chat_id}</code>\nLast Message ID: <code>{last_msg_id}</code>',
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    if isinstance(chat_id, int):
        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            return await message.reply('Make sure I am an admin with permission to invite users.')
    else:
        link = f"@{message.forward_from_chat.username}"
    buttons = [
        [InlineKeyboardButton('Accept Index', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')],
        [InlineKeyboardButton('Reject Index', callback_data=f'index#reject#{chat_id}#{message.id}#{message.from_user.id}')]
    ]
    await bot.send_message(
        LOG_CHANNEL,
        f'#IndexRequest\n\nBy: {message.from_user.mention} (<code>{message.from_user.id}</code>)\n'
        f'Chat ID/Username: <code>{chat_id}</code>\nLast Message ID: <code>{last_msg_id}</code>\nInvite Link: {link}',
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    await message.reply('Thank you for the contribution! Wait for our moderators to verify the files.')


@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    parts = message.text.split(" ", 1)
    if len(parts) < 2:
        return await message.reply("Please provide a skip number.")
    try:
        skip = int(parts[1])
    except ValueError:
        return await message.reply("Skip number must be an integer.")
    temp.CURRENT = skip
    await message.reply(f"Successfully set SKIP number to {skip}.")


def _build_status_text(current, total_files, caption_updated, duplicate, deleted, no_media, unsupported, errors):
    return (
        f"Messages fetched: <code>{current}</code>\n"
        f"Files saved: <code>{total_files}</code>\n"
        f"Caption updated: <code>{caption_updated}</code>\n"
        f"Duplicates skipped: <code>{duplicate}</code>\n"
        f"Deleted messages skipped: <code>{deleted}</code>\n"
        f"Non-media skipped: <code>{no_media + unsupported}</code> "
        f"(Unsupported: <code>{unsupported}</code>)\n"
        f"Errors: <code>{errors}</code>"
    )


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = duplicate = errors = deleted = no_media = unsupported = caption_updated = 0
    cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Cancel', callback_data='index_cancel')]])
    async with lock:
        try:
            current = temp.CURRENT
            temp.CANCEL = False
            async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                if temp.CANCEL:
                    await msg.edit(
                        "Indexing cancelled!\n\n" +
                        _build_status_text(current, total_files, caption_updated, duplicate, deleted, no_media, unsupported, errors)
                    )
                    return
                current += 1
                if current % 20 == 0:
                    await msg.edit_text(
                        _build_status_text(current, total_files, caption_updated, duplicate, deleted, no_media, unsupported, errors),
                        reply_markup=cancel_markup
                    )
                if message.empty:
                    deleted += 1
                    continue
                if not message.media:
                    no_media += 1
                    continue
                if message.media not in SUPPORTED_MEDIA:
                    unsupported += 1
                    continue
                media = getattr(message, message.media.value, None)
                if not media:
                    unsupported += 1
                    continue
                media.file_type = message.media.value
                media.caption = message.caption
                saved, status = await save_file(media)
                if status == 1:
                    total_files += 1
                elif status == 3:
                    caption_updated += 1
                elif status == 0:
                    duplicate += 1
                elif status == 2:
                    errors += 1
        except Exception as e:
            logger.exception(e)
            await msg.edit(f'Error: {e}')
        else:
            await msg.edit(
                "Indexing complete!\n\n" +
                _build_status_text(current, total_files, caption_updated, duplicate, deleted, no_media, unsupported, errors)
    )
            
