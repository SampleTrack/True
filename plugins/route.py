"""
Feature 22 — Rich Health Check Endpoint
Exposes /health with real DB, uptime, and file stats.
"""
import time
from datetime import datetime
from aiohttp import web
from database.users_chats_db import db
from database.ia_filterdb import Media

START_TIME = time.time()


async def health_route(request):
    try:
        total_users = await db.total_users_count()
        total_chats = await db.total_chat_count()
        total_files = await Media.count_documents({})
        db_size = await db.get_db_size()
        maintenance = await db.get_maintenance()
        uptime_sec = int(time.time() - START_TIME)
        h, rem = divmod(uptime_sec, 3600)
        m, s = divmod(rem, 60)
        uptime_str = f"{h}h {m}m {s}s"
        return web.json_response({
            "status": "ok",
            "uptime": uptime_str,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "maintenance": maintenance,
            "stats": {
                "users": total_users,
                "chats": total_chats,
                "files": total_files,
                "db_size_bytes": db_size,
            }
        })
    except Exception as e:
        return web.json_response({"status": "error", "detail": str(e)}, status=500)


async def web_server():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is alive!"))
    app.router.add_get("/health", health_route)
    return app
