"""
tools/admin.py — Admin-only log and stats tools for Apolio Home bot.

Commands (admin only):
  /log [username|user_id]  → last 20 messages from conversation_log for that user
  /stats                   → activity summary: messages per day, top intents
"""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


async def tool_get_user_log(params: dict, session, sheets, auth) -> dict:
    """
    Return the last N messages for a specific user from conversation_log.

    params:
      user_ref  — username (str) or user_id (int); if omitted → all users
      limit     — number of rows to return (default 20, max 50)
    """
    if not auth.is_admin(session.user_id):
        return {"error": "Admin only"}

    import db
    user_ref = params.get("user_ref", "")
    limit = min(int(params.get("limit", 20)), 50)

    pool = await db.get_pool()
    if pool is None:
        return {"error": "Database unavailable"}

    try:
        async with pool.acquire() as conn:
            if user_ref:
                # Try numeric user_id first, then match by name in context
                try:
                    uid = int(user_ref)
                    rows = await conn.fetch(
                        """SELECT ts, user_id, role, content, intent, media_type
                           FROM conversation_log
                           WHERE user_id = $1
                           ORDER BY ts DESC LIMIT $2""",
                        uid, limit,
                    )
                except ValueError:
                    # Search by username substring in content or context fields
                    rows = await conn.fetch(
                        """SELECT ts, user_id, role, content, intent, media_type
                           FROM conversation_log
                           WHERE content ILIKE $1 OR intent ILIKE $1
                           ORDER BY ts DESC LIMIT $2""",
                        f"%{user_ref}%", limit,
                    )
            else:
                rows = await conn.fetch(
                    """SELECT ts, user_id, role, content, intent, media_type
                       FROM conversation_log
                       ORDER BY ts DESC LIMIT $1""",
                    limit,
                )

        messages = []
        for r in rows:
            messages.append({
                "ts":         str(r["ts"])[:19],
                "user_id":    r["user_id"],
                "role":       r["role"],
                "content":    (r["content"] or "")[:200],
                "intent":     r["intent"] or "",
                "media_type": r["media_type"] or "",
            })

        return {
            "status": "ok",
            "user_ref": user_ref or "all",
            "count": len(messages),
            "messages": messages,
        }

    except Exception as e:
        logger.error(f"[admin] tool_get_user_log failed: {e}", exc_info=True)
        return {"error": str(e)}


async def tool_get_stats(params: dict, session, sheets, auth) -> dict:
    """
    Return activity stats from conversation_log.

    params:
      days  — number of past days to analyse (default 7)
    """
    if not auth.is_admin(session.user_id):
        return {"error": "Admin only"}

    import db
    days = int(params.get("days", 7))

    pool = await db.get_pool()
    if pool is None:
        return {"error": "Database unavailable"}

    try:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        async with pool.acquire() as conn:
            # Messages per day
            by_day = await conn.fetch(
                """SELECT DATE(ts AT TIME ZONE 'Europe/Rome') AS day,
                          user_id,
                          COUNT(*) AS cnt
                   FROM conversation_log
                   WHERE ts >= $1 AND role = 'user'
                   GROUP BY day, user_id
                   ORDER BY day DESC""",
                since,
            )

            # Top intents
            by_intent = await conn.fetch(
                """SELECT intent, COUNT(*) AS cnt
                   FROM conversation_log
                   WHERE ts >= $1 AND role = 'user' AND intent IS NOT NULL AND intent != ''
                   GROUP BY intent
                   ORDER BY cnt DESC
                   LIMIT 10""",
                since,
            )

            # Unique users active
            unique_users = await conn.fetchval(
                """SELECT COUNT(DISTINCT user_id)
                   FROM conversation_log
                   WHERE ts >= $1 AND role = 'user'""",
                since,
            )

        return {
            "status": "ok",
            "period_days": days,
            "unique_users": int(unique_users or 0),
            "by_day": [
                {"day": str(r["day"]), "user_id": r["user_id"], "messages": int(r["cnt"])}
                for r in by_day
            ],
            "top_intents": [
                {"intent": r["intent"], "count": int(r["cnt"])}
                for r in by_intent
            ],
        }

    except Exception as e:
        logger.error(f"[admin] tool_get_stats failed: {e}", exc_info=True)
        return {"error": str(e)}
