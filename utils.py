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
from typing import List
from database.users_chats_db import db
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)



imdb = IMDb() 

TOKENS = {}
VERIFIED = {}
URLINK = {}
BANNED = {}
SMART_OPEN = '“'
SMART_CLOSE = '”'
START_CHAR = ('\'', '"', SMART_OPEN)

# temp db for banned 
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
    # ADD THIS:
    MAINTENANCE_MODE = False
    
async def add_new_user(client, user):
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    today = now.date()
    time = now.strftime('%I:%M:%S %p')
    total_users = await db.total_users_count() + 1
    daily_users = await db.daily_users_count(today) + 1
    await db.add_user(user.id, user.first_name)
    await client.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(a=user.id, b=user.mention, c=user.username, d=total_users, e=daily_users, f=str(today), g=time, h=temp.U_NAME))

def extract_commands(file_path):
    commands = []
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            match = re.search(r'filters\.command\(["\'](\w+)["\']', line)
            if match:
                commands.append(match.group(1))
    return commands
    
async def is_subscribed(bot, query):
    try:
        user = await bot.get_chat_member(AUTH_CHANNEL, query.from_user.id)
    except UserNotParticipant:
        pass
    except Exception as e:
        print(e)
    else:
        if user.status != enums.ChatMemberStatus.BANNED:
            return True
    return False

async def get_poster(query, bulk=False, id=False, file=None):
    if not id:
        # https://t.me/GetTGLink/4183
        query = (query.strip()).lower()
        title = query
        year = re.findall(r'[1-2]\d{3}$', query, re.IGNORECASE)
        if year:
            year = list_to_str(year[:1])
            title = (query.replace(year, "")).strip()
        elif file is not None:
            year = re.findall(r'[1-2]\d{3}', file, re.IGNORECASE)
            if year:
                year = list_to_str(year[:1]) 
        else:
            year = None
        movieid = imdb.search_movie(title.lower(), results=10)
        if not movieid:
            return None
        if year:
            filtered=list(filter(lambda k: str(k.get('year')) == str(year), movieid))
            if not filtered:
                filtered = movieid
        else:
            filtered = movieid
        movieid=list(filter(lambda k: k.get('kind') in ['movie', 'tv series'], filtered))
        if not movieid:
            movieid = filtered
        if bulk:
            return movieid
        movieid = movieid[0].movieID
    else:
        movieid = query
    movie = imdb.get_movie(movieid)
    if movie.get("original air date"):
        date = movie["original air date"]
    elif movie.get("year"):
        date = movie.get("year")
    else:
        date = "N/A"
    plot = ""
    if not LONG_IMDB_DESCRIPTION:
        plot = movie.get('plot')
        if plot and len(plot) > 0:
            plot = plot[0]
    else:
        plot = movie.get('plot outline')
    if plot and len(plot) > 800:
        plot = plot[0:800] + "..."

    return {
        'title': movie.get('title'),
        'votes': movie.get('votes'),
        "aka": list_to_str(movie.get("akas")),
        "seasons": movie.get("number of seasons"),
        "box_office": movie.get('box office'),
        'localized_title': movie.get('localized title'),
        'kind': movie.get("kind"),
        "imdb_id": f"tt{movie.get('imdbID')}",
        "cast": list_to_str(movie.get("cast")),
        "runtime": list_to_str(movie.get("runtimes")),
        "countries": list_to_str(movie.get("countries")),
        "certificates": list_to_str(movie.get("certificates")),
        "languages": list_to_str(movie.get("languages")),
        "director": list_to_str(movie.get("director")),
        "writer":list_to_str(movie.get("writer")),
        "producer":list_to_str(movie.get("producer")),
        "composer":list_to_str(movie.get("composer")) ,
        "cinematographer":list_to_str(movie.get("cinematographer")),
        "music_team": list_to_str(movie.get("music department")),
        "distributors": list_to_str(movie.get("distributors")),
        'release_date': date,
        'year': movie.get('year'),
        'genres': list_to_str(movie.get("genres")),
        'poster': movie.get('full-size cover url'),
        'plot': plot,
        'rating': str(movie.get("rating")),
        'url':f'https://www.imdb.com/title/tt{movieid}'
    }


async def search_gagala(text):
    usr_agent = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/61.0.3163.100 Safari/537.36'
    }
    text = text.replace(" ", '+')
    url = f'https://www.google.com/search?q={text}'
    
    try:
        async with aiohttp.ClientSession(headers=usr_agent) as session:
            async with session.get(url, raise_for_status=True) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                titles = soup.find_all('h3')
                return [title.getText() for title in titles]
    except Exception as e:
        logger.error(f"Error in search_gagala: {e}")
        return []

async def get_settings(group_id):
    settings = temp.SETTINGS.get(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        temp.SETTINGS[group_id] = settings
    return settings
    
async def save_group_settings(group_id, key, value):
    current = await get_settings(group_id)
    current[key] = value
    temp.SETTINGS[group_id] = current
    await db.update_settings(group_id, current)
    
def get_size(size):
    """Get size in readable format"""

    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])



def get_file_id(msg: Message):
    if msg.media:
        for message_type in (
            "photo",
            "animation",
            "audio",
            "document",
            "video",
            "video_note",
            "voice",
            "sticker"
        ):
            obj = getattr(msg, message_type)
            if obj:
                setattr(obj, "message_type", message_type)
                return obj
                
def extract_user(message: Message) -> Union[int, str]:
    """extracts the user from a message"""
    # https://github.com/SpEcHiDe/PyroGramBot/blob/f30e2cca12002121bad1982f68cd0ff9814ce027/pyrobot/helper_functions/extract_user.py#L7
    user_id = None
    user_first_name = None
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_first_name = message.reply_to_message.from_user.first_name

    elif len(message.command) > 1:
        if (
            len(message.entities) > 1 and
            message.entities[1].type == enums.MessageEntityType.TEXT_MENTION
        ):
           
            required_entity = message.entities[1]
            user_id = required_entity.user.id
            user_first_name = required_entity.user.first_name
        else:
            user_id = message.command[1]
            # don't want to make a request -_-
            user_first_name = user_id
        try:
            user_id = int(user_id)
        except ValueError:
            pass
    else:
        user_id = message.from_user.id
        user_first_name = message.from_user.first_name
    return (user_id, user_first_name)

def list_to_str(k):
    if not k:
        return "N/A"
    elif len(k) == 1:
        return str(k[0])
    elif MAX_LIST_ELM:
        k = k[:int(MAX_LIST_ELM)]
        return ' '.join(f'{elem}, ' for elem in k)
    else:
        return ' '.join(f'{elem}, ' for elem in k)

def last_online(from_user):
    time = ""
    if from_user.is_bot:
        time += "🤖 Bot :("
    elif from_user.status == enums.UserStatus.RECENTLY:
        time += "Recently"
    elif from_user.status == enums.UserStatus.LAST_WEEK:
        time += "Within the last week"
    elif from_user.status == enums.UserStatus.LAST_MONTH:
        time += "Within the last month"
    elif from_user.status == enums.UserStatus.LONG_AGO:
        time += "A long time ago :("
    elif from_user.status == enums.UserStatus.ONLINE:
        time += "Currently Online"
    elif from_user.status == enums.UserStatus.OFFLINE:
        time += from_user.last_online_date.strftime("%a, %d %b %Y, %H:%M:%S")
    return time







def humanbytes(size):
    if not size:
        return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'


async def send_verification_log(bot, userid, date_temp, time_temp):
    user = await bot.get_users(int(userid))
    log_message = f"#VerificationLog:\nUser ID: {user.id}\nUser Name: {user.mention}\nDate: {date_temp}\nTime: {time_temp}"
    await bot.send_message(LOG_CHANNEL, log_message)


async def update_verify_status(bot, userid, date_temp, time_temp):
    status = await get_verify_status(userid)
    status["date"] = date_temp
    status["time"] = time_temp
    temp.VERIFY[userid] = status
    await db.update_verification(userid, date_temp, time_temp)
    await send_verification_log(bot, userid, date_temp, time_temp)

async def verify_user(bot, userid, token):
    user = await bot.get_users(int(userid))
    if not await db.is_user_exist(user.id):
        await db.add_user(user.id, user.first_name)
        await bot.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(user.id, user.mention))
    TOKENS[user.id] = {token: True}
    tz = pytz.timezone('Asia/Kolkata')
    date_var = datetime.now(tz)+timedelta(hours=12)
    temp_time = date_var.strftime("%H:%M:%S")
    date_var, time_var = str(date_var).split(" ")
    await update_verify_status(bot, user.id, date_var, temp_time)


async def check_token(bot, userid, token):
    user = await bot.get_users(userid)
    if not await db.is_user_exist(user.id):
        await db.add_user(user.id, user.first_name)
        await bot.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(user.id, user.mention))
    if user.id in TOKENS.keys():
        TKN = TOKENS[user.id]
        if token in TKN.keys():
            is_used = TKN[token]
            if is_used == True:
                return False
            else:
                return True
    else:
        return False

async def get_verify_shorted_link(num, link):
    if int(num) == 1:
        API = SHORTLINK_API
        URL = SHORTLINK_URL
    else:
        API = VERIFY2_API
        URL = VERIFY2_URL
    https = link.split(":")[0]
    if "http" == https:
        https = "https"
        link = link.replace("http", https)

    if URL == "api.shareus.in":
        url = f"https://{URL}/shortLink"
        params = {"token": API,
                  "format": "json",
                  "link": link,
                  }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, raise_for_status=True, ssl=False) as response:
                    data = await response.json(content_type="text/html")
                    if data["status"] == "success":
                        return data["shortlink"]
                    else:
                        logger.error(f"Error: {data['message']}")
                        return f'https://{URL}/shortLink?token={API}&format=json&link={link}'

        except Exception as e:
            logger.error(e)
            return f'https://{URL}/shortLink?token={API}&format=json&link={link}'
    else:
        url = f'https://{URL}/api'
        params = {'api': API,
                  'url': link,
                  }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, raise_for_status=True, ssl=False) as response:
                    data = await response.json()
                    if data["status"] == "success":
                        return data["shortenedUrl"]
                    else:
                        logger.error(f"Error: {data['message']}")
                        if URL == 'clicksfly.com':
                            return f'https://{URL}/api?api={API}&url={link}'
                        else:
                            return f'https://{URL}/api?api={API}&link={link}'
        except Exception as e:
            logger.error(e)
            if URL == 'clicksfly.com':
                return f'https://{URL}/api?api={API}&url={link}'
            else:
                return f'https://{URL}/api?api={API}&link={link}'


async def get_token(bot, userid, link, fileid):
    user = await bot.get_users(userid)
    if not await db.is_user_exist(user.id):
        await db.add_user(user.id, user.first_name)
        await bot.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(user.id, user.mention))
    token = ''.join(random.choices(string.ascii_letters + string.digits, k=7))
    TOKENS[user.id] = {token: False}
    url = f"{link}verify-{user.id}-{token}-{fileid}"
    status = await get_verify_status(user.id)
    date_var = status["date"]
    time_var = status["time"]
    hour, minute, second = time_var.split(":")
    year, month, day = date_var.split("-")
    last_date, last_time = str((datetime(year=int(year), month=int(month), day=int(day), hour=int(hour), minute=int(minute), second=int(second)))-timedelta(hours=12)).split(" ")
    tz = pytz.timezone('Asia/Kolkata')
    curr_date, curr_time = str(datetime.now(tz)).split(" ")
    if last_date == curr_date:
        vr_num = 2
    else:
        vr_num = 1
    shortened_verify_url = await get_verify_shorted_link(vr_num, url)
    return str(shortened_verify_url)


async def get_verify_status(userid):
    status = temp.VERIFY.get(userid)
    if not status:
        status = await db.get_verified(userid)
        temp.VERIFY[userid] = status
    return status


async def check_verification(bot, userid):
    user = await bot.get_users(int(userid))
    if not await db.is_user_exist(user.id):
        await db.add_user(user.id, user.first_name)
        await bot.send_message(LOG_CHANNEL, script.LOG_TEXT_P.format(user.id, user.mention))
    tz = pytz.timezone('Asia/Kolkata')
    today = date.today()
    now = datetime.now(tz)
    curr_time = now.strftime("%H:%M:%S")
    hour1, minute1, second1 = curr_time.split(":")
    curr_time = time(int(hour1), int(minute1), int(second1))
    status = await get_verify_status(user.id)
    date_var = status["date"]
    time_var = status["time"]
    years, month, day = date_var.split('-')
    comp_date = date(int(years), int(month), int(day))
    hour, minute, second = time_var.split(":")
    comp_time = time(int(hour), int(minute), int(second))
    if comp_date<today:
        return False
    else:
        if comp_date == today:
            if comp_time<curr_time:
                return False
            else:
                return True
        else:
            return True
