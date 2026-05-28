"""
Feature 9  — User History & Favourites
Feature 10 — Watch Keywords
Feature 11 — Referral System
"""
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users_chats_db import db
from info import ADMINS
from utils import temp


# ── /history ─────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("history") & filters.private)
async def history_cmd(bot, message):
    records = await db.get_history(message.from_user.id)
    if not records:
        return await message.reply("You have no download history yet.")
    lines = [f"{i+1}. <code>{r['file_name']}</code>"
             for i, r in enumerate(records)]
    await message.reply("📜 <b>Your last 10 downloads:</b>\n\n" + "\n".join(lines))


# ── /favourites + /addfav ─────────────────────────────────────────────────────
@Client.on_message(filters.command("favourites") & filters.private)
async def favourites_cmd(bot, message):
    favs = await db.get_favourites(message.from_user.id)
    if not favs:
        return await message.reply("You have no favourites yet. Use /addfav while receiving a file.")
    buttons = [[InlineKeyboardButton(f"🗑 Remove {f['file_name'][:25]}",
                callback_data=f"rmfav#{f['file_id']}")] for f in favs[:10]]
    await message.reply(
        "⭐ <b>Your favourites:</b>\n\n" +
        "\n".join(f"{i+1}. <code>{f['file_name']}</code>" for i, f in enumerate(favs[:10])),
        reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_callback_query(filters.regex(r"^rmfav#"))
async def remove_fav_cb(bot, query):
    await query.answer()
    file_id = query.data.split("#", 1)[1]
    await db.remove_favourite(query.from_user.id, file_id)
    await query.answer("Removed from favourites ✅", show_alert=True)
    await query.message.delete()


# ── /watch, /unwatch, /watchlist ─────────────────────────────────────────────
@Client.on_message(filters.command("watch") & filters.private)
async def watch_cmd(bot, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /watch <keyword>\nExample: /watch RRR 2022")
    keyword = " ".join(message.command[1:]).strip().lower()
    if len(keyword) < 2:
        return await message.reply("Keyword too short.")
    keywords = await db.get_watch_keywords(message.from_user.id)
    if len(keywords) >= 10:
        return await message.reply("You can watch at most 10 keywords. Remove some with /unwatch.")
    if keyword in keywords:
        return await message.reply(f"Already watching <code>{keyword}</code>.")
    await db.add_watch_keyword(message.from_user.id, keyword)
    await message.reply(f"🔔 Now watching: <code>{keyword}</code>\n\nYou'll be notified when new files are indexed matching this keyword.")


@Client.on_message(filters.command("unwatch") & filters.private)
async def unwatch_cmd(bot, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /unwatch <keyword>")
    keyword = " ".join(message.command[1:]).strip().lower()
    await db.remove_watch_keyword(message.from_user.id, keyword)
    await message.reply(f"🔕 Removed watch: <code>{keyword}</code>")


@Client.on_message(filters.command("watchlist") & filters.private)
async def watchlist_cmd(bot, message):
    keywords = await db.get_watch_keywords(message.from_user.id)
    if not keywords:
        return await message.reply("You're not watching any keywords. Add one with /watch <keyword>")
    lines = "\n".join(f"• <code>{k}</code>" for k in keywords)
    await message.reply(f"🔔 <b>Your watch keywords:</b>\n\n{lines}\n\nRemove with /unwatch <keyword>")


# ── /referral ─────────────────────────────────────────────────────────────────
@Client.on_message(filters.command("referral") & filters.private)
async def referral_cmd(bot, message):
    user_id = message.from_user.id
    count = await db.get_referral_count(user_id)
    sub = await db.get_subscription(user_id)
    bot_username = temp.U_NAME
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    await message.reply(
        f"🔗 <b>Your Referral Link:</b>\n<code>{link}</code>\n\n"
        f"👥 Total referrals: <b>{count}</b>\n"
        f"🎁 Each referral gives your friend 1 day free premium.\n\n"
        f"Current plan: <b>{sub['plan'].upper()}</b>" +
        (f"\nExpires: <code>{sub['expiry'].strftime('%d %b %Y')}</code>" if sub.get("expiry") else ""),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏆 Top Referrers", callback_data="top_referrers")
        ]])
    )


@Client.on_callback_query(filters.regex(r"^top_referrers$"))
async def top_referrers_cb(bot, query):
    await query.answer()
    top = await db.get_top_referrers(10)
    if not top:
        return await query.answer("No referrals yet!", show_alert=True)
    lines = "\n".join(
        f"{i+1}. {r.get('name', 'Unknown')} — <b>{r['referral_count']}</b> referrals"
        for i, r in enumerate(top)
    )
    await query.message.reply(f"🏆 <b>Top Referrers:</b>\n\n{lines}")
    await query.answer()
