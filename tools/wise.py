"""Wise CSV import tool"""
import csv
import io
import uuid
from datetime import datetime
from typing import Any

from sheets import SheetsClient
from auth import AuthManager, SessionContext


MERCHANT_CATEGORY_MAP = {
    "esselunga": ("Food", "Groceries"),
    "conad": ("Food", "Groceries"),
    "billa": ("Food", "Groceries"),
    "carrefour": ("Food", "Groceries"),
    "lidl": ("Food", "Groceries"),
    "aldi": ("Food", "Groceries"),
    "biedronka": ("Food", "Groceries"),
    "kaufland": ("Food", "Groceries"),
    "eni": ("Transport", "Fuel"),
    "agip": ("Transport", "Fuel"),
    "q8": ("Transport", "Fuel"),
    "shell": ("Transport", "Fuel"),
    "orlen": ("Transport", "Fuel"),
    "trenitalia": ("Transport", "Public Transport"),
    "italo": ("Transport", "Public Transport"),
    "ryanair": ("Entertainment", "Travel"),
    "easyjet": ("Entertainment", "Travel"),
    "wizzair": ("Entertainment", "Travel"),
    "netflix": ("Entertainment", "Subscriptions"),
    "spotify": ("Entertainment", "Subscriptions"),
    "amazon": ("Household", "Electronics"),
    "farmaci": ("Health", "Pharmacy"),
    "farmacia": ("Health", "Pharmacy"),
    "apteka": ("Health", "Pharmacy"),
}


def _guess_category(description: str) -> tuple[str, str]:
    desc_lower = description.lower()
    for keyword, cat in MERCHANT_CATEGORY_MAP.items():
        if keyword in desc_lower:
            return cat
    return ("Other", "Miscellaneous")


async def tool_import_wise_csv(params: dict, session: SessionContext,
                                sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.is_admin(session.user_id):
        return {"error": "Admin only."}

    envelope_id = params.get("envelope_id") or session.current_envelope_id
    envelopes = sheets.get_envelopes()
    env = next((e for e in envelopes if e.get("ID") == envelope_id), None)
    if not env:
        return {"error": "Envelope not found."}

    content = params["file_content"]
    reader = csv.DictReader(io.StringIO(content))

    imported = 0
    skipped = 0
    needs_review = []

    existing = sheets.get_transactions(env["file_id"])
    existing_wise_ids = {r.get("Wise_ID") for r in existing if r.get("Wise_ID")}

    for row in reader:
        # Wise CSV columns: TransferWise ID, Date, Amount, Currency, Description, etc.
        wise_id = row.get("TransferWise ID") or row.get("ID") or ""
        if wise_id and wise_id in existing_wise_ids:
            skipped += 1
            continue

        try:
            date_raw = row.get("Date") or row.get("Created on") or ""
            # Handle DD-MM-YYYY or YYYY-MM-DD
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    date = datetime.strptime(date_raw, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            else:
                date = datetime.now().strftime("%Y-%m-%d")

            amount_raw = row.get("Amount") or row.get("Source amount (after fees)") or "0"
            amount = abs(float(str(amount_raw).replace(",", ".")))
            currency = row.get("Currency") or row.get("Source currency") or "EUR"
            description = row.get("Description") or row.get("Merchant") or ""
            tx_type = "income" if float(str(amount_raw).replace(",", ".")) > 0 else "expense"

            category, subcategory = _guess_category(description)
            confidence = "high" if category != "Other" else "low"

            tx_id = uuid.uuid4().hex[:8]
            now = datetime.utcnow().isoformat()

            row_data = [
                tx_id, date, envelope_id,
                amount, currency, "",
                category, subcategory,
                "Joint", "", tx_type,
                description, "wise_csv", wise_id,
                now, "FALSE",
            ]

            sheets.add_transaction(env["file_id"], row_data)
            imported += 1

            if confidence == "low":
                needs_review.append({
                    "tx_id": tx_id,
                    "description": description,
                    "amount": amount,
                    "currency": currency,
                    "date": date,
                })

        except Exception as e:
            skipped += 1

    result = {
        "status": "ok",
        "imported": imported,
        "skipped": skipped,
        "needs_review": needs_review,
    }

    if needs_review:
        review_lines = "\n".join(
            f"{i+1}. {r['description']} · {r['amount']} {r['currency']} · {r['date']}"
            for i, r in enumerate(needs_review)
        )
        result["message"] = (
            f"Imported {imported} transactions ✓\n\n"
            f"Need category for {len(needs_review)} items:\n{review_lines}"
        )
    else:
        result["message"] = f"✓ Imported {imported} transactions."

    return result
