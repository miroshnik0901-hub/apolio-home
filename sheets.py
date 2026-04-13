import os
import json
import base64
import time
import logging as _log_module
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as google_build
from datetime import datetime
from typing import Optional

_sheets_logger = _log_module.getLogger(__name__)

# T-172: retry wrapper for Google Sheets API 429 / 503 transient errors.
# Applied to any sheets read or write call that can hit quota limits.
def _sheets_retry(fn, *args, max_attempts: int = 3, base_delay: float = 5.0, **kwargs):
    """Call fn(*args, **kwargs) with exponential backoff on gspread APIError 429/503."""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            status = e.response.status_code if hasattr(e, "response") else 0
            if status in (429, 503) and attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                _sheets_logger.warning(
                    f"Sheets API {status} on attempt {attempt+1}/{max_attempts}, "
                    f"retrying in {delay:.0f}s"
                )
                time.sleep(delay)
                last_exc = e
            else:
                raise
    raise last_exc


class SheetsCache:
    """Simple TTL cache for Google Sheets reads (default 60s)."""

    def __init__(self, ttl_seconds: int = 60):
        self._cache: dict = {}
        self._timestamps: dict = {}
        self.ttl = ttl_seconds

    def get(self, key: str):
        if key in self._cache:
            if time.time() - self._timestamps[key] < self.ttl:
                return self._cache[key]
        return None

    def set(self, key: str, value):
        self._cache[key] = value
        self._timestamps[key] = time.time()

    def invalidate(self, key: str = None):
        if key:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._timestamps.clear()

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def safe_float(value, default: float = 0.0) -> float:
    """Convert value to float safely, handling European number formats.

    Handles:
    - None / empty string → default
    - Already numeric (int/float) → direct cast
    - '2,735.00' (comma as thousands separator) → 2735.0
    - '1.234,56' (European decimal comma) → 1234.56
    - '-123.45' → -123.45

    T-154: float('2,735.00') crashes on European comma-as-thousands-separator.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        s = str(value).strip()
        if not s:
            return default
        # Remove spaces used as thousand separators
        s = s.replace(" ", "")
        # European format: 1.234,56 → decimal comma, dot as thousands
        # Detect if comma is decimal separator (e.g. '1234,56' or '1.234,56')
        if "," in s and "." in s:
            # Both present: whichever comes last is the decimal separator
            if s.rfind(",") > s.rfind("."):
                # '1.234,56' → '1234.56'
                s = s.replace(".", "").replace(",", ".")
            else:
                # '1,234.56' → '1234.56' (standard US/UK format with thousands comma)
                s = s.replace(",", "")
        elif "," in s:
            # Only comma: could be thousands ('2,735') or decimal ('12,5')
            # If digits after comma > 2 → thousands separator
            parts = s.split(",")
            if len(parts) == 2 and len(parts[1]) > 2:
                # '2,735' → thousands separator
                s = s.replace(",", "")
            else:
                # '12,50' → decimal comma
                s = s.replace(",", ".")
        return float(s)
    except (ValueError, TypeError):
        return default


def get_sheets_client() -> gspread.Client:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT", "")
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT env var not set")
    creds_dict = json.loads(base64.b64decode(raw))
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


class AdminSheets:
    """Reads/writes the central Admin Google Sheets file."""

    def __init__(self, client: gspread.Client):
        self.client = client
        self.sheet_id = os.environ["ADMIN_SHEETS_ID"]
        self._wb = None

    def _workbook(self):
        if not self._wb:
            self._wb = self.client.open_by_key(self.sheet_id)
        return self._wb

    def _ws(self, name: str):
        return self._workbook().worksheet(name)

    # ── Config ────────────────────────────────────────────────────────────

    def read_config(self) -> dict:
        ws = self._ws("Config")
        rows = ws.get_all_values()
        return {row[0]: row[1] for row in rows if len(row) >= 2 and row[0]}

    def write_config(self, key: str, value: str):
        ws = self._ws("Config")
        # T-120: write numeric values as numbers (not text with ' prefix)
        write_val: str | int | float = value
        if isinstance(value, str):
            stripped = value.strip()
            try:
                write_val = int(stripped) if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()) else float(stripped) if "." in stripped else value
            except (ValueError, IndexError):
                write_val = value
        rows = ws.get_all_values()
        for i, row in enumerate(rows):
            if row and row[0] == key:
                ws.update_cell(i + 1, 2, write_val)
                return
        ws.append_row([key, write_val])

    # ── Dashboard config ──────────────────────────────────────────────────

    # Default dashboard settings (used if DashboardConfig tab not found)
    DASHBOARD_DEFAULTS = {
        "auto_refresh_on_transaction": "FALSE",
        "show_contribution_history": "TRUE",
        "history_months": "3",
        "budget_warning_pct": "80",
        "show_category_breakdown": "TRUE",
        "master_template_id": "",   # empty = use MM_BUDGET_FILE_ID env var
        "mode": "prod",             # "prod" or "test"
        "test_file_id": "",         # override file ID in test mode
    }

    def get_dashboard_config(self) -> dict:
        """Read DashboardConfig tab from Admin sheet. Falls back to defaults if tab missing."""
        try:
            ws = self._ws("DashboardConfig")
            rows = ws.get_all_values()
            cfg = dict(self.DASHBOARD_DEFAULTS)
            cfg.update({row[0]: row[1] for row in rows if len(row) >= 2 and row[0]})
            return cfg
        except Exception:
            return dict(self.DASHBOARD_DEFAULTS)

    def write_dashboard_config(self, key: str, value: str):
        """Write a single key-value to DashboardConfig tab. Creates tab if missing."""
        try:
            ws = self._ws("DashboardConfig")
        except Exception:
            wb = self._workbook()
            ws = wb.add_worksheet(title="DashboardConfig", rows=30, cols=3)
            ws.update("A1", [["Key", "Value", "Description"]])
            for k, v in self.DASHBOARD_DEFAULTS.items():
                ws.append_row([k, v, ""])
        rows = ws.get_all_values()
        for i, row in enumerate(rows):
            if row and row[0] == key:
                ws.update_cell(i + 1, 2, value)
                return
        ws.append_row([key, value, ""])

    # ── Envelopes registry ────────────────────────────────────────────────

    def get_envelopes(self) -> list[dict]:
        ws = self._ws("Envelopes")
        return ws.get_all_records()

    def get_envelope(self, envelope_id: str) -> Optional[dict]:
        for env in self.get_envelopes():
            if env.get("ID") == envelope_id:
                return env
        return None

    def register_envelope(self, data: dict):
        ws = self._ws("Envelopes")
        headers = ws.row_values(1)
        row = [data.get(h, "") for h in headers]
        ws.append_row(row)

    # ── Users ─────────────────────────────────────────────────────────────

    def get_users(self) -> list[dict]:
        ws = self._ws("Users")
        return ws.get_all_records()

    def add_user(self, telegram_id: int, name: str, role: str, envelope_ids: list[str]):
        ws = self._ws("Users")
        ws.append_row([
            telegram_id, name, role,
            ",".join(envelope_ids),
            datetime.utcnow().isoformat()
        ])

    def get_user_names(self) -> list[str]:
        """Return list of user display names from the Users tab."""
        try:
            users = self.get_users()
            names = []
            for u in users:
                name = u.get("name") or u.get("Name") or u.get("username") or ""
                if name:
                    names.append(name.strip())
            return names
        except Exception:
            return []

    def remove_user(self, telegram_id: int):
        ws = self._ws("Users")
        records = ws.get_all_records()
        for i, row in enumerate(records):
            if str(row.get("telegram_id")) == str(telegram_id):
                ws.delete_rows(i + 2)
                return

    # ── Audit log ─────────────────────────────────────────────────────────

    def log_action(self, user_id: int, user_name: str, action: str, details: str = ""):
        ws = self._ws("Audit_Log")
        ws.append_row([
            datetime.utcnow().isoformat(),
            user_id,
            user_name,
            action,
            details,
        ])

    def get_account_types(self) -> list[dict]:
        """Read account types from Admin Accounts tab.
        Returns list of {"name": str, "type": str}.
        Defaults to [Joint, Personal] if tab missing.
        """
        try:
            ws = self._ws("Accounts")
            records = ws.get_all_records()
            result = []
            for r in records:
                name = r.get("Name", "").strip()
                if not name:
                    continue
                active = str(r.get("Active", "TRUE")).upper()
                if active == "FALSE":
                    continue
                acct_type = r.get("Type", name).strip()
                result.append({"name": name, "type": acct_type})
            if result:
                return result
        except Exception:
            pass
        # Default fallback
        return [
            {"name": "Joint",    "type": "Joint"},
            {"name": "Personal", "type": "Personal"},
        ]


class EnvelopeSheets:
    """Reads/writes a single Envelope Google Sheets file."""

    def __init__(self, client: gspread.Client, sheet_id: str):
        self.client = client
        self.sheet_id = sheet_id
        self._wb = None

    def _workbook(self):
        if not self._wb:
            self._wb = self.client.open_by_key(self.sheet_id)
        return self._wb

    def _ws(self, name: str):
        return self._workbook().worksheet(name)

    # ── Transactions ──────────────────────────────────────────────────────

    def add_transaction(self, row: dict) -> str:
        """Add a transaction from a dict (legacy/manual path). Uses new column order."""
        ws = self._ws("Transactions")
        import uuid
        tx_id = uuid.uuid4().hex[:8]
        now = datetime.utcnow().isoformat()
        # New column order: Date, Amount_Orig, Currency_Orig, Category, Subcategory,
        # Note, Who, Amount_EUR, Type, Account, ID, Envelope, Source, Wise_ID, Created_At, Deleted
        ws.append_row([
            row.get("date", datetime.utcnow().strftime("%Y-%m-%d")),  # A
            row.get("amount_orig", ""),                                # B
            row.get("currency_orig", "EUR"),                           # C
            row.get("category", ""),                                   # D
            row.get("subcategory", ""),                                # E
            row.get("note", ""),                                       # F
            row.get("who", ""),                                        # G
            row.get("amount_eur", ""),                                 # H
            row.get("type", "expense"),                                # I
            row.get("account", ""),                                    # J
            tx_id,                                                     # K
            row.get("envelope", ""),                                   # L
            row.get("source", "bot"),                                  # M
            row.get("wise_id", ""),                                    # N
            now,                                                       # O
            "FALSE",                                                   # P
        ])
        return tx_id

    # ── Reference data ────────────────────────────────────────────────────

    def get_categories(self) -> list[dict]:
        """Read categories from the Categories tab.
        Each row: Category, Subcategory (optional), Description (optional).
        Returns list of dicts with 'category' and 'subcategory' keys.
        If the tab doesn't exist, falls back to unique values from Transactions."""
        try:
            ws = self._ws("Categories")
            records = ws.get_all_records()
            if records:
                return records
        except Exception:
            pass
        # Fallback: derive unique categories from existing transactions
        try:
            ws = self._ws("Transactions")
            all_values = ws.get_all_values()
            if not all_values:
                return []
            headers = all_values[0]
            cat_idx = headers.index("Category") if "Category" in headers else -1
            sub_idx = headers.index("Subcategory") if "Subcategory" in headers else -1
            seen = {}
            for row in all_values[1:]:
                padded = row + [""] * max(0, len(headers) - len(row))
                if padded[cat_idx].strip() if cat_idx >= 0 else "":
                    cat = padded[cat_idx].strip()
                    sub = padded[sub_idx].strip() if sub_idx >= 0 else ""
                    if cat not in seen:
                        seen[cat] = set()
                    if sub:
                        seen[cat].add(sub)
            result = []
            for cat, subs in seen.items():
                if subs:
                    for sub in sorted(subs):
                        result.append({"Category": cat, "Subcategory": sub})
                else:
                    result.append({"Category": cat, "Subcategory": ""})
            return result
        except Exception:
            return []

    def get_accounts_with_types(self) -> list[dict]:
        """Read accounts with type info from the Accounts tab.
        Returns list of {"name": str, "type": "Joint"|"Personal"|""}.
        T-087: supports Joint/Personal account classification.
        """
        try:
            ws = self._ws("Accounts")
            records = ws.get_all_records()
            if records:
                result = []
                for r in records:
                    name = r.get("Account", r.get("Name", "")).strip()
                    if not name:
                        continue
                    acct_type = str(r.get("Type", "")).strip()
                    if acct_type.lower() in ("joint", "загальний", "общий"):
                        acct_type = "Joint"
                    elif acct_type.lower() in ("personal", "особистий", "личный"):
                        acct_type = "Personal"
                    else:
                        acct_type = ""
                    result.append({"name": name, "type": acct_type})
                if result:
                    return result
        except Exception:
            pass
        # Fallback: derive from transactions (no type info)
        try:
            ws = self._ws("Transactions")
            all_values = ws.get_all_values()
            if not all_values:
                return []
            headers = all_values[0]
            acc_idx = headers.index("Account") if "Account" in headers else -1
            if acc_idx < 0:
                return []
            accounts = set()
            for row in all_values[1:]:
                padded = row + [""] * max(0, len(headers) - len(row))
                acc = padded[acc_idx].strip()
                if acc:
                    accounts.add(acc)
            return [{"name": a, "type": ""} for a in sorted(accounts)]
        except Exception:
            return []

    def get_accounts(self) -> list[str]:
        """Read account names from the Accounts tab (backward-compat wrapper)."""
        return [a["name"] for a in self.get_accounts_with_types()]

    def get_transactions(self, filters: dict = None) -> list[dict]:
        ws = self._ws("Transactions")
        all_values = _sheets_retry(ws.get_all_values)
        if not all_values:
            return []
        headers = all_values[0]
        records = []
        for i, row in enumerate(all_values[1:], start=2):  # row 2 = first data row
            padded = row + [""] * max(0, len(headers) - len(row))
            rec = dict(zip(headers, padded))
            rec["_row"] = i  # physical sheet row number (header=1, data starts at 2)
            records.append(rec)
        active = [r for r in records if str(r.get("Deleted", "FALSE")).upper() != "TRUE"]
        if not filters:
            return active
        result = active
        if filters.get("date_from"):
            result = [r for r in result if r.get("Date", "") >= filters["date_from"]]
        if filters.get("date_to"):
            result = [r for r in result if r.get("Date", "") <= filters["date_to"]]
        if filters.get("category"):
            result = [r for r in result if filters["category"].lower() in r.get("Category", "").lower()]
        if filters.get("who"):
            result = [r for r in result if r.get("Who", "") == filters["who"]]
        if filters.get("note_contains"):
            result = [r for r in result if filters["note_contains"].lower() in r.get("Note", "").lower()]
        return result[:filters.get("limit", 10)]

    def edit_transaction(self, tx_id: str, field: str, new_value: str) -> bool:
        ws = self._ws("Transactions")
        records = ws.get_all_records()
        headers = ws.row_values(1)
        for i, row in enumerate(records):
            if row.get("ID") == tx_id:
                col = headers.index(field) + 1
                ws.update_cell(i + 2, col, new_value)
                # Update Modified_At if column exists
                if "Modified_At" in headers:
                    mod_col = headers.index("Modified_At") + 1
                    ws.update_cell(i + 2, mod_col, datetime.utcnow().isoformat())
                return True
        return False

    def delete_transaction(self, tx_id: str) -> bool:
        """Soft-delete: set Deleted=TRUE (kept for backward compat, prefer hard_delete_by_tx_id)."""
        return self.edit_transaction(tx_id, "Deleted", "TRUE")

    def batch_hard_delete_by_tx_ids(self, tx_ids: list) -> dict:
        """
        T-194: Batch hard-delete multiple rows in ONE sheet read.
        Reads all_values once, finds row numbers for all tx_ids, then deletes
        in reverse row order (prevents row-index drift).
        Returns: {"deleted": [...tx_ids...], "not_found": [...tx_ids...]}
        Raises on Sheets API error.
        """
        ws = self._ws("Transactions")
        all_values = _sheets_retry(ws.get_all_values)
        deleted_ids: list = []
        not_found_ids: list = []
        if not all_values:
            return {"deleted": deleted_ids, "not_found": list(tx_ids)}
        headers = all_values[0]
        try:
            id_col = headers.index("ID")
        except ValueError:
            return {"deleted": deleted_ids, "not_found": list(tx_ids)}
        tx_ids_stripped = {str(tid).strip(): str(tid) for tid in tx_ids}
        found_rows: dict = {}  # stripped_tx_id → row_number (1-based)
        for i, row in enumerate(all_values[1:], start=2):
            padded = row + [""] * max(0, len(headers) - len(row))
            row_id = padded[id_col].strip()
            if row_id in tx_ids_stripped:
                found_rows[row_id] = i
        # Delete in reverse order to avoid row-index shifts
        for stripped_id, row_num in sorted(found_rows.items(), key=lambda x: x[1], reverse=True):
            _sheets_retry(ws.delete_rows, row_num)
            deleted_ids.append(tx_ids_stripped[stripped_id])
        not_found_ids = [
            tx_ids_stripped[s] for s in tx_ids_stripped if s not in found_rows
        ]
        return {"deleted": deleted_ids, "not_found": not_found_ids}

    def hard_delete_by_tx_id(self, tx_id: str) -> bool:
        """
        Physically remove the row matching tx_id from the Transactions sheet.
        Returns True if row was found and deleted, False if tx_id not found.
        Raises on Sheets API error.
        """
        ws = self._ws("Transactions")
        all_values = _sheets_retry(ws.get_all_values)
        if not all_values:
            return False
        headers = all_values[0]
        try:
            id_col = headers.index("ID")
        except ValueError:
            return False

        # Normalise tx_id: strip whitespace for comparison
        tx_id_stripped = tx_id.strip()

        # Find the physical row number (1-based; row 1 = header)
        target_row = None
        for i, row in enumerate(all_values[1:], start=2):
            padded = row + [""] * max(0, len(headers) - len(row))
            if padded[id_col].strip() == tx_id_stripped:
                target_row = i
                break

        if target_row is None:
            return False

        _sheets_retry(ws.delete_rows, target_row)

        # Post-delete verification: confirm the row is actually gone
        # (gspread delete_rows can fail silently on quota errors)
        try:
            check_values = ws.get_all_values()
            for row in check_values[1:]:
                padded = row + [""] * max(0, len(check_values[0]) - len(row))
                if len(padded) > id_col and padded[id_col].strip() == tx_id_stripped:
                    # Row is still there — deletion did not take effect
                    raise RuntimeError(
                        f"delete_rows called for row {target_row} but "
                        f"tx_id {tx_id_stripped} is still present in sheet"
                    )
        except RuntimeError:
            raise  # propagate verification failure
        except Exception:
            pass  # non-critical: if re-read fails, trust the original call

        return True

    def get_rows_raw(self, start_row: int, end_row: int) -> list[list]:
        """Return raw cell values for rows start_row..end_row (1-based) from Transactions."""
        ws = self._ws("Transactions")
        all_rows = ws.get_all_values()
        result = []
        for r in range(start_row, end_row + 1):
            if r <= len(all_rows):
                result.append(all_rows[r - 1])
            else:
                result.append([])
        return result

    def delete_rows_hard(self, start_row: int, end_row: int) -> int:
        """Physically delete rows start_row..end_row (1-based, inclusive) from Transactions sheet.
        Row 1 is the header — caller must ensure start_row >= 2.
        Returns number of rows deleted."""
        ws = self._ws("Transactions")
        # gspread delete_rows(start_index, end_index) is 1-based, inclusive
        ws.delete_rows(start_row, end_row)
        return end_row - start_row + 1

    def sort_by_date(self, order: str = "asc") -> int:
        """Sort Transactions data rows by Date (col A) in-place.
        Header (row 1) is preserved. Returns number of rows sorted.
        order: 'asc' (oldest first) or 'desc' (newest first)."""
        ws = self._ws("Transactions")
        all_rows = ws.get_all_values()
        if len(all_rows) < 2:
            return 0

        header = all_rows[0]
        data_rows = [r for r in all_rows[1:] if any(cell.strip() for cell in r)]
        if not data_rows:
            return 0

        # Pad rows to header width so the update range is uniform
        width = len(header)
        padded = [r + [""] * max(0, width - len(r)) for r in data_rows]

        # ISO dates (YYYY-MM-DD) sort correctly as strings; empty dates go last
        reverse = (order.lower() == "desc")
        padded.sort(key=lambda r: r[0] if r[0].strip() else "9999-99-99",
                    reverse=reverse)

        # Overwrite data area with sorted rows (single API call)
        end_row = 1 + len(padded)
        col_letter = chr(ord('A') + width - 1)  # e.g. 'P' for 16 columns
        ws.update(f"A2:{col_letter}{end_row}", padded,
                  value_input_option="USER_ENTERED")
        return len(padded)

    def sum_expenses(self, month: str) -> float:
        txs = self.get_transactions({"date_from": f"{month}-01", "date_to": f"{month}-31"})
        return sum(
            safe_float(t.get("Amount_EUR", 0))
            for t in txs
            if t.get("Type", "expense") == "expense"
        )

    # ── Config ────────────────────────────────────────────────────────────

    def read_config(self) -> dict:
        ws = self._ws("Config")
        rows = ws.get_all_values()
        return {row[0]: row[1] for row in rows if len(row) >= 2 and row[0]}

    # ── Dashboard writer ─────────────────────────────────────────────────

    def update_dashboard(self, snap: dict, contrib_snap: dict = None,
                          contrib_history: list = None,
                          cumulative: dict = None) -> None:
        """
        Dashboard v2 — structured key-value format.
        Both humans (Google Sheets) and bot (get_dashboard_snapshot) can read it.

        Layout:
          Section A (rows 1-12):  SNAPSHOT — key-value pairs
          Section B1 (rows 14+):  CUMULATIVE_BALANCE — static, all-time per-user balance
          Section B2 (rows after): USER_BALANCE — current month obligation/credit
          Section C (rows after): CATEGORIES — table with headers
          Section D (rows after): HISTORY — monthly table
        """
        import logging as _logging
        _log = _logging.getLogger(__name__)
        try:
            ws = self._ws("Dashboard")
            ws.clear()
            # Remove any leftover merged cells — merges survive clear()
            # and block writes to non-anchor cells (e.g. B2 in a merged A2:B2)
            sheet_id = ws.id
            wb = ws.spreadsheet
            meta = wb.fetch_sheet_metadata()
            requests = []
            for s in meta.get("sheets", []):
                if s["properties"]["sheetId"] == sheet_id:
                    merges = s.get("merges", [])
                    if merges:
                        requests.extend(
                            {"unmergeCells": {"range": m}} for m in merges
                        )
                    break
            # Reset all cell formatting — old formats (date, %, currency)
            # corrupt new formula outputs. Must clear after ws.clear()
            # which only removes values, not formatting.
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "NUMBER", "pattern": ""},
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            })
            if requests:
                wb.batch_update({"requests": requests})

            month = snap.get("month", datetime.utcnow().strftime("%Y-%m"))
            cap = snap.get("cap", 0)
            spent = snap.get("spent", 0)
            remaining = snap.get("remaining", cap - spent)
            pct = snap.get("pct_used", 0)
            cur = snap.get("currency", "EUR")
            pace = snap.get("pace_status", "")
            days_left = snap.get("days_left", 0)
            daily_avg = snap.get("daily_avg", 0)
            daily_budget = remaining / days_left if days_left > 0 else 0

            rows = []

            # ── Helper: Transactions formula filters ─────────────────────
            # Transactions columns: A=Date H=Amount_EUR I=Type J=Account G=Who P=Deleted
            _R = "Transactions!$A$2:$A$1000"        # Date range
            _H = "Transactions!$H$2:$H$1000"        # Amount_EUR
            _I = "Transactions!$I$2:$I$1000"         # Type
            _J = "Transactions!$J$2:$J$1000"         # Account
            _G = "Transactions!$G$2:$G$1000"         # Who
            _P = "Transactions!$P$2:$P$1000"         # Deleted
            _D = "Transactions!$D$2:$D$1000"         # Category
            _ND = f'({_P}<>"TRUE")'                  # not deleted
            _CM = f'(TEXT({_R},"yyyy-mm")=B2)'        # current month (dates are serials)

            # ── Section A: SNAPSHOT — all formulas ───────────────────────
            rows.append(["[SNAPSHOT]", "", "", "", ""])          # row 1
            # Prefix with ' to force text — USER_ENTERED interprets "2026-04" as date serial
            current_month = "'" + datetime.utcnow().strftime("%Y-%m")
            rows.append(["month", current_month, "", "", ""])  # row 2
            rows.append(["budget", '=VLOOKUP("monthly_cap",Config!A:B,2,FALSE)', "", "", ""])  # row 3
            rows.append(["spent",  f'=SUMPRODUCT(({_I}="expense")*{_ND}*{_CM}*{_H})', "", "", ""])  # row 4
            rows.append(["remaining", "=B3-B4", "", "", ""])     # row 5
            rows.append(["pct_used", '=IF(B3>0,B4/B3*100,0)', "", "", ""])  # row 6
            rows.append(["pace", '=IF(B6>(DAY(TODAY())/DAY(EOMONTH(TODAY(),0))*100),"over_pace","under_pace")', "", "", ""])  # row 7
            rows.append(["currency", '=VLOOKUP("currency",Config!A:B,2,FALSE)', "", "", ""])  # row 8
            rows.append(["days_left", '=EOMONTH(TODAY(),0)-TODAY()', "", "", ""])  # row 9
            rows.append(["daily_avg", '=IF(DAY(TODAY())>1,B4/(DAY(TODAY())-1),B4)', "", "", ""])  # row 10
            rows.append(["daily_budget", '=IF(B9>0,B5/B9,0)', "", "", ""])  # row 11
            rows.append(["updated_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "", "", ""])
            rows.append(["", "", "", "", ""])

            # ── Section B: HISTORY — unified per-user per-month table ──────────
            # Replaces CUMULATIVE_BALANCE + USER_BALANCE + CATEGORIES + HISTORY.
            # Base columns: Month | Spent | Budget | Pct
            # Per-user group (5 cols each): {u}_min | {u}_topup | {u}_exp_joint | {u}_exp_personal | {u}_balance
            # TOTAL row at bottom = cumulative SUM across all months.
            # All values are Sheets formulas keyed on A-column (month text) — self-updating.
            rows.append(["[HISTORY]", "", "", "", ""])
            if contrib_history:
                all_users: list = []
                for h in contrib_history:
                    for u in h.get("split_users", []):
                        if u not in all_users:
                            all_users.append(u)

                # Header row
                h_header = ["Month", "Spent", "Budget", "Pct"]
                for u in all_users:
                    h_header += [
                        f"{u}_min",
                        f"{u}_topup",
                        f"{u}_exp_joint",
                        f"{u}_exp_personal",
                        f"{u}_balance",
                    ]
                rows.append(h_header)

                # Helper: month-match for a given row referencing A{row}
                def _month_match(row_n: int) -> str:
                    return f'(TEXT({_R},"yyyy-mm")=A{row_n})'

                # total_min_pool formula (sum of all users' min from Config)
                f_total_min_cfg = "+".join(
                    f'VLOOKUP("min_{uu}",Config!A:B,2,FALSE)' for uu in all_users
                )

                ok_months = [h for h in contrib_history if h.get("status") == "ok"]
                first_data_row: int | None = None

                for h in ok_months:
                    h_month = "'" + h.get("month", "") if h.get("month") else ""
                    r = len(rows) + 1  # 1-indexed row this entry will occupy in the sheet
                    if first_data_row is None:
                        first_data_row = r
                    _HM = _month_match(r)

                    # Base columns
                    f_spent  = f'=SUMPRODUCT(({_I}="expense")*{_ND}*{_HM}*{_H})'
                    f_budget = '=VLOOKUP("monthly_cap",Config!A:B,2,FALSE)'
                    f_pct    = f'=IF(C{r}>0,B{r}/C{r}*100,0)'

                    data_row = [h_month, f_spent, f_budget, f_pct]

                    # split_base for this row = spent_this_month - total_min_pool
                    f_split_base = f"B{r}-({f_total_min_cfg})"

                    for u_idx, u in enumerate(all_users):
                        # Column indices (0-based): base=4, per-user stride=5
                        col_base = 4 + u_idx * 5
                        # Note: chr(65+n) works for up to 26 cols (Z). For >26, use _col_letter() below.
                        c_min   = chr(65 + col_base)
                        c_topup = chr(65 + col_base + 1)
                        # c_joint = chr(65 + col_base + 2)  # informational only
                        c_pers  = chr(65 + col_base + 3)
                        # c_bal   = chr(65 + col_base + 4)  # balance column itself

                        f_split_u = f'VLOOKUP("split_{u}",Config!A:B,2,FALSE)'

                        f_min_u   = f'=VLOOKUP("min_{u}",Config!A:B,2,FALSE)'
                        f_topup_u = (
                            f'=SUMPRODUCT(({_G}="{u}")*({_I}="income")*{_ND}*{_HM}*{_H})'
                        )
                        f_exp_joint_u = (
                            f'=SUMPRODUCT(({_G}="{u}")*({_I}="expense")*({_J}="Joint")*{_ND}*{_HM}*{_H})'
                        )
                        f_exp_pers_u = (
                            f'=SUMPRODUCT(({_G}="{u}")*({_I}="expense")*({_J}="Personal")*{_ND}*{_HM}*{_H})'
                        )
                        # balance = -obligation = topup - min - max(0, split_base)*split%/100 + personal_exp
                        # References own row cells for topup/min/personal so TOTAL SUM works correctly.
                        f_balance_u = (
                            f"={c_topup}{r}-{c_min}{r}"
                            f"-MAX(0,{f_split_base})*{f_split_u}/100"
                            f"+{c_pers}{r}"
                        )

                        data_row += [f_min_u, f_topup_u, f_exp_joint_u, f_exp_pers_u, f_balance_u]

                    rows.append(data_row)

                # TOTAL row — SUM across all data rows
                if ok_months and first_data_row is not None:
                    last_data = len(rows)
                    total_row: list = ["TOTAL"]
                    total_row.append(f"=SUM(B{first_data_row}:B{last_data})")   # Spent total
                    total_row.append(f"=SUM(C{first_data_row}:C{last_data})")   # Budget total (n*monthly_cap)
                    total_row.append("")                                          # Pct — not meaningful for TOTAL
                    for u_idx in range(len(all_users)):
                        col_base = 4 + u_idx * 5
                        for ci in range(5):
                            c = chr(65 + col_base + ci)
                            total_row.append(f"=SUM({c}{first_data_row}:{c}{last_data})")
                    rows.append(total_row)
            else:
                rows.append(["(no history data)", "", "", "", ""])

            # ── Write to sheet ───────────────────────────────────────────
            max_cols = max(len(r) for r in rows) if rows else 5
            for r in rows:
                while len(r) < max_cols:
                    r.append("")

            def _col_letter(n: int) -> str:
                result = ""
                while n > 0:
                    n, rem = divmod(n - 1, 26)
                    result = chr(65 + rem) + result
                return result

            end_col = _col_letter(max_cols)
            end_row = len(rows)
            ws.update(f"A1:{end_col}{end_row}", rows, value_input_option="USER_ENTERED")

        except Exception as e:
            import logging as _logging2
            _logging2.getLogger(__name__).warning(f"update_dashboard failed: {e}")



def get_credentials() -> Credentials:
    """Return raw Google Credentials (for direct gspread use)."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT", "")
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT env var not set")
    creds_dict = json.loads(base64.b64decode(raw))
    return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)


_drive_folder_cache: Optional[str] = None


def get_or_create_drive_folder(creds: Credentials,
                                folder_name: str = "Apolio Home") -> Optional[str]:
    """Return the Drive folder ID for the project, creating it if needed.
    Uses the service-account Drive — files are visible to the SA, not Mikhail.
    Returns None on any error so callers can fall back gracefully."""
    global _drive_folder_cache
    if _drive_folder_cache:
        return _drive_folder_cache
    try:
        from googleapiclient.discovery import build as google_build
        drive = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        # Search for existing folder
        q = (f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
             " and trashed=false")
        results = drive.files().list(q=q, fields="files(id,name)").execute()
        files = results.get("files", [])
        if files:
            _drive_folder_cache = files[0]["id"]
            return _drive_folder_cache
        # Create it
        meta = {"name": folder_name,
                "mimeType": "application/vnd.google-apps.folder"}
        folder = drive.files().create(body=meta, fields="id").execute()
        _drive_folder_cache = folder["id"]
        return _drive_folder_cache
    except Exception as e:
        print(f"[Drive] Could not get/create folder: {e}")
        return None


class SheetsClient:
    """Unified facade over AdminSheets + EnvelopeSheets.

    Single object passed through bot -> agent -> tools.

    T-152: TTL strategy to avoid 429 ReadRequestsPerMinutePerUser.
    - Static admin data (envelopes, users, dashboard config): 300s
    - Envelope config (monthly_cap, split_rule): 120s
    - Transactions: 60s (invalidated on every add/edit/delete)
    - Snapshots from intelligence.py: 30s (via separate snapshot_cache)
    """

    def __init__(self):
        self._gc = get_sheets_client()
        self._admin = AdminSheets(self._gc)
        self._cache = SheetsCache(ttl_seconds=60)          # default TTL
        self._static_cache = SheetsCache(ttl_seconds=300)  # envelopes/users/dashcfg
        self._cfg_cache = SheetsCache(ttl_seconds=120)     # env configs
        self.snapshot_cache = SheetsCache(ttl_seconds=30)  # intelligence snapshots

    @property
    def admin(self):
        """Raw gspread Spreadsheet for the Admin file."""
        return self._admin._workbook()

    # Admin pass-throughs (with TTL cache to avoid 429 rate-limit errors)
    def get_envelopes(self) -> list:
        cached = self._static_cache.get("admin_envelopes")
        if cached is not None:
            return cached
        result = self._admin.get_envelopes()
        self._static_cache.set("admin_envelopes", result)
        return result

    def list_envelopes_with_links(self) -> list[dict]:
        """Return active envelopes with Google Sheets URLs included.

        T-135: monthly_cap and split_rule are read from envelope Config tab
        (single source of truth), NOT from Admin Envelopes columns.
        """
        envelopes = self.get_envelopes()  # uses cache
        result = []
        for e in envelopes:
            if str(e.get("Active", "TRUE")).upper() == "FALSE":
                continue
            file_id = e.get("file_id", "")
            url = f"https://docs.google.com/spreadsheets/d/{file_id}" if file_id else ""
            # Read canonical values from envelope's own Config tab
            env_cfg = {}
            if file_id:
                try:
                    env_cfg = self.read_envelope_config(file_id)
                except Exception:
                    pass
            result.append({
                "id": e.get("ID", ""),
                "name": e.get("Name", ""),
                "currency": env_cfg.get("currency") or e.get("Currency", "EUR"),
                "monthly_cap": safe_float(env_cfg.get("monthly_cap") or 0),
                "split_rule": env_cfg.get("split_rule") or "solo",
                "file_id": file_id,
                "url": url,
            })
        return result

    def get_users(self) -> list:
        cached = self._static_cache.get("admin_users")
        if cached is not None:
            return cached
        result = self._admin.get_users()
        self._static_cache.set("admin_users", result)
        return result

    def read_config(self) -> dict:
        """Read global settings from Admin Config tab."""
        cached = self._cache.get("admin_config")
        if cached is not None:
            return cached
        result = self._admin.read_config()
        self._cache.set("admin_config", result)
        return result

    def write_config(self, key: str, value: str):
        self._admin.write_config(key, value)
        self._cache.invalidate("admin_config")

    def read_envelope_config(self, file_id: str) -> dict:
        """Read settings from the envelope's own Config tab.

        Envelope-specific keys (split_rule, split_threshold, split_users,
        base_contributor, budget_cap, etc.) live HERE, not in Admin Config.
        Returns empty dict if file_id is blank or tab is missing.
        """
        if not file_id:
            return {}
        cache_key = f"env_config_{file_id}"
        cached = self._cfg_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            result = self._env_sheets(file_id).read_config()
            self._cfg_cache.set(cache_key, result)
            return result
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                f"read_envelope_config({file_id}): {e}"
            )
            return {}

    def ensure_envelope_config(self, envelope_id: str) -> dict:
        """Check envelope's Config tab and write any missing split/budget keys.

        Reads defaults from the Envelopes registry (Monthly_Cap, Split_Rule, etc.).
        Only writes keys that are not already present — never overwrites existing values.
        Returns a dict with keys: written (list), skipped (list), error (str|None).
        """
        import logging as _logging
        _log = _logging.getLogger(__name__)
        try:
            envelopes = self.get_envelopes()
            env = next((e for e in envelopes if e.get("ID") == envelope_id), None)
            if not env:
                return {"written": [], "skipped": [], "error": f"Envelope {envelope_id!r} not found"}

            file_id = env.get("file_id", "")
            if not file_id:
                return {"written": [], "skipped": [], "error": "No file_id for this envelope"}

            env_sheets = self._env_sheets(file_id)
            existing = env_sheets.read_config()

            # Infer active users for this envelope from Users sheet
            users = self.get_users()
            active_users = [
                u.get("name", "") for u in users
                if envelope_id in str(u.get("envelopes", ""))
                and str(u.get("status", "active")).lower() == "active"
            ]
            split_users_default = ",".join(active_users) if active_users else ""

            # Per-user min/split defaults:
            # - admin user gets Monthly_Cap from Envelopes registry as their min
            # - other users get 0
            # - split % is equal share across all users
            threshold_default = str(env.get("Monthly_Cap", "0") or "0")
            per_user_defaults: dict[str, str] = {}
            for u in active_users:
                is_admin = any(
                    usr.get("name") == u and usr.get("role") == "admin"
                    for usr in users
                )
                per_user_defaults[f"min_{u}"] = threshold_default if is_admin else "0"
                per_user_defaults[f"split_{u}"] = str(
                    round(100 / len(active_users)) if active_users else 50
                )

            DEFAULTS = {
                "currency":    env.get("Currency", "EUR"),
                "monthly_cap": str(int(safe_float(env.get("Monthly_Cap", 0) or 0))),
                "split_rule":  str(env.get("Split_Rule", "50_50") or "50_50"),
                "split_users": split_users_default,
                "base_contributor": active_users[0] if active_users else "",
                "split_threshold": threshold_default,
                **per_user_defaults,
            }

            written, skipped = [], []
            for key, default_val in DEFAULTS.items():
                if key in existing:
                    skipped.append(key)
                else:
                    env_sheets.write_config(key, default_val)
                    written.append(f"{key}={default_val}")
                    _log.info(f"[ensure_envelope_config] {envelope_id}: wrote {key}={default_val!r}")

            # Invalidate envelope config cache if we wrote new keys
            if written:
                self._cfg_cache.invalidate(f"env_config_{file_id}")
            return {"written": written, "skipped": skipped, "error": None}

        except Exception as e:
            _log.error(f"ensure_envelope_config({envelope_id}): {e}", exc_info=True)
            return {"written": [], "skipped": [], "error": str(e)}

    def get_dashboard_config(self) -> dict:
        cached = self._cache.get("admin_dashboard_config")
        if cached is not None:
            return cached
        result = self._admin.get_dashboard_config()
        self._cache.set("admin_dashboard_config", result)
        return result

    def write_dashboard_config(self, key: str, value: str):
        self._admin.write_dashboard_config(key, value)
        self._cache.invalidate("admin_dashboard_config")

    def register_envelope(self, envelope_id: str, name: str, file_id: str,
                          owner_id: int, settings: dict):
        data = {
            "ID": envelope_id,
            "Name": name,
            "file_id": file_id,
            "Owner_TG": str(owner_id),
            "Currency": settings.get("currency", "EUR"),
            "Monthly_Cap": settings.get("monthly_cap", 0),
            "Split_Rule": settings.get("split_rule", "solo"),
            "Active": "TRUE",
            "Created_At": datetime.utcnow().isoformat(),
        }
        self._admin.register_envelope(data)
        self._static_cache.invalidate("admin_envelopes")

    def write_audit(self, user_id: int, user_name: str, action: str,
                    envelope_id: str, details: str = ""):
        detail_str = f"[{envelope_id}] {details}" if envelope_id else details
        self._admin.log_action(user_id, user_name, action, detail_str)

    # Envelope operations
    def _env_sheets(self, sheet_id: str) -> EnvelopeSheets:
        return EnvelopeSheets(self._gc, sheet_id)

    def add_transaction(self, sheet_id: str, row) -> str:
        """Accept either a pre-formatted list (from tools) or a dict."""
        # Invalidate cache so next read reflects the new row
        self._cache.invalidate(f"txns_{sheet_id}")
        if isinstance(row, list):
            env = self._env_sheets(sheet_id)
            # T-183: wrap with retry — batch writes trigger 429 after ~4 rapid requests
            _sheets_retry(env._ws("Transactions").append_row, row)
            return row[10]  # tx_id is at index 10 (col K) in new column order
        return self._env_sheets(sheet_id).add_transaction(row)

    def get_transactions(self, sheet_id: str, filters: dict = None) -> list:
        cache_key = f"txns_{sheet_id}"
        if filters is None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        result = self._env_sheets(sheet_id).get_transactions(filters)
        if filters is None:
            self._cache.set(cache_key, result)
        return result

    def update_transaction_field(self, sheet_id: str, tx_id: str,
                                 field: str, value: str) -> bool:
        return self._env_sheets(sheet_id).edit_transaction(tx_id, field, value)

    def soft_delete_transaction(self, sheet_id: str, tx_id: str) -> bool:
        """Soft-delete: sets Deleted=TRUE flag. Kept for backward compat."""
        return self._env_sheets(sheet_id).delete_transaction(tx_id)

    def hard_delete_transaction(self, sheet_id: str, tx_id: str) -> bool:
        """Physically remove the row for tx_id from the Transactions sheet."""
        self._cache.invalidate(f"txns_{sheet_id}")
        return self._env_sheets(sheet_id).hard_delete_by_tx_id(tx_id)

    def batch_hard_delete_transactions(self, sheet_id: str, tx_ids: list) -> dict:
        """T-194: Batch hard-delete — ONE sheet read, N deletes (no per-item quota hit).
        Returns: {"deleted": [...], "not_found": [...]}"""
        self._cache.invalidate(f"txns_{sheet_id}")
        return self._env_sheets(sheet_id).batch_hard_delete_by_tx_ids(tx_ids)

    def delete_transaction_rows(self, sheet_id: str, start_row: int, end_row: int) -> int:
        """Physically delete rows start_row..end_row from Transactions sheet.
        Invalidates cache after deletion."""
        self._cache.invalidate(f"txns_{sheet_id}")
        return self._env_sheets(sheet_id).delete_rows_hard(start_row, end_row)

    def get_transaction_rows_preview(self, sheet_id: str,
                                      start_row: int, end_row: int) -> list[list]:
        """Return raw cell values for preview before deletion."""
        return self._env_sheets(sheet_id).get_rows_raw(start_row, end_row)

    def sort_transactions_by_date(self, sheet_id: str, order: str = "asc") -> int:
        """Sort Transactions sheet by date and invalidate cache."""
        self._cache.invalidate(f"txns_{sheet_id}")
        return self._env_sheets(sheet_id).sort_by_date(order)

    def get_reference_data(self, sheet_id: str) -> dict:
        """Return all reference lists for the given envelope:
        categories, subcategories, accounts, known users (from Admin), currencies.
        Used for input validation before recording transactions."""
        cache_key = f"ref_{sheet_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        env = self._env_sheets(sheet_id)

        # Categories + subcategories
        cat_records = env.get_categories()
        categories = sorted({r.get("Category", "") for r in cat_records if r.get("Category", "")})
        subcategories = sorted({r.get("Subcategory", "") for r in cat_records if r.get("Subcategory", "")})

        # Accounts — read from Admin (global, default: Joint + Personal)
        accounts_typed = self._admin.get_account_types()
        accounts = [a["name"] for a in accounts_typed]

        # Users from Admin file
        try:
            who_values = self._admin.get_user_names()
        except Exception:
            who_values = []

        # Envelope base currency from Admin (look up by file_id)
        base_currency = "EUR"
        try:
            all_envs = self._admin.get_envelopes()
            env_meta = next((e for e in all_envs if e.get("file_id") == sheet_id), None)
            if env_meta:
                base_currency = env_meta.get("Currency", "EUR") or "EUR"
        except Exception:
            pass

        # Known currencies from FX_Rates
        currencies = [base_currency]
        try:
            fx_ws = env._ws("FX_Rates")
            fx_headers = fx_ws.row_values(1)
            for h in fx_headers:
                if h.startswith("EUR_"):
                    c = h[4:]  # e.g. "EUR_PLN" → "PLN"
                    if c and c not in currencies:
                        currencies.append(c)
        except Exception:
            pass

        result = {
            "categories": categories,
            "subcategories": subcategories,
            "accounts": accounts,            # list[str] — backward compat
            "accounts_typed": accounts_typed, # list[{name, type}] — T-087
            "who": who_values,
            "currencies": currencies,
            "base_currency": base_currency,
        }
        self._cache.set(cache_key, result)
        return result

    def update_dashboard_sheet(self, sheet_id: str, snap: dict,
                                contrib_snap: dict = None,
                                contrib_history: list = None,
                                cumulative: dict = None) -> None:
        """Write computed budget + contribution data to the Dashboard tab."""
        self._env_sheets(sheet_id).update_dashboard(snap, contrib_snap, contrib_history, cumulative)

    def read_dashboard_snapshot(self, sheet_id: str) -> dict:
        """Read the [SNAPSHOT] section from Dashboard tab as a key-value dict.
        Bot uses this for instant budget answers without recalculating all transactions."""
        cache_key = f"dashboard_snap_{sheet_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            ws = self._env_sheets(sheet_id)._ws("Dashboard")
            data = ws.get_all_values()
            result = {}
            in_section = False
            for row in data:
                if not row or not row[0]:
                    if in_section:
                        break  # empty row = end of section
                    continue
                if row[0] == "[SNAPSHOT]":
                    in_section = True
                    continue
                if row[0].startswith("["):
                    break  # next section
                if in_section:
                    result[row[0]] = row[1] if len(row) > 1 else ""
            self._cache.set(cache_key, result)
            return result
        except Exception:
            return {}

    def create_spreadsheet_as_owner(self, title: str) -> str:
        """Create a new Google Sheets file using Mikhail's OAuth credentials.
        Returns the new file ID. Falls back to service account if OAuth not configured."""
        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
        refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN")

        if not all([client_id, client_secret, refresh_token]):
            raise RuntimeError(
                "OAuth credentials not configured. Set GOOGLE_OAUTH_CLIENT_ID, "
                "GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_OAUTH_REFRESH_TOKEN in .env"
            )

        creds = OAuthCredentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        creds.refresh(Request())

        service = google_build("sheets", "v4", credentials=creds, cache_discovery=False)
        spreadsheet = service.spreadsheets().create(body={
            "properties": {"title": title}
        }).execute()

        file_id = spreadsheet["spreadsheetId"]

        # Share with service account so the bot can read/write
        sa_email = "apolio-home-bot@apolio-home.iam.gserviceaccount.com"
        drive_service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        drive_service.permissions().create(
            fileId=file_id,
            body={"type": "user", "role": "writer", "emailAddress": sa_email},
            sendNotificationEmail=False,
        ).execute()

        return file_id
