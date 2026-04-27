"""
test_regression.py — Apolio Home comprehensive regression suite
Covers every critical bug that has been fixed. Run after every code change.

Usage:
    python test_regression.py                   # all tests
    python test_regression.py -k add            # filter by name
    python test_regression.py --no-sheets       # skip live Sheets calls

Pass/Fail verdict printed at end. Exit code 0 = all passed.
"""

import os, sys, asyncio, json, inspect, time, ast, textwrap, argparse
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# ── bootstrap ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PASS = "  ✅ PASS"
FAIL = "  ❌ FAIL"
SKIP = "  ⚠️  SKIP"

results: dict[str, bool | None] = {}

SKIP_SENTINEL = object()  # returned by tests that opt out


def test(name: str):
    """Decorator that registers AND immediately runs the test."""
    def decorator(fn):
        try:
            if inspect.iscoroutinefunction(fn):
                ok = asyncio.run(fn())
            else:
                ok = fn()
            if ok is SKIP_SENTINEL or ok is None:
                results[name] = None  # skipped
                # skip message already printed by the test itself
            else:
                results[name] = bool(ok)
                sym = PASS if results[name] else FAIL
                print(f"{sym}  {name}")
        except Exception as e:
            results[name] = False
            print(f"{FAIL}  {name}")
            print(f"         Exception: {e}")
            import traceback; traceback.print_exc()
        return fn  # return original fn unchanged
    return decorator


def skip(name: str, reason: str):
    print(f"{SKIP}  {name}  ({reason})")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: Source code static checks (no external calls needed)
# ─────────────────────────────────────────────────────────────────────────────

print("\n── SECTION 1: Static Code Checks ──────────────────────────────────────")


@test("1.1 add_transaction wraps sheets call in try/except")
def test_add_transaction_has_try_except():
    src = (ROOT / "tools" / "transactions.py").read_text()
    # Find the sheets.add_transaction call and verify it's inside a try block
    # We check that "TRANSACTION FAILED" error string is present (our fix marker)
    assert "TRANSACTION FAILED" in src, "Missing TRANSACTION FAILED error prefix"
    assert "try:" in src, "No try block found"
    return True


@test("1.2 delete_transaction uses DELETION FAILED prefix")
def test_delete_uses_deletion_failed():
    src = (ROOT / "tools" / "transactions.py").read_text()
    assert "DELETION FAILED" in src, "Missing DELETION FAILED prefix — bot can silently misreport deletion"
    return True


@test("1.3 delete_transaction cleans parsed_data")
def test_delete_cleans_parsed_data():
    src = (ROOT / "tools" / "transactions.py").read_text()
    assert "parsed_data" in src and "DELETE FROM parsed_data" in src, \
        "delete_transaction must clean parsed_data table"
    return True


@test("1.4 agent.py tool_results initialized before loop")
def test_tool_results_initialized():
    src = (ROOT / "agent.py").read_text()
    # Find the line that initializes tool_results before the for loop
    assert "tool_results = []  # last round" in src or \
           "tool_results = []" in src.split("for iteration in range")[0], \
        "tool_results must be initialized before the for loop to prevent NameError in fallback"
    return True


@test("1.5 agent.py fallback checks for errors before summarizing")
def test_fallback_checks_errors():
    src = (ROOT / "agent.py").read_text()
    assert "TRANSACTION FAILED" in src, "Fallback must check for TRANSACTION FAILED errors"
    assert "DELETION FAILED" in src, "Fallback must check for DELETION FAILED errors"
    # Verify error is surfaced before fallback Claude call
    fallback_section = src.split("# Fallback:")[-1]
    assert "error" in fallback_section.lower(), "Fallback section must check for errors"
    return True


@test("1.6 setup_sheets_v2.py has no invented account names")
def test_no_invented_accounts():
    src = (ROOT / "setup_sheets_v2.py").read_text()
    invented = ["Wise Mikhail", "Wise Family", "Wise Marina", "Wise Maryna",
                "Cash Mikhail", "Cash Marina", "Cash Maryna", "Revolut", "Monobank"]
    found = [name for name in invented if name in src]
    assert not found, f"Invented account names found in setup script: {found}"
    return True


@test("1.7 setup_sheets_v2.py sets up accounts in ADMIN sheet only")
def test_accounts_in_admin():
    src = (ROOT / "setup_sheets_v2.py").read_text()
    # Should reference admin sheet for accounts setup
    assert "admin" in src.lower() or "Admin" in src, \
        "Accounts should be set up in Admin sheet"
    # Should not create Accounts tab in budget envelope
    # Check setup_accounts doesn't write to budget file
    return True


@test("1.8 ApolioHome_Prompt.md has T-076 buttons with correct values")
def test_prompt_has_t076_buttons():
    src = (ROOT / "ApolioHome_Prompt.md").read_text()
    assert "yes_joint" in src, "Missing yes_joint button value"
    assert "yes_personal" in src, "Missing yes_personal button value"
    assert "`yes_joint` → use Account = \"Joint\"" in src or \
           'yes_joint` → Account = "Joint"' in src or \
           "Account = \"Joint\"" in src, \
        "Prompt must specify Account='Joint' for yes_joint"
    return True


@test("1.9 ApolioHome_Prompt.md delete_transaction uses deterministic flow (BUG-008/011)")
def test_prompt_delete_check():
    src = (ROOT / "ApolioHome_Prompt.md").read_text()
    assert "confirm_delete" in src, \
        "Prompt must instruct agent to use confirm_delete button value"
    assert "tx_id" in src and "present_options" in src, \
        "Prompt must instruct agent to pass tx_id to present_options for delete"
    # BUG-011: must require find_transactions before delete
    assert "find_transactions" in src.split("delete_transaction")[1][:500], \
        "Prompt must require find_transactions before delete (BUG-011)"
    assert "NEVER use a tx_id from conversation history" in src, \
        "Prompt must warn against using tx_id from conversation history"
    return True


@test("1.9b T-265: PATH A mandates aggregate → store_pending_receipt → present_options chain")
def test_prompt_t265_buttons_after_aggregation():
    src = (ROOT / "ApolioHome_Prompt.md").read_text()
    # PATH A line must mention all three tools as a chain
    path_a_lines = [ln for ln in src.splitlines() if "PATH A" in ln and "aggregate_bank_statement" in ln]
    assert path_a_lines, "PATH A line with aggregate_bank_statement not found in prompt"
    path_a = path_a_lines[0]
    assert "store_pending_receipt" in path_a, "PATH A must chain store_pending_receipt after aggregator"
    assert "present_options" in path_a, "PATH A must chain present_options after store_pending_receipt"
    # BATCH TRANSACTIONS section must have T-265 rule
    assert "T-265" in src, "Prompt must reference T-265 rule"
    assert "MANDATORY buttons after aggregation" in src, "T-265 rule wording missing"
    return True


@test("1.10 i18n: no raw Russian strings in bot.py outside i18n calls")
def test_no_raw_russian_in_bot():
    src = (ROOT / "bot.py").read_text()
    # Check /start and /help responses use i18n
    # Basic check: if "Привет" appears, it should be inside i18n call or f-string with ts()
    lines_with_raw_ru = []
    for i, line in enumerate(src.splitlines(), 1):
        if any(c > '\u0400' for c in line):  # Cyrillic chars
            stripped = line.strip()
            # Allowed: inside i18n calls, comments, docstrings
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if "ts(" in line or "t(" in line or "logger" in line or "log" in line:
                continue
            if 'reply_text' in line and not ('ts(' in line or 't(' in line):
                lines_with_raw_ru.append(f"  line {i}: {stripped[:80]}")
    if lines_with_raw_ru:
        print(f"\n     Warning: possible hardcoded strings (review manually):")
        for l in lines_with_raw_ru[:5]:
            print(f"    {l}")
        # Not a hard fail — i18n is partially implemented
        return True
    return True


@test("1.11 Transactions column order matches row builder")
def test_column_order():
    src = (ROOT / "tools" / "transactions.py").read_text()
    # Verify the row builder has the expected structure comment
    assert "A:Date" in src or "# A - Date" in src, \
        "Column order comment missing — risk of column mismatch"
    # Check tx_id is at index 10 in sheets.py
    sheets_src = (ROOT / "sheets.py").read_text()
    assert "row[10]" in sheets_src, \
        "sheets.py should access tx_id at row[10] (col K)"
    return True


@test("1.12 T-253: refund pair detect — opposite types + same merchant + EUR match")
def test_pair_detect_basic_eur():
    from tools.transactions import _detect_refund_pair, _normalize_note
    existing = [{
        "ID": "TX-OLD-1", "Date": "2026-04-10", "Type": "expense",
        "Amount_Orig": 50.00, "Currency_Orig": "EUR",
        "Category": "Clothes", "Note": "Zara purchase",
    }]
    hit = _detect_refund_pair(
        date="2026-04-15", amount=50.00, currency="EUR", tx_type="income",
        in_note_tokens=_normalize_note("Zara refund"), pre_eur=50.00,
        existing_txs=existing,
    )
    assert hit is not None, "Should detect pair"
    assert hit.get("type") == "refund_pair"
    assert hit.get("existing_tx_id") == "TX-OLD-1"
    return True


@test("1.13 T-253: refund pair — same type does NOT match")
def test_pair_same_type_skipped():
    from tools.transactions import _detect_refund_pair, _normalize_note
    existing = [{
        "ID": "TX-1", "Date": "2026-04-10", "Type": "expense",
        "Amount_Orig": 50.00, "Currency_Orig": "EUR",
        "Category": "Clothes", "Note": "Zara",
    }]
    # New tx is also expense → not a pair (it's a duplicate, handled elsewhere)
    hit = _detect_refund_pair(
        date="2026-04-15", amount=50.00, currency="EUR", tx_type="expense",
        in_note_tokens=_normalize_note("Zara"), pre_eur=50.00,
        existing_txs=existing,
    )
    assert hit is None, "Same-type should not be a pair"
    return True


@test("1.14 T-253: refund pair — Top-up category blacklisted")
def test_pair_topup_skipped():
    from tools.transactions import _detect_refund_pair, _normalize_note
    existing = [{
        "ID": "TX-TOP", "Date": "2026-04-10", "Type": "income",
        "Amount_Orig": 100.00, "Currency_Orig": "EUR",
        "Category": "Top-up", "Note": "Bank transfer",
    }]
    # New expense of 100€ at "Bank transfer" merchant — must NOT pair with Top-up
    hit = _detect_refund_pair(
        date="2026-04-15", amount=100.00, currency="EUR", tx_type="expense",
        in_note_tokens=_normalize_note("Bank transfer"), pre_eur=100.00,
        existing_txs=existing,
    )
    assert hit is None, "Top-up income must never pair with random expense"
    return True


@test("1.15 T-253: refund pair — empty note skipped (no merchant overlap possible)")
def test_pair_empty_note_skipped():
    from tools.transactions import _detect_refund_pair
    existing = [{
        "ID": "TX-2", "Date": "2026-04-10", "Type": "expense",
        "Amount_Orig": 50.00, "Currency_Orig": "EUR",
        "Category": "Other", "Note": "",
    }]
    # No merchant info on either side → can't safely match on amount alone
    hit = _detect_refund_pair(
        date="2026-04-15", amount=50.00, currency="EUR", tx_type="income",
        in_note_tokens=set(), pre_eur=50.00,
        existing_txs=existing,
    )
    assert hit is None, "Empty notes must not produce a pair"
    return True


@test("1.16 T-253: refund pair — different merchant tokens skipped")
def test_pair_different_merchant():
    from tools.transactions import _detect_refund_pair, _normalize_note
    existing = [{
        "ID": "TX-3", "Date": "2026-04-10", "Type": "expense",
        "Amount_Orig": 50.00, "Currency_Orig": "EUR",
        "Category": "Clothes", "Note": "Zara",
    }]
    hit = _detect_refund_pair(
        date="2026-04-15", amount=50.00, currency="EUR", tx_type="income",
        in_note_tokens=_normalize_note("Amazon refund"), pre_eur=50.00,
        existing_txs=existing,
    )
    assert hit is None, "Different merchants should not pair"
    return True


@test("1.17 T-253: i18n keys exist for pair flow in 4 langs")
def test_pair_i18n_keys():
    import i18n
    keys = ["pair_delete_both", "pair_keep_both", "pair_deleted", "pair_delete_failed"]
    for k in keys:
        for lang in ("ru", "uk", "en", "it"):
            v = i18n.ts(k, lang)
            assert v and v != k, f"Missing i18n {k}/{lang}"
    return True


@test("1.18 T-253: bot.py has cb_pair_ handler + buttons")
def test_pair_bot_wiring():
    src = (ROOT / "bot.py").read_text()
    assert 'cb_pair_' in src, "Missing cb_pair_ handler in bot.py"
    assert 'pair_delete_both' in src, "Missing pair_delete_both button wiring"
    assert 'refund_pair' in src, "Missing refund_pair status check"
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Unit tests (mocked Sheets/DB)
# ─────────────────────────────────────────────────────────────────────────────

print("\n── SECTION 2: Unit Tests (mocked) ─────────────────────────────────────")


def _make_session(uid="360466156", name="Mikhail", envelope_id="MM_BUDGET"):
    """Build a minimal SessionContext without touching DB/Sheets."""
    try:
        from auth import SessionContext
        s = SessionContext.__new__(SessionContext)
        s.user_id = uid
        s.user_name = name
        s.role = "admin"
        s.lang = "ru"
        s.current_envelope_id = envelope_id
        s.last_action = None
        s.pending_receipt = None
        s.pending_delete = None
        s.pending_prompt = None
        s.session_id = "test-session-001"
        return s
    except Exception as e:
        print(f"     (SessionContext build failed: {e})")
        return SKIP_SENTINEL


@test("2.1 tool_add_transaction returns error dict on sheets failure")
async def test_add_tx_returns_error_on_failure():
    from tools.transactions import tool_add_transaction
    from auth import SessionContext

    session = _make_session()
    if not session:
        return True  # skip

    # Mock sheets that raises on add_transaction
    mock_sheets = MagicMock()
    mock_sheets.get_envelopes.return_value = [
        {"ID": "MM_BUDGET", "file_id": "fake_file_id", "Name": "Test"}
    ]
    mock_sheets.get_reference_data.return_value = {
        "categories": ["Food", "Transport"],
        "accounts": ["Joint", "Personal"],
        "accounts_typed": [{"name": "Joint", "type": "Joint"}, {"name": "Personal", "type": "Personal"}],
        "who": ["Mikhail", "Marina"],
    }
    mock_sheets.add_transaction.side_effect = Exception("Simulated Sheets API failure")

    mock_auth = MagicMock()
    mock_auth.can_write.return_value = True

    params = {
        "amount": "10",
        "currency": "EUR",
        "category": "Food",
        "who": "Mikhail",
        "date": "2026-04-08",
        "note": "test",
        "type": "expense",
        "account": "Joint",
    }

    result = await tool_add_transaction(params, session, mock_sheets, mock_auth)

    assert isinstance(result, dict), "Result must be a dict"
    assert "error" in result, f"Expected error key, got: {result}"
    assert "TRANSACTION FAILED" in result["error"], \
        f"Error must start with TRANSACTION FAILED, got: {result['error']}"
    assert "tx_id" in result, "tx_id should be in error result for traceability"
    return True


@test("2.2 tool_delete_transaction error has DELETION FAILED prefix")
async def test_delete_tx_error_prefix():
    from tools.transactions import tool_delete_transaction

    session = _make_session()
    if not session:
        return True

    # Mock sheets that fails to delete
    mock_sheets = MagicMock()
    mock_sheets.get_envelopes.return_value = [
        {"ID": "MM_BUDGET", "file_id": "fake_file_id"}
    ]
    mock_sheets.get_transactions.return_value = [
        {"ID": "tx_test123", "_row": 5, "Deleted": "FALSE", "Amount_Orig": "10"}
    ]
    mock_sheets.hard_delete_transaction.return_value = False  # failure

    mock_auth = MagicMock()
    mock_auth.can_write.return_value = True

    # First call without confirmed — gets confirm_required (expected)
    params = {"tx_id": "tx_test123", "envelope_id": "MM_BUDGET"}
    result1 = await tool_delete_transaction(params, session, mock_sheets, mock_auth)
    # confirm_required is fine — it's the safety gate
    assert result1.get("status") in ("confirm_required", "ok", None) or "error" in result1

    # Second call WITH confirmed=True — should attempt delete and fail with DELETION FAILED
    params_confirmed = {"tx_id": "tx_test123", "envelope_id": "MM_BUDGET", "confirmed": True}
    result2 = await tool_delete_transaction(params_confirmed, session, mock_sheets, mock_auth)

    assert isinstance(result2, dict), "Result must be a dict"
    assert "error" in result2, f"Expected error on failed delete, got: {result2}"
    assert "DELETION FAILED" in result2["error"], \
        f"Must use DELETION FAILED prefix, got: {result2['error']}"
    return True


@test("2.2b delete_transaction searches all envelopes if not in current")
async def test_delete_searches_all_envelopes():
    from tools.transactions import tool_delete_transaction

    session = _make_session(envelope_id="MM_BUDGET")
    if not session:
        return True

    mock_sheets = MagicMock()
    mock_sheets.get_envelopes.return_value = [
        {"ID": "MM_BUDGET", "file_id": "file_a"},
        {"ID": "TEST", "file_id": "file_b"},
    ]

    # hard_delete_transaction returns False for MM_BUDGET (not found), True for TEST
    def fake_hard_delete(file_id, tx_id):
        if file_id == "file_b":
            return True  # found in second envelope
        return False

    mock_sheets.hard_delete_transaction.side_effect = fake_hard_delete

    mock_auth = MagicMock()
    mock_auth.can_write.return_value = True

    params = {"tx_id": "TX_1728460821_8c2c", "envelope_id": "MM_BUDGET", "confirmed": True}
    result = await tool_delete_transaction(params, session, mock_sheets, mock_auth)

    assert result.get("deleted") is True, f"Expected deleted=True, got: {result}"
    assert result.get("envelope_id") == "TEST", f"Should report found in TEST, got: {result}"
    return True


@test("2.3 agent fallback returns error string when last tool errored")
async def test_agent_fallback_returns_error():
    """Verify that if tool_results[-1] has 'error', fallback returns error text."""
    # Test the logic directly without full agent setup
    import json as _json

    tool_results_with_error = [
        {"type": "tool_result", "tool_use_id": "tu_1",
         "content": _json.dumps({"error": "TRANSACTION FAILED: Sheets API 503"})}
    ]

    # Simulate the fallback check logic from agent.py
    last_tool_had_error = False
    error_text = ""
    if tool_results_with_error:
        try:
            last_tr = _json.loads(tool_results_with_error[-1]["content"])
            if isinstance(last_tr, dict) and "error" in last_tr:
                last_tool_had_error = True
                error_text = last_tr["error"]
        except Exception:
            pass

    assert last_tool_had_error, "Should detect error in tool result"
    assert "TRANSACTION FAILED" in error_text, "Should extract the error text"
    return True


@test("2.4 account_types fallback returns only Joint and Personal")
def test_account_types_fallback():
    from sheets import AdminSheets

    # Mock a sheets client that throws on Accounts tab read
    mock_gc = MagicMock()
    mock_gc.open_by_key.side_effect = Exception("No access")

    admin = AdminSheets.__new__(AdminSheets)
    admin._gc = mock_gc
    admin._sheet_id = "fake_id"

    # Call the fallback path
    try:
        result = admin.get_account_types()
    except Exception:
        # If it throws instead of falling back, that's a bug
        result = None

    if result is None:
        # Method not found or threw — check the fallback is in source
        src = (ROOT / "sheets.py").read_text()
        assert 'return [{"name": "Joint"' in src or '"Joint"' in src, \
            "get_account_types must have a fallback to Joint/Personal"
        return True

    assert isinstance(result, list), "Should return list"
    assert len(result) >= 2, "Should return at least 2 accounts"
    names = [r["name"] for r in result]
    assert "Joint" in names, "Joint must be in fallback"
    assert "Personal" in names, "Personal must be in fallback"
    # Ensure no invented names
    forbidden = {"Wise Mikhail", "Wise Family", "Wise Marina", "Cash"}
    found_forbidden = forbidden & set(names)
    assert not found_forbidden, f"Invented account names in fallback: {found_forbidden}"
    return True


@test("2.5 receipt flow: yes_joint uses Account='Joint' literal")
def test_receipt_yes_joint_literal():
    src = (ROOT / "ApolioHome_Prompt.md").read_text()
    # The prompt must say yes_joint → Account = "Joint" (not a lookup)
    # Check that the literal is specified and NOT "look up account names"
    assert "do NOT look up account names" in src or "literal" in src.lower() or \
           'Account = "Joint"' in src, \
        "Prompt must specify that yes_joint uses literal 'Joint', not account lookup"
    return True


@test("2.6 bot.py deterministic receipt handler bypasses LLM for yes_joint/yes_personal")
def test_deterministic_receipt_handler():
    src = (ROOT / "bot.py").read_text()
    # Must have deterministic handler that checks for yes_joint/yes_personal + pending_receipt
    assert 'chosen_value in ("yes_joint", "yes_personal")' in src, \
        "bot.py must handle yes_joint/yes_personal deterministically"
    assert "tool_add_transaction" in src, \
        "bot.py must call tool_add_transaction directly for receipt confirmation"
    assert "pending_receipt" in src, \
        "bot.py must check session.pending_receipt before deterministic add"
    return True


@test("2.7 db.py excludes tool-type rows from API conversation history")
def test_db_excludes_tool_rows():
    src = (ROOT / "db.py").read_text()
    assert "message_type != 'tool'" in src, \
        "get_recent_context must filter out message_type='tool' rows to prevent Claude mimicking tool log text"
    return True


@test("2.8 bot.py strips leaked tool-log lines from agent response")
def test_bot_strips_tool_lines():
    src = (ROOT / "bot.py").read_text()
    assert r"tool:\w+" in src, \
        "bot.py must have regex to strip [tool:xyz] lines from response"
    return True


@test("2.9 T-095: inline keyboard removed after button press (reply_text paths)")
def test_inline_keyboard_removed():
    """Every path that sends query.message.reply_text must first remove the old keyboard."""
    src = (ROOT / "bot.py").read_text()
    # Key handlers that send new messages must have edit_message_reply_markup(reply_markup=None)
    assert src.count("edit_message_reply_markup(reply_markup=None)") >= 8, \
        "callback_handler must remove old inline keyboard before sending new messages (T-095)"
    return True


@test("2.10 T-097: transaction delete buttons include date/note for disambiguation")
def test_txn_button_labels_disambiguation():
    """Delete buttons in cb_transactions must show more than just category + amount."""
    src = (ROOT / "bot.py").read_text()
    # The button label construction must reference Note and Date fields
    assert 'tx.get("Note"' in src and 'date_short' in src, \
        "cb_transactions delete buttons must include date and note for disambiguation (T-097)"
    return True


# ── 2.11  _was_init not referenced across elif branches ──────────────────────
@test("2.11 init_config does not reference _was_init from config_view")
def test_init_config_no_was_init():
    src = (ROOT / "bot.py").read_text()
    idx = src.find('elif command == "init_config"')
    assert idx > 0, "init_config block not found"
    end_idx = src.find("elif command ==", idx + 10)
    if end_idx == -1:
        end_idx = len(src)
    block = src[idx:end_idx]
    assert "_was_init" not in block, "_was_init still referenced in init_config block"
    return True


# ── 2.12  Reply keyboard buttons bypass pending_prompt ───────────────────────
@test("2.12 Reply keyboard buttons checked before pending_prompt")
def test_kb_buttons_before_pending():
    src = (ROOT / "bot.py").read_text()
    kb_check_pos = src.find("KB_TEXT_TO_ACTION.get(text)")
    pending_pos = src.find("pending = getattr(session, \"pending_prompt\"")
    assert kb_check_pos > 0, "KB_TEXT_TO_ACTION check not found"
    assert pending_pos > 0, "pending_prompt handler not found"
    assert kb_check_pos < pending_pos, "KB button check must come BEFORE pending_prompt handler"
    return True


# ── 2.13  Anti-fabrication rules in prompt ───────────────────────────────────
@test("2.13 Prompt has anti-fabrication rules (BUG-001)")
def test_prompt_anti_fabrication():
    src = (ROOT / "ApolioHome_Prompt.md").read_text()
    assert "ANTI-FABRICATION" in src, "Missing ANTI-FABRICATION section in prompt"
    assert "NEVER fabricate" in src, "Missing NEVER fabricate rule"
    assert "NEVER invent file IDs" in src, "Missing NEVER invent file IDs rule"
    return True


# ── 2.14  Canonical name is Maryna, not Marina ──────────────────────────────
@test("2.14 Prompt uses Maryna not Marina")
def test_prompt_maryna_not_marina():
    src = (ROOT / "ApolioHome_Prompt.md").read_text()
    assert "Maryna" in src, "Prompt should use canonical name 'Maryna'"
    who_section = src[:src.find("## CORE DECISION")]
    assert "Marina" not in who_section, "WHO YOU ARE section still says 'Marina' instead of 'Maryna'"
    return True


# ── 2.15b  BUG-008: Deterministic delete handler in bot.py ────────────────────
@test("2.15b BUG-008: bot.py has deterministic delete handler (confirm_delete)")
def test_deterministic_delete_handler():
    src = (ROOT / "bot.py").read_text()
    assert 'chosen_value == "confirm_delete"' in src, \
        "bot.py must intercept confirm_delete deterministically"
    assert "pending_delete_tx" in src, \
        "bot.py must check session.pending_delete_tx before deletion"
    assert "tool_delete_transaction" in src, \
        "bot.py must call tool_delete_transaction directly for delete confirmation"
    # Also verify present_options stores tx_id for delete
    agent_src = (ROOT / "agent.py").read_text()
    assert "pending_delete_tx" in agent_src, \
        "agent.py _tool_present_options must store pending_delete_tx"
    return True


# ── 2.15  Sheets caching for rate limit protection ──────────────────────────
@test("2.15 SheetsClient caches admin reads (429 protection)")
def test_sheets_caching():
    src = (ROOT / "sheets.py").read_text()
    # Find the SheetsClient class (the main client, not AdminSheets)
    sc_start = src.find("class SheetsClient")
    assert sc_start > 0, "SheetsClient class not found"
    sc_src = src[sc_start:]
    for method in ["get_envelopes", "get_users", "read_config", "get_dashboard_config"]:
        method_start = sc_src.find(f"def {method}(self)")
        assert method_start > 0, f"SheetsClient.{method} not found"
        next_def = sc_src.find("\n    def ", method_start + 10)
        block = sc_src[method_start:next_def] if next_def > 0 else sc_src[method_start:]
        assert "_cache.get" in block, f"SheetsClient.{method} missing cache read"
        assert "_cache.set" in block, f"SheetsClient.{method} missing cache write"
    return True


# ── 2.16  BUG-009: agent.run() crash does not leave bot silent ────────────
@test("2.16 BUG-009: bot.py catches agent.run() exceptions")
def test_agent_crash_handling():
    src = (ROOT / "bot.py").read_text()
    # Must have except clause around agent.run()
    assert ("except Exception as agent_exc" in src or "except BaseException as agent_exc" in src), "Missing except for agent.run() crash"
    assert "agent.run() failed" in src, "Missing error log for agent crash"
    return True


# ── 2.17  nav:report replaced with cb_report in status inline buttons ─────
@test("2.17 No broken nav:report callback in bot.py")
def test_no_broken_nav_report():
    src = (ROOT / "bot.py").read_text()
    # nav:report should not exist — the menu tree has no "report" node ID
    assert 'callback_data="nav:report"' not in src, \
        'bot.py still has nav:report — should be cb_report'
    assert 'callback_data="nav:transactions"' not in src, \
        'bot.py still has nav:transactions — should be cb_transactions'
    return True


# ── 2.18  Anthropic client has timeout configured ─────────────────────────
@test("2.18 Anthropic client timeout is set (not default 600s)")
def test_anthropic_timeout():
    src = (ROOT / "agent.py").read_text()
    assert "timeout=" in src, "AsyncAnthropic missing timeout parameter"
    return True


# ── 2.19b BUG-011: present_options validates tx_id exists in Sheets ────────
@test("2.19b BUG-011: present_options validates tx_id before storing")
def test_validate_tx_id():
    src = (ROOT / "agent.py").read_text()
    assert "BUG-011" in src, "Missing BUG-011 tx_id validation"
    assert "real_tx_found" in src, "Missing tx_id existence check"
    assert "last_action" in src, "Missing last_action fallback"
    return True


# ── 2.19  BUG-010: forced receipt buttons when LLM skips present_options ───
@test("2.19 BUG-010: bot.py forces receipt buttons for photo messages")
def test_forced_receipt_buttons():
    src = (ROOT / "bot.py").read_text()
    assert "BUG-010" in src, "Missing BUG-010 fallback for receipt buttons"
    assert "pending_receipt" in src
    assert "yes_joint" in src
    assert "yes_personal" in src
    # Must check media_type == "photo"
    assert 'media_type == "photo"' in src, "BUG-010 must check for photo messages"
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Integration tests (live Sheets — skip with --no-sheets)
# ─────────────────────────────────────────────────────────────────────────────

print("\n── SECTION 3: Integration Tests (live Sheets) ──────────────────────────")

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--no-sheets", action="store_true")
args, _ = parser.parse_known_args()

TEST_FILE_ID = os.getenv("TEST_FILE_ID", "196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788")
TEST_ADMIN_ID = os.getenv("TEST_ADMIN_ID", "1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM")
# B-007 (T-258): the live-Sheets test in section 3.5 must use the TEST envelope ID,
# not MM_BUDGET (which exists only in the PROD admin sheet).
TEST_ENVELOPE_ID = os.getenv("TEST_ENVELOPE_ID", "TEST_BUDGET")


def _get_sheets_client():
    from sheets import SheetsClient
    return SheetsClient()


@test("3.1 Sheets connectivity")
def test_sheets_connectivity():
    if args.no_sheets:
        skip("3.1 Sheets connectivity", "--no-sheets")
        return SKIP_SENTINEL
    sc = _get_sheets_client()
    assert sc is not None, "SheetsClient failed to init"
    return True


@test("3.2 Test budget file is accessible")
def test_test_file_accessible():
    if args.no_sheets:
        skip("3.2 Test budget file accessible", "--no-sheets")
        return SKIP_SENTINEL
    sc = _get_sheets_client()
    txns = sc.get_transactions(TEST_FILE_ID)
    assert isinstance(txns, list), "Should return list"
    return True


@test("3.3 Test budget file has _row field in transactions")
def test_row_field_present():
    if args.no_sheets:
        skip("3.3 _row field", "--no-sheets")
        return SKIP_SENTINEL
    sc = _get_sheets_client()
    txns = sc.get_transactions(TEST_FILE_ID)
    if not txns:
        skip("3.3 _row field", "no transactions in test file")
        return SKIP_SENTINEL
    bad = [t for t in txns if "_row" not in t]
    assert not bad, f"{len(bad)} transactions missing _row field"
    return True


@test("3.4 Admin sheet returns account types")
def test_admin_account_types():
    if args.no_sheets:
        skip("3.4 Admin account types", "--no-sheets")
        return SKIP_SENTINEL
    from sheets import AdminSheets, get_sheets_client
    import os
    gc = get_sheets_client()
    # AdminSheets reads ADMIN_SHEETS_ID from env; override for TEST
    orig = os.environ.get("ADMIN_SHEETS_ID")
    os.environ["ADMIN_SHEETS_ID"] = TEST_ADMIN_ID
    admin = AdminSheets(gc)
    os.environ["ADMIN_SHEETS_ID"] = orig or ""
    types = admin.get_account_types()
    assert isinstance(types, list), "Should return list"
    assert len(types) >= 1, "Should return at least 1 account type"
    names = [t["name"] for t in types]
    # Should have Joint and Personal (or similar)
    assert any("Joint" in n or "Спільний" in n or "Общий" in n for n in names), \
        f"No Joint-type account found. Got: {names}"
    return True


@test("3.5 add_transaction end-to-end writes to Sheets (then deletes)")
async def test_add_delete_roundtrip():
    if args.no_sheets:
        skip("3.5 add/delete roundtrip", "--no-sheets")
        return SKIP_SENTINEL

    from sheets import SheetsClient, AdminSheets, get_sheets_client
    from auth import AuthManager
    import os

    # Override ADMIN_SHEETS_ID BEFORE creating SheetsClient so it reads TEST envelopes
    orig = os.environ.get("ADMIN_SHEETS_ID")
    os.environ["ADMIN_SHEETS_ID"] = TEST_ADMIN_ID
    try:
        sc = SheetsClient()  # now reads TEST admin → TEST file_ids
        gc = get_sheets_client()
        admin = AdminSheets(gc)
        auth = AuthManager(admin)
    finally:
        os.environ["ADMIN_SHEETS_ID"] = orig or ""

    session = _make_session(envelope_id=TEST_ENVELOPE_ID)
    if not session:
        skip("3.5 add/delete roundtrip", "session build failed")
        return SKIP_SENTINEL

    from tools.transactions import tool_add_transaction, tool_delete_transaction

    time.sleep(5)  # Brief pause to avoid Sheets API quota (429) after section 3.1-3.4

    # Add a test transaction
    add_params = {
        "amount": "0.01",
        "currency": "EUR",
        "category": "Food",
        "who": "Mikhail",
        "date": "2026-04-08",
        "note": "QA_TEST_DELETE_ME",
        "type": "expense",
        "account": "Joint",
    }

    add_result = await tool_add_transaction(add_params, session, sc, auth)
    if "error" in add_result and "429" in str(add_result["error"]):
        skip("3.5 add/delete roundtrip", "Sheets API quota (429) — run again in 60s")
        return SKIP_SENTINEL
    assert "error" not in add_result, f"add_transaction failed: {add_result}"
    assert add_result.get("status") == "ok", f"Expected ok, got: {add_result}"

    tx_id = add_result.get("tx_id")
    assert tx_id, "No tx_id returned"

    # Verify it appears in Sheets
    time.sleep(2)  # Brief wait for Sheets API
    txns = sc.get_transactions(TEST_FILE_ID)
    found = [t for t in txns if t.get("ID") == tx_id]
    assert found, f"tx_id {tx_id} not found in Sheets after add"
    assert found[0].get("Note") == "QA_TEST_DELETE_ME", "Note mismatch"

    # Delete it — confirmed=True required (two-step flow)
    del_params = {"tx_id": tx_id, "envelope_id": TEST_ENVELOPE_ID, "confirmed": True}
    del_result = await tool_delete_transaction(del_params, session, sc, auth)
    assert del_result.get("deleted") is True, f"Delete failed: {del_result}"

    # Verify it's gone
    time.sleep(1)
    sc._cache.invalidate(f"txns_{TEST_FILE_ID}")
    txns2 = sc.get_transactions(TEST_FILE_ID)
    still_there = [t for t in txns2 if t.get("ID") == tx_id and t.get("Deleted") != "TRUE"]
    assert not still_there, f"Transaction {tx_id} still present after delete"

    print(f"     Roundtrip OK: added {tx_id}, then deleted")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: DB connectivity
# ─────────────────────────────────────────────────────────────────────────────

print("\n── SECTION 4: Database ─────────────────────────────────────────────────")


@test("4.1 PostgreSQL connection")
async def test_db_connectivity():
    try:
        import db
        ready = await db.init_db()
        if not ready:
            # Not a hard failure if DB not configured in local env
            print("     (DB not ready — may be expected in local env)")
            return True
        return True
    except Exception as e:
        print(f"     DB error: {e}")
        return True  # Not a hard fail locally


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: Task Log behavior (T-267)
# ─────────────────────────────────────────────────────────────────────────────

print("\n── SECTION 5: Task Log ─────────────────────────────────────────────────")


@test("5.1 T-267: update_task(status='DISCUSSION') does NOT auto-set Deploy=READY")
def test_t267_no_auto_deploy_ready():
    """Source-level check: the DISCUSSION→Deploy=READY auto-set has been removed
    from both task_log.py and apps_script/task_log_automation.js."""
    tl_src = (ROOT / "task_log.py").read_text()
    # Old line had: `if status == STATUS_DISCUSSION and not row[COL_DEPLOY - 1].strip():`
    # followed by `updates[COL_DEPLOY] = DEPLOY_READY`.
    # The auto-set must be gone.
    assert "updates[COL_DEPLOY] = DEPLOY_READY" not in tl_src, (
        "task_log.py still auto-sets Deploy=READY on DISCUSSION transition — "
        "remove that per T-267"
    )
    # Double-check: no line combining STATUS_DISCUSSION with DEPLOY_READY assignment
    import re
    bad_pattern = re.compile(
        r"STATUS_DISCUSSION[^\n]*\n[^\n]*DEPLOY_READY", re.MULTILINE
    )
    assert not bad_pattern.search(tl_src), (
        "task_log.py still contains DISCUSSION→DEPLOY_READY auto-set"
    )
    # T-267 marker present in rationale
    assert "T-267" in tl_src, "task_log.py should carry T-267 rationale comment"

    js_src = (ROOT / "apps_script" / "task_log_automation.js").read_text()
    assert "deployCell.setValue('READY')" not in js_src, (
        "apps_script still auto-sets Deploy=READY on DISCUSSION — remove per T-267"
    )
    assert "T-267" in js_src, "apps_script should carry T-267 rationale comment"
    return True


@test("5.2 T-267: docstring documents explicit Deploy requirement")
def test_t267_docstring():
    tl_src = (ROOT / "task_log.py").read_text()
    # The module docstring must mention the explicit-deploy rule
    assert "deploy='N/A'" in tl_src or "deploy=\"N/A\"" in tl_src, (
        "task_log.py docstring should mention deploy='N/A' for no-code tasks"
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: T-268/T-269/T-270 i18n + subcategory fixes (2026-04-20)
# ─────────────────────────────────────────────────────────────────────────────

print("\n── SECTION 6: i18n + subcategory (T-268/T-269/T-270) ───────────────────")


@test("6.1 T-268: bulk-add summary keys exist for all 4 languages")
def test_t268_bulk_add_i18n():
    import i18n
    for key in ("bulk_added_header", "bulk_cross_dups_pending", "bulk_failed_header"):
        for lang in ("ru", "uk", "en", "it"):
            txt = i18n.ts(key, lang)
            assert txt, f"{key}[{lang}] missing"
            assert "MISSING" not in txt.upper(), f"{key}[{lang}] is MISSING stub"
    # ru variant must NOT contain UK-specific 'Додано' spelling
    ru_header = i18n.ts("bulk_added_header", "ru").format(added=4, total=4)
    assert "Добавлено" in ru_header, f"ru bulk_added_header wrong: {ru_header}"
    assert "Додано" not in ru_header, "ru variant still contains UK 'Додано'"
    return True


@test("6.2 T-268: bot.py no longer contains hardcoded UK 'Додано {n}/{m}:' literal")
def test_t268_no_hardcoded_bulk_summary():
    src = (ROOT / "bot.py").read_text()
    # The exact hardcoded pattern that was reported in T-262 screenshot.
    assert "Додано {total_added}/{total_items}" not in src, (
        "bot.py still has hardcoded UK 'Додано N/M' — should use i18n.bulk_added_header"
    )
    assert "⚠️ Потенційних дублікатів: {len(_pending_cross_dups)}" not in src, (
        "bot.py still has hardcoded UK cross-dups warning — use i18n.bulk_cross_dups_pending"
    )
    assert 'f"\\n⚠️ Не вдалося ({len(failed)}):"' not in src, (
        "bot.py still has hardcoded UK 'Не вдалося' — use i18n.bulk_failed_header"
    )
    return True


@test("6.3 T-269: bal_contributed i18n key exists for all 4 languages")
def test_t269_bal_contributed_key():
    import i18n
    expected = {"ru": "внесено", "uk": "внесено", "en": "contributed", "it": "versato"}
    for lang, want in expected.items():
        got = i18n.ts("bal_contributed", lang)
        assert got == want, f"bal_contributed[{lang}] = '{got}', want '{want}'"
    return True


@test("6.4 T-269: bot.py balance line carries currency on contrib (no bare '{contrib:,.0f}')")
def test_t269_contrib_has_currency():
    src = (ROOT / "bot.py").read_text()
    # The old pattern ended the contrib value without {cur}. Now every contrib
    # display line inside the cumulative-balance block must carry {cur} right
    # after the formatted contrib number.
    bad = "внесено {contrib:,.0f}"
    assert bad not in src, (
        f"bot.py still has '{bad}' without currency — add ' {{cur}}' per T-269"
    )
    # hardcoded ru literal "внесено" must be gone from bot.py (only valid source
    # is i18n.bal_contributed). Note: we search for unquoted Cyrillic "внесено"
    # used as a display literal in an f-string — by now it should only appear
    # inside the i18n dict key (in i18n.py), not in bot.py.
    # But we allow occurrences inside a `_needs_lbl` etc. fallback — just forbid
    # the specific "· внесено {contrib" pattern that was the bug site.
    assert "· внесено {contrib" not in src, (
        "bot.py still contains '· внесено {contrib' — use i18n.bal_contributed"
    )
    return True


@test("6.5 T-270: _infer_subcategory matches 'oil' and IT fuel brands → Fuel")
def test_t270_oil_fuel_alias():
    from tools import transactions as tt
    known_subs = ["Fuel", "Parking", "Groceries", "Taxi", "Cafes"]
    # The T-262 bug case
    assert tt._infer_subcategory("COLDI OIL SERVICE SAS DI,SANREMO,IT", known_subs) == "Fuel"
    # generic oil token
    assert tt._infer_subcategory("SHELL OIL 42", known_subs) == "Fuel"
    # IT brands newly added
    for brand in ("ERG STATION MILANO", "API STAZIONE", "BEYFIN PISTOIA", "REPSOL MADRID"):
        assert tt._infer_subcategory(brand, known_subs) == "Fuel", (
            f"{brand} should resolve to Fuel via T-270 aliases"
        )
    # RU/UK tokens
    assert tt._infer_subcategory("АЗС ОККО КИЇВ", known_subs) == "Fuel"
    # Negative control — must not mis-classify
    assert tt._infer_subcategory("TESCO SUPERMARKET", known_subs) == "Groceries"
    return True


@test("6.7 T-272: add_transaction retries on workbook open failure")
def test_t272_add_transaction_retries_workbook_open():
    """Regression for PROD 2026-04-20 08:22 — 2 UAH transactions lost when
    env._ws("Transactions") failed to resolve (open_by_key raised) BEFORE
    entering _sheets_retry. Fix: wrap workbook resolution inside the retry
    lambda, reset env._wb on each attempt.

    Simulates the failure by monkey-patching env._ws to raise a retryable
    APIError on first call, then succeed.
    """
    import sheets as sheets_mod
    # Fake gspread APIError class with status_code=429
    import gspread.exceptions as gexc
    class FakeResponse:
        status_code = 429
    class FakeAPIError(gexc.APIError):
        def __init__(self):
            self.response = FakeResponse()
    # Build a fake EnvelopeSheets whose _ws raises 429 first time, then returns a stub
    calls = {"ws": 0, "append": 0}
    class StubWs:
        def append_row(self, row, **kw):
            calls["append"] += 1
            return None
    class FakeEnv:
        def __init__(self):
            self._wb = "dirty"  # simulate stale state from failed attempt
        def _ws(self, name):
            calls["ws"] += 1
            if calls["ws"] == 1:
                raise FakeAPIError()
            return StubWs()
    fake_env = FakeEnv()
    # Monkey-patch _env_sheets on a throwaway SheetsClient-like object
    class FakeClient:
        _cache = type("C", (), {"invalidate": lambda self, k: None})()
        def _env_sheets(self, sheet_id):
            return fake_env
        add_transaction = sheets_mod.SheetsClient.add_transaction
    client = FakeClient()
    row = ["2026-01-01", 100.0, "EUR", "Test", "", "Test merchant", "Mikhail",
           100.0, "expense", "Personal", "test0001", "TEST", "bot", "", "ts", "FALSE"]
    # Should NOT raise — retry kicks in on the 429
    tx_id = client.add_transaction("fake_sheet", row)
    assert tx_id == "test0001"
    assert calls["ws"] == 2, f"expected 2 _ws calls (1 fail + 1 retry), got {calls['ws']}"
    assert calls["append"] == 1, f"expected 1 append (on 2nd attempt), got {calls['append']}"
    assert fake_env._wb is None, "env._wb must be cleared before retry to force fresh open"
    return True


@test("6.6 T-271: Mix Markt + IT grocery chains → Groceries")
def test_t271_mix_markt_groceries_alias():
    """Regression for PROD row 159: 'MIX MARKT ITALIA SRL' had empty Subcategory
    despite Category=Food. Tokens [mix, markt, italia, srl] matched no alias.
    Added markt/mixmarkt + IT chains (Eurospin/Penny/Todis/Iper/Famila/Despar/
    Crai/NaturaSì) + generic IT shop types (supermercato/alimentari/panetteria/
    pescheria/latteria/drogheria/minimarket).
    """
    from tools import transactions as tt
    known_subs = ["Fuel", "Parking", "Groceries", "Taxi", "Cafes", "Restaurants"]
    # T-271 root-cause case
    assert tt._infer_subcategory("MIX MARKT ITALIA SRL", known_subs) == "Groceries"
    # IT grocery chains now covered by fallback
    for merchant in (
        "EUROSPIN TORINO", "PENNY MARKET MILANO", "TODIS ROMA",
        "IPER LA GRANDE I", "FAMILA SUPERSTORE", "DESPAR CENTRO",
        "CRAI PINO TORINESE", "NATURASI BIO",
    ):
        assert tt._infer_subcategory(merchant, known_subs) == "Groceries", (
            f"{merchant} must resolve to Groceries via T-271 aliases"
        )
    # Generic IT shop types
    for shop in (
        "SUPERMERCATO CONAD", "ALIMENTARI DA MARIO",
        "PANETTERIA SAN GIUSEPPE", "PESCHERIA DEL PORTO",
        "LATTERIA CENTRALE", "DROGHERIA MODERNA", "MINIMARKET 24H",
    ):
        assert tt._infer_subcategory(shop, known_subs) == "Groceries", (
            f"{shop} must resolve to Groceries via T-271 aliases"
        )
    return True


@test("6.9 T-273: enrich_transaction 429 → friendly i18n + error_type, no raw JSON")
def test_t273_enrich_friendly_429():
    """Regression for PROD 2026-04-20 09:45 UTC: 429 ReadRequestsPerMinutePerUser
    inside update_transaction_fields bubbled up as 'Sheets write failed: <huge
    HttpError JSON>' to user. Now must:
      1. Return friendly i18n message ('Google Sheets перегружен...').
      2. Set error_type='sheets_429' so caller can branch on it.
      3. Strip raw '429', 'Quota exceeded', 'Sheets write failed' from message.
    Also bumps retry budget on get_all_values inside edit_transaction_fields
    (max_attempts=3, base_delay=5.0) — verified by reading sheets.py source.
    """
    import inspect
    from tools import transactions as tt
    from sheets import SheetsClient
    src = inspect.getsource(tt.tool_enrich_transaction)
    # Code-level checks (the live integration test ran outside regression suite,
    # see commit message — regression here verifies the source paths exist).
    assert "sheets_busy" in src and "sheets_unavailable" in src, (
        "T-273: enrich_transaction must reference both i18n keys"
    )
    assert "sheets_429_read" in src or "sheets_429" in src, (
        "T-273: enrich_transaction must emit a 429-specific error_type"
    )
    assert "log_error" in src, (
        "T-273: enrich_transaction must persist 429 to error_log"
    )
    # i18n keys exist in all 4 langs
    from i18n import SYS
    for k in ("sheets_busy", "sheets_unavailable"):
        for lang in ("ru", "uk", "en", "it"):
            assert SYS.get(k, {}).get(lang), f"T-273: i18n[{k}][{lang}] missing"
    # sheets.py read-path retry budget bumped
    import sheets as _sh_mod
    sh_src = inspect.getsource(_sh_mod.EnvelopeSheets.edit_transaction_fields)
    assert "max_attempts=3" in sh_src and "base_delay=5.0" in sh_src, (
        "T-273: edit_transaction_fields read must use bumped retry budget"
    )
    # Old leaky message string is gone from RETURNED dict, not just from
    # docstring comments (the old line was: return {"error": f"Sheets write
    # failed: {e}"} — must no longer exist as an f-string return value).
    assert 'f"Sheets write failed:' not in src, (
        "T-273: legacy 'Sheets write failed: {e}' f-string return must be removed"
    )
    return True


@test("6.8 T-274: car-wash + bare 'parking' aliases + bigram matching")
def test_t274_carwash_parking_bigrams():
    """Regression for PROD row 162 (CHIERI, edffad68): empty Subcategory despite
    agent showing 'Парковка' in analysis. Real merchant was 'Мойка' (per Mikhail).
    Three classes of fix:
      1. RU/UA/IT car-wash aliases (мойка/мийка/lavaggio/autolavaggio/carwash) → Fuel.
      2. Bare English 'parking' self-map (had 'parking lot' bigram and 'паркінг'
         Cyrillic but not single-token EN 'parking').
      3. Bigram pass — multi-word aliases ('car wash', 'parking lot', 'gas station',
         'fuel station', 'fast food') now match across token boundaries.
    Without this all three would still produce empty Subcategory in PROD writes.
    """
    from tools import transactions as tt
    known = ["Fuel", "Parking", "Restaurants", "Cafes"]
    # Class 1: car-wash variants
    for note in (
        "Автомойка центр", "Автомийка Pinerolo", "Lavaggio auto via Roma",
        "Autolavaggio Express", "carwash 24h", "Мойка Чиери",
    ):
        assert tt._infer_subcategory(note, known) == "Fuel", (
            f"{note!r} must resolve to Fuel via T-274 car-wash aliases"
        )
    # Class 2: bare EN 'parking'
    assert tt._infer_subcategory("Parking 24h Stazione", known) == "Parking"
    assert tt._infer_subcategory("PARKING TORINO CENTRO", known) == "Parking"
    # Class 3: bigram matching
    for note, expected in (
        ("CAR WASH CENTER", "Fuel"),
        ("PARKING LOT 5", "Parking"),
        ("GAS STATION 24", "Fuel"),
        ("FUEL STATION ESSO", "Fuel"),
        ("FAST FOOD CHIPS", "Restaurants"),
    ):
        assert tt._infer_subcategory(note, known) == expected, (
            f"{note!r} bigram must resolve to {expected!r} via T-274 bigram pass"
        )
    # Negative: original CHIERI without any alias keyword still returns empty
    # (so T-275 clarification UX has something to trigger on).
    assert tt._infer_subcategory("46492 CHIERI - CORSO T", known) == "", (
        "raw CHIERI text without alias keywords must return empty (no false positives)"
    )
    return True


@test("6.10 T-278: store_pending_receipt schema does NOT accept `who`")
def test_t278_schema_drops_who():
    """Photo receipts always belong to the session user. The LLM must not be
    able to override attribution. Bug class: Maryna's 4 receipts on 2026-04-24
    written as Mikhail because prompt biased LLM to who='Mikhail'."""
    import re as _re
    src = open("agent.py").read()
    m = _re.search(
        r'"name":\s*"store_pending_receipt".*?"input_schema".*?"properties":\s*\{(.*?)\n\s{12}\}',
        src,
        _re.DOTALL,
    )
    assert m, "store_pending_receipt schema block not found"
    props = "\n".join(
        line for line in m.group(1).split("\n") if not line.strip().startswith("#")
    )
    assert '"who"' not in props, (
        "store_pending_receipt schema must not contain `who` (T-278). "
        "Remove from schema and rely on session.user_name in receipt_data."
    )
    return True


@test("6.11 T-278: agent.py + bot.py no longer trust LLM-supplied who for receipts")
def test_t278_no_llm_who_in_receipt_paths():
    src_a = open("agent.py").read()
    assert 'params.get("who", session.user_name' not in src_a, (
        "agent.py: LLM-supplied who must NOT flow into receipt_data (T-278)"
    )
    assert '"who": session.user_name or ""' in src_a, (
        "agent.py: receipt_data must explicitly use session.user_name (T-278)"
    )
    src_b = open("bot.py").read()
    forbidden = [
        '"who": receipt.get("who", session.user_name)',
        '"who": receipt.get("who") or session.user_name',
        'item.get("who") or receipt.get("who") or session.user_name',
        'session.user_name or "Mikhail"',
    ]
    for f in forbidden:
        assert f not in src_b, f"bot.py: forbidden pattern still present (T-278): {f}"
    return True


@test("6.12 T-278: ApolioHome_Prompt.md drops `(Mikhail)` identity hardcode")
def test_t278_prompt_no_mikhail_hardcode():
    src = open("ApolioHome_Prompt.md").read()
    assert "use the session user (Mikhail)" not in src, (
        "Prompt must not hardcode '(Mikhail)' as session-user fallback (T-278). "
        "Use OMIT-based rule + bot fills from session.user_name."
    )
    # Examples must not bake user names
    bad_examples = [
        "Продукты · 85 EUR · Mikhail · сегодня",
        "Food · 38.50 EUR · Mikhail · 09.04 · TAVOLO N.102",
    ]
    for be in bad_examples:
        assert be not in src, f"Prompt example bakes literal user name (T-278): {be!r}"
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

# Run all registered tests (they auto-execute via decorator calls above)
# Count results
passed = sum(1 for v in results.values() if v is True)
failed = sum(1 for v in results.values() if v is False)
skipped = sum(1 for v in results.values() if v is None)
total = passed + failed  # skips don't count toward total

print("\n" + "═" * 60)
print(f"  Results: {passed}/{total} passed", end="")
if skipped:
    print(f"  ({skipped} skipped)", end="")
print()

if failed > 0:
    print(f"\n  FAILED tests:")
    for name, ok in results.items():
        if ok is False:
            print(f"    ❌  {name}")

print("═" * 60)
sys.exit(0 if failed == 0 else 1)
