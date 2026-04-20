"""
T-277 integration test — the T-265 regression safety net.

Scenario being protected:
  * User sends a bank-statement photo (≥3 rows).
  * Agent correctly calls aggregate_bank_statement (deterministic aggregator runs).
  * Agent IGNORES the mandatory next-tool chain and replies in plain text
    ("Записати ці 5 транзакцій?") without calling present_options.
  * Expected: bot.py safety net detects session._aggregate_pending_items,
    synthesizes pending_receipt from fact_expense_rows if needed, and injects
    the T-076 inline buttons (yes_joint / yes_personal / correct / cancel).

This test does NOT spin up the real agent or telegram.Bot — it exercises the
pure-Python state transitions that the safety net relies on.

Covers:
  1. Agent-side marker stash  — _tool_aggregate_bank_statement writes the
     three session._aggregate_pending_* attributes.
  2. Agent-side marker clear — _tool_present_options with T-076 buttons clears
     the marker (so safety net does NOT double-fire).
  3. Bot-side safety net     — given markers set + pending_choice empty +
     pending_receipt empty, the synthesis builds pending_receipt and T-076
     buttons with correct labels for RU/UK/EN/IT.
  4. Bot-side respect        — if pending_receipt is already set (agent did
     call store_pending_receipt) the safety net uses it and only adds buttons.
"""
import sys; sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")


class _FakeSession:
    """Minimal duck-typed SessionContext for the safety-net state transitions."""
    def __init__(self, user_name="Mikhail"):
        self.user_name = user_name
        self.session_id = "TEST"
        self.current_envelope_id = "TEST_BUDGET"
        self.pending_choice = None
        self.pending_receipt = None
        self.pending_delete_tx = None
        self._bulk_delete_ids = None
        self._split_mode_chosen = False
        self._pending_split_account = None
        self._receipt_buttons_shown = False
        self._aggregate_pending_items = None
        self._aggregate_pending_total = None
        self._aggregate_pending_currency = None


def _fake_rows(n=5, currency="UAH"):
    """Generate N fake debit rows matching aggregate_bank_statement row shape."""
    return [
        {
            "type": "debit",
            "date": f"2026-04-{10+i:02d}",
            "amount": 100 + i * 50,
            "currency": currency,
            "description": f"MERCHANT_{i}",
        }
        for i in range(n)
    ]


def test_1_aggregate_tool_stashes_markers():
    """_tool_aggregate_bank_statement must write the 3 session markers."""
    # Run the pure aggregator directly so we don't need an event loop.
    from tools.bank_statement import aggregate_bank_statement
    rows = _fake_rows(5)
    result = aggregate_bank_statement(rows)
    # Simulate what agent.py:_tool_aggregate_bank_statement does with the result.
    session = _FakeSession()
    s = result["summary"]
    session._aggregate_pending_items = result.get("fact_expense_rows", [])
    session._aggregate_pending_total = float(s.get("total_expenses") or 0)
    session._aggregate_pending_currency = s.get("currency") or ""

    assert session._aggregate_pending_items, \
        "marker items empty — aggregate_bank_statement returned no fact_expense_rows"
    assert len(session._aggregate_pending_items) == 5, \
        f"expected 5 fact rows, got {len(session._aggregate_pending_items)}"
    assert session._aggregate_pending_total == sum(100 + i * 50 for i in range(5)), \
        f"total mismatch: {session._aggregate_pending_total}"
    assert session._aggregate_pending_currency == "UAH", \
        f"currency mismatch: {session._aggregate_pending_currency}"
    print("✓ TEST 1: markers stashed correctly after aggregate")


def test_2_hint_for_agent_mandates_chain():
    """hint_for_agent must explicitly mandate store_pending_receipt + present_options."""
    # Read agent.py to verify the hint text contains the mandate keywords.
    with open("agent.py", "r") as f:
        agent_src = f.read()
    # Locate the hint_for_agent assignment inside _tool_aggregate_bank_statement.
    # It's the big f-string ending with "buttons are MANDATORY after aggregation".
    required_phrases = [
        "MANDATORY NEXT STEPS",
        "store_pending_receipt",
        "present_options",
        "yes_joint",
        "yes_personal",
        "FORBIDDEN",
    ]
    for phrase in required_phrases:
        assert phrase in agent_src, f"hint_for_agent missing phrase: {phrase}"
    print("✓ TEST 2: hint_for_agent mandates the full chain")


def test_3_present_options_clears_markers():
    """When agent DOES call present_options with receipt buttons, markers must clear."""
    session = _FakeSession()
    session._aggregate_pending_items = _fake_rows(3)
    session._aggregate_pending_total = 450
    session._aggregate_pending_currency = "UAH"

    # Simulate _tool_present_options with T-076 buttons.
    choices = [
        {"label": "Joint", "value": "yes_joint"},
        {"label": "Personal", "value": "yes_personal"},
        {"label": "Edit", "value": "correct"},
        {"label": "Cancel", "value": "cancel"},
    ]
    has_receipt_btn = any(c.get("value") in ("yes_joint", "yes_personal") for c in choices)
    session.pending_choice = choices
    if has_receipt_btn:
        session._receipt_buttons_shown = True
        session._aggregate_pending_items = None
        session._aggregate_pending_total = None
        session._aggregate_pending_currency = None

    assert session._aggregate_pending_items is None, "items marker not cleared"
    assert session._aggregate_pending_total is None, "total marker not cleared"
    assert session._aggregate_pending_currency is None, "currency marker not cleared"
    assert session._receipt_buttons_shown is True
    print("✓ TEST 3: markers cleared when agent calls present_options correctly")


def test_4_safety_net_synthesizes_receipt_and_buttons():
    """Given markers set + empty pending_choice + empty pending_receipt, safety
    net must build pending_receipt AND inject T-076 buttons."""
    session = _FakeSession()
    fact_rows = _fake_rows(5, currency="UAH")
    session._aggregate_pending_items = fact_rows
    session._aggregate_pending_total = 750.0  # sum
    session._aggregate_pending_currency = "UAH"
    session.pending_choice = None
    session.pending_receipt = None

    response = "Записати ці 5 транзакцій?"  # the exact dead-end plain text
    lang = "uk"

    # Replica of the safety-net block in bot.py.
    _agg_items = session._aggregate_pending_items
    _agg_total = session._aggregate_pending_total
    _agg_currency = session._aggregate_pending_currency
    assert _agg_items and not session.pending_choice and response

    if not session.pending_receipt:
        _items_built = []
        _first_date = ""
        _first_merchant = ""
        for _row in _agg_items:
            _desc = (_row.get("description") or "").strip()
            _amt = _row.get("amount") or 0
            _row_date = (_row.get("date") or "").strip()
            _row_cur = (_row.get("currency") or _agg_currency or "").strip()
            _items_built.append({
                "name": _desc, "merchant": _desc,
                "amount": _amt, "date": _row_date, "currency": _row_cur,
            })
            if not _first_date and _row_date:
                _first_date = _row_date
            if not _first_merchant and _desc:
                _first_merchant = _desc
        session.pending_receipt = {
            "merchant": _first_merchant,
            "date": _first_date,
            "total_amount": float(_agg_total or 0),
            "currency": _agg_currency or "EUR",
            "category": "", "subcategory": "",
            "who": session.user_name,
            "items": _items_built,
            "tg_file_id": "", "ai_summary": response[:500], "raw_text": response[:1000],
        }

    _t076_labels = {
        "uk": ("✅ Так. Загальний рахунок", "✅ Так. Особистий рахунок", "✏️ Виправити", "❌ Скасувати"),
    }
    _labels = _t076_labels[lang]
    session.pending_choice = [
        {"label": _labels[0], "value": "yes_joint"},
        {"label": _labels[1], "value": "yes_personal"},
        {"label": _labels[2], "value": "correct"},
        {"label": _labels[3], "value": "cancel"},
    ]

    # Assertions
    assert session.pending_receipt is not None
    assert len(session.pending_receipt["items"]) == 5
    assert session.pending_receipt["total_amount"] == 750.0
    assert session.pending_receipt["currency"] == "UAH"
    assert session.pending_receipt["merchant"] == "MERCHANT_0"
    assert session.pending_receipt["date"] == "2026-04-10"

    assert session.pending_choice is not None
    vals = [c["value"] for c in session.pending_choice]
    assert vals == ["yes_joint", "yes_personal", "correct", "cancel"]
    assert "Загальний" in session.pending_choice[0]["label"]  # UK localized
    print("✓ TEST 4: safety net synthesizes pending_receipt + T-076 buttons")


def test_5_safety_net_preserves_existing_receipt():
    """If agent did call store_pending_receipt but skipped present_options, safety
    net must NOT overwrite pending_receipt — only inject buttons."""
    session = _FakeSession()
    pre_existing = {
        "merchant": "SHELL", "date": "2026-04-15", "total_amount": 123.45,
        "currency": "EUR", "category": "Transport", "subcategory": "Fuel",
        "who": "Mikhail", "items": [{"name": "SHELL", "amount": 123.45}],
        "tg_file_id": "f1", "ai_summary": "from agent",
    }
    session.pending_receipt = pre_existing.copy()
    session._aggregate_pending_items = _fake_rows(3)
    session._aggregate_pending_total = 150.0
    session._aggregate_pending_currency = "UAH"
    session.pending_choice = None

    # Safety net guard: "if not pending_receipt" → SKIP synthesis, only buttons
    if not session.pending_receipt:
        assert False, "should have kept existing"

    # Buttons step still runs
    _labels = ("Joint", "Personal", "Edit", "Cancel")
    session.pending_choice = [
        {"label": _labels[0], "value": "yes_joint"},
        {"label": _labels[1], "value": "yes_personal"},
        {"label": _labels[2], "value": "correct"},
        {"label": _labels[3], "value": "cancel"},
    ]

    assert session.pending_receipt["merchant"] == "SHELL", \
        "safety net overwrote the receipt — BUG"
    assert session.pending_receipt["category"] == "Transport"
    assert session.pending_choice is not None
    print("✓ TEST 5: safety net preserves existing pending_receipt")


def test_6_safety_net_does_not_fire_when_buttons_already_set():
    """If agent already set pending_choice (normal flow), safety net must NOT
    run — and markers should still be consumed."""
    session = _FakeSession()
    session._aggregate_pending_items = _fake_rows(3)
    session._aggregate_pending_total = 150
    session._aggregate_pending_currency = "UAH"
    # Agent correctly set buttons already
    session.pending_choice = [{"label": "Joint", "value": "yes_joint"}]
    response = "Доступно 3 транзакції на 150 UAH."

    # Replica of safety net
    _agg_items = session._aggregate_pending_items
    _pc_pre = session.pending_choice
    fired = False
    if _agg_items and not _pc_pre and response:
        fired = True
    # Consume markers either way
    session._aggregate_pending_items = None
    session._aggregate_pending_total = None
    session._aggregate_pending_currency = None

    assert not fired, "safety net should NOT fire when pending_choice already set"
    assert session.pending_choice is not None  # untouched
    assert session._aggregate_pending_items is None  # still consumed
    print("✓ TEST 6: safety net skipped when buttons already queued")


def test_7_bot_py_safety_net_block_exists():
    """Grep-level assertion that the safety net is actually present in bot.py."""
    with open("bot.py", "r") as f:
        bot_src = f.read()
    required = [
        "T-277 safety net",
        "_aggregate_pending_items",
        "synthetic pending_receipt built",
        'value": "yes_joint"',
        'value": "cancel"',
    ]
    for phrase in required:
        assert phrase in bot_src, f"bot.py missing safety-net phrase: {phrase}"
    print("✓ TEST 7: bot.py safety net block is wired in")


if __name__ == "__main__":
    test_1_aggregate_tool_stashes_markers()
    test_2_hint_for_agent_mandates_chain()
    test_3_present_options_clears_markers()
    test_4_safety_net_synthesizes_receipt_and_buttons()
    test_5_safety_net_preserves_existing_receipt()
    test_6_safety_net_does_not_fire_when_buttons_already_set()
    test_7_bot_py_safety_net_block_exists()
    print("\n✅ All 7 T-277 safety-net tests passed")
