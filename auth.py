import os
import json
from datetime import datetime
from typing import Optional
from sheets import AdminSheets

# T-259: No hardcoded DEFAULT_ENVELOPE — it must be resolved per-user from
# Admin.Users.envelopes (first entry). Previous hardcode "MM_BUDGET" broke
# TEST where envelope_id=TEST_BUDGET, causing weekly report → "❌ Envelope not found".
# See _resolve_default_envelope() below.


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

            # T-136: Build name→ID mapping so Users sheet can store
            # either envelope IDs or Names — both will resolve correctly.
            name_to_id: dict[str, str] = {}
            try:
                for env in self.sheets.get_envelopes():
                    eid = env.get("ID", "")
                    ename = env.get("Name", "")
                    if eid:
                        name_to_id[eid.lower()] = eid          # ID→ID (already valid)
                        if ename:
                            name_to_id[ename.lower()] = eid     # Name→ID
            except Exception:
                pass  # envelope lookup is best-effort

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
                # T-136: resolve envelope names/IDs to canonical IDs
                raw_envs = [e.strip() for e in str(u.get("envelopes", "")).split(",") if e.strip()]
                envelopes = [name_to_id.get(e.lower(), e) for e in raw_envs]
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
        # Pending delete: tx_id awaiting user confirmation via present_options.
        # Set by agent when presenting delete confirmation, consumed in cb_choice_.
        self.pending_delete_tx: Optional[str] = None


# In-memory session store (keyed by user_id)
_sessions: dict = {}

# T-259: Registered AuthManager, set by bot.py at startup.
# Used by get_session() to resolve the default envelope for a user from
# Admin.Users.envelopes — removes the previous DEFAULT_ENVELOPE="MM_BUDGET"
# hardcode that broke TEST (where envelope_id=TEST_BUDGET).
_registered_auth: Optional["AuthManager"] = None


def register_auth_manager(auth_manager: "AuthManager") -> None:
    """Register the AuthManager instance so get_session() can resolve
    the user's default envelope from Admin.Users.envelopes.
    Call this once at startup, right after instantiating AuthManager.
    """
    global _registered_auth
    _registered_auth = auth_manager


def _resolve_default_envelope(user_id: int) -> Optional[str]:
    """Return the first envelope assigned to user_id in Admin.Users.envelopes,
    or None if unknown. Used as the default for new sessions (T-259).
    """
    if _registered_auth is None:
        return None
    try:
        user = _registered_auth.get_user(user_id)
        if user:
            envs = user.get("envelopes", []) or []
            if envs:
                return envs[0]
    except Exception as e:
        print(f"[get_session] Failed to resolve default envelope for {user_id}: {e}")
    return None


def get_session(user_id: int, user_name: str, role: str) -> SessionContext:
    """Return existing session or create a new one for the given user.

    Default envelope is resolved from Admin.Users.envelopes (first entry) —
    NO hardcode. T-259 removed the previous DEFAULT_ENVELOPE="MM_BUDGET" which
    broke TEST (envelope_id=TEST_BUDGET). Requires register_auth_manager() to
    have been called at startup; if not, current_envelope_id stays None and
    downstream code must handle None (bot.py:1291-1296 fallback path already does).
    """
    if user_id not in _sessions:
        session = SessionContext(user_id, user_name, role)
        # T-104: readonly users need an envelope too, otherwise they see nothing.
        # T-259: resolve from Admin.Users.envelopes instead of hardcoded default.
        session.current_envelope_id = _resolve_default_envelope(user_id)
        _sessions[user_id] = session
    else:
        # Refresh name and role on each call
        _sessions[user_id].user_name = user_name
        _sessions[user_id].role = role
        # Restore default if envelope was lost (e.g. process restart)
        if not _sessions[user_id].current_envelope_id:
            _sessions[user_id].current_envelope_id = _resolve_default_envelope(user_id)
    return _sessions[user_id]
