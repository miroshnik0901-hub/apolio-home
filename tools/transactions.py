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

    # Income transactions: category/subcategory are not from the expense taxonomy.
    # Strip subcategory silently (AI often sets "Top-up" which doesn't exist in expense list).
    # Skip category/subcategory validation entirely for income — validate only who/account.
    tx_type_for_val = params.get("type", "expense")
    if tx_type_for_val == "income":
        params["subcategory"] = ""  # strip — income has no subcategory
        # Leave category as-is (e.g. "Income") but don't validate it against expense list
    else:
        # Validate category — auto-correct if fuzzy match finds exactly one hit
        category = params.get("category", "")
        known_cats = ref.get("categories", [])
        if category and known_cats:
            if not any(k.lower() == category.lower() for k in known_cats):
                similar = _fuzzy_suggest(category, known_cats)
                if len(similar) == 1:
                    params["category"] = similar[0]  # auto-correct
                else:
                    unknown["category"] = category
                    suggestions["category"] = similar

        # Validate subcategory (only if parent category is known) — auto-correct
        subcategory = params.get("subcategory", "")
        known_subs = ref.get("subcategories", [])
        if subcategory and known_subs and "category" not in unknown:
            if not any(k.lower() == subcategory.lower() for k in known_subs):
                similar = _fuzzy_suggest(subcategory, known_subs)
                if len(similar) == 1:
                    params["subcategory"] = similar[0]  # auto-correct
                else:
                    unknown["subcategory"] = subcategory
                    suggestions["subcategory"] = similar

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
                                sheets: SheetsClient, auth: AuthManager,
                                skip_sort: bool = False,
                                batch_mode: bool = False) -> Any:
    """batch_mode=True: skip validation + dup check to avoid N×2 Sheets read
    calls that exhaust the 60 req/min quota when adding items in a loop."""
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    envelope = _resolve_envelope(params, session, sheets)
    if not auth.can_access_envelope(session.user_id, envelope["ID"]):
        return {"error": "You don't have access to this envelope."}

    # batch_mode: inject flags that skip validation and duplicate detection.
    # User already reviewed and confirmed the item list — no need for per-item checks.
    if batch_mode:
        params = dict(params)       # don't mutate caller's dict
        params["force_new"] = True  # skip category/who validation
        params["force_add"] = True  # skip duplicate detection

    # ── Validation against reference data ────────────────────────────────
    # T-211: skip get_reference_data entirely in batch_mode (force_new=True skips anyway)
    # This saves 1 read per batch item = 7 reads for 7 items.
    if batch_mode or params.get("force_new"):
        issues = {}  # no validation in batch mode
    else:
        issues = {}
    try:
        if not batch_mode:
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
                    "message": "⚠️ Неизвестные значения:\n" + "\n".join(lines),
                    "unknown_fields": unknown,
                    "suggestions": sug,
                    "hint_for_agent": (
                        "Ask the user: pick one of the suggested values, or confirm "
                        "creating a new one? If user confirms new value, call again with force_new=true."
                    ),
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

    # ── Duplicate detection (T-030 / T-182 / T-192) ──────────────────────
    # Checks: same date + amount within tolerance + note overlap.
    # Same-currency tolerance:
    #   EUR  → strict: abs diff < 0.01 (rounding only)
    #   other → ±5%: covers FX rate fluctuation.
    # Cross-currency (T-192): compare Amount_EUR from existing vs pre-computed
    #   EUR equivalent of new tx.  Handles UAH bank stmt vs EUR manual entry.
    # Note/merchant: if both sides have a non-empty note, strings that share
    #   no common tokens are treated as different transactions (not duplicate).
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
            in_note = str(params.get("note", "")).strip().lower()
            in_cur = currency.upper()

            # T-192: pre-compute EUR equivalent of new tx for cross-currency check.
            # Reuses FX_Rates sheet (same read done later for Amount_EUR column).
            _pre_eur: float | None = None
            if in_cur == "EUR":
                _pre_eur = in_amount
            else:
                try:
                    # T-211: use cached get_fx_rates (no raw gspread call)
                    _fx_rows2 = sheets.get_fx_rates(envelope["file_id"])
                    _fx_row2 = next(
                        (r for r in _fx_rows2 if r.get("Month") == date[:7]), None
                    )
                    if _fx_row2:
                        _col2 = f"EUR_{in_cur}"
                        _rate2 = float(_fx_row2.get(_col2, 0) or 0)
                        if _rate2:
                            _pre_eur = round(in_amount / _rate2, 2)
                except Exception:
                    pass  # leave _pre_eur = None; cross-currency check skipped

            for ex in existing:
                ex_cur = str(ex.get("Currency_Orig", "EUR")).upper()

                if ex_cur != in_cur:
                    # ── T-192: cross-currency check via Amount_EUR ───────
                    if _pre_eur is None or _pre_eur <= 0:
                        continue
                    try:
                        ex_eur = float(ex.get("Amount_EUR") or 0)
                    except (ValueError, TypeError):
                        ex_eur = 0.0
                    if ex_eur <= 0:
                        continue
                    eur_tol = max(_pre_eur * 0.05, 0.5)
                    if abs(ex_eur - _pre_eur) > eur_tol:
                        continue
                    # EUR amounts match — check note overlap before flagging
                    ex_note_x = str(ex.get("Note", "")).strip().lower()
                    if in_note and ex_note_x:
                        in_toks_x = set(in_note.split())
                        ex_toks_x = set(ex_note_x.split())
                        if not in_toks_x & ex_toks_x:
                            continue
                    return {
                        "status": "confirm_required",
                        "type": "duplicate",
                        "message": (
                            f"⚠️ Похожая запись уже есть за {date}: "
                            f"{ex.get('Category', '')} · {ex_eur:.2f} EUR"
                            f" (оригінал: {ex.get('Amount_Orig', '')} {ex_cur})"
                            + (f" · {ex.get('Note', '')}" if ex.get("Note") else "")
                            + f" · {ex.get('Who', '')} (cross-currency ±5% EUR match)"
                        ),
                        "existing_tx_id": ex.get("ID", ""),
                        "hint_for_agent": "Ask user: is this a duplicate? If not, call add_transaction again with force_add=true.",
                    }
                    # end cross-currency branch — continue to next existing tx

                # ── Same-currency amount tolerance ───────────────────────
                try:
                    ex_amount = float(ex.get("Amount_Orig") or 0)
                except (ValueError, TypeError):
                    ex_amount = 0.0
                if in_cur == "EUR":
                    same_amount = abs(ex_amount - in_amount) < 0.01
                else:
                    # ±5% for non-EUR: covers FX rounding and rate differences
                    tolerance = max(in_amount * 0.05, 0.5)
                    same_amount = abs(ex_amount - in_amount) <= tolerance

                if not same_amount:
                    continue

                # ── Category + who ───────────────────────────────────────
                ex_cat = str(ex.get("Category", "")).lower()
                ex_who = str(ex.get("Who", "")).lower()
                same_cat = (ex_cat == category.lower()) if category else True
                same_who = (ex_who == who.lower()) if who else True

                if not (same_cat and same_who):
                    continue

                # ── Note / merchant: reject if both present and no overlap ──
                ex_note = str(ex.get("Note", "")).strip().lower()
                if in_note and ex_note:
                    in_tokens = set(in_note.split())
                    ex_tokens = set(ex_note.split())
                    if not in_tokens & ex_tokens:
                        # No common words → different merchants, not a duplicate
                        continue

                return {
                    "status": "confirm_required",
                    "type": "duplicate",
                    "message": (
                        f"⚠️ Похожая запись уже есть за {date}: "
                        f"{ex.get('Category', '')} · {ex_amount:,.2f} {ex_cur}"
                        + (f" · {ex.get('Note', '')}" if ex.get('Note') else "")
                        + f" · {ex.get('Who', '')}"
                        + (f" (±5% FX tolerance)" if in_cur != "EUR" else "")
                    ),
                    "existing_tx_id": ex.get("ID", ""),
                    "hint_for_agent": "Ask user: is this a duplicate? If not, call add_transaction again with force_add=true.",
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
            # T-211: use cached get_fx_rates (5-min TTL via _static_cache).
            # OLD: fx_ws.get_all_records() — uncached, hit quota on every batch item.
            fx_rows = sheets.get_fx_rates(file_id)
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
        # T-212: keep TRANSACTION FAILED prefix (test compatibility) but clean raw JSON
        import re as _re
        _err_str = str(e)
        _code_m = _re.search(r"'code':\s*(\d+)", _err_str)
        if _code_m:
            _code = int(_code_m.group(1))
            _friendly = {
                429: "Quota exceeded (60 reads/min). Try again in 30 sec.",
                500: "Sheets server error (transient). Retry in ~30 sec.",
                503: "Sheets unavailable (transient). Retry.",
            }.get(_code, f"Sheets API {_code}")
            return {"error": f"TRANSACTION FAILED: {_friendly}", "tx_id": tx_id}
        return {"error": f"TRANSACTION FAILED to save: {_err_str[:120]}", "tx_id": tx_id}

    # T-176: sort Transactions sheet by Date (asc) after every add.
    # T-183: skip_sort=True in batch mode (cb_split_separate) — caller sorts once at end.
    if not skip_sort:
        try:
            sheets.sort_transactions_by_date(envelope["file_id"], order="asc")
        except Exception as _sort_err:
            logger.warning(f"sort_transactions_by_date failed (non-fatal): {_sort_err}")

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


async def tool_enrich_transaction(params: dict, session: SessionContext,
                                   sheets: SheetsClient, auth: AuthManager) -> Any:
    """T-134: Enrich an existing transaction with receipt data.
    Updates multiple fields at once (note, category, subcategory, etc.)
    without creating a duplicate transaction."""
    if not auth.can_write(session.user_id):
        return {"error": "Permission denied."}

    tx_id = params.get("tx_id", "")
    if not tx_id:
        return {"error": "tx_id is required."}

    envelope_id = params.get("envelope_id") or session.current_envelope_id
    envelopes = sheets.get_envelopes()
    file_id = None
    for e in envelopes:
        if e.get("ID") == envelope_id:
            file_id = e["file_id"]
            break
    if not file_id:
        return {"error": "Envelope not found."}

    # Validate category/subcategory/who against reference data
    try:
        ref = sheets.get_reference_data(file_id)
        # Build a mini-params dict for validation
        _vparams = {}
        if params.get("category"):
            _vparams["category"] = params["category"]
        if params.get("subcategory"):
            _vparams["subcategory"] = params["subcategory"]
        if params.get("who"):
            _vparams["who"] = params["who"]
        if _vparams:
            issues = _validate_transaction_params(_vparams, ref)
            if issues:
                unknown = issues["unknown"]
                sug = issues["suggestions"]
                known = issues["known"]
                lines = []
                for field, val in unknown.items():
                    s = sug.get(field, [])
                    hint = (f"Похожие: {', '.join(s)}" if s
                            else f"Известные: {', '.join(known.get(field + 's', known.get(field, [])))}")
                    lines.append(f"• {field} = «{val}» — не найдено. {hint}")
                return {
                    "status": "confirm_required",
                    "type": "unknown_values",
                    "message": "⚠️ Неизвестные значения:\n" + "\n".join(lines),
                    "unknown_fields": unknown,
                    "suggestions": sug,
                    "hint_for_agent": (
                        "Ask user: pick a suggested value, or confirm creating new? "
                        "If confirmed, call enrich_transaction again — the value will be accepted."
                    ),
                }
            # Apply auto-corrections from validation
            if "category" in _vparams:
                params["category"] = _vparams["category"]
            if "subcategory" in _vparams:
                params["subcategory"] = _vparams["subcategory"]
            if "who" in _vparams:
                params["who"] = _vparams["who"]
    except Exception:
        pass  # validation is best-effort

    # Fields that can be enriched from receipt data
    # T-210: also support amount_orig / currency_orig (e.g. UAH original from bank statement)
    col_map = {
        "note": "Note",
        "category": "Category",
        "subcategory": "Subcategory",
        "who": "Who",
        "account": "Account",
        "amount_orig": "Amount_Orig",
        "currency_orig": "Currency_Orig",
    }
    field_sources = {
        "note": params.get("note"),
        "category": params.get("category"),
        "subcategory": params.get("subcategory"),
        "who": params.get("who"),
        "account": params.get("account"),
        "amount_orig": str(params["amount_orig"]) if params.get("amount_orig") else None,
        "currency_orig": params.get("currency_orig"),
    }
    fields_to_write = {
        col_map[k]: v for k, v in field_sources.items()
        if v is not None and v != ""
    }

    if not fields_to_write:
        return {"error": "No fields to update."}

    # T-209: ONE read + N writes instead of N reads + N writes.
    # Also fixes false-positive: update_transaction_fields returns list of
    # actually-updated field names, not just "no exception raised".
    try:
        written_cols = sheets.update_transaction_fields(file_id, tx_id, fields_to_write)
    except Exception as e:
        logger.error(f"enrich_transaction: batch write failed: {e}")
        return {"error": f"Sheets write failed: {e}"}

    if not written_cols:
        logger.warning(f"enrich_transaction: tx_id {tx_id} not found in {file_id}")
        return {"error": f"Transaction {tx_id} not found in Sheets. It may have been deleted or the ID is wrong."}

    # Build human-readable summary of what was updated
    reverse_map = {v: k for k, v in col_map.items()}
    updated_display = [f"{reverse_map.get(c, c)}={fields_to_write[c]}" for c in written_cols]

    return {
        "status": "ok",
        "message": f"✓ Enriched {tx_id}: {', '.join(updated_display)}",
        "tx_id": tx_id,
        "updated_fields": written_cols,
    }


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

    # Try the target envelope first; if not found, search ALL envelopes
    # (handles cases where old transactions have a different format or were added
    #  before the current session's envelope was set)
    matched_envelope = next((e for e in envelopes if e.get("ID") == envelope_id), None)

    deleted = False
    found_in_envelope = None

    if matched_envelope:
        try:
            deleted = sheets.hard_delete_transaction(matched_envelope["file_id"], tx_id)
            if deleted:
                found_in_envelope = envelope_id
        except Exception as e:
            return {"error": f"DELETION FAILED — Sheets error in envelope '{envelope_id}': {e}"}

    if not deleted:
        # Fallback: try every other envelope
        for env in envelopes:
            if env.get("ID") == envelope_id:
                continue  # already tried
            try:
                if sheets.hard_delete_transaction(env["file_id"], tx_id):
                    deleted = True
                    found_in_envelope = env["ID"]
                    break
            except Exception:
                pass  # continue trying other envelopes

    if not deleted:
        searched = [e.get("ID", "?") for e in envelopes]
        return {
            "error": f"DELETION FAILED — transaction '{tx_id}' not found in any envelope "
                     f"({', '.join(searched)}). Row was NOT removed. "
                     f"Check that the tx_id is correct.",
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
        "envelope_id": found_in_envelope,
        "message": f"Transaction {tx_id} permanently deleted from envelope {found_in_envelope}.",
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
