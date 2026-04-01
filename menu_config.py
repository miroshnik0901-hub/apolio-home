"""
Dynamic bot menu loaded from Admin Google Sheet (BotMenu tab).
Falls back to DEFAULT_MENU when the sheet is absent.

BotMenu sheet columns:
  ID       – unique key, e.g. "rep_last"
  Label    – button text shown to user, e.g. "◀ Пред. месяц"
  Parent   – parent node ID; empty string = top-level
  Type     – "cmd" | "submenu" | "free_text"
  Command  – for Type=cmd: status | report | transactions | week | help | envelopes | settings
  Params   – JSON params for the command, e.g. {"period":"last"}  (optional)
  Order    – numeric sort order within a level
  Visible  – TRUE or FALSE (hide without deleting)
  Roles    – comma-separated roles that can see this item: admin,viewer,member
             Leave empty = visible to everyone.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default menu (used when BotMenu sheet is absent) ──────────────────────────

DEFAULT_MENU: dict[str, dict] = {
    # ── Top level (all roles) ──────────────────────────────────────────────
    "status": {
        "label": "📊 Статус", "parent": "",
        "type": "cmd", "command": "status", "params": {}, "order": 1,
        "roles": [],
    },
    "report": {
        "label": "📋 Отчёт", "parent": "",
        "type": "submenu", "command": "", "params": {}, "order": 2,
        "roles": [],
    },
    "transactions": {
        "label": "📝 Записи", "parent": "",
        "type": "submenu", "command": "", "params": {}, "order": 3,
        "roles": [],
    },
    "week": {
        "label": "📅 Неделя", "parent": "",
        "type": "cmd", "command": "week", "params": {}, "order": 4,
        "roles": [],
    },
    "add": {
        "label": "➕ Добавить", "parent": "",
        "type": "free_text", "command": "", "params": {}, "order": 5,
        "roles": [],
    },
    "settings": {
        "label": "⚙️ Настройки", "parent": "",
        "type": "submenu", "command": "", "params": {}, "order": 6,
        "roles": ["admin"],
    },
    # ── Report submenu ─────────────────────────────────────────────────────
    "rep_curr": {
        "label": "▶ Тек. месяц", "parent": "report",
        "type": "cmd", "command": "report", "params": {"period": "current"}, "order": 1,
        "roles": [],
    },
    "rep_last": {
        "label": "◀ Пред. месяц", "parent": "report",
        "type": "cmd", "command": "report", "params": {"period": "last"}, "order": 2,
        "roles": [],
    },
    # ── Transactions submenu ───────────────────────────────────────────────
    "txn_recent": {
        "label": "📋 Последние 10", "parent": "transactions",
        "type": "cmd", "command": "transactions", "params": {"limit": 10}, "order": 1,
        "roles": [],
    },
    "txn_week": {
        "label": "📅 За неделю", "parent": "transactions",
        "type": "cmd", "command": "week", "params": {}, "order": 2,
        "roles": [],
    },
    "txn_month": {
        "label": "📆 За месяц", "parent": "transactions",
        "type": "cmd", "command": "report", "params": {"period": "current"}, "order": 3,
        "roles": [],
    },
    # ── Settings submenu (admin only) ──────────────────────────────────────
    "set_envelopes": {
        "label": "📁 Конверты", "parent": "settings",
        "type": "cmd", "command": "envelopes", "params": {}, "order": 1,
        "roles": ["admin"],
    },
    "set_refresh": {
        "label": "🔄 Обновить меню", "parent": "settings",
        "type": "cmd", "command": "refresh", "params": {}, "order": 2,
        "roles": ["admin"],
    },
    "set_undo": {
        "label": "↩️ Отменить", "parent": "settings",
        "type": "cmd", "command": "undo", "params": {}, "order": 3,
        "roles": ["admin"],
    },
}

# Rows for auto-creating / re-creating the BotMenu sheet
_DEFAULT_ROWS = [
    ("status",        "📊 Статус",        "",             "cmd",       "status",       "",                        1, "TRUE", ""),
    ("report",        "📋 Отчёт",         "",             "submenu",   "",             "",                        2, "TRUE", ""),
    ("transactions",  "📝 Записи",        "",             "submenu",   "",             "",                        3, "TRUE", ""),
    ("week",          "📅 Неделя",        "",             "cmd",       "week",         "",                        4, "TRUE", ""),
    ("add",           "➕ Добавить",      "",             "free_text", "",             "",                        5, "TRUE", ""),
    ("settings",      "⚙️ Настройки",    "",             "submenu",   "",             "",                        6, "TRUE", "admin"),
    ("rep_curr",      "▶ Тек. месяц",    "report",       "cmd",       "report",       '{"period":"current"}',    1, "TRUE", ""),
    ("rep_last",      "◀ Пред. месяц",   "report",       "cmd",       "report",       '{"period":"last"}',       2, "TRUE", ""),
    ("txn_recent",    "📋 Последние 10",  "transactions", "cmd",       "transactions", '{"limit":10}',            1, "TRUE", ""),
    ("txn_week",      "📅 За неделю",    "transactions", "cmd",       "week",         "",                        2, "TRUE", ""),
    ("txn_month",     "📆 За месяц",     "transactions", "cmd",       "report",       '{"period":"current"}',    3, "TRUE", ""),
    ("set_envelopes", "📁 Конверты",      "settings",     "cmd",       "envelopes",    "",                        1, "TRUE", "admin"),
    ("set_refresh",   "🔄 Обновить меню", "settings",     "cmd",       "refresh",      "",                        2, "TRUE", "admin"),
    ("set_undo",      "↩️ Отменить",     "settings",     "cmd",       "undo",         "",                        3, "TRUE", "admin"),
]

_HEADERS = ["ID", "Label", "Parent", "Type", "Command", "Params", "Order", "Visible", "Roles"]

# ── Cache ──────────────────────────────────────────────────────────────────────
_cache: Optional[dict] = None


def _parse_roles(raw: str) -> list[str]:
    """Parse a comma-separated roles string into a list. Empty = no restriction."""
    if not raw:
        return []
    return [r.strip().lower() for r in raw.split(",") if r.strip()]


def node_visible_for_role(node: dict, role: str) -> bool:
    """Return True if this menu node should be shown to the given role."""
    roles = node.get("roles", [])
    if not roles:
        return True  # no restriction → visible to all
    return role in roles or "all" in roles


def get_menu(gc=None, admin_sheet_id: str = "") -> dict:
    """Return the menu tree dict. Loads from Admin sheet; falls back to defaults."""
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
                    "roles":   _parse_roles(str(row.get("Roles", ""))),
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


def sorted_children_for_role(tree: dict, parent_id: str, role: str) -> list[tuple[str, dict]]:
    """Like sorted_children, but filtered to nodes the given role can see."""
    return [(nid, n) for nid, n in sorted_children(tree, parent_id)
            if node_visible_for_role(n, role)]


def root_nodes(tree: dict) -> list[tuple[str, dict]]:
    """Top-level nodes (parent == '')."""
    return sorted_children(tree, "")


def root_nodes_for_role(tree: dict, role: str) -> list[tuple[str, dict]]:
    """Top-level nodes visible to the given role."""
    return sorted_children_for_role(tree, "", role)


def ensure_sheet(gc, admin_sheet_id: str) -> bool:
    """Create/update BotMenu tab in Admin sheet. Returns True if created."""
    try:
        wb = gc.open_by_key(admin_sheet_id)
        try:
            ws = wb.worksheet("BotMenu")
            # Check if Roles column exists; if not, add it
            headers = ws.row_values(1)
            if "Roles" not in headers:
                col = len(headers) + 1
                ws.update_cell(1, col, "Roles")
                logger.info("BotMenu: added Roles column to existing sheet")
            return False  # already existed
        except Exception:
            pass  # create it

        ws = wb.add_worksheet("BotMenu", rows=60, cols=10)
        ws.update("A1:I1", [_HEADERS])
        data = [list(row) for row in _DEFAULT_ROWS]
        ws.update(f"A2:I{1 + len(data)}", data)
        try:
            ws.format("A1:I1", {"textFormat": {"bold": True}})
        except Exception:
            pass
        logger.info("BotMenu: created sheet with %d default rows", len(data))
        return True
    except Exception as e:
        logger.error("ensure_sheet failed: %s", e)
        return False
