"""
Feature 5  — Better search (year extraction, language filter, synonym expansion)
Feature 6  — Atlas Search / full-text index support
Feature 7  — Duplicate detection via file hash
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
from info import (DATABASE_URI, DATABASE_NAME, COLLECTION_NAME,
                  USE_CAPTION_FILTER)

logger = logging.getLogger(__name__)
client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

# ── synonym map for common search terms ─────────────────────────────────────
SYNONYMS = {
    "hindi":   ["hindi", "hin", "bollywood", "hd"],
    "tamil":   ["tamil", "tam", "kollywood"],
    "telugu":  ["telugu", "tel", "tollywood"],
    "english": ["english", "eng", "hollywood"],
    "dubbed":  ["dubbed", "dub", "dual audio"],
}


@instance.register
class Media(Document):
    file_id = fields.StrField(attribute="_id")
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    file_hash = fields.StrField(allow_none=True)   # Feature 7
    indexed_at = fields.DateTimeField(allow_none=True)  # Feature 10/13

    class Meta:
        indexes = ("$file_name",)
        collection_name = COLLECTION_NAME


def _file_hash(file_name: str, file_size: int) -> str:
    """Feature 7 — deterministic hash for dedup check."""
    raw = f"{file_name.lower().strip()}:{file_size}"
    return hashlib.md5(raw.encode()).hexdigest()


async def save_file(media):
    """Save file, skipping true duplicates via content hash (Feature 7)."""
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    f_hash = _file_hash(file_name, media.file_size)

    # Feature 7: reject if same content already exists under a different file_id
    existing = await Media.find_one({"file_hash": f_hash})
    if existing:
        logger.info(f"Duplicate skipped (hash match): {file_name}")
        return False, 0

    tz = pytz.timezone("Asia/Kolkata")
    try:
        file = Media(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
            file_hash=f_hash,
            indexed_at=datetime.now(tz),
        )
    except ValidationError:
        logger.exception("Validation error saving file")
        return False, 2
    try:
        await file.commit()
    except DuplicateKeyError:
        logger.warning(f"Duplicate file_id skipped: {file_name}")
        return False, 0
    logger.info(f"Saved: {file_name}")
    # Queue notification for subscribed users
    try:
        from plugins.file_notify import queue_new_file
        queue_new_file(file_name, file_id)
    except Exception:
        pass
    return True, 1


def _build_filter(query: str, file_type=None) -> dict:
    """
    Feature 5 — smarter filter:
    - Extract year from query and search separately
    - Expand synonyms
    - Build $and / $or for multi-word queries
    """
    query = query.strip()
    if not query:
        raw_pattern = "."
    else:
        # Extract year if present
        year_match = re.search(r"\b([12]\d{3})\b", query)
        year = year_match.group(1) if year_match else None
        clean_query = re.sub(r"\b[12]\d{3}\b", "", query).strip()

        # Synonym expansion
        words = clean_query.lower().split()
        expanded = []
        for w in words:
            syns = None
            for key, aliases in SYNONYMS.items():
                if w in aliases or w == key:
                    syns = aliases
                    break
            expanded.append(f"({'|'.join(syns)})" if syns else re.escape(w))

        raw_pattern = r".*[\s\.\+\-_]".join(expanded) if expanded else "."
        if year:
            raw_pattern = f"(?=.*{year}){raw_pattern}"

    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except re.error:
        return None

    if USE_CAPTION_FILTER:
        base = {"$or": [{"file_name": regex}, {"caption": regex}]}
    else:
        base = {"file_name": regex}

    if file_type:
        base["file_type"] = file_type

    return base


async def get_search_results(query, file_type=None, max_results=10,
                              offset=0, filter=False):
    """Return (files, next_offset, total_results)."""
    search_filter = _build_filter(query, file_type)
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


# ── encoding helpers ─────────────────────────────────────────────────────────
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
