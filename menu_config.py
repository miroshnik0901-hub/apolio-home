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
    # ══════════════════════════════════════════════════════════════════════
    # MENU v2 — flat root, max 2 taps to any action
    # "💰 Бюджет" and "➕ Добавить" live on the reply keyboard, NOT here.
    # This inline menu opens from "☰ Меню" reply button.
    # ══════════════════════════════════════════════════════════════════════

    # ── Root level: 6 buttons in 3 rows ──────────────────────────────────
    # T-205: labels use clear action-oriented names; emoji consistent with context
    "rep_curr": {
        "label": "📊 Деталі: цей місяць", "parent": "",
        "type": "cmd", "command": "report", "params": {"period": "current"},
        "order": 1, "roles": [],
    },
    "rep_last": {
        "label": "◀ Деталі: минулий місяць", "parent": "",
        "type": "cmd", "command": "report", "params": {"period": "last"},
        "order": 2, "roles": [],
    },
    "txn_recent": {
        "label": "📝 Останні записи", "parent": "",
        "type": "cmd", "command": "transactions", "params": {"limit": 10},
        "order": 3, "roles": [],
    },
    "txn_search": {
        "label": "🔍 Пошук…", "parent": "",
        "type": "free_text", "command": "",
        "params": {
            "prompt": "Введіть запит:\nЗа назвою, категорією, сумою або датою\nНаприклад: Mercato, їжа, > 50, 2026-04-11",
            "pending_key": "transactions:search",
        },
        "order": 4, "roles": [],
    },
    "rep_contribution": {
        "label": "🤝 Внески та розрахунки", "parent": "",
        "type": "cmd", "command": "contribution", "params": {},
        "order": 5, "roles": [],
    },
    "settings": {
        "label": "⚙️ Система", "parent": "",
        "type": "submenu", "command": "", "params": {},
        "order": 6, "roles": [],
    },

    # ── Settings submenu ─────────────────────────────────────────────────
    "set_lang": {
        "label": "🌍 Язык", "parent": "settings",
        "type": "submenu", "command": "", "params": {},
        "order": 1, "roles": [],
    },
    "set_lang_ru": {
        "label": "🇷🇺 Русский", "parent": "set_lang",
        "type": "cmd", "command": "set_language", "params": {"lang": "ru"},
        "order": 1, "roles": [],
    },
    "set_lang_uk": {
        "label": "🇺🇦 Українська", "parent": "set_lang",
        "type": "cmd", "command": "set_language", "params": {"lang": "uk"},
        "order": 2, "roles": [],
    },
    "set_lang_en": {
        "label": "🇬🇧 English", "parent": "set_lang",
        "type": "cmd", "command": "set_language", "params": {"lang": "en"},
        "order": 3, "roles": [],
    },
    "set_lang_it": {
        "label": "🇮🇹 Italiano", "parent": "set_lang",
        "type": "cmd", "command": "set_language", "params": {"lang": "it"},
        "order": 4, "roles": [],
    },
    "set_envelope": {
        "label": "📁 Сменить конверт", "parent": "settings",
        "type": "cmd", "command": "envelopes", "params": {},
        "order": 2, "roles": [],
    },
    # ── Admin panel (only admin sees this) ───────────────────────────────
    "admin_panel": {
        "label": "🔧 Админ", "parent": "settings",
        "type": "submenu", "command": "", "params": {},
        "order": 3, "roles": ["admin"],
    },
    "set_config_view": {
        "label": "⚙️ Конфиг", "parent": "admin_panel",
        "type": "cmd", "command": "config_view", "params": {},
        "order": 1, "roles": ["admin"],
    },
    "set_users": {
        "label": "👥 Юзеры", "parent": "admin_panel",
        "type": "cmd", "command": "users_view", "params": {},
        "order": 2, "roles": ["admin"],
    },
    "set_learning": {
        "label": "🧠 База знаний", "parent": "admin_panel",
        "type": "cmd", "command": "learning_summary", "params": {},
        "order": 3, "roles": ["admin"],
    },
    "set_dashboard": {
        "label": "🔄 Обновить Dashboard", "parent": "admin_panel",
        "type": "cmd", "command": "dashboard_refresh", "params": {},
        "order": 4, "roles": ["admin"],
    },
}

# Rows for auto-creating / re-creating the BotMenu sheet (v2 — flat root)
_DEFAULT_ROWS = [
    # Root level — 6 buttons in 3 rows, max 2 taps to any action
    # T-205: clear action names, consistent emoji
    ("rep_curr",         "📊 Деталі: цей місяць",   "",        "cmd",       "report",       '{"period":"current"}',   1, "TRUE", ""),
    ("rep_last",         "◀ Деталі: мин. місяць",   "",        "cmd",       "report",       '{"period":"last"}',      2, "TRUE", ""),
    ("txn_recent",       "📝 Останні записи",       "",        "cmd",       "transactions", '{"limit":10}',           3, "TRUE", ""),
    ("txn_search",       "🔍 Пошук…",              "",        "free_text", "",             '{"prompt":"Введіть запит:\\nЗа назвою, категорією, сумою або датою","pending_key":"transactions:search"}', 4, "TRUE", ""),
    ("rep_contribution", "🤝 Внески та розрахунки", "",        "cmd",       "contribution", "",                       5, "TRUE", ""),
    ("settings",         "⚙️ Система",              "",        "submenu",   "",             "",                       6, "TRUE", ""),
    # Settings submenu
    ("set_lang",         "🌍 Язык",                 "settings",     "submenu",   "",             "",                   1, "TRUE", ""),
    ("set_lang_ru",      "🇷🇺 Русский",              "set_lang",     "cmd",       "set_language", '{"lang":"ru"}',      1, "TRUE", ""),
    ("set_lang_uk",      "🇺🇦 Українська",           "set_lang",     "cmd",       "set_language", '{"lang":"uk"}',      2, "TRUE", ""),
    ("set_lang_en",      "🇬🇧 English",              "set_lang",     "cmd",       "set_language", '{"lang":"en"}',      3, "TRUE", ""),
    ("set_lang_it",      "🇮🇹 Italiano",             "set_lang",     "cmd",       "set_language", '{"lang":"it"}',      4, "TRUE", ""),
    ("set_envelope",     "📁 Сменить конверт",      "settings",     "cmd",       "envelopes",    "",                   2, "TRUE", ""),
    # Admin panel (admin only)
    ("admin_panel",      "🔧 Админ",                "settings",     "submenu",   "",             "",                   3, "TRUE", "admin"),
    ("set_config_view",  "⚙️ Конфиг",               "admin_panel",  "cmd",       "config_view",  "",                   1, "TRUE", "admin"),
    ("set_users",        "👥 Юзеры",                "admin_panel",  "cmd",       "users_view",   "",                   2, "TRUE", "admin"),
    ("set_learning",     "🧠 База знаний",          "admin_panel",  "cmd",       "learning_summary", "",               3, "TRUE", "admin"),
    ("set_dashboard",    "🔄 Обновить Dashboard",   "admin_panel",  "cmd",       "dashboard_refresh", "",              4, "TRUE", "admin"),
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


def reset_to_defaults(gc, admin_sheet_id: str) -> bool:
    """Overwrite BotMenu tab with current _DEFAULT_ROWS. Clears cache. Returns True on success."""
    global _cache
    _cache = None
    try:
        wb = gc.open_by_key(admin_sheet_id)
        try:
            ws = wb.worksheet("BotMenu")
        except Exception:
            ws = wb.add_worksheet("BotMenu", rows=60, cols=10)
        ws.clear()
        ws.update("A1:I1", [_HEADERS])
        data = [list(row) for row in _DEFAULT_ROWS]
        ws.update(f"A2:I{1 + len(data)}", data)
        try:
            ws.format("A1:I1", {"textFormat": {"bold": True}})
        except Exception:
            pass
        logger.info("BotMenu: reset to defaults (%d rows)", len(data))
        return True
    except Exception as e:
        logger.error("BotMenu reset_to_defaults failed: %s", e)
        return False


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
