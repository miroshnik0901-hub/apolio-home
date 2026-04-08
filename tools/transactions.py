"""Transaction tools — add, edit, delete, find"""
import uuid
import csv
import io
import logging
from datetime import datetime
from typing import Any

from sheets import SheetsClient
from auth import AuthManager, SessionContext, LastAction

logger = logging.getLogger(__name__)


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


def _fuzzy_suggest(value: str, known: list[str], max_results: int = 3) -> list[str]:
    """Return known values that are similar to value (case-insensitive substring match)."""
    value_l = value.lower()
    exact = [k for k in known if k.lower() == value_l]
    if exact:
        return []  # it's actually a match
    contains = [k for k in known if value_l in k.lower() or k.lower() in value_l]
    return contains[:max_results] if contains else known[:max_results]


def _normalize_who(who: str, known_who: list[str]) -> str | None:
    """Auto-correct 'who' if a known user first name appears in the submitted value.

    Handles cases like "Marina Maslo" → "Marina" when "Marina" is a known user.
    Returns the normalized known name, or None if no clear match.
    This prevents phantom users from being created when full names are submitted.
    """
    if not who or not known_who:
        return None
    who_l = who.lower().strip()
    # Already an exact match — no normalization needed
    for k in known_who:
        if k.lower() == who_l:
            return k
    # Check if any individual word in the submitted value exactly matches a known user
    who_words = who_l.split()
    for k in known_who:
        if k.lower() in who_words:
            return k
    return None


def _validate_transaction_params(params: dict, ref: dict) -> dict:
    """Check category, who, account against reference data.
    Returns dict of unknown fields and suggestions, or empty dict if all OK.
    Skip validation if force_new=True or if reference list is empty (not set up yet).

    Side effect: normalizes params['who'] in-place if a known user name is found
    within the submitted value (e.g. "Marina Maslo" → "Marina"). This prevents
    phantom users from appearing in contribution reports.
    """
    if params.get("force_new"):
        return {}

    unknown = {}
    suggestions = {}

    # Validate category
    category = params.get("category", "")
    known_cats = ref.get("categories", [])
    if category and known_cats:
        if not any(k.lower() == category.lower() for k in known_cats):
            unknown["category"] = category
            suggestions["category"] = _fuzzy_suggest(category, known_cats)

    # Validate subcategory (only if parent category is known)
    subcategory = params.get("subcategory", "")
    known_subs = ref.get("subcategories", [])
    if subcategory and known_subs and "category" not in unknown:
        if not any(k.lower() == subcategory.lower() for k in known_subs):
            unknown["subcategory"] = subcategory
            suggestions["subcategory"] = _fuzzy_suggest(subcategory, known_subs)

    # Validate who — with auto-normalization for full names (T-034)
    who = params.get("who", "")
    known_who = ref.get("who", [])
    if who and known_who:
        normalized = _normalize_who(who, known_who)
        if normalized and normalized.lower() != who.lower():
            # Auto-correct silently: "Marina Maslo" → "Marina"
            params["who"] = normalized
        elif not any(k.lower() == who.lower() for k in known_who):
            unknown["who"] = who
            suggestions["who"] = _fuzzy_suggest(who, known_who)

    if unknown:
        return {"unknown": unknown, "suggestions": suggestions, "known": ref}
    return {}


async def tool_add_transaction(params: dict, session: SessionContext,
                                sheets: SheetsClient, auth: AuthManager) -> Any:
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    envelope = _resolve_envelope(params, session, sheets)
    if not auth.can_access_envelope(session.user_id, envelope["ID"]):
        return {"error": "You don't have access to this envelope."}

    # ── Validation against reference data ────────────────────────────────
    try:
        ref = sheets.get_reference_data(envelope["file_id"])
        issues = _validate_transaction_params(params, ref)
        if issues:
            unknown = issues["unknown"]
            sug = issues["suggestions"]
            known = issues["known"]

            lines = []
            for field, val in unknown.items():
                s = sug.get(field, [])
                hint = f"Похожие: {', '.join(s)}" if s else f"Известные: {', '.join(known.get(field + 's', known.get(field, [])))}"
                lines.append(f"• {field} = «{val}» — не найдено. {hint}")

            return {
                "status": "confirm_required",
                "type": "unknown_values",
                "message": (
                    "Обнаружены неизвестные значения:\n" + "\n".join(lines) +
                    "\n\nУточни у пользователя: использовать одно из предложенных "
                    "или добавить новое значение в справочник? "
                    "При подтверждении вызови снова с force_new=true."
                ),
                "unknown_fields": unknown,
                "suggestions": sug,
            }
    except Exception:
        pass  # validation is best-effort; don't block the write

    tx_id = _gen_id()
    now = datetime.utcnow().isoformat()
    date = params.get("date") or _today()
    amount = params["amount"]
    currency = params.get("currency", "EUR")
    category = params.get("category", "")
    subcategory = params.get("subcategory", "")
    who = params.get("who", session.user_name)

    # ── Duplicate detection (T-030) ──────────────────────────────────────
    # get_transactions already filters out deleted rows
    if not params.get("force_add"):
        try:
            existing = sheets.get_transactions(
                envelope["file_id"],
                {"date_from": date, "date_to": date, "limit": 50},
            )
            try:
                in_amount = float(amount)
            except (ValueError, TypeError):
                in_amount = 0.0
            for ex in existing:
                try:
                    ex_amount = float(ex.get("Amount_Orig") or 0)
                except (ValueError, TypeError):
                    ex_amount = 0.0
                ex_cat = str(ex.get("Category", "")).lower()
                ex_who = str(ex.get("Who", "")).lower()
                same_amount = abs(ex_amount - in_amount) < 0.01
                same_cat = (ex_cat == category.lower()) if category else True
                same_who = (ex_who == who.lower()) if who else True
                if same_amount and same_cat and same_who:
                    return {
                        "status": "confirm_required",
                        "type": "duplicate",
                        "message": (
                            f"Похожая запись уже есть за {date}: "
                            f"{ex.get('Category', '')} · {ex_amount} {ex.get('Currency_Orig', currency)} · {ex.get('Who', '')}. "
                            "Это дубликат? Если нет — вызови снова с force_add=true."
                        ),
                        "existing_tx_id": ex.get("ID", ""),
                    }
        except Exception:
            pass  # duplicate check is best-effort; don't block the write
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

    try:
        sheets.add_transaction(envelope["file_id"], row)
    except Exception as e:
        logger.error(f"sheets.add_transaction failed for {tx_id}: {e}", exc_info=True)
        return {"error": f"TRANSACTION FAILED to save: {e}", "tx_id": tx_id}

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
    import db as _db
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    if not params.get("confirmed"):
        return {
            "status": "confirm_required",
            "message": "confirmed=true required to proceed with deletion.",
        }

    tx_id = params.get("tx_id", "").strip()
    if not tx_id:
        return {"error": "tx_id is required."}

    envelope_id = params.get("envelope_id") or session.current_envelope_id
    envelopes = sheets.get_envelopes()
    matched_envelope = next((e for e in envelopes if e.get("ID") == envelope_id), None)

    if not matched_envelope:
        return {
            "error": f"DELETION FAILED — envelope '{envelope_id}' not found. "
                     f"Transaction was NOT deleted. Check envelope_id.",
        }

    deleted = sheets.hard_delete_transaction(matched_envelope["file_id"], tx_id)
    if not deleted:
        return {
            "error": f"DELETION FAILED — transaction '{tx_id}' not found in "
                     f"envelope '{envelope_id}'. Row was NOT removed.",
        }

    # Clean up parsed_data in PostgreSQL
    if _db.is_ready():
        try:
            pool = await _db.get_pool()
            if pool:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM parsed_data WHERE transaction_id = $1", tx_id
                    )
        except Exception as e:
            logger.warning(f"delete_transaction: parsed_data cleanup failed: {e}")

    return {
        "status": "ok",
        "deleted": True,
        "tx_id": tx_id,
        "message": f"Transaction {tx_id} permanently deleted from Sheets and DB.",
    }


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
