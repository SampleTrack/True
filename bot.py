"""
Feature 20 — Multi-Bot Token Pool
Feature 21 — Sentry Error Tracking
"""
import logging
import logging.config
import asyncio
logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)

from pyrogram import Client, __version__
from pyrogram.raw.all import layer
from database.ia_filterdb import Media
from database.users_chats_db import db
from info import (SESSION, API_ID, API_HASH, BOT_TOKEN, LOG_STR, PORT,
                  LOG_CHANNEL, SENTRY_DSN, EXTRA_BOT_TOKENS)
from utils import temp
from aiohttp import web
from datetime import date, datetime
import pytz
from Script import script
from plugins import web_server
from typing import Union, Optional, AsyncGenerator
from pyrogram import types
from scheduler.tasks import start_scheduler

# ── Feature 21 — Sentry ──────────────────────────────────────────────────────
if SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=SENTRY_DSN, traces_sample_rate=0.2)
    logging.info("Sentry error tracking enabled")


class Bot(Client):

    def __init__(self):
        super().__init__(
            name=SESSION,
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,
            plugins={"root": "plugins"},
            sleep_threshold=5,
        )

    async def start(self):
        b_users, b_chats = await db.get_banned()
        temp.BANNED_USERS = b_users
        temp.BANNED_CHATS = b_chats
        temp.MAINTENANCE_MODE = await db.get_maintenance()
        await super().start()
        await Media.ensure_indexes()
        me = await self.get_me()
        temp.ME = me.id
        temp.U_NAME = me.username
        temp.B_NAME = me.first_name
        self.username = "@" + me.username
        logging.info(f"{me.first_name} with Pyrogram v{__version__} (Layer {layer}) started on {me.username}.")
        logging.info(LOG_STR)
        tz = pytz.timezone("Asia/Kolkata")
        today = date.today()
        now = datetime.now(tz)
        time_str = now.strftime("%H:%M:%S %p")
        await self.send_message(chat_id=LOG_CHANNEL,
            text=script.RESTART_TXT.format(a=today, b=time_str, c=temp.U_NAME))
        app = web.AppRunner(await web_server())
        await app.setup()
        await web.TCPSite(app, "0.0.0.0", PORT).start()
        # Start background tasks (non-blocking)
        asyncio.create_task(self.send_report_message())
        # Feature 13/14/10/15 — start scheduler
        start_scheduler(self)
        # Feature 20 — start extra bot instances
        asyncio.create_task(self._start_extra_bots())

    async def _start_extra_bots(self):
        """Feature 20 — spin up worker bots for load-distributed file sends."""
        for i, token in enumerate(EXTRA_BOT_TOKENS):
            try:
                worker = Client(
                    name=f"worker_{i}",
                    api_id=API_ID,
                    api_hash=API_HASH,
                    bot_token=token,
                    workers=10,
                    sleep_threshold=5,
                )
                await worker.start()
                temp.WORKER_BOTS.append(worker)
                logging.info(f"Worker bot {i+1} started")
            except Exception as e:
                logging.error(f"Worker bot {i+1} failed to start: {e}")

    async def send_report_message(self):
        while True:
            tz = pytz.timezone("Asia/Kolkata")
            today = date.today()
            now = datetime.now(tz)
            if now.hour == 23 and now.minute == 59:
                formatted_date_1 = now.strftime("%d-%B-%Y")
                formatted_date_2 = today.strftime("%d %b")
                time_str = now.strftime("%H:%M:%S %p")
                total_users = await db.total_users_count()
                total_chats = await db.total_chat_count()
                today_users = await db.daily_users_count(today)
                today_chats = await db.daily_chats_count(today)
                status = await db.get_bot_status()
                k = await self.send_message(
                    chat_id=LOG_CHANNEL,
                    text=script.REPORT_TXT.format(
                        a=formatted_date_1, b=formatted_date_2, c=time_str,
                        d=total_users, e=total_chats, f=today_users,
                        g=today_chats, h=status["daily_active_users"],
                        i=status["active_user_percentage"], j=temp.U_NAME))
                await k.pin()
                await asyncio.sleep(120)
            else:
                await asyncio.sleep(30)

    async def stop(self, *args):
        for worker in temp.WORKER_BOTS:
            try:
                await worker.stop()
            except Exception:
                pass
        await super().stop()
        logging.info("Bot stopped.")

    async def iter_messages(
        self, chat_id: Union[int, str], limit: int, offset: int = 0,
    ) -> Optional[AsyncGenerator["types.Message", None]]:
        current = offset
        while True:
            new_diff = min(200, limit - current)
            if new_diff <= 0:
                return
            messages = await self.get_messages(chat_id, list(range(current, current + new_diff)))
            for message in messages:
                yield message
                current += 1


app = Bot()
app.run()
