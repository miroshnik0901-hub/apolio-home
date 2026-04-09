import os
import json
from datetime import datetime
from typing import Optional
from sheets import AdminSheets

DEFAULT_ENVELOPE = "MM_BUDGET"


class AuthManager:
    """
    Manages user authorization from the Admin Google Sheets Config.
    Caches for 5 minutes. Updates at runtime without redeployment.
    Bootstrap admin: MIKHAIL_TELEGRAM_ID env var (works even if Config is empty).
    """

    CACHE_TTL = 300  # seconds

    def __init__(self, admin_sheets: AdminSheets):
        self.sheets = admin_sheets
        self._cache: dict[int, dict] = {}
        self._loaded_at: Optional[datetime] = None

    def get_user(self, telegram_id: int) -> Optional[dict]:
        if self._should_reload():
            self._reload()
        cached = self._cache.get(int(telegram_id))
        if cached:
            return cached
        # Bootstrap admin always gets through even if Sheets is unavailable
        bootstrap = os.environ.get("MIKHAIL_TELEGRAM_ID", "")
        if bootstrap and str(telegram_id) == str(bootstrap):
            return {"id": int(telegram_id), "name": "Mikhail", "role": "admin", "envelopes": []}
        return None

    def is_admin(self, telegram_id: int) -> bool:
        # Bootstrap admin from env var
        bootstrap = os.environ.get("MIKHAIL_TELEGRAM_ID", "")
        if bootstrap and str(telegram_id) == str(bootstrap):
            return True
        user = self.get_user(telegram_id)
        return bool(user and user["role"] == "admin")

    def can_access_envelope(self, telegram_id: int, envelope_id: str) -> bool:
        if self.is_admin(telegram_id):
            return True
        user = self.get_user(telegram_id)
        if not user:
            return False
        allowed = user.get("envelopes", [])
        return envelope_id in allowed

    def can_write(self, telegram_id: int) -> bool:
        user = self.get_user(telegram_id)
        return bool(user and user["role"] in ("admin", "contributor"))

    def invalidate(self):
        """Force reload on next request (call after add/remove user)."""
        self._loaded_at = None

    def _should_reload(self) -> bool:
        if not self._loaded_at:
            return True
        return (datetime.now() - self._loaded_at).seconds > self.CACHE_TTL

    def _reload(self):
        try:
            users = self.sheets.get_users()
            new_cache: dict[int, dict] = {}
            for u in users:
                try:
                    raw_id = u.get("telegram_id", "") or ""
                    if not str(raw_id).strip():
                        continue  # empty telegram_id — skip silently
                    tid = int(str(raw_id).strip())
                    if not tid:
                        continue
                except (ValueError, TypeError) as exc:
                    print(f"[AuthManager] Skipping row with bad telegram_id {u.get('telegram_id')!r}: {exc}")
                    continue
                # Skip suspended users
                if u.get("status", "active").lower() == "suspended":
                    continue
                envelopes = [e.strip() for e in str(u.get("envelopes", "")).split(",") if e.strip()]
                new_cache[tid] = {
                    "id": tid,
                    "name": u.get("name", ""),
                    "role": u.get("role", "readonly"),
                    "envelopes": envelopes,
                    "language": u.get("language", "RU"),
                    "status": u.get("status", "active"),
                }
            self._cache = new_cache
            print(f"[AuthManager] Loaded {len(new_cache)} users from sheet")
        except Exception as e:
            print(f"[AuthManager] Failed to reload users: {e}")
        self._loaded_at = datetime.now()


class LastAction:
    """Records the last state-changing action for undo support."""
    def __init__(self, tx_id: str, action: str, envelope_id: str, snapshot: dict):
        self.tx_id = tx_id
        self.action = action
        self.envelope_id = envelope_id
        self.snapshot = snapshot


class SessionContext:
    """Per-user session state, persisted in memory between messages."""
    def __init__(self, user_id: int, user_name: str, role: str):
        self.user_id = user_id
        self.user_name = user_name
        self.role = role
        self.lang: str = "ru"           # default Russian; overridden to uk/it if detected
        self.current_envelope_id: Optional[str] = None
        self.last_action: Optional[LastAction] = None
        self.pending_edit_tx: Optional[str] = None
        # Stores the key of the next expected free-text input from user.
        # Format: "<domain>:<action>", e.g. "report:custom_period"
        # Set by free_text menu callbacks; cleared after use in handle_message.
        self.pending_prompt: Optional[str] = None
        # Short ID grouping messages in one conversation session.
        # Assigned on first message; used by ConversationLogger.
        self.session_id: Optional[str] = None
        # Inline choice buttons requested by the agent.
        # Format: [{"label": "✅ Да", "value": "yes"}, ...]
        # Bot.py attaches these as InlineKeyboard after the agent response, then clears.
        self.pending_choice: Optional[list] = None
        # Pending delete state
        self.pending_delete: Optional[dict] = None
        # Pending receipt: parsed data from photo analysis awaiting user confirmation.
        # Format: {"merchant": str, "total_amount": float, "currency": str,
        #          "date": str, "items": list, "category": str, "subcategory": str,
        #          "tg_file_id": str, "ai_summary": str, "raw_text": str}
        # Set by agent after photo analysis, consumed when user confirms.
        self.pending_receipt: Optional[dict] = None


# In-memory session store (keyed by user_id)
_sessions: dict = {}


def get_session(user_id: int, user_name: str, role: str) -> SessionContext:
    """Return existing session or create a new one for the given user."""
    if user_id not in _sessions:
        session = SessionContext(user_id, user_name, role)
        # Auto-set default envelope for ALL roles (not just admin/contributor).
        # T-104: readonly users need an envelope too, otherwise they see nothing.
        session.current_envelope_id = DEFAULT_ENVELOPE
        _sessions[user_id] = session
    else:
        # Refresh name and role on each call
        _sessions[user_id].user_name = user_name
        _sessions[user_id].role = role
        # Restore default if envelope was lost (e.g. process restart)
        if not _sessions[user_id].current_envelope_id:
            _sessions[user_id].current_envelope_id = DEFAULT_ENVELOPE
    return _sessions[user_id]
