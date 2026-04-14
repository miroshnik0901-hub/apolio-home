#!/usr/bin/env python3
"""
T-221: Post-PROD deploy verification script.
Run AFTER every `git push main`.

RULES:
  ✅ Verify tab/header EXISTENCE — always safe
  ✅ Fix EMPTY header row (Row 1) — safe, no data loss
  ✅ CREATE missing config tabs (BotMenu, UserAliases, CategoryAliases) — safe
  ⚠️  BotMenu reset_to_defaults() — config-only, no user data
  ❌ NEVER modify data rows (transactions, FX rates, Envelope settings)
  ❌ Any data change beyond structure needs Mikhail confirmation

Usage: python3 scripts/sync_prod_after_deploy.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from sheets import SheetsClient
import menu_config as mc

sheets = SheetsClient()

PROD_ADMIN  = "1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk"
PROD_BUDGET = "1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ"

TRANSACTIONS_HEADERS = [
    "Date", "Amount_Orig", "Currency_Orig", "Category", "Subcategory",
    "Note", "Who", "Amount_EUR", "Type", "Account", "ID", "Envelope",
    "Source", "Wise_ID", "Created_At", "Deleted"
]

results = []

def check(label, ok, note=""):
    status = "✅" if ok else "❌"
    msg = f"  {status} {label}"
    if note:
        msg += f"\n     → {note}"
    print(msg)
    results.append((ok, label))
    return ok

print("=== Post-PROD deploy verification ===")
print(f"PROD Admin:  {PROD_ADMIN[:30]}...")
print(f"PROD Budget: {PROD_BUDGET[:30]}...\n")

# ── 1. BotMenu (config-only, no user data) ──────────────────────────────────
print("1. BotMenu — config tab, no user data")
try:
    ok = mc.reset_to_defaults(sheets._gc, PROD_ADMIN)
    check("BotMenu reset in PROD Admin", ok)
except Exception as e:
    check("BotMenu reset", False, str(e)[:80])

# ── 2. Transactions headers (Row 1 only, data rows untouched) ───────────────
print("\n2. Transactions sheet headers (Row 1 only — data rows NOT touched)")
try:
    from sheets import _sheets_retry
    wb = sheets._gc.open_by_key(PROD_BUDGET)
    ws_t = wb.worksheet("Transactions")
    headers = ws_t.row_values(1)
    if not headers or "ID" not in headers:
        print(f"   ⚠️  Current headers: {headers[:6]}")
        print(f"   This only updates Row 1 (column names). All data rows are preserved.")
        confirm = input("   Fix header row? [y/N]: ").strip().lower()
        if confirm == "y":
            _sheets_retry(ws_t.update, "A1:P1", [TRANSACTIONS_HEADERS])
            check("Transactions headers fixed (Row 1 only, data untouched)", True)
        else:
            check("Transactions headers NOT fixed (skipped)", False,
                  "⚠️ Bulk delete and edit may fail without correct headers")
    else:
        id_col = headers.index("ID") + 1
        check(f"Transactions headers OK (ID at col {id_col}, {len(headers)} cols)", True)
except Exception as e:
    check("Transactions tab access", False, str(e)[:80])

# ── 3. UserAliases tab (creates only if missing, never overwrites) ───────────
print("\n3. UserAliases tab (creates with seed if missing, never overwrites)")
try:
    # SheetsClient already uses correct admin from env — just call directly
    aliases = sheets.get_user_aliases()
    check(f"UserAliases tab OK ({len(aliases)} aliases)", len(aliases) > 0)
except Exception as e:
    check("UserAliases tab", False, str(e)[:80])

# ── 4. CategoryAliases tab (creates only if missing, never overwrites) ───────
print("\n4. CategoryAliases tab (creates with seed if missing, never overwrites)")
try:
    cat_aliases = sheets.get_category_aliases()
    check(f"CategoryAliases tab OK ({len(cat_aliases)} aliases)", len(cat_aliases) > 0)
except Exception as e:
    check("CategoryAliases tab", False, str(e)[:80])

# ── 5. FX_Rates — read-only existence check (DATA NOT TOUCHED) ──────────────
print("\n5. FX_Rates tab — read-only check (no data changes)")
try:
    fx = sheets.get_fx_rates(PROD_BUDGET)
    if fx:
        from datetime import datetime
        latest = max((r.get("Month","") for r in fx), default="")
        cur_m = datetime.now().strftime("%Y-%m")
        if latest < cur_m:
            check(f"FX_Rates exists (latest={latest})", True,
                  f"⚠️ Rates may be outdated vs {cur_m} — update MANUALLY in PROD Budget → FX_Rates")
        else:
            check(f"FX_Rates OK (latest={latest}, {len(fx)} rows)", True)
    else:
        check("FX_Rates tab empty", False,
              "⚠️ Add rates manually — DO NOT run automated data write without Mikhail confirmation")
except Exception as e:
    check("FX_Rates tab", False, str(e)[:80])

# ── 6. Envelope Config — read-only check (no data changes) ──────────────────
print("\n6. Envelope Config — read-only check (data NOT touched)")
try:
    cfg = sheets.read_envelope_config(PROD_BUDGET)
    has_split = "split_users" in cfg
    has_min   = any("min_" in k for k in cfg)
    has_cap   = "monthly_cap" in cfg
    check(
        f"Config OK (split_users={'✓' if has_split else '✗'}, "
        f"min_user={'✓' if has_min else '✗'}, "
        f"monthly_cap={'✓' if has_cap else '✗'})",
        has_split and has_cap,
        "" if has_split else "⚠️ Missing split_users — contributions won't work"
    )
except Exception as e:
    check("Envelope Config", False, str(e)[:80])

# ── 7. Admin sheets structure (Users, Envelopes tabs) — read-only ─────────────
print("\n7. Admin structure — read-only check")
try:
    users = sheets.get_users()
    envs  = sheets.get_envelopes()
    check(f"Users tab OK ({len(users)} users)", len(users) > 0)
    check(f"Envelopes tab OK ({len(envs)} envelopes)", len(envs) > 0)
except Exception as e:
    check("Admin structure", False, str(e)[:80])

# ── Summary ──────────────────────────────────────────────────────────────────
passed = sum(1 for ok, _ in results if ok)
total  = len(results)
print(f"\n{'='*55}")
print(f"{'✅ ALL OK' if passed == total else '⚠️  ISSUES FOUND'}: {passed}/{total} checks passed")
print("=" * 55)
if passed < total:
    print("\nFailed/warned checks:")
    for ok, label in results:
        if not ok:
            print(f"  ❌ {label}")
print("\nRun after every: git push main")
