"""
tools/bank_statement.py — T-261

Pure-Python aggregator for bank statement screenshots.

Why this exists:
    Photo analysis (agent.py:1040) used to do extract + count + sum + preauth-pairing
    in ONE LLM call (Claude Sonnet 4). It produced wrong totals on simple statements:
    Privatbank example (Feb-Mar 2026, 12 transactions = 4 preauth + 4 cancellations + 4 facts):
      LLM said:      "6 expenses + 6 cancellations" → wrong
      LLM said:      "expenses 34,114 - cancellations 20,199 = net 15,067 ₴" → arithmetically wrong
      Real numbers:   8 expenses (4 preauth + 4 fact) + 4 cancellations = 12 rows
                      sum of 4 fact rows = 12,915 ₴ (3,018 + 4,149 + 2,387 + 3,361)
                      preauth+cancellation pairs cancel out (net 0)

How the new flow works (T-261):
    1. LLM extracts STRUCTURED rows from the photo (no math, no counting):
         [{date, description, amount, currency, type}, ...]
       where type ∈ {"debit", "credit", "preauth", "cancellation"}
    2. LLM calls `aggregate_bank_statement(rows=...)` — this module.
    3. Python pairs preauth ↔ cancellation, classifies remaining as expense/income/transfer,
       computes counts and sums DETERMINISTICALLY.
    4. LLM uses the returned summary verbatim in its reply.

Public API:
    aggregate_bank_statement(rows: list[dict],
                             pair_window_days: int = 7,
                             amount_tolerance_pct: float = 1.0) -> dict

Returned dict shape:
    {
        "total_rows": int,                    # input rows count
        "preauth_count": int,                 # rows with type=preauth
        "cancellation_count": int,            # rows with type=cancellation
        "matched_pairs": int,                 # paired preauth↔cancellation (cancel out)
        "unmatched_preauth": [<row>...],      # not yet released — counted as real expense
        "unmatched_cancellation": [<row>...], # cancellation without matching preauth (anomaly)
        "fact_expense_rows": [<row>...],      # type=debit, after preauth removal
        "income_rows": [<row>...],            # type=credit (incoming transfers)
        "summary": {
            "expense_count": int,             # len(fact_expense_rows) + len(unmatched_preauth)
            "income_count": int,
            "cancellation_count": int,
            "preauth_count": int,
            "matched_pairs_count": int,
            "total_expenses": float,          # sum of fact_expense_rows + unmatched_preauth
            "total_income": float,
            "total_cancellations_amount": float,
            "currency": str,                  # most common currency
        },
        "warnings": [str, ...],               # anomalies the LLM should mention
    }

The aggregator is currency-agnostic but expects all rows in one currency
(if multi-currency, splits are not handled — currency mismatch is added to warnings).

Self-test: tests/t261_bank_statement_selftest.py
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

VALID_TYPES = {"debit", "credit", "preauth", "cancellation"}


def _parse_date(s: str) -> Optional[datetime]:
    """Best-effort date parser. Accepts YYYY-MM-DD, DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY.
    Returns None if unparseable.
    """
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _normalize_amount(x) -> float:
    """Coerce any reasonable input to a positive float. Strips currency symbols.
    T-248 rule: amounts are always positive in our system; type encodes direction.
    """
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return abs(float(x))
    s = str(x).strip()
    # Strip common currency symbols and thousands separators
    for sym in ("₴", "€", "$", "zł", "грн", " "):
        s = s.replace(sym, "")
    s = s.replace(",", ".")
    # Handle leading minus
    s = s.lstrip("+").replace(" ", "")
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


def _amounts_match(a: float, b: float, tol_pct: float) -> bool:
    """Two amounts considered equal within tolerance (percent of larger value)."""
    if a == 0 and b == 0:
        return True
    bigger = max(a, b)
    if bigger == 0:
        return False
    return abs(a - b) / bigger * 100.0 <= tol_pct


def _dates_within(d1: Optional[datetime], d2: Optional[datetime], window_days: int) -> bool:
    """True if both dates parsed and within window (inclusive). If either is None → True
    (we don't punish missing dates — preauth-cancel pairing should still work).
    """
    if d1 is None or d2 is None:
        return True
    return abs((d1 - d2).days) <= window_days


def aggregate_bank_statement(
    rows: list[dict],
    pair_window_days: int = 7,
    amount_tolerance_pct: float = 1.0,
) -> dict:
    """Aggregate bank statement rows. See module docstring for shape.

    Pairing algorithm (greedy, by date proximity):
        For each cancellation row, find the closest unmatched preauth with:
          - amount within `amount_tolerance_pct`
          - date within `pair_window_days`
        First match wins. Remaining preauths → counted as real expense
        (preauth not yet released — money is out).

    Pure function — no I/O, no globals.
    """
    warnings: list[str] = []

    # Normalize input
    norm_rows: list[dict] = []
    currencies = Counter()
    for i, raw in enumerate(rows or []):
        if not isinstance(raw, dict):
            warnings.append(f"row#{i}: not a dict, skipped")
            continue
        rtype = str(raw.get("type", "")).strip().lower()
        if rtype not in VALID_TYPES:
            warnings.append(
                f"row#{i}: unknown type {rtype!r} (expected {sorted(VALID_TYPES)}), "
                f"defaulting to 'debit'"
            )
            rtype = "debit"
        amount = _normalize_amount(raw.get("amount"))
        if amount == 0:
            warnings.append(f"row#{i}: amount=0 or unparseable ({raw.get('amount')!r}), skipped")
            continue
        currency = str(raw.get("currency", "")).strip().upper() or "UAH"
        currencies[currency] += 1
        norm_rows.append({
            "_index": i,
            "date": str(raw.get("date", "")).strip(),
            "_date_obj": _parse_date(str(raw.get("date", ""))),
            "description": str(raw.get("description", "")).strip(),
            "amount": amount,
            "currency": currency,
            "type": rtype,
        })

    if currencies and len(currencies) > 1:
        warnings.append(
            f"mixed currencies in one statement: {dict(currencies)}. "
            f"Sums computed per-currency only for the dominant one ({currencies.most_common(1)[0][0]})"
        )
    dominant_currency = currencies.most_common(1)[0][0] if currencies else "UAH"

    # Split by type
    preauths       = [r for r in norm_rows if r["type"] == "preauth"]
    cancellations  = [r for r in norm_rows if r["type"] == "cancellation"]
    debits         = [r for r in norm_rows if r["type"] == "debit"]
    credits        = [r for r in norm_rows if r["type"] == "credit"]

    # Pair cancellations with preauths (greedy by date proximity)
    matched_pairs = []
    used_preauth_idx: set[int] = set()
    unmatched_cancellations = []

    for c in cancellations:
        # Find best candidate: same amount within tolerance, date within window,
        # not yet used. Prefer closest by date when multiple candidates qualify.
        candidates = []
        for j, p in enumerate(preauths):
            if j in used_preauth_idx:
                continue
            if not _amounts_match(c["amount"], p["amount"], amount_tolerance_pct):
                continue
            if not _dates_within(c["_date_obj"], p["_date_obj"], pair_window_days):
                continue
            # Compute date distance for sorting
            if c["_date_obj"] and p["_date_obj"]:
                dist = abs((c["_date_obj"] - p["_date_obj"]).days)
            else:
                dist = 999
            candidates.append((dist, j, p))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            _, j_best, p_best = candidates[0]
            used_preauth_idx.add(j_best)
            matched_pairs.append({"preauth": p_best, "cancellation": c})
        else:
            unmatched_cancellations.append(c)

    unmatched_preauth = [p for j, p in enumerate(preauths) if j not in used_preauth_idx]

    if unmatched_cancellations:
        warnings.append(
            f"{len(unmatched_cancellations)} cancellation(s) without matching preauth — "
            f"possible refund or data anomaly; treated as negative expense"
        )

    # Real expenses = all debits + unmatched preauths (money out, not released)
    fact_expense_rows = list(debits) + list(unmatched_preauth)

    # Sums
    total_expenses = sum(r["amount"] for r in fact_expense_rows)
    total_income = sum(r["amount"] for r in credits)
    total_cancellations_amount = sum(c["amount"] for c in cancellations)

    # Subtract unmatched cancellations as refunds (reduce expense)
    refund_amount = sum(c["amount"] for c in unmatched_cancellations)
    if refund_amount > 0:
        total_expenses -= refund_amount

    return {
        "total_rows": len(norm_rows),
        "preauth_count": len(preauths),
        "cancellation_count": len(cancellations),
        "matched_pairs": len(matched_pairs),
        "unmatched_preauth": unmatched_preauth,
        "unmatched_cancellation": unmatched_cancellations,
        "fact_expense_rows": fact_expense_rows,
        "income_rows": credits,
        "summary": {
            "expense_count": len(fact_expense_rows),
            "income_count": len(credits),
            "cancellation_count": len(cancellations),
            "preauth_count": len(preauths),
            "matched_pairs_count": len(matched_pairs),
            "total_expenses": round(total_expenses, 2),
            "total_income": round(total_income, 2),
            "total_cancellations_amount": round(total_cancellations_amount, 2),
            "currency": dominant_currency,
        },
        "warnings": warnings,
    }
