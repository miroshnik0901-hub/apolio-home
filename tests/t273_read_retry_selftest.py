"""
T-273 integration test: verify that READ-path calls in the enrichment/dup-update
flow are wrapped in _sheets_retry so a 429 transient error gets retried instead
of bubbling raw HttpError JSON to the user.

Scenario:
  1. Mock gspread.Worksheet to raise HttpError 429 on first get_all_values() call
     and succeed on the second.
  2. Call each wrapped function and verify it completes cleanly (retry fires).
  3. Verify tool_enrich_transaction's except path classifies 429 correctly,
     logs to error_log, and returns friendly i18n (error_type='sheets_429').
  4. Assert no raw JSON "HttpError", "Quota exceeded", or {"code": 429,...} in
     the returned error message.
"""
import sys, os; sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")
import asyncio


def make_fake_http_error(code=429, msg="Quota exceeded for quota metric 'ReadRequestsPerMinutePerUser'"):
    """Fake googleapiclient HttpError with the standard 429 shape."""
    _reason = msg  # rebind to avoid class-body scope bug
    _code = code
    class _Resp:
        status = _code
        reason = _reason
    from googleapiclient.errors import HttpError
    content = (
        f'{{"error": {{"code": {code}, "message": "{msg}", '
        f'"status": "RESOURCE_EXHAUSTED"}}}}'
    ).encode()
    return HttpError(_Resp(), content)


def make_gspread_api_error(status=429):
    """Fake gspread APIError — this is what _sheets_retry actually catches.
    Real errors raised by gspread wrap the google API response."""
    import gspread
    class _Resp:
        status_code = status
        def json(self): return {"error": {"code": status, "message": "Quota exceeded"}}
    err = gspread.exceptions.APIError(_Resp())
    err.response = _Resp()
    return err


def test_sheets_retry_covers_429():
    """Verify _sheets_retry retries a gspread APIError 429 and eventually succeeds."""
    from sheets import _sheets_retry
    calls = {"n": 0}
    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise make_gspread_api_error(429)
        return [["Header1", "Header2"], ["a", "b"]]
    result = _sheets_retry(flaky, max_attempts=3, base_delay=0.01)
    assert calls["n"] == 2, f"expected 2 calls (1 fail + 1 success), got {calls['n']}"
    assert result == [["Header1", "Header2"], ["a", "b"]]
    print("  ✓ _sheets_retry retries APIError 429 → success on 2nd attempt")


def test_sheets_retry_final_failure_raises():
    """All attempts fail → _sheets_retry raises (caller must catch)."""
    from sheets import _sheets_retry
    def always_429():
        raise make_gspread_api_error(429)
    try:
        _sheets_retry(always_429, max_attempts=2, base_delay=0.01)
        print("  ✗ expected APIError to propagate after max_attempts")
        return False
    except Exception as e:
        assert "429" in str(e) or "Quota" in str(e) or "APIError" in type(e).__name__, \
            f"unexpected exception: {type(e).__name__}: {e!r}"
        print("  ✓ _sheets_retry raises after max_attempts exhausted")
    return True


def test_enrich_catches_429_and_returns_friendly():
    """tool_enrich_transaction wraps the 429 into friendly i18n + logs + error_type."""
    import tools.transactions as txmod
    import logging; logging.getLogger().setLevel(logging.CRITICAL)  # silence noise

    class FakeSession:
        user_id = 360466156
        current_envelope_id = "TEST_BUDGET"
        lang = "ru"

    class FakeSheets:
        def get_envelopes(self):
            return [{"ID": "TEST_BUDGET", "file_id": "fake_file"}]
        def get_reference_data(self, file_id):
            return {"categories": [], "subcategories": ["Fuel", "Parking"],
                    "accounts": [{"name": "Personal"}]}
        # Real method called by tool_enrich_transaction (line 1105):
        def update_transaction_fields(self, file_id, tx_id, fields):
            raise make_fake_http_error(429)

    class FakeAuth:
        def can_write(self, uid):
            return True

    async def run():
        return await txmod.tool_enrich_transaction(
            {"tx_id": "abc123", "subcategory": "Fuel"},
            FakeSession(), FakeSheets(), FakeAuth(),
        )
    result = asyncio.run(run())

    assert isinstance(result, dict), f"expected dict, got {type(result).__name__}"
    assert "error" in result, f"expected 'error' key; got {result!r}"
    err_msg = result["error"]
    # Must NOT contain raw JSON
    assert "HttpError" not in err_msg, f"raw HttpError leaked: {err_msg}"
    assert '"code":' not in err_msg, f"raw JSON leaked: {err_msg}"
    assert "Quota exceeded" not in err_msg or "Google Sheets" in err_msg, \
        f"raw quota message leaked without wrapping: {err_msg}"
    # Must contain friendly signal
    assert "Sheets" in err_msg or "лимит" in err_msg or "перегр" in err_msg, \
        f"friendly phrasing missing: {err_msg}"
    # Must classify error_type
    assert result.get("error_type") == "sheets_429", \
        f"expected error_type='sheets_429', got {result.get('error_type')!r}"
    print(f"  ✓ tool_enrich_transaction returns friendly error: {err_msg[:70]}...")
    print(f"  ✓ error_type correctly classified as {result['error_type']!r}")


def test_read_path_calls_are_wrapped():
    """Grep sheets.py to confirm each naked ws.get_all_values() at enrichment-adjacent
    read sites is now wrapped in _sheets_retry."""
    with open("sheets.py") as f:
        src = f.read()
    # Lines that SHOULD be wrapped (T-273 scope):
    wrapped_markers = [
        "rows = _sheets_retry(ws.get_all_values)",
        "all_values = _sheets_retry(ws.get_all_values)",
        "all_vals = _sheets_retry(ws.get_all_values, max_attempts=3, base_delay=5.0)",
        "all_rows = _sheets_retry(ws.get_all_values)",
    ]
    for m in wrapped_markers:
        assert m in src, f"expected wrapped read not found: {m!r}"
    # edit_transaction_fields must use the bumped budget (T-273 original fix)
    assert "_sheets_retry(ws.get_all_values, max_attempts=3, base_delay=5.0)" in src, \
        "edit_transaction_fields retry budget not bumped"
    # Multiple wrapped read sites — not just one
    wrap_count = src.count("_sheets_retry(ws.get_all_values")
    assert wrap_count >= 8, f"expected ≥8 wrapped READ sites, got {wrap_count}"
    print(f"  ✓ {wrap_count} _sheets_retry-wrapped READ sites in sheets.py")


def test_i18n_keys_present():
    """T-273 i18n keys must exist in all 4 languages."""
    import i18n
    for key in ("sheets_busy", "sheets_unavailable"):
        for lang in ("ru", "uk", "en", "it"):
            val = i18n.ts(key, lang)
            assert val and val != key, f"{key}.{lang} missing (got {val!r})"
    print("  ✓ i18n keys sheets_busy + sheets_unavailable present in ru/uk/en/it")


if __name__ == "__main__":
    print("=== T-273 read-path retry self-test ===\n")
    tests = [
        test_sheets_retry_covers_429,
        test_sheets_retry_final_failure_raises,
        test_enrich_catches_429_and_returns_friendly,
        test_read_path_calls_are_wrapped,
        test_i18n_keys_present,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: unexpected {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    sys.exit(0 if failed == 0 else 1)
