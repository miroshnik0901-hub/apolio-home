"""
Apolio Home — Intelligence Layer
Computes budget snapshot, category trends, anomalies, and goal progress.
Called by agent.py before each Claude API call to enrich the system prompt.
"""

import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from sheets import SheetsClient, safe_float
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
    """Parse transaction amount safely, handling European comma formats."""
    return safe_float(record.get("Amount_EUR") or record.get("Amount_Orig") or 0)


class IntelligenceEngine:
    """Pre-computes intelligence snapshot for agent context injection."""

    def __init__(self, sheets: SheetsClient):
        self.sheets = sheets

    def compute_snapshot(self, envelope_id: str) -> dict:
        """Compute a full intelligence snapshot for the given envelope.

        T-152: Result is cached on sheets.snapshot_cache for 30s to avoid
        recomputing on every agent turn (each call costs 3 Sheets reads).
        Cache is NOT invalidated on transaction writes — the 30s stale window
        is acceptable for context injection (not for balance display).
        Returns a dict ready to be formatted into the system prompt.
        """
        cache_key = f"snapshot_{envelope_id}"
        cached = self.sheets.snapshot_cache.get(cache_key)
        if cached is not None:
            return cached
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
            cap = safe_float(env_cfg.get("monthly_cap") or 0)
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

            snap = {
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
            # T-152: cache snapshot for 30s to reduce Sheets reads per minute
            self.sheets.snapshot_cache.set(cache_key, snap)
            return snap

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

        # T-202: Guard against empty config (happens when 429 silenced the read).
        # Empty config would fall into legacy solo-mode giving wrong obligation = total_expenses.
        if not env_config:
            logger.warning(f"compute_contribution_status: empty env_config for file_id={file_id[:20] if file_id else 'none'} — retrying once")
            try:
                env_config = sheets.read_envelope_config(file_id) or {}
                # Invalidate cache so next read is fresh
                sheets._cfg_cache.invalidate(f"env_config_{file_id}")
                env_config = sheets.read_envelope_config(file_id) or {}
            except Exception as _e:
                logger.error(f"compute_contribution_status: retry also failed: {_e}")

        split_users_raw  = env_config.get("split_users", "")
        split_users      = [u.strip() for u in split_users_raw.split(",") if u.strip()]
        base_contributor = env_config.get("base_contributor", "Mikhail")

        if not split_users:
            split_users = [base_contributor]

        # Detect new per-user model (min_<user> / split_<user> keys in Config).
        _has_per_user_min = any(f"min_{u}" in env_config for u in split_users)
        if not _has_per_user_min and env_config.get("split_users"):
            # Config loaded but no min_ keys — legacy mode is intentional
            pass
        elif not _has_per_user_min and not env_config.get("split_users"):
            logger.warning(f"compute_contribution_status: no split_users in config, using legacy mode. env_config keys: {list(env_config.keys())[:10]}")

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
        # joint_exp:    expenses from Joint account (informational only — NOT
        #               subtracted from obligation. Joint = shared bank account;
        #               who=u on a joint expense just means u initiated the payment
        #               from the shared pool, not that u used personal money.)
        top_up_joint: dict[str, float] = defaultdict(float)
        personal_exp: dict[str, float] = defaultdict(float)
        joint_exp: dict[str, float] = defaultdict(float)
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
            # Normalise names containing "joint" → Joint type
            if not acct_type and "joint" in acct.lower():
                acct_type = "Joint"
            if txn_type in ("income", "transfer"):
                if acct_type == "Joint" or not acct_type:
                    top_up_joint[who] += amt
            elif txn_type == "expense":
                if acct_type == "Personal":
                    personal_exp[who] += amt
                elif acct_type == "Joint":
                    joint_exp[who] += amt  # tracked for display; not used in obligation

        # Total expenses (all expense transactions regardless of account)
        total_expenses = sum(
            _parse_amount(t) for t in month_txns if t.get("Type") == "expense"
        )

        # ── Per-user model (xlsx formula: ApolioHome_UserBalance_formula) ──
        # obligation = (min - top_up) + max(0, split_base) * split% - personal_exp
        # credit = -obligation  (positive = overpaid, negative = owes)
        if _has_per_user_min and split_users:
            total_min_pool = sum(
                safe_float(env_config.get(f"min_{u}", 0)) for u in split_users
            )
            split_base = total_expenses - total_min_pool
            user_shares: dict[str, float] = {}
            for u in split_users:
                u_min   = safe_float(env_config.get(f"min_{u}", 0))
                u_split = safe_float(env_config.get(f"split_{u}", 0))
                from_min      = u_min - top_up_joint.get(u, 0.0)
                from_split    = max(0.0, split_base) * u_split / 100
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
            threshold     = safe_float(env_config.get("split_threshold", 0))
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
            balances[u] = round(-safe_float(user_shares.get(u, 0.0)), 2)

        # Build per-user contribution for display: top_up + personal_exp
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
            "top_up_joint": dict(top_up_joint),     # per-user income transfers to joint
            "personal_exp": dict(personal_exp),     # per-user expenses from Personal account
            "joint_exp": dict(joint_exp),           # per-user expenses from Joint account (display only)
            "has_account_types": has_account_types,
            "user_shares": user_shares,             # obligation per user
            "balances": balances,                   # credit per user (-obligation)
            "excess_amount": round(excess_amount, 2),
            "excess_per_user": round(excess_per_user, 2),
            # per-user min pool contributions (non-zero only if per_user_min model active)
            "per_user_min": {
                u: safe_float(env_config.get(f"min_{u}", 0)) for u in split_users
            } if _has_per_user_min else {},
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
    T-175: Return contribution snapshots for every month that has ≥1 non-deleted
    transaction, sorted oldest-first.

    The old months_back approach generated N calendar months backwards from today
    regardless of actual data — producing empty rows for months with no transactions
    and missing months older than months_back. This version:
      1. Reads all non-deleted transactions from the envelope.
      2. Extracts distinct YYYY-MM values from the Date column.
      3. Computes contribution_status per month, keeps only status==ok results.

    months_back is now ignored (kept for backward-compatible signature).
    """
    try:
        envelopes = sheets.get_envelopes()
        env = next((e for e in envelopes if e.get("ID") == envelope_id), None)
        if not env:
            return []
        file_id = env.get("file_id", "")
        if not file_id:
            return []
        env_sheets = sheets._env_sheets(file_id)
        txs = env_sheets.get_transactions({})
        # Collect distinct months from non-deleted transactions
        months_set: set[str] = set()
        for t in txs:
            date_str = t.get("Date", "")
            if date_str and len(date_str) >= 7 and t.get("Deleted", "FALSE") != "TRUE":
                months_set.add(date_str[:7])
    except Exception:
        return []

    results = []
    for month in sorted(months_set):
        snap = compute_contribution_status(sheets, envelope_id, month)
        if snap.get("status") == "ok":
            results.append(snap)
    return results


def compute_cumulative_balance(sheets: SheetsClient, envelope_id: str) -> dict:
    """
    T-167: Compute cumulative per-user balance from the FIRST transaction to today.

    Unlike compute_contribution_status (which is month-scoped), this function:
    1. Finds all months that have transactions
    2. Applies per-user min obligation for EVERY such month (even if user didn't transact that month)
    3. Sums credits/obligations across all months → cumulative balance

    Returns:
      {
        "status": "ok",
        "currency": "EUR",
        "split_users": [...],
        "months_counted": 3,
        "first_month": "2026-02",
        "cumulative_balances": {"Mikhail": -45.20, "Maryna": +45.20},
        "cumulative_obligations": {"Mikhail": 300.00, ...},
        "cumulative_contributions": {"Mikhail": 254.80, ...},
      }
    """
    try:
        envelopes = sheets.get_envelopes()
        env = next((e for e in envelopes if e.get("ID") == envelope_id), None)
        if not env:
            return {"error": "envelope_not_found"}

        file_id = env.get("file_id", "")
        currency = env.get("Currency", "EUR")

        env_config = sheets.read_envelope_config(file_id) if file_id else {}
        split_users_raw = env_config.get("split_users", "")
        split_users = [u.strip() for u in split_users_raw.split(",") if u.strip()]
        base_contributor = env_config.get("base_contributor", "Mikhail")
        if not split_users:
            split_users = [base_contributor]

        all_txns = sheets.get_transactions(file_id)
        # Filter out soft-deleted
        active_txns = [t for t in all_txns if str(t.get("Deleted", "")).upper() != "TRUE"]

        # Find all months that have at least one transaction
        months_with_txns = sorted({
            str(t.get("Date", ""))[:7] for t in active_txns
            if len(str(t.get("Date", ""))) >= 7
        })

        if not months_with_txns:
            return {
                "status": "ok", "currency": currency, "split_users": split_users,
                "months_counted": 0, "first_month": None,
                "cumulative_balances": {u: 0.0 for u in split_users},
                "cumulative_obligations": {u: 0.0 for u in split_users},
                "cumulative_contributions": {u: 0.0 for u in split_users},
            }

        # Accumulate balance per user across all months
        cumulative_obligations: dict[str, float] = defaultdict(float)
        cumulative_contributions: dict[str, float] = defaultdict(float)

        for month in months_with_txns:
            snap = compute_contribution_status(sheets, envelope_id, month)
            if snap.get("status") != "ok":
                continue
            for u in split_users:
                obligation = safe_float(snap.get("user_shares", {}).get(u, 0))
                contribution = safe_float(snap.get("assets", {}).get(u, 0))
                cumulative_obligations[u] += obligation
                cumulative_contributions[u] += contribution

        # Cumulative balance = sum of monthly credits = -(obligations)
        # Positive = overpaid overall, negative = owes overall
        cumulative_balances: dict[str, float] = {
            u: round(cumulative_contributions[u] - cumulative_obligations[u], 2)
            for u in split_users
        }

        return {
            "status": "ok",
            "currency": currency,
            "split_users": split_users,
            "months_counted": len(months_with_txns),
            "first_month": months_with_txns[0],
            "last_month": months_with_txns[-1],
            "cumulative_balances": dict(cumulative_balances),
            "cumulative_obligations": {u: round(v, 2) for u, v in cumulative_obligations.items()},
            "cumulative_contributions": {u: round(v, 2) for u, v in cumulative_contributions.items()},
        }

    except Exception as e:
        logger.error(f"compute_cumulative_balance failed: {e}", exc_info=True)
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
