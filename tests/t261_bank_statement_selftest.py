#!/usr/bin/env python3
"""Self-test for T-261 — pure-Python bank-statement aggregator.

Real-world fixture: the Privatbank screenshot from 2026-04-19 that exposed the bug.
Old LLM-only flow said "6 expenses + 6 cancellations, net 15,067 ₴" — both wrong.
Real values: 8 expense rows (4 preauth + 4 fact debit) + 4 cancellations,
4 preauth↔cancellation pairs match → net = 4 fact debits = 12,915 ₴
(3,018 + 4,149 + 2,387 + 3,361).

Run: python3 tests/t261_bank_statement_selftest.py
Exits 0 on success, 1 on failure.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.bank_statement import aggregate_bank_statement

FAIL = 0


def assert_eq(label, got, expected):
    global FAIL
    ok = got == expected
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}: got={got!r}  expected={expected!r}")
    if not ok:
        FAIL += 1


def assert_close(label, got, expected, tol=0.01):
    global FAIL
    ok = abs(got - expected) <= tol
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}: got={got}  expected={expected}  (tol={tol})")
    if not ok:
        FAIL += 1


def assert_true(label, cond, detail=""):
    global FAIL
    mark = "✓" if cond else "✗"
    print(f"  {mark} {label}  {detail}")
    if not cond:
        FAIL += 1


# ── Fixture: Privatbank Feb-Mar 2026 statement ────────────────────────────────
# 4 preauth (gas station authorizations) + 4 cancellations (matching) + 4 fact debits.
# Pairs cancel out → net expense = 4 fact = 12,915 ₴.

PRIVATBANK_FIXTURE = [
    # 4 preauth rows (temporarily blocked)
    {"date": "2026-02-15", "description": "WOG AUTH",     "amount": 5295.00, "currency": "UAH", "type": "preauth"},
    {"date": "2026-02-22", "description": "OKKO AUTH",    "amount": 5295.00, "currency": "UAH", "type": "preauth"},
    {"date": "2026-03-01", "description": "WOG AUTH",     "amount": 5295.00, "currency": "UAH", "type": "preauth"},
    {"date": "2026-03-08", "description": "BRSM AUTH",    "amount": 5295.00, "currency": "UAH", "type": "preauth"},
    # 4 cancellations (released funds, ~3 days later)
    {"date": "2026-02-18", "description": "WOG CANCEL",   "amount": 5295.00, "currency": "UAH", "type": "cancellation"},
    {"date": "2026-02-25", "description": "OKKO CANCEL",  "amount": 5295.00, "currency": "UAH", "type": "cancellation"},
    {"date": "2026-03-04", "description": "WOG CANCEL",   "amount": 5295.00, "currency": "UAH", "type": "cancellation"},
    {"date": "2026-03-11", "description": "BRSM CANCEL",  "amount": 5295.00, "currency": "UAH", "type": "cancellation"},
    # 4 fact debits (real fuel charges — these are the real expense)
    {"date": "2026-02-18", "description": "WOG FACT",     "amount": 3018.00, "currency": "UAH", "type": "debit"},
    {"date": "2026-02-25", "description": "OKKO FACT",    "amount": 4149.00, "currency": "UAH", "type": "debit"},
    {"date": "2026-03-04", "description": "WOG FACT",     "amount": 2387.00, "currency": "UAH", "type": "debit"},
    {"date": "2026-03-11", "description": "BRSM FACT",    "amount": 3361.00, "currency": "UAH", "type": "debit"},
]


def test_privatbank_statement():
    print("\n[T-261] Privatbank fixture — 4 preauth + 4 cancel + 4 fact = 12 rows")
    result = aggregate_bank_statement(PRIVATBANK_FIXTURE)
    s = result["summary"]

    assert_eq("total_rows",          result["total_rows"],          12)
    assert_eq("preauth_count",       result["preauth_count"],        4)
    assert_eq("cancellation_count",  result["cancellation_count"],   4)
    assert_eq("matched_pairs",       result["matched_pairs"],        4)
    assert_eq("unmatched_preauth",   len(result["unmatched_preauth"]), 0)
    assert_eq("unmatched_cancel",    len(result["unmatched_cancellation"]), 0)
    assert_eq("fact_expense_rows",   len(result["fact_expense_rows"]), 4)
    assert_eq("income_rows",         len(result["income_rows"]),     0)

    # The bug in the old flow: LLM said total 15,067 ₴; real total is 12,915.
    expected_total = 3018.0 + 4149.0 + 2387.0 + 3361.0  # = 12915.0
    assert_close("total_expenses",   s["total_expenses"], expected_total)
    assert_eq("currency",            s["currency"],         "UAH")
    assert_eq("expense_count",       s["expense_count"],    4)
    assert_eq("matched_pairs_count", s["matched_pairs_count"], 4)

    # Hint should NOT be auto-attached at module level (only via agent wrapper);
    # but warnings list should be empty for this clean fixture.
    assert_eq("warnings", result["warnings"], [])


# ── Anomaly cases ─────────────────────────────────────────────────────────────

def test_unmatched_preauth_counts_as_expense():
    print("\n[T-261] preauth without cancellation → counted as real expense")
    rows = [
        {"date": "2026-04-01", "description": "AUTH 100", "amount": 100.0, "currency": "UAH", "type": "preauth"},
        {"date": "2026-04-01", "description": "REAL 50",  "amount":  50.0, "currency": "UAH", "type": "debit"},
    ]
    r = aggregate_bank_statement(rows)
    assert_eq("matched_pairs", r["matched_pairs"], 0)
    assert_eq("unmatched_preauth", len(r["unmatched_preauth"]), 1)
    assert_close("total_expenses", r["summary"]["total_expenses"], 150.0)  # 100 + 50


def test_unmatched_cancel_reduces_expense():
    print("\n[T-261] cancellation without preauth → reduces total (refund)")
    rows = [
        {"date": "2026-04-01", "description": "BUY 200",     "amount": 200.0, "currency": "UAH", "type": "debit"},
        {"date": "2026-04-02", "description": "REFUND 30",   "amount":  30.0, "currency": "UAH", "type": "cancellation"},
    ]
    r = aggregate_bank_statement(rows)
    assert_eq("unmatched_cancellation", len(r["unmatched_cancellation"]), 1)
    assert_close("total_expenses (200 - 30 refund)", r["summary"]["total_expenses"], 170.0)
    assert_true("warnings non-empty (refund flagged)", len(r["warnings"]) >= 1)


def test_amount_tolerance_pairing():
    print("\n[T-261] preauth/cancel within 1% tolerance still pair")
    rows = [
        {"date": "2026-04-01", "description": "AUTH",   "amount": 100.00, "currency": "UAH", "type": "preauth"},
        {"date": "2026-04-02", "description": "CANCEL", "amount":  99.50, "currency": "UAH", "type": "cancellation"},  # 0.5% off
    ]
    r = aggregate_bank_statement(rows)
    assert_eq("matched_pairs (within 1%)", r["matched_pairs"], 1)


def test_date_window_pairing():
    print("\n[T-261] preauth/cancel outside 7-day window do NOT pair")
    rows = [
        {"date": "2026-04-01", "description": "AUTH",   "amount": 100.0, "currency": "UAH", "type": "preauth"},
        {"date": "2026-04-15", "description": "CANCEL", "amount": 100.0, "currency": "UAH", "type": "cancellation"},  # 14 days
    ]
    r = aggregate_bank_statement(rows)
    assert_eq("matched_pairs (>7d apart)", r["matched_pairs"], 0)
    assert_eq("unmatched_preauth", len(r["unmatched_preauth"]), 1)
    assert_eq("unmatched_cancel", len(r["unmatched_cancellation"]), 1)


def test_multi_currency_warning():
    print("\n[T-261] mixed currencies → warning, dominant currency wins")
    rows = [
        {"date": "2026-04-01", "amount": 100.0, "currency": "UAH", "type": "debit"},
        {"date": "2026-04-01", "amount": 200.0, "currency": "UAH", "type": "debit"},
        {"date": "2026-04-01", "amount":  50.0, "currency": "EUR", "type": "debit"},
    ]
    r = aggregate_bank_statement(rows)
    assert_eq("currency (dominant)", r["summary"]["currency"], "UAH")
    assert_true("warning about mixed currencies",
                any("mixed currencies" in w for w in r["warnings"]))


def test_amount_normalization():
    print("\n[T-261] amount strings with currency symbols/commas normalize correctly")
    rows = [
        {"date": "2026-04-01", "amount": "1 234,56 ₴", "currency": "UAH", "type": "debit"},
        {"date": "2026-04-01", "amount": "-100.00",    "currency": "UAH", "type": "debit"},
    ]
    r = aggregate_bank_statement(rows)
    assert_close("total_expenses (normalized)", r["summary"]["total_expenses"], 1334.56)


def test_unknown_type_defaults_to_debit():
    print("\n[T-261] unknown row type → warning + treated as debit")
    rows = [
        {"date": "2026-04-01", "amount": 50.0, "currency": "UAH", "type": "withdrawal"},  # invalid
    ]
    r = aggregate_bank_statement(rows)
    assert_eq("counted as expense", r["summary"]["expense_count"], 1)
    assert_true("warning about unknown type",
                any("unknown type" in w for w in r["warnings"]))


def test_empty_input():
    print("\n[T-261] empty input → all zeros, no crash")
    r = aggregate_bank_statement([])
    assert_eq("total_rows", r["total_rows"], 0)
    assert_eq("expense_count", r["summary"]["expense_count"], 0)


def main():
    print("=" * 70)
    print("T-261 Bank-statement aggregator self-test")
    print("=" * 70)

    test_privatbank_statement()
    test_unmatched_preauth_counts_as_expense()
    test_unmatched_cancel_reduces_expense()
    test_amount_tolerance_pairing()
    test_date_window_pairing()
    test_multi_currency_warning()
    test_amount_normalization()
    test_unknown_type_defaults_to_debit()
    test_empty_input()

    print("\n" + "=" * 70)
    if FAIL == 0:
        print("✅ ALL TESTS PASSED")
        return 0
    print(f"❌ {FAIL} ASSERTION(S) FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
