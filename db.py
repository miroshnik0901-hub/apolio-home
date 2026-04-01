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
    envelope_id     VARCHAR(64) DEFAULT ''
);

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
                     entities_json, tool_called, result_short, session_id, envelope_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                user_id, direction, message_type,
                raw_text[:2000], intent,
                _json.dumps(entities or {}, ensure_ascii=False),
                tool_called, result_short[:500],
                session_id, envelope_id,
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
                       tool_called, result_short
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
