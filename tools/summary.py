"""Summary and budget status tools"""
from datetime import datetime
from collections import defaultdict
from typing import Any

from sheets import SheetsClient
from auth import AuthManager, SessionContext


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


async def tool_get_summary(params: dict, session: SessionContext,
                            sheets: SheetsClient, auth: AuthManager) -> Any:
    envelope_id = params.get("envelope_id") or session.current_envelope_id
    if not auth.can_access_envelope(session.user_id, envelope_id):
        return {"error": "Permission denied."}

    period = params.get("period", "current")
    if period == "current":
        period = _current_month()
    elif period == "last":
        y, m = map(int, _current_month().split("-"))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        period = f"{y:04d}-{m:02d}"

    envelopes = sheets.get_envelopes()
    file_id = next((e["file_id"] for e in envelopes
                    if e.get("ID") == envelope_id), None)
    if not file_id:
        return {"error": "Envelope not found."}

    records = sheets.get_transactions(file_id)
    month_records = [r for r in records
                     if str(r.get("Date", "")).startswith(period)
                     and r.get("Type") == "expense"]

    by_category = defaultdict(float)
    by_who = defaultdict(float)
    total = 0.0

    for r in month_records:
        amt = float(r.get("Amount_EUR") or r.get("Amount_Orig") or 0)
        cat = r.get("Category", "Other")
        who = r.get("Who", "Unknown")
        by_category[cat] += amt
        by_who[who] += amt
        total += amt

    breakdown_by = params.get("breakdown_by", "category")
    breakdown = dict(by_category) if breakdown_by == "category" else dict(by_who)

    return {
        "status": "ok",
        "envelope_id": envelope_id,
        "period": period,
        "total_spent": round(total, 2),
        "categories": {k: round(v, 2) for k, v in by_category.items()},
        "by_who": {k: round(v, 2) for k, v in by_who.items()},
        "breakdown": {k: round(v, 2) for k, v in breakdown.items()},
    }


async def tool_get_budget_status(params: dict, session: SessionContext,
                                  sheets: SheetsClient, auth: AuthManager) -> Any:
    envelope_id = params.get("envelope_id") or session.current_envelope_id
    if not auth.can_access_envelope(session.user_id, envelope_id):
        return {"error": "Permission denied."}

    config = sheets.read_config()
    envelopes = sheets.get_envelopes()
    env = next((e for e in envelopes if e.get("ID") == envelope_id), None)
    if not env:
        return {"error": "Envelope not found."}

    # Monthly_Cap is a direct column in the Envelopes sheet (not a JSON field)
    cap = float(env.get("Monthly_Cap") or env.get("monthly_cap") or
                config.get(f"budget_{envelope_id}_monthly", 0))

    month = _current_month()
    file_id = env["file_id"]
    records = sheets.get_transactions(file_id)
    month_records = [r for r in records
                     if str(r.get("Date", "")).startswith(month)
                     and r.get("Type") == "expense"]

    spent = sum(float(r.get("Amount_EUR") or r.get("Amount_Orig") or 0)
                for r in month_records)
    remaining = cap - spent
    pct = round(spent / cap * 100, 1) if cap else 0
    threshold = float(config.get("alert_threshold_pct", 80))

    return {
        "status": "ok",
        "envelope_id": envelope_id,
        "month": month,
        "cap": cap,
        "spent": round(spent, 2),
        "remaining": round(remaining, 2),
        "pct_used": pct,
        "alert": pct >= threshold,
    }
