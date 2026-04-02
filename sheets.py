import os
import json
import base64
import time
import gspread
from google.oauth2.service_account import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as google_build
from datetime import datetime
from typing import Optional


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
        rows = ws.get_all_values()
        for i, row in enumerate(rows):
            if row and row[0] == key:
                ws.update_cell(i + 1, 2, value)
                return
        ws.append_row([key, value])

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

    def get_transactions(self, filters: dict = None) -> list[dict]:
        ws = self._ws("Transactions")
        all_values = ws.get_all_values()
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

    def hard_delete_by_tx_id(self, tx_id: str) -> bool:
        """
        Physically remove the row matching tx_id from the Transactions sheet.
        Returns True if a row was deleted, False if tx_id not found.
        """
        ws = self._ws("Transactions")
        all_values = ws.get_all_values()
        if not all_values:
            return False
        headers = all_values[0]
        try:
            id_col = headers.index("ID")
        except ValueError:
            return False

        # Find the physical row number (1-based; row 1 = header)
        target_row = None
        for i, row in enumerate(all_values[1:], start=2):
            padded = row + [""] * max(0, len(headers) - len(row))
            if padded[id_col] == tx_id:
                target_row = i
                break

        if target_row is None:
            return False

        ws.delete_rows(target_row)
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
            float(t.get("Amount_EUR", 0) or 0)
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
                          contrib_history: list = None) -> None:
        """
        Overwrite the Dashboard tab with budget snapshot, current month contribution
        table, and multi-month contribution history.

        Args:
            snap            = compute_snapshot() result from intelligence.py
            contrib_snap    = compute_contribution_status() for current month (optional)
            contrib_history = list of compute_contribution_status() snapshots,
                              one per month, oldest first (from compute_contribution_history)
        """
        import logging as _logging
        _log = _logging.getLogger(__name__)
        try:
            ws = self._ws("Dashboard")
            ws.clear()

            month = snap.get("month", datetime.utcnow().strftime("%Y-%m"))
            cap = snap.get("cap", 0)
            spent = snap.get("spent", 0)
            remaining = snap.get("remaining", cap - spent)
            pct = snap.get("pct_used", 0)
            cur = snap.get("currency", "EUR")
            pace = snap.get("pace_status", "")
            pace_label = {
                "on_track": "✅ В норме",
                "over_pace": "⚠️ Превышает темп",
                "under_pace": "📉 Ниже темпа",
            }.get(pace, "")

            rows = []

            # ── Header ───────────────────────────────────────────────────
            rows.append(["📊 APOLIO HOME — MM Budget", "", "", "", ""])
            rows.append(["", "", "", "", ""])
            rows.append([f"Дашборд за {month}", "", "", "", ""])
            rows.append(["", "", "", "", ""])

            # ── Budget summary (current month) ───────────────────────────
            rows.append(["Месяц:", month, "", "", ""])
            rows.append(["Лимит бюджета:", f"{cap:,.2f} {cur}", "", "", ""])
            rows.append(["Расходы:", f"{spent:,.2f} {cur}", "", "", ""])
            rows.append(["Остаток:", f"{remaining:,.2f} {cur}", "", "", ""])
            rows.append(["Использовано:", f"{pct:.1f}%", "", "", ""])
            if pace_label:
                rows.append(["Темп:", pace_label, "", "", ""])
            rows.append(["", "", "", "", ""])

            # ── Current month contribution table ─────────────────────────
            if contrib_snap and contrib_snap.get("status") == "ok":
                rows.append(["━━━ Взносы — текущий месяц ━━━", "", "", "", ""])
                rows.append([
                    "Порог (базовый взнос):",
                    f"{contrib_snap['threshold']:,.2f} {cur}",
                    "", "", "",
                ])
                rows.append([
                    "Правило сплита:",
                    contrib_snap.get("split_rule", "50_50").replace("_", "/"),
                    "", "", "",
                ])
                rows.append(["", "", "", "", ""])
                rows.append(["Пользователь", "Взнос", "Доля расходов", "Баланс", "Статус"])

                for u in contrib_snap.get("split_users", []):
                    contributed = float(contrib_snap.get("contributions", {}).get(u, 0))
                    share = float(contrib_snap.get("user_shares", {}).get(u, 0))
                    balance = float(contrib_snap.get("balances", {}).get(u, 0))
                    status = "🟢 в плюсе" if balance >= 0 else "🔴 нужно покрыть"
                    rows.append([
                        u,
                        f"{contributed:,.2f} {cur}",
                        f"{share:,.2f} {cur}",
                        f"{balance:+,.2f} {cur}",
                        status,
                    ])

                excess = contrib_snap.get("excess_amount", 0)
                if excess > 0:
                    rows.append(["", "", "", "", ""])
                    rows.append([
                        "Превышение порога:",
                        f"{excess:,.2f} {cur}",
                        f"→ по {contrib_snap.get('excess_per_user', 0):,.2f} {cur}/чел.",
                        "", "",
                    ])
                rows.append(["", "", "", "", ""])

            # ── Multi-month contribution history ─────────────────────────
            if contrib_history:
                # Collect all users across all months
                all_users: list = []
                for h in contrib_history:
                    for u in h.get("split_users", []):
                        if u not in all_users:
                            all_users.append(u)

                # Table: Month | Total expenses | [User: contributed, share, balance] per user
                # Column layout (6 cols per user): user | contributed | share | balance | status | (spacer)
                # Keep it readable: one row per month, separate sub-columns per user
                rows.append(["━━━ История взносов по месяцам ━━━", "", "", "", ""])
                rows.append(["", "", "", "", ""])

                # Build a wide table — need more than 5 cols; use column G+ for extra users
                # Row 1: header
                h_row = ["Месяц", "Расходы EUR", "Лимит EUR", "% лимита", ""]
                for u in all_users:
                    h_row += [f"{u}: внёс", f"{u}: доля", f"{u}: баланс", ""]
                rows.append(h_row)

                # Data rows
                for h in contrib_history:
                    if h.get("status") != "ok":
                        continue
                    h_cur = h.get("currency", "EUR")
                    h_threshold = h.get("threshold", 0)
                    h_spent = h.get("total_expenses", 0)
                    h_pct = f"{(h_spent / h_threshold * 100):.1f}%" if h_threshold else "—"
                    data_row = [
                        h.get("month", ""),
                        f"{h_spent:,.2f}",
                        f"{h_threshold:,.2f}",
                        h_pct,
                        "",
                    ]
                    for u in all_users:
                        contributed = float(h.get("contributions", {}).get(u, 0))
                        share = float(h.get("user_shares", {}).get(u, 0))
                        balance = float(h.get("balances", {}).get(u, 0))
                        data_row += [
                            f"{contributed:,.2f}",
                            f"{share:,.2f}",
                            f"{balance:+,.2f}",
                            "",
                        ]
                    rows.append(data_row)

                rows.append(["", "", "", "", ""])

                # ── Running totals (YTD) ──────────────────────────────────
                rows.append(["━━━ Итого за период (YTD) ━━━", "", "", "", ""])
                ytd_contrib: dict[str, float] = {u: 0.0 for u in all_users}
                ytd_share:   dict[str, float] = {u: 0.0 for u in all_users}
                ytd_spent = 0.0
                for h in contrib_history:
                    if h.get("status") != "ok":
                        continue
                    ytd_spent += float(h.get("total_expenses", 0))
                    for u in all_users:
                        ytd_contrib[u] += float(h.get("contributions", {}).get(u, 0))
                        ytd_share[u]   += float(h.get("user_shares", {}).get(u, 0))

                rows.append(["Итого расходов:", f"{ytd_spent:,.2f} {cur}", "", "", ""])
                for u in all_users:
                    balance = ytd_contrib[u] - ytd_share[u]
                    status = "🟢 в плюсе" if balance >= 0 else "🔴 нужно покрыть"
                    rows.append([
                        f"{u} — взнос:",
                        f"{ytd_contrib[u]:,.2f} {cur}",
                        f"доля: {ytd_share[u]:,.2f} {cur}",
                        f"баланс: {balance:+,.2f} {cur}",
                        status,
                    ])
                rows.append(["", "", "", "", ""])

            # ── Category breakdown ───────────────────────────────────────
            top_cats = snap.get("top_categories", {})
            if top_cats:
                rows.append(["━━━ По категориям (текущий месяц) ━━━", "", "", "", ""])
                for cat, amt in top_cats.items():
                    rows.append([f"  {cat}:", f"{amt:,.2f} {cur}", "", "", ""])
                rows.append(["", "", "", "", ""])

            # ── Recent transactions ──────────────────────────────────────
            txs = self.get_transactions({"date_from": f"{month}-01"})
            active_txs = [t for t in txs if t.get("Type") == "expense"][-10:]
            if active_txs:
                rows.append(["━━━ Последние 10 транзакций ━━━", "", "", "", ""])
                rows.append(["Дата", "Сумма EUR", "Категория", "Заметка", "Кто"])
                for t in reversed(active_txs):
                    rows.append([
                        t.get("Date", ""),
                        f"{float(t.get('Amount_EUR') or t.get('Amount_Orig') or 0):,.2f}",
                        t.get("Category", ""),
                        t.get("Note", "")[:40],
                        t.get("Who", ""),
                    ])

            rows.append(["", "", "", "", ""])
            rows.append([
                f"Обновлено: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
                "", "", "", "",
            ])

            # Determine actual column width needed
            max_cols = max(len(r) for r in rows) if rows else 5
            # Pad all rows to same width
            for r in rows:
                while len(r) < max_cols:
                    r.append("")

            def _col_letter(n: int) -> str:
                """Convert 1-based column number to letter(s): 1→A, 26→Z, 27→AA…"""
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
    """

    def __init__(self):
        self._gc = get_sheets_client()
        self._admin = AdminSheets(self._gc)
        self._cache = SheetsCache(ttl_seconds=60)

    @property
    def admin(self):
        """Raw gspread Spreadsheet for the Admin file."""
        return self._admin._workbook()

    # Admin pass-throughs
    def get_envelopes(self) -> list:
        return self._admin.get_envelopes()

    def list_envelopes_with_links(self) -> list[dict]:
        """Return active envelopes with Google Sheets URLs included."""
        envelopes = self._admin.get_envelopes()
        result = []
        for e in envelopes:
            if str(e.get("Active", "TRUE")).upper() == "FALSE":
                continue
            file_id = e.get("file_id", "")
            url = f"https://docs.google.com/spreadsheets/d/{file_id}" if file_id else ""
            result.append({
                "id": e.get("ID", ""),
                "name": e.get("Name", ""),
                "currency": e.get("Currency", "EUR"),
                "monthly_cap": e.get("Monthly_Cap", 0),
                "split_rule": e.get("Split_Rule", "solo"),
                "file_id": file_id,
                "url": url,
            })
        return result

    def get_users(self) -> list:
        return self._admin.get_users()

    def read_config(self) -> dict:
        return self._admin.read_config()

    def write_config(self, key: str, value: str):
        self._admin.write_config(key, value)

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
            env._ws("Transactions").append_row(row)
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

    def update_dashboard_sheet(self, sheet_id: str, snap: dict,
                                contrib_snap: dict = None,
                                contrib_history: list = None) -> None:
        """Write computed budget + contribution data to the Dashboard tab."""
        self._env_sheets(sheet_id).update_dashboard(snap, contrib_snap, contrib_history)

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
