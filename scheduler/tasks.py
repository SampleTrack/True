"""
Feature 13 — Scheduled Auto-Index
Feature 14 — Automated Backup System
Feature 10 — Smart Watch-Keyword Notifications
Feature 15 — Analytics cleanup
"""
import logging
import asyncio
import json
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


def start_scheduler(bot):
    """Register all scheduled tasks and start the scheduler."""
    scheduler.add_job(auto_index_task, IntervalTrigger(minutes=30),
                      id="auto_index", args=[bot], replace_existing=True)
    scheduler.add_job(backup_task, CronTrigger(hour=2, minute=0),
                      id="daily_backup", args=[bot], replace_existing=True)
    scheduler.add_job(watch_keyword_notify_task, IntervalTrigger(hours=1),
                      id="watch_notify", args=[bot], replace_existing=True)
    scheduler.add_job(analytics_cleanup_task, CronTrigger(hour=3, minute=0),
                      id="analytics_cleanup", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started with 4 tasks")


# ── Feature 13 — Auto-Index ──────────────────────────────────────────────────
async def auto_index_task(bot):
    """Automatically index new files from all configured channels."""
    from info import CHANNELS, LOG_CHANNEL
    from database.ia_filterdb import Media, save_file
    from database.users_chats_db import db

    logger.info("Auto-index task started")
    total_new = 0
    for channel in CHANNELS:
        try:
            last_msg_id = await db.get_last_indexed_msg_id(channel)
            async for message in bot.get_chat_history(channel, offset_id=last_msg_id):
                if message.id <= last_msg_id:
                    break
                if message.media:
                    from plugins.channel import save_media
                    saved, _ = await save_media(message)
                    if saved:
                        total_new += 1
                        await db.set_last_indexed_msg_id(channel, message.id)
        except Exception as e:
            logger.error(f"Auto-index error for channel {channel}: {e}")

    if total_new > 0:
        try:
            await bot.send_message(LOG_CHANNEL,
                f"#AutoIndex\n🔄 <b>Auto-index complete</b>\nNew files indexed: <code>{total_new}</code>")
        except Exception:
            pass
    logger.info(f"Auto-index done. New files: {total_new}")


# ── Feature 14 — Backup ──────────────────────────────────────────────────────
async def backup_task(bot):
    """Export entire files collection to JSON and send to LOG_CHANNEL."""
    from info import LOG_CHANNEL
    from database.ia_filterdb import Media
    import io

    logger.info("Backup task started")
    try:
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.now(tz)
        files = await Media.find({}).to_list(length=None)
        data = []
        for f in files:
            data.append({
                "file_id": f.get("_id"),
                "file_name": f.get("file_name"),
                "file_size": f.get("file_size"),
                "file_type": f.get("file_type"),
                "mime_type": f.get("mime_type"),
            })
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        buf = io.BytesIO(json_bytes)
        buf.name = f"backup_{now.strftime('%Y-%m-%d')}.json"
        await bot.send_document(
            LOG_CHANNEL, buf,
            caption=f"#DailyBackup\n📦 <b>Files DB Backup</b>\nDate: <code>{now.strftime('%d %b %Y')}</code>\nTotal Files: <code>{len(data)}</code>"
        )
        logger.info(f"Backup sent: {len(data)} files")
    except Exception as e:
        logger.error(f"Backup task error: {e}")


# ── Feature 10 — Watch Keyword Notifications ─────────────────────────────────
async def watch_keyword_notify_task(bot):
    """Notify users when new files matching their watch keywords are indexed."""
    from database.users_chats_db import db
    from database.ia_filterdb import get_search_results

    logger.info("Watch-keyword notification task started")
    tz = pytz.timezone("Asia/Kolkata")
    since = datetime.now(tz) - timedelta(hours=1)

    try:
        all_keywords = await db.get_all_watch_keywords()
        for keyword, user_ids in all_keywords.items():
            try:
                files, _, total = await get_search_results(keyword, max_results=3)
                new_files = [f for f in files if f.get("indexed_at") and f["indexed_at"] >= since]
                if not new_files:
                    continue
                for user_id in user_ids:
                    try:
                        lines = "\n".join(
                            f"  • <code>{f.get('file_name', 'Unknown')}</code>"
                            for f in new_files
                        )
                        await bot.send_message(
                            user_id,
                            f"🔔 <b>New files for your keyword</b> <code>{keyword}</code>\n\n{lines}\n\nSearch now in @{bot.username}"
                        )
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Watch notify error for keyword {keyword}: {e}")
    except Exception as e:
        logger.error(f"Watch keyword task error: {e}")


# ── Feature 15 — Analytics Cleanup ──────────────────────────────────────────
async def analytics_cleanup_task():
    """Remove analytics records older than 90 days."""
    from database.users_chats_db import db
    deleted = await db.cleanup_old_analytics(days=90)
    logger.info(f"Analytics cleanup: removed {deleted} old records")
