import motor.motor_asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from info import ADMINS, DATABASE_URI, DATABASE_NAME
import logging

logger = logging.getLogger(__name__)

# Initialize isolated database connection for destructive operations
db_client = motor.motor_asyncio.AsyncIOMotorClient(DATABASE_URI)
db = db_client[DATABASE_NAME]

# ==========================================
# COMMANDS: Trigger the confirmation warnings
# ==========================================

@Client.on_message(filters.command("cleardb_users") & filters.user(ADMINS))
async def cmd_clear_users(client, message):
    await message.reply_text(
        "⚠️ **WARNING: DESTRUCTIVE ACTION** ⚠️\n\n"
        "This will permanently delete **ALL USERS AND CHATS** from the database. "
        "Your bot will forget everyone who has ever started it, and broadcast will be empty.\n\n"
        "Are you absolutely sure?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚨 YES, WIPE ALL USERS 🚨", callback_data="wipe_users")],
            [InlineKeyboardButton("❌ CANCEL", callback_data="cancel_wipe")]
        ])
    )

@Client.on_message(filters.command("cleardb_files") & filters.user(ADMINS))
async def cmd_clear_files(client, message):
    await message.reply_text(
        "⚠️ **WARNING: DESTRUCTIVE ACTION** ⚠️\n\n"
        "This will permanently delete **ALL INDEXED FILES (MOVIES/MEDIA)**. "
        "The auto-filter will be completely empty until you index your channels again.\n\n"
        "Are you absolutely sure?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚨 YES, WIPE ALL FILES 🚨", callback_data="wipe_files")],
            [InlineKeyboardButton("❌ CANCEL", callback_data="cancel_wipe")]
        ])
    )

@Client.on_message(filters.command("cleardb_all") & filters.user(ADMINS))
async def cmd_clear_all(client, message):
    await message.reply_text(
        "💀 **NUCLEAR WARNING** 💀\n\n"
        "This will drop the **ENTIRE DATABASE**. Users, groups, files, settings, everything. "
        "Your database will become 0 KB. This action is irreversible.\n\n"
        "Do you want to nuke the database?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("☢️ NUKE EVERYTHING ☢️", callback_data="wipe_all")],
            [InlineKeyboardButton("❌ CANCEL", callback_data="cancel_wipe")]
        ])
    )

# ==========================================
# CALLBACKS: Execute the destruction
# ==========================================

@Client.on_callback_query(filters.regex(r"^(wipe_users|wipe_files|wipe_all|cancel_wipe)$") & filters.user(ADMINS))
async def execute_wipe(client, query: CallbackQuery):
    action = query.data

    if action == "cancel_wipe":
        await query.message.edit_text("✅ Operation cancelled. Database is safe.")
        return await query.answer("Cancelled.")

    # 1. Wipe Users & Chats
    if action == "wipe_users":
        try:
            # Drop standard user collections. Adjust collection names if your db.py uses different ones.
            await db.users.drop()
            await db.chats.drop()
            await query.message.edit_text("🗑 **SUCCESS:** All user and chat data has been permanently deleted.")
        except Exception as e:
            logger.error(f"Failed to wipe users: {e}")
            await query.message.edit_text(f"❌ Error occurred: {e}")

    # 2. Wipe Indexed Files
    elif action == "wipe_files":
        try:
            # Your bot uses 'Telegram_files' (from info.py) or similar collection for media
            # This drops the primary file storage
            from info import COLLECTION_NAME
            await db[COLLECTION_NAME].drop()
            await query.message.edit_text("🗑 **SUCCESS:** All indexed files have been permanently deleted.")
        except Exception as e:
            logger.error(f"Failed to wipe files: {e}")
            await query.message.edit_text(f"❌ Error occurred: {e}")

    # 3. Nuke Everything (Drop all collections in the DB)
    elif action == "wipe_all":
        try:
            collections = await db.list_collection_names()
            for col in collections:
                await db[col].drop()
            await query.message.edit_text("☢️ **SUCCESS:** The entire database has been nuked. It is now completely empty.")
        except Exception as e:
            logger.error(f"Failed to nuke database: {e}")
            await query.message.edit_text(f"❌ Error occurred: {e}")

    await query.answer("Operation Complete.", show_alert=True)
