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
from tools.transactions import _normalize_who

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

            # T-135: read cap/currency from envelope Config (single source of truth)
            env_cfg = self.sheets.read_envelope_config(file_id) if file_id else {}
            cap = float(env_cfg.get("monthly_cap") or 0)
            currency = env_cfg.get("currency") or env.get("Currency", "EUR")

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


def compute_contribution_status(sheets: SheetsClient, envelope_id: str,
                                month: str = None) -> dict:
    """
    Compute per-user contribution and expense split for the given month.

    Rules (from envelope's own Config tab):
      split_rule:         50_50 | solo
      split_threshold:    base EUR covered by base_contributor
      split_users:        comma-separated list of users in split
      base_contributor:   user who covers up to threshold

    Returns structured dict ready for formatting or tool response.
    """
    try:
        if not month:
            month = _current_month()

        envelopes = sheets.get_envelopes()
        env = next((e for e in envelopes if e.get("ID") == envelope_id), None)
        if not env:
            return {"error": "envelope_not_found"}

        file_id = env.get("file_id", "")
        currency = env.get("Currency", "EUR")

        # Read split settings from the envelope's own Config tab (not Admin Config).
        # Keys in the envelope Config tab are unprefixed: split_rule, split_threshold, etc.
        # Admin Config holds only global settings.
        env_config = sheets.read_envelope_config(file_id) if file_id else {}

        split_users_raw  = env_config.get("split_users", "")
        split_users      = [u.strip() for u in split_users_raw.split(",") if u.strip()]
        base_contributor = env_config.get("base_contributor", "Mikhail")

        if not split_users:
            split_users = [base_contributor]

        # Detect new per-user model (min_<user> / split_<user> keys in Config).
        _has_per_user_min = any(f"min_{u}" in env_config for u in split_users)

        all_txns = sheets.get_transactions(file_id)
        month_txns = [t for t in all_txns if str(t.get("Date", "")).startswith(month)]

        # Load known users for who-normalization (fixes "Maslo" → "Maryna" etc.)
        try:
            ref = sheets.get_reference_data(file_id)
            known_who = ref.get("who", [])
        except Exception:
            known_who = []

        # T-093: Read account types for asset calculation
        account_type_map: dict[str, str] = {}
        has_account_types = False
        try:
            env_sheets = sheets._env_sheets(file_id)
            accounts_typed = env_sheets.get_accounts_with_types()
            account_type_map = {a["name"]: a["type"] for a in accounts_typed if a["type"]}
            has_account_types = bool(account_type_map)
        except Exception:
            pass

        # ── Collect per-user data from transactions ─────────────────────────
        # top_up_joint: income/transfer to Joint account (or no account = Joint)
        # personal_exp: expenses from Personal account
        # All used in the xlsx obligation formula.
        top_up_joint: dict[str, float] = defaultdict(float)
        personal_exp: dict[str, float] = defaultdict(float)
        for t in month_txns:
            who_raw = t.get("Who", "Unknown")
            who = _normalize_who(who_raw, known_who) or who_raw
            amt = _parse_amount(t)
            if amt <= 0:
                continue
            txn_type = t.get("Type", "")
            acct = t.get("Account", "")
            # Resolve account type: direct value first, then map lookup
            if acct in ("Joint", "Personal"):
                acct_type = acct
            else:
                acct_type = account_type_map.get(acct, "")
            if txn_type in ("income", "transfer"):
                if acct_type == "Joint" or not acct_type:
                    top_up_joint[who] += amt
            elif txn_type == "expense":
                if acct_type == "Personal":
                    personal_exp[who] += amt

        # Total expenses (all expense transactions regardless of account)
        total_expenses = sum(
            _parse_amount(t) for t in month_txns if t.get("Type") == "expense"
        )

        # ── Per-user model (xlsx formula: ApolioHome_UserBalance_formula) ──
        # obligation = (min - top_up) + max(0, split_base) * split% - personal_exp
        # credit = -obligation  (positive = overpaid, negative = owes)
        if _has_per_user_min and split_users:
            total_min_pool = sum(
                float(env_config.get(f"min_{u}", 0) or 0) for u in split_users
            )
            split_base = total_expenses - total_min_pool
            user_shares: dict[str, float] = {}
            for u in split_users:
                u_min   = float(env_config.get(f"min_{u}", 0) or 0)
                u_split = float(env_config.get(f"split_{u}", 0) or 0)
                from_min = u_min - top_up_joint.get(u, 0.0)
                from_split = max(0.0, split_base) * u_split / 100
                from_personal = -personal_exp.get(u, 0.0)
                obligation = from_min + from_split + from_personal
                user_shares[u] = round(obligation, 2)
            threshold       = total_min_pool
            excess_amount   = max(0.0, split_base)
            excess_per_user = excess_amount / len(split_users) if split_users else 0.0
            split_rule      = "per_user"

        # ── Legacy split_rule model ────────────────────────────────────────
        else:
            split_rule    = env_config.get("split_rule", "solo")
            threshold     = float(env_config.get("split_threshold", 0) or 0)
            if split_rule == "solo" or len(split_users) == 0:
                user_shares   = {base_contributor: total_expenses}
                excess_amount = 0.0
                excess_per_user = 0.0
            else:
                excess_amount   = max(0.0, total_expenses - threshold)
                covered_by_base = min(total_expenses, threshold)
                excess_per_user = excess_amount / len(split_users) if split_users else 0.0
                user_shares = {}
                for u in split_users:
                    share = excess_per_user
                    if u == base_contributor:
                        share += covered_by_base
                    user_shares[u] = round(share, 2)

        # Credit = -obligation (positive = overpaid / owed to you, negative = you owe)
        balances: dict[str, float] = {}
        for u in split_users:
            balances[u] = round(-float(user_shares.get(u, 0.0)), 2)

        # Build per-user top_up + personal for display
        assets: dict[str, float] = {}
        for u in split_users:
            assets[u] = round(top_up_joint.get(u, 0.0) + personal_exp.get(u, 0.0), 2)

        return {
            "status": "ok",
            "month": month,
            "currency": currency,
            "split_rule": split_rule,
            "threshold": threshold,
            "base_contributor": base_contributor,
            "split_users": split_users,
            "total_expenses": round(total_expenses, 2),
            "contributions": assets,                # backward compat key
            "assets": assets,                       # top_up + personal per user
            "top_up_joint": dict(top_up_joint),     # per-user top-up to joint
            "personal_exp": dict(personal_exp),     # per-user personal expenses
            "has_account_types": has_account_types,
            "user_shares": user_shares,             # obligation per user
            "balances": balances,                   # credit per user (-obligation)
            "excess_amount": round(excess_amount, 2),
            "excess_per_user": round(excess_per_user, 2),
        }

    except Exception as e:
        logger.error(f"compute_contribution_status failed: {e}", exc_info=True)
        return {"error": str(e)}


def format_contribution_for_prompt(snap: dict) -> str:
    """
    Compact text block injected into system prompt so the agent always
    knows the current contribution/split state.
    """
    if snap.get("error") or snap.get("status") != "ok":
        return ""

    cur = snap["currency"]
    month = snap["month"]
    threshold = snap["threshold"]
    total_exp = snap["total_expenses"]
    contributions = snap.get("assets", snap.get("contributions", {}))
    balances = snap["balances"]
    excess = snap["excess_amount"]
    excess_per = snap["excess_per_user"]
    split_users = snap["split_users"]
    base_c = snap["base_contributor"]
    has_account_types = snap.get("has_account_types", False)

    top_up = snap.get("top_up_joint", {})
    pers_exp = snap.get("personal_exp", {})
    user_shares = snap.get("user_shares", {})

    lines = [f"## CONTRIBUTION & SPLIT STATUS ({month})"]
    lines.append(f"Total expenses: {total_exp:.2f} {cur}")
    if threshold > 0:
        lines.append(f"Min pool: {threshold:.0f} {cur}, overflow: {excess:.2f} {cur}")

    # Per-user: obligation and credit
    for u in split_users:
        tu = top_up.get(u, 0)
        pe = pers_exp.get(u, 0)
        obl = user_shares.get(u, 0)
        credit = balances.get(u, 0)
        sign = "+" if credit >= 0 else ""
        lines.append(
            f"{u}: top_up={tu:.0f}, personal={pe:.0f}, "
            f"obligation={obl:.0f}, credit={sign}{credit:.0f} {cur}"
        )

    return "\n".join(lines)


def compute_contribution_history(sheets: SheetsClient, envelope_id: str,
                                  months_back: int = 6) -> list[dict]:
    """
    Return a list of compute_contribution_status snapshots for the last
    months_back months (oldest first). Skips months with errors.
    """
    results = []
    month = _current_month()
    for _ in range(months_back):
        snap = compute_contribution_status(sheets, envelope_id, month)
        if snap.get("status") == "ok":
            results.insert(0, snap)
        month = _prev_month(month)
    return results


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
