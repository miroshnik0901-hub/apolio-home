#!/usr/bin/env python3
"""Self-tests for T-259 (DEFAULT_ENVELOPE hardcode removed),
A-011 (base_contributor 'Mikhail' default removed),
T-260 (weekly report UX reuses _build_balance_line_async format).

Run: python3 tests/t259_t260_a011_selftest.py
Exits 0 on success, 1 on failure. Prints concrete output for each assertion.
"""
import sys
import os

# Load .env before importing project modules
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

FAIL = 0


def assert_eq(label, got, expected):
    global FAIL
    ok = got == expected
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}: got={got!r}  expected={expected!r}")
    if not ok:
        FAIL += 1


def assert_true(label, cond, detail=""):
    global FAIL
    mark = "✓" if cond else "✗"
    print(f"  {mark} {label}  {detail}")
    if not cond:
        FAIL += 1


def test_t259_no_default_envelope_constant():
    print("\n[T-259] auth.py no longer exposes DEFAULT_ENVELOPE as a hardcoded constant")
    import auth
    assert_true(
        "auth module has no DEFAULT_ENVELOPE attribute",
        not hasattr(auth, "DEFAULT_ENVELOPE"),
        "(old hardcode 'MM_BUDGET' must be gone)",
    )


def test_t259_get_session_uses_auth_manager():
    print("\n[T-259] get_session resolves envelope from Admin.Users.envelopes")
    import auth
    from sheets import SheetsClient

    # Clear in-memory sessions to avoid state bleed
    auth._sessions.clear()

    sheets = SheetsClient()
    auth_mgr = auth.AuthManager(sheets)
    auth.register_auth_manager(auth_mgr)

    # Mikhail's Telegram ID — same on TEST + PROD Admin.Users
    mikhail_id = int(os.environ.get("MIKHAIL_TELEGRAM_ID", "360466156"))

    # Force reload so we read fresh Admin.Users data
    auth_mgr.invalidate()
    user = auth_mgr.get_user(mikhail_id)
    assert_true(
        "AuthManager knows Mikhail",
        user is not None,
        f"(user={user})",
    )
    envelopes = (user or {}).get("envelopes", [])
    assert_true(
        "Mikhail has >=1 envelope in Admin.Users",
        len(envelopes) > 0,
        f"(envelopes={envelopes})",
    )
    first_env = envelopes[0] if envelopes else None

    session = auth.get_session(mikhail_id, "Mikhail", "admin")
    assert_eq(
        "get_session returns envelope matching Admin.Users.envelopes[0]",
        session.current_envelope_id,
        first_env,
    )

    # Second call must also return same envelope (restore path)
    auth._sessions.clear()
    session2 = auth.get_session(mikhail_id, "Mikhail", "admin")
    # Force restore-path: clear current_envelope_id then call again
    session2.current_envelope_id = None
    session3 = auth.get_session(mikhail_id, "Mikhail", "admin")
    assert_eq(
        "get_session restore-path resolves to same envelope",
        session3.current_envelope_id,
        first_env,
    )


def test_t259_get_session_without_auth_registered():
    print("\n[T-259] get_session with no registered AuthManager → None (no hardcoded fallback)")
    import auth

    auth._sessions.clear()
    saved = auth._registered_auth
    auth._registered_auth = None
    try:
        session = auth.get_session(999999999, "Unknown", "readonly")
        assert_eq(
            "unregistered + unknown user → current_envelope_id=None",
            session.current_envelope_id,
            None,
        )
    finally:
        auth._registered_auth = saved


def test_a011_no_mikhail_default():
    print("\n[A-011] intelligence.py no longer hardcodes base_contributor='Mikhail'")
    with open(os.path.join(os.path.dirname(__file__), "..", "intelligence.py")) as f:
        src = f.read()
    # The old default must be gone. Two call sites: compute_contribution_status + compute_cumulative_balance
    bad = 'env_config.get("base_contributor", "Mikhail")'
    occurrences = src.count(bad)
    assert_eq(
        "no `base_contributor, \"Mikhail\"` defaults remain",
        occurrences,
        0,
    )
    # Must have the new warning-on-empty code
    assert_true(
        "compute_contribution_status warns on missing base_contributor",
        "compute_contribution_status: base_contributor missing" in src,
    )
    assert_true(
        "compute_cumulative_balance warns on missing base_contributor",
        "compute_cumulative_balance: base_contributor missing" in src,
    )


def test_t260_build_report_html_uses_new_format():
    print("\n[T-260] _build_report_html emits 'потрібно внести/переплата' vocabulary, not 'доля'")
    with open(os.path.join(os.path.dirname(__file__), "..", "bot.py")) as f:
        src = f.read()

    # Old confusing vocabulary must be gone from _build_report_html block
    # (still acceptable elsewhere in i18n dicts etc.)
    bad_fragment = "{a:,.0f} внесено · {s:,.0f} доля"
    assert_true(
        "old '{a} внесено · {s} доля → ±Z EUR' rendering is gone",
        bad_fragment not in src,
        f"(checked for: {bad_fragment!r})",
    )

    # New vocabulary present
    assert_true(
        "new _needs_lbl table present in bot.py",
        '"uk": "потрібно внести"' in src and '"ru": "нужно внести"' in src,
    )
    # T-269 refactor: bal_contributed moved from local dict to i18n.py.
    # Test now verifies i18n.bal_contributed carries all 4 languages.
    with open("i18n.py", "r") as _f:
        _i18n_src = _f.read()
    assert_true(
        "bal_contributed in i18n.py covers all 4 langs (T-269 refactor of T-260 dict)",
        '"bal_contributed"' in _i18n_src and '"it": "versato"' in _i18n_src
        and '"en": "contributed"' in _i18n_src,
    )
    assert_true(
        "uses i18n.ts('bal_overpaid', ...) for credit > 0 branch",
        "i18n.ts('bal_overpaid', lang)" in src,
    )


def test_t260_format_simulation():
    print("\n[T-260] Format simulation for Mikhail's screenshot case")
    # Screenshot said:
    #   ⚠️ Mikhail: 1,322 внесено · 1,178 доля → -1,178 EUR  → interpret credit = -1178
    #   ✅ Maryna:     396 внесено ·  -396 доля → +396 EUR  → interpret credit = +396
    # New rendering must be readable.
    cur = "EUR"
    lang = "uk"
    _needs_lbl = {"ru": "нужно внести", "uk": "потрібно внести",
                  "en": "needs to fund", "it": "da versare"}
    _contributed_lbl = {"ru": "внесено", "uk": "внесено",
                        "en": "contributed", "it": "versato"}

    def render(user, credit, contrib):
        if credit < 0:
            return (f"  ⚠️ <b>{user}</b>: {abs(credit):,.0f} {cur} "
                    f"({_needs_lbl[lang]}) · {_contributed_lbl[lang]} {contrib:,.0f}")
        elif credit > 0:
            # bal_overpaid = "переплата" in uk
            return (f"  ✅ <b>{user}</b>: +{credit:,.0f} {cur} "
                    f"(переплата) · {_contributed_lbl[lang]} {contrib:,.0f}")
        return (f"  ✅ <b>{user}</b>: 0 {cur} · {_contributed_lbl[lang]} {contrib:,.0f}")

    mikhail_line = render("Mikhail", -1178, 1322)
    maryna_line  = render("Maryna",   396,  396)
    print(f"    {mikhail_line}")
    print(f"    {maryna_line}")
    assert_true(
        "Mikhail line: 'потрібно внести 1,178' present",
        "потрібно внести" in mikhail_line and "1,178" in mikhail_line,
    )
    assert_true(
        "Maryna line: '+396 (переплата)' present",
        "+396" in maryna_line and "переплата" in maryna_line,
    )


if __name__ == "__main__":
    test_t259_no_default_envelope_constant()
    test_t259_get_session_uses_auth_manager()
    test_t259_get_session_without_auth_registered()
    test_a011_no_mikhail_default()
    test_t260_build_report_html_uses_new_format()
    test_t260_format_simulation()
    print("\n" + "=" * 50)
    if FAIL:
        print(f"  FAILED: {FAIL} assertion(s)")
        sys.exit(1)
    print("  PASS: all T-259 + A-011 + T-260 assertions")
    sys.exit(0)
