"""
Apolio Home — Intelligence Layer
Computes budget snapshot, category trends, anomalies, and goal progress.
Called by agent.py before each Claude API call to enrich the system prompt.
"""

import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from sheets import SheetsClient

logger = logging.getLogger(__name__)


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def _prev_month(month_str: str) -> str:
    y, m = map(int, month_str.split("-"))
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y:04d}-{m:02d}"


def _days_left_in_month() -> int:
    now = datetime.now()
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1)
    else:
        end = datetime(now.year, now.month + 1, 1)
    return (end - now).days


def _parse_amount(record: dict) -> float:
    try:
        return float(record.get("Amount_EUR") or record.get("Amount_Orig") or 0)
    except (ValueError, TypeError):
        return 0.0


class IntelligenceEngine:
    """Pre-computes intelligence snapshot for agent context injection."""

    def __init__(self, sheets: SheetsClient):
        self.sheets = sheets

    def compute_snapshot(self, envelope_id: str) -> dict:
        """
        Compute a full intelligence snapshot for the given envelope.
        Returns a dict ready to be formatted into the system prompt.
        """
        try:
            envelopes = self.sheets.get_envelopes()
            env = next((e for e in envelopes if e.get("ID") == envelope_id), None)
            if not env:
                return {"error": "envelope_not_found"}

            file_id = env.get("file_id", "")
            if not file_id:
                return {"error": "no_file_id"}

            cap = float(env.get("Monthly_Cap") or env.get("monthly_cap") or 0)
            currency = env.get("Currency", "EUR")

            all_txns = self.sheets.get_transactions(file_id)
            month = _current_month()
            prev = _prev_month(month)
            prev2 = _prev_month(prev)

            # Current month expenses
            cur_expenses = [
                r for r in all_txns
                if str(r.get("Date", "")).startswith(month)
                and r.get("Type") == "expense"
            ]
            prev_expenses = [
                r for r in all_txns
                if str(r.get("Date", "")).startswith(prev)
                and r.get("Type") == "expense"
            ]
            prev2_expenses = [
                r for r in all_txns
                if str(r.get("Date", "")).startswith(prev2)
                and r.get("Type") == "expense"
            ]

            # Budget status
            spent = sum(_parse_amount(r) for r in cur_expenses)
            remaining = cap - spent if cap else None
            pct = round(spent / cap * 100, 1) if cap else 0
            days_left = _days_left_in_month()
            day_of_month = datetime.now().day

            # Pace calculation
            if day_of_month > 0 and cap > 0:
                daily_rate = spent / day_of_month
                projected = daily_rate * (day_of_month + days_left)
                pace_status = "on_track"
                if projected > cap * 1.05:
                    pace_status = "over_pace"
                elif projected < cap * 0.7:
                    pace_status = "under_pace"
            else:
                daily_rate = 0
                projected = 0
                pace_status = "unknown"

            # Category breakdown — current vs previous month
            cur_by_cat = defaultdict(float)
            for r in cur_expenses:
                cur_by_cat[r.get("Category", "Other")] += _parse_amount(r)

            prev_by_cat = defaultdict(float)
            for r in prev_expenses:
                prev_by_cat[r.get("Category", "Other")] += _parse_amount(r)

            # 3-month average for anomaly detection
            avg_by_cat = defaultdict(float)
            months_data = [prev_expenses, prev2_expenses]
            month_count = sum(1 for m in months_data if m)  # non-empty months
            if month_count > 0:
                for month_txns in months_data:
                    for r in month_txns:
                        avg_by_cat[r.get("Category", "Other")] += _parse_amount(r)
                for cat in avg_by_cat:
                    avg_by_cat[cat] /= month_count

            # Trends — category changes vs previous month
            trends = []
            for cat, cur_amt in sorted(cur_by_cat.items(), key=lambda x: -x[1]):
                prev_amt = prev_by_cat.get(cat, 0)
                if prev_amt > 0:
                    change_pct = round((cur_amt - prev_amt) / prev_amt * 100, 0)
                    if abs(change_pct) >= 10:
                        direction = "↑" if change_pct > 0 else "↓"
                        trends.append({
                            "category": cat,
                            "current": round(cur_amt, 2),
                            "previous": round(prev_amt, 2),
                            "change_pct": change_pct,
                            "direction": direction,
                        })

            # Anomalies — >1.5x average
            anomalies = []
            for cat, cur_amt in cur_by_cat.items():
                avg_amt = avg_by_cat.get(cat, 0)
                if avg_amt > 0 and cur_amt > avg_amt * 1.5:
                    anomalies.append({
                        "category": cat,
                        "current": round(cur_amt, 2),
                        "average": round(avg_amt, 2),
                        "ratio": round(cur_amt / avg_amt, 1),
                    })

            # Recent large transactions (last 7 days, >50 EUR)
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            large_recent = []
            for r in cur_expenses:
                amt = _parse_amount(r)
                if r.get("Date", "") >= week_ago and amt > 50:
                    large_recent.append({
                        "date": r.get("Date"),
                        "amount": round(amt, 2),
                        "category": r.get("Category", ""),
                        "note": r.get("Note", ""),
                    })

            return {
                "status": "ok",
                "month": month,
                "currency": currency,
                "cap": cap,
                "spent": round(spent, 2),
                "remaining": round(remaining, 2) if remaining is not None else None,
                "pct_used": pct,
                "days_left": days_left,
                "daily_rate": round(daily_rate, 2),
                "projected_total": round(projected, 2),
                "pace_status": pace_status,
                "top_categories": {
                    k: round(v, 2) for k, v in
                    sorted(cur_by_cat.items(), key=lambda x: -x[1])[:5]
                },
                "trends": trends[:5],
                "anomalies": anomalies,
                "large_recent": large_recent[:3],
                "transaction_count": len(cur_expenses),
            }

        except Exception as e:
            logger.error(f"Intelligence snapshot failed: {e}", exc_info=True)
            return {"error": str(e)}


def format_snapshot_for_prompt(snap: dict) -> str:
    """
    Format the intelligence snapshot as a compact text block
    for injection into the agent system prompt.
    """
    if snap.get("error"):
        return ""

    lines = []

    # Budget state
    cur = snap.get("currency", "EUR")
    lines.append("## CURRENT BUDGET STATE")
    lines.append(
        f"Spent: {snap['spent']} {cur} of {snap['cap']} {cur} "
        f"({snap['pct_used']}%) | Remaining: {snap.get('remaining', '?')} {cur}"
    )
    lines.append(
        f"Days left: {snap['days_left']} | Daily rate: {snap['daily_rate']} {cur}/day | "
        f"Projected total: {snap['projected_total']} {cur}"
    )
    pace_labels = {
        "on_track": "ON TRACK",
        "over_pace": "⚠ OVER PACE — projected to exceed budget",
        "under_pace": "Under budget — good",
        "unknown": "",
    }
    pace = pace_labels.get(snap.get("pace_status", ""), "")
    if pace:
        lines.append(f"Pace: {pace}")

    # Top categories
    top = snap.get("top_categories", {})
    if top:
        lines.append("")
        lines.append("## TOP CATEGORIES THIS MONTH")
        for cat, amt in top.items():
            lines.append(f"  {cat}: {amt} {cur}")

    # Trends
    trends = snap.get("trends", [])
    if trends:
        lines.append("")
        lines.append("## CATEGORY TRENDS (vs last month)")
        for t in trends:
            lines.append(
                f"  {t['direction']} {t['category']}: "
                f"{t['current']} {cur} ({t['change_pct']:+.0f}%)"
            )

    # Anomalies
    anomalies = snap.get("anomalies", [])
    if anomalies:
        lines.append("")
        lines.append("## ⚠ ANOMALIES (significantly above average)")
        for a in anomalies:
            lines.append(
                f"  {a['category']}: {a['current']} {cur} "
                f"(avg: {a['average']} {cur}, {a['ratio']}x higher)"
            )

    return "\n".join(lines)
