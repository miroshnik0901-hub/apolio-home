"""
tools/support.py — Support service for Apolio Home.

Handles:
  - Intent detection (error | question | feedback | other)
  - FAQ lookup from KnowledgeBase sheet in Admin spreadsheet
  - Creating/fetching support_requests from PostgreSQL
  - /admin_support command handler data
"""

import re
import logging
from typing import Optional

import db

logger = logging.getLogger(__name__)

# ── Intent detection ────────────────────────────────────────────────────────────

_ERROR_PATTERNS = [
    r"не раб", r"ошибк", r"error", r"fails?", r"broken", r"бот не", r"сломал",
    r"не получ", r"проблем", r"баг", r"bug", r"не могу", r"cannot", r"can't",
    r"зависл", r"не отвеч", r"не понима", r"не вижу", r"пропал",
]

_QUESTION_PATTERNS = [
    r"\bкак\b", r"\bчто\b", r"\bкогда\b", r"\bпочему\b", r"\bзачем\b",
    r"\bможно\b", r"\bможно ли\b", r"how\b", r"what\b", r"why\b", r"when\b",
    r"where\b", r"which\b", r"can i\b", r"is it\b", r"does\b",
    r"come\b", r"perch", r"quando\b", r"cosa\b", r"\?",
]

_FEEDBACK_PATTERNS = [
    r"хочу", r"хотел", r"было бы", r"предлаг", r"идея", r"улучш",
    r"нравит", r"не нравит", r"плох", r"хорош", r"неудобн", r"удобн",
    r"suggest", r"feature", r"improve", r"love", r"hate", r"wish",
    r"suggerir", r"miglior",
]


def detect_intent(text: str) -> str:
    """Return 'error' | 'question' | 'feedback' | 'other' based on keyword rules."""
    t = text.lower()
    if any(re.search(p, t) for p in _ERROR_PATTERNS):
        return "error"
    if any(re.search(p, t) for p in _FEEDBACK_PATTERNS):
        return "feedback"
    if any(re.search(p, t) for p in _QUESTION_PATTERNS):
        return "question"
    return "other"


# ── KnowledgeBase (Admin sheet) ─────────────────────────────────────────────────

KB_TAB = "KnowledgeBase"
KB_HEADERS = ["Question", "Answer", "Tags", "Active"]


def _get_kb(sheets) -> list[dict]:
    """Read KnowledgeBase sheet from Admin spreadsheet. Creates it if missing."""
    try:
        admin = sheets.admin if hasattr(sheets, "admin") else sheets
        wb = admin._workbook()
        try:
            ws = wb.worksheet(KB_TAB)
        except Exception:
            # Create the tab on first access
            ws = wb.add_worksheet(title=KB_TAB, rows=100, cols=4)
            ws.append_row(KB_HEADERS)
            logger.info(f"[Support] Created {KB_TAB} worksheet in Admin sheet")
            return []
        return ws.get_all_records(expected_headers=KB_HEADERS)
    except Exception as e:
        logger.warning(f"[Support] _get_kb failed: {e}")
        return []


def _faq_search(text: str, kb: list[dict]) -> Optional[dict]:
    """Simple keyword search through KnowledgeBase. Returns best matching row or None."""
    t = text.lower()
    words = set(re.findall(r"\w+", t))
    best: Optional[dict] = None
    best_score = 0
    for row in kb:
        if str(row.get("Active", "")).upper() in ("", "0", "FALSE", "NO"):
            continue
        q = str(row.get("Question", "")).lower()
        q_words = set(re.findall(r"\w+", q))
        if not q_words:
            continue
        overlap = len(words & q_words)
        score = overlap / max(len(q_words), 1)
        if score > best_score and score >= 0.4:
            best_score = score
            best = row
    return best


# ── Tool functions ──────────────────────────────────────────────────────────────

async def tool_create_support_request(
    params: dict,
    session,
    sheets,
    auth,
) -> dict:
    """
    Save a support request from the user.

    params:
      text (str): the user's message
      user_name (str, optional): display name

    Returns:
      {
        "id": <int or None>,
        "intent": "error|question|feedback|other",
        "auto_answer": "<str> — FAQ answer if found, else None",
        "status": "AUTO_ANSWERED" | "OPEN"
      }
    """
    text = str(params.get("text", "")).strip()
    if not text:
        return {"error": "text is required"}

    user_name = params.get("user_name", "") or getattr(session, "name", "")
    envelope_id = getattr(session, "current_envelope_id", "") or ""
    user_id = getattr(session, "user_id", 0)

    intent = detect_intent(text)

    # Try FAQ first
    kb = _get_kb(sheets)
    match = _faq_search(text, kb)
    auto_answer = str(match["Answer"]) if match and match.get("Answer") else None

    # Save to DB
    request_id = await db.create_support_request(
        user_id=user_id,
        text=text,
        intent=intent,
        user_name=user_name,
        envelope_id=envelope_id,
    )

    # Mark as AUTO_ANSWERED if we found a FAQ match
    if auto_answer and request_id:
        await db.resolve_support_request(request_id, resolution=f"[FAQ] {auto_answer}")

    return {
        "id": request_id,
        "intent": intent,
        "auto_answer": auto_answer,
        "status": "AUTO_ANSWERED" if auto_answer else "OPEN",
    }


async def tool_get_support_requests(
    params: dict,
    session,
    sheets,
    auth,
) -> dict:
    """
    Fetch support requests (admin only).

    params:
      status (str, optional): filter by status — "OPEN" | "RESOLVED" | "AUTO_ANSWERED"
      limit (int, optional): default 20

    Returns:
      {"requests": [...], "count": int}
    """
    if not auth.is_admin(session.user_id):
        return {"error": "admin only"}

    status = params.get("status") or None
    limit = min(int(params.get("limit", 20)), 50)
    requests = await db.get_support_requests(status=status, limit=limit)
    return {"requests": requests, "count": len(requests)}


async def tool_resolve_support_request(
    params: dict,
    session,
    sheets,
    auth,
) -> dict:
    """
    Mark a support request as resolved (admin only).

    params:
      id (int): request id
      resolution (str, optional): resolution note

    Returns:
      {"ok": True} | {"error": "..."}
    """
    if not auth.is_admin(session.user_id):
        return {"error": "admin only"}

    req_id = params.get("id")
    if not req_id:
        return {"error": "id is required"}

    resolution = str(params.get("resolution", "")).strip()
    ok = await db.resolve_support_request(int(req_id), resolution=resolution)
    return {"ok": ok}
