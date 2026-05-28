"""
Feature 1 — Redis-backed temp state
Feature 3 — Rate limiting integration
"""
import logging
from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid
from info import AUTH_CHANNEL, LONG_IMDB_DESCRIPTION, MAX_LIST_ELM, LOG_CHANNEL
from imdb import IMDb
import asyncio
import string
import aiohttp
from pyrogram.types import Message, InlineKeyboardButton
from pyrogram import enums
from typing import Union
import random
import re
import pytz
from Script import script
from datetime import datetime, timedelta, date, time
from database.users_chats_db import db
from bs4 import BeautifulSoup
from cache.redis_manager import RedisManager, RateLimiter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
imdb = IMDb()

TOKENS = {}
VERIFIED = {}
URLINK = {}


class temp(object):
    BANNED_USERS = []
    BANNED_CHATS = []
    ME = None
    CURRENT = 0
    CANCEL = False
    MELCOW = {}
    U_NAME = None
    B_NAME = None
    USERS_CANCEL = False
    GROUPS_CANCEL = False
    SETTINGS = {}
    VERIFY = {}
    VERIFY_PERIOD = {}
    ACTIVE_URL = {}
    TOKEN_ACCEPTED = {}
    STORE_ID = {}
    MAINTENANCE_MODE = False
    WORKER_BOTS = []   # Feature 20 — populated by bot.py


async def add_new_user(client, user):
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    today = now.date()
    time_str = now.strftime("%I:%M:%S %p")
    total_users = await db.total_users_count()
    daily_users = await db.daily_users_count(today)
    await db.add_user(user.id, user.first_name)
    await client.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(
        a=user.id, b=user.mention, c=getattr(user, "username", "N/A"),
        d=total_users, e=daily_users, f=str(today), g=time_str, h=temp.U_NAME))


async def get_settings(group_id):
    # Feature 1 — try Redis first
    settings = await RedisManager.get_settings(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        await RedisManager.set_settings(group_id, settings)
    return settings


async def save_group_settings(group_id, key, value):
    current = await get_settings(group_id)
    current[key] = value
    await RedisManager.set_settings(group_id, current)
    await db.update_settings(group_id, current)


async def check_rate_limit(user_id: int, action: str = "search") -> bool:
    """Feature 3 — Returns True if request is allowed."""
    return await RateLimiter.check(user_id, action, limit=5, window=10)


def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])


def humanbytes(size):
    if not size:
        return ""
    power = 2 ** 10
    n = 0
    Dic_powerN = {0: " ", 1: "Ki", 2: "Mi", 3: "Gi", 4: "Ti"}
    while size > power and n < 4:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + "B"


def list_to_str(k):
    if not k:
        return "N/A"
    elif len(k) == 1:
        return str(k[0])
    elif MAX_LIST_ELM:
        k = k[:int(MAX_LIST_ELM)]
    return ", ".join(str(e) for e in k)


def get_file_id(msg: Message):
    if msg.media:
        for message_type in ("photo", "animation", "audio", "document",
                             "video", "video_note", "voice", "sticker"):
            obj = getattr(msg, message_type)
            if obj:
                setattr(obj, "message_type", message_type)
                return obj


def get_readable_time(seconds):
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for name, secs in periods:
        if seconds >= secs:
            val, seconds = divmod(seconds, secs)
            result += f"{int(val)}{name}"
    return result or "0s"


# ── verify helpers ────────────────────────────────────────────────────────────
async def get_verify_status(userid):
    # Feature 1 — Redis-backed verify cache
    status = await RedisManager.get_verify_status(userid)
    if not status:
        status = await db.get_verified(userid)
        await RedisManager.set_verify_status(userid, status)
    return status


async def verify_user(bot, userid, token):
    user = await bot.get_users(int(userid))
    if not await db.is_user_exist(user.id):
        await db.add_user(user.id, user.first_name)
        await bot.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(
            a=user.id, b=user.mention, c=getattr(user, "username", "N/A"),
            d="N/A", e="N/A", f="N/A", g="N/A", h=temp.U_NAME))
    # Feature 17 — mark token as used in Redis
    await RedisManager.mark_token_used(user.id, token)
    TOKENS[user.id] = {token: True}
    tz = pytz.timezone("Asia/Kolkata")
    date_var = datetime.now(tz) + timedelta(hours=12)
    temp_time = date_var.strftime("%H:%M:%S")
    date_str, _ = str(date_var).split(" ")
    await db.update_verification(user.id, date_str, temp_time)
    await RedisManager.set_verify_status(user.id, {"date": date_str, "time": temp_time})


async def check_token(bot, userid, token):
    # Feature 17 — check Redis first for used tokens
    if await RedisManager.is_token_used(userid, token):
        return False
    user = await bot.get_users(userid)
    if user.id in TOKENS:
        tkn = TOKENS[user.id]
        if token in tkn:
            return not tkn[token]
    return False


async def get_token(bot, userid, link, fileid):
    user = await bot.get_users(userid)
    if not await db.is_user_exist(user.id):
        await db.add_user(user.id, user.first_name)
        await bot.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(
            a=user.id, b=user.mention, c=getattr(user, "username", "N/A"),
            d="N/A", e="N/A", f="N/A", g="N/A", h=temp.U_NAME))
    token = "".join(random.choices(string.ascii_letters + string.digits, k=7))
    TOKENS[user.id] = {token: False}
    await RedisManager.set_verify_token(user.id, token)
    url = f"{link}verify-{user.id}-{token}-{fileid}"
    status = await get_verify_status(user.id)
    date_var = status["date"]
    time_var = status["time"]
    hour, minute, second = time_var.split(":")
    year, month, day = date_var.split("-")
    tz = pytz.timezone("Asia/Kolkata")
    last_dt = datetime(int(year), int(month), int(day),
                       int(hour), int(minute), int(second)) - timedelta(hours=12)
    curr_date = datetime.now(tz).date()
    vr_num = 2 if str(last_dt.date()) == str(curr_date) else 1
    return await get_verify_shorted_link(vr_num, url)


async def check_verification(bot, userid):
    user = await bot.get_users(int(userid))
    if not await db.is_user_exist(user.id):
        await db.add_user(user.id, user.first_name)
    tz = pytz.timezone("Asia/Kolkata")
    today = date.today()
    now = datetime.now(tz)
    curr_time_str = now.strftime("%H:%M:%S")
    h, m, s = curr_time_str.split(":")
    curr_time = time(int(h), int(m), int(s))
    status = await get_verify_status(user.id)
    date_var, time_var = status["date"], status["time"]
    yr, mo, dy = date_var.split("-")
    comp_date = date(int(yr), int(mo), int(dy))
    hh, mm, ss = time_var.split(":")
    comp_time = time(int(hh), int(mm), int(ss))
    if comp_date < today:
        return False
    if comp_date == today:
        return comp_time >= curr_time
    return True


async def get_verify_shorted_link(num, link):
    from info import SHORTLINK_API, SHORTLINK_URL, VERIFY2_API, VERIFY2_URL
    from database.users_chats_db import db as _db
    # Feature 19 — prefer DB-stored keys over env vars
    if int(num) == 1:
        API = await _db.get_api_key("shortlink") or SHORTLINK_API
        URL = await _db.get_api_key("shortlink_url") or SHORTLINK_URL
    else:
        API = await _db.get_api_key("verify2") or VERIFY2_API
        URL = await _db.get_api_key("verify2_url") or VERIFY2_URL

    if link.startswith("http:"):
        link = "https:" + link[5:]

    url = f"https://{URL}/api"
    params = {"api": API, "url": link}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, ssl=False) as resp:
                data = await resp.json()
                if data.get("status") == "success":
                    return data["shortenedUrl"]
    except Exception as e:
        logger.error(f"Shortlink error: {e}")
    return link


async def get_poster(query, bulk=False, id=False, file=None):
    if not id:
        query = query.strip().lower()
        title = query
        year = re.findall(r"[1-2]\d{3}$", query, re.IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = query.replace(year, "").strip()
        elif file:
            year = re.findall(r"[1-2]\d{3}", file, re.IGNORECASE)
            year = list_to_str(year[:1]) if year else None
        else:
            year = None
        movieid = imdb.search_movie(title, results=10)
        if not movieid:
            return None
        if year:
            filtered = [k for k in movieid if str(k.get("year")) == str(year)]
            if not filtered:
                filtered = movieid
        else:
            filtered = movieid
        movieid = [k for k in filtered if k.get("kind") in ["movie", "tv series"]] or filtered
        if bulk:
            return movieid
        movieid = movieid[0].movieID
    else:
        movieid = query
    movie = imdb.get_movie(movieid)
    plot = movie.get("plot outline" if LONG_IMDB_DESCRIPTION else "plot")
    if isinstance(plot, list) and plot:
        plot = plot[0]
    if plot and len(plot) > 800:
        plot = plot[:800] + "..."
    return {
        "title": movie.get("title"),
        "votes": movie.get("votes"),
        "aka": list_to_str(movie.get("akas")),
        "seasons": movie.get("number of seasons"),
        "imdb_id": f"tt{movie.get('imdbID')}",
        "cast": list_to_str(movie.get("cast")),
        "runtime": list_to_str(movie.get("runtimes")),
        "countries": list_to_str(movie.get("countries")),
        "languages": list_to_str(movie.get("languages")),
        "director": list_to_str(movie.get("director")),
        "genres": list_to_str(movie.get("genres")),
        "poster": movie.get("full-size cover url"),
        "plot": plot,
        "rating": str(movie.get("rating")),
        "year": movie.get("year"),
        "url": f"https://www.imdb.com/title/tt{movieid}",
    }
