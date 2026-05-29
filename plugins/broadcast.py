"""
Broadcast — Fast Concurrent + Personalized

Improvements over old version:
  1. Concurrent sending via asyncio.Semaphore (25 parallel sends)
     — 10-20x faster than sequential one-by-one
  2. Personalized message — every user sees "Hey {first_name}!" prepended
     Works for text messages (prepended) and media (added to caption)
  3. Live progress bar in status message
  4. Per-user name fetched from DB (no extra Telegram API calls)
  5. Separate deactivated-user cleanup — auto-removes dead accounts
  6. Cancel still works mid-broadcast
"""
from pyrogram import Client, filters
import time
import asyncio
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users_chats_db import db
from info import ADMINS
from utils import temp

lock = asyncio.Lock()

# ── How many messages to send at the same time ────────────────────────────────
# 25 is safe for most bots. Lower to 10 if you get flood errors.
CONCURRENT_LIMIT = 25


def progress_bar(done: int, total: int, length: int = 10) -> str:
    filled = int(length * done / total) if total else 0
    bar = "█" * filled + "░" * (length - filled)
    pct = int(100 * done / total) if total else 0
    return f"[{bar}] {pct}%"


def get_readable_time(seconds: float) -> str:
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for name, secs in periods:
        if seconds >= secs:
            val, seconds = divmod(seconds, secs)
            result += f"{int(val)}{name}"
    return result or "0s"


def eta(done: int, total: int, elapsed: float) -> str:
    if done == 0:
        return "calculating..."
    rate = done / elapsed
    remaining = (total - done) / rate
    return get_readable_time(remaining)


# ── Personalized send ─────────────────────────────────────────────────────────
async def send_personalized(bot, user_id: int, user_name: str,
                             message, pin: bool) -> str:
    """
    Send a copy of `message` to `user_id` with a personalised greeting.
    Supports text, photo, video, document, audio, voice, animation.
    """
    greeting = f"Hey <b>{user_name}</b>! 👋

"
    try:
        if message.text:
            # Text message — prepend greeting
            personalized_text = greeting + message.text.html
            m = await bot.send_message(
                user_id, personalized_text,
                disable_web_page_preview=True
            )
        elif message.media:
            # Media message — prepend greeting to caption
            original_caption = message.caption.html if message.caption else ""
            new_caption = greeting + original_caption if original_caption else greeting.rstrip("

")
            m = await message.copy(
                chat_id=user_id,
                caption=new_caption[:1024]   # Telegram caption limit
            )
        else:
            # Fallback — plain copy
            m = await message.copy(chat_id=user_id)

        if pin:
            try:
                await m.pin(both_sides=True)
            except Exception:
                pass
        return "Success"

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await send_personalized(bot, user_id, user_name, message, pin)

    except (InputUserDeactivated, UserIsBlocked, PeerIdInvalid):
        return "Blocked"   # user blocked bot or deactivated — mark for cleanup

    except Exception:
        return "Error"


async def send_to_group(bot, chat_id: int, message, pin: bool) -> str:
    """Groups broadcast — no personalisation (no single user name)."""
    try:
        k = await message.copy(chat_id=chat_id)
        if pin:
            try:
                await k.pin()
            except Exception:
                pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await send_to_group(bot, chat_id, message, pin)
    except Exception:
        return "Error"


# ── Cancel callbacks ──────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^broadcast_cancel#"))
async def broadcast_cancel(bot, query):
    await query.answer()
    _, ident = query.data.split("#")
    if ident == "users":
        await query.message.edit("⏹ Cancelling user broadcast...")
        temp.USERS_CANCEL = True
    elif ident == "groups":
        await query.message.edit("⏹ Cancelling group broadcast...")
        temp.GROUPS_CANCEL = True


# ── /broadcast ────────────────────────────────────────────────────────────────
@Client.on_message(
    filters.command(["broadcast", "pinbroadcast"]) &
    filters.user(ADMINS) & filters.reply
)
async def users_broadcast(bot, message):
    if lock.locked():
        return await message.reply("⚠️ A broadcast is already running. Wait for it to finish.")

    pin = message.command[0] == "pinbroadcast"
    b_msg = message.reply_to_message
    b_sts = await message.reply_text("📡 Preparing broadcast...")

    # Load all users into memory once (avoids cursor timeout mid-broadcast)
    users_cursor = await db.get_all_users()
    users = await users_cursor.to_list(length=None)
    total = len(users)
    if total == 0:
        return await b_sts.edit("No users found.")

    start_time = time.time()
    success = 0
    failed = 0
    blocked = 0
    done = 0
    temp.USERS_CANCEL = False
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    results_lock = asyncio.Lock()

    async def send_one(user):
        nonlocal success, failed, blocked, done
        async with semaphore:
            if temp.USERS_CANCEL:
                return
            name = user.get("name") or "there"
            uid = user.get("id")
            result = await send_personalized(bot, uid, name, b_msg, pin)
            async with results_lock:
                if result == "Success":
                    success += 1
                elif result == "Blocked":
                    blocked += 1
                    await db.delete_user(uid)   # auto-cleanup dead accounts
                else:
                    failed += 1
                done += 1

    async with lock:
        # Split into batches for live progress updates
        BATCH = 100
        for batch_start in range(0, total, BATCH):
            if temp.USERS_CANCEL:
                break
            batch = users[batch_start:batch_start + BATCH]
            await asyncio.gather(*[send_one(u) for u in batch])

            # Update status every batch
            elapsed = time.time() - start_time
            bar = progress_bar(done, total)
            time_taken = get_readable_time(elapsed)
            est = eta(done, total, elapsed)
            btn = [[InlineKeyboardButton("⏹ Cancel", callback_data="broadcast_cancel#users")]]
            await b_sts.edit(
                f"📡 <b>Broadcasting to Users</b>

"
                f"{bar}

"
                f"👥 Total: <code>{total}</code>
"
                f"✅ Success: <code>{success}</code>
"
                f"🚫 Blocked/Dead: <code>{blocked}</code>
"
                f"❌ Failed: <code>{failed}</code>
"
                f"⏱ Elapsed: <code>{time_taken}</code>
"
                f"⌛ ETA: <code>{est}</code>",
                reply_markup=InlineKeyboardMarkup(btn)
            )

    elapsed = time.time() - start_time
    time_taken = get_readable_time(elapsed)
    speed = round(success / elapsed, 1) if elapsed > 0 else 0
    cancelled = temp.USERS_CANCEL

    await b_sts.edit(
        f"{'⏹ Broadcast Cancelled' if cancelled else '✅ Broadcast Complete'}!

"
        f"👥 Total: <code>{total}</code>
"
        f"✅ Delivered: <code>{success}</code>
"
        f"🚫 Blocked/Deactivated: <code>{blocked}</code>
"
        f"❌ Failed: <code>{failed}</code>
"
        f"⚡ Speed: <code>{speed} msg/s</code>
"
        f"⏱ Time: <code>{time_taken}</code>"
    )
    temp.USERS_CANCEL = False


# ── /grp_broadcast ────────────────────────────────────────────────────────────
@Client.on_message(
    filters.command(["grp_broadcast", "pin_grp_broadcast"]) &
    filters.user(ADMINS) & filters.reply
)
async def groups_broadcast(bot, message):
    if lock.locked():
        return await message.reply("⚠️ A broadcast is already running. Wait for it to finish.")

    pin = message.command[0] == "pin_grp_broadcast"
    b_msg = message.reply_to_message
    b_sts = await message.reply_text("📡 Preparing group broadcast...")

    chats_cursor = await db.get_all_chats()
    chats = await chats_cursor.to_list(length=None)
    total = len(chats)
    if total == 0:
        return await b_sts.edit("No groups found.")

    start_time = time.time()
    success = 0
    failed = 0
    done = 0
    temp.GROUPS_CANCEL = False
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    results_lock = asyncio.Lock()

    async def send_one_group(chat):
        nonlocal success, failed, done
        async with semaphore:
            if temp.GROUPS_CANCEL:
                return
            result = await send_to_group(bot, int(chat["id"]), b_msg, pin)
            async with results_lock:
                if result == "Success":
                    success += 1
                else:
                    failed += 1
                done += 1

    async with lock:
        BATCH = 50
        for batch_start in range(0, total, BATCH):
            if temp.GROUPS_CANCEL:
                break
            batch = chats[batch_start:batch_start + BATCH]
            await asyncio.gather(*[send_one_group(c) for c in batch])

            elapsed = time.time() - start_time
            bar = progress_bar(done, total)
            btn = [[InlineKeyboardButton("⏹ Cancel", callback_data="broadcast_cancel#groups")]]
            await b_sts.edit(
                f"📡 <b>Broadcasting to Groups</b>

"
                f"{bar}

"
                f"🏘 Total: <code>{total}</code>
"
                f"✅ Success: <code>{success}</code>
"
                f"❌ Failed: <code>{failed}</code>
"
                f"⏱ Elapsed: <code>{get_readable_time(elapsed)}</code>",
                reply_markup=InlineKeyboardMarkup(btn)
            )

    elapsed = time.time() - start_time
    speed = round(success / elapsed, 1) if elapsed > 0 else 0
    cancelled = temp.GROUPS_CANCEL

    await b_sts.edit(
        f"{'⏹ Cancelled' if cancelled else '✅ Group Broadcast Complete'}!

"
        f"🏘 Total: <code>{total}</code>
"
        f"✅ Delivered: <code>{success}</code>
"
        f"❌ Failed: <code>{failed}</code>
"
        f"⚡ Speed: <code>{speed} msg/s</code>
"
        f"⏱ Time: <code>{get_readable_time(elapsed)}</code>"
    )
    temp.GROUPS_CANCEL = False
