"""Transaction tools — add, edit, delete, find"""
import uuid
import csv
import io
from datetime import datetime
from typing import Any

from sheets import SheetsClient
from auth import AuthManager, SessionContext, LastAction


def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _resolve_envelope(params: dict, session: SessionContext,
                       sheets: SheetsClient) -> dict:
    """Find the envelope file_id for the given envelope_id."""
    env_id = params.get("envelope_id") or session.current_envelope_id
    if not env_id:
        raise ValueError("Конверт не выбран. Используйте /envelope для выбора конверта.")
    envelopes = sheets.get_envelopes()
    for e in envelopes:
        if e.get("ID") == env_id:
            return e
    raise ValueError(f"Конверт {env_id} не найден. Проверьте список конвертов командой /envelope.")


async def tool_add_transaction(params: dict, session: SessionContext,
                                sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    envelope = _resolve_envelope(params, session, sheets)
    if not auth.can_access_envelope(session.user_id, envelope["ID"]):
        return {"error": "You don't have access to this envelope."}

    tx_id = _gen_id()
    now = datetime.utcnow().isoformat()
    date = params.get("date") or _today()
    amount = params["amount"]
    currency = params.get("currency", "EUR")
    category = params.get("category", "Other")
    subcategory = params.get("subcategory", "")
    who = params.get("who", session.user_name)
    account = params.get("account", "")
    tx_type = params.get("type", "expense")
    note = params.get("note", "")

    # Resolve Amount_EUR: direct for EUR, otherwise look up FX rate
    amount_eur = ""
    if currency.upper() == "EUR":
        amount_eur = amount
    else:
        try:
            month = date[:7]  # YYYY-MM
            file_id = envelope["file_id"]
            fx_ws = sheets._env_sheets(file_id)._ws("FX_Rates")
            fx_rows = fx_ws.get_all_records()
            fx_row = next((r for r in fx_rows if r.get("Month") == month), None)
            if fx_row:
                # FX_Rates columns are named EUR_PLN, EUR_UAH, EUR_USD etc.
                # Each value means: 1 EUR = N <currency>
                # To convert to EUR: amount_eur = amount_orig / rate
                col_key = f"EUR_{currency.upper()}"
                rate = float(fx_row.get(col_key, 0) or 0)
                if rate:
                    amount_eur = round(float(amount) / rate, 2)
        except Exception:
            pass  # leave blank; fallback in reporting uses Amount_Orig

    # Column order matches the restructured Transactions sheet (Task 4a):
    # A:Date  B:Amount_Orig  C:Currency_Orig  D:Category  E:Subcategory
    # F:Note  G:Who  H:Amount_EUR  I:Type  J:Account
    # K:ID  L:Envelope  M:Source  N:Wise_ID  O:Created_At  P:Deleted
    row = [
        date,           # A - Date
        amount,         # B - Amount_Orig
        currency,       # C - Currency_Orig
        category,       # D - Category
        subcategory,    # E - Subcategory
        note,           # F - Note
        who,            # G - Who
        amount_eur,     # H - Amount_EUR
        tx_type,        # I - Type
        account,        # J - Account
        tx_id,          # K - ID
        envelope["ID"], # L - Envelope
        "bot",          # M - Source
        "",             # N - Wise_ID
        now,            # O - Created_At
        "FALSE",        # P - Deleted
    ]

    sheets.add_transaction(envelope["file_id"], row)

    # Update session last_action for undo
    session.last_action = LastAction(
        tx_id=tx_id, action="add",
        envelope_id=envelope["ID"],
        snapshot={"amount": amount, "currency": currency,
                   "date": date, "category": category}
    )

    symbol = "✓" if tx_type == "expense" else "+"
    return {
        "status": "ok",
        "message": (
            f"{symbol} {category} · {amount} {currency} · {who} · {date}"
            + (f" · {note}" if note else "")
        ),
        "tx_id": tx_id,
    }


async def tool_edit_transaction(params: dict, session: SessionContext,
                                 sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    tx_id = params["tx_id"]
    field = params["field"]
    new_value = params["new_value"]

    # Find which envelope contains this tx
    envelope_id = params.get("envelope_id") or session.current_envelope_id
    envelopes = sheets.get_envelopes()
    file_id = None
    for e in envelopes:
        if e.get("ID") == envelope_id:
            file_id = e["file_id"]
            break

    if not file_id:
        return {"error": "Envelope not found."}

    sheets.update_transaction_field(file_id, tx_id, field, new_value)
    session.last_action = LastAction(
        tx_id=tx_id, action="edit",
        envelope_id=envelope_id,
        snapshot={"field": field, "new_value": new_value}
    )
    return {"status": "ok", "message": f"✓ Updated {field} → {new_value} ({tx_id})"}


async def tool_delete_transaction(params: dict, session: SessionContext,
                                   sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    if not params.get("confirmed"):
        return {
            "status": "confirm_required",
            "message": f"Reply /confirm_delete_{params['tx_id']} to remove this entry.",
        }

    tx_id = params["tx_id"]
    envelope_id = params.get("envelope_id") or session.current_envelope_id
    envelopes = sheets.get_envelopes()
    for e in envelopes:
        if e.get("ID") == envelope_id:
            sheets.soft_delete_transaction(e["file_id"], tx_id)
            return {"status": "ok", "message": f"✓ Deleted ({tx_id})"}

    return {"error": "Envelope not found."}


async def tool_delete_transaction_rows(params: dict, session: SessionContext,
                                        sheets: SheetsClient, auth: AuthManager) -> Any:
    """Physically delete a range of rows from the Transactions sheet by row number.
    Two-step: first call (confirmed=False) returns a preview; second (confirmed=True) executes."""
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    start_row = params.get("start_row")
    end_row = params.get("end_row")

    if start_row is None or end_row is None:
        return {"error": "start_row и end_row обязательны."}
    start_row = int(start_row)
    end_row = int(end_row)

    if start_row < 2:
        return {"error": "Строка 1 — заголовок, удалять нельзя. Строки данных начинаются с 2."}
    if end_row < start_row:
        return {"error": "end_row должен быть >= start_row."}
    if end_row - start_row > 99:
        return {"error": "Нельзя удалять больше 100 строк за раз."}

    envelope = _resolve_envelope(params, session, sheets)
    if not auth.can_access_envelope(session.user_id, envelope["ID"]):
        return {"error": "You don't have access to this envelope."}

    count = end_row - start_row + 1

    # ── Step 1: preview (no confirmed flag) ──────────────────────────────────
    if not params.get("confirmed"):
        try:
            raw_rows = sheets.get_transaction_rows_preview(
                envelope["file_id"], start_row, end_row
            )
        except Exception as e:
            raw_rows = []

        lines = []
        for i, row in enumerate(raw_rows):
            sheet_row = start_row + i
            try:
                date     = row[0] if len(row) > 0 else "?"
                amount   = row[1] if len(row) > 1 else "?"
                currency = row[2] if len(row) > 2 else ""
                category = row[3] if len(row) > 3 else ""
                tx_type  = row[8] if len(row) > 8 else ""
                note     = row[5] if len(row) > 5 else ""
                desc = f"{date} · {amount} {currency} · {category}"
                if note:
                    desc += f" · {note}"
                lines.append(f"  {sheet_row}: {desc}")
            except Exception:
                lines.append(f"  {sheet_row}: [данные]")

        preview = "\n".join(lines) if lines else "  (нет данных)"

        # Store pending action in session for inline-button confirmation
        session.pending_delete = {
            "start_row": start_row,
            "end_row": end_row,
            "file_id": envelope["file_id"],
            "count": count,
        }

        return {
            "status": "confirm_required",
            "message": (
                f"⚠️ ВНИМАНИЕ — безвозвратное удаление {count} {_row_word(count)} "
                f"({start_row}–{end_row}):\n\n"
                f"{preview}\n\n"
                "Это действие нельзя отменить. Нажмите кнопку ниже для подтверждения."
            ),
        }

    # ── Step 2: execute (confirmed=True) ─────────────────────────────────────
    try:
        deleted = sheets.delete_transaction_rows(envelope["file_id"], start_row, end_row)
    except Exception as e:
        return {"error": f"Ошибка удаления: {e}"}

    return {
        "status": "ok",
        "message": f"✓ Удалено {deleted} {_row_word(deleted)} ({start_row}–{end_row})",
    }


def _row_word(n: int) -> str:
    if n % 100 in (11, 12, 13, 14):
        return "строк"
    r = n % 10
    if r == 1:
        return "строка"
    if r in (2, 3, 4):
        return "строки"
    return "строк"


async def tool_sort_transactions(params: dict, session: SessionContext,
                                  sheets: SheetsClient, auth: AuthManager) -> Any:
    """Sort Transactions sheet by date (ascending = oldest first, descending = newest first)."""
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    order = params.get("order", "asc").lower()
    if order not in ("asc", "desc"):
        order = "asc"

    envelope = _resolve_envelope(params, session, sheets)
    if not auth.can_access_envelope(session.user_id, envelope["ID"]):
        return {"error": "You don't have access to this envelope."}

    try:
        count = sheets.sort_transactions_by_date(envelope["file_id"], order)
    except Exception as e:
        return {"error": f"Ошибка сортировки: {e}"}

    direction = "старые → новые" if order == "asc" else "новые → старые"
    return {
        "status": "ok",
        "message": f"✓ Отсортировано {count} {_row_word(count)} по дате ({direction})",
    }


async def tool_find_transactions(params: dict, session: SessionContext,
                                  sheets: SheetsClient, auth: AuthManager) -> Any:
    envelope_id = params.get("envelope_id") or session.current_envelope_id
    if not auth.can_access_envelope(session.user_id, envelope_id):
        return {"error": "Permission denied."}

    envelopes = sheets.get_envelopes()
    file_id = None
    for e in envelopes:
        if e.get("ID") == envelope_id:
            file_id = e["file_id"]
            break

    if not file_id:
        return {"error": "Envelope not found."}

    records = sheets.get_transactions(file_id)
    limit = params.get("limit", 10)

    # Apply filters
    if params.get("date_from"):
        records = [r for r in records if r.get("Date", "") >= params["date_from"]]
    if params.get("date_to"):
        records = [r for r in records if r.get("Date", "") <= params["date_to"]]
    if params.get("category"):
        records = [r for r in records
                   if params["category"].lower() in r.get("Category", "").lower()]
    if params.get("who"):
        records = [r for r in records if r.get("Who") == params["who"]]
    if params.get("note_contains"):
        records = [r for r in records
                   if params["note_contains"].lower() in r.get("Note", "").lower()]

    records = records[-limit:]
    return {"status": "ok", "count": len(records), "transactions": records}
