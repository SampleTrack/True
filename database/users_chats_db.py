"""
Feature 1  — Redis-backed settings/banned lists
Feature 7  — Duplicate detection helper
Feature 8  — Subscription plans
Feature 9  — User history & favourites
Feature 10 — Watch keywords
Feature 11 — Referral system
Feature 15 — Analytics tracking
Feature 16 — Granular maintenance
Feature 19 — API key storage / rotation
"""
import pytz
import hashlib
from datetime import date, datetime, timedelta
import motor.motor_asyncio
from info import (DATABASE_NAME, DATABASE_URI, AUTO_DELETE, IMDB,
                  IMDB_TEMPLATE, MELCOW_NEW_USERS, P_TTI_SHOW_OFF,
                  SINGLE_BUTTON, SPELL_CHECK_REPLY, PROTECT_CONTENT)


class Database:

    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.users
        self.grp = self.db.groups
        self.analytics = self.db.analytics
        self.config = self.db.bot_config

    # ── helpers ───────────────────────────────────────────────────────────────
    def _tz_now(self):
        return datetime.now(pytz.timezone("Asia/Kolkata"))

    def new_user(self, id, name):
        return dict(id=id, name=name,
                    ban_status=dict(is_banned=False, ban_reason=""),
                    timestamp=self._tz_now())

    def new_group(self, id, title):
        return dict(id=id, title=title,
                    chat_status=dict(is_disabled=False, reason=""),
                    timestamp=self._tz_now())

    # ── users ─────────────────────────────────────────────────────────────────
    async def add_user(self, id, name):
        if not await self.is_user_exist(id):
            await self.col.insert_one(self.new_user(id, name))

    async def is_user_exist(self, id):
        return bool(await self.col.find_one({"id": int(id)}))

    async def total_users_count(self):
        return await self.col.count_documents({})

    async def get_all_users(self):
        return self.col.find({})

    async def delete_user(self, user_id):
        await self.col.delete_many({"id": int(user_id)})

    async def track_user_activity(self, id, name):
        await self.add_user(id, name)
        await self.col.update_one({"id": int(id)},
                                  {"$set": {"last_active": self._tz_now()}})

    async def daily_users_count(self, today):
        tz = pytz.timezone("Asia/Kolkata")
        start = tz.localize(datetime.combine(today, datetime.min.time()))
        end = tz.localize(datetime.combine(today, datetime.max.time()))
        return await self.col.count_documents({"timestamp": {"$gte": start, "$lt": end}})

    # ── ban / unban ───────────────────────────────────────────────────────────
    async def ban_user(self, user_id, ban_reason="No Reason"):
        await self.col.update_one({"id": user_id},
            {"$set": {"ban_status": dict(is_banned=True, ban_reason=ban_reason)}})

    async def remove_ban(self, id):
        await self.col.update_one({"id": id},
            {"$set": {"ban_status": dict(is_banned=False, ban_reason="")}})

    async def get_ban_status(self, id):
        default = dict(is_banned=False, ban_reason="")
        user = await self.col.find_one({"id": int(id)})
        return (user or {}).get("ban_status", default)

    async def get_banned(self):
        users = self.col.find({"ban_status.is_banned": True})
        chats = self.grp.find({"chat_status.is_disabled": True})
        return ([u["id"] async for u in users],
                [c["id"] async for c in chats])

    # ── groups ────────────────────────────────────────────────────────────────
    async def add_chat(self, chat, title, username=None):
        doc = self.new_group(chat, title)
        if username:
            doc["username"] = username
        await self.grp.insert_one(doc)

    async def get_chat(self, chat):
        doc = await self.grp.find_one({"id": int(chat)})
        return False if not doc else doc.get("chat_status")

    async def total_chat_count(self):
        return await self.grp.count_documents({})

    async def daily_chats_count(self, today):
        tz = pytz.timezone("Asia/Kolkata")
        start = tz.localize(datetime.combine(today, datetime.min.time()))
        end = tz.localize(datetime.combine(today, datetime.max.time()))
        return await self.grp.count_documents({"timestamp": {"$gte": start, "$lt": end}})

    async def disable_chat(self, chat, reason="No Reason"):
        await self.grp.update_one({"id": int(chat)},
            {"$set": {"chat_status": dict(is_disabled=True, reason=reason)}})

    async def re_enable_chat(self, id):
        await self.grp.update_one({"id": int(id)},
            {"$set": {"chat_status": dict(is_disabled=False, reason="")}})

    async def get_all_chats(self):
        return self.grp.find({})

    async def delete_chat(self, chat):
        await self.grp.delete_many({"id": int(chat)})

    async def save_chat_invite_link(self, chat_id, invite_link):
        await self.grp.update_one({"id": int(chat_id)},
                                  {"$set": {"invite_link": invite_link}})

    async def get_chat_invite_link(self, chat_id):
        doc = await self.grp.find_one({"id": int(chat_id)})
        return doc.get("invite_link") if doc else None

    # ── settings ──────────────────────────────────────────────────────────────
    async def update_settings(self, id, settings):
        await self.grp.update_one({"id": int(id)},
                                  {"$set": {"settings": settings}})

    async def get_settings(self, id):
        default = {
            "button": SINGLE_BUTTON, "botpm": P_TTI_SHOW_OFF,
            "file_secure": PROTECT_CONTENT, "imdb": IMDB,
            "spell_check": SPELL_CHECK_REPLY, "welcome": MELCOW_NEW_USERS,
            "template": IMDB_TEMPLATE, "auto_delete": AUTO_DELETE
        }
        doc = await self.grp.find_one({"id": int(id)})
        if doc:
            saved = doc.get("settings", default)
            for k, v in default.items():
                saved.setdefault(k, v)
            return saved
        return default

    # ── verification ──────────────────────────────────────────────────────────
    async def update_verification(self, id, date, time):
        await self.col.update_one({"id": int(id)},
            {"$set": {"verification_status": {"date": str(date), "time": str(time)}}},
            upsert=True)

    async def get_verified(self, id):
        default = {"date": "1999-12-31", "time": "23:59:59"}
        doc = await self.col.find_one({"id": int(id)})
        return (doc or {}).get("verification_status", default)

    # ── bot status / stats ────────────────────────────────────────────────────
    async def get_bot_status(self):
        tz = pytz.timezone("Asia/Kolkata")
        today_start = tz.localize(datetime.combine(date.today(), datetime.min.time()))
        today_end = tz.localize(datetime.combine(date.today(), datetime.max.time()))
        total_users = await self.col.count_documents({})
        daily_active = await self.col.count_documents(
            {"last_active": {"$gte": today_start, "$lt": today_end}})
        pct = (daily_active / total_users * 100) if total_users > 0 else 0
        return {"total_users": total_users, "daily_active_users": daily_active,
                "active_user_percentage": round(pct, 2)}

    async def get_db_size(self):
        return (await self.db.command("dbstats"))["dataSize"]

    # ── maintenance ───────────────────────────────────────────────────────────
    async def set_maintenance(self, status: bool):
        await self.config.update_one({"id": "bot_maintenance"},
            {"$set": {"status": status}}, upsert=True)

    async def get_maintenance(self) -> bool:
        doc = await self.config.find_one({"id": "bot_maintenance"})
        return doc["status"] if doc else False

    # ── Feature 16 — Granular Maintenance ─────────────────────────────────────
    async def set_feature_maintenance(self, feature: str, status: bool):
        """Toggle individual features: search, verify, index, broadcast."""
        await self.config.update_one({"id": "feature_maintenance"},
            {"$set": {f"features.{feature}": status}}, upsert=True)

    async def get_feature_maintenance(self, feature: str) -> bool:
        doc = await self.config.find_one({"id": "feature_maintenance"})
        if not doc:
            return False
        return doc.get("features", {}).get(feature, False)

    async def get_all_feature_maintenance(self) -> dict:
        doc = await self.config.find_one({"id": "feature_maintenance"})
        return (doc or {}).get("features", {})

    # ── Feature 8 — Subscription Plans ───────────────────────────────────────
    async def set_subscription(self, user_id: int, plan: str, days: int):
        expiry = datetime.now(pytz.utc) + timedelta(days=days)
        await self.col.update_one({"id": user_id},
            {"$set": {"subscription": {"plan": plan, "expiry": expiry}}},
            upsert=True)

    async def get_subscription(self, user_id: int) -> dict:
        doc = await self.col.find_one({"id": int(user_id)})
        sub = (doc or {}).get("subscription", {"plan": "free", "expiry": None})
        if sub.get("expiry") and sub["expiry"] < datetime.now(pytz.utc):
            sub = {"plan": "free", "expiry": None}
        return sub

    async def is_premium(self, user_id: int) -> bool:
        sub = await self.get_subscription(user_id)
        return sub["plan"] != "free"

    async def get_daily_download_count(self, user_id: int) -> int:
        tz = pytz.timezone("Asia/Kolkata")
        today_start = tz.localize(datetime.combine(date.today(), datetime.min.time()))
        return await self.analytics.count_documents(
            {"user_id": int(user_id), "action": "download",
             "timestamp": {"$gte": today_start}})

    # ── Feature 9 — User History & Favourites ────────────────────────────────
    async def add_to_history(self, user_id: int, file_id: str, file_name: str):
        entry = {"file_id": file_id, "file_name": file_name,
                 "timestamp": self._tz_now()}
        await self.col.update_one({"id": int(user_id)},
            {"$push": {"history": {"$each": [entry], "$slice": -20}}},
            upsert=True)

    async def get_history(self, user_id: int) -> list:
        doc = await self.col.find_one({"id": int(user_id)})
        return list(reversed((doc or {}).get("history", [])))[:10]

    async def add_favourite(self, user_id: int, file_id: str, file_name: str):
        entry = {"file_id": file_id, "file_name": file_name,
                 "added_at": self._tz_now()}
        await self.col.update_one({"id": int(user_id)},
            {"$addToSet": {"favourites": entry}}, upsert=True)

    async def remove_favourite(self, user_id: int, file_id: str):
        await self.col.update_one({"id": int(user_id)},
            {"$pull": {"favourites": {"file_id": file_id}}})

    async def get_favourites(self, user_id: int) -> list:
        doc = await self.col.find_one({"id": int(user_id)})
        return (doc or {}).get("favourites", [])

    # ── Feature 10 — Watch Keywords ───────────────────────────────────────────
    async def add_watch_keyword(self, user_id: int, keyword: str):
        kw = keyword.strip().lower()
        await self.col.update_one({"id": int(user_id)},
            {"$addToSet": {"watch_keywords": kw}}, upsert=True)
        await self.config.update_one({"id": "watch_index"},
            {"$addToSet": {f"kw.{kw}": int(user_id)}}, upsert=True)

    async def remove_watch_keyword(self, user_id: int, keyword: str):
        kw = keyword.strip().lower()
        await self.col.update_one({"id": int(user_id)},
            {"$pull": {"watch_keywords": kw}})
        await self.config.update_one({"id": "watch_index"},
            {"$pull": {f"kw.{kw}": int(user_id)}})

    async def get_watch_keywords(self, user_id: int) -> list:
        doc = await self.col.find_one({"id": int(user_id)})
        return (doc or {}).get("watch_keywords", [])

    async def get_all_watch_keywords(self) -> dict:
        doc = await self.config.find_one({"id": "watch_index"})
        return (doc or {}).get("kw", {})

    # ── Feature 11 — Referral System ─────────────────────────────────────────
    async def add_referral(self, referrer_id: int, referred_id: int):
        """Record a referral and reward the referrer with +1 day premium."""
        already = await self.col.find_one({"id": int(referred_id),
                                           "referred_by": {"$exists": True}})
        if already:
            return False
        await self.col.update_one({"id": int(referred_id)},
            {"$set": {"referred_by": int(referrer_id)}}, upsert=True)
        await self.col.update_one({"id": int(referrer_id)},
            {"$inc": {"referral_count": 1}}, upsert=True)
        return True

    async def get_referral_count(self, user_id: int) -> int:
        doc = await self.col.find_one({"id": int(user_id)})
        return (doc or {}).get("referral_count", 0)

    async def get_top_referrers(self, limit: int = 10) -> list:
        cursor = self.col.find({"referral_count": {"$gt": 0}},
                               {"id": 1, "name": 1, "referral_count": 1}
                               ).sort("referral_count", -1).limit(limit)
        return await cursor.to_list(length=limit)

    # ── Feature 15 — Analytics Tracking ──────────────────────────────────────
    async def track_event(self, user_id: int, action: str,
                          meta: dict = None):
        await self.analytics.insert_one({
            "user_id": int(user_id),
            "action": action,
            "meta": meta or {},
            "timestamp": self._tz_now()
        })

    async def get_popular_searches(self, limit: int = 10) -> list:
        pipeline = [
            {"$match": {"action": "search"}},
            {"$group": {"_id": "$meta.query", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        return await self.analytics.aggregate(pipeline).to_list(length=limit)

    async def get_analytics_summary(self) -> dict:
        tz = pytz.timezone("Asia/Kolkata")
        today_start = tz.localize(datetime.combine(date.today(), datetime.min.time()))
        total_searches = await self.analytics.count_documents({"action": "search"})
        total_downloads = await self.analytics.count_documents({"action": "download"})
        today_searches = await self.analytics.count_documents(
            {"action": "search", "timestamp": {"$gte": today_start}})
        today_downloads = await self.analytics.count_documents(
            {"action": "download", "timestamp": {"$gte": today_start}})
        return {"total_searches": total_searches, "total_downloads": total_downloads,
                "today_searches": today_searches, "today_downloads": today_downloads}

    async def cleanup_old_analytics(self, days: int = 90) -> int:
        cutoff = datetime.now(pytz.utc) - timedelta(days=days)
        result = await self.analytics.delete_many({"timestamp": {"$lt": cutoff}})
        return result.deleted_count

    # ── Feature 19 — API Key Rotation ────────────────────────────────────────
    async def set_api_key(self, service: str, key: str):
        await self.config.update_one({"id": "api_keys"},
            {"$set": {f"keys.{service}": key}}, upsert=True)

    async def get_api_key(self, service: str) -> str:
        doc = await self.config.find_one({"id": "api_keys"})
        return (doc or {}).get("keys", {}).get(service, "")

    # ── Feature 13 — Auto-index state ────────────────────────────────────────
    async def set_last_indexed_msg_id(self, channel_id: int, msg_id: int):
        await self.config.update_one({"id": "index_state"},
            {"$set": {f"channels.{channel_id}": msg_id}}, upsert=True)

    async def get_last_indexed_msg_id(self, channel_id: int) -> int:
        doc = await self.config.find_one({"id": "index_state"})
        return (doc or {}).get("channels", {}).get(str(channel_id), 0)


    # ── File Notification Subscription ────────────────────────────────────────
    async def set_notify_status(self, user_id: int, status: bool):
        await self.col.update_one(
            {"id": int(user_id)},
            {"$set": {"new_file_notify": status}},
            upsert=True
        )

    async def get_notify_status(self, user_id: int) -> bool:
        doc = await self.col.find_one({"id": int(user_id)})
        return (doc or {}).get("new_file_notify", False)

    async def get_notify_subscribers(self) -> list:
        """Return list of user IDs who have new_file_notify = True."""
        cursor = self.col.find({"new_file_notify": True}, {"id": 1})
        return [doc["id"] async for doc in cursor]

    # ── Admin Settings Panel ───────────────────────────────────────────────────
    async def get_bot_admin_settings(self) -> dict:
        doc = await self.config.find_one({"id": "admin_settings"})
        return dict(doc) if doc else {}

    async def save_bot_admin_settings(self, settings: dict):
        settings.pop("_id", None)
        await self.config.update_one(
            {"id": "admin_settings"},
            {"$set": settings},
            upsert=True
        )


db = Database(DATABASE_URI, DATABASE_NAME)
