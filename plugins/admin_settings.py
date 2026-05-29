"""
Feature: Admin Settings Panel
Full inline-keyboard dashboard for bot-level config.
All settings stored in MongoDB bot_config collection.
No redeploy needed — everything changeable at runtime via bot.

/settings  — open the panel (admin only)

Toggles available:
  IMDB, SpellCheck, AutoDelete, ProtectContent,
  ForceSub, Verification, Shortlink, MelcowWelcome,
  P_TTI_ShowOff, SingleButton, CaptionFilter

Text-editable fields:
  CustomCaption, IMDBTemplate, WelcomeText

Maintenance toggles:
  Global maintenance, per-feature (search/verify/index/broadcast)
"""
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from database.users_chats_db import db
from info import ADMINS

logger = logging.getLogger(__name__)

# ── Default settings schema ───────────────────────────────────────────────────
DEFAULT_ADMIN_SETTINGS = {
    "imdb":            True,
    "spell_check":     True,
    "auto_delete":     False,
    "protect_content": False,
    "force_sub":       True,
    "verification":    True,
    "shortlink":       False,
    "melcow_welcome":  True,
    "p_tti_show_off":  False,
    "single_button":   True,
    "caption_filter":  False,
}

TOGGLE_LABELS = {
    "imdb":            "🎬 IMDB",
    "spell_check":     "✏️ Spell Check",
    "auto_delete":     "🗑 Auto Delete",
    "protect_content": "🔒 Protect Content",
    "force_sub":       "📢 Force Subscribe",
    "verification":    "🔐 Verification",
    "shortlink":       "🔗 Shortlink",
    "melcow_welcome":  "👋 Welcome Msg",
    "p_tti_show_off":  "📤 PM Show Off",
    "single_button":   "🔘 Single Button",
    "caption_filter":  "🔍 Caption Filter",
}

TEXT_FIELDS = {
    "custom_caption": "📝 Custom Caption",
    "imdb_template":  "🎭 IMDB Template",
    "welcome_text":   "💬 Welcome Text",
}


async def get_admin_settings() -> dict:
    settings = await db.get_bot_admin_settings()
    for k, v in DEFAULT_ADMIN_SETTINGS.items():
        settings.setdefault(k, v)
    return settings


def build_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    """Build the full settings inline keyboard."""
    rows = []
    # Toggles — 2 per row
    items = list(TOGGLE_LABELS.items())
    for i in range(0, len(items), 2):
        row = []
        for key, label in items[i:i+2]:
            val = settings.get(key, DEFAULT_ADMIN_SETTINGS.get(key, False))
            emoji = "✅" if val else "❌"
            row.append(InlineKeyboardButton(
                f"{emoji} {label}",
                callback_data=f"admsetting_toggle#{key}"
            ))
        rows.append(row)

    # Text field editors
    rows.append([
        InlineKeyboardButton("📝 Edit Caption", callback_data="admsetting_edit#custom_caption"),
        InlineKeyboardButton("🎭 Edit IMDB Template", callback_data="admsetting_edit#imdb_template"),
    ])
    rows.append([
        InlineKeyboardButton("💬 Edit Welcome Text", callback_data="admsetting_edit#welcome_text"),
    ])

    # Maintenance section
    rows.append([InlineKeyboardButton("─── 🛠 Maintenance ───", callback_data="admsetting_noop")])
    rows.append([
        InlineKeyboardButton("⚙️ Feature Toggles", callback_data="admsetting_features"),
        InlineKeyboardButton("🔴 Global Maintenance", callback_data="admsetting_global_maint"),
    ])

    # Stats shortcut
    rows.append([
        InlineKeyboardButton("📊 Analytics", callback_data="admsetting_analytics"),
        InlineKeyboardButton("❌ Close", callback_data="admsetting_close"),
    ])

    return InlineKeyboardMarkup(rows)


def settings_text(settings: dict) -> str:
    lines = ["⚙️ <b>Bot Admin Settings</b>
"]
    for key, label in TOGGLE_LABELS.items():
        val = settings.get(key, DEFAULT_ADMIN_SETTINGS.get(key, False))
        lines.append(f"{'✅' if val else '❌'} {label}")
    return "
".join(lines)


# ── /settings command ─────────────────────────────────────────────────────────
@Client.on_message(filters.command("settings") & filters.user(ADMINS) & filters.private)
async def admin_settings_cmd(bot, message):
    settings = await get_admin_settings()
    await message.reply(
        settings_text(settings),
        reply_markup=build_settings_keyboard(settings)
    )


# ── Toggle handler ─────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^admsetting_toggle#") & filters.user(ADMINS))
async def settings_toggle_cb(bot, query):
    await query.answer()
    key = query.data.split("#", 1)[1]
    settings = await get_admin_settings()
    current = settings.get(key, DEFAULT_ADMIN_SETTINGS.get(key, False))
    settings[key] = not current
    await db.save_bot_admin_settings(settings)
    label = TOGGLE_LABELS.get(key, key)
    new_val = settings[key]
    await query.message.edit_text(
        settings_text(settings),
        reply_markup=build_settings_keyboard(settings)
    )
    await query.answer(f"{'✅ Enabled' if new_val else '❌ Disabled'}: {label}", show_alert=False)


# ── Edit text fields ──────────────────────────────────────────────────────────
PENDING_EDITS = {}   # user_id -> field key

@Client.on_callback_query(filters.regex(r"^admsetting_edit#") & filters.user(ADMINS))
async def settings_edit_cb(bot, query):
    await query.answer()
    field = query.data.split("#", 1)[1]
    label = TEXT_FIELDS.get(field, field)
    settings = await get_admin_settings()
    current = settings.get(field, "Not set")
    PENDING_EDITS[query.from_user.id] = {"field": field, "msg_id": query.message.id}
    await query.message.reply(
        f"✏️ <b>Editing: {label}</b>

"
        f"Current value:
<code>{current[:300] if current else 'Not set'}</code>

"
        f"Send the new value now. Or /cancel to abort.",
    )


@Client.on_message(filters.private & filters.user(ADMINS) & filters.text & ~filters.command([]))
async def settings_text_input(bot, message):
    user_id = message.from_user.id
    if user_id not in PENDING_EDITS:
        return
    if message.text.strip() == "/cancel":
        PENDING_EDITS.pop(user_id, None)
        return await message.reply("Cancelled.")
    edit_info = PENDING_EDITS.pop(user_id)
    field = edit_info["field"]
    settings = await get_admin_settings()
    settings[field] = message.text.strip()
    await db.save_bot_admin_settings(settings)
    label = TEXT_FIELDS.get(field, field)
    await message.reply(f"✅ <b>{label}</b> updated successfully.")


# ── Feature toggles sub-panel ─────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^admsetting_features$") & filters.user(ADMINS))
async def settings_features_cb(bot, query):
    await query.answer()
    features = ["search", "verify", "index", "broadcast", "pm_filter"]
    statuses = await db.get_all_feature_maintenance()
    rows = []
    for f in features:
        disabled = statuses.get(f, False)
        rows.append([InlineKeyboardButton(
            f"{'🔴' if disabled else '🟢'} {f.capitalize()} {'(disabled)' if disabled else '(enabled)'}",
            callback_data=f"admsetting_ftoggle#{f}"
        )])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="admsetting_back")])
    await query.message.edit_text(
        "⚙️ <b>Feature Maintenance Toggles</b>

"
        "🟢 = active  |  🔴 = disabled",
        reply_markup=InlineKeyboardMarkup(rows)
    )


@Client.on_callback_query(filters.regex(r"^admsetting_ftoggle#") & filters.user(ADMINS))
async def settings_ftoggle_cb(bot, query):
    await query.answer()
    feature = query.data.split("#", 1)[1]
    statuses = await db.get_all_feature_maintenance()
    current = statuses.get(feature, False)
    await db.set_feature_maintenance(feature, not current)
    new_state = "disabled" if not current else "enabled"
    await query.answer(f"{feature} is now {new_state}", show_alert=True)
    # Refresh the panel
    features = ["search", "verify", "index", "broadcast", "pm_filter"]
    statuses = await db.get_all_feature_maintenance()
    rows = []
    for f in features:
        disabled = statuses.get(f, False)
        rows.append([InlineKeyboardButton(
            f"{'🔴' if disabled else '🟢'} {f.capitalize()} {'(disabled)' if disabled else '(enabled)'}",
            callback_data=f"admsetting_ftoggle#{f}"
        )])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="admsetting_back")])
    await query.message.edit_reply_markup(InlineKeyboardMarkup(rows))


# ── Global maintenance toggle ─────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^admsetting_global_maint$") & filters.user(ADMINS))
async def settings_global_maint_cb(bot, query):
    await query.answer()
    current = await db.get_maintenance()
    await db.set_maintenance(not current)
    new_state = "ON 🔴" if not current else "OFF 🟢"
    await query.answer(f"Global Maintenance is now {new_state}", show_alert=True)
    settings = await get_admin_settings()
    await query.message.edit_text(
        settings_text(settings),
        reply_markup=build_settings_keyboard(settings)
    )


# ── Analytics shortcut ────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^admsetting_analytics$") & filters.user(ADMINS))
async def settings_analytics_cb(bot, query):
    await query.answer()
    from database.ia_filterdb import Media
    from utils import get_size
    summary = await db.get_analytics_summary()
    bot_status = await db.get_bot_status()
    total_files = await Media.count_documents({})
    db_size = await db.get_db_size()
    await query.message.reply(
        f"📊 <b>Quick Analytics</b>

"
        f"👤 Users: <code>{bot_status['total_users']}</code>
"
        f"📈 Daily Active: <code>{bot_status['daily_active_users']}</code>
"
        f"📁 Files: <code>{total_files}</code>
"
        f"💾 DB: <code>{get_size(db_size)}</code>

"
        f"🔍 Today Searches: <code>{summary['today_searches']}</code>
"
        f"📥 Today Downloads: <code>{summary['today_downloads']}</code>"
    )


# ── Back / Close ──────────────────────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^admsetting_back$") & filters.user(ADMINS))
async def settings_back_cb(bot, query):
    await query.answer()
    settings = await get_admin_settings()
    await query.message.edit_text(
        settings_text(settings),
        reply_markup=build_settings_keyboard(settings)
    )


@Client.on_callback_query(filters.regex(r"^admsetting_close$") & filters.user(ADMINS))
async def settings_close_cb(bot, query):
    await query.answer()
    await query.message.delete()


@Client.on_callback_query(filters.regex(r"^admsetting_noop$") & filters.user(ADMINS))
async def settings_noop_cb(bot, query):
    await query.answer()
