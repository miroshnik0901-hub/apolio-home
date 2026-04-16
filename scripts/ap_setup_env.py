"""
Setup script — creates the Apolio Home Admin Google Sheets file.
Run once: python setup.py
"""
import os
import json
import base64
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

def main():
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT"]
    creds_dict = json.loads(base64.b64decode(raw))
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)

    print("Creating Apolio Home Admin file...")
    spreadsheet = gc.create("Apolio Home — Admin")

    # Envelopes sheet
    ws_env = spreadsheet.add_worksheet("Envelopes", rows=100, cols=10)
    ws_env.update([["ID", "Name", "File_ID", "Owner_ID",
                    "Settings", "Active", "Created_At"]])

    # Config sheet
    ws_cfg = spreadsheet.add_worksheet("Config", rows=100, cols=3)
    ws_cfg.update([
        ["Key", "Value", "Description"],
        ["admin_users", f'[{{"id":{os.environ.get("MIKHAIL_TELEGRAM_ID","0")},"name":"Mikhail"}}]', "Admin users JSON"],
        ["contributor_users", "[]", "Contributor users JSON"],
        ["alert_threshold_pct", "80", "Alert at % of monthly budget"],
        ["default_currency", "EUR", "Default currency"],
        ["fx_fallback", "nearest", "FX fallback strategy"],
    ])

    # Audit log sheet
    ws_audit = spreadsheet.add_worksheet("Audit_Log", rows=10000, cols=7)
    ws_audit.update([["Timestamp", "Telegram_ID", "Name",
                      "Action", "Envelope_ID", "Details"]])

    # FX_Rates sheet (shared across envelopes)
    ws_fx = spreadsheet.add_worksheet("FX_Rates", rows=100, cols=7)
    ws_fx.update([["Month", "PLN", "UAH", "GBP", "USD", "Source", "Updated"]])

    # Delete default Sheet1
    try:
        spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
    except Exception:
        pass

    print(f"✓ Admin file created: https://docs.google.com/spreadsheets/d/{spreadsheet.id}")
    print(f"\nAdd this to your .env file:")
    print(f"GOOGLE_SHEETS_ADMIN_ID={spreadsheet.id}")

if __name__ == "__main__":
    main()
