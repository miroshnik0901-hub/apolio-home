"""
Apolio Home — Sheets Restructure Script (v2)
Run once after deploying v2 code.

What this does:
1. MM Budget — Transactions: reorder columns to new layout, add Amount_EUR formula,
   hide technical columns K-P, freeze row 1 + col A, set dropdowns, column widths
2. MM Budget — Summary: rebuild with proper SUMPRODUCT formulas for all months 2026
3. MM Budget — add Accounts sheet
4. Admin — Config: add Description column, fill descriptions
5. Admin — Users: add language/status/notes/updated_at columns, update Mikhail row
6. Admin — Audit_Log: bold headers, freeze row 1

Run from the apolio-home directory:
    python setup_sheets_v2.py
"""
import os
import json
import base64
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build as google_build

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

MM_BUDGET_ID = "1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ"
ADMIN_ID = "1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk"


def get_creds():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT", "")
    creds_dict = json.loads(base64.b64decode(raw))
    return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)


def get_sheets_service(creds):
    return google_build("sheets", "v4", credentials=creds, cache_discovery=False)


def batch_update(service, spreadsheet_id, requests):
    if not requests:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    print(f"  Applied {len(requests)} request(s)")


# ── 1. MM Budget — Transactions sheet ────────────────────────────────────────

def restructure_transactions(gc, service):
    print("\n[1] Restructuring MM Budget Transactions sheet...")
    wb = gc.open_by_key(MM_BUDGET_ID)

    try:
        ws = wb.worksheet("Transactions")
    except Exception:
        ws = wb.add_worksheet("Transactions", rows=1000, cols=20)

    # New column order
    NEW_HEADERS = [
        "Date", "Amount_Orig", "Currency_Orig", "Category", "Subcategory",
        "Note", "Who", "Amount_EUR", "Type", "Account",
        "ID", "Envelope", "Source", "Wise_ID", "Created_At", "Deleted"
    ]

    # Read existing data
    existing = ws.get_all_values()
    old_headers = existing[0] if existing else []
    old_data = existing[1:] if len(existing) > 1 else []

    print(f"  Old headers: {old_headers}")
    print(f"  Rows of data: {len(old_data)}")

    # Remap existing data to new column order
    def remap_row(row, old_h, new_h):
        """Map a row from old column order to new."""
        old_map = {h: i for i, h in enumerate(old_h)}
        new_row = []
        for h in new_h:
            old_idx = old_map.get(h)
            new_row.append(row[old_idx] if old_idx is not None and old_idx < len(row) else "")
        return new_row

    remapped = [NEW_HEADERS]
    for row in old_data:
        if any(row):  # skip empty rows
            remapped.append(remap_row(row, old_headers, NEW_HEADERS))

    # Clear and rewrite
    ws.clear()
    if remapped:
        ws.update(remapped, "A1")
    print(f"  Written {len(remapped)} rows with new column order")

    # Get sheet ID for API calls
    sheet_id = None
    meta = service.spreadsheets().get(spreadsheetId=MM_BUDGET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Transactions":
            sheet_id = s["properties"]["sheetId"]
            break

    requests = []

    # ── Amount_EUR formula (col H = index 7) ──────────────────────────────
    # Set formula in H2:H1000
    formula = '=IF(C2="EUR",B2,IFERROR(B2/VLOOKUP(TEXT(A2,"YYYY-MM"),FX_Rates!$A:$F,MATCH(C2,FX_Rates!$1:$1,0),0),"FX_MISSING"))'
    ws.update([[formula]] * 999, "H2:H1000", value_input_option="USER_ENTERED")
    print("  Amount_EUR formula set in H2:H1000")

    # ── Freeze row 1 and column A ──────────────────────────────────────────
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 1},
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    })

    # ── Hide columns K-P (indices 10-15) ──────────────────────────────────
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": 10,  # K
                "endIndex": 16,    # P+1
            },
            "properties": {"hiddenByUser": True},
            "fields": "hiddenByUser",
        }
    })

    # ── Column widths (A-H) ────────────────────────────────────────────────
    widths = [120, 100, 80, 150, 150, 250, 100, 120]
    for i, w in enumerate(widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })

    # ── Bold header row ────────────────────────────────────────────────────
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold",
        }
    })

    # ── Data validation: Currency (col C = index 2) ────────────────────────
    requests.append({
        "setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000,
                      "startColumnIndex": 2, "endColumnIndex": 3},
            "rule": {
                "condition": {"type": "ONE_OF_LIST",
                              "values": [{"userEnteredValue": v} for v in ["EUR", "PLN", "UAH", "GBP", "USD"]]},
                "showCustomUi": True,
                "strict": False,
            },
        }
    })

    # ── Data validation: Who (col G = index 6) ────────────────────────────
    requests.append({
        "setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000,
                      "startColumnIndex": 6, "endColumnIndex": 7},
            "rule": {
                "condition": {"type": "ONE_OF_LIST",
                              "values": [{"userEnteredValue": v} for v in ["Mikhail", "Maryna", "Joint"]]},
                "showCustomUi": True,
                "strict": False,
            },
        }
    })

    # ── Data validation: Type (col I = index 8) ───────────────────────────
    requests.append({
        "setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000,
                      "startColumnIndex": 8, "endColumnIndex": 9},
            "rule": {
                "condition": {"type": "ONE_OF_LIST",
                              "values": [{"userEnteredValue": v} for v in ["expense", "income", "transfer"]]},
                "showCustomUi": True,
                "strict": False,
            },
        }
    })

    # ── Conditional formatting: FX_MISSING in H → light red ───────────────
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 1000,
                            "startColumnIndex": 0, "endColumnIndex": 16}],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ",
                                  "values": [{"userEnteredValue": "FX_MISSING"}]},
                    "format": {"backgroundColor": {"red": 1.0, "green": 0.8, "blue": 0.8}},
                },
            },
            "index": 0,
        }
    })

    batch_update(service, MM_BUDGET_ID, requests)
    print("  Transactions sheet restructured ✓")


# ── 2. MM Budget — Summary sheet ─────────────────────────────────────────────

def rebuild_summary(gc, service):
    print("\n[2] Rebuilding Summary sheet...")
    wb = gc.open_by_key(MM_BUDGET_ID)

    try:
        ws = wb.worksheet("Summary")
    except Exception:
        ws = wb.add_worksheet("Summary", rows=50, cols=15)

    ws.clear()

    CATEGORIES = ["Housing", "Food", "Transport", "Health", "Entertainment",
                   "Personal", "Household", "Groceries", "Other"]

    # T-132: Formulas use TEXT() for date matching (dates are serials, not strings)
    # and <>"TRUE" for Deleted filter (empty cells are not "FALSE")
    _R = "Transactions!$A$2:$A$1000"   # Date
    _H = "Transactions!$H$2:$H$1000"   # Amount_EUR
    _I = "Transactions!$I$2:$I$1000"   # Type
    _P = "Transactions!$P$2:$P$1000"   # Deleted
    _D = "Transactions!$D$2:$D$1000"   # Category

    headers = (["Month", "Total_Expenses", "Total_Income", "Balance"]
               + CATEGORIES + ["Cap", "Remaining", "Used_%"])
    rows = [headers]

    for month_num in range(1, 13):
        month_str = f"2026-{month_num:02d}"
        _M = f'(TEXT({_R},"yyyy-mm")=A{len(rows)+1})'
        _ND = f'({_P}<>"TRUE")'
        total_exp = f'=SUMPRODUCT({_M}*{_ND}*({_I}="expense")*{_H})'
        total_inc = f'=SUMPRODUCT({_M}*{_ND}*({_I}="income")*{_H})'
        r = len(rows) + 1
        balance = f"=C{r}-B{r}"

        cat_cells = []
        for cat in CATEGORIES:
            cat_cells.append(
                f'=SUMPRODUCT({_M}*({_D}="{cat}")*{_ND}*({_I}="expense")*{_H})'
            )

        cap_f = '=VLOOKUP("monthly_cap",Config!A:B,2,FALSE)'
        remaining_f = f"=N{r}-B{r}"
        used_pct_f = f'=IF(N{r}>0,ROUND(B{r}/N{r}*100,1),0)'

        rows.append(["'" + month_str, total_exp, total_inc, balance]
                    + cat_cells + [cap_f, remaining_f, used_pct_f])

    ws.update(rows, "A1", value_input_option="USER_ENTERED")

    # Get sheet_id and bold headers
    sheet_id = None
    meta = service.spreadsheets().get(spreadsheetId=MM_BUDGET_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Summary":
            sheet_id = s["properties"]["sheetId"]
            break

    if sheet_id is not None:
        batch_update(service, MM_BUDGET_ID, [{
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        }])

    print("  Summary sheet rebuilt with 12-month formulas ✓")


# ── 3. Admin — Accounts sheet (Joint/Personal) ────────────────────────────────
# Accounts are global config in Admin, not per-budget envelope.

def setup_accounts(gc, service):
    print("\n[3] Setting up Admin Accounts sheet...")
    wb = gc.open_by_key(os.environ["ADMIN_SHEETS_ID"])

    try:
        ws = wb.worksheet("Accounts")
        print("  Admin Accounts sheet already exists, skipping")
        return
    except Exception:
        ws = wb.add_worksheet("Accounts", rows=20, cols=4)

    headers = ["Name", "Type", "Description", "Active"]
    data = [
        headers,
        ["Joint",    "Joint",    "Спільний бюджет / Общий бюджет",    "TRUE"],
        ["Personal", "Personal", "Особистий рахунок / Личный счёт", "TRUE"],
    ]
    ws.update(data, "A1")
    print("  Admin Accounts sheet created (Joint + Personal) ✓")


# ── 4. Admin — Config sheet ────────────────────────────────────────────────────

def update_admin_config(gc, service):
    print("\n[4] Updating Admin Config sheet...")
    wb = gc.open_by_key(ADMIN_ID)
    ws = wb.worksheet("Config")

    existing = ws.get_all_values()
    existing_keys = {row[0] for row in existing if row}

    CONFIG_ENTRIES = [
        ("alert_threshold_pct", "80",        "Alert when spending reaches X% of monthly budget"),
        ("default_currency",    "EUR",        "Default currency for new transactions"),
        ("fx_fallback",         "nearest",    "FX rate fallback: nearest or previous month"),
        ("budget_MM_BUDGET_monthly", "2500",  "Monthly cap for MM Budget envelope"),
        ("default_envelope",    "MM_BUDGET",  "Default envelope for admin user"),
        ("bot_version",         "2.0",        "Current bot version"),
    ]

    # Add Description header if not present
    headers = ws.row_values(1) if existing else []
    if len(headers) < 3 or headers[2] != "Description":
        ws.update_cell(1, 3, "Description")

    # Ensure all config keys exist
    for key, value, desc in CONFIG_ENTRIES:
        if key not in existing_keys:
            ws.append_row([key, value, desc])
        else:
            # Add description if missing
            rows = ws.get_all_values()
            for i, row in enumerate(rows):
                if row and row[0] == key:
                    if len(row) < 3 or not row[2]:
                        ws.update_cell(i + 1, 3, desc)
                    break

    # Get sheet_id and bold header row
    sheet_id = None
    meta = service.spreadsheets().get(spreadsheetId=ADMIN_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Config":
            sheet_id = s["properties"]["sheetId"]
            break

    if sheet_id is not None:
        batch_update(service, ADMIN_ID, [{
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        }])

    print("  Admin Config updated ✓")


# ── 5. Admin — Users sheet ─────────────────────────────────────────────────────

def update_admin_users(gc, service):
    print("\n[5] Updating Admin Users sheet...")
    wb = gc.open_by_key(ADMIN_ID)
    ws = wb.worksheet("Users")

    existing = ws.get_all_values()
    headers = existing[0] if existing else []

    # Expand sheet column count if needed (gspread can't write beyond existing grid size)
    NEW_COLUMNS = ["language", "status", "notes", "updated_at"]
    needed_cols = len(headers) + len([c for c in NEW_COLUMNS if c not in headers])
    ws_meta = service.spreadsheets().get(
        spreadsheetId=ADMIN_ID,
        ranges=["Users"],
        fields="sheets.properties",
    ).execute()
    for s in ws_meta.get("sheets", []):
        if s["properties"]["title"] == "Users":
            current_cols = s["properties"]["gridProperties"]["columnCount"]
            if needed_cols > current_cols:
                sheet_id_expand = s["properties"]["sheetId"]
                batch_update(service, ADMIN_ID, [{
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id_expand,
                            "gridProperties": {"columnCount": needed_cols + 2},
                        },
                        "fields": "gridProperties.columnCount",
                    }
                }])
            break

    # Reload headers after potential expansion
    headers = ws.row_values(1)

    # Add missing columns
    for col in NEW_COLUMNS:
        if col not in headers:
            col_idx = len(headers) + 1
            ws.update_cell(1, col_idx, col)
            headers.append(col)

    # Update Mikhail's row: set language=RU, status=active, notes=Owner
    rows = ws.get_all_records()
    for i, row in enumerate(rows):
        if str(row.get("telegram_id")) == "360466156":
            row_num = i + 2  # 1-indexed + header
            col_map = {h: j + 1 for j, h in enumerate(ws.row_values(1))}
            if "language" in col_map and not row.get("language"):
                ws.update_cell(row_num, col_map["language"], "RU")
            if "status" in col_map and not row.get("status"):
                ws.update_cell(row_num, col_map["status"], "active")
            if "notes" in col_map and not row.get("notes"):
                ws.update_cell(row_num, col_map["notes"], "Owner")
            if "updated_at" in col_map:
                ws.update_cell(row_num, col_map["updated_at"], datetime.utcnow().isoformat())
            break

    # Bold header row
    sheet_id = None
    meta = service.spreadsheets().get(spreadsheetId=ADMIN_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Users":
            sheet_id = s["properties"]["sheetId"]
            break

    if sheet_id is not None:
        batch_update(service, ADMIN_ID, [
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                    "fields": "userEnteredFormat.textFormat.bold",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
        ])

    print("  Admin Users updated ✓")


# ── 6. Admin — Audit_Log formatting ───────────────────────────────────────────

def format_audit_log(gc, service):
    print("\n[6] Formatting Audit_Log sheet...")
    wb = gc.open_by_key(ADMIN_ID)

    try:
        ws = wb.worksheet("Audit_Log")
    except Exception:
        print("  Audit_Log sheet not found, skipping")
        return

    sheet_id = None
    meta = service.spreadsheets().get(spreadsheetId=ADMIN_ID).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Audit_Log":
            sheet_id = s["properties"]["sheetId"]
            break

    if sheet_id is None:
        return

    requests = [
        # Bold + freeze header
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Timestamp column width 200px
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 200},
                "fields": "pixelSize",
            }
        },
    ]

    batch_update(service, ADMIN_ID, requests)
    print("  Audit_Log formatted ✓")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Apolio Home — Sheets Restructure v2")
    print("=" * 50)

    creds = get_creds()
    gc = gspread.authorize(creds)
    service = get_sheets_service(creds)

    restructure_transactions(gc, service)
    rebuild_summary(gc, service)
    setup_accounts(gc, service)
    update_admin_config(gc, service)
    update_admin_users(gc, service)
    format_audit_log(gc, service)

    print("\n" + "=" * 50)
    print("All done! ✓")
    print("\nNext steps:")
    print("  1. Open MM Budget in browser and verify column layout")
    print("  2. Add a test row manually (columns A-G only)")
    print("  3. Verify H (Amount_EUR) fills via formula")
    print("  4. Check Summary tab has 2026 monthly formulas")


if __name__ == "__main__":
    main()
