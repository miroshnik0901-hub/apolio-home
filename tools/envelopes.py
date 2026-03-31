import gspread
from datetime import datetime

from sheets import SheetsClient
from auth import AuthManager, SessionContext


# Envelope Google Sheets template — sheet structure
ENVELOPE_SHEETS = [
    {
        "name": "Transactions",
        "headers": [
            "ID", "Date", "Amount_Orig", "Currency_Orig", "Amount_EUR",
            "Category", "Subcategory", "Who", "Account", "Type",
            "Note", "Source", "Wise_ID", "Created_At", "Deleted"
        ],
    },
    {
        "name": "Summary",
        "headers": ["Month", "Total_Expenses", "Total_Income", "Balance", "Budget_Cap", "Pct_Used"],
    },
    {
        "name": "Categories",
        "headers": ["Category", "Subcategory", "Type", "Fixed"],
    },
    {
        "name": "FX_Rates",
        "headers": ["Month", "PLN", "UAH", "GBP", "USD", "Source"],
    },
    {
        "name": "Accounts",
        "headers": ["Account", "Owner", "Currency", "Description"],
    },
    {
        "name": "Config",
        "headers": ["Key", "Value"],
    },
]


async def tool_create_envelope(params: dict, session: SessionContext,
                               sheets: SheetsClient, auth: AuthManager) -> dict:
    if not auth.is_admin(session.user_id):
        raise PermissionError("Admin access required")

    name = params["name"]
    envelope_id = params.get("envelope_id") or _slugify(name)
    currency = params.get("currency", "EUR")
    monthly_cap = params.get("monthly_cap", 0)
    split_rule = params.get("split_rule", "solo")
    owner_id = params.get("owner_id", session.user_id)

    gc = sheets._admin.client

    # Create new Google Sheets file using Mikhail's OAuth (avoids service account Drive quota)
    if hasattr(sheets, "create_spreadsheet_as_owner"):
        sheet_id = sheets.create_spreadsheet_as_owner(f"Apolio Home — {name}")
        wb = gc.open_by_key(sheet_id)
    else:
        wb = gc.create(f"Apolio Home — {name}")
        sheet_id = wb.id

    # Build sheets from template
    existing = [ws.title for ws in wb.worksheets()]
    for sheet_def in ENVELOPE_SHEETS:
        if sheet_def["name"] not in existing:
            ws = wb.add_worksheet(title=sheet_def["name"], rows=1000, cols=len(sheet_def["headers"]) + 2)
        else:
            ws = wb.worksheet(sheet_def["name"])
        ws.update([sheet_def["headers"]], "A1")

    # Remove default "Sheet1" if present
    try:
        wb.del_worksheet(wb.worksheet("Sheet1"))
    except Exception:
        pass

    # Seed Config sheet
    config_ws = wb.worksheet("Config")
    config_ws.append_row(["envelope_id", envelope_id])
    config_ws.append_row(["name", name])
    config_ws.append_row(["currency", currency])
    config_ws.append_row(["monthly_cap", str(monthly_cap)])
    config_ws.append_row(["split_rule", split_rule])
    config_ws.append_row(["created_at", datetime.utcnow().isoformat()])
    config_ws.append_row(["alert_threshold_pct", "80"])

    # Register in Admin (use file_id key to match Envelopes sheet column)
    sheets.register_envelope(
        envelope_id=envelope_id,
        name=name,
        file_id=sheet_id,
        owner_id=owner_id,
        settings={
            "currency": currency,
            "monthly_cap": monthly_cap,
            "split_rule": split_rule,
        }
    )

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    sheets.write_audit(
        session.user_id, session.user_name, "create_envelope", envelope_id,
        f"name={name} sheet={sheet_id}"
    )

    return {
        "ok": True,
        "envelope_id": envelope_id,
        "name": name,
        "sheet_id": sheet_id,
        "sheet_url": sheet_url,
    }


def _slugify(name: str) -> str:
    import re
    import unicodedata
    # Transliterate common Cyrillic/accented characters to ASCII equivalents
    _TRANSLIT = {
        'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh',
        'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o',
        'п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts',
        'ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu',
        'я':'ya',
        # Ukrainian extras
        'і':'i','ї':'yi','є':'ye','ґ':'g',
    }
    result = ""
    for ch in name.lower():
        if ch in _TRANSLIT:
            result += _TRANSLIT[ch]
        elif ch.isascii() and (ch.isalnum() or ch in (' ', '_', '-')):
            result += ch
        else:
            # Try Unicode NFKD decomposition as fallback
            decomposed = unicodedata.normalize('NFKD', ch).encode('ascii', 'ignore').decode()
            result += decomposed if decomposed else '_'
    slug = re.sub(r"[^a-zA-Z0-9]", "_", result).upper()
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:10] or "ENV"
