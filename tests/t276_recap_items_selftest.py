"""
T-276 integration test — per-item list restored alongside T-254 compact recap.

Scenario being protected:
  * User confirms bank statement with 6 items via cb_split_separate.
  * 2 items go straight to Sheets (phase-1 successes) → appended to `added`.
  * 4 items match existing records (cross-currency dups) → queued for prompts.
  * User clicks: add_new (x2), update (x1), cancel (x1).
  * Before T-276: final message = only compact "📊 Added N, Updated M ..." line.
  * After  T-276: final message = per-item list (✓ / ↻ / ✗ lines) + compact tally.

This test simulates the session state transitions the drain relies on —
no telegram.Bot, no real Sheets calls. It exercises the pure state machine.

Covers:
  1. Phase-1 successes copied into `_batch_recap_items` when queue armed.
  2. cb_dup_cancel appends "✗" line with merchant/amount/currency.
  3. cb_dup_add_new appends "✓" line on success.
  4. cb_dup_update appends "↻" line on success.
  5. Drain renders items list ABOVE compact tally (standard-scheme order).
  6. Empty queue → compact tally only (backward compat).
  7. bot.py drain block actually contains the T-276 wiring.
"""
import sys; sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")


class _FakeSession:
    def __init__(self):
        self._batch_recap_enabled = False
        self._batch_recap_sent = True
        self._batch_recap_added = 0
        self._batch_recap_updated = 0
        self._batch_recap_cancelled = 0
        self._batch_recap_total = 0
        self._batch_recap_items = []
        self._pending_cross_dups = []


def _arm(session, phase1_added_lines, total_items, pending_dups_count):
    """Replicate bot.py arming block (after the batch loop)."""
    if pending_dups_count > 0:
        session._batch_recap_enabled = True
        session._batch_recap_added = len(phase1_added_lines)
        session._batch_recap_updated = 0
        session._batch_recap_cancelled = 0
        session._batch_recap_total = total_items
        session._batch_recap_sent = False
        session._batch_recap_items = list(phase1_added_lines)  # T-276
    else:
        session._batch_recap_enabled = False
        session._batch_recap_sent = True
        session._batch_recap_items = []


def _handle_dup(session, action, receipt, dup_add_params, ok=True):
    """Replicate the per-dup recap bookkeeping inside cb_choice_ dup handlers."""
    # cancel branch
    if action == "cancel":
        if session._batch_recap_enabled:
            session._batch_recap_cancelled += 1
            try:
                _amt = float((dup_add_params or {}).get("amount") or 0)
            except (TypeError, ValueError):
                _amt = 0.0
            _cur = (dup_add_params or {}).get("currency", "") or (receipt or {}).get("currency", "")
            _note = (receipt or {}).get("merchant", "") or (dup_add_params or {}).get("note", "") or "?"
            session._batch_recap_items.append(f"✗ {_note} · {_amt:,.2f} {_cur}".rstrip())
        return

    # update / add_new — only bump on success
    if ok and session._batch_recap_enabled:
        if action == "update":
            session._batch_recap_updated += 1
        elif action == "add_new":
            session._batch_recap_added += 1
        try:
            _amt = float((dup_add_params or {}).get("amount") or 0)
        except (TypeError, ValueError):
            _amt = 0.0
        _cur = (dup_add_params or {}).get("currency", "") or (receipt or {}).get("currency", "")
        _note = (receipt or {}).get("merchant", "") or (dup_add_params or {}).get("note", "") or "?"
        _mark = "↻" if action == "update" else "✓"
        session._batch_recap_items.append(f"{_mark} {_note} · {_amt:,.2f} {_cur}".rstrip())


def _render_drain(session, lang="uk"):
    """Replicate the drain-path recap render at bot.py:3664+."""
    import i18n
    _ra = session._batch_recap_added
    _ru = session._batch_recap_updated
    _rc = session._batch_recap_cancelled
    _rt = session._batch_recap_total
    _items = list(session._batch_recap_items or [])
    header = (
        i18n.ts("batch_recap_header", lang) + "\n" +
        i18n.ts("batch_recap_line", lang).format(
            added=_ra, updated=_ru, cancelled=_rc, total=_rt,
        )
    )
    if _items:
        return "\n".join(_items) + "\n\n" + header
    return header


def test_1_phase1_seed_on_arm():
    session = _FakeSession()
    phase1 = ["✓ SHELL · 72.50 EUR", "✓ METRO · 45.00 EUR"]
    _arm(session, phase1, total_items=6, pending_dups_count=4)
    assert session._batch_recap_enabled is True
    assert session._batch_recap_items == phase1
    assert session._batch_recap_added == 2
    assert session._batch_recap_total == 6
    print("✓ TEST 1: phase-1 successes seeded into recap items")


def test_2_cancel_appends_line():
    session = _FakeSession()
    _arm(session, [], total_items=3, pending_dups_count=3)
    receipt = {"merchant": "TAXI", "currency": "UAH"}
    add_params = {"amount": 50, "currency": "UAH", "note": "TAXI"}
    _handle_dup(session, "cancel", receipt, add_params)
    assert session._batch_recap_cancelled == 1
    assert session._batch_recap_items == ["✗ TAXI · 50.00 UAH"]
    print("✓ TEST 2: cancel appends ✗ line")


def test_3_add_new_appends_success_line():
    session = _FakeSession()
    _arm(session, [], total_items=3, pending_dups_count=3)
    receipt = {"merchant": "ATM", "currency": "UAH"}
    add_params = {"amount": 100, "currency": "UAH", "note": "ATM"}
    _handle_dup(session, "add_new", receipt, add_params, ok=True)
    assert session._batch_recap_added == 1
    assert session._batch_recap_items == ["✓ ATM · 100.00 UAH"]
    print("✓ TEST 3: add_new success appends ✓ line")


def test_4_update_appends_enrich_line():
    session = _FakeSession()
    _arm(session, [], total_items=3, pending_dups_count=3)
    receipt = {"merchant": "GROCERY", "currency": "EUR"}
    add_params = {"amount": 23.45, "currency": "EUR", "note": "GROCERY"}
    _handle_dup(session, "update", receipt, add_params, ok=True)
    assert session._batch_recap_updated == 1
    assert session._batch_recap_items == ["↻ GROCERY · 23.45 EUR"]
    print("✓ TEST 4: update success appends ↻ line")


def test_5_drain_puts_items_above_tally():
    session = _FakeSession()
    _arm(session, ["✓ SHELL · 72.50 EUR", "✓ METRO · 45.00 EUR"],
         total_items=6, pending_dups_count=4)
    # 4 dup resolutions: 2 add_new, 1 update, 1 cancel
    _handle_dup(session, "add_new", {"merchant": "ATM"},
                {"amount": 100, "currency": "UAH"}, ok=True)
    _handle_dup(session, "add_new", {"merchant": "CAFE"},
                {"amount": 30, "currency": "EUR"}, ok=True)
    _handle_dup(session, "update", {"merchant": "GROCERY"},
                {"amount": 23.45, "currency": "EUR"}, ok=True)
    _handle_dup(session, "cancel", {"merchant": "TAXI"},
                {"amount": 50, "currency": "UAH"})

    text = _render_drain(session, lang="uk")
    # Phase-1 lines present
    assert "✓ SHELL · 72.50 EUR" in text
    assert "✓ METRO · 45.00 EUR" in text
    # Drain lines present
    assert "✓ ATM · 100.00 UAH" in text
    assert "↻ GROCERY · 23.45 EUR" in text
    assert "✗ TAXI · 50.00 UAH" in text
    # Compact tally still present (batch_recap_header + line)
    assert "4" in text or "Added: 4" in text or "Додано: 4" in text or "📊" in text
    # Items come BEFORE the header block — check ordering
    idx_shell = text.find("✓ SHELL")
    idx_header = text.find("📊")
    assert idx_shell >= 0 and idx_header > idx_shell, \
        f"items list must precede compact header. shell={idx_shell} header={idx_header}"
    # Counts
    assert session._batch_recap_added == 4        # 2 phase-1 + 2 add_new
    assert session._batch_recap_updated == 1
    assert session._batch_recap_cancelled == 1
    assert session._batch_recap_total == 6
    print("✓ TEST 5: drain emits list above compact tally, all counters correct")


def test_6_empty_queue_keeps_compact_only():
    """Backward compat: when no dup queue was armed, drain has no items → no list
    prefix, just the compact header (but typically this path isn't reached because
    _batch_recap_enabled=False → whole drain block is skipped). Still, _render_drain
    must not crash on an empty items list."""
    session = _FakeSession()
    _arm(session, [], total_items=0, pending_dups_count=0)
    # Force-enable to test rendering path
    session._batch_recap_enabled = True
    session._batch_recap_sent = False
    text = _render_drain(session, lang="uk")
    # No item lines → text starts with the header glyph
    assert not text.startswith("✓") and not text.startswith("↻") and not text.startswith("✗"), \
        f"empty-items path produced item-lead output: {text[:80]}"
    print("✓ TEST 6: empty recap items yields compact-only rendering")


def test_7_bot_py_wiring_present():
    """Grep assertion — T-276 blocks must be wired in bot.py."""
    with open("bot.py", "r") as f:
        src = f.read()
    required = [
        "T-276: accumulate per-item lines",
        "session._batch_recap_items = list(added)",
        "T-276: append per-item line so final recap",
        "T-276: append per-item line — update",
        "T-276: restore per-item list",
        '"\\n".join(_items_acc) + "\\n\\n" + _recap_header',
    ]
    for phrase in required:
        assert phrase in src, f"bot.py missing T-276 wiring phrase: {phrase!r}"
    print("✓ TEST 7: bot.py has all T-276 wiring")


if __name__ == "__main__":
    test_1_phase1_seed_on_arm()
    test_2_cancel_appends_line()
    test_3_add_new_appends_success_line()
    test_4_update_appends_enrich_line()
    test_5_drain_puts_items_above_tally()
    test_6_empty_queue_keeps_compact_only()
    test_7_bot_py_wiring_present()
    print("\n✅ All 7 T-276 recap-items tests passed")
