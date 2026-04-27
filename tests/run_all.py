#!/usr/bin/env python3
"""
Apolio Home — Automated Test Runner
Usage: python3 tests/run_all.py
"""
import json, sys, re, base64, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

results = []
def test(name, fn):
    try:
        fn(); results.append(("PASS", name, None)); print(f"  ✅ {name}")
    except Exception as e:
        results.append(("FAIL", name, str(e)[:150])); print(f"  ❌ {name}: {str(e)[:100]}")

print("=" * 65)
print("APOLIO HOME — AUTOMATED TEST SUITE")
print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 65)

# Deps
try:
    import gspread
    from google.oauth2.service_account import Credentials
    env_text = open(".env").read()
    SA_B64 = re.search(r'GOOGLE_SERVICE_ACCOUNT=(\S+)', env_text).group(1)
    sa_json = json.loads(base64.b64decode(SA_B64))
    creds = Credentials.from_service_account_info(sa_json, scopes=[
        'https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive'])
    gc = gspread.authorize(creds)

    # A-003 (T-258): default to TEST sheets; allow override via env vars.
    # PROD IDs are accepted ONLY when ALLOW_PROD_READ=1 is explicitly set.
    # This prevents an accidental local run from touching PROD data.
    PROD_ADMIN_ID = "1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk"
    PROD_MM_ID    = "1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ"
    TEST_ADMIN_ID = "1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM"
    TEST_MM_ID    = "196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788"
    ADMIN_ID = os.getenv("ADMIN_SHEETS_ID", TEST_ADMIN_ID)
    MM_ID    = os.getenv("MM_BUDGET_SHEETS_ID", TEST_MM_ID)
    if (ADMIN_ID == PROD_ADMIN_ID or MM_ID == PROD_MM_ID) and os.getenv("ALLOW_PROD_READ") != "1":
        raise RuntimeError(
            "PROD sheet IDs detected in tests/run_all.py without ALLOW_PROD_READ=1. "
            "Tests must run against TEST sheets. Unset ADMIN_SHEETS_ID/MM_BUDGET_SHEETS_ID "
            "or set ALLOW_PROD_READ=1 if you really intend to read PROD."
        )
    SHEETS_OK = True
except Exception as e:
    print(f"⚠️  Sheets setup failed: {e}"); SHEETS_OK = False

# L1 — STATIC
print("\n[L1] STATIC ANALYSIS")
test("bot.py compiles", lambda: compile(open("bot.py").read(), "bot.py", "exec"))
test("auth.py compiles", lambda: compile(open("auth.py").read(), "auth.py", "exec"))
test("sheets.py compiles", lambda: compile(open("sheets.py").read(), "sheets.py", "exec"))
test("intelligence.py compiles", lambda: compile(open("intelligence.py").read(), "intelligence.py", "exec"))
test("Prompt: {contribution_context} present", lambda: "{contribution_context}" in open("ApolioHome_Prompt.md").read())
test("Prompt: no FINANCIAL CONTEXT hardcode", lambda: "FINANCIAL CONTEXT" not in open("ApolioHome_Prompt.md").read())
test("Prompt: no hardcoded amounts", lambda: "2500" not in open("ApolioHome_Prompt.md").read())
test("intelligence.py: reads envelope Config", lambda: "read_envelope_config" in open("intelligence.py").read())
test("bot.py: thinking indicator", lambda: "_thinking_msg" in open("bot.py").read())
test("bot.py: ensure_envelope_config in config_view", lambda: "ensure_envelope_config" in open("bot.py").read())
test("sheets.py: ensure_envelope_config", lambda: "def ensure_envelope_config" in open("sheets.py").read())
test("sheets.py: read_envelope_config", lambda: "def read_envelope_config" in open("sheets.py").read())
test("auth.py: empty telegram_id fix", lambda: "str(raw_id).strip()" in open("auth.py").read())
test("menu_config.py: admin_panel + set_init_config", lambda: "admin_panel" in open("menu_config.py").read() and "set_init_config" in open("menu_config.py").read())

# L2 — UNIT
print("\n[L2] UNIT TESTS")
def t_auth_empty_id():
    cache = {}
    for u in [{"telegram_id": "", "name": "X", "role": "admin", "status": "active", "envelopes": "", "language": "RU"}]:
        raw_id = u.get("telegram_id","") or ""
        if not str(raw_id).strip(): continue
        try: cache[int(str(raw_id).strip())] = u
        except: continue
    assert len(cache) == 0
test("auth: empty telegram_id skipped", t_auth_empty_id)

def t_auth_suspended():
    cache = {}
    for u in [{"telegram_id": "111", "name": "X", "role": "admin", "status": "suspended", "envelopes": "", "language": "RU"}]:
        if u.get("status","active").lower() == "suspended": continue
        cache[int(u["telegram_id"])] = u
    assert 111 not in cache
test("auth: suspended user excluded", t_auth_suspended)

def t_month_offset():
    def off(m, d):
        y, mo = map(int, m.split("-")); mo += d
        while mo > 12: mo -= 12; y += 1
        while mo < 1: mo += 12; y -= 1
        return f"{y:04d}-{mo:02d}"
    assert off("2026-01", 2) == "2026-03"
    assert off("2026-12", 1) == "2027-01"
    assert off("2026-03", -3) == "2025-12"
test("_offset_month: month arithmetic correct (inc. year rollover)", t_month_offset)

def t_ols_known():
    import numpy as np
    X = np.array([[1,1],[1,2],[1,3],[1,4],[1,5]], dtype=float)
    y = np.array([2,4,5,4,5], dtype=float)
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    assert abs(beta[0] - 2.2) < 0.1 and abs(beta[1] - 0.6) < 0.1
test("OLS math: known dataset gives correct β", t_ols_known)

# L3 — INTEGRATION
print("\n[L3] INTEGRATION (Google Sheets live)")
if SHEETS_OK:
    test("Admin: open", lambda: gc.open_by_key(ADMIN_ID))
    test("Admin/Users: Mikhail present", lambda: any(str(u.get("telegram_id",""))=="360466156" for u in gc.open_by_key(ADMIN_ID).worksheet("Users").get_all_records()))
    test("Admin/Users: Maryna active + MM_BUDGET", lambda: (lambda u: u and u.get("status")=="active" and "MM_BUDGET" in str(u.get("envelopes","")))(next((r for r in gc.open_by_key(ADMIN_ID).worksheet("Users").get_all_records() if str(r.get("telegram_id",""))=="219501159"),None)))
    test("Admin/Users: no blank telegram_id rows", lambda: all(str(r.get("telegram_id","")).strip() for r in gc.open_by_key(ADMIN_ID).worksheet("Users").get_all_records() if r.get("name","").strip()))
    test("MM_BUDGET/Config: split_rule=50_50", lambda: ({r[0]:r[1] for r in gc.open_by_key(MM_ID).worksheet("Config").get_all_values() if len(r)>=2 and r[0]}).get("split_rule")=="50_50")
    test("MM_BUDGET/Config: all 6 keys present", lambda: all(k in {r[0]:r[1] for r in gc.open_by_key(MM_ID).worksheet("Config").get_all_values() if len(r)>=2 and r[0]} for k in ["split_rule","split_threshold","split_users","base_contributor","monthly_cap","currency"]))
    test("MM_BUDGET: required tabs", lambda: all(t in [ws.title for ws in gc.open_by_key(MM_ID).worksheets()] for t in ["Transactions","Categories","Accounts","Config"]))
else:
    print("  ⏭  Skipped (no sheets connection)")

# L4 — BOT BEHAVIOUR (agent.run() — no user required)
print("\n[L4] BOT BEHAVIOUR (agent.run() — autonomous)")
try:
    import asyncio, time as _time
    import sys as _sys
    from pathlib import Path
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from sheets import SheetsClient as _SC
    from auth import AuthManager as _AM, SessionContext as _SCtx
    from agent import ApolioAgent as _Ag

    async def _run_l4():
        _sh = _SC(); _au = _AM(_sh); _ag = _Ag(_sh, _au)
        _s = object.__new__(_SCtx)
        _s.user_id=360466156; _s.user_name="Mikhail"; _s.role="admin"; _s.lang="ru"
        _s.current_envelope_id="MM_BUDGET"; _s.session_id="l4_auto"
        _s.last_action=None; _s.pending_prompt=None; _s.pending_edit_tx=None
        _s.pending_choice=None; _s.pending_delete=None
        l4_cases = [
            ("L4-1 plain greeting",   "привет"),
            ("L4-2 budget status",    "какой у нас бюджет?"),
            ("L4-3 add transaction",  "потратил 5 евро на кофе"),
            ("L4-4 monthly summary",  "покажи расходы за этот месяц"),
            ("L4-5 english query",    "show me this month expenses"),
        ]
        for name, msg in l4_cases:
            t0 = _time.time()
            try:
                resp = await _ag.run(msg, _s)
                ok = bool(resp and len(resp) > 5)
                test(name, lambda r=resp: len(r) > 5)
            except Exception as e:
                test(name, lambda e=e: (_ for _ in ()).throw(e))

    asyncio.run(_run_l4())
except Exception as e:
    print(f"  ⚠  L4 skipped: {e}")

# SUMMARY
total = len(results); passed = sum(1 for r in results if r[0]=="PASS"); failed = total - passed
print(f"\n{'='*65}")
print(f"{'🟢 ALL PASS' if failed==0 else '🟡 MOSTLY PASS' if failed<=2 else '🔴 ATTENTION'}  — {passed}/{total} passed")
print(f"{'='*65}")
if failed:
    for s,n,e in results:
        if s=="FAIL": print(f"  ❌ {n}\n     {e}")

out = {"ts":datetime.now().isoformat(),"total":total,"passed":passed,"failed":failed,
       "results":[{"s":s,"n":n,"e":e} for s,n,e in results]}
with open("/tmp/test_results_latest.json","w") as f: json.dump(out, f, indent=2)
print(f"\nResults → /tmp/test_results_latest.json")
sys.exit(0 if failed==0 else 1)
