"""
Feature: Force-Sub Channel Join/Leave Logging

- Logs every new member join in the force-sub channel to LOG_CHANNEL
- When a user fails the force-sub check (left the channel), sends them
  a "please don't leave" DM instead of a generic error
- Channel leave detection is handled at access-check time (reliable)
  since Telegram does not push real-time leave events for channels
"""
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, ChannelPrivate
from database.users_chats_db import db
from info import AUTH_CHANNEL, LOG_CHANNEL, UPDATE_CHANNEL, SUPPORT_CHAT
from utils import temp
import pytz
from datetime import datetime


# ── Join logger — fires when someone joins the force-sub channel ──────────────
@Client.on_chat_member_updated(filters.chat(AUTH_CHANNEL) if AUTH_CHANNEL else filters.all)
async def forcesub_member_update(bot, update):
    if not AUTH_CHANNEL:
        return
    if not update.new_chat_member:
        return

    user = update.new_chat_member.user
    status = update.new_chat_member.status.value   # "member", "administrator", "left", "banned"

    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    date_str = now.strftime("%d %b %Y")
    time_str = now.strftime("%H:%M:%S")

    try:
        chat = await bot.get_chat(AUTH_CHANNEL)
        total_members = await bot.get_chat_members_count(AUTH_CHANNEL)
        channel_name = chat.title
    except Exception:
        total_members = "N/A"
        channel_name = str(AUTH_CHANNEL)

    if status == "member":
        # New join
        await bot.send_message(
            LOG_CHANNEL,
            f"#ChannelJoin 🎉

"
            f"👤 User: {user.mention}
"
            f"🆔 ID: <code>{user.id}</code>
"
            f"📛 Username: @{user.username or 'N/A'}
"
            f"📢 Channel: <b>{channel_name}</b>
"
            f"👥 Total Members: <code>{total_members}</code>
"
            f"📅 Date: <code>{date_str}</code>
"
            f"⏰ Time: <code>{time_str}</code>

"
            f"#{temp.U_NAME}",
            disable_web_page_preview=True
        )

    elif status in ("left", "kicked"):
        # Left or banned — log it
        await bot.send_message(
            LOG_CHANNEL,
            f"#ChannelLeave 😔

"
            f"👤 User: {user.mention}
"
            f"🆔 ID: <code>{user.id}</code>
"
            f"📛 Username: @{user.username or 'N/A'}
"
            f"📢 Channel: <b>{channel_name}</b>
"
            f"👥 Remaining Members: <code>{total_members}</code>
"
            f"📅 Date: <code>{date_str}</code>
"
            f"⏰ Time: <code>{time_str}</code>

"
            f"#{temp.U_NAME}",
            disable_web_page_preview=True
        )
        # Send "don't leave" DM to the user
        try:
            buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔔 Re-Join Channel", url=f"https://t.me/{(await bot.get_chat(AUTH_CHANNEL)).username}"),
                InlineKeyboardButton("💬 Support", url=SUPPORT_CHAT)
            ]])
            await bot.send_message(
                user.id,
                f"😢 <b>Hey {user.first_name}!</b>

"
                f"We noticed you left <b>{channel_name}</b>.

"
                f"You won't be able to access files from me without being a member. "
                f"The channel is where we post updates, new content, and announcements!

"
                f"👇 Please re-join to continue using the bot.",
                reply_markup=buttons
            )
        except Exception:
            pass  # User may have blocked the bot


async def check_forcesub(bot, user_id: int) -> bool:
    """
    Check if a user is subscribed to AUTH_CHANNEL.
    If not — send the 'don't leave' nudge and return False.
    Call this from /start and pm_filter handlers.
    """
    if not AUTH_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(AUTH_CHANNEL, user_id)
        from pyrogram.enums import ChatMemberStatus
        if member.status == ChatMemberStatus.BANNED:
            return False
        return True
    except UserNotParticipant:
        # User is not in the channel — send the nudge
        try:
            chat = await bot.get_chat(AUTH_CHANNEL)
            channel_link = f"https://t.me/{chat.username}" if chat.username else UPDATE_CHANNEL
            channel_name = chat.title
            buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Join Channel", url=channel_link)
            ], [
                InlineKeyboardButton("🔄 I Joined — Try Again", callback_data="check_sub")
            ]])
            await bot.send_message(
                user_id,
                f"🔒 <b>Access Restricted</b>

"
                f"You need to join <b>{channel_name}</b> to use this bot.

"
                f"👇 Join and then tap <b>I Joined</b>.",
                reply_markup=buttons
            )
        except Exception:
            pass
        return False
    except (ChatAdminRequired, ChannelPrivate):
        return True  # Can't check — let through
    except Exception:
        return True


@Client.on_callback_query(filters.regex("^check_sub$"))
async def check_sub_callback(bot, query):
    await query.answer()
    is_subbed = await check_forcesub(bot, query.from_user.id)
    if is_subbed:
        await query.message.edit_text(
            "✅ <b>Verified!</b> You're now subscribed.

Send me a movie name to search.")
    else:
        await query.answer("❌ You haven't joined yet. Please join the channel first.", show_alert=True)
