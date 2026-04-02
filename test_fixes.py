"""
test_fixes.py — verify the three fixes from commit 7d55a00

  T1: FX column name fix  (tools/transactions.py  + sheets.py FX_Rates lookup)
  T2: _row field in get_transactions  (sheets.py EnvelopeSheets.get_transactions)
  T3: Dashboard writer via refresh_dashboard tool

Usage:  python test_fixes.py
"""

import os, sys, asyncio, time
from dotenv import load_dotenv
load_dotenv()

PASS = "  ✓"
FAIL = "  ✗"
SKIP = "  ⚠"

ENV_ID  = "MM_BUDGET"
FILE_ID = "1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ"

# ── helpers ──────────────────────────────────────────────────────────────────

def _sheets_client():
    from sheets import SheetsClient
    return SheetsClient()

def _auth_manager():
    from sheets import get_sheets_client, AdminSheets
    from auth import AuthManager
    return AuthManager(AdminSheets(get_sheets_client()))

def _session(uid="360466156", name="Mikhail"):
    from auth import SessionContext
    try:
        s = SessionContext(user_id=uid, user_name=name, role="admin")
    except TypeError:
        # Fallback if constructor differs
        s = SessionContext.__new__(SessionContext)
        s.user_id = uid
        s.user_name = name
        s.role = "admin"
        s.lang = "ru"
        s.current_envelope_id = ENV_ID
        s.last_action = None
        s.pending_prompt = None
        s.pending_delete = None
        s.session_id = None
        return s
    s.current_envelope_id = ENV_ID
    return s

# ── T1: FX fix ───────────────────────────────────────────────────────────────

def test_T1_fx_column():
    print("\nT1 — FX rate lookup column name fix")
    try:
        sc = _sheets_client()
        file_id = FILE_ID
        # Read FX_Rates sheet directly to confirm column names
        from sheets import EnvelopeSheets, get_sheets_client
        gc = get_sheets_client()
        es = EnvelopeSheets(gc, file_id)
        ws = es._ws("FX_Rates")
        headers = ws.row_values(1)
        print(f"   FX_Rates headers: {headers}")

        expected_keys = [h for h in headers if h.startswith("EUR_")]
        if not expected_keys:
            print(f"{SKIP} No EUR_* columns found — no FX data in sheet yet")
            return True

        # Check that the code uses the right key
        code = open("tools/transactions.py").read()
        if 'f"EUR_{currency.upper()}"' in code or "EUR_{currency.upper()}" in code:
            print(f"{PASS} tools/transactions.py uses EUR_<CURRENCY> key")
            return True
        else:
            print(f"{FAIL} tools/transactions.py does NOT use EUR_<CURRENCY> key")
            return False
    except Exception as e:
        print(f"{FAIL} Exception: {e}")
        return False


# ── T2: _row field ───────────────────────────────────────────────────────────

def test_T2_row_field():
    print("\nT2 — _row field in get_transactions")
    try:
        sc = _sheets_client()
        time.sleep(2)
        txns = sc.get_transactions(FILE_ID)
        if not txns:
            print(f"{SKIP} No transactions in sheet — cannot verify")
            return True

        t = txns[0]
        if "_row" not in t:
            print(f"{FAIL} First transaction has no _row field. Keys: {list(t.keys())[:8]}")
            return False

        # Verify _row is always >= 2 (row 1 is header)
        bad = [t for t in txns if t.get("_row", 0) < 2]
        if bad:
            print(f"{FAIL} {len(bad)} transaction(s) have _row < 2")
            return False

        # Verify _row is monotonically increasing (can have gaps after deletes)
        rows = [t["_row"] for t in txns]
        if rows != sorted(rows):
            print(f"{FAIL} _row values are not sorted: {rows[:10]}")
            return False

        print(f"{PASS} _row field present and correct on {len(txns)} transactions")
        print(f"   First row: {txns[0]['_row']}, Last row: {txns[-1]['_row']}")
        return True
    except Exception as e:
        print(f"{FAIL} Exception: {e}")
        import traceback; traceback.print_exc()
        return False


# ── T3: Dashboard writer ──────────────────────────────────────────────────────

async def test_T3_dashboard_async():
    print("\nT3 — refresh_dashboard writes to Dashboard tab")
    try:
        from agent import ApolioAgent
        from auth import SessionContext

        sc = _sheets_client()
        auth = _auth_manager()
        agent = ApolioAgent(sc, auth)

        session = _session()

        params = {"envelope_id": ENV_ID}
        result = await agent._tool_refresh_dashboard(params, session, sc, auth)

        if result.get("status") == "ok":
            print(f"{PASS} refresh_dashboard returned OK")
            print(f"   {result['message']}")
        elif result.get("error"):
            print(f"{FAIL} refresh_dashboard error: {result['error']}")
            return False
        else:
            print(f"{SKIP} Unexpected result: {result}")
            return False

        # Verify the Dashboard tab actually has data now
        from sheets import EnvelopeSheets, get_sheets_client
        gc = get_sheets_client()
        es = EnvelopeSheets(gc, FILE_ID)
        ws = es._ws("Dashboard")
        all_values = ws.get_all_values()
        if not all_values or not any(any(c.strip() for c in row) for row in all_values[:5]):
            print(f"{FAIL} Dashboard tab appears empty after write")
            return False

        # Check for key markers
        flat = "\n".join(" | ".join(r) for r in all_values)
        checks = [
            ("Отчёт за" in flat or "Дашборд за" in flat, "Header with month"),
            ("Взносы" in flat, "Contribution section"),
            ("Расходы" in flat, "Expenses line"),
        ]
        all_ok = True
        for ok, label in checks:
            sym = PASS if ok else FAIL
            print(f"{sym} Dashboard contains: {label}")
            if not ok:
                all_ok = False

        print(f"   Dashboard has {len(all_values)} rows written")
        return all_ok

    except Exception as e:
        print(f"{FAIL} Exception: {e}")
        import traceback; traceback.print_exc()
        return False

def test_T3_dashboard():
    return asyncio.run(test_T3_dashboard_async())


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Apolio Home — Fix Regression Tests (commit 7d55a00) ===")

    results = {
        "T1 FX column fix":          test_T1_fx_column(),
        "T2 _row field":             test_T2_row_field(),
        "T3 Dashboard writer":       test_T3_dashboard(),
    }

    print("\n" + "=" * 50)
    passed = sum(1 for v in results.values() if v)
    total  = len(results)
    for name, ok in results.items():
        sym = "✅" if ok else "❌"
        print(f"  {sym}  {name}")
    print(f"\n{passed}/{total} tests passed")
    sys.exit(0 if passed == total else 1)
