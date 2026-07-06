import asyncio
import re
import math
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserIsBlocked, MessageNotModified

# Import configurations and database methods
from info import ADMINS, AUTH_USERS, PM_FILTER_ON, FILE_CHANNEL, UPDATE_CHANNEL, FILE_FORWARD, IS_VERIFY, HOW_TO_VERIFY
from utils import get_size, search_gagala, temp, check_verification, get_token
from database.users_chats_db import db
from database.ia_filterdb import get_file_details, get_search_results

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

PM_BUTTONS = {}
PM_SPELL_CHECK = {}

# --- UTILITY FUNCTIONS ---

async def safe_delete(message, delay: int = 0):
    if delay > 0:
        await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass

def generate_pm_buttons(files, pre):
    """Generates a streamlined layout for PM file results."""
    return [
        [InlineKeyboardButton(text=f"[{get_size(file.file_size)}] {file.file_name}", callback_data=f'{pre}#{file.file_id}')]
        for file in files
    ]

# --- MESSAGE HANDLER ---

@Client.on_message(filters.private & filters.text & filters.incoming)
async def pm_filter_handler(client, message):
    # 1. Global Toggle Check
    if not PM_FILTER_ON:
        return

    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    # 2. Strict Authorization Guard (Only Admins & Authorized Users)
    if user_id not in ADMINS and user_id not in AUTH_USERS:
        return

    # Track activity for authorized users
    await db.track_user_activity(user_id, message.from_user.first_name or "User")

    text = message.text.strip()
    text_lower = text.lower()

    # 3. Structural Validation & Ignored Text Filters
    if len(text) < 3 or text_lower.startswith(("/", "!", ".", ",")):
        return

    IGNORE_TEXTS = {"hi", "hello", "ok", "hmm", "thanks", "thank you", "good morning", "good night", "yes", "no", "lol"}
    if text_lower in IGNORE_TEXTS:
        return

    BAD_PATTERNS = ["@", "#", "www.", ".com", "http://", "https://", "t.me/"]
    if any(x in text_lower for x in BAD_PATTERNS) or len(text) > 300:
        return

    # Clean query text
    search = re.sub(r'[^a-zA-Z0-9 ]', '', text_lower)
    search = " ".join(search.split())
    if not search:
        return

    # Automatically trigger auto-deletion for valid incoming user search messages
    asyncio.create_task(safe_delete(message, 600))
    await execute_pm_filter(client, message, search)


async def execute_pm_filter(client, message, search, spoll_string=None):
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return

    target_search = spoll_string if spoll_string else search
    
    files, offset, total_results = await get_search_results(target_search, offset=0, filter=True)
    
    if not files:
        # If no files match and it wasn't already a spellcheck selection, trigger spellcheck
        if not spoll_string:
            return await pm_spell_check_handler(message)
        return

    # Generate results interface using unique pm prefix
    btn = generate_pm_buttons(files, "pmfile")

    if offset != "":
        key = f"pm-{user_id}-{message.id}"
        PM_BUTTONS[key] = target_search
        total_pages = math.ceil(int(total_results) / 10)
        btn.append([
            InlineKeyboardButton(text=f"📃 1 / {total_pages}", callback_data="pm_pages"),
            InlineKeyboardButton(text="NEXT ⏩", callback_data=f"pmnext_{user_id}_{key}_{offset}")
        ])
    else:
        btn.append([InlineKeyboardButton(text="📃 Page 1 / 1", callback_data="pm_pages")])

    cap = f"<b>✨ PM Search Results for:</b> <code>{target_search}</code>"
    bot_reply = await message.reply_text(cap, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
    
    # Auto-delete the search results overview message after 10 minutes
    asyncio.create_task(safe_delete(bot_reply, 600))


# --- CALLBACK QUERY HANDLERS ---

@Client.on_callback_query(filters.regex(r"^pmnext"))
async def pm_next_page(bot, query):
    if not PM_FILTER_ON:
        return await query.answer("PM Filter is currently disabled.", show_alert=True)

    _, req, key, offset = query.data.split("_")
    if query.from_user.id != int(req):
        return await query.answer("This menu is locked to the original searcher.", show_alert=True)
    
    offset = int(offset) if offset.isdigit() else 0
    search = PM_BUTTONS.get(key)
    if not search:
        return await query.answer("Search session expired. Please type the movie name again.", show_alert=True)

    files, n_offset, total = await get_search_results(search, offset=offset, filter=True)
    if not files:
        return await query.answer("No additional records found.")

    btn = generate_pm_buttons(files, "pmfile")
    n_offset = int(n_offset) if str(n_offset).isdigit() else 0
    current_page = math.ceil(offset / 10) + 1
    total_pages = math.ceil(total / 10)

    nav_row = []
    if offset > 0:
        nav_row.append(InlineKeyboardButton("⏪ BACK", callback_data=f"pmnext_{req}_{key}_{max(0, offset - 10)}"))
    
    nav_row.append(InlineKeyboardButton(f"📃 {current_page} / {total_pages}", callback_data="pm_pages"))
    
    if n_offset > 0:
        nav_row.append(InlineKeyboardButton("NEXT ⏩", callback_data=f"pmnext_{req}_{key}_{n_offset}"))
    
    btn.append(nav_row)
    
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
    except MessageNotModified:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^pmfile"))
async def pm_file_delivery(client, query):
    ident, file_id = query.data.split("#")
    user_id = query.from_user.id

    files_ = await get_file_details(file_id)
    if not files_:
        return await query.answer('Requested file records no longer exist.', show_alert=True)
    
    file = files_[0]
    title = file.file_name
    size = get_size(file.file_size)
    
    # Verification System Integration
    if IS_VERIFY and not await check_verification(client, user_id):
        btn = [[
            InlineKeyboardButton("Verify", url=await get_token(client, user_id, f"https://telegram.me/{temp.U_NAME}?start=", file_id)),
            InlineKeyboardButton("How To Verify", url=HOW_TO_VERIFY)
        ]]
        verify_msg = await client.send_message(
            chat_id=user_id,
            text="<b>You are not verified!\nKindly complete verification to access content for 12 hours.</b>",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(btn)
        )
        # Auto-delete the verification prompt after 10 minutes
        asyncio.create_task(safe_delete(verify_msg, 600))
        return await query.answer("Verification required! Complete check inside PM.", show_alert=True)

    try:
        file_send = await client.send_cached_media(
            chat_id=FILE_CHANNEL,
            file_id=file_id,
            caption=f"<b>File Name:</b> <code>{title}</code>\n<b>Size:</b> {size}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Update Channel", url=UPDATE_CHANNEL)],
                [InlineKeyboardButton('Hindi', 'pm_hin'), InlineKeyboardButton('Marathi', 'pm_mar'), InlineKeyboardButton('Telugu', 'pm_tel')]
            ])
        )
        
        info_msg = await query.message.reply_text(
            f"<b>✅ File Processed Successfully!</b>\n\n<b>Title:</b> {title}\n<b>Size:</b> {size}",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('📥 Download Link 📥', url=file_send.link)],
                [InlineKeyboardButton("⚠️ Can't Access ❓ Click Here ⚠️", url=FILE_FORWARD)]
            ])
        )
        await query.answer('File delivered successfully!')
        
        # Auto-delete file references after 10 minutes to maintain copyright safety and cleanliness
        asyncio.create_task(safe_delete(info_msg, 600))
        asyncio.create_task(safe_delete(file_send, 600))
        
        # Clean up the original search list immediately once file delivery executes successfully
        asyncio.create_task(safe_delete(query.message))
        
    except UserIsBlocked:
        await query.answer('Please unblock the bot to route media transfers.', show_alert=True)
    except Exception as e:
        logger.exception(e)
        await query.answer("Delivery failure. Attempting manual start routine...", url=f"https://t.me/{temp.U_NAME}?start=pm_{file_id}")


@Client.on_callback_query(filters.regex(r"^pmspolling"))
async def pm_spellcheck_callback(bot, query):
    _, user_id, movie_idx = query.data.split('#')
    
    if query.from_user.id != int(user_id):
        return await query.answer("This menu is locked to another user configuration.", show_alert=True)
        
    if movie_idx == "close_pm_spell":
        return await safe_delete(query.message)
        
    movies = PM_SPELL_CHECK.get(query.message.id)
    if not movies:
        return await query.answer("This listing sequence has expired. Submit a new search text.", show_alert=True)
        
    selected_movie = movies[int(movie_idx)]
    await query.answer('Searching records...')
    await execute_pm_filter(bot, query.message, search=None, spoll_string=selected_movie)
    await safe_delete(query.message)


@Client.on_callback_query(filters.regex(r"^pm_"))
async def pm_language_alerts(bot, query):
    alerts = {
        "pm_hin": "कॉपीराइट के कारण फ़ाइल 10 मिनट में डिलीट हो जाएगी, इसे Saved Messages में सुरक्षित करें!",
        "pm_mar": "कॉपीराइट मुळे ही ... ... फाइल 10 मिनिटांत डिलिट केली जाईल, Saved Messages मध्ये पाठवून डाउनलोड करा.",
        "pm_tel": "కాపీరైట్ కారణంగా ఈ ఫైల్ 10 నిమిషాల్లో తొలగిపోతుంది, సేవ్డ్ సందేశాలలో పంపించండి!"
    }
    if query.data in alerts:
        await query.answer(alerts[query.data], show_alert=True)
    elif query.data == "pm_pages":
        await query.answer()


# --- SPELL CHECK SYSTEM ---

async def pm_spell_check_handler(msg):
    clean_regex = r"\b(pl(i|e)*?(s|z+|ease|se|ese)|((send|snd|giv(e)?|gib)(\sme)?)|movie(s)?|new|latest|br((o|u)h?)*|h(e|a)?(l)*(o)*|file|find|full\smovie|any(one)|with\ssubtitle(s)?)"
    query = re.sub(clean_regex, "", msg.text, flags=re.IGNORECASE).strip()
    
    if not query:
        return
        
    g_s = await search_gagala(f"{query} movie") + await search_gagala(msg.text)
    if not g_s:
        err = await msg.reply("No records matching spelling permutations found locally.")
        asyncio.create_task(safe_delete(err, 8))
        return

    regex_filter = re.compile(r".*(imdb|wikipedia).*", re.IGNORECASE)
    gs = list(filter(regex_filter.match, g_s))
    
    gs_parsed = [
        re.sub(r'\b(\-([a-zA-Z-\s])\-\simdb|(\-\s)?imdb|(\-\s)?wikipedia|\(|\)|\-|reviews|full|all|episode(s)?|film|movie|series)', '', i, flags=re.IGNORECASE).strip()
        for i in gs
    ]
    
    movielist = list(dict.fromkeys([m for m in gs_parsed if m]))[:3]
    if not movielist:
        err = await msg.reply("Alternative query structures unresolvable.")
        asyncio.create_task(safe_delete(err, 8))
        return

    user = msg.from_user.id
    btn = [[InlineKeyboardButton(text=movie, callback_data=f"pmspolling#{user}#{idx}")] for idx, movie in enumerate(movielist)]
    btn.append([InlineKeyboardButton(text="Close", callback_data=f'pmspolling#{user}#close_pm_spell')])
    
    reply_msg = await msg.reply("I couldn't locate exact file matches.\nDid you mean one of the following variations?", reply_markup=InlineKeyboardMarkup(btn))
    PM_SPELL_CHECK[reply_msg.id] = movielist
    
    # Auto-delete the spell check recommendation panel after 10 minutes
    asyncio.create_task(safe_delete(reply_msg, 600))
