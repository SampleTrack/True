"""
Feature 12 — Web Dashboard (inline stats panel)
Feature 15 — Detailed Analytics
Feature 16 — Granular Maintenance Mode
Feature 18 — Suspicious Activity Detection
Feature 19 — API Key Rotation via bot command
"""
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users_chats_db import db
from database.ia_filterdb import Media
from info import ADMINS, LOG_CHANNEL
from utils import get_size
from datetime import datetime
import pytz


# ── Feature 15 — /analytics ──────────────────────────────────────────────────
@Client.on_message(filters.command("analytics") & filters.user(ADMINS))
async def analytics_cmd(bot, message):
    await message.reply("📊 Fetching analytics...")
    try:
        summary = await db.get_analytics_summary()
        top_searches = await db.get_popular_searches(5)
        bot_status = await db.get_bot_status()
        total_files = await Media.count_documents({})
        db_size = await db.get_db_size()

        top_lines = "\n".join(
            f"  {i+1}. <code>{s.get('_id', 'N/A')}</code> — {s['count']}x"
            for i, s in enumerate(top_searches)
        ) or "  No data yet."

        text = (
            "📊 <b>Bot Analytics Dashboard</b>\n\n"
            f"👤 Total Users: <code>{bot_status['total_users']}</code>\n"
            f"📈 Daily Active: <code>{bot_status['daily_active_users']}</code> "
            f"(<code>{bot_status['active_user_percentage']}%</code>)\n"
            f"📁 Total Files: <code>{total_files}</code>\n"
            f"💾 DB Size: <code>{get_size(db_size)}</code>\n\n"
            f"🔍 All-time Searches: <code>{summary['total_searches']}</code>\n"
            f"📥 All-time Downloads: <code>{summary['total_downloads']}</code>\n"
            f"🔍 Today Searches: <code>{summary['today_searches']}</code>\n"
            f"📥 Today Downloads: <code>{summary['today_downloads']}</code>\n\n"
            f"🔥 <b>Top 5 Searches:</b>\n{top_lines}"
        )
        await message.reply(text)
    except Exception as e:
        await message.reply(f"Error fetching analytics: {e}")


# ── Feature 16 — Granular Maintenance ────────────────────────────────────────
FEATURES = ["search", "verify", "index", "broadcast", "pm_filter"]

@Client.on_message(filters.command("feature") & filters.user(ADMINS))
async def feature_cmd(bot, message):
    """Usage: /feature search off  OR  /feature  (shows all statuses)"""
    args = message.command[1:]
    if len(args) == 0:
        # show all
        statuses = await db.get_all_feature_maintenance()
        lines = "\n".join(
            f"{'🔴' if statuses.get(f) else '🟢'} <code>{f}</code> — "
            f"{'disabled' if statuses.get(f) else 'enabled'}"
            for f in FEATURES
        )
        return await message.reply(
            f"⚙️ <b>Feature Status</b>\n\n{lines}\n\n"
            f"Toggle: /feature <name> on|off"
        )

    if len(args) != 2 or args[0] not in FEATURES or args[1] not in ("on", "off"):
        return await message.reply(
            f"Usage: /feature <name> on|off\nFeatures: {', '.join(FEATURES)}")

    feature, state = args
    disabled = (state == "off")
    await db.set_feature_maintenance(feature, disabled)
    emoji = "🔴" if disabled else "🟢"
    await message.reply(f"{emoji} Feature <code>{feature}</code> is now <b>{'disabled' if disabled else 'enabled'}</b>.")
    await bot.send_message(LOG_CHANNEL,
        f"#FeatureToggle\n{emoji} <b>{feature}</b> set to <b>{'OFF' if disabled else 'ON'}</b>\nBy: {message.from_user.mention}")


# ── Feature 19 — API Key Rotation ─────────────────────────────────────────────
@Client.on_message(filters.command("setapikey") & filters.user(ADMINS) & filters.private)
async def set_api_key_cmd(bot, message):
    """Usage: /setapikey shortlink YOUR_KEY_HERE"""
    args = message.command[1:]
    if len(args) < 2:
        return await message.reply(
            "Usage: /setapikey <service> <key>\n"
            "Services: shortlink, shortlink_url, verify2, verify2_url")
    service, key = args[0], " ".join(args[1:])
    await db.set_api_key(service, key)
    await message.delete()
    await message.reply(f"✅ API key for <code>{service}</code> updated successfully.\n(Message deleted for security)")


@Client.on_message(filters.command("getapikey") & filters.user(ADMINS) & filters.private)
async def get_api_key_cmd(bot, message):
    args = message.command[1:]
    if not args:
        return await message.reply("Usage: /getapikey <service>")
    key = await db.get_api_key(args[0])
    m = await message.reply(f"🔑 <code>{args[0]}</code>: <code>{key or 'Not set'}</code>")
    import asyncio
    await asyncio.sleep(15)
    await m.delete()


# ── Feature 18 — Suspicious Activity Detection ────────────────────────────────
@Client.on_message(filters.command("checkuser") & filters.user(ADMINS))
async def check_user_cmd(bot, message):
    """Check a user for suspicious activity."""
    args = message.command[1:]
    if not args:
        return await message.reply("Usage: /checkuser <user_id>")
    try:
        user_id = int(args[0])
    except ValueError:
        return await message.reply("Invalid user ID.")

    tz = pytz.timezone("Asia/Kolkata")
    today_downloads = await db.get_daily_download_count(user_id)
    sub = await db.get_subscription(user_id)
    ref_count = await db.get_referral_count(user_id)
    ban = await db.get_ban_status(user_id)

    flags = []
    if today_downloads > 50:
        flags.append(f"⚠️ High downloads today: {today_downloads}")
    if ref_count > 50:
        flags.append(f"⚠️ Abnormal referral count: {ref_count}")

    flag_text = "\n".join(flags) if flags else "✅ No suspicious activity"

    await message.reply(
        f"🔍 <b>User Check: <code>{user_id}</code></b>\n\n"
        f"Plan: <b>{sub['plan'].upper()}</b>\n"
        f"Today downloads: <code>{today_downloads}</code>\n"
        f"Referrals: <code>{ref_count}</code>\n"
        f"Banned: <code>{ban['is_banned']}</code>\n\n"
        f"<b>Flags:</b>\n{flag_text}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚫 Ban User", callback_data=f"ban_suspicious#{user_id}"),
            InlineKeyboardButton("✅ Clear", callback_data=f"clear_check#{user_id}")
        ]])
    )


@Client.on_callback_query(filters.regex(r"^ban_suspicious#") & filters.user(ADMINS))
async def ban_suspicious_cb(bot, query):
    user_id = int(query.data.split("#")[1])
    await db.ban_user(user_id, "Suspicious activity — auto-flagged")
    await query.message.edit_text(f"🚫 User <code>{user_id}</code> has been banned.")
    await bot.send_message(LOG_CHANNEL,
        f"#SuspiciousBan\nUser <code>{user_id}</code> banned by {query.from_user.mention}")


@Client.on_callback_query(filters.regex(r"^clear_check#") & filters.user(ADMINS))
async def clear_check_cb(bot, query):
    await query.message.edit_text("✅ User check cleared. No action taken.")


# ── Feature 8 — /plan (admin sets plans) ─────────────────────────────────────
@Client.on_message(filters.command("setplan") & filters.user(ADMINS))
async def set_plan_cmd(bot, message):
    """Usage: /setplan <user_id> <free|basic|premium> <days>"""
    args = message.command[1:]
    if len(args) < 3:
        return await message.reply(
            "Usage: /setplan <user_id> <free|basic|premium> <days>\n"
            "Example: /setplan 123456789 premium 30")
    try:
        user_id = int(args[0])
        plan = args[1]
        days = int(args[2])
    except (ValueError, IndexError):
        return await message.reply("Invalid arguments.")
    if plan not in ("free", "basic", "premium"):
        return await message.reply("Plan must be: free, basic, or premium")
    await db.set_subscription(user_id, plan, days)
    await message.reply(
        f"✅ Set <b>{plan.upper()}</b> plan for <code>{user_id}</code> for <b>{days} days</b>.")
    await bot.send_message(LOG_CHANNEL,
        f"#PlanSet\n<code>{user_id}</code> → {plan.upper()} ({days}d)\nBy: {message.from_user.mention}")


@Client.on_message(filters.command("myplan") & filters.private)
async def my_plan_cmd(bot, message):
    sub = await db.get_subscription(message.from_user.id)
    plan = sub["plan"].upper()
    expiry = sub.get("expiry")
    expiry_str = expiry.strftime("%d %b %Y") if expiry else "N/A"
    limits = {"FREE": "3 files/day", "BASIC": "20 files/day", "PREMIUM": "Unlimited"}
    await message.reply(
        f"💳 <b>Your Plan: {plan}</b>\n"
        f"Expires: <code>{expiry_str}</code>\n"
        f"Daily limit: <b>{limits.get(plan, 'Unlimited')}</b>\n\n"
        f"Upgrade: contact @{(await bot.get_me()).username}")
