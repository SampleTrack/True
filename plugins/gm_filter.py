import asyncio
import re
import ast
import math
import logging
from pyrogram.errors.exceptions.forbidden_403 import MessageDeleteForbidden
from pyrogram.errors.exceptions.bad_request_400 import MediaEmpty, PhotoInvalidDimensions, WebpageMediaEmpty
from Script import script
import pyrogram
from pyrogram.enums import MessageEntityType, ChatMemberStatus
from info import ADMINS, AUTH_CHANNEL, UPDATE_CHANNEL, FILE_FORWARD, FILE_CHANNEL, AUTH_USERS, CUSTOM_FILE_CAPTION, AUTH_GROUPS, P_TTI_SHOW_OFF, SINGLE_BUTTON, SPELL_CHECK_REPLY, IS_VERIFY, HOW_TO_VERIFY, LOG_CHANNEL 
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait, UserIsBlocked, MessageNotModified, PeerIdInvalid
from utils import get_size, is_subscribed, search_gagala, temp, get_settings, save_group_settings, check_verification, get_token
from database.users_chats_db import db
from database.ia_filterdb import Media, get_file_details, get_search_results

logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

BUTTONS = {}
SPELL_CHECK = {}
USER_SPAM_CACHE = {}  # Format: {chat_id: {user_id: (last_text, count)}}
DELETE_DELAY = 600    # Global configuration: Auto-delete lifetime for text logs (10 minutes)

# --- UTILITY FUNCTIONS ---

async def safe_delete(message, delay: int = 0):
    """Safely handles asynchronous background deletions with exception suppression."""
    if delay > 0:
        await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass

async def is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Fast cache-less check for administrative privileges."""
    if user_id in ADMINS:
        return True
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False

def generate_file_buttons(files, pre, button_setting):
    """Generates a standardized inline keyboard layout for files."""
    if button_setting:
        return [
            [InlineKeyboardButton(text=f"[{get_size(file.file_size)}] {file.file_name}", callback_data=f'{pre}#{file.file_id}')]
            for file in files
        ]
    return [
        [
            InlineKeyboardButton(text=f"{file.file_name}", callback_data=f'{pre}#{file.file_id}'),
            InlineKeyboardButton(text=get_size(file.file_size), callback_data=f'{pre}#{file.file_id}')
        ]
        for file in files
    ]

async def deliver_file(client, query, file_id, ident, settings):
    """Unified file delivery mechanism to eliminate code duplication."""
    files_ = await get_file_details(file_id)
    if not files_:
        return await query.answer('No such file exists.', show_alert=True)
    
    file = files_[0]
    title = file.file_name
    size = get_size(file.file_size)
    
    # Process Verification Guard
    if IS_VERIFY and not await check_verification(client, query.from_user.id):
        btn = [[
            InlineKeyboardButton("Verify", url=await get_token(client, query.from_user.id, f"https://telegram.me/{temp.U_NAME}?start=", file_id)),
            InlineKeyboardButton("How To Verify", url=HOW_TO_VERIFY)
        ]]
        verify_msg = await client.send_message(
            chat_id=query.from_user.id,
            text="<b>You are not verified!\nKindly verify to continue to get access for 12 hours!</b>",
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(btn)
        )
        asyncio.create_task(safe_delete(verify_msg, DELETE_DELAY))
        return await query.answer("Verification required! Check private messages.", show_alert=True)

    try:
        file_send = await client.send_cached_media(
            chat_id=FILE_CHANNEL,
            file_id=file_id,
            caption=script.CHANNEL_CAP.format(query.from_user.mention, title, query.message.chat.title),
            protect_content=True if ident in ["filep", "checksubp"] else False,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Update Channel", url=UPDATE_CHANNEL)],
                [InlineKeyboardButton('Hindi', 'hin'), InlineKeyboardButton('Marathi', 'mar'), InlineKeyboardButton('Telugu', 'tel')]
            ])
        )
        
        info_msg = await query.message.reply_text(
            script.FILE_MSG.format(query.from_user.mention, title, size),
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('📥 Download Link 📥', url=file_send.link)],
                [InlineKeyboardButton("⚠️ Can't Access ❓ Click Here ⚠️", url=FILE_FORWARD)]
            ])
        )
        await query.answer('File routed to File Channel successfully!')
        asyncio.create_task(safe_delete(info_msg, DELETE_DELAY))
        asyncio.create_task(safe_delete(file_send, DELETE_DELAY))
    except UserIsBlocked:
        await query.answer('Unblock the bot to receive your files!', show_alert=True)
    except Exception as e:
        logger.exception(e)
        await query.answer(url=f"https://t.me/{temp.U_NAME}?start={ident}_{file_id}")

# --- MESSAGE FILTERS ---

@Client.on_message(filters.group & filters.incoming)
async def give_filter(client, message):
    user_id = message.from_user.id if message.from_user else 0
    chat_id = message.chat.id

    if not user_id:
        return

    await db.track_user_activity(user_id, message.from_user.first_name or "User")

    # Step 1: Privilege Check
    is_user_admin = await is_admin(client, chat_id, user_id)

    # Step 2: Severe Structural/Spam Validations
    if not is_user_admin:
        if message.forward_date or message.media:
            return await safe_delete(message)

        if not message.text:
            return

        text = message.text.strip()
        text_lower = text.lower()

        # Ban Patterns & URL Prevention
        BAD_PATTERNS = ["@", "#", "www.", ".com", "http://", "https://", "t.me/"]
        if any(x in text_lower for x in BAD_PATTERNS) or len(text) > 300:
            return await safe_delete(message)

        # Anti-Flood / Repetitive Text matching
        user_cache = USER_SPAM_CACHE.setdefault(chat_id, {}).get(user_id, (None, 0))
        if user_cache[0] == text_lower:
            count = user_cache[1] + 1
            USER_SPAM_CACHE[chat_id][user_id] = (text_lower, count)
            if count >= 3:  # Delete third consecutive repeat
                return await safe_delete(message)
        else:
            USER_SPAM_CACHE[chat_id][user_id] = (text_lower, 1)
    else:
        if not message.text:
            return
        text_lower = message.text.strip().lower()

    # Step 3: Global Text Length & Common Phrase Skips
    if len(text_lower) < 3 or text_lower.startswith(("/", "!", ".", ",")):
        return

    IGNORE_TEXTS = {"hi", "hello", "ok", "hmm", "thanks", "thank you", "good morning", "good night", "yes", "no", "lol"}
    if text_lower in IGNORE_TEXTS:
        return

    # Clean query for processing
    search = re.sub(r'[^a-zA-Z0-9 ]', '', text_lower)
    search = " ".join(search.split())
    if not search:
        return

    # Trigger baseline user search loop
    await auto_filter(client, message)


async def auto_filter(client, msg, spoll=False):
    # Setup placeholder message instantly to retain user attention
    if not spoll:
        status_msg = await msg.reply_text("<b>🔍 Searching database, please wait...</b>", parse_mode=enums.ParseMode.HTML)
        message = msg
        settings = await get_settings(message.chat.id)
        if message.text.startswith("/"): 
            asyncio.create_task(safe_delete(status_msg))
            return
        search = message.text.lower()
        files, offset, total_results = await get_search_results(search, offset=0, filter=True)
        if not files:
            asyncio.create_task(safe_delete(status_msg))
            if settings["spell_check"]:
                return await advantage_spell_chok(msg)
            return
    else:
        status_msg = await msg.message.edit('<b>🔍 Sifting structural index matching...</b>', parse_mode=enums.ParseMode.HTML)
        settings = await get_settings(msg.message.chat.id)
        message = msg.message.reply_to_message
        search, files, offset, total_results = spoll

    pre = 'filep' if settings['file_secure'] else 'file'
    btn = generate_file_buttons(files, pre, settings["button"])

    # High-Performance UI Pagination
    if offset != "":
        key = f"{message.chat.id}-{message.id}"
        BUTTONS[key] = search
        req = message.from_user.id if message.from_user else 0
        total_pages = math.ceil(int(total_results) / 10)
        btn.append([
            InlineKeyboardButton(text=f"📃 1 / {total_pages}", callback_data="pages"),
            InlineKeyboardButton(text="NEXT ⏩", callback_data=f"next_{req}_{key}_{offset}")
        ])
    else:
        btn.append([InlineKeyboardButton(text="📃 Page 1 / 1", callback_data="pages")])

    cap = f"<b>✨ Here are the results for your query:</b> <code>{search}</code>"
    
    # Edit the loading sequence placeholder with final database matches
    await status_msg.edit_text(cap, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(btn))
    
    # Schedule structural cleanups for conversational clarity
    asyncio.create_task(safe_delete(message, DELETE_DELAY))
    asyncio.create_task(safe_delete(status_msg, DELETE_DELAY))
    
    if spoll:
        await safe_delete(msg.message)


# --- CALLBACK QUERY HANDLERS ---

@Client.on_callback_query(filters.regex(r"^next"))
async def next_page(bot, query):
    _, req, key, offset = query.data.split("_")
    if int(req) not in [query.from_user.id, 0]:
        return await query.answer("This is not your request menu!", show_alert=True)
    
    offset = int(offset) if offset.isdigit() else 0
    search = BUTTONS.get(key)
    if not search:
        return await query.answer("Session expired. Please request the movie name again.", show_alert=True)

    files, n_offset, total = await get_search_results(search, offset=offset, filter=True)
    if not files:
        return await query.answer("No more files found.")

    settings = await get_settings(query.message.chat.id)
    pre = 'filep' if settings['file_secure'] else 'file'
    btn = generate_file_buttons(files, pre, settings["button"])

    n_offset = int(n_offset) if str(n_offset).isdigit() else 0
    current_page = math.ceil(offset / 10) + 1
    total_pages = math.ceil(total / 10)

    nav_row = []
    if offset > 0:
        nav_row.append(InlineKeyboardButton("⏪ BACK", callback_data=f"next_{req}_{key}_{max(0, offset - 10)}"))
    
    nav_row.append(InlineKeyboardButton(f"📃 {current_page} / {total_pages}", callback_data="pages"))
    
    if n_offset > 0:
        nav_row.append(InlineKeyboardButton("NEXT ⏩", callback_data=f"next_{req}_{key}_{n_offset}"))
    
    btn.append(nav_row)
    
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btn))
    except MessageNotModified:
        pass
    await query.answer()


@Client.on_callback_query(filters.regex(r"^spolling"))
async def advantage_spoll_choker(bot, query):
    _, user, movie_idx = query.data.split('#')
    if int(user) != 0 and query.from_user.id != int(user):
        return await query.answer("This search belongs to another user.", show_alert=True)
        
    if movie_idx == "close_spellcheck":
        return await safe_delete(query.message)
        
    movies = SPELL_CHECK.get(query.message.reply_to_message.id)
    if not movies:
        return await query.answer("This list has expired. Please type a new search.", show_alert=True)
        
    movie = movies[int(movie_idx)]
    await query.answer('Searching database...')
    
    files, offset, total_results = await get_search_results(movie, offset=0, filter=True)
    if files:
        await auto_filter(bot, query, (movie, files, offset, total_results))
    else:
        err_msg = await query.message.edit('The requested title does not match items in database.')
        asyncio.create_task(safe_delete(err_msg, 5))


@Client.on_callback_query(group=1)
async def cb_handler(client: Client, query: CallbackQuery):
    if query.data == "close_data":
        await safe_delete(query.message)
        return

    if query.data.startswith(("file", "checksub")):
        ident, file_id = query.data.split("#")
        settings = await get_settings(query.message.chat.id)
        
        try:
            target_user = query.message.reply_to_message.from_user.id
        except Exception:
            target_user = query.from_user.id

        if settings.get('botpm') or AUTH_CHANNEL:
            if query.from_user.id != target_user:
                return await query.answer("This is not your movie choice. Submit your own request!", show_alert=True)
        
        await deliver_file(client, query, file_id, ident, settings)
        
    elif query.data in ["hin", "mar", "tel"]:
        alerts = {
            "hin": "कॉपीराइट के कारण फ़ाइल 10 मिनट में डिलीट हो जाएगी, इसे Saved Messages में सुरक्षित करें!",
            "mar": "कॉपीराइट मुळे ही फाइल 10 मिनिटांत डिलिट केली जाईल, Saved Messages मध्ये पाठवून डाउनलोड करा.",
            "tel": "కాపీరైట్ కారణంగా ఈ ఫైల్ 10 నిమిషాల్లో తొలగిపోతుంది, సేవ్డ్ సందేశాలలో పంపించండి!"
        }
        await query.answer(alerts[query.data], show_alert=True)
            
    elif query.data in ["start", "help", "about"]:
        text_map = {
            "start": (script.START_TXT.format(query.from_user.mention, temp.U_NAME, temp.B_NAME) if hasattr(script, 'START_TXT') else "Welcome"),
            "help": (script.HELP_TXT.format(query.from_user.mention) if hasattr(script, 'HELP_TXT') else "Help Manual"),
            "about": (script.ABOUT_TXT.format(temp.B_NAME) if hasattr(script, 'ABOUT_TXT') else "About Info")
        }
        buttons_map = {
            "start": [
                [InlineKeyboardButton('➕ Add Me To Your Groups ➕', url=f'http://t.me/{temp.U_NAME}?startgroup=true')],
                [InlineKeyboardButton('ℹ️ Help', callback_data='help'), InlineKeyboardButton('😊 About', callback_data='about')]
            ],
            "help": [[InlineKeyboardButton('🏠 Home', callback_data='start'), InlineKeyboardButton('🔐 Close', callback_data='close_data')]],
            "about": [[InlineKeyboardButton('🏠 Home', callback_data='start'), InlineKeyboardButton('🔐 Close', callback_data='close_data')]]
        }
        await query.message.edit_text(
            text=text_map[query.data],
            reply_markup=InlineKeyboardMarkup(buttons_map[query.data]),
            parse_mode=enums.ParseMode.HTML
        )
        await query.answer()

# --- OPTIMIZED SPELL CHECK SYSTEM ---

async def advantage_spell_chok(msg):
    clean_regex = r"\b(pl(i|e)*?(s|z+|ease|se|ese)|((send|snd|giv(e)?|gib)(\sme)?)|movie(s)?|new|latest|br((o|u)h?)*|h(e|a)?(l)*(o)*|file|find|full\smovie|any(one)|with\ssubtitle(s)?)"
    query = re.sub(clean_regex, "", msg.text, flags=re.IGNORECASE).strip()
    
    if not query:
        return
        
    g_s = await search_gagala(f"{query} movie") + await search_gagala(msg.text)
    if not g_s:
        err = await msg.reply("No records matches found for spelling alternatives.")
        asyncio.create_task(safe_delete(msg, DELETE_DELAY))
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
        err = await msg.reply("Spelling configuration unresolvable. Double check request text.")
        asyncio.create_task(safe_delete(msg, DELETE_DELAY))
        asyncio.create_task(safe_delete(err, 8))
        return

    SPELL_CHECK[msg.id] = movielist
    user = msg.from_user.id if msg.from_user else 0
    
    btn = [[InlineKeyboardButton(text=movie, callback_data=f"spolling#{user}#{idx}")] for idx, movie in enumerate(movielist)]
    btn.append([InlineKeyboardButton(text="Close", callback_data=f'spolling#{user}#close_spellcheck')])
    
    spell_msg = await msg.reply("I couldn't locate structural records matches.\nDid you intend one of the following?", reply_markup=InlineKeyboardMarkup(btn))
    
    # Auto-delete spell check sequence if left unaddressed
    asyncio.create_task(safe_delete(msg, DELETE_DELAY))
    asyncio.create_task(safe_delete(spell_msg, DELETE_DELAY))
