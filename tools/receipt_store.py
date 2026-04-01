"""
Receipt storage for Apolio Home.
Saves itemized receipt data from photo analysis into the Receipts sheet
within the MM_BUDGET spreadsheet.

See APOLIO_HOME_INTELLIGENCE_v1.0.md §6.2 for storage schema.

Columns:
  A: receipt_id   B: transaction_id  C: date       D: merchant
  E: total_amount F: currency        G: items_json H: ai_summary
  I: raw_text     J: tg_file_id      K: created_at
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import gspread

SHEET_NAME = "Receipts"

HEADERS = [
    "receipt_id", "transaction_id", "date", "merchant",
    "total_amount", "currency", "items_json", "ai_summary",
    "raw_text", "tg_file_id", "created_at",
]


class ReceiptStore:
    """
    Append-only store for receipt data parsed from photos.
    One shared instance per bot process.
    """

    def __init__(self, sheets_client: gspread.Client, file_id: str):
        self._client = sheets_client
        self._file_id = file_id
        self._ws = None
        self._ready = False

    def _ensure_sheet(self):
        if self._ready:
            return
        try:
            wb = self._client.open_by_key(self._file_id)
            try:
                ws = wb.worksheet(SHEET_NAME)
            except gspread.WorksheetNotFound:
                ws = wb.add_worksheet(SHEET_NAME, rows=500, cols=len(HEADERS))
                ws.append_row(HEADERS)
            self._ws = ws
            self._ready = True
        except Exception as e:
            print(f"[ReceiptStore] could not ensure sheet: {e}")

    def save_receipt(
        self,
        *,
        transaction_id: str,
        date: str,
        merchant: str,
        total_amount: float,
        currency: str = "EUR",
        items: list[dict],
        ai_summary: str,
        raw_text: str,
        tg_file_id: str = "",
    ) -> str:
        """
        Save parsed receipt data. Returns receipt_id.

        items: list of {name, amount, category, subcategory (optional)}
        """
        self._ensure_sheet()
        if not self._ws:
            return ""

        receipt_id = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc).isoformat()

        row = [
            receipt_id,
            transaction_id,
            date,
            merchant,
            str(total_amount),
            currency,
            json.dumps(items, ensure_ascii=False),
            ai_summary,
            raw_text[:1000],
            tg_file_id,
            now,
        ]

        try:
            self._ws.append_row(row, value_input_option="USER_ENTERED")
        except Exception as e:
            print(f"[ReceiptStore] save failed: {e}")
            return ""

        return receipt_id

    def get_receipts_for_merchant(self, merchant: str, limit: int = 5) -> list[dict]:
        """
        Load recent receipts from a specific merchant.
        Useful for auto-categorization: "last time at Esselunga, items were categorized as..."
        """
        self._ensure_sheet()
        if not self._ws:
            return []

        try:
            all_rows = self._ws.get_all_records()
            merchant_lower = merchant.lower()
            matching = [
                r for r in all_rows
                if merchant_lower in r.get("merchant", "").lower()
            ]
            return matching[-limit:]
        except Exception as e:
            print(f"[ReceiptStore] get_receipts_for_merchant error: {e}")
            return []


def parse_receipt_from_claude_response(response_text: str) -> dict:
    """
    Extract structured receipt data from Claude's photo analysis response.
    Claude is prompted to return JSON block; this extracts and validates it.

    Returns dict with keys: merchant, date, total_amount, currency, items, summary
    Returns empty dict if parsing fails.
    """
    import re

    # Look for JSON block in response
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if not json_match:
        # Try without code block
        json_match = re.search(r'(\{"merchant".*?\})', response_text, re.DOTALL)

    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return data
        except json.JSONDecodeError:
            pass

    # Fallback: return empty (will be handled gracefully by caller)
    return {}


def build_receipt_confirmation_message(parsed: dict, lang: str = "ru") -> str:
    """
    Build the confirmation message shown to user after photo analysis.
    User sees this before confirming the transaction.
    """
    merchant = parsed.get("merchant", "Неизвестный магазин")
    total = parsed.get("total_amount", 0)
    currency = parsed.get("currency", "EUR")
    items = parsed.get("items", [])
    date = parsed.get("date", "сегодня")

    messages = {
        "ru": {
            "header": f"📄 {merchant} · {total} {currency} · {date}",
            "items_header": "\nРаспознанные позиции:",
            "confirm": "\nЗаписать как единую трату?",
        },
        "uk": {
            "header": f"📄 {merchant} · {total} {currency} · {date}",
            "items_header": "\nРозпізнані позиції:",
            "confirm": "\nЗаписати як єдину витрату?",
        },
        "en": {
            "header": f"📄 {merchant} · {total} {currency} · {date}",
            "items_header": "\nRecognized items:",
            "confirm": "\nRecord as a single transaction?",
        },
        "it": {
            "header": f"📄 {merchant} · {total} {currency} · {date}",
            "items_header": "\nVoci riconosciute:",
            "confirm": "\nRegistrare come transazione singola?",
        },
    }

    m = messages.get(lang, messages["ru"])
    lines = [m["header"]]

    if items:
        lines.append(m["items_header"])
        for item in items[:10]:  # cap display at 10 items
            name = item.get("name", "?")
            amount = item.get("amount", "")
            lines.append(f"• {name} — {amount} {currency}")
        if len(items) > 10:
            lines.append(f"  ... и ещё {len(items) - 10} позиций")

    lines.append(m["confirm"])
    return "\n".join(lines)
