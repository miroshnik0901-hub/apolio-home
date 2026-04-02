"""
Apolio Home — User Context Manager
Reads/writes user goals and behavioral patterns from UserContext sheet.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import gspread

logger = logging.getLogger(__name__)

SHEET_NAME = "UserContext"

HEADERS = [
    "user_id", "key", "value", "updated_at",
]

# Predefined keys
KEY_SAVINGS_TARGET = "savings_target_monthly"
KEY_EMERGENCY_FUND_TARGET = "emergency_fund_target"
KEY_EMERGENCY_FUND_CURRENT = "emergency_fund_current"
KEY_BUDGET_CAP = "budget_cap_monthly"
KEY_HOUSEHOLD = "household"
KEY_PRIMARY_CURRENCY = "primary_currency"
KEY_COUNTRIES = "countries"
KEY_CUSTOM_GOAL = "custom_goal"


class UserContextManager:
    """
    Key-value store for user goals and preferences.
    Stored in a UserContext sheet in the envelope spreadsheet.
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
                ws = wb.add_worksheet(SHEET_NAME, rows=100, cols=len(HEADERS))
                ws.append_row(HEADERS)
                # Pre-populate defaults for Mikhail
                now = datetime.now(timezone.utc).isoformat()
                defaults = [
                    ["360466156", KEY_PRIMARY_CURRENCY, "EUR", now],
                    ["360466156", KEY_HOUSEHOLD, "Mikhail, Marina", now],
                    ["360466156", KEY_COUNTRIES, "IT, PL, UA", now],
                ]
                ws.append_rows(defaults)
            self._ws = ws
            self._ready = True
        except Exception as e:
            logger.error(f"[UserContext] could not ensure sheet: {e}")

    def get(self, user_id: int, key: str) -> Optional[str]:
        """Get a single context value."""
        self._ensure_sheet()
        if not self._ws:
            return None
        try:
            rows = self._ws.get_all_records()
            for row in rows:
                if str(row.get("user_id")) == str(user_id) and row.get("key") == key:
                    return row.get("value", "")
        except Exception as e:
            logger.error(f"[UserContext] get error: {e}")
        return None

    def get_all(self, user_id: int) -> dict:
        """Get all context values for a user as a dict."""
        self._ensure_sheet()
        if not self._ws:
            return {}
        try:
            rows = self._ws.get_all_records()
            return {
                row["key"]: row["value"]
                for row in rows
                if str(row.get("user_id")) == str(user_id)
            }
        except Exception as e:
            logger.error(f"[UserContext] get_all error: {e}")
            return {}

    def set(self, user_id: int, key: str, value: str):
        """Set (upsert) a context value."""
        self._ensure_sheet()
        if not self._ws:
            return
        now = datetime.now(timezone.utc).isoformat()
        try:
            rows = self._ws.get_all_values()
            for i, row in enumerate(rows):
                if i == 0:
                    continue  # skip header
                if len(row) >= 2 and str(row[0]) == str(user_id) and row[1] == key:
                    # Update existing
                    self._ws.update_cell(i + 1, 3, value)
                    self._ws.update_cell(i + 1, 4, now)
                    return
            # Insert new
            self._ws.append_row([str(user_id), key, value, now])
        except Exception as e:
            logger.error(f"[UserContext] set error: {e}")

    def delete(self, user_id: int, key: str):
        """Remove a context value."""
        self._ensure_sheet()
        if not self._ws:
            return
        try:
            rows = self._ws.get_all_values()
            for i, row in enumerate(rows):
                if i == 0:
                    continue
                if len(row) >= 2 and str(row[0]) == str(user_id) and row[1] == key:
                    self._ws.delete_rows(i + 1)
                    return
        except Exception as e:
            logger.error(f"[UserContext] delete error: {e}")


def format_goals_for_prompt(ctx: dict) -> str:
    """
    Format user context as text block for injection into agent system prompt.
    """
    if not ctx:
        return ""

    lines = ["## USER GOALS & CONTEXT"]

    household = ctx.get(KEY_HOUSEHOLD)
    if household:
        lines.append(f"Household: {household}")

    countries = ctx.get(KEY_COUNTRIES)
    if countries:
        lines.append(f"Countries: {countries}")

    savings = ctx.get(KEY_SAVINGS_TARGET)
    if savings:
        lines.append(f"Monthly savings target: {savings} EUR")

    emergency_target = ctx.get(KEY_EMERGENCY_FUND_TARGET)
    emergency_current = ctx.get(KEY_EMERGENCY_FUND_CURRENT)
    if emergency_target:
        cur = f" (current: {emergency_current} EUR)" if emergency_current else ""
        lines.append(f"Emergency fund target: {emergency_target} EUR{cur}")

    # Custom goals
    custom = ctx.get(KEY_CUSTOM_GOAL)
    if custom:
        lines.append(f"Custom goal: {custom}")

    # If no goals set at all, hint the agent to ask
    goal_keys = [KEY_SAVINGS_TARGET, KEY_EMERGENCY_FUND_TARGET, KEY_CUSTOM_GOAL]
    if not any(ctx.get(k) for k in goal_keys):
        lines.append("(No financial goals set yet — consider asking the user about their goals)")

    return "\n".join(lines) if len(lines) > 1 else ""
