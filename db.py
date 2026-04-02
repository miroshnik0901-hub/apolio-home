"""
Apolio Home — PostgreSQL data layer
Tables: conversation_log, sessions, agent_learning
"""
import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool: Optional[asyncpg.Pool] = None

# ── Schema ─────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL,
    session_id  VARCHAR(64) UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_seen   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_log (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ DEFAULT NOW(),
    user_id       BIGINT NOT NULL,
    session_id    VARCHAR(64) DEFAULT '',
    direction     VARCHAR(8)  NOT NULL,   -- 'user' or 'bot'
    message_type  VARCHAR(16) NOT NULL,   -- 'text', 'photo', 'voice', 'tool'
    content       TEXT        DEFAULT '',
    media_file_id TEXT        DEFAULT '',
    metadata      JSONB       DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_conv_log_user_ts
    ON conversation_log (user_id, ts DESC);

CREATE TABLE IF NOT EXISTS agent_learning (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ DEFAULT NOW(),
    user_id       BIGINT      NOT NULL,
    envelope_id   VARCHAR(64) DEFAULT '',
    event_type    VARCHAR(50) NOT NULL,
    trigger_text  TEXT        DEFAULT '',
    context_json  JSONB       DEFAULT '{}',
    learned_json  JSONB       DEFAULT '{}',
    confidence    FLOAT       DEFAULT 0.7,
    times_seen    INT         DEFAULT 1,
    last_seen_ts  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_learning_user
    ON agent_learning (user_id);
CREATE INDEX IF NOT EXISTS idx_learning_event
    ON agent_learning (event_type, confidence DESC);
"""

# ── Pool ───────────────────────────────────────────────────────────────────────

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL env var not set")
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
        async with _pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        logger.info("PostgreSQL pool initialised")
    return _pool


async def init_db() -> bool:
    """Initialise pool and schema. Returns False if DATABASE_URL not configured."""
    if not DATABASE_URL:
        logger.warning("DATABASE_URL not set — PostgreSQL features disabled")
        return False
    try:
        await get_pool()
        return True
    except Exception as e:
        logger.error(f"PostgreSQL init failed: {e}")
        return False

# ── Conversation log ───────────────────────────────────────────────────────────

async def log_message(
    user_id: int,
    session_id: str,
    direction: str,          # 'user' or 'bot'
    message_type: str,       # 'text', 'photo', 'voice', 'tool'
    content: str = "",
    media_file_id: str = "",
    metadata: dict = None,
) -> None:
    """Append a message to conversation_log. Silently swallows all errors."""
    try:
        pool = await get_pool()
        await pool.execute(
            """
            INSERT INTO conversation_log
                (user_id, session_id, direction, message_type, content, media_file_id, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            user_id,
            session_id or "",
            direction,
            message_type,
            content or "",
            media_file_id or "",
            json.dumps(metadata or {}),
        )
    except Exception as e:
        logger.warning(f"log_message failed: {e}")


async def get_recent_messages_for_api(
    user_id: int,
    limit: int = 20,
    telegram_bot=None,
) -> list:
    """
    Returns recent conversation as Claude API messages[].
    For photo messages with media_file_id, re-downloads from Telegram
    and includes as base64 image block.
    Skips tool messages.
    """
    try:
        pool = await get_pool()
        rows = await pool.fetch(
            """
            SELECT direction, message_type, content, media_file_id
            FROM conversation_log
            WHERE user_id = $1
              AND message_type != 'tool'
              AND content != ''
            ORDER BY ts DESC
            LIMIT $2
            """,
            user_id, limit,
        )
    except Exception as e:
        logger.warning(f"get_recent_messages_for_api failed: {e}")
        return []

    # Chronological order
    rows = list(reversed(rows))
    messages = []

    for row in rows:
        role = "user" if row["direction"] == "user" else "assistant"
        content_text = row["content"] or ""

        if (
            row["message_type"] == "photo"
            and row["media_file_id"]
            and telegram_bot is not None
        ):
            try:
                file_obj = await telegram_bot.get_file(row["media_file_id"])
                photo_bytes = bytes(await file_obj.download_as_bytearray())
                content = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": base64.b64encode(photo_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": content_text or "Photo"},
                ]
            except Exception as e:
                logger.warning(f"Photo re-download failed for {row['media_file_id']}: {e}")
                content = f"[Photo] {content_text}"
        else:
            content = content_text

        if content:
            messages.append({"role": role, "content": content})

    # Claude API requires alternating roles — deduplicate consecutive same-role messages
    merged: list = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            # Merge: append text content
            prev = merged[-1]["content"]
            curr = msg["content"]
            if isinstance(prev, str) and isinstance(curr, str):
                merged[-1]["content"] = prev + "\n" + curr
            # If multimodal — skip merging (keep first, drop duplicate)
        else:
            merged.append(msg)

    return merged


# ── Self-learning ──────────────────────────────────────────────────────────────

async def save_learning(
    user_id: int,
    envelope_id: str,
    event_type: str,
    trigger_text: str,
    learned_json: dict,
    context_json: dict = None,
) -> None:
    """
    Upsert a learning entry.
    If trigger exists for this user + event_type: update confidence (+0.1), increment times_seen.
    Otherwise insert with confidence 0.7.
    Confidence is capped at 0.98.
    """
    try:
        pool = await get_pool()
        existing = await pool.fetchrow(
            """
            SELECT id, confidence, times_seen
            FROM agent_learning
            WHERE user_id = $1 AND event_type = $2 AND trigger_text = $3
            LIMIT 1
            """,
            user_id, event_type, trigger_text,
        )

        if existing:
            new_conf = min(0.98, existing["confidence"] + 0.1)
            await pool.execute(
                """
                UPDATE agent_learning
                SET times_seen   = $1,
                    confidence   = $2,
                    learned_json = $3,
                    last_seen_ts = NOW()
                WHERE id = $4
                """,
                existing["times_seen"] + 1,
                new_conf,
                json.dumps(learned_json),
                existing["id"],
            )
        else:
            await pool.execute(
                """
                INSERT INTO agent_learning
                    (user_id, envelope_id, event_type, trigger_text,
                     context_json, learned_json, confidence)
                VALUES ($1, $2, $3, $4, $5, $6, 0.7)
                """,
                user_id,
                envelope_id or "",
                event_type,
                trigger_text,
                json.dumps(context_json or {}),
                json.dumps(learned_json),
            )
    except Exception as e:
        logger.warning(f"save_learning failed: {e}")


async def correct_learning(
    user_id: int,
    event_type: str,
    trigger_text: str,
) -> None:
    """
    Mark a learning entry as corrected: decrease confidence by 0.3.
    If confidence drops below 0.2, entry is removed.
    """
    try:
        pool = await get_pool()
        existing = await pool.fetchrow(
            """
            SELECT id, confidence FROM agent_learning
            WHERE user_id = $1 AND event_type = $2 AND trigger_text = $3
            LIMIT 1
            """,
            user_id, event_type, trigger_text,
        )
        if not existing:
            return
        new_conf = existing["confidence"] - 0.3
        if new_conf < 0.2:
            await pool.execute(
                "DELETE FROM agent_learning WHERE id = $1", existing["id"]
            )
        else:
            await pool.execute(
                "UPDATE agent_learning SET confidence = $1 WHERE id = $2",
                new_conf, existing["id"],
            )
    except Exception as e:
        logger.warning(f"correct_learning failed: {e}")


async def get_learning_context_for_prompt(
    user_id: int,
    envelope_id: str = "",
) -> str:
    """
    Build a compact text block of learned vocabulary and patterns for system prompt injection.
    Only includes entries with confidence >= 0.6.
    Returns "" if nothing learned yet or on error.
    """
    try:
        pool = await get_pool()
        rows = await pool.fetch(
            """
            SELECT event_type, trigger_text, learned_json, confidence
            FROM agent_learning
            WHERE user_id = $1 AND confidence >= 0.6
            ORDER BY confidence DESC, times_seen DESC
            LIMIT 60
            """,
            user_id,
        )
    except Exception as e:
        logger.warning(f"get_learning_context_for_prompt failed: {e}")
        return ""

    if not rows:
        return ""

    vocab_lines: list[str] = []
    pattern_lines: list[str] = []
    category_lines: list[str] = []

    for row in rows:
        try:
            learned = row["learned_json"]
            if isinstance(learned, str):
                learned = json.loads(learned)
        except Exception:
            learned = {}

        if row["event_type"] in ("vocabulary", "correction"):
            mapping = learned.get("mapping") or learned.get("category") or ""
            if mapping:
                vocab_lines.append(f'  "{row["trigger_text"]}" → {mapping}')

        elif row["event_type"] == "new_category":
            cat = learned.get("category", row["trigger_text"])
            if cat:
                category_lines.append(f"  • {cat}")

        elif row["event_type"] == "pattern":
            desc = learned.get("description", "")
            if desc:
                pattern_lines.append(f"  • {desc}")

    parts: list[str] = []
    if vocab_lines:
        parts.append("LEARNED VOCABULARY:\n" + "\n".join(vocab_lines[:25]))
    if category_lines:
        parts.append("CUSTOM CATEGORIES:\n" + "\n".join(category_lines[:15]))
    if pattern_lines:
        parts.append("KNOWN PATTERNS:\n" + "\n".join(pattern_lines[:10]))

    if not parts:
        return ""

    return "\n---\n## Agent Memory\n" + "\n\n".join(parts) + "\n---"


# ── Pattern detection ──────────────────────────────────────────────────────────

async def check_and_save_pattern(
    user_id: int,
    envelope_id: str,
    category: str,
    who: str,
    amount: float,
    sheets_client=None,
) -> None:
    """
    After a transaction is added, check if there are 3+ similar transactions
    in the last 60 days. If yes, save a pattern learning entry.
    'Similar' = same category + who.
    Runs silently — never raises.
    """
    if not category:
        return
    try:
        pool = await get_pool()
        # Count recent similar entries in conversation_log metadata
        # We check agent_learning patterns to avoid counting duplicates
        existing = await pool.fetchrow(
            """
            SELECT id FROM agent_learning
            WHERE user_id = $1
              AND event_type = 'pattern'
              AND learned_json->>'category' = $2
              AND learned_json->>'who' = $3
            LIMIT 1
            """,
            user_id, category, who,
        )
        if existing:
            # Already recorded this pattern — update confidence
            await save_learning(
                user_id, envelope_id, "pattern",
                f"{category}/{who}",
                {"category": category, "who": who,
                 "description": f"{who} regularly buys {category}"},
            )
            return

        # Need to count actual transactions — use sheets_client if provided
        if sheets_client is None:
            return

        from datetime import timedelta
        from_date = (datetime.utcnow() - timedelta(days=60)).strftime("%Y-%m-%d")

        envelopes = sheets_client.get_envelopes()
        file_id = None
        for e in envelopes:
            if e.get("ID") == envelope_id:
                file_id = e.get("file_id")
                break
        if not file_id:
            return

        env_sheets = sheets_client._envelope(file_id)
        txs = env_sheets.get_transactions({"date_from": from_date})
        matches = [
            t for t in txs
            if t.get("Category", "") == category
            and t.get("Who", "") == who
        ]

        if len(matches) >= 3:
            await save_learning(
                user_id, envelope_id, "pattern",
                f"{category}/{who}",
                {
                    "category": category,
                    "who": who,
                    "description": f"{who} regularly spends on {category} ({len(matches)}x in 60 days)",
                },
            )
            logger.info(f"Pattern saved: {who}/{category} ({len(matches)} times)")

    except Exception as e:
        logger.warning(f"check_and_save_pattern failed: {e}")
