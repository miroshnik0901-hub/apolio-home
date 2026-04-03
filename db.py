"""
Apolio Home — PostgreSQL connection layer.
Uses DATABASE_URL from Railway (or any PostgreSQL provider).
Auto-creates tables on first connect.

Tables:
  conversation_log — full message history between bot and users
  user_context     — key-value store for user goals, preferences, patterns
"""

import os
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy import: asyncpg ──────────────────────────────────────────────────────
# We import asyncpg lazily so the module can be imported even if asyncpg
# is not installed (graceful degradation to Google Sheets fallback).

_pool = None
_initialized = False

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversation_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id         BIGINT NOT NULL,
    direction       VARCHAR(10) NOT NULL,          -- 'user' | 'bot'
    message_type    VARCHAR(20) DEFAULT 'text',    -- text | voice | photo | command | response
    raw_text        TEXT DEFAULT '',
    intent          VARCHAR(100) DEFAULT '',
    entities_json   JSONB DEFAULT '{}',
    tool_called     VARCHAR(100) DEFAULT '',
    result_short    TEXT DEFAULT '',
    session_id      VARCHAR(32) DEFAULT '',
    envelope_id     VARCHAR(64) DEFAULT '',
    media_file_id   TEXT DEFAULT ''
);

-- Migration: add media_file_id to existing deployments
ALTER TABLE conversation_log ADD COLUMN IF NOT EXISTS media_file_id TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_convlog_user_ts
    ON conversation_log (user_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_convlog_session
    ON conversation_log (session_id);


CREATE TABLE IF NOT EXISTS user_context (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    key             VARCHAR(100) NOT NULL,
    value           TEXT DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_uctx_user
    ON user_context (user_id);


-- Self-learning table: vocabulary, corrections, confirmations, patterns
CREATE TABLE IF NOT EXISTS agent_learning (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id         BIGINT NOT NULL,
    envelope_id     VARCHAR(64) DEFAULT '',
    event_type      VARCHAR(50) NOT NULL,   -- vocabulary|correction|confirmation|pattern|new_value|ambiguity_resolved
    trigger_text    TEXT DEFAULT '',        -- the word/phrase that triggered this entry
    context_json    JSONB DEFAULT '{}',     -- original input and surrounding context
    learned_json    JSONB DEFAULT '{}',     -- what was learned: {field, value, category, ...}
    confidence      FLOAT DEFAULT 0.7,      -- 0.0–1.0
    times_seen      INT DEFAULT 1,
    last_seen_ts    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_learning_user_type
    ON agent_learning (user_id, event_type);

CREATE INDEX IF NOT EXISTS idx_learning_trigger
    ON agent_learning (user_id, trigger_text);

CREATE TABLE IF NOT EXISTS parsed_data (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id         BIGINT NOT NULL,
    data_type       VARCHAR(32) NOT NULL,   -- receipt | voice | image | document
    source_msg_id   BIGINT DEFAULT NULL,    -- Telegram message_id that triggered parsing
    envelope_id     VARCHAR(64) DEFAULT '', -- active envelope at parse time
    payload_json    JSONB DEFAULT '{}',     -- full parsed details: items, totals, OCR text, etc.
    transaction_id  VARCHAR(32) DEFAULT ''  -- linked Sheets transaction ID if expense was saved
);

CREATE INDEX IF NOT EXISTS idx_parsed_data_user
    ON parsed_data (user_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_parsed_data_type
    ON parsed_data (user_id, data_type);
"""


# ── Connection pool ───────────────────────────────────────────────────────────

async def init_db() -> bool:
    """
    Initialize the connection pool and create tables.
    Returns True if PostgreSQL is available, False otherwise.
    Call once at bot startup.
    """
    global _pool, _initialized

    if not DATABASE_URL:
        logger.warning("[DB] DATABASE_URL not set — PostgreSQL disabled, falling back to Google Sheets")
        return False

    try:
        import asyncpg
    except ImportError:
        logger.warning("[DB] asyncpg not installed — PostgreSQL disabled")
        return False

    try:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=15,
        )
        async with _pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        _initialized = True
        logger.info("[DB] PostgreSQL connected, tables ready")
        return True
    except Exception as e:
        logger.error(f"[DB] PostgreSQL init failed: {e}")
        _pool = None
        return False


async def close_db():
    """Close the connection pool. Call on shutdown."""
    global _pool, _initialized
    if _pool:
        await _pool.close()
        _pool = None
        _initialized = False


def is_ready() -> bool:
    """Check if PostgreSQL is available."""
    return _initialized and _pool is not None


@asynccontextmanager
async def acquire():
    """Acquire a connection from the pool."""
    if not _pool:
        raise RuntimeError("Database pool not initialized")
    async with _pool.acquire() as conn:
        yield conn


# ── ConversationLog operations ────────────────────────────────────────────────

async def log_message(
    *,
    user_id: int,
    direction: str,
    message_type: str = "text",
    raw_text: str = "",
    intent: str = "",
    entities: dict = None,
    tool_called: str = "",
    result_short: str = "",
    session_id: str = "",
    envelope_id: str = "",
    media_file_id: str = "",
):
    """Write a single conversation log entry."""
    if not is_ready():
        return
    try:
        import json as _json
        async with acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversation_log
                    (user_id, direction, message_type, raw_text, intent,
                     entities_json, tool_called, result_short, session_id, envelope_id,
                     media_file_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                user_id, direction, message_type,
                raw_text[:2000], intent,
                _json.dumps(entities or {}, ensure_ascii=False),
                tool_called, result_short[:500],
                session_id, envelope_id,
                media_file_id or "",
            )
    except Exception as e:
        logger.error(f"[DB] log_message failed: {e}")


async def get_recent_context(user_id: int, n: int = 5) -> list[dict]:
    """
    Load the last N conversation exchanges for a user.
    Returns list of dicts sorted by time ascending (oldest first).
    """
    if not is_ready():
        return []
    try:
        async with acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ts, direction, message_type, raw_text,
                       tool_called, result_short, media_file_id
                FROM conversation_log
                WHERE user_id = $1
                ORDER BY ts DESC
                LIMIT $2
                """,
                user_id, n * 2,  # n turns ≈ 2n rows (user + bot)
            )
            result = []
            for row in reversed(rows):  # oldest first
                result.append({
                    "ts": row["ts"].strftime("%Y-%m-%d %H:%M"),
                    "direction": row["direction"],
                    "message_type": row["message_type"],
                    "raw_text": row["raw_text"],
                    "tool_called": row["tool_called"],
                    "result_short": row["result_short"],
                    "media_file_id": row["media_file_id"] or "",
                })
            return result
    except Exception as e:
        logger.error(f"[DB] get_recent_context failed: {e}")
        return []


def format_context_for_prompt(rows: list[dict]) -> str:
    """Format recent conversation rows as a compact text block for the system prompt."""
    if not rows:
        return ""
    lines = ["RECENT CONVERSATION (last turns):"]
    for row in rows:
        direction = row.get("direction", "?")
        text = row.get("raw_text", "")
        result = row.get("result_short", "")
        ts = row.get("ts", "")

        if direction == "user" and text:
            lines.append(f"[{ts}] User: {text}")
        elif direction == "bot" and (result or text):
            lines.append(f"[{ts}] Bot: {result or text}")
    return "\n".join(lines)


async def get_recent_messages_for_api(user_id: int,
                                       n_turns: int = 6,
                                       telegram_bot=None) -> list[dict]:
    """
    Load the last n_turns conversation turns and return a properly alternating
    messages list ready for the Claude API.

    If telegram_bot is provided, photo messages are re-downloaded from Telegram
    and included as base64 images in the history — giving Claude visual memory
    of previously sent screenshots without the user having to resend them.

    Rules:
      - Alternates user / assistant roles strictly
      - Consecutive same-role rows are merged
      - Starts with a user turn (drops leading assistant turns)
      - Returns [] if DB is unavailable or history is empty
    """
    rows = await get_recent_context(user_id, n=n_turns)
    if not rows:
        return []

    # Build a list of (role, content) where content can be str or list (multimodal)
    pending_role: str | None = None
    pending_parts: list = []   # list of text strings or image dicts
    messages: list[dict] = []

    def _flush():
        if pending_role is None or not pending_parts:
            return
        # If all parts are strings, collapse to a single string
        if all(isinstance(p, str) for p in pending_parts):
            combined = "\n".join(p for p in pending_parts if p.strip())
            if combined.strip():
                messages.append({"role": pending_role, "content": combined})
        else:
            # Mixed content (text + images): use list form
            content_blocks = []
            for p in pending_parts:
                if isinstance(p, str):
                    if p.strip():
                        content_blocks.append({"type": "text", "text": p})
                else:
                    content_blocks.append(p)
            if content_blocks:
                messages.append({"role": pending_role, "content": content_blocks})

    for row in rows:
        direction = row.get("direction", "")
        role = "user" if direction == "user" else "assistant"
        text = (row.get("raw_text") or row.get("result_short") or "").strip()
        file_id = row.get("media_file_id", "")
        msg_type = row.get("message_type", "text")

        # Build the content for this row
        row_parts: list = []

        # For photo messages with a stored file_id, try to re-download the image
        if msg_type == "photo" and file_id and telegram_bot is not None:
            try:
                import base64 as _b64
                tg_file = await telegram_bot.get_file(file_id)
                img_bytes = await tg_file.download_as_bytearray()
                row_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": _b64.b64encode(bytes(img_bytes)).decode(),
                    },
                })
            except Exception:
                pass  # if download fails, fall through to text-only
            if text:
                row_parts.append(text)
        elif text:
            row_parts.append(text)

        if not row_parts:
            continue

        if role == pending_role:
            pending_parts.extend(row_parts)
        else:
            _flush()
            pending_role = role
            pending_parts = list(row_parts)

    _flush()

    # Claude API requires messages to start with "user" — drop leading assistant turns
    while messages and messages[0]["role"] == "assistant":
        messages.pop(0)

    # Defensive merge of consecutive same-role entries (after pop)
    merged: list[dict] = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            prev = merged[-1]["content"]
            cur = msg["content"]
            # Both are strings
            if isinstance(prev, str) and isinstance(cur, str):
                merged[-1]["content"] = prev + "\n" + cur
            # One or both are lists — convert both to lists and concatenate
            else:
                prev_list = prev if isinstance(prev, list) else [{"type": "text", "text": prev}]
                cur_list = cur if isinstance(cur, list) else [{"type": "text", "text": cur}]
                merged[-1]["content"] = prev_list + cur_list
        else:
            merged.append(msg)

    return merged


async def search_conversation_history(user_id: int,
                                       keyword: str = "",
                                       limit: int = 20,
                                       offset: int = 0) -> list[dict]:
    """
    Search conversation history for a user.
    - keyword: full-text search in raw_text (case-insensitive); empty = all
    - limit/offset: pagination (max 50 per call)
    Returns rows sorted oldest-first.
    """
    if not is_ready():
        return []
    limit = min(limit, 50)
    try:
        async with acquire() as conn:
            if keyword.strip():
                rows = await conn.fetch(
                    """
                    SELECT ts, direction, message_type, raw_text,
                           tool_called, result_short
                    FROM conversation_log
                    WHERE user_id = $1
                      AND raw_text ILIKE $2
                    ORDER BY ts DESC
                    LIMIT $3 OFFSET $4
                    """,
                    user_id, f"%{keyword}%", limit, offset,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT ts, direction, message_type, raw_text,
                           tool_called, result_short
                    FROM conversation_log
                    WHERE user_id = $1
                    ORDER BY ts DESC
                    LIMIT $2 OFFSET $3
                    """,
                    user_id, limit, offset,
                )
            result = []
            for row in reversed(rows):  # oldest first within the page
                result.append({
                    "ts": row["ts"].strftime("%Y-%m-%d %H:%M"),
                    "direction": row["direction"],
                    "message_type": row["message_type"],
                    "raw_text": row["raw_text"],
                    "tool_called": row["tool_called"],
                    "result_short": row["result_short"],
                })
            return result
    except Exception as e:
        logger.error(f"[DB] search_conversation_history failed: {e}")
        return []


# ── UserContext operations ────────────────────────────────────────────────────

async def ctx_get(user_id: int, key: str) -> Optional[str]:
    """Get a single context value."""
    if not is_ready():
        return None
    try:
        async with acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM user_context WHERE user_id = $1 AND key = $2",
                user_id, key,
            )
            return row["value"] if row else None
    except Exception as e:
        logger.error(f"[DB] ctx_get failed: {e}")
        return None


async def ctx_get_all(user_id: int) -> dict:
    """Get all context key-value pairs for a user."""
    if not is_ready():
        return {}
    try:
        async with acquire() as conn:
            rows = await conn.fetch(
                "SELECT key, value FROM user_context WHERE user_id = $1",
                user_id,
            )
            return {row["key"]: row["value"] for row in rows}
    except Exception as e:
        logger.error(f"[DB] ctx_get_all failed: {e}")
        return {}


async def ctx_set(user_id: int, key: str, value: str):
    """Upsert a context value."""
    if not is_ready():
        return
    try:
        async with acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_context (user_id, key, value, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (user_id, key)
                DO UPDATE SET value = $3, updated_at = NOW()
                """,
                user_id, key, value,
            )
    except Exception as e:
        logger.error(f"[DB] ctx_set failed: {e}")


async def ctx_delete(user_id: int, key: str):
    """Remove a context value."""
    if not is_ready():
        return
    try:
        async with acquire() as conn:
            await conn.execute(
                "DELETE FROM user_context WHERE user_id = $1 AND key = $2",
                user_id, key,
            )
    except Exception as e:
        logger.error(f"[DB] ctx_delete failed: {e}")


# ── Agent Learning operations ─────────────────────────────────────────────────

async def save_learning(
    *,
    user_id: int,
    event_type: str,
    trigger_text: str = "",
    context: dict = None,
    learned: dict = None,
    confidence_delta: float = 0.0,
    envelope_id: str = "",
) -> bool:
    """
    Upsert a learning event.
    - For vocabulary: upsert by (user_id, event_type='vocabulary', trigger_text)
      → increment times_seen, adjust confidence, update learned_json
    - For other types: insert new row.
    Returns True on success, False on failure.
    """
    if not is_ready():
        return False
    try:
        import json as _json
        ctx_str = _json.dumps(context or {}, ensure_ascii=False)
        learned_str = _json.dumps(learned or {}, ensure_ascii=False)

        async with acquire() as conn:
            if event_type in ("vocabulary", "pattern"):
                # Upsert: update existing entry if same trigger exists
                existing = await conn.fetchrow(
                    """
                    SELECT id, confidence, times_seen
                    FROM agent_learning
                    WHERE user_id = $1 AND event_type = $2 AND trigger_text = $3
                    ORDER BY ts DESC LIMIT 1
                    """,
                    user_id, event_type, trigger_text.lower().strip(),
                )
                if existing:
                    new_confidence = max(0.0, min(0.98, existing["confidence"] + confidence_delta))
                    new_times = existing["times_seen"] + 1
                    await conn.execute(
                        """
                        UPDATE agent_learning
                        SET confidence = $1, times_seen = $2, last_seen_ts = NOW(),
                            learned_json = $3, context_json = $4
                        WHERE id = $5
                        """,
                        new_confidence, new_times, learned_str, ctx_str, existing["id"],
                    )
                    return True
            # Insert new row for all other cases (or new vocabulary entry)
            initial_confidence = max(0.0, min(0.98, 0.7 + confidence_delta))
            await conn.execute(
                """
                INSERT INTO agent_learning
                    (user_id, envelope_id, event_type, trigger_text,
                     context_json, learned_json, confidence, times_seen, last_seen_ts)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 1, NOW())
                """,
                user_id, envelope_id, event_type, trigger_text.lower().strip(),
                ctx_str, learned_str, initial_confidence,
            )
        return True
    except Exception as e:
        logger.error(f"[DB] save_learning failed: {e}")
        return False


async def get_vocabulary(user_id: int, min_confidence: float = 0.4) -> list[dict]:
    """
    Load vocabulary entries for a user with confidence >= min_confidence.
    Returns list sorted by confidence desc.
    """
    if not is_ready():
        return []
    try:
        import json as _json
        async with acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT trigger_text, learned_json, confidence, times_seen
                FROM agent_learning
                WHERE user_id = $1 AND event_type = 'vocabulary'
                  AND confidence >= $2
                ORDER BY confidence DESC, times_seen DESC
                """,
                user_id, min_confidence,
            )
            return [
                {
                    "trigger": row["trigger_text"],
                    "learned": _json.loads(row["learned_json"]),
                    "confidence": row["confidence"],
                    "times_seen": row["times_seen"],
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"[DB] get_vocabulary failed: {e}")
        return []


async def get_patterns(user_id: int) -> list[dict]:
    """Load recognized recurring patterns for a user."""
    if not is_ready():
        return []
    try:
        import json as _json
        async with acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT trigger_text, learned_json, confidence, times_seen, last_seen_ts
                FROM agent_learning
                WHERE user_id = $1 AND event_type = 'pattern'
                ORDER BY times_seen DESC
                """,
                user_id,
            )
            return [
                {
                    "trigger": row["trigger_text"],
                    "pattern": _json.loads(row["learned_json"]),
                    "confidence": row["confidence"],
                    "times_seen": row["times_seen"],
                    "last_seen": row["last_seen_ts"].strftime("%Y-%m-%d") if row["last_seen_ts"] else "",
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"[DB] get_patterns failed: {e}")
        return []


async def get_learning_context_for_prompt(user_id: int) -> str:
    """
    Return a compact text block of vocabulary and patterns for injection
    into the system prompt. Only includes high-confidence entries.
    """
    vocab = await get_vocabulary(user_id, min_confidence=0.75)
    patterns = await get_patterns(user_id)

    if not vocab and not patterns:
        return ""

    lines = []
    if vocab:
        lines.append("LEARNED VOCABULARY (use these mappings directly without asking):")
        for v in vocab[:20]:
            learned = v["learned"]
            mapping = ", ".join(f"{k}={val}" for k, val in learned.items() if val)
            conf_label = "✓✓" if v["confidence"] >= 0.95 else "✓"
            lines.append(f"  {conf_label} '{v['trigger']}' → {mapping} (seen {v['times_seen']}x)")

    if patterns:
        lines.append("\nRECURRING PATTERNS (suggest these when input matches):")
        for p in patterns[:10]:
            pat = p["pattern"]
            desc = pat.get("description", p["trigger"])
            lines.append(f"  • {desc} (seen {p['times_seen']}x, last {p['last_seen']})")

    return "\n".join(lines)


async def get_all_learning(user_id: int, envelope_id: str = "",
                            min_confidence: float = 0.5) -> list[dict]:
    """Return all learning rows for a user above min_confidence threshold.
    Used by refresh_learning_summary tool to write to Google Sheets."""
    pool = await get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            if envelope_id:
                rows = await conn.fetch(
                    """SELECT event_type, trigger_text, learned, confidence,
                              updated_at, envelope_id
                       FROM agent_learning
                       WHERE user_id=$1 AND envelope_id=$2 AND confidence >= $3
                       ORDER BY updated_at DESC""",
                    user_id, envelope_id, min_confidence,
                )
            else:
                rows = await conn.fetch(
                    """SELECT event_type, trigger_text, learned, confidence,
                              updated_at, envelope_id
                       FROM agent_learning
                       WHERE user_id=$1 AND confidence >= $2
                       ORDER BY updated_at DESC""",
                    user_id, min_confidence,
                )
            result = []
            for r in rows:
                try:
                    learned = json.loads(r["learned"]) if isinstance(r["learned"], str) else r["learned"]
                except Exception:
                    learned = {}
                result.append({
                    "event_type":   r["event_type"],
                    "trigger_text": r["trigger_text"],
                    "learned":      learned,
                    "confidence":   float(r["confidence"]),
                    "updated_at":   str(r["updated_at"]),
                    "envelope_id":  r["envelope_id"] or "",
                })
            return result
    except Exception as e:
        logger.warning(f"[DB] get_all_learning failed: {e}")


# ── parsed_data ───────────────────────────────────────────────────────────────

async def save_parsed_data(
    user_id: int,
    data_type: str,
    payload: dict,
    source_msg_id: Optional[int] = None,
    envelope_id: str = "",
    transaction_id: str = "",
) -> Optional[int]:
    """
    Save parsed receipt / voice / image / document details to parsed_data table.
    Returns the new row id, or None on failure.

    data_type values: receipt | voice | image | document
    payload: arbitrary dict with all parsed details (items, totals, OCR text, etc.)
    transaction_id: linked Sheets transaction ID if an expense was saved
    """
    pool = await get_pool()
    if pool is None:
        return None
    try:
        import json as _json
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO parsed_data
                       (user_id, data_type, source_msg_id, envelope_id, payload_json, transaction_id)
                   VALUES ($1, $2, $3, $4, $5, $6)
                   RETURNING id""",
                user_id,
                data_type,
                source_msg_id,
                envelope_id,
                _json.dumps(payload, ensure_ascii=False),
                transaction_id,
            )
            return int(row["id"]) if row else None
    except Exception as e:
        logger.warning(f"[DB] save_parsed_data failed: {e}")
        return None


async def get_parsed_data(
    user_id: int,
    data_type: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    """
    Retrieve recent parsed data rows for a user.
    Optionally filter by data_type (receipt / voice / image / document).
    """
    pool = await get_pool()
    if pool is None:
        return []
    try:
        import json as _json
        async with pool.acquire() as conn:
            if data_type:
                rows = await conn.fetch(
                    """SELECT id, ts, data_type, source_msg_id, envelope_id,
                              payload_json, transaction_id
                       FROM parsed_data
                       WHERE user_id=$1 AND data_type=$2
                       ORDER BY ts DESC LIMIT $3""",
                    user_id, data_type, limit,
                )
            else:
                rows = await conn.fetch(
                    """SELECT id, ts, data_type, source_msg_id, envelope_id,
                              payload_json, transaction_id
                       FROM parsed_data
                       WHERE user_id=$1
                       ORDER BY ts DESC LIMIT $2""",
                    user_id, limit,
                )
            result = []
            for r in rows:
                try:
                    payload = _json.loads(r["payload_json"]) if r["payload_json"] else {}
                except Exception:
                    payload = {}
                result.append({
                    "id":             int(r["id"]),
                    "ts":             str(r["ts"]),
                    "data_type":      r["data_type"],
                    "source_msg_id":  r["source_msg_id"],
                    "envelope_id":    r["envelope_id"] or "",
                    "payload":        payload,
                    "transaction_id": r["transaction_id"] or "",
                })
            return result
    except Exception as e:
        logger.warning(f"[DB] get_parsed_data failed: {e}")
        return []
        return []
