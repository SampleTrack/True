import logging
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
)
from info import ADMINS
from info import INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()


@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    logger.info(f"Index callback received: {query.data} from {query.from_user.id}")

    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing")

    # ✅ Validate callback data parts
    parts = query.data.split("#")
    if len(parts) != 5:
        logger.error(f"Invalid callback data format: {query.data}")
        return await query.answer("Invalid callback data. Please try again.", show_alert=True)

    _, raju, chat, lst_msg_id, from_user = parts

    if raju == 'reject':
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f'Your Submission for indexing {chat} has been declined by our moderators.',
            reply_to_message_id=int(lst_msg_id)
        )
        return

    if lock.locked():
        return await query.answer('Wait until previous process completes.', show_alert=True)

    msg = query.message
    await query.answer('Processing...⏳', show_alert=True)

    if int(from_user) not in ADMINS:
        await bot.send_message(
            int(from_user),
            f'Your Submission for indexing {chat} has been accepted by our moderators and will be added soon.',
            reply_to_message_id=int(lst_msg_id)
        )

    await msg.edit(
        "Starting Indexing",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton('Cancel', callback_data='index_cancel')]]
        )
    )

    # ✅ Safely convert chat and lst_msg_id
    try:
        chat = int(chat)
    except ValueError:
        pass  # keep as string username

    try:
        lst_msg_id = int(lst_msg_id)
    except ValueError:
        logger.error(f"Invalid lst_msg_id: {lst_msg_id}")
        return await msg.edit("❌ Error: Invalid message ID in callback data.")

    # ✅ Wrapped with proper error handling
    try:
        await index_files_to_db(lst_msg_id, chat, msg, bot)
    except Exception as e:
        logger.exception(f"Fatal error during indexing: {e}")
        await msg.edit(f"❌ Fatal Error: {e}")


@Client.on_message((filters.forwarded | (filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")) & filters.text ) & filters.private & filters.incoming)
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
        match = regex.match(message.text)
        if not match:
            return await message.reply('Invalid link')
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
        return await message.reply('Invalid Link specified.')
    except Exception as e:
        logger.exception(e)
        return await message.reply(f'Error: {e}')

    try:
        k = await bot.get_messages(chat_id, last_msg_id)
    except Exception as e:
        return await message.reply(f'Make sure I am an admin in the channel. Error: {e}')

    if k.empty:
        return await message.reply('This may be a group and I am not an admin of the group.')

    if message.from_user.id in ADMINS:
        buttons = [
            [InlineKeyboardButton(
                'Yes ✅',
                callback_data=f'index#accept#{str(chat_id)}#{last_msg_id}#{message.from_user.id}'
            )],
            [InlineKeyboardButton('Close ❌', callback_data='close_data')]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        return await message.reply(
            f'Do you want to index this channel/group?\n\n'
            f'Chat ID/Username: <code>{chat_id}</code>\n'
            f'Last Message ID: <code>{last_msg_id}</code>',
            reply_markup=reply_markup
        )

    if type(chat_id) is int:
        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            return await message.reply('Make sure I am an admin with permission to invite users.')
    else:
        link = f"@{chat_id}"

    buttons = [
        [InlineKeyboardButton(
            'Accept Index ✅',
            callback_data=f'index#accept#{str(chat_id)}#{last_msg_id}#{message.from_user.id}'
        )],
        [InlineKeyboardButton(
            'Reject Index ❌',
            callback_data=f'index#reject#{str(chat_id)}#{message.id}#{message.from_user.id}'
        )]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await bot.send_message(
        LOG_CHANNEL,
        f'#IndexRequest\n\nBy: {message.from_user.mention} (<code>{message.from_user.id}</code>)\n'
        f'Chat ID/Username: <code>{chat_id}</code>\n'
        f'Last Message ID: <code>{last_msg_id}</code>\n'
        f'Invite Link: {link}',
        reply_markup=reply_markup
    )
    await message.reply('Thank you for the contribution! Wait for our moderators to verify the files.')


@Client.on_message(filters.command('setskip') & filters.user(ADMINS))
async def set_skip_number(bot, message):
    if ' ' in message.text:
        _, skip = message.text.split(" ", 1)
        try:
            skip = int(skip)
        except ValueError:
            return await message.reply("Skip number must be an integer.")
        temp.CURRENT = skip
        await message.reply(f"✅ Successfully set SKIP number to {skip}")
    else:
        await message.reply("Please provide a skip number. Example: /setskip 100")


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0

    # ✅ Lock with timeout to prevent permanent deadlock
    try:
        async with asyncio.timeout(3600):  # 1 hour max timeout
            async with lock:
                try:
                    current = temp.CURRENT
                    temp.CANCEL = False

                    async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                        if temp.CANCEL:
                            await msg.edit(
                                f"✅ Successfully Cancelled!\n\n"
                                f"Saved: <code>{total_files}</code> files\n"
                                f"Duplicate Skipped: <code>{duplicate}</code>\n"
                                f"Deleted Skipped: <code>{deleted}</code>\n"
                                f"Non-Media Skipped: <code>{no_media + unsupported}</code> "
                                f"(Unsupported: <code>{unsupported}</code>)\n"
                                f"Errors: <code>{errors}</code>"
                            )
                            break

                        current += 1

                        if current % 20 == 0:
                            try:
                                await msg.edit_text(
                                    text=(
                                        f"⏳ Indexing in progress...\n\n"
                                        f"Messages Fetched: <code>{current}</code>\n"
                                        f"Files Saved: <code>{total_files}</code>\n"
                                        f"Duplicate Skipped: <code>{duplicate}</code>\n"
                                        f"Deleted Skipped: <code>{deleted}</code>\n"
                                        f"Non-Media Skipped: <code>{no_media + unsupported}</code> "
                                        f"(Unsupported: <code>{unsupported}</code>)\n"
                                        f"Errors: <code>{errors}</code>"
                                    ),
                                    reply_markup=InlineKeyboardMarkup(
                                        [[InlineKeyboardButton('Cancel ❌', callback_data='index_cancel')]]
                                    )
                                )
                            except FloodWait as fw:
                                logger.warning(f"FloodWait: sleeping {fw.value}s")
                                await asyncio.sleep(fw.value)

                        if message.empty:
                            deleted += 1
                            continue
                        elif not message.media:
                            no_media += 1
                            continue
                        elif message.media not in [
                            enums.MessageMediaType.VIDEO,
                            enums.MessageMediaType.AUDIO,
                            enums.MessageMediaType.DOCUMENT
                        ]:
                            unsupported += 1
                            continue

                        media = getattr(message, message.media.value, None)
                        if not media:
                            unsupported += 1
                            continue

                        media.file_type = message.media.value
                        media.caption = message.caption

                        aynav, vnay = await save_file(media)
                        if aynav:
                            total_files += 1
                        elif vnay == 0:
                            duplicate += 1
                        elif vnay == 2:
                            errors += 1

                except Exception as e:
                    logger.exception(f"Error during indexing loop: {e}")
                    await msg.edit(f"❌ Error during indexing: {e}")
                    return

                await msg.edit(
                    f"✅ Indexing Complete!\n\n"
                    f"Files Saved: <code>{total_files}</code>\n"
                    f"Duplicate Skipped: <code>{duplicate}</code>\n"
                    f"Deleted Skipped: <code>{deleted}</code>\n"
                    f"Non-Media Skipped: <code>{no_media + unsupported}</code> "
                    f"(Unsupported: <code>{unsupported}</code>)\n"
                    f"Errors: <code>{errors}</code>"
                )

    except asyncio.TimeoutError:
        logger.error("Indexing timed out after 1 hour.")
        await msg.edit("❌ Indexing timed out after 1 hour. Please try again with fewer messages.")
        
