"""
tools/ideas.py — Ideas service for Apolio Home.

Handles:
  - /idea command: save an idea to ideas table in PostgreSQL
  - tool_get_ideas: fetch ideas (admin)
  - tool_archive_idea: archive an idea (admin)
"""

import logging
from typing import Optional

import db

logger = logging.getLogger(__name__)


async def tool_save_idea(
    params: dict,
    session,
    sheets,
    auth,
) -> dict:
    """
    Save a user idea.

    params:
      text (str): idea text

    Returns:
      {"id": <int>, "text": <str>} | {"error": "..."}
    """
    text = str(params.get("text", "")).strip()
    if not text:
        return {"error": "idea text is required"}

    user_id = getattr(session, "user_id", 0)
    user_name = getattr(session, "name", "")
    envelope_id = getattr(session, "current_envelope_id", "") or ""

    idea_id = await db.create_idea(
        user_id=user_id,
        text=text,
        user_name=user_name,
        tags=[],
        envelope_id=envelope_id,
    )

    if idea_id is None:
        return {"error": "failed to save idea (DB unavailable)"}

    return {"id": idea_id, "text": text}


async def tool_get_ideas(
    params: dict,
    session,
    sheets,
    auth,
) -> dict:
    """
    Fetch ideas (admin only or own ideas).

    params:
      user_id (int, optional): filter by user; admin sees all if omitted
      status (str, optional): "NEW" | "REVIEWED" | "ARCHIVED"
      limit (int, optional): default 30

    Returns:
      {"ideas": [...], "count": int}
    """
    is_admin = auth.is_admin(session.user_id)
    req_uid = params.get("user_id")

    if is_admin:
        uid = int(req_uid) if req_uid else None
    else:
        uid = session.user_id  # non-admins only see own ideas

    status = params.get("status") or None
    limit = min(int(params.get("limit", 30)), 100)

    ideas = await db.get_ideas(user_id=uid, status=status, limit=limit)
    return {"ideas": ideas, "count": len(ideas)}


async def tool_archive_idea(
    params: dict,
    session,
    sheets,
    auth,
) -> dict:
    """
    Archive an idea (admin only).

    params:
      id (int): idea id

    Returns:
      {"ok": True} | {"error": "..."}
    """
    if not auth.is_admin(session.user_id):
        return {"error": "admin only"}

    idea_id = params.get("id")
    if not idea_id:
        return {"error": "id is required"}

    if not db.is_ready():
        return {"error": "DB unavailable"}

    try:
        async with db._pool.acquire() as conn:
            await conn.execute(
                "UPDATE ideas SET status='ARCHIVED' WHERE id=$1",
                int(idea_id),
            )
        return {"ok": True}
    except Exception as e:
        logger.warning(f"[Ideas] archive failed: {e}")
        return {"error": str(e)}
