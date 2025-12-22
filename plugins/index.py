import logging
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid,
    ChatAdminRequired,
    UsernameInvalid,
    UsernameNotModified,
)
from info import ADMINS
from info import INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Per-chat locking dictionary - prevents blocking all users
indexing_locks = {}


async def get_lock(chat_id):
    """Get or create an asyncio lock for a specific chat."""
    if chat_id not in indexing_locks:
        indexing_locks[chat_id] = asyncio.Lock()
    return indexing_locks[chat_id]


@Client.on_callback_query(filters.regex(r"^index"))
async def index_files(bot, query):
    """Handle index callback queries (accept/reject/cancel)."""
    if query.data.startswith("index_cancel"):
        temp.CANCEL = True
        return await query.answer("Cancelling Indexing")

    _, raju, chat, lst_msg_id, from_user = query.data.split("#")

    if raju == "reject":
        await query.message.delete()
        await bot.send_message(
            int(from_user),
            f"Your Submission for indexing {chat} has been declined by our moderators.",
            reply_to_message_id=int(lst_msg_id),
        )
        return

    # Get per-chat lock
    try:
        chat_int = int(chat)
    except ValueError:
        chat_int = chat

    chat_lock = await get_lock(chat_int)

    if chat_lock.locked():
        return await query.answer(
            "Wait until previous process complete.", show_alert=True
        )

    msg = query.message

    await query.answer("Processing...⏳", show_alert=True)

    if int(from_user) not in ADMINS:
        await bot.send_message(
            int(from_user),
            f"Your Submission for indexing {chat} has been accepted by our moderators and will be added soon.",
            reply_to_message_id=int(lst_msg_id),
        )

    await msg.edit(
        "Starting Indexing",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Cancel", callback_data="index_cancel")]]
        ),
    )

    # Normalize chat_id
    try:
        chat = int(chat)
    except ValueError:
        chat = chat

    await index_files_to_db(int(lst_msg_id), chat, msg, bot, start_from=0)


@Client.on_message(
    (
        filters.forwarded
        | (
            filters.regex(
                r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
            )
            & filters.text
        )
    )
    & filters.private
    & filters.incoming
)
async def send_for_index(bot, message):
    """Handle file indexing submission - process links and forward messages."""
    chat_id = None
    last_msg_id = None

    # Handle regex text link
    if message.text:
        regex = re.compile(
            r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
        )
        match = regex.match(message.text)
        if not match:
            return await message.reply("Invalid link")

        chat_id = match.group(4)
        last_msg_id = int(match.group(5))

        # Convert numeric IDs to proper format
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)

    # Handle forwarded message
    elif (
        message.forward_from_chat
        and message.forward_from_chat.type == enums.ChatType.CHANNEL
    ):
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return

    # Validate chat access
    try:
        await bot.get_chat(chat_id)
    except ChannelInvalid:
        return await message.reply(
            "This may be a private channel / group. Make me an admin over there to index the files."
        )
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply("Invalid Link specified.")
    except Exception as e:
        logger.exception(e)
        return await message.reply(f"Error - {e}")

    # Verify we can access the message
    try:
        k = await bot.get_messages(chat_id, last_msg_id)
    except Exception as e:
        logger.debug(f"Cannot access message: {e}")
        return await message.reply(
            "Make Sure That I am an Admin In The Channel, if channel is private"
        )

    if k.empty:
        return await message.reply("This may be a group and I am not an admin of the group.")

    # Admin bypass - direct indexing
    if message.from_user.id in ADMINS:
        buttons = [
            [
                InlineKeyboardButton(
                    "Yes",
                    callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}",
                )
            ],
            [
                InlineKeyboardButton("Close", callback_data="close_data"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        return await message.reply(
            f"Do you Want To Index This Channel/Group ?\n\nChat ID/Username: <code>{chat_id}</code>\nLast Message ID: <code>{last_msg_id}</code>",
            reply_markup=reply_markup,
        )

    # Get invite link for moderators
    if isinstance(chat_id, int):
        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            return await message.reply(
                "Make sure I am an admin in the chat and have permission to invite users."
            )
    else:
        link = f"t.me/{chat_id}" if message.forward_from_chat else f"@{chat_id}"

    # Send to moderators for approval
    buttons = [
        [
            InlineKeyboardButton(
                "Accept Index",
                callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}",
            )
        ],
        [
            InlineKeyboardButton(
                "Reject Index",
                callback_data=f"index#reject#{chat_id}#{message.id}#{message.from_user.id}",
            ),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await bot.send_message(
        LOG_CHANNEL,
        f"#IndexRequest\n\nBy : {message.from_user.mention} (<code>{message.from_user.id}</code>)\nChat ID/Username - <code>{chat_id}</code>\nLast Message ID - <code>{last_msg_id}</code>\nInvite Link - {link}",
        reply_markup=reply_markup,
    )
    await message.reply(
        "Thank you for the Contribution, wait for my Moderators to verify the files."
    )


@Client.on_message(filters.command("setskip") & filters.user(ADMINS))
async def set_skip_number(bot, message):
    """Set the starting message ID for indexing."""
    if " " in message.text:
        try:
            _, skip = message.text.split(" ", 1)
            skip = int(skip)
        except ValueError:
            return await message.reply("Skip number should be an integer.")

        temp.CURRENT = skip
        await message.reply(f"Successfully set SKIP number as {skip}")
    else:
        await message.reply("Give me a skip number")


async def index_files_to_db(lst_msg_id, chat, msg, bot, start_from=0):
    """
    Index files from a chat to the database.
    
    Args:
        lst_msg_id: Last message ID to start indexing from
        chat: Chat ID or username
        msg: Message object to update with progress
        bot: Pyrogram client
        start_from: Starting offset (default: 0)
    """
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    current = start_from

    # Get per-chat lock
    try:
        chat_int = int(chat)
    except (ValueError, TypeError):
        chat_int = chat

    chat_lock = await get_lock(chat_int)

    async with chat_lock:
        try:
            temp.CANCEL = False

            # Iterate messages from last_msg_id backwards
            async for message in bot.iter_messages(
                chat, offset_id=lst_msg_id, offset=start_from, reverse=False
            ):
                # Check cancellation flag
                if temp.CANCEL:
                    await msg.edit(
                        f"Successfully Cancelled!!\n\nSaved <code>{total_files}</code> files to database!\n"
                        f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
                        f"Deleted Messages Skipped: <code>{deleted}</code>\n"
                        f"Non-Media messages skipped: <code>{no_media + unsupported}</code> (Unsupported Media - <code>{unsupported}</code>)\n"
                        f"Errors Occurred: <code>{errors}</code>"
                    )
                    break

                current += 1

                # Update progress every 20 messages
                if current % 20 == 0:
                    can = [[InlineKeyboardButton("Cancel", callback_data="index_cancel")]]
                    reply = InlineKeyboardMarkup(can)
                    await msg.edit_text(
                        text=f"Total messages fetched: <code>{current}</code>\n"
                        f"Total messages saved: <code>{total_files}</code>\n"
                        f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
                        f"Deleted Messages Skipped: <code>{deleted}</code>\n"
                        f"Non-Media messages skipped: <code>{no_media + unsupported}</code> (Unsupported Media - <code>{unsupported}</code>)\n"
                        f"Errors Occurred: <code>{errors}</code>",
                        reply_markup=reply,
                    )

                # Skip empty messages
                if message.empty:
                    deleted += 1
                    continue

                # Skip non-media messages
                if not message.media:
                    no_media += 1
                    continue

                # Check if media type is supported
                if message.media not in [
                    enums.MessageMediaType.VIDEO,
                    enums.MessageMediaType.AUDIO,
                    enums.MessageMediaType.DOCUMENT,
                ]:
                    unsupported += 1
                    continue

                # Get media object
                media = getattr(message, message.media.name, None)
                if not media:
                    unsupported += 1
                    continue

                # Attach metadata
                media.file_type = message.media.name  # Use enum name instead of value
                media.caption = message.caption or ""

                # Save to database
                try:
                    success, result_code = await save_file(media)
                    if success:
                        total_files += 1
                    elif result_code == 0:
                        duplicate += 1
                    elif result_code == 2:
                        errors += 1
                except Exception as e:
                    logger.exception(f"Error saving file: {e}")
                    errors += 1

        except FloodWait as e:
            logger.warning(f"FloodWait: sleeping for {e.value} seconds")
            await msg.edit(
                f"FloodWait detected. Pausing for {e.value} seconds...\n\n"
                f"Current Progress:\n"
                f"Total messages fetched: <code>{current}</code>\n"
                f"Total files saved: <code>{total_files}</code>\n"
                f"Duplicate Files: <code>{duplicate}</code>"
            )
            await asyncio.sleep(e.value)
            # Resume indexing after flood wait
            await index_files_to_db(lst_msg_id, chat, msg, bot, start_from=current)
        except Exception as e:
            logger.exception(f"Indexing error: {e}")
            await msg.edit(
                f"Error during indexing: <code>{e}</code>\n\n"
                f"Partial Results:\n"
                f"Files saved: <code>{total_files}</code>\n"
                f"Duplicates: <code>{duplicate}</code>\n"
                f"Errors: <code>{errors}</code>"
            )
        else:
            # Success - show final stats
            await msg.edit(
                f"Successfully saved <code>{total_files}</code> files to database!\n"
                f"Duplicate Files Skipped: <code>{duplicate}</code>\n"
                f"Deleted Messages Skipped: <code>{deleted}</code>\n"
                f"Non-Media messages skipped: <code>{no_media + unsupported}</code> (Unsupported Media - <code>{unsupported}</code>)\n"
                f"Errors Occurred: <code>{errors}</code>"
            )
