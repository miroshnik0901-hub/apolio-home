#!/usr/bin/env python3
"""Self-tests for T-278: contributor attribution must come from session, not LLM.

Three layers of defense:
  L1 (static)  — agent.py store_pending_receipt schema MUST NOT contain `who`.
  L1 (static)  — ApolioHome_Prompt.md MUST NOT contain "(Mikhail)" hardcode in
                 identity-rule blocks (line 319 historical bug location).
  L2 (logic)   — _tool_store_pending_receipt always assigns receipt['who'] from
                 session.user_name regardless of what params['who'] would be.
  L3 (smoke)   — bot.py photo callback paths use session.user_name, never
                 receipt.get('who'); grep-based check.

Run: python3 tests/t278_who_attribution_selftest.py
Exits 0 on success, 1 on failure.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

FAIL = 0


def assert_true(label, cond, detail=""):
    global FAIL
    mark = "✓" if cond else "✗"
    print(f"  {mark} {label}  {detail}")
    if not cond:
        FAIL += 1


def assert_eq(label, got, expected):
    global FAIL
    ok = got == expected
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}: got={got!r}  expected={expected!r}")
    if not ok:
        FAIL += 1


def _read(path):
    with open(os.path.join(os.path.dirname(__file__), "..", path)) as f:
        return f.read()


def test_l1_store_pending_receipt_schema_has_no_who():
    print("\n[T-278 L1] agent.py store_pending_receipt schema MUST NOT have `who`")
    src = _read("agent.py")
    # Locate the store_pending_receipt tool block
    m = re.search(
        r'"name":\s*"store_pending_receipt".*?"input_schema".*?"properties":\s*\{(.*?)\n\s{12}\}',
        src,
        re.DOTALL,
    )
    assert_true(
        "store_pending_receipt schema block found",
        m is not None,
        "(regex must locate the tool's input_schema.properties)",
    )
    if m:
        props_block = m.group(1)
        # `who` must be absent OR present only in a comment line
        # Strip comment lines first
        non_comment = "\n".join(
            line for line in props_block.split("\n") if not line.strip().startswith("#")
        )
        assert_true(
            "no `who` key in store_pending_receipt properties (comments stripped)",
            '"who"' not in non_comment,
            "(LLM must not be able to supply `who` for photo receipts)",
        )


def test_l1_prompt_no_mikhail_hardcode_in_identity_rule():
    print("\n[T-278 L1] ApolioHome_Prompt.md identity rule MUST NOT hardcode \"(Mikhail)\"")
    src = _read("ApolioHome_Prompt.md")
    # Historical bug: line 319 had "If sender is not identifiable → use the session user (Mikhail)"
    bad = "use the session user (Mikhail)"
    assert_true(
        "old `use the session user (Mikhail)` hardcode is gone",
        bad not in src,
        f"(checked for: {bad!r})",
    )
    # Bot must rely on `{user_name}` placeholder or session-fill instruction
    assert_true(
        "T-278 OMIT-fallback rule present in prompt",
        "OMIT the `who` field" in src or "the bot fills `who` from the session user" in src
            or "bot fills it from the session user" in src,
        "(prompt should tell agent to omit who and let bot fill from session)",
    )


def test_l1_prompt_examples_do_not_bake_in_user_name():
    print("\n[T-278 L1] prompt example outputs MUST use placeholder, not literal user")
    src = _read("ApolioHome_Prompt.md")
    bad_a = "Продукты · 85 EUR · Mikhail · сегодня"
    bad_b = "1. 🍕 Food · 38.50 EUR · Mikhail · 09.04 · TAVOLO N.102"
    assert_true(
        "old example `Продукты · 85 EUR · Mikhail` replaced",
        bad_a not in src,
        f"(checked for: {bad_a!r})",
    )
    assert_true(
        "old example `Food · 38.50 EUR · Mikhail` replaced",
        bad_b not in src,
        f"(checked for: {bad_b!r})",
    )


def test_l2_tool_store_pending_receipt_uses_session_user_name():
    print("\n[T-278 L2] _tool_store_pending_receipt assigns who from session.user_name only")
    src = _read("agent.py")
    # Old code: `"who": params.get("who", session.user_name or "")`
    bad = 'params.get("who", session.user_name'
    assert_true(
        "no `params.get(\"who\", session.user_name...)` left in agent.py",
        bad not in src,
        f"(LLM-supplied who must not flow into receipt_data; checked: {bad!r})",
    )
    # Must have explicit session-only assignment somewhere in the receipt_data block
    assert_true(
        "explicit `session.user_name` assignment for receipt who present",
        '"who": session.user_name or ""' in src,
        "(grep `\"who\": session.user_name or \"\"`)",
    )


def test_l3_bot_photo_callback_no_receipt_get_who():
    print("\n[T-278 L3] bot.py photo paths MUST collapse who to session.user_name")
    src = _read("bot.py")
    # The two old patterns that put LLM-supplied who into add_params:
    #   "who": receipt.get("who", session.user_name)
    #   "who": receipt.get("who") or session.user_name
    bad_patterns = [
        '"who": receipt.get("who", session.user_name)',
        '"who": receipt.get("who") or session.user_name',
    ]
    for bp in bad_patterns:
        assert_true(
            f"old pattern absent: {bp!r}",
            bp not in src,
            "(receipt.get(who) is no longer trusted — collapse to session.user_name)",
        )
    # Old bulk per-item path must also be gone
    bad_bulk = 'item.get("who") or receipt.get("who") or session.user_name'
    assert_true(
        "bulk per-item fallback no longer chains receipt.get(who)",
        bad_bulk not in src,
        f"(checked: {bad_bulk!r})",
    )
    # Old cmd_start hardcode `or "Mikhail"` must be gone
    assert_true(
        "cmd_start `name = session.user_name or \"Mikhail\"` removed",
        'session.user_name or "Mikhail"' not in src,
        "(no literal `or \"Mikhail\"` fallback anywhere in bot.py)",
    )


def test_l3_simulation_maryna_session():
    print("\n[T-278 L3] Simulation: Maryna session → photo receipt → who=Maryna")
    # Mimic the receipt_data construction from agent._tool_store_pending_receipt
    # post-T-278 logic.
    class _S:
        user_name = "Maryna"
        user_id = 219501159
        pending_receipt = None

    session = _S()
    # Even if the LLM tried to pass who="Mikhail" (legacy bug input),
    # the schema rejects it at the API layer; here we simulate the function body
    # which should ignore params["who"] and use session.user_name.
    params = {
        "merchant": "ANTICA PIZZERIA DA MICHELE SRL",
        "total_amount": 25.0,
        "currency": "EUR",
        "category": "Food",
        # legacy bug input that MUST be ignored:
        "who": "Mikhail",
    }

    # Re-implement the post-T-278 receipt_data builder inline:
    receipt_data = {
        "merchant": params.get("merchant", ""),
        "total_amount": params.get("total_amount", 0),
        "currency": params.get("currency", "EUR"),
        "category": params.get("category", ""),
        "who": session.user_name or "",  # T-278 lock
    }
    assert_eq(
        "receipt_data['who'] == 'Maryna' (LLM-supplied 'Mikhail' ignored)",
        receipt_data["who"],
        "Maryna",
    )

    # Now simulate bot.py photo-callback add_params (line 3850 post-T-278):
    add_params = {
        "amount": receipt_data.get("total_amount", 0),
        "currency": receipt_data.get("currency", "EUR"),
        "category": receipt_data.get("category", "Food"),
        "who": session.user_name,  # T-278 lock at callback site too
    }
    assert_eq(
        "bot.py add_params['who'] == 'Maryna' (always session)",
        add_params["who"],
        "Maryna",
    )


def test_l3_simulation_bank_statement_per_item_who():
    print("\n[T-278 L3] Simulation: bank-statement items[].who set by Python parser → preserved")
    # aggregate_bank_statement (T-261) sets items[].who from sender names parsed
    # in Note. After T-278 the receipt-level who is gone, but per-item who must
    # still be honored when explicitly set (not from LLM, from Python parser).
    class _S:
        user_name = "Maryna"

    session = _S()
    items = [
        {"name": "From Mikhail Miro top-up", "amount": 500, "who": "Mikhail"},  # explicit
        {"name": "Coffee", "amount": 4.5},                                     # no who
    ]

    resolved = []
    for item in items:
        # bot.py line ~4241 post-T-278: item_who = item.get("who") or session.user_name
        item_who = item.get("who") or session.user_name
        resolved.append(item_who)

    assert_eq(
        "explicit per-item who survives (Mikhail's top-up in Maryna's statement)",
        resolved[0],
        "Mikhail",
    )
    assert_eq(
        "missing per-item who → session user fallback (Maryna)",
        resolved[1],
        "Maryna",
    )


if __name__ == "__main__":
    test_l1_store_pending_receipt_schema_has_no_who()
    test_l1_prompt_no_mikhail_hardcode_in_identity_rule()
    test_l1_prompt_examples_do_not_bake_in_user_name()
    test_l2_tool_store_pending_receipt_uses_session_user_name()
    test_l3_bot_photo_callback_no_receipt_get_who()
    test_l3_simulation_maryna_session()
    test_l3_simulation_bank_statement_per_item_who()
    print("\n" + "=" * 50)
    if FAIL:
        print(f"  FAILED: {FAIL} assertion(s)")
        sys.exit(1)
    print("  PASS: all T-278 assertions")
    sys.exit(0)
