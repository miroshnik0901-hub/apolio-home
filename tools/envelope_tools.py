"""Envelope creation tool — creates Google Sheets file from template"""
import json
import re
import uuid
from datetime import datetime
from typing import Any

import gspread
from sheets import SheetsClient, get_credentials  # get_credentials: SA fallback only
from auth import AuthManager, SessionContext


ENVELOPE_TEMPLATE = {
    "Transactions": [
        ["Date", "Amount_Orig", "Currency_Orig", "Category", "Subcategory",
         "Note", "Who", "Amount_EUR", "Type", "Account",
         "ID", "Envelope", "Source", "Wise_ID", "Created_At", "Deleted"]
    ],
    "Summary": [
        ["Month", "Total_Expenses", "Total_Income", "Balance",
         "Top_Category", "Note"]
    ],
    "Categories": [
        ["Category", "Subcategory", "Type"],
    ],
    "FX_Rates": [
        ["Month", "PLN", "UAH", "GBP", "USD", "Source"]
    ],
}

DEFAULT_CATEGORIES_A = [
    ["Housing", "Rent", "Fixed"],
    ["Housing", "Utilities", "Fixed"],
    ["Housing", "Internet", "Fixed"],
    ["Housing", "Maintenance", "Variable"],
    ["Housing", "Insurance", "Fixed"],
    ["Transport", "Car Lease", "Fixed"],
    ["Transport", "Fuel", "Variable"],
    ["Transport", "Parking", "Variable"],
    ["Transport", "Public Transport", "Variable"],
    ["Transport", "Taxi", "Variable"],
    ["Food", "Groceries", "Variable"],
    ["Food", "Restaurants", "Variable"],
    ["Food", "Delivery", "Variable"],
    ["Food", "Coffee", "Variable"],
    ["Health", "Doctor", "Variable"],
    ["Health", "Pharmacy", "Variable"],
    ["Health", "Gym", "Variable"],
    ["Entertainment", "Cinema", "Variable"],
    ["Entertainment", "Travel", "Variable"],
    ["Entertainment", "Subscriptions", "Fixed"],
    ["Personal", "Clothing", "Variable"],
    ["Personal", "Beauty", "Variable"],
    ["Household", "Repairs", "Variable"],
    ["Household", "Electronics", "Variable"],
    ["Other", "Miscellaneous", "Variable"],
    ["Income", "Contribution", "Income"],
    ["Transfer", "Between Accounts", "Transfer"],
]

DEFAULT_CATEGORIES_POLINA = [
    ["School", "Tuition", "Fixed"],
    ["School", "Books", "Variable"],
    ["School", "Supplies", "Variable"],
    ["School", "Trips", "Variable"],
    ["Living", "Food", "Variable"],
    ["Living", "Transport", "Variable"],
    ["Living", "Personal", "Variable"],
    ["Clothing", "Clothes", "Variable"],
    ["Clothing", "Shoes", "Variable"],
    ["Activities", "Sport", "Variable"],
    ["Activities", "Hobbies", "Variable"],
    ["Activities", "Entertainment", "Variable"],
    ["Pocket Money", "Regular", "Variable"],
    ["Pocket Money", "Extra", "Variable"],
    ["Health", "Doctor", "Variable"],
    ["Health", "Pharmacy", "Variable"],
    ["Other", "Miscellaneous", "Variable"],
]


async def tool_list_envelopes(params: dict, session: SessionContext,
                              sheets: SheetsClient, auth: AuthManager) -> Any:
    """Return all active envelopes with Google Sheets links."""
    envelopes = sheets.list_envelopes_with_links()
    if not envelopes:
        return {"status": "ok", "envelopes": [], "message": "No envelopes registered yet."}
    return {
        "status": "ok",
        "count": len(envelopes),
        "envelopes": envelopes,
    }


async def tool_create_envelope(params: dict, session: SessionContext,
                                sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.is_admin(session.user_id):
        return {"error": "Admin only."}

    name = params["name"]
    currency = params.get("currency", "EUR")
    monthly_cap = params.get("monthly_cap", 0)
    split_rule = params.get("split_rule", "solo")
    owner_id = params.get("owner_id") or session.user_id
    viewer_ids = params.get("viewer_ids", [])

    # Generate envelope ID from name — ASCII only, no Cyrillic/special chars
    raw_id = name.upper().replace(" ", "_")
    env_id = re.sub(r"[^A-Z0-9_]", "", raw_id)[:10].strip("_") or "ENV"

    # Create Google Sheets file in Mikhail's Drive via OAuth (not service account).
    # This ensures the file appears in his Drive folder, not the SA's hidden storage.
    # Falls back to service account if OAuth env vars are not set.
    try:
        file_id = sheets.create_spreadsheet_as_owner(f"Apolio Home — {name}")
        creds = get_credentials()
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(file_id)
    except RuntimeError:
        # OAuth not configured — fall back to service account
        creds = get_credentials()
        gc = gspread.authorize(creds)
        spreadsheet = gc.create(f"Apolio Home — {name}")

    # Build sheets from template
    for sheet_name, headers in ENVELOPE_TEMPLATE.items():
        try:
            ws = spreadsheet.add_worksheet(sheet_name, rows=1000, cols=20)
        except Exception:
            ws = spreadsheet.worksheet(sheet_name)
        ws.update(headers)

    # Delete default Sheet1
    try:
        spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
    except Exception:
        pass

    # Add default categories based on name hint
    ws_cat = spreadsheet.worksheet("Categories")
    if "polina" in name.lower():
        ws_cat.update([DEFAULT_CATEGORIES_POLINA[0]] + DEFAULT_CATEGORIES_POLINA,
                      "A2")
    else:
        ws_cat.update([DEFAULT_CATEGORIES_A[0]] + DEFAULT_CATEGORIES_A, "A2")

    settings = {
        "monthly_cap": monthly_cap,
        "split_rule": split_rule,
        "currency": currency,
    }

    sheets.register_envelope(
        envelope_id=env_id,
        name=name,
        file_id=spreadsheet.id,
        owner_id=owner_id,
        settings=settings,
    )

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet.id}"
    return {
        "status": "ok",
        "envelope_id": env_id,
        "file_id": spreadsheet.id,
        "url": url,
        "message": (
            f"✓ Envelope '{name}' created.\n"
            f"ID: {env_id}\n"
            f"File: {url}"
        ),
    }
