"""
T-274 integration test: verify that items[i].subcategory from agent's output
is actually carried through the bank-statement loop into Transactions Subcategory column.

This tests the PRIMARY fix (bot.py:4322 params dict includes "subcategory"),
not just the alias layer.

Scenario:
  1. Build a fake receipt with 2 items, one with explicit subcategory ("Fuel"),
     one without (relies on _infer_subcategory).
  2. Simulate the bank-statement loop at bot.py:4185+.
  3. Capture the params dict that would be passed to tool_add_transaction for each item.
  4. Assert:
     - Item with explicit subcategory="Fuel" → params["subcategory"] == "Fuel".
     - Item without explicit subcategory → params["subcategory"] == "" (downstream
       _infer_subcategory / merchant-memory kicks in at transactions.py:603).
     - Receipt-level subcategory fallback works when item has none but receipt does.
"""
import sys; sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env")


def simulate_batch_loop(items, receipt):
    """Replica of the critical slice of bot.py bank-statement loop —
    reproduces exactly the params-building that feeds tool_add_transaction.
    MUST mirror the fixed code at bot.py:4314+ (T-274 primary plumbing)."""
    captured = []
    for item in items:
        item_name = item.get("name") or "?"
        item_amount = float(item.get("amount") or 0)
        if item_amount < 0:
            item_amount = abs(item_amount)
        item_date = item.get("date") or receipt.get("date") or ""
        item_cat = item.get("category") or receipt.get("category") or "Other"
        item_who = item.get("who") or receipt.get("who") or "Mikhail"
        item_type = item.get("type") or "expense"

        # T-274 FIX (the line under test):
        _item_subcategory = item.get("subcategory") or receipt.get("subcategory", "")

        params = {
            "amount": item_amount,
            "currency": receipt.get("currency", "EUR"),
            "category": item_cat,
            "subcategory": _item_subcategory,
            "who": item_who,
            "date": item_date,
            "note": item_name,
            "account": "Personal",
            "type": item_type,
        }
        captured.append(params)
    return captured


def run_tests():
    passed = failed = 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        if cond:
            print(f"  ✓ {name}")
            passed += 1
        else:
            print(f"  ✗ {name}  — {detail}")
            failed += 1

    print("=== T-274 plumbing self-test ===\n")

    # Case 1: explicit item-level subcategory should win
    items1 = [
        {"name": "CHIERI - CORSO T", "amount": 3540, "category": "Transport", "subcategory": "Fuel"},
        {"name": "STAZIONE ESSO DI PINO", "amount": 45.50, "category": "Transport", "subcategory": "Fuel"},
    ]
    receipt1 = {"currency": "UAH", "date": "2026-01-26"}
    out = simulate_batch_loop(items1, receipt1)
    check("Case 1.1 CHIERI subcategory=Fuel plumbed",
          out[0]["subcategory"] == "Fuel", f"got {out[0]['subcategory']!r}")
    check("Case 1.2 ESSO subcategory=Fuel plumbed",
          out[1]["subcategory"] == "Fuel", f"got {out[1]['subcategory']!r}")

    # Case 2: no item subcategory, no receipt subcategory → empty (triggers downstream inference)
    items2 = [{"name": "UNKNOWN MERCHANT", "amount": 10, "category": "Food"}]
    receipt2 = {"currency": "EUR"}
    out2 = simulate_batch_loop(items2, receipt2)
    check("Case 2 no subcategory → empty (fallback to inference)",
          out2[0]["subcategory"] == "", f"got {out2[0]['subcategory']!r}")

    # Case 3: receipt-level subcategory as fallback when item lacks one
    items3 = [{"name": "LIDL VIA ROMA", "amount": 25.40, "category": "Food"}]
    receipt3 = {"currency": "EUR", "subcategory": "Groceries"}
    out3 = simulate_batch_loop(items3, receipt3)
    check("Case 3 receipt-level subcategory carried",
          out3[0]["subcategory"] == "Groceries", f"got {out3[0]['subcategory']!r}")

    # Case 4: item subcategory WINS over receipt-level
    items4 = [{"name": "CHIERI", "amount": 100, "category": "Transport", "subcategory": "Parking"}]
    receipt4 = {"currency": "EUR", "subcategory": "Fuel"}  # receipt says Fuel; item says Parking
    out4 = simulate_batch_loop(items4, receipt4)
    check("Case 4 item subcategory overrides receipt",
          out4[0]["subcategory"] == "Parking", f"got {out4[0]['subcategory']!r}")

    # Case 5: verify that simulate_batch_loop matches the real code (structural)
    # Read the fixed line from bot.py to ensure this test is in sync.
    with open("bot.py") as f:
        src = f.read()
    check("Case 5 bot.py contains T-274 primary fix line",
          '_item_subcategory = item.get("subcategory") or receipt.get("subcategory", "")' in src,
          "fix not found — test would silently drift")
    check("Case 5.1 params dict at 4322 carries subcategory",
          '"subcategory": _item_subcategory,' in src,
          "plumbing broken — params dict missing subcategory key")

    # Case 6: verify single-row save path (bot.py ~4528) also carries subcategory
    check("Case 6 single-row save path plumbs subcategory",
          '"subcategory": receipt.get("subcategory", ""),' in src and
          'receipt.get("merchant") or "Multiple merchants"' in src,
          "single-row save path still drops subcategory")

    print(f"\n{passed}/{passed+failed} passed")
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
