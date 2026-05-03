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


# ✅ DEBUG: Catches ALL callback queries - remove after fixing
@Client.on_callback_query()
async def debug_all_callbacks(bot, query):
    print(f"🔍 RAW CALLBACK DATA: '{query.data}'")
    logger.info(f"🔍 RAW CALLBACK DATA: '{query.data}'")


@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    print(f"✅ INDEX CALLBACK TRIGGERED: '{query.data}'")
    logger.info(f"✅ INDEX CALLBACK TRIGGERED: '{query.data}'")

    try:
        await query.answer("Received! Processing...", show_alert=True)
    except Exception as e:
        print(f"❌ query.answer failed: {e}")

    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return

    parts = query.data.split("#")
    print(f"📦 Parts: {parts} | Length: {len(parts)}")

    if len(parts) != 5:
        print(f"❌ Invalid parts length: {len(parts)}")
        try:
            await query.message.edit(f"❌ Invalid callback data: <code>{query.data}</code>")
        except Exception as e:
            print(f"❌ msg.edit failed: {e}")
        return

    _, raju, chat, lst_msg_id, from_user = parts
    print(f"📋 raju={raju} | chat={chat} | lst_msg_id={lst_msg_id} | from_user={from_user}")

    if raju == 'reject':
        try:
            await query.message.delete()
            await bot.send_message(
                int(from_user),
                f'Your Submission for indexing {chat} has been declined by our moderators.'
            )
        except Exception as e:
            print(f"❌ Reject error: {e}")
        return

    print(f"🔒 Lock status: {lock.locked()}")
    if lock.locked():
        return await query.answer('Wait until previous process completes.', show_alert=True)

    msg = query.message

    try:
        if int(from_user) not in ADMINS:
            await bot.send_message(
                int(from_user),
                f'Your Submission for indexing {chat} has been accepted by our moderators and will be added soon.'
            )
    except Exception as e:
        print(f"❌ Send message to user error: {e}")

    try:
        await msg.edit(
            "⏳ Starting Indexing...",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton('Cancel ❌', callback_data='index_cancel')]]
            )
        )
        print("✅ msg.edit successful")
    except Exception as e:
        print(f"❌ msg.edit failed: {e}")

    try:
        chat = int(chat)
        print(f"✅ chat converted to int: {chat}")
    except ValueError:
        print(f"ℹ️ chat kept as string: {chat}")

    try:
        lst_msg_id = int(lst_msg_id)
        print(f"✅ lst_msg_id converted: {lst_msg_id}")
    except ValueError as e:
        print(f"❌ lst_msg_id conversion failed: {e}")
        return await msg.edit(f"❌ Invalid message ID: <code>{lst_msg_id}</code>")

    print(f"🚀 Calling index_files_to_db | chat={chat} | lst_msg_id={lst_msg_id}")
    try:
        await index_files_to_db(lst_msg_id, chat, msg, bot)
        print("✅ index_files_to_db completed successfully")
    except Exception as e:
        print(f"❌ index_files_to_db crashed: {e}")
        logger.exception(e)
        try:
            await msg.edit(f"❌ Fatal Error: {e}")
        except Exception as edit_err:
            print(f"❌ Could not edit error message: {edit_err}")


@Client.on_message(
    (filters.forwarded | (
        filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$")
    ) & filters.text) & filters.private & filters.incoming
)
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(
            r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
        )
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
        # ✅ DEBUG: Print button callback data before creating
        callback_str = f'index#accept#{str(chat_id)}#{last_msg_id}#{message.from_user.id}'
        print(f"🔘 ADMIN BUTTON CREATED WITH: '{callback_str}'")
        logger.info(f"🔘 ADMIN BUTTON CREATED WITH: '{callback_str}'")

        buttons = [
            [InlineKeyboardButton(
                'Yes ✅',
                callback_data=callback_str
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

    # ✅ DEBUG: Print button callback data before creating
    callback_str = f'index#accept#{str(chat_id)}#{last_msg_id}#{message.from_user.id}'
    print(f"🔘 MOD BUTTON CREATED WITH: '{callback_str}'")
    logger.info(f"🔘 MOD BUTTON CREATED WITH: '{callback_str}'")

    buttons = [
        [InlineKeyboardButton(
            'Accept Index ✅',
            callback_data=callback_str
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

    print(f"📂 index_files_to_db started | chat={chat} | lst_msg_id={lst_msg_id}")

    try:
        async with asyncio.timeout(3600):
            async with lock:
                print("🔒 Lock acquired, starting iteration...")
                try:
                    current = temp.CURRENT
                    temp.CANCEL = False

                    async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
                        if temp.CANCEL:
                            await msg.edit(
                                f"✅ Cancelled!\n\n"
                                f"Files Saved: <code>{total_files}</code>\n"
                                f"Duplicates Skipped: <code>{duplicate}</code>\n"
                                f"Deleted Skipped: <code>{deleted}</code>\n"
                                f"Non-Media Skipped: <code>{no_media + unsupported}</code> "
                                f"(Unsupported: <code>{unsupported}</code>)\n"
                                f"Errors: <code>{errors}</code>"
                            )
                            break

                        current += 1

                        if current % 20 == 0:
                            print(f"📊 Progress: {current} messages processed, {total_files} saved")
                            try:
                                await msg.edit_text(
                                    text=(
                                        f"⏳ Indexing in progress...\n\n"
                                        f"Messages Fetched: <code>{current}</code>\n"
                                        f"Files Saved: <code>{total_files}</code>\n"
                                        f"Duplicates Skipped: <code>{duplicate}</code>\n"
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
                                print(f"⏳ FloodWait: sleeping {fw.value}s")
                                await asyncio.sleep(fw.value)
                            except Exception as e:
                                print(f"❌ Progress edit error: {e}")

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
                    print(f"❌ Error inside lock: {e}")
                    logger.exception(e)
                    await msg.edit(f"❌ Error during indexing: <code>{e}</code>")
                    return

                print(f"✅ Indexing complete: {total_files} files saved")
                await msg.edit(
                    f"✅ Indexing Complete!\n\n"
                    f"Files Saved: <code>{total_files}</code>\n"
                    f"Duplicates Skipped: <code>{duplicate}</code>\n"
                    f"Deleted Skipped: <code>{deleted}</code>\n"
                    f"Non-Media Skipped: <code>{no_media + unsupported}</code> "
                    f"(Unsupported: <code>{unsupported}</code>)\n"
                    f"Errors: <code>{errors}</code>"
                )

    except asyncio.TimeoutError:
        print("❌ Indexing timed out after 1 hour")
        await msg.edit("❌ Indexing timed out after 1 hour. Please try with fewer messages.")
    except Exception as e:
        print(f"❌ Outer exception: {e}")
        logger.exception(e)
        await msg.edit(f"❌ Unexpected Error: <code>{e}</code>")
        
