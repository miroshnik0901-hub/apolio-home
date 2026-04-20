"""
tests/t264_monobank_selftest.py — T-264 self-test

Reproduces the Monobank case that caused the bug:
    8 debit rows + 4 cancellation rows, NO preauth rows (Monobank pattern).

Before T-264:
    - fact_expense_rows = 8 (all debits)
    - matched_pairs = 0 (only cancel↔preauth was checked)
    - total_expenses = sum(all 8 debits) - sum(4 cancels) = 34,114 - 21,199 = 12,915
    - Output wrongly said "8 transactions added".

After T-264:
    - 4 cancellations match 4 debits (same amount, within 7d) → matched_pairs = 4
    - 4 debits remain → fact_expense_rows = 4
    - total_expenses = 12,915 (same, but now broken down correctly)
    - Output says "4 transactions added, 8 excluded due to returns" ✓

Run: python3 tests/t264_monobank_selftest.py
Expected: all assertions pass, exit 0.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.bank_statement import aggregate_bank_statement


def test_monobank_case():
    """Monobank Feb-Mar 2026 statement: 4 real purchases + 4 canceled preauth pairs."""
    # 8 debits: 4 real purchases (3018 + 4149 + 2387 + 3361 = 12,915)
    # + 4 canceled debits (5500 + 4200 + 6800 + 4699 = 21,199)
    # Total debit = 34,114
    # 4 cancellations matching the 4 canceled debits (same amount, next day).
    rows = [
        # Real purchases (no cancellation) — should remain as fact expenses
        {"date": "2026-02-15", "description": "WOG fuel", "amount": 3018, "currency": "UAH", "type": "debit"},
        {"date": "2026-02-20", "description": "OKKO fuel", "amount": 4149, "currency": "UAH", "type": "debit"},
        {"date": "2026-03-02", "description": "WOG fuel", "amount": 2387, "currency": "UAH", "type": "debit"},
        {"date": "2026-03-10", "description": "Shell fuel", "amount": 3361, "currency": "UAH", "type": "debit"},
        # Canceled attempts (debit + matching cancellation within 1-2 days)
        {"date": "2026-02-18", "description": "ATB hold", "amount": 5500, "currency": "UAH", "type": "debit"},
        {"date": "2026-02-19", "description": "ATB refund", "amount": 5500, "currency": "UAH", "type": "cancellation"},
        {"date": "2026-02-25", "description": "Silpo hold", "amount": 4200, "currency": "UAH", "type": "debit"},
        {"date": "2026-02-26", "description": "Silpo refund", "amount": 4200, "currency": "UAH", "type": "cancellation"},
        {"date": "2026-03-05", "description": "Novus hold", "amount": 6800, "currency": "UAH", "type": "debit"},
        {"date": "2026-03-06", "description": "Novus refund", "amount": 6800, "currency": "UAH", "type": "cancellation"},
        {"date": "2026-03-15", "description": "Fora hold", "amount": 4699, "currency": "UAH", "type": "debit"},
        {"date": "2026-03-16", "description": "Fora refund", "amount": 4699, "currency": "UAH", "type": "cancellation"},
    ]

    result = aggregate_bank_statement(rows)
    summary = result["summary"]

    # Counts
    assert result["total_rows"] == 12, f"total_rows: expected 12, got {result['total_rows']}"
    assert summary["preauth_count"] == 0, f"preauth_count: expected 0, got {summary['preauth_count']}"
    assert summary["cancellation_count"] == 4, f"cancellation_count: expected 4, got {summary['cancellation_count']}"
    assert summary["matched_pairs_count"] == 4, (
        f"matched_pairs_count: expected 4, got {summary['matched_pairs_count']} "
        f"(T-264 cancel↔debit pairing broken)"
    )
    assert summary["expense_count"] == 4, (
        f"expense_count: expected 4 real purchases, got {summary['expense_count']} "
        f"(T-264 should exclude canceled debits)"
    )
    assert summary["income_count"] == 0, f"income_count: expected 0, got {summary['income_count']}"

    # Sums
    assert summary["total_expenses"] == 12915.0, (
        f"total_expenses: expected 12915.0, got {summary['total_expenses']}"
    )
    assert summary["total_income"] == 0.0, f"total_income: expected 0.0, got {summary['total_income']}"
    assert summary["total_cancellations_amount"] == 21199.0, (
        f"total_cancellations_amount: expected 21199.0, got {summary['total_cancellations_amount']}"
    )

    # Unmatched must be empty
    assert result["unmatched_cancellation"] == [], (
        f"unmatched_cancellation: expected [], got {result['unmatched_cancellation']}"
    )
    assert result["unmatched_preauth"] == [], (
        f"unmatched_preauth: expected [], got {result['unmatched_preauth']}"
    )

    # fact_expense_rows must contain the 4 real purchases, not the canceled ones
    fact_amounts = sorted(r["amount"] for r in result["fact_expense_rows"])
    assert fact_amounts == [2387.0, 3018.0, 3361.0, 4149.0], (
        f"fact_expense_rows amounts: expected [2387, 3018, 3361, 4149], got {fact_amounts}"
    )

    print("✓ Monobank case PASS")
    print(f"  total_rows:          {result['total_rows']}")
    print(f"  matched_pairs:       {summary['matched_pairs_count']}")
    print(f"  expense_count:       {summary['expense_count']}")
    print(f"  cancellation_count:  {summary['cancellation_count']}")
    print(f"  total_expenses:      {summary['total_expenses']} {summary['currency']}")
    print(f"  total_cancellations: {summary['total_cancellations_amount']} {summary['currency']}")
    return result


def test_preauth_precedence_over_debit():
    """If both a preauth and a debit could pair with a cancellation, preauth wins (T-264 precedence)."""
    rows = [
        # Matching preauth for the cancellation (same amount, close date)
        {"date": "2026-03-01", "description": "Hold A", "amount": 1000, "currency": "UAH", "type": "preauth"},
        # Matching debit with same amount (further date)
        {"date": "2026-02-20", "description": "Real purchase A", "amount": 1000, "currency": "UAH", "type": "debit"},
        # Cancellation matches BOTH amounts, but preauth pairing should win
        {"date": "2026-03-02", "description": "Refund", "amount": 1000, "currency": "UAH", "type": "cancellation"},
    ]
    result = aggregate_bank_statement(rows)
    summary = result["summary"]

    # preauth↔cancel pass should match first → real debit remains as expense
    assert summary["matched_pairs_count"] == 1
    assert summary["expense_count"] == 1, (
        f"expected 1 real debit to remain as expense, got {summary['expense_count']}"
    )
    assert summary["total_expenses"] == 1000.0
    # The remaining debit is our "real purchase"
    assert result["fact_expense_rows"][0]["description"] == "Real purchase A"
    print("✓ preauth-precedence PASS")


def test_preauth_plus_debit_and_cancel():
    """Mixed case: one explicit preauth pair + one cancel↔debit pair. Both should match."""
    rows = [
        {"date": "2026-03-01", "description": "Hold", "amount": 500, "currency": "UAH", "type": "preauth"},
        {"date": "2026-03-02", "description": "Hold refund", "amount": 500, "currency": "UAH", "type": "cancellation"},
        {"date": "2026-03-10", "description": "Purchase attempt", "amount": 700, "currency": "UAH", "type": "debit"},
        {"date": "2026-03-11", "description": "Purchase refund", "amount": 700, "currency": "UAH", "type": "cancellation"},
        {"date": "2026-03-15", "description": "Real purchase", "amount": 999, "currency": "UAH", "type": "debit"},
    ]
    result = aggregate_bank_statement(rows)
    summary = result["summary"]
    assert summary["matched_pairs_count"] == 2
    assert summary["expense_count"] == 1
    assert summary["total_expenses"] == 999.0
    assert result["fact_expense_rows"][0]["description"] == "Real purchase"
    print("✓ preauth+debit-cancel mixed PASS")


def test_orphan_cancellation_still_treated_as_refund():
    """Cancellation with no matching preauth AND no matching debit → still goes to unmatched, reduces expenses."""
    rows = [
        {"date": "2026-03-01", "description": "Purchase", "amount": 1000, "currency": "UAH", "type": "debit"},
        # Orphan cancellation — no matching amount
        {"date": "2026-03-02", "description": "Random refund", "amount": 333, "currency": "UAH", "type": "cancellation"},
    ]
    result = aggregate_bank_statement(rows)
    summary = result["summary"]
    assert summary["matched_pairs_count"] == 0
    assert summary["expense_count"] == 1
    # Refund reduces expenses: 1000 - 333 = 667
    assert summary["total_expenses"] == 667.0
    assert len(result["unmatched_cancellation"]) == 1
    assert any("cancellation" in w for w in result["warnings"])
    print("✓ orphan-cancel refund PASS")


if __name__ == "__main__":
    print("=== T-264 self-test (Monobank cancel↔debit pairing) ===")
    test_monobank_case()
    test_preauth_precedence_over_debit()
    test_preauth_plus_debit_and_cancel()
    test_orphan_cancellation_still_treated_as_refund()
    print("\n✅ ALL T-264 TESTS PASSED")
