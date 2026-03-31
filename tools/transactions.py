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
        raise ValueError("No envelope selected. Use /envelope <id> to select one.")
    envelopes = sheets.get_envelopes()
    for e in envelopes:
        if e.get("ID") == env_id:
            return e
    raise ValueError(f"Envelope {env_id} not found.")


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

    row = [
        tx_id, date, envelope["ID"],
        amount, currency, "",          # Amount_EUR filled by formula
        category, subcategory,
        who, account, tx_type,
        note, "bot", "",               # Wise_ID empty for manual
        now, "FALSE",
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
