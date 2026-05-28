# 🎬 True — Telegram File Search Bot

A powerful Telegram bot that indexes media files from channels and delivers them to users on demand — with inline search, IMDb integration, force-subscribe, verification tokens, and full admin controls.

---

## ✨ Features

- 🔍 **Inline & group-based file search** with fuzzy spell-check fallback
- 📁 **Auto-indexing** of media from configured Telegram channels
- 🎭 **IMDb integration** — fetch movie posters, ratings, cast, and plot
- 🔐 **Force-subscribe** gate before users can access files
- 🪙 **Token-based verification** system with 12-hour validity
- 🔗 **Shortlink monetisation** via configurable shortener APIs
- 📢 **Broadcast** to all users and groups (with cancel support)
- 🛡️ **Maintenance mode** — freeze the bot for all non-admins instantly
- 🚫 **Ban/unban** users and disable/enable groups
- 📊 **Daily stats report** auto-sent to your log channel at 23:59
- 🔒 **Content protection** — optional `protect_content` on all sends
- 🗑️ **Auto-delete** welcome messages after a configurable delay
- 🌐 **Aiohttp web server** — keeps the bot alive on platforms like Render

---

## 🚀 Deploy

### Prerequisites
- Python 3.10+
- MongoDB Atlas URI (or self-hosted)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org)

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Locally
```bash
python bot.py
```

### Deploy on Render
1. Create a **Worker** service (not Web Service)
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `python bot.py`
4. Add all environment variables from the table below

---

## ⚙️ Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `API_ID` | Telegram API ID from my.telegram.org |
| `API_HASH` | Telegram API Hash from my.telegram.org |
| `BOT_TOKEN` | Bot token from @BotFather |
| `DATABASE_URI` | MongoDB connection URI |
| `LOG_CHANNEL` | Channel/group ID for bot logs (integer) |
| `CHANNELS` | Space-separated IDs of channels to index files from |

### Optional — Bot Behaviour

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION` | `Media_search` | Pyrogram session name |
| `DATABASE_NAME` | `Rajappan` | MongoDB database name |
| `COLLECTION_NAME` | `Telegram_files` | MongoDB collection name |
| `CACHE_TIME` | `300` | Inline query cache time (seconds) |
| `PORT` | `8080` | Port for the keep-alive web server |

### Optional — Access Control

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMINS` | _(empty)_ | Space-separated admin user IDs |
| `AUTH_USERS` | _(empty)_ | Space-separated IDs of extra authorised users |
| `AUTH_CHANNEL` | _(none)_ | Channel ID for force-subscribe gate |
| `AUTH_GROUP` | _(none)_ | Space-separated group IDs to restrict usage to |

### Optional — Verification & Shortlinks

| Variable | Default | Description |
|----------|---------|-------------|
| `IS_VERIFY` | `True` | Enable token-based verification |
| `HOW_TO_VERIFY` | _(link)_ | Tutorial link shown in verify prompt |
| `SHORTLINK_URL` | `runurl.in` | Primary shortener domain |
| `SHORTLINK_API` | _(empty)_ | Primary shortener API key |
| `VERIFY2_URL` | `kingurl.in` | Secondary shortener domain |
| `VERIFY2_API` | _(empty)_ | Secondary shortener API key |
| `IS_SHORTLINK` | `False` | Enable shortlink wrapping for file links |

### Optional — File & Caption Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CUSTOM_FILE_CAPTION` | _(none)_ | Caption template: `{file_name}`, `{file_size}`, `{file_caption}` |
| `BATCH_FILE_CAPTION` | _(same as above)_ | Caption template for batch sends |
| `PROTECT_CONTENT` | `False` | Prevent forwarding of sent files |
| `USE_CAPTION_FILTER` | `False` | Also search inside file captions |
| `AUTO_DELETE` | `False` | Auto-delete welcome messages after 10 min |
| `FILE_CHANNEL` | `0` | Channel ID where files are forwarded before PM |
| `FILE_FORWARD` | _(link)_ | Fallback link if user can't access file channel |

### Optional — IMDb & UI

| Variable | Default | Description |
|----------|---------|-------------|
| `IMDB` | `False` | Show IMDb data with search results |
| `IMDB_TEMPLATE` | _(default template)_ | HTML template for IMDb display |
| `LONG_IMDB_DESCRIPTION` | `False` | Show full plot instead of short excerpt |
| `SINGLE_BUTTON` | `True` | Show file name + size in one button |
| `SPELL_CHECK_REPLY` | `True` | Suggest similar titles when nothing found |
| `MAX_LIST_ELM` | _(none)_ | Limit cast/crew list length in IMDb template |
| `P_TTI_SHOW_OFF` | `False` | Redirect group users to bot PM for file delivery |
| `MELCOW_NEW_USERS` | `True` | Send welcome photo when new member joins a group |
| `PICS` | _(telegra.ph URLs)_ | Space-separated URLs for `/start` photo rotation |
| `MELCOW_PIC` | _(telegra.ph URLs)_ | Space-separated URLs for welcome photos |

### Optional — Channels & Notifications

| Variable | Default | Description |
|----------|---------|-------------|
| `UPDATE_CHANNEL` | _(link)_ | Your update channel link (shown in buttons) |
| `SUPPORT_CHAT` | _(link)_ | Your support group link |
| `INDEX_REQ_CHANNEL` | _(same as LOG_CHANNEL)_ | Channel for index requests from non-admins |
| `REQ_CHANNEL` | `0` | Request channel ID |

---

## 🤖 Commands

### User Commands
| Command | Description |
|---------|-------------|
| `/start` | Start the bot / get a file via deep link |
| `/verification` | Check your current verification status |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/broadcast` | Broadcast a message to all users (reply to a message) |
| `/pinbroadcast` | Broadcast and pin the message |
| `/grp_broadcast` | Broadcast to all groups |
| `/pin_grp_broadcast` | Broadcast to all groups and pin |
| `/ban <user_id>` | Ban a user |
| `/unban <user_id>` | Unban a user |
| `/disable <chat_id> [reason]` | Disable a group |
| `/enable <chat_id>` | Re-enable a group |
| `/maintenance on\|off` | Toggle maintenance mode |
| `/stats` | Show total files, users, chats and DB size |
| `/invite <chat_id>` | Generate an invite link for a chat |
| `/leave <chat_id>` | Make the bot leave a chat |
| `/users` | List all users in the database |
| `/chats` | List all groups in the database |
| `/channel` | Show all indexed channels |
| `/logs` | Get the bot log file |
| `/delete` | Delete a file from the database (reply to file) |
| `/setskip <number>` | Set the message offset for indexing |

---

## 📂 Project Structure

```
.
├── bot.py                  # Entry point — Bot class and startup
├── info.py                 # All config via environment variables
├── utils.py                # Shared helpers, temp state, verification logic
├── Script.py               # All bot message templates
├── requirements.txt        # Python dependencies
├── logging.conf            # Logging configuration
├── database/
│   ├── ia_filterdb.py      # Media indexing and search (MongoDB + umongo)
│   └── users_chats_db.py   # Users, groups, bans, settings, verification
└── plugins/
    ├── __init__.py         # Aiohttp web server setup
    ├── route.py            # Health-check route
    ├── banned.py           # Banned user/chat filters
    ├── broadcast.py        # Broadcast to users and groups
    ├── channel.py          # Auto-save media from indexed channels
    ├── commands.py         # /start, file delivery, batch/DSTORE, verify
    ├── index.py            # Manual channel indexing
    ├── inline.py           # Inline query handler
    ├── maintenance.py      # Maintenance mode interceptor
    ├── p_ttishow.py        # Group join/leave logging, admin group commands
    ├── pm_filter.py        # Auto-filter, callbacks, IMDb, spell-check
    └── route.py            # Aiohttp keep-alive route
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Telegram client | [Pyrofork](https://github.com/Mayuri-Chan/pyrofork) (Pyrogram fork) |
| Database | MongoDB via [Motor](https://motor.readthedocs.io/) (async) + [uMongo](https://umongo.readthedocs.io/) |
| Web server | [aiohttp](https://docs.aiohttp.org/) |
| IMDb data | [IMDbPY](https://imdbpy.github.io/) |
| HTML parsing | [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) |
| Hosting | [Render](https://render.com) (Worker service) |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
