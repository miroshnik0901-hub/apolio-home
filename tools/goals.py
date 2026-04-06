"""
tools/goals.py — Goal tracking service for Apolio Home.

Features:
  - /goal → show active goals
  - /goal add <type> <text> → add a goal
  - /goal done #id → deactivate a goal
  - check_goals_against_transaction() → called after each expense is saved
  - Goals sheet in Admin spreadsheet (templates)
"""

import logging
from typing import Optional

import db

logger = logging.getLogger(__name__)

GOAL_TYPES = {
    "savings":       {"ru": "💰 Накопления",       "uk": "💰 Заощадження",   "en": "💰 Savings",       "it": "💰 Risparmio"},
    "expense_limit": {"ru": "🚫 Бюджет расходов",   "uk": "🚫 Бюджет витрат",  "en": "🚫 Expense budget", "it": "🚫 Budget spese"},
    "contribution":  {"ru": "🤝 Взнос",            "uk": "🤝 Внесок",         "en": "🤝 Contribution",  "it": "🤝 Contributo"},
    "custom":        {"ru": "🎯 Цель",              "uk": "🎯 Ціль",           "en": "🎯 Goal",          "it": "🎯 Obiettivo"},
}

PROGRESS_BAR_LEN = 8


def _progress_bar(pct: float) -> str:
    filled = round(pct / 100 * PROGRESS_BAR_LEN)
    return "█" * filled + "░" * (PROGRESS_BAR_LEN - filled)


def _goal_type_label(goal_type: str, lang: str) -> str:
    return GOAL_TYPES.get(goal_type, GOAL_TYPES["custom"]).get(lang, "🎯")


# ── Goals sheet (templates) ─────────────────────────────────────────────────────

GOALS_TAB = "Goals"
GOALS_HEADERS = ["Name", "Type", "Description", "DefaultRules"]


def _get_goal_templates(sheets) -> list[dict]:
    """Read goal templates from Admin Goals sheet. Creates it if missing."""
    try:
        admin = sheets.admin if hasattr(sheets, "admin") else sheets
        wb = admin._workbook()
        try:
            ws = wb.worksheet(GOALS_TAB)
        except Exception:
            ws = wb.add_worksheet(title=GOALS_TAB, rows=50, cols=4)
            ws.append_row(GOALS_HEADERS)
            # Seed with default templates
            ws.append_row(["Ежемесячный бюджет", "expense_limit",
                            "Не превышать бюджет расходов за месяц",
                            '{"category": "", "limit_eur": 2500}'])
            ws.append_row(["Накопления", "savings",
                            "Накопить сумму к дате",
                            '{"target_eur": 1000, "deadline": ""}'])
            logger.info(f"[Goals] Created {GOALS_TAB} worksheet")
            return []
        return ws.get_all_records(expected_headers=GOALS_HEADERS)
    except Exception as e:
        logger.warning(f"[Goals] _get_goal_templates failed: {e}")
        return []


# ── Tool functions ──────────────────────────────────────────────────────────────

async def tool_get_goals(params: dict, session, sheets, auth) -> dict:
    """
    Return active goals for the current user.

    params:
      active_only (bool): default True

    Returns:
      {"goals": [...], "count": int}
    """
    user_id = getattr(session, "user_id", 0)
    active_only = params.get("active_only", True)
    goals = await db.get_goals(user_id, active_only=active_only)
    return {"goals": goals, "count": len(goals)}


async def tool_add_goal(params: dict, session, sheets, auth) -> dict:
    """
    Add a new goal for the current user.

    params:
      goal_type (str): savings | expense_limit | contribution | custom
      goal_text (str): human-readable description
      rules (dict, optional): {"target": N, "category": "...", "deadline": "YYYY-MM-DD"}

    Returns:
      {"id": <int>, "goal_text": <str>} | {"error": "..."}
    """
    goal_type = str(params.get("goal_type", "custom")).strip()
    goal_text = str(params.get("goal_text", "")).strip()

    if not goal_text:
        return {"error": "goal_text is required"}
    if goal_type not in GOAL_TYPES:
        goal_type = "custom"

    rules = params.get("rules") or {}
    user_id = getattr(session, "user_id", 0)
    envelope_id = getattr(session, "current_envelope_id", "") or ""

    goal_id = await db.create_goal(
        user_id=user_id,
        goal_type=goal_type,
        goal_text=goal_text,
        rules=rules,
        envelope_id=envelope_id,
    )

    if goal_id is None:
        return {"error": "failed to save goal (DB unavailable)"}

    return {"id": goal_id, "goal_text": goal_text, "goal_type": goal_type}


async def tool_deactivate_goal(params: dict, session, sheets, auth) -> dict:
    """
    Mark a goal as done/inactive.

    params:
      id (int): goal id

    Returns:
      {"ok": True} | {"error": "..."}
    """
    goal_id = params.get("id")
    if not goal_id:
        return {"error": "id is required"}

    ok = await db.deactivate_goal(int(goal_id))
    return {"ok": ok}


async def check_goals_against_transaction(
    user_id: int,
    amount_eur: float,
    category: str,
    sheets,
) -> list[str]:
    """
    Check the user's active goals against a newly added transaction.
    Returns a list of notification strings (empty if nothing noteworthy).
    Called after each successful expense save.
    """
    goals = await db.get_goals(user_id, active_only=True)
    if not goals:
        return []

    notifications = []
    for g in goals:
        rules = g.get("rules", {})
        gtype = g["goal_type"]

        if gtype == "expense_limit":
            limit = float(rules.get("limit_eur") or rules.get("target") or 0)
            cat_filter = str(rules.get("category", "")).strip()
            if limit > 0:
                if not cat_filter or cat_filter.lower() in category.lower():
                    # We can't easily check cumulative total here without a DB query.
                    # Just flag if a single transaction is over 30% of the limit.
                    pct = amount_eur / limit * 100
                    if pct >= 30:
                        notifications.append(
                            f"⚠️ Цель «{g['goal_text']}»: эта трата = {pct:.0f}% от бюджета ({limit:,.0f} EUR)"
                        )

        # For savings / contribution goals, progress tracking is done separately
        # (would require a summary query — deferred to a scheduled job)

    return notifications
