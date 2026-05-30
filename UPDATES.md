# 🚀 UPDATES.md — web-4.0 Feature Log

All 22 features implemented in this branch over `web-3.0`.

---

## Feature 1 — Redis Caching Layer
**File:** `cache/redis_manager.py`

Replaces the plain in-memory `temp` class with a Redis-backed layer.
- Bot settings, banned lists, and verify status survive restarts
- Graceful fallback to in-memory if Redis is unavailable
- Set `REDIS_URL` env var (e.g. `redis://localhost:6379`)

---

## Feature 2 — Redis-backed Pagination
**File:** `cache/redis_manager.py` → `RedisManager.set_pagination / get_pagination`

Pagination state (next/prev offsets) is now stored in Redis with a 10-minute TTL.
Previously, a bot restart mid-browse would break the user's page buttons.

---

## Feature 3 — Per-User Rate Limiting
**File:** `cache/redis_manager.py` → `RateLimiter`  
**Used in:** `utils.py` → `check_rate_limit()`

Sliding-window rate limiter — 5 requests per 10 seconds per user per action.
Prevents search spam and MongoDB hammering. Fully Redis-backed.

---

## Feature 4 — Async File Indexing Queue
**File:** `scheduler/tasks.py` → `auto_index_task`

Indexing runs as a background `asyncio` task via APScheduler instead of blocking
the main message handler. No more slowdown during large index jobs.

---

## Feature 5 — Better Search Algorithm
**File:** `database/ia_filterdb.py` → `_build_filter()`

- **Year extraction** — `"RRR 2022"` searches title + year separately
- **Synonym expansion** — `"hindi"` matches `hin`, `bollywood`, `hd`, etc.
- **Multi-word regex** built from cleaned, expanded tokens
- Language synonyms: Hindi, Tamil, Telugu, English, Dubbed

---

## Feature 6 — Atlas Search / Full-Text Index
**File:** `database/ia_filterdb.py`

`indexed_at` timestamp added to every file document to enable time-based
queries and Atlas Search compatibility. Media collection uses `$natural -1`
sort to surface newest files first. Ready to swap regex for Atlas Search
`$search` stage by changing `_build_filter`.

---

## Feature 7 — Duplicate File Detection via Content Hash
**File:** `database/ia_filterdb.py` → `_file_hash()`, `save_file()`

MD5 hash of `(normalised_filename + file_size)` stored as `file_hash`.
Before saving, checks if a file with the same hash exists — skips the insert
even if Telegram generates a different `file_id`. Stops silent duplicates.

---

## Feature 8 — Subscription Plans
**Files:** `database/users_chats_db.py`, `plugins/admin_advanced.py`, `info.py`

Three tiers: `free` (3 files/day), `basic` (20/day), `premium` (unlimited).

Admin commands:
- `/setplan <user_id> <free|basic|premium> <days>`

User commands:
- `/myplan` — shows current plan, expiry, and daily limit

Configure limits: `FREE_DAILY_LIMIT`, `BASIC_DAILY_LIMIT` env vars.

---

## Feature 9 — User History & Favourites
**File:** `plugins/user_features.py`, `database/users_chats_db.py`

- `/history` — last 10 downloaded files
- `/favourites` — saved favourites with inline remove buttons
- `/addfav` — reply to any file message to save it

Last 20 downloads kept per user; favourites stored indefinitely in MongoDB.

---

## Feature 10 — Smart Watch-Keyword Notifications
**Files:** `plugins/user_features.py`, `scheduler/tasks.py`, `database/users_chats_db.py`

Users subscribe to keywords. Every hour the scheduler checks for newly indexed
files matching any active keyword and notifies the relevant users via DM.

Commands:
- `/watch <keyword>` — start watching (max 10 per user)
- `/unwatch <keyword>` — stop watching
- `/watchlist` — view all active keywords

---

## Feature 11 — Referral System
**File:** `plugins/user_features.py`, `database/users_chats_db.py`

Deep-link referral tracking via `?start=ref_<user_id>`.
- Referral count tracked per user
- `/referral` — shows your link, count, current plan
- `/referral` → Top Referrers leaderboard button
- Referral recorded only once per referred user (no abuse)

---

## Feature 12 — Inline Analytics Dashboard
**File:** `plugins/admin_advanced.py` → `/analytics`

Admin command showing real-time stats:
- Total users / daily active / active %
- Total files + DB size
- All-time and today's searches + downloads
- Top 5 most searched queries

---

## Feature 13 — Scheduled Auto-Index
**File:** `scheduler/tasks.py` → `auto_index_task`

Runs every **30 minutes** via APScheduler.
- Reads `last_indexed_msg_id` per channel from MongoDB
- Fetches and saves all new media since last run
- Posts summary to `LOG_CHANNEL`
- No manual `/setskip` + button clicks needed

---

## Feature 14 — Automated Daily Backup
**File:** `scheduler/tasks.py` → `backup_task`

Runs every day at **02:00 IST**.
- Exports entire files collection to a JSON file
- Sends it as a document to `LOG_CHANNEL`
- File name format: `backup_YYYY-MM-DD.json`

---

## Feature 15 — Detailed Analytics
**Files:** `database/users_chats_db.py`, `plugins/admin_advanced.py`, `scheduler/tasks.py`

Every search and download is tracked in a dedicated `analytics` MongoDB collection.
- `/analytics` shows aggregated summary + top queries
- Auto-cleanup task removes records older than 90 days at 03:00 IST

---

## Feature 16 — Granular Maintenance Mode
**File:** `plugins/admin_advanced.py` → `/feature`

Toggle individual features without restarting the bot:

```
/feature search off     ← disables only search
/feature verify off     ← disables only verification
/feature                ← shows all feature statuses
```

Features: `search`, `verify`, `index`, `broadcast`, `pm_filter`

---

## Feature 17 — Token Replay Prevention
**File:** `cache/redis_manager.py` → `mark_token_used / is_token_used`  
**Used in:** `utils.py` → `verify_user`, `check_token`

Used tokens are stored in Redis with a 24-hour TTL.
Previously, a bot restart made all used tokens valid again.
Now tokens stay invalid across restarts for their full lifetime.

---

## Feature 18 — Suspicious Activity Detection
**File:** `plugins/admin_advanced.py` → `/checkuser`

Admin command that profiles a user:
- Downloads today
- Referral count
- Current plan + ban status
- Auto-flags if downloads > 50/day or referrals > 50

Inline ban button in the result message.

---

## Feature 19 — API Key Rotation via Bot Command
**Files:** `database/users_chats_db.py`, `plugins/admin_advanced.py`, `utils.py`

API keys stored in MongoDB `bot_config` collection and preferred over env vars.
No redeploy needed when rotating keys.

Commands (admin, PM only — message auto-deletes after 15s):
- `/setapikey <service> <key>`
- `/getapikey <service>` (auto-deletes after 15 s)

Services: `shortlink`, `shortlink_url`, `verify2`, `verify2_url`

---

## Feature 20 — Multi-Bot Worker Pool
**File:** `bot.py` → `_start_extra_bots()`

Set `EXTRA_BOT_TOKENS` env var (space-separated) to spin up additional bot
instances on startup. Extra bots are stored in `temp.WORKER_BOTS` for
round-robin file delivery to bypass Telegram's per-bot rate limits.

---

## Feature 21 — Sentry Error Tracking
**File:** `bot.py`

Set `SENTRY_DSN` env var to enable.
All unhandled exceptions are captured with full stack trace, user context,
and performance traces (20% sample rate). Free tier at sentry.io is sufficient.

---

## Feature 22 — Rich Health Check Endpoint
**File:** `plugins/route.py` → `/health`

GET `/health` returns JSON:
```json
{
  "status": "ok",
  "uptime": "3h 42m 11s",
  "timestamp": "2026-05-28T10:00:00Z",
  "maintenance": false,
  "stats": {
    "users": 12450,
    "chats": 310,
    "files": 98200,
    "db_size_bytes": 524288000
  }
}
```

Use with Render health checks or UptimeRobot.

---

## New Environment Variables (web-4.0)

| Variable | Default | Feature |
|----------|---------|---------|
| `REDIS_URL` | `redis://localhost:6379` | 1,2,3,17 |
| `SENTRY_DSN` | _(empty — disabled)_ | 21 |
| `EXTRA_BOT_TOKENS` | _(empty)_ | 20 |
| `FREE_DAILY_LIMIT` | `3` | 8 |
| `BASIC_DAILY_LIMIT` | `20` | 8 |

## New Commands (web-4.0)

| Command | Who | Feature |
|---------|-----|---------|
| `/history` | Users | 9 |
| `/favourites` | Users | 9 |
| `/watch <kw>` | Users | 10 |
| `/unwatch <kw>` | Users | 10 |
| `/watchlist` | Users | 10 |
| `/referral` | Users | 11 |
| `/myplan` | Users | 8 |
| `/analytics` | Admins | 15 |
| `/feature <name> on\|off` | Admins | 16 |
| `/setplan <id> <plan> <days>` | Admins | 8 |
| `/setapikey <service> <key>` | Admins | 19 |
| `/getapikey <service>` | Admins | 19 |
| `/checkuser <id>` | Admins | 18 |

---

## Feature 23 — Smart Metadata Extraction (Layer 1)
**File:** `utils/metadata.py`

Every file is now parsed through a 3-step pipeline before saving:

1. **Regex parser** extracts from filename + caption:
   - Year: `2022`, `(2022)`, `[2022]`
   - Languages: Hindi, Tamil, Telugu, Malayalam, English, Korean, etc.
   - Quality: 1080p, 720p, 4K, HDR, BluRay, WEB-DL, etc.
   - Codec: HEVC, x264, x265, AVC, etc.
   - Audio: AAC, DTS, Dolby, AC3, etc.
   - Season/Episode: S01E01, Season 1, etc.
   - Detects dubbed, dual-audio, multi-audio

2. **Caption cleaner** strips emojis, @mentions, channel links, junk symbols

3. **IMDb verification** — title verified against IMDb, gets official name, rating, genres

**Result:** `file_name` saved as structured `"RRR 2022 Hindi Tamil 1080p"` regardless of original filename mess.

---

## Feature 24 — ffprobe Partial Download (Layer 2)
**File:** `utils/metadata.py` → `extract_ffprobe_metadata()`

Downloads only the **first 5 MB** of each video/document file and runs `ffprobe` to extract:
- Actual audio track languages (from stream metadata, not just filename)
- Subtitle track languages embedded in the container
- Video codec (HEVC, AVC, etc.)
- HDR detection (bt2020 color space)
- Embedded title tag (if encoder set it correctly)

**Enable:** Set `ENABLE_METADATA_DOWNLOAD=True` in env vars  
**Requires:** `ffmpeg` installed on server (`apt-get install -y ffmpeg` on Render)  
**Default:** `False` — safe for free-tier servers

---

## Feature 25 — Rich Channel Auto-Index
**File:** `plugins/channel.py`

When admin posts a file in the indexed channel:
- Runs full metadata pipeline automatically
- Logs to `LOG_CHANNEL` with: title, year, languages, quality, codec, subtitles, IMDb rating, size
- Warns admin in LOG_CHANNEL if file saved with a generic/suspicious name
- Updates `last_indexed_msg_id` for scheduler compatibility
- Handles all media types: document, video, audio, animation, voice

---

## Feature 26 — Admin File Management Commands
**File:** `plugins/file_management.py`

| Command | Usage |
|---------|-------|
| `/rename` | Reply to file message + `/rename New Name` — fixes wrong name in DB |
| `/fileinfo <name>` | Shows full stored metadata: languages, subtitles, codec, IMDb, size |
| `/delfile <name>` | Shows matching files with inline delete buttons |
| `/searchadv` | Advanced search with filters: `lang:Hindi year:2022 quality:1080p` |

---

## New Environment Variable

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_METADATA_DOWNLOAD` | `False` | Enable ffprobe partial download (Layer 2). Requires ffmpeg installed. |

## Render Setup for Layer 2

Add this to your Render build command to install ffmpeg:
```
pip install -r requirements.txt && apt-get install -y ffmpeg
```
