#!/usr/bin/env python3
"""
T-221: Post-PROD deploy sync script.
Run AFTER every `git push main` to sync Admin Sheets + Budget headers.
Usage: python3 scripts/sync_prod_after_deploy.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from sheets import SheetsClient
import menu_config as mc

sheets = SheetsClient()

PROD_ADMIN = "1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk"
PROD_BUDGET = "1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ"

HEADERS = ["Date", "Amount_Orig", "Currency_Orig", "Category", "Subcategory",
           "Note", "Who", "Amount_EUR", "Type", "Account", "ID", "Envelope",
           "Source", "Wise_ID", "Created_At", "Deleted"]

def check(label, ok):
    status = "✅" if ok else "❌"
    print(f"  {status} {label}")
    return ok

all_ok = True

print("=== Post-PROD deploy sync ===\n")

# 1. Sync BotMenu in PROD Admin
print("1. Syncing BotMenu...")
ok = mc.reset_to_defaults(sheets._gc, PROD_ADMIN)
all_ok = check("BotMenu reset in PROD Admin", ok) and all_ok

# 2. Verify/set PROD Budget Transactions headers
print("\n2. Verifying PROD Budget Transactions headers...")
try:
    from sheets import _sheets_retry
    ws = sheets._env_sheets(PROD_BUDGET)._ws("Transactions")
    h = ws.row_values(1)
    if "ID" not in h:
        ws.update("A1:P1", [HEADERS])
        check("PROD Budget headers set (was missing ID)", True)
    else:
        check(f"PROD Budget headers OK (ID at col {h.index('ID')+1})", True)
except Exception as e:
    all_ok = check(f"PROD Budget headers: {e}", False) and all_ok

# 3. Ensure UserAliases tab in PROD Admin
print("\n3. Ensuring UserAliases tab...")
try:
    sheets.get_user_aliases()
    check("UserAliases tab exists in PROD Admin", True)
except Exception as e:
    all_ok = check(f"UserAliases: {e}", False) and all_ok

# 4. Ensure CategoryAliases tab
print("\n4. Ensuring CategoryAliases tab...")
try:
    sheets.get_category_aliases()
    check("CategoryAliases tab exists in PROD Admin", True)
except Exception as e:
    all_ok = check(f"CategoryAliases: {e}", False) and all_ok

# 5. Check FX_Rates in PROD Budget
print("\n5. Checking FX_Rates tab...")
try:
    fx = sheets.get_fx_rates(PROD_BUDGET)
    check(f"FX_Rates OK ({len(fx)} rows)", len(fx) > 0)
except Exception as e:
    all_ok = check(f"FX_Rates: {e}", False) and all_ok

print(f"\n{'✅ ALL OK' if all_ok else '❌ SOME CHECKS FAILED'}")
print("Run this script after every: git push main")
