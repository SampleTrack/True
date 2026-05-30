"""
Feature: Accurate file storage + smart search
- Rich schema: title, year, languages, quality, codec, subtitles, IMDb data
- Search matches on title, languages, year, quality — not just raw filename
- Content-hash dedup (filename + size)
"""
import logging
import re
import base64
import hashlib
from struct import pack
from datetime import datetime
import pytz
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import DATABASE_URI, DATABASE_NAME, COLLECTION_NAME, USE_CAPTION_FILTER

logger = logging.getLogger(__name__)
client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)


@instance.register
class Media(Document):
    # ── core ──────────────────────────────────────────────────────────────────
    file_id    = fields.StrField(attribute="_id")
    file_ref   = fields.StrField(allow_none=True)
    file_name  = fields.StrField(required=True)   # display name — what users search
    file_size  = fields.IntField(required=True)
    file_type  = fields.StrField(allow_none=True)
    mime_type  = fields.StrField(allow_none=True)
    caption    = fields.StrField(allow_none=True)
    file_hash  = fields.StrField(allow_none=True)
    indexed_at = fields.DateTimeField(allow_none=True)

    # ── metadata (Layer 1 + 2) ────────────────────────────────────────────────
    title      = fields.StrField(allow_none=True)   # bare title: "RRR"
    year       = fields.StrField(allow_none=True)   # "2022"
    languages  = fields.ListField(fields.StrField(), default=list)  # ["Hindi","Tamil"]
    quality    = fields.StrField(allow_none=True)   # "1080p"
    codec      = fields.StrField(allow_none=True)   # "HEVC"
    audio_codec= fields.StrField(allow_none=True)   # "AAC"
    subtitles  = fields.ListField(fields.StrField(), default=list)
    is_dubbed  = fields.BoolField(default=False)
    is_series  = fields.BoolField(default=False)
    episode    = fields.StrField(allow_none=True)   # "S01E01"
    is_hdr     = fields.BoolField(default=False)
    duration   = fields.IntField(allow_none=True)
    width      = fields.IntField(allow_none=True)
    height     = fields.IntField(allow_none=True)

    # ── IMDb ──────────────────────────────────────────────────────────────────
    imdb_id     = fields.StrField(allow_none=True)
    imdb_rating = fields.StrField(allow_none=True)
    genres      = fields.ListField(fields.StrField(), default=list)

    class Meta:
        indexes = ("$file_name", "$title")
        collection_name = COLLECTION_NAME


async def ensure_indexes():
    """Create indexes including file_hash for fast dedup checks."""
    col = db[COLLECTION_NAME]
    await col.create_index("file_hash", sparse=True)
    await col.create_index("languages")
    await col.create_index("year")
    await col.create_index("quality")
    await col.create_index([("title", "text"), ("file_name", "text")])
    logger.info("DB indexes ensured")


def _file_hash(file_name: str, file_size: int) -> str:
    raw = f"{file_name.lower().strip()}:{file_size}"
    return hashlib.md5(raw.encode()).hexdigest()


async def save_file(media):
    """Save file with full metadata. Skips true duplicates via content hash."""
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"(_|-|\.|\+)", " ", str(media.file_name))
    f_hash = _file_hash(file_name, media.file_size)

    existing = await Media.find_one({"file_hash": f_hash})
    if existing:
        logger.info(f"Duplicate skipped: {file_name}")
        return False, 0

    tz = pytz.timezone("Asia/Kolkata")
    try:
        file = Media(
            file_id    = file_id,
            file_ref   = file_ref,
            file_name  = file_name,
            file_size  = media.file_size,
            file_type  = media.file_type,
            mime_type  = media.mime_type,
            caption    = media.caption.html if media.caption else None,
            file_hash  = f_hash,
            indexed_at = datetime.now(tz),
            # ── metadata fields from build_file_metadata() ────────────────
            title      = getattr(media, "title", None),
            year       = getattr(media, "year", None),
            languages  = getattr(media, "languages", []),
            quality    = getattr(media, "quality", None),
            codec      = getattr(media, "codec", None),
            audio_codec= getattr(media, "audio_codec", None),
            subtitles  = getattr(media, "subtitles", []),
            is_dubbed  = getattr(media, "is_dubbed", False),
            is_series  = getattr(media, "is_series", False),
            episode    = getattr(media, "episode", None),
            is_hdr     = getattr(media, "is_hdr", False),
            duration   = getattr(media, "duration", None),
            width      = getattr(media, "width", None),
            height     = getattr(media, "height", None),
            imdb_id    = getattr(media, "imdb_id", None),
            imdb_rating= getattr(media, "imdb_rating", None),
            genres     = getattr(media, "genres", []),
        )
    except ValidationError:
        logger.exception("Validation error saving file")
        return False, 2

    try:
        await file.commit()
    except DuplicateKeyError:
        logger.warning(f"Duplicate file_id: {file_name}")
        return False, 0

    logger.info(f"Saved: {file_name}")
    try:
        from plugins.file_notify import queue_new_file
        queue_new_file(file_name, file_id)
    except Exception:
        pass
    return True, 1


def _build_search_filter(query: str, file_type=None,
                          language=None, year=None, quality=None) -> dict:
    """
    Build a MongoDB filter that searches across:
      - file_name (regex — broad match)
      - title     (regex — precise match)
      - languages (exact array match)
      - year      (exact match)
      - quality   (exact match)
    """
    query = query.strip()
    if not query:
        base_filter = {}
    else:
        # Extract year/language/quality hints from the query itself
        from utils.metadata import parse_tags, extract_clean_title, YEAR_RE, LANGUAGE_RE, QUALITY_RE
        auto_tags  = parse_tags(query)
        clean_title = extract_clean_title(query)

        # Merge explicit params with auto-detected
        year     = year     or auto_tags["year"]
        quality  = quality  or auto_tags["quality"]
        language = language or (auto_tags["languages"][0] if auto_tags["languages"] else None)

        # Build regex from clean title (no year/lang/quality noise)
        search_term = clean_title if clean_title and len(clean_title) > 1 else query
        try:
            regex = re.compile(search_term.replace(" ", r".*[\s\.\+\-_]"), re.IGNORECASE)
        except re.error:
            try:
                regex = re.compile(re.escape(search_term), re.IGNORECASE)
            except re.error:
                return None

        if USE_CAPTION_FILTER:
            base_filter = {"$or": [
                {"file_name": regex},
                {"title": regex},
                {"caption": regex}
            ]}
        else:
            base_filter = {"$or": [
                {"file_name": regex},
                {"title": regex}
            ]}

    # Exact-match filters narrow results precisely
    if language:
        base_filter["languages"] = {
            "$elemMatch": {"$regex": language, "$options": "i"}
        }
    if year:
        base_filter["year"] = str(year)
    if quality:
        base_filter["quality"] = {"$regex": quality, "$options": "i"}
    if file_type:
        base_filter["file_type"] = file_type

    return base_filter


async def get_search_results(query, file_type=None, max_results=10,
                              offset=0, filter=False,
                              language=None, year=None, quality=None):
    """Return (files, next_offset, total_results)."""
    search_filter = _build_search_filter(
        query, file_type, language, year, quality)
    if search_filter is None:
        return [], "", 0

    total_results = await Media.count_documents(search_filter)
    next_offset = offset + max_results
    if next_offset > total_results:
        next_offset = ""

    cursor = Media.find(search_filter)
    cursor.sort("$natural", -1)
    cursor.skip(offset).limit(max_results)
    files = await cursor.to_list(length=max_results)
    return files, next_offset, total_results


async def get_file_details(query):
    cursor = Media.find({"file_id": query})
    return await cursor.to_list(length=1)


# ── encoding helpers ──────────────────────────────────────────────────────────
def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")


def unpack_new_file_id(new_file_id):
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack("<iiqq", int(decoded.file_type), decoded.dc_id,
             decoded.media_id, decoded.access_hash))
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref
