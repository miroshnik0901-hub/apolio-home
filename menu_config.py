"""
Dynamic bot menu loaded from Admin Google Sheet (BotMenu tab).
Falls back to DEFAULT_MENU when the sheet is absent.

BotMenu sheet columns:
  ID       – unique key, e.g. "rep_last"
  Label    – button text shown to user, e.g. "◀ Пред. месяц"
  Parent   – parent node ID; empty string = top-level
  Type     – "cmd" | "submenu" | "free_text"
  Command  – for Type=cmd: status | report | transactions | week | help | envelopes
  Params   – JSON params for the command, e.g. {"period":"last"}  (optional)
  Order    – numeric sort order within a level
  Visible  – TRUE or FALSE (hide without deleting)
"""
from __future__ import annotations
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default menu (used when BotMenu sheet is absent) ──────────────────────────

DEFAULT_MENU: dict[str, dict] = {
    # ── Top level ──────────────────────────────────────────────────────────
    "status": {
        "label": "📊 Статус", "parent": "",
        "type": "cmd", "command": "status", "params": {}, "order": 1,
    },
    "report": {
        "label": "📋 Отчёт", "parent": "",
        "type": "submenu", "command": "", "params": {}, "order": 2,
    },
    "transactions": {
        "label": "📝 Записи", "parent": "",
        "type": "submenu", "command": "", "params": {}, "order": 3,
    },
    "week": {
        "label": "📅 Неделя", "parent": "",
        "type": "cmd", "command": "week", "params": {}, "order": 4,
    },
    "add": {
        "label": "➕ Добавить", "parent": "",
        "type": "free_text", "command": "", "params": {}, "order": 5,
    },
    "help": {
        "label": "❓ Помощь", "parent": "",
        "type": "cmd", "command": "help", "params": {}, "order": 6,
    },
    # ── Report submenu ─────────────────────────────────────────────────────
    "rep_curr": {
        "label": "▶ Тек. месяц", "parent": "report",
        "type": "cmd", "command": "report", "params": {"period": "current"}, "order": 1,
    },
    "rep_last": {
        "label": "◀ Пред. месяц", "parent": "report",
        "type": "cmd", "command": "report", "params": {"period": "last"}, "order": 2,
    },
    # ── Transactions submenu ───────────────────────────────────────────────
    "txn_recent": {
        "label": "📋 Последние 10", "parent": "transactions",
        "type": "cmd", "command": "transactions", "params": {"limit": 10}, "order": 1,
    },
    "txn_week": {
        "label": "📅 За неделю", "parent": "transactions",
        "type": "cmd", "command": "week", "params": {}, "order": 2,
    },
    "txn_month": {
        "label": "📆 За месяц", "parent": "transactions",
        "type": "cmd", "command": "report", "params": {"period": "current"}, "order": 3,
    },
}

# Rows for auto-creating the BotMenu sheet with sensible defaults
_DEFAULT_ROWS = [
    ("status",       "📊 Статус",       "",             "cmd",       "status",       "",                        1, "TRUE"),
    ("report",       "📋 Отчёт",        "",             "submenu",   "",             "",                        2, "TRUE"),
    ("transactions", "📝 Записи",       "",             "submenu",   "",             "",                        3, "TRUE"),
    ("week",         "📅 Неделя",       "",             "cmd",       "week",         "",                        4, "TRUE"),
    ("add",          "➕ Добавить",     "",             "free_text", "",             "",                        5, "TRUE"),
    ("help",         "❓ Помощь",       "",             "cmd",       "help",         "",                        6, "TRUE"),
    ("rep_curr",     "▶ Тек. месяц",   "report",       "cmd",       "report",       '{"period":"current"}',    1, "TRUE"),
    ("rep_last",     "◀ Пред. месяц",  "report",       "cmd",       "report",       '{"period":"last"}',       2, "TRUE"),
    ("txn_recent",   "📋 Последние 10", "transactions", "cmd",       "transactions", '{"limit":10}',            1, "TRUE"),
    ("txn_week",     "📅 За неделю",   "transactions", "cmd",       "week",         "",                        2, "TRUE"),
    ("txn_month",    "📆 За месяц",    "transactions", "cmd",       "report",       '{"period":"current"}',    3, "TRUE"),
]

_HEADERS = ["ID", "Label", "Parent", "Type", "Command", "Params", "Order", "Visible"]

# ── Cache ──────────────────────────────────────────────────────────────────────
_cache: Optional[dict] = None


def get_menu(gc=None, admin_sheet_id: str = "") -> dict:
    """Return the menu tree dict.  Loads from Admin sheet; falls back to defaults."""
    global _cache
    if _cache is not None:
        return _cache

    if gc and admin_sheet_id:
        try:
            wb = gc.open_by_key(admin_sheet_id)
            ws = wb.worksheet("BotMenu")
            records = ws.get_all_records()
            tree: dict[str, dict] = {}
            for row in records:
                vis = str(row.get("Visible", "TRUE")).strip().upper()
                if vis in ("FALSE", "0", "НЕТ", "NO"):
                    continue
                nid = str(row.get("ID", "")).strip()
                if not nid:
                    continue
                params: dict = {}
                raw = str(row.get("Params", "")).strip()
                if raw:
                    try:
                        params = json.loads(raw)
                    except Exception:
                        pass
                tree[nid] = {
                    "label":   str(row.get("Label",   nid)),
                    "parent":  str(row.get("Parent",  "")).strip(),
                    "type":    str(row.get("Type",    "cmd")).strip().lower(),
                    "command": str(row.get("Command", "")).strip(),
                    "params":  params,
                    "order":   int(row.get("Order", 99) or 99),
                }
            if tree:
                logger.info("BotMenu: loaded %d items from sheet", len(tree))
                _cache = tree
                return _cache
        except Exception as e:
            logger.warning("BotMenu sheet unavailable (%s), using defaults", e)

    logger.info("BotMenu: using defaults")
    _cache = dict(DEFAULT_MENU)
    return _cache


def invalidate() -> None:
    """Force reload from sheet on next get_menu() call."""
    global _cache
    _cache = None


def sorted_children(tree: dict, parent_id: str) -> list[tuple[str, dict]]:
    """Return (id, node) children of parent_id, sorted by order."""
    result = [(nid, n) for nid, n in tree.items() if n.get("parent", "") == parent_id]
    return sorted(result, key=lambda x: x[1].get("order", 99))


def root_nodes(tree: dict) -> list[tuple[str, dict]]:
    """Top-level nodes (parent == '')."""
    return sorted_children(tree, "")


def ensure_sheet(gc, admin_sheet_id: str) -> bool:
    """Create BotMenu tab in Admin sheet if it doesn't exist. Returns True if created."""
    try:
        wb = gc.open_by_key(admin_sheet_id)
        try:
            wb.worksheet("BotMenu")
            return False  # already exists
        except Exception:
            pass  # create it

        ws = wb.add_worksheet("BotMenu", rows=60, cols=10)
        ws.update("A1:H1", [_HEADERS])
        data = [list(row) for row in _DEFAULT_ROWS]
        ws.update(f"A2:H{1 + len(data)}", data)
        try:
            ws.format("A1:H1", {"textFormat": {"bold": True}})
        except Exception:
            pass
        logger.info("BotMenu: created sheet with %d default rows", len(data))
        return True
    except Exception as e:
        logger.error("ensure_sheet failed: %s", e)
        return False
