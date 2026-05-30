import re
from os import environ

id_pattern = re.compile(r'^-?\d+$')


def is_enabled(value, default):
    if isinstance(value, bool):
        return value
    if str(value).lower() in ["true", "yes", "1", "enable", "y"]:
        return True
    elif str(value).lower() in ["false", "no", "0", "disable", "n"]:
        return False
    return default


# ── Core ─────────────────────────────────────────────────────────────────────
SESSION   = environ.get('SESSION', 'Media_search')
API_ID    = int(environ['API_ID'])
API_HASH  = environ['API_HASH']
BOT_TOKEN = environ['BOT_TOKEN']

# ── Feature 1/2/3 — Redis ────────────────────────────────────────────────────
REDIS_URL = environ.get('REDIS_URL', 'redis://localhost:6379')

# ── Feature 21 — Sentry ──────────────────────────────────────────────────────
SENTRY_DSN = environ.get('SENTRY_DSN', '')

# ── Metadata extraction (Layer 2)
ENABLE_METADATA_DOWNLOAD = is_enabled(environ.get('ENABLE_METADATA_DOWNLOAD', 'False'), False)

# ── Feature 20 — Multi-bot token pool ────────────────────────────────────────
# Space-separated extra bot tokens; primary is BOT_TOKEN above
EXTRA_BOT_TOKENS = environ.get('EXTRA_BOT_TOKENS', '').split()

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URI    = environ.get('DATABASE_URI', '')
DATABASE_NAME   = environ.get('DATABASE_NAME', 'Rajappan')
COLLECTION_NAME = environ.get('COLLECTION_NAME', 'Telegram_files')

# ── Bot settings ─────────────────────────────────────────────────────────────
CACHE_TIME         = int(environ.get('CACHE_TIME', 300))
USE_CAPTION_FILTER = is_enabled(environ.get('USE_CAPTION_FILTER', 'False'), False)
PICS       = environ.get('PICS', '').split()
MELCOW_PIC = environ.get('MELCOW_PIC', '').split()
PORT       = environ.get('PORT', '8080')

# ── Access control ───────────────────────────────────────────────────────────
ADMINS      = [int(a) for a in environ.get('ADMINS', '').split() if id_pattern.search(a)]
CHANNELS    = [int(c) for c in environ.get('CHANNELS', '0').split() if id_pattern.search(c)]
auth_users  = [int(u) for u in environ.get('AUTH_USERS', '').split() if id_pattern.search(u)]
AUTH_USERS  = (auth_users + ADMINS) if auth_users else []
auth_channel = environ.get('AUTH_CHANNEL')
auth_grp     = environ.get('AUTH_GROUP')
AUTH_CHANNEL = int(auth_channel) if auth_channel and id_pattern.search(auth_channel) else None
AUTH_GROUPS  = [int(c) for c in auth_grp.split()] if auth_grp else None

# ── Channels & logs ──────────────────────────────────────────────────────────
LOG_CHANNEL       = int(environ.get('LOG_CHANNEL', 0))
INDEX_REQ_CHANNEL = int(environ.get('INDEX_REQ_CHANNEL', LOG_CHANNEL))
REQ_CHANNEL       = int(environ.get('REQ_CHANNEL', 0))
FILE_CHANNEL      = int(environ.get('FILE_CHANNEL', 0))
FILE_FORWARD      = environ.get('FILE_FORWARD', '')
UPDATE_CHANNEL    = environ.get('UPDATE_CHANNEL', '')
SUPPORT_CHAT      = environ.get('SUPPORT_CHAT', '')

# ── Verification & shortlinks ─────────────────────────────────────────────────
IS_VERIFY       = is_enabled(environ.get('IS_VERIFY', 'True'), True)
HOW_TO_VERIFY   = environ.get('HOW_TO_VERIFY', '')
VERIFY2_URL     = environ.get('VERIFY2_URL', 'kingurl.in')
VERIFY2_API     = environ.get('VERIFY2_API', '')
SHORTLINK_URL   = environ.get('SHORTLINK_URL', 'runurl.in')
SHORTLINK_API   = environ.get('SHORTLINK_API', '')
IS_SHORTLINK    = is_enabled(environ.get('IS_SHORTLINK', 'False'), False)

# ── Feature 8 — Subscription daily limits ────────────────────────────────────
FREE_DAILY_LIMIT    = int(environ.get('FREE_DAILY_LIMIT', 3))
BASIC_DAILY_LIMIT   = int(environ.get('BASIC_DAILY_LIMIT', 20))

# ── File / caption ────────────────────────────────────────────────────────────
CUSTOM_FILE_CAPTION = environ.get('CUSTOM_FILE_CAPTION', None)
BATCH_FILE_CAPTION  = environ.get('BATCH_FILE_CAPTION', CUSTOM_FILE_CAPTION)
PROTECT_CONTENT     = is_enabled(environ.get('PROTECT_CONTENT', 'False'), False)
AUTO_DELETE         = is_enabled(environ.get('AUTO_DELETE', 'False'), False)

# ── IMDb & UI ─────────────────────────────────────────────────────────────────
IMDB                 = is_enabled(environ.get('IMDB', 'False'), False)
IMDB_TEMPLATE        = environ.get('IMDB_TEMPLATE', '')
LONG_IMDB_DESCRIPTION = is_enabled(environ.get('LONG_IMDB_DESCRIPTION', 'False'), False)
SINGLE_BUTTON        = is_enabled(environ.get('SINGLE_BUTTON', 'True'), True)
SPELL_CHECK_REPLY    = is_enabled(environ.get('SPELL_CHECK_REPLY', 'True'), True)
MAX_LIST_ELM         = environ.get('MAX_LIST_ELM', None)
P_TTI_SHOW_OFF       = is_enabled(environ.get('P_TTI_SHOW_OFF', 'False'), False)
MELCOW_NEW_USERS     = is_enabled(environ.get('MELCOW_NEW_USERS', 'True'), True)

# ── LOG_STR ────────────────────────────────────────────────────────────────────
LOG_STR = "Current Customized Configurations:\n"
LOG_STR += f"IMDB: {'enabled' if IMDB else 'disabled'}\n"
LOG_STR += f"P_TTI_SHOW_OFF: {'enabled' if P_TTI_SHOW_OFF else 'disabled'}\n"
LOG_STR += f"SINGLE_BUTTON: {'enabled' if SINGLE_BUTTON else 'disabled'}\n"
LOG_STR += f"PROTECT_CONTENT: {'enabled' if PROTECT_CONTENT else 'disabled'}\n"
LOG_STR += f"AUTO_DELETE: {'enabled' if AUTO_DELETE else 'disabled'}\n"
LOG_STR += f"IS_VERIFY: {'enabled' if IS_VERIFY else 'disabled'}\n"
LOG_STR += f"REDIS_URL: {'set' if REDIS_URL else 'NOT SET — in-memory fallback'}\n"
LOG_STR += f"SENTRY_DSN: {'set' if SENTRY_DSN else 'not set'}\n"
