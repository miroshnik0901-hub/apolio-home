"""Apolio Home — Telegram Bot Entry Point — v2.1.0"""
import asyncio
import logging
import os
import re
import datetime as dt
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Logging: console + rotating file
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
from logging.handlers import RotatingFileHandler
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, "bot.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.StreamHandler(), _file_handler],
)
logger = logging.getLogger(__name__)

import menu_config as mc
import i18n

from telegram import (
    Update, BotCommand,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton,
    MenuButtonCommands,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

from sheets import SheetsClient
from auth import AuthManager, get_session
from agent import ApolioAgent
from tools.conversation_log import ConversationLogger, make_session_id
from tools.receipt_store import ReceiptStore
import db as appdb

# Initialise shared clients
sheets = SheetsClient()
auth = AuthManager(sheets)
agent = ApolioAgent(sheets, auth)
receipt_store: Optional[ReceiptStore] = None
conv_logger: Optional[ConversationLogger] = None

_PROD_ADMIN_ID = "1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk"
_TEST_ADMIN_ID = "1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM"


def _get_active_file_id() -> str:
    """Return the budget file_id for the default envelope (MM_BUDGET).
    Reads from Admin → Envelopes tab — no hardcoded budget file IDs."""
    try:
        envs = sheets.get_envelopes()
        for e in envs:
            if e.get("ID") == "MM_BUDGET" and str(e.get("Active", "")).upper() == "TRUE":
                return e["file_id"]
    except Exception:
        pass
    # Last resort fallback (should never reach here if Admin is configured)
    return os.environ.get("MM_BUDGET_FILE_ID", "")
# True when running with the test bot token (8298458285:…)
_IS_TEST_BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").startswith("8298458285:")
# Flag: True once PostgreSQL is ready (set in post_init)
_db_ready = False

# ── Keyboards ──────────────────────────────────────────────────────────────────

def _build_main_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Build reply keyboard in the user's language.

    Layout (1 row × 3 columns) — T-028:
        💰 Бюджет  |  ➕ Добавить  |  ☰ Ещё

    Бюджет → quick budget status
    Добавить → prompted transaction entry
    Ещё → opens the inline navigation menu

    is_persistent=False so the keyboard is collapsible and the toggle button
    stays visible in the input bar. The keyboard itself is re-sent whenever
    the bot needs to ensure it's active (e.g. /start, language change).
    Never send ReplyKeyboardRemove() — that kills the toggle button permanently.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(i18n.t_kb("budget", lang)),
                KeyboardButton(i18n.t_kb("add", lang)),
                KeyboardButton(i18n.t_kb("more", lang)),
            ],
        ],
        resize_keyboard=True,
        is_persistent=False,  # collapsible; toggle button visible on right side of input
    )


def _menu_label(lang: str = "ru") -> str:
    """Translated label for the ☰ Menu inline button."""
    labels = {"ru": "☰ Меню", "uk": "☰ Меню", "en": "☰ Menu", "it": "☰ Menu"}
    return labels.get(lang, "☰ Меню")


def _with_menu_btn(*extra_rows, lang: str = "ru") -> InlineKeyboardMarkup:
    """Build inline keyboard: extra rows + translated [☰ Меню] at the bottom."""
    rows = [list(r) for r in extra_rows]
    rows.append([InlineKeyboardButton(_menu_label(lang), callback_data="nav:__menu__")])
    return InlineKeyboardMarkup(rows)


def _build_inline_menu(parent_id: str = "", tree: dict = None,
                        role: str = "admin", lang: str = "en") -> InlineKeyboardMarkup:
    """Build an inline keyboard grid from the menu config, filtered by role.

    parent_id="" → root level.
    parent_id="report" → children of report submenu.
    role → only show nodes visible to this role.
    lang → label language (ru/uk/en/it).
    """
    if tree is None:
        tree = mc.get_menu()

    if parent_id:
        children = mc.sorted_children_for_role(tree, parent_id, role)
        parent_node = tree.get(parent_id, {})
        grandparent = parent_node.get("parent", "")
        back_cb = f"nav:{grandparent}" if grandparent else "nav:__root__"
    else:
        children = mc.root_nodes_for_role(tree, role)
        back_cb = None

    rows: list[list[InlineKeyboardButton]] = []
    for nid, node in children:
        # Prefer i18n translation; fall back to sheet label
        label = i18n.t_menu(nid, lang) or node["label"]
        if node["type"] == "submenu":
            label = label + " ›"
        rows.append([InlineKeyboardButton(label, callback_data=f"nav:{nid}")])
    if back_cb:
        rows.append([InlineKeyboardButton(i18n.t_menu("back", lang), callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)


# Alias kept for backward compatibility
def _build_submenu_keyboard(parent_id: str, tree: dict,
                             role: str = "admin", lang: str = "en") -> InlineKeyboardMarkup:
    return _build_inline_menu(parent_id, tree, role, lang)


GREETINGS = {
    "привет", "hi", "hello", "ciao", "hey", "добрий день",
    "як справи", "как дела", "что умеешь", "help", "start", "хелп",
    "buongiorno", "salve", "allo",
}

# ── Bot command definitions ────────────────────────────────────────────────────
# Only /menu shown in the ≡ commands list — all other nav via reply keyboard
BOT_COMMANDS_ALL = [
    BotCommand("menu", "☰ Открыть меню"),
]

BOT_COMMANDS_ADMIN = [
    BotCommand("menu", "☰ Открыть меню"),
]


# ── Formatting helpers ─────────────────────────────────────────────────────────

MONTH_NAMES_RU = {
    "01": "январе", "02": "феврале", "03": "марте",
    "04": "апреле", "05": "мае", "06": "июне",
    "07": "июле", "08": "августе", "09": "сентябре",
    "10": "октябре", "11": "ноябре", "12": "декабре",
}
MONTH_LABELS_RU = {
    "01": "Январь", "02": "Февраль", "03": "Март",
    "04": "Апрель", "05": "Май", "06": "Июнь",
    "07": "Июль", "08": "Август", "09": "Сентябрь",
    "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь",
}
CAT_ICONS = {
    "Groceries": "🛒", "Продукты": "🛒", "Food": "🍎", "Еда": "🍎",
    "Transport": "🚗", "Транспорт": "🚗", "Taxi": "🚕", "Такси": "🚕",
    "Restaurant": "🍽", "Ресторан": "🍽", "Кафе": "☕", "Coffee": "☕",
    "Health": "💊", "Здоровье": "💊", "Медицина": "💊",
    "Entertainment": "🎬", "Развлечения": "🎬",
    "Clothing": "👕", "Одежда": "👕",
    "Utilities": "💡", "Коммунальные": "💡",
    "Education": "📚", "Образование": "📚",
    "Travel": "✈️", "Путешествия": "✈️",
    "Savings": "💰", "Сбережения": "💰",
    "Other": "📌", "Другое": "📌",
    "Transfer": "↔️", "Перевод": "↔️",
    "Shopping": "🛍", "Покупки": "🛍",
    "Sport": "🏋️", "Спорт": "🏋️",
    "Kids": "🧒", "Дети": "🧒",
    "Beauty": "💅", "Красота": "💅",
    "Home": "🏠", "Дом": "🏠",
    "Bills": "📄", "Счета": "📄",
}


def _cat_icon(category: str) -> str:
    return CAT_ICONS.get(category, "•")


def _format_txn_list(txs: list[dict], lang: str = "ru", *, show_title: bool = True) -> str:
    """Format transaction list with expenses/income grouped separately (T-046)."""
    if not txs:
        return i18n.ts("no_transactions", lang)

    ordered = list(reversed(txs))  # newest first
    expenses = [tx for tx in ordered if tx.get("Type", "expense") == "expense"]
    income = [tx for tx in ordered if tx.get("Type", "") == "income"]

    lines: list[str] = []
    if show_title:
        lines.append(i18n.tu("txn_list_title", lang, count=len(txs)))

    def _render(tx_list: list[dict]) -> None:
        for tx in tx_list:
            date = tx.get("Date", "")
            cat = tx.get("Category", "?")
            amt = tx.get("Amount_Orig", tx.get("Amount_EUR", "?"))
            curr = tx.get("Currency_Orig", "EUR")
            amt_eur = tx.get("Amount_EUR", "")
            who = tx.get("Who", "")
            note = tx.get("Note", "")
            icon = _cat_icon(cat)
            if curr != "EUR" and amt_eur:
                amt_str = f"{amt} {curr} ({amt_eur} EUR)"
            else:
                amt_str = f"{amt} EUR"
            who_str = f" — {who}" if who else ""
            note_str = f"\n     📎 {note}" if note else ""
            lines.append(f"{icon} <b>{cat}</b>  {amt_str}{who_str}  <i>{date}</i>{note_str}")

    if expenses:
        if income:
            lines.append(i18n.tu("txn_section_expense", lang))
        _render(expenses)
    if income:
        lines.append(i18n.tu("txn_section_income", lang))
        _render(income)

    return "\n".join(lines)


def _month_name_ru(period: str) -> str:
    """Convert YYYY-MM to 'апреле 2026' (Russian, legacy — use _month_name where lang is available)."""
    return _month_name(period, "ru")


def _month_label_ru(period: str) -> str:
    """Convert YYYY-MM to 'Апрель 2026' (Russian, legacy — use _month_label where lang is available)."""
    return _month_label(period, "ru")


def _month_label(period: str, lang: str = "ru") -> str:
    """Convert YYYY-MM to localized standalone month name, e.g. 'April 2026'."""
    try:
        y, m = period.split("-")
        labels = i18n.MONTH_LABELS.get(lang, i18n.MONTH_LABELS["ru"])
        return f"{labels.get(m, m)} {y}"
    except Exception:
        return period


def _month_name(period: str, lang: str = "ru") -> str:
    """Convert YYYY-MM to localized prepositional form, e.g. 'April 2026' / 'апреле 2026'."""
    try:
        y, m = period.split("-")
        names = i18n.MONTH_NAMES.get(lang, i18n.MONTH_NAMES["ru"])
        return f"{names.get(m, m)} {y}"
    except Exception:
        return period


def _progress_bar(current: float, total: float, width: int = 10) -> str:
    """Budget progress bar: green→yellow→red based on spend level."""
    if not total or total <= 0:
        return "▱" * width
    pct = min(current / total, 1.0)
    filled = round(pct * width)
    if pct < 0.7:
        block = "🟩"
    elif pct < 0.9:
        block = "🟨"
    else:
        block = "🟥"
    return block * filled + "▱" * (width - filled)


def _share_bar(current: float, total: float, width: int = 6) -> str:
    """Neutral share bar for category breakdown (always blue, no alarm colors)."""
    if not total or total <= 0:
        return "▱" * width
    pct = min(current / total, 1.0)
    filled = round(pct * width)
    return "🟦" * filled + "▱" * (width - filled)


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    """Russian plural form: 1 запись, 2-4 записи, 5+ записей."""
    if 11 <= (n % 100) <= 19:
        return many
    r = n % 10
    if r == 1:
        return one
    if 2 <= r <= 4:
        return few
    return many


def _strip_markdown(text: str) -> str:
    """Strip basic Telegram markdown markers to produce plain text."""
    text = re.sub(r'\*\*?(.*?)\*\*?', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text


async def _safe_reply(message, text: str, reply_markup=None, **kwargs):
    """Send agent text: try MARKDOWN, fall back to plain if parse error."""
    try:
        return await message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            **kwargs,
        )
    except BadRequest as e:
        logger.warning(f"Markdown parse failed ({e}), retrying as plain text")
        return await message.reply_text(
            _strip_markdown(text),
            reply_markup=reply_markup,
            **kwargs,
        )


async def _safe_edit(query, text: str, reply_markup=None, **kwargs):
    """Edit message: try MARKDOWN, fall back to plain if parse error."""
    try:
        return await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            **kwargs,
        )
    except BadRequest as e:
        logger.warning(f"Markdown edit failed ({e}), retrying as plain text")
        return await query.edit_message_text(
            _strip_markdown(text),
            reply_markup=reply_markup,
            **kwargs,
        )


# ── Direct budget renderers ────────────────────────────────────────────────────

def _offset_month(month_str: str, delta: int) -> str:
    """Add/subtract months from a YYYY-MM string."""
    y, m = map(int, month_str.split("-"))
    m += delta
    while m > 12:
        m -= 12; y += 1
    while m < 1:
        m += 12; y -= 1
    return f"{y:04d}-{m:02d}"


def _current_month_str() -> str:
    return dt.date.today().strftime("%Y-%m")


async def _build_status_html(session, lang: str = "ru") -> str:
    """Render budget status as HTML without going through the agent."""
    try:
        from tools.summary import tool_get_budget_status, tool_get_summary
        status = await tool_get_budget_status({}, session, sheets, auth)
        if status.get("error"):
            return f"❌ {status['error']}"

        summary = await tool_get_summary(
            {"breakdown_by": "category"}, session, sheets, auth
        )

        cap = float(status.get("cap") or 0)
        spent = float(status.get("spent") or 0)
        remaining = float(status.get("remaining") or 0)
        pct = float(status.get("pct_used") or 0)
        month = status.get("month", "")
        alert = status.get("alert", False)

        label = _month_label(month, lang)
        env_id = session.current_envelope_id or "?"
        try:
            env_list = sheets.get_envelopes()
            env_match = next((e for e in env_list if e.get("ID") == env_id), None)
            env_label = env_match.get("Name", env_id) if env_match else env_id
        except Exception:
            env_label = env_id

        # Show TEST tag only on PROD bot running in test mode (misconfiguration)
        # Test bot = test data by definition, no tag needed
        try:
            mode_tag = ""
            if not _IS_TEST_BOT:
                dash_cfg = sheets.get_dashboard_config()
                if dash_cfg.get("mode", "prod").lower() == "test":
                    mode_tag = "  🧪 <b>TEST</b>"
        except Exception:
            mode_tag = ""

        # Progress bar + status emoji
        bar = _progress_bar(spent, cap, 10) if cap else ""
        if pct >= 100:
            status_emoji = "🔴"
        elif pct >= 80:
            status_emoji = "⚠️"
        elif pct >= 50:
            status_emoji = "🟡"
        else:
            status_emoji = "✅"

        # Days left + daily pace + projection
        today_num = dt.date.today().day
        days_in_month = (dt.date(dt.date.today().year, dt.date.today().month % 12 + 1, 1)
                         - dt.timedelta(days=1)).day if dt.date.today().month < 12 else 31
        days_left = days_in_month - today_num
        daily_rate = spent / today_num if today_num > 0 else 0
        projected = daily_rate * days_in_month if cap else 0

        lines = [
            i18n.tu("status_title", lang, label=label, env=env_label, mode=mode_tag),
            "",
        ]

        if cap:
            lines.append(f"{bar}  {status_emoji}")
            lines.append(f"<b>{spent:,.0f}</b> / {cap:,.0f} EUR  <b>({pct:.0f}%)</b>")
            lines.append(i18n.tu("status_remaining", lang, remaining=remaining, days=days_left))
        else:
            lines.append(i18n.tu("status_spent", lang, spent=spent))

        if daily_rate > 0 and cap:
            pace_delta = projected - cap
            pace_str = (f"+{pace_delta:,.0f}" if pace_delta > 0 else f"{pace_delta:,.0f}")
            lines.append(i18n.tu("status_pace", lang, rate=daily_rate, proj=projected, delta=pace_str))

        # Status is a COMPACT widget — no category/who breakdown.
        # Detailed breakdown is in _build_report_html (📋 Аналітика).
        if summary.get("status") == "ok":
            by_who = summary.get("by_who", {})
            # Only show top spender as a one-liner if 2+ people
            if len(by_who) > 1:
                top_who = max(by_who.items(), key=lambda x: x[1])
                lines.append("")
                lines.append(f"👥 {' · '.join(f'{w}: {a:,.0f}' for w, a in sorted(by_who.items(), key=lambda x: -x[1]))}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"_build_status_html failed: {e}", exc_info=True)
        return i18n.tu("status_error", lang, detail=str(e))


async def _build_report_html(session, period: str = "current", lang: str = "ru") -> str:
    """Render monthly report as HTML without going through the agent."""
    try:
        from tools.summary import tool_get_summary
        if period == "current":
            period = _current_month_str()
        elif period == "last":
            period = _offset_month(_current_month_str(), -1)

        summary = await tool_get_summary(
            {"breakdown_by": "category", "period": period},
            session, sheets, auth
        )
        if summary.get("error"):
            return f"❌ {summary['error']}"

        # Previous period for comparison
        prev_period = _offset_month(period, -1)
        summary_prev = await tool_get_summary(
            {"breakdown_by": "category", "period": prev_period}, session, sheets, auth
        )

        total = float(summary.get("total_spent") or 0)
        total_prev = float(summary_prev.get("total_spent") or 0) if summary_prev.get("status") == "ok" else 0
        label = _month_label(period, lang)
        cats = summary.get("categories", {})
        by_who = summary.get("by_who", {})
        prev_cats = summary_prev.get("categories", {}) if summary_prev.get("status") == "ok" else {}

        # Envelope info for heading + cap
        try:
            env_id = session.current_envelope_id or "MM_BUDGET"
            env_list = sheets.get_envelopes()
            env_match = next((e for e in env_list if e.get("ID") == env_id), None)
            cap = float(env_match.get("Monthly_Cap") or env_match.get("monthly_cap") or 0) if env_match else 0
            env_label = env_match.get("Name", env_id) if env_match else env_id
        except Exception:
            cap = 0
            env_label = env_id

        # Show TEST tag only on PROD bot running in test mode (misconfiguration)
        try:
            mode_tag = ""
            if not _IS_TEST_BOT:
                dash_cfg = sheets.get_dashboard_config()
                if dash_cfg.get("mode", "prod").lower() == "test":
                    mode_tag = "  🧪 <b>TEST</b>"
        except Exception:
            mode_tag = ""

        lines = [i18n.tu("report_heading", lang, label=label, env=env_label, mode=mode_tag), ""]

        if total == 0:
            lines.append(i18n.tu("report_no_records", lang))
            return "\n".join(lines)

        # Total with comparison
        if total_prev > 0:
            delta = total - total_prev
            pct_delta = round(delta / total_prev * 100)
            arrow = "↑" if delta > 0 else "↓"
            lines.append(i18n.tu("report_total_vs", lang,
                                 total=total, arrow=arrow, pct=abs(pct_delta),
                                 prev_label=_month_label(prev_period, lang)))
        else:
            lines.append(i18n.tu("report_total", lang, total=total))

        if cap:
            bar = _progress_bar(total, cap, 10)
            pct_of_cap = round(total / cap * 100)
            lines.append(f"{bar}  {i18n.tu('report_of_budget', lang, pct=pct_of_cap, cap=cap)}")

        if cats:
            lines.append("")
            lines.append(i18n.tu("by_category", lang))
            for cat, amt in sorted(cats.items(), key=lambda x: -x[1]):
                pct_share = round(amt / total * 100) if total else 0
                bar = _share_bar(amt, total, 6)
                icon = _cat_icon(cat)
                prev_amt = prev_cats.get(cat, 0)
                if prev_amt > 0:
                    delta = amt - prev_amt
                    sign = "↑" if delta > 0 else "↓"
                    trend = f"  <i>{sign}{abs(delta):,.0f}</i>"
                else:
                    trend = ""
                lines.append(
                    f"{icon} <b>{cat}</b>  {bar}\n"
                    f"   {amt:,.0f} EUR  ({pct_share}%){trend}"
                )

        if len(by_who) > 1:
            lines.append("")
            lines.append(i18n.tu("by_person", lang))
            for who, amt in sorted(by_who.items(), key=lambda x: -x[1]):
                pct_share = round(amt / total * 100) if total else 0
                lines.append(f"  👤 {who}: {amt:,.0f} EUR  ({pct_share}%)")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"_build_report_html failed: {e}", exc_info=True)
        return i18n.tu("report_error", lang, detail=str(e))


async def _build_week_html(session, lang: str = "ru") -> str:
    """Render this-week expenses as HTML."""
    try:
        from tools.transactions import tool_find_transactions
        today = dt.date.today()
        monday = today - dt.timedelta(days=today.weekday())
        result = await tool_find_transactions(
            {"date_from": monday.isoformat(), "date_to": today.isoformat(), "limit": 50},
            session, sheets, auth
        )
        if result.get("error"):
            return f"❌ {result['error']}"

        txs = [r for r in result.get("transactions", []) if r.get("Type") == "expense"]
        if not txs:
            return i18n.tu("week_no_expenses", lang)

        total = sum(float(r.get("Amount_EUR") or r.get("Amount_Orig") or 0) for r in txs)
        cats: dict = {}
        by_day: dict = {}
        for r in txs:
            cat = r.get("Category", "Other")
            amt = float(r.get("Amount_EUR") or r.get("Amount_Orig") or 0)
            cats[cat] = cats.get(cat, 0) + amt
            day = r.get("Date", "")[:10]
            by_day[day] = by_day.get(day, 0) + amt

        week_label = f"{monday.strftime('%d.%m')} — {today.strftime('%d.%m')}"
        days_elapsed = max(today.weekday() + 1, 1)
        daily_avg = total / days_elapsed

        lines = [
            i18n.tu("week_title", lang, week_label=week_label),
            "",
            i18n.tu("week_total", lang, total=total, n=len(txs)),
            i18n.tu("week_daily_avg", lang, avg=daily_avg),
        ]

        if by_day:
            lines.append("")
            lines.append(i18n.tu("by_day", lang))
            for day in sorted(by_day.keys()):
                eng_abbrev = dt.datetime.strptime(day, "%Y-%m-%d").strftime("%a")
                day_abbrev = i18n.day_abbrev(eng_abbrev, lang)
                day_label = dt.datetime.strptime(day, "%Y-%m-%d").strftime("%d.%m") + f" {day_abbrev}"
                amt = by_day[day]
                lines.append(f"  {day_label}: {amt:,.0f} EUR")

        if cats:
            lines.append("")
            lines.append(i18n.tu("by_category", lang))
            for cat, amt in sorted(cats.items(), key=lambda x: -x[1]):
                icon = _cat_icon(cat)
                pct_share = round(amt / total * 100) if total else 0
                lines.append(f"  {icon} {cat}: {amt:,.0f} EUR  ({pct_share}%)")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"_build_week_html failed: {e}", exc_info=True)
        return i18n.tu("week_error", lang, detail=str(e))


async def _build_contribution_html(session, lang: str = "ru") -> str:
    """Render contribution/split status — who owes what."""
    try:
        from intelligence import compute_contribution_status
        envelope_id = session.current_envelope_id or "MM_BUDGET"
        snap = compute_contribution_status(sheets, envelope_id)
        if snap.get("error"):
            return f"❌ {snap['error']}"
        if snap.get("status") != "ok":
            return i18n.tu("contrib_unavailable", lang)

        cur = snap["currency"]
        month = snap["month"]
        label = _month_label(month, lang)
        total_exp = snap["total_expenses"]
        threshold = snap["threshold"]
        excess = snap["excess_amount"]
        excess_per = snap["excess_per_user"]
        contributions = snap["contributions"]
        balances = snap["balances"]
        user_shares = snap["user_shares"]
        split_users = snap["split_users"]
        base_c = snap["base_contributor"]
        split_rule = snap["split_rule"]

        lines = [i18n.tu("contrib_title", lang, label=label), ""]

        # Contributions (who put in how much)
        if contributions:
            lines.append(i18n.tu("contrib_contributed", lang))
            for u in split_users:
                amt = float(contributions.get(u, 0))
                lines.append(f"  👤 {u}: {amt:,.0f} {cur}")
            lines.append("")

        # Total expenses and split
        lines.append(i18n.tu("contrib_total_exp", lang, total=total_exp, cur=cur))

        if split_rule == "solo" or len(split_users) <= 1:
            lines.append(i18n.tu("contrib_solo", lang, user=base_c))
        else:
            if total_exp <= threshold:
                lines.append(i18n.tu("contrib_below_threshold", lang,
                                     thr=threshold, cur=cur, user=base_c))
            else:
                lines.append(i18n.tu("contrib_excess", lang,
                                     thr=threshold, cur=cur, excess=excess,
                                     per=excess_per, user=base_c))

        # Shares
        if user_shares:
            lines.append("")
            lines.append(i18n.tu("contrib_shares", lang))
            for u in split_users:
                share = float(user_shares.get(u, 0))
                lines.append(f"  👤 {u}: {share:,.0f} {cur}")

        # Balances
        lines.append("")
        lines.append(i18n.tu("contrib_balance", lang))
        for u in split_users:
            b = float(balances.get(u, 0))
            if b > 0:
                lines.append(f"  👤 {u}: <b>+{b:,.0f} {cur}</b>  {i18n.tu('contrib_in_plus', lang)}")
            elif b < 0:
                lines.append(f"  👤 {u}: <b>{b:,.0f} {cur}</b>  {i18n.tu('contrib_owes', lang)}")
            else:
                lines.append(f"  👤 {u}: 0 {cur}  {i18n.tu('contrib_even', lang)}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"_build_contribution_html failed: {e}", exc_info=True)
        return i18n.tu("trends_error", lang, detail=str(e))


async def _build_trends_html(session, lang: str = "ru") -> str:
    """Render intelligence snapshot: budget trends + anomalies."""
    try:
        from intelligence import IntelligenceEngine
        envelope_id = session.current_envelope_id or "MM_BUDGET"
        engine = IntelligenceEngine(sheets)
        snap = engine.compute_snapshot(envelope_id)
        if snap.get("error"):
            return f"❌ {snap['error']}"

        cur = snap.get("currency", "EUR")
        month = snap.get("month", "")
        label = _month_label(month, lang)
        lines = [i18n.tu("trends_title", lang, label=label), ""]

        trends = snap.get("trends", [])
        if trends:
            lines.append(i18n.tu("trends_by_cat", lang))
            for t in trends:
                direction = t["direction"]
                cat = t["category"]
                cur_amt = t["current"]
                prev_amt = t["previous"]
                chg = t["change_pct"]
                icon = _cat_icon(cat)
                lines.append(
                    f"  {direction} {icon} <b>{cat}</b>: {cur_amt:,.0f} → "
                    f"({chg:+.0f}%  vs {prev_amt:,.0f} {cur})"
                )
        else:
            lines.append(i18n.tu("trends_empty", lang))

        anomalies = snap.get("anomalies", [])
        if anomalies:
            lines.append("")
            lines.append(i18n.tu("trends_anomalies", lang))
            for a in anomalies:
                icon = _cat_icon(a["category"])
                lines.append(
                    f"  {icon} {a['category']}: {a['current']:,.0f} {cur}  "
                    f"{i18n.tu('trends_anomaly_detail', lang, avg=a['average'], ratio=a['ratio'])}"
                )

        large = snap.get("large_recent", [])
        if large:
            lines.append("")
            lines.append(i18n.tu("trends_large", lang))
            for r in large:
                icon = _cat_icon(r.get("category", ""))
                note = f" — {r['note']}" if r.get("note") else ""
                lines.append(
                    f"  {icon} {r['amount']:,.0f} {cur}  {r['date']}{note}"
                )

        pace = snap.get("pace_status", "unknown")
        if pace == "over_pace":
            projected = snap.get("projected_total", 0)
            cap = snap.get("cap", 0)
            lines.append(i18n.tu("trends_over_pace", lang, proj=projected, cur=cur, cap=cap))
        elif pace == "under_pace":
            lines.append(i18n.tu("trends_under_pace", lang))

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"_build_trends_html failed: {e}", exc_info=True)
        return i18n.tu("trends_error", lang, detail=str(e))


async def _report_cat_rows(session, period: str, lang: str) -> list:
    """Return list of InlineKeyboardButton rows for category drill-down.
    Returns [] if categories can't be fetched (optional feature)."""
    try:
        from tools.summary import tool_get_summary
        summ = await tool_get_summary({"period": period}, session, sheets, auth)
        cats = sorted(summ.get("categories", {}).items(), key=lambda x: -x[1])[:6]
        rows = []
        for cat, _ in cats:
            cat_key = cat[:20]  # Telegram callback_data max 64 bytes
            cat_label = f"{_cat_icon(cat)} {cat[:18]}"
            rows.append([InlineKeyboardButton(cat_label, callback_data=f"cb_cat_drill:{period}:{cat_key}")])
        return rows
    except Exception as e:
        logger.debug(f"_report_cat_rows: {e}")
        return []


async def _build_category_html(session, period: str, category: str, lang: str = "ru") -> str:
    """Drill-down: show all transactions for a given category in a period."""
    try:
        from tools.transactions import tool_find_transactions
        result = await tool_find_transactions(
            {"period": period, "category": category, "limit": 30},
            session, sheets, auth,
        )
        if result.get("error"):
            return f"❌ {result['error']}"

        txs = [r for r in result.get("transactions", []) if r.get("Type") == "expense"]
        label = _month_label(period, lang)
        icon = _cat_icon(category)

        titles = {
            "ru": f"{icon} <b>{category}</b>  ·  {label}",
            "uk": f"{icon} <b>{category}</b>  ·  {label}",
            "en": f"{icon} <b>{category}</b>  ·  {label}",
            "it": f"{icon} <b>{category}</b>  ·  {label}",
        }
        lines = [titles.get(lang, titles["ru"]), ""]

        if not txs:
            empty = {"ru": "Записей нет.", "uk": "Записів немає.",
                     "en": "No records.", "it": "Nessun record."}
            lines.append(empty.get(lang, empty["ru"]))
            return "\n".join(lines)

        total = sum(float(r.get("Amount_EUR") or r.get("Amount_Orig") or 0) for r in txs)
        totals = {"ru": f"Итого: <b>{total:,.0f} EUR</b>  ·  {len(txs)} записей",
                  "uk": f"Разом: <b>{total:,.0f} EUR</b>  ·  {len(txs)} записів",
                  "en": f"Total: <b>{total:,.0f} EUR</b>  ·  {len(txs)} records",
                  "it": f"Totale: <b>{total:,.0f} EUR</b>  ·  {len(txs)} voci"}
        lines.append(totals.get(lang, totals["ru"]))
        lines.append("")

        for r in reversed(txs):  # chronological order
            date = r.get("Date", "")[:10]
            amt = float(r.get("Amount_EUR") or r.get("Amount_Orig") or 0)
            note = r.get("Note", "").strip()
            who = r.get("Who", "").strip()
            parts = [f"  {date}  <b>{amt:,.0f} EUR</b>"]
            if note:
                parts.append(f"  {note}")
            if who and who not in (session.name or ""):
                parts.append(f"  👤{who}")
            lines.append("".join(parts))

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"_build_category_html failed: {e}", exc_info=True)
        return f"❌ {e}"


# ── Post init ──────────────────────────────────────────────────────────────────

async def post_init(app: Application):
    """Register bot commands, ensure BotMenu sheet exists, schedule weekly summary."""
    # Set the native Telegram menu button to show commands (the [≡] left of input)
    try:
        if hasattr(app.bot, "set_my_menu_button"):
            await app.bot.set_my_menu_button(menu_button=MenuButtonCommands())
    except Exception as e:
        logger.warning(f"Could not set menu button: {e}")

    # Register commands for all users (default scope)
    await app.bot.set_my_commands(BOT_COMMANDS_ALL)

    # Register extended commands for admin users
    try:
        admin_tg_id = int(os.environ.get("MIKHAIL_TELEGRAM_ID", 0))
        if admin_tg_id:
            from telegram import BotCommandScopeChat
            await app.bot.set_my_commands(
                BOT_COMMANDS_ADMIN,
                scope=BotCommandScopeChat(chat_id=admin_tg_id),
            )
    except Exception as e:
        logger.warning(f"Could not set admin commands: {e}")
    logger.info("Bot commands registered in Telegram")

    # ── Auto-switch to test Admin when running with test bot token (T-042) ──
    _token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    _is_test_token = _token.startswith("8298458285:")  # test bot token prefix
    _uses_prod_admin = os.environ.get("ADMIN_SHEETS_ID", _PROD_ADMIN_ID) == _PROD_ADMIN_ID
    if _is_test_token and _uses_prod_admin:
        # Auto-fix: switch Admin to test — budget file_id resolves from Envelopes tab
        os.environ["ADMIN_SHEETS_ID"] = _TEST_ADMIN_ID
        sheets._admin.sheet_id = _TEST_ADMIN_ID
        sheets._admin._wb = None  # force re-open on next access
        logger.info(
            "🔄 TEST MODE: auto-switched to test Admin "
            f"(admin={_TEST_ADMIN_ID[:12]}…). Budget file resolves from Envelopes."
        )

    # Reset BotMenu tab to current defaults on every deploy (keeps sheet in sync with code)
    try:
        admin_id = os.environ.get("ADMIN_SHEETS_ID", "")
        mc.reset_to_defaults(sheets._gc, admin_id)
        mc.get_menu(sheets._gc, admin_id)
        logger.info("BotMenu sheet reset to defaults and loaded")
    except Exception as e:
        logger.warning(f"Could not reset BotMenu sheet: {e}")

    try:
        import pytz
        rome_tz = pytz.timezone("Europe/Rome")
        app.job_queue.run_daily(
            weekly_summary_job,
            time=dt.time(9, 0, tzinfo=rome_tz),
            days=(0,),
            name="weekly_summary",
        )
        logger.info("Weekly summary job scheduled: Monday 09:00 Rome")
    except Exception as e:
        logger.warning(f"Could not schedule weekly summary: {e}")

    # Initialize PostgreSQL (conversation log + user context)
    global _db_ready
    try:
        _db_ready = await appdb.init_db()
        if _db_ready:
            logger.info("PostgreSQL initialized — conversation history enabled")
        else:
            logger.warning("PostgreSQL not available — conversation history disabled")
    except Exception as e:
        logger.warning(f"Could not initialize PostgreSQL: {e}")

    # Initialize ReceiptStore
    global receipt_store
    try:
        receipt_store = ReceiptStore(sheets._gc, _get_active_file_id())
        logger.info("ReceiptStore initialized")
    except Exception as e:
        logger.warning(f"Could not initialize ReceiptStore: {e}")

    # Initialize ConversationLogger (writes to Admin Sheets)
    global conv_logger
    try:
        admin_id = os.environ.get("ADMIN_SHEETS_ID", "")
        if admin_id and sheets._gc:
            conv_logger = ConversationLogger(sheets._gc, admin_id)
            conv_logger.start()
            logger.info("ConversationLogger (Sheets) initialized")
        else:
            logger.warning("ConversationLogger skipped — no ADMIN_SHEETS_ID or sheets client")
    except Exception as e:
        logger.warning(f"Could not initialize ConversationLogger: {e}")


# ── Auth helper ────────────────────────────────────────────────────────────────

def _require_user(update: Update):
    user = update.effective_user
    tg_user = auth.get_user(user.id)
    if not tg_user:
        return None, None
    session = get_session(user.id, user.first_name, tg_user["role"])

    # Load saved user preferences once per session (language + active envelope)
    if getattr(session, "_prefs_loaded", False):
        return tg_user, session
    try:
        from user_context import UserContextManager
        ctx_mgr = UserContextManager(sheets._gc, _get_active_file_id())

        # Language preference
        saved_lang = ctx_mgr.get(user.id, "language")
        if saved_lang and saved_lang in i18n.SUPPORTED_LANGS:
            session.lang = saved_lang

        # Active envelope preference
        saved_env = ctx_mgr.get(user.id, "active_envelope")
        if saved_env:
            # Validate the saved envelope still exists
            try:
                known_ids = [e.get("ID") for e in sheets.get_envelopes()]
                if saved_env in known_ids:
                    session.current_envelope_id = saved_env
            except Exception:
                pass  # leave default

        session._prefs_loaded = True
        return tg_user, session
    except Exception as e:
        logger.debug(f"Could not load user prefs: {e}")

    # Fallback: Language detection from Telegram
    tg_lang = i18n.get_lang(getattr(user, "language_code", None) or "")
    if tg_lang in ("uk", "it"):
        session.lang = tg_lang
    elif not getattr(session, "lang", "") or session.lang == "en":
        session.lang = "ru"
    return tg_user, session


# ── Menu navigation helper ─────────────────────────────────────────────────────

async def _handle_menu_node(node_id: str, update: Update, ctx,
                             role: str = "admin") -> bool:
    """Handle a menu node tap. Returns True if the message was fully handled."""
    tg_user, session = _require_user(update)
    if not tg_user:
        return False

    lang = getattr(session, "lang", "en")

    if node_id in ("__menu__", "__root__"):
        tree = mc.get_menu()
        kb = _build_inline_menu("", tree, role, lang)
        await update.message.reply_text(i18n.t_menu("menu_title", lang), reply_markup=kb)
        return True

    tree = mc.get_menu()
    node = tree.get(node_id)
    if not node:
        return False

    # Role check
    if not mc.node_visible_for_role(node, role):
        await update.message.reply_text(i18n.ts("no_rights", "ru"))
        return True

    ntype = node.get("type", "cmd")

    if ntype == "submenu":
        kb = _build_inline_menu(node_id, tree, role, lang)
        node_label = i18n.t_menu(node_id, lang) or node["label"]
        await update.message.reply_text(
            node_label + ":",
            reply_markup=kb,
        )
        return True

    if ntype == "free_text":
        await update.message.reply_text(
            i18n.t("", lang, i18n.ADD_PROMPT),
            reply_markup=_with_menu_btn(lang=lang),
        )
        return True

    if ntype == "cmd":
        command = node.get("command", "")
        params  = node.get("params", {})
        if command == "status":
            await cmd_status(update, ctx)
        elif command == "report":
            period = params.get("period", "current")
            await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            html = await _build_report_html(session, period, lang)
            kb = _with_menu_btn(
                [InlineKeyboardButton(i18n.t_menu("rep_last", lang), callback_data="nav:rep_last"),
                 InlineKeyboardButton(i18n.t_menu("rep_curr", lang), callback_data="nav:rep_curr")],
            )
            await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif command == "transactions":
            await cmd_transactions(update, ctx)
        elif command == "week":
            await cmd_week(update, ctx)
        elif command == "help":
            await cmd_help(update, ctx)
        elif command == "envelopes":
            await cmd_envelopes(update, ctx)
        elif command == "refresh":
            await cmd_refresh(update, ctx)
        elif command == "undo":
            await cmd_undo(update, ctx)
        elif command == "settings":
            await cmd_settings(update, ctx)
        elif command == "contribution":
            await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            html = await _build_contribution_html(session, lang)
            kb = _with_menu_btn(
                [InlineKeyboardButton(i18n.t_menu("report", lang), callback_data="nav:rep_curr"),
                 InlineKeyboardButton(i18n.t_menu("rep_trends", lang), callback_data="nav:rep_trends")],
            )
            await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif command == "trends":
            await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            html = await _build_trends_html(session, lang)
            kb = _with_menu_btn(
                [InlineKeyboardButton(i18n.t_menu("report", lang), callback_data="nav:rep_curr"),
                 InlineKeyboardButton(i18n.t_menu("rep_contribution", lang), callback_data="nav:rep_contribution")],
            )
            await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            return False
        return True

    return False


# ── /start ─────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    logger.info("cmd_start invoked — bot v2.1.0 inline menu")
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "en")
    name = session.user_name or "Mikhail"
    msg = i18n.t("", lang, i18n.START_MSG).format(name=name)

    # Show welcome with persistent reply keyboard (stays in input bar)
    # Inline quick-access buttons below the text
    welcome_inline = InlineKeyboardMarkup([
        [InlineKeyboardButton(i18n.t_menu("report", lang), callback_data="nav:report")],
        [InlineKeyboardButton(_menu_label(lang), callback_data="nav:__menu__")],
    ])

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=_build_main_keyboard(lang),  # attach persistent reply keyboard
    )
    await update.message.reply_text(
        "👇",
        reply_markup=welcome_inline,
    )


async def cmd_log(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/log [username|user_id] — last 20 messages for a user (admin only)."""
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return
    if not auth.is_admin(session.user_id):
        await update.message.reply_text("❌ Только для администратора.")
        return

    args = ctx.args or []
    user_ref = args[0] if args else ""
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    from tools.admin import tool_get_user_log
    result = await tool_get_user_log(
        {"user_ref": user_ref, "limit": limit}, session, sheets, auth
    )

    if result.get("error"):
        await update.message.reply_text(f"❌ {result['error']}")
        return

    messages = result.get("messages", [])
    if not messages:
        await update.message.reply_text(
            f"Сообщений не найдено для {'<b>' + user_ref + '</b>' if user_ref else 'всех пользователей'}.",
            parse_mode=ParseMode.HTML,
        )
        return

    header = f"📋 <b>Лог</b> {'пользователя <code>' + user_ref + '</code>' if user_ref else '(все)'} — последние {len(messages)} сообщений:\n"
    lines = []
    for m in messages:
        role_icon = "👤" if m["role"] == "user" else "🤖"
        media = f" [{m['media_type']}]" if m["media_type"] else ""
        intent = f" <i>#{m['intent']}</i>" if m["intent"] else ""
        text = m["content"][:120].replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"{role_icon} <code>{m['ts']}</code> uid={m['user_id']}{media}{intent}\n{text}")

    full = header + "\n\n".join(lines)
    # Split if too long
    if len(full) > 4000:
        full = full[:4000] + "\n…(обрезано)"
    await update.message.reply_text(full, parse_mode=ParseMode.HTML)


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/stats [days] — activity stats from conversation_log (admin only)."""
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return
    if not auth.is_admin(session.user_id):
        await update.message.reply_text("❌ Только для администратора.")
        return

    args = ctx.args or []
    days = int(args[0]) if args and args[0].isdigit() else 7

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    from tools.admin import tool_get_stats
    result = await tool_get_stats({"days": days}, session, sheets, auth)

    if result.get("error"):
        await update.message.reply_text(f"❌ {result['error']}")
        return

    lines = [f"📊 <b>Статистика за {days} дней</b>\n"]
    lines.append(f"Уникальных пользователей: <b>{result['unique_users']}</b>")

    if result["by_day"]:
        lines.append("\n<b>Активность по дням:</b>")
        cur_day = None
        for r in result["by_day"]:
            if r["day"] != cur_day:
                cur_day = r["day"]
                lines.append(f"  📅 {cur_day}")
            lines.append(f"    uid={r['user_id']}: {r['messages']} сообщений")

    if result["top_intents"]:
        lines.append("\n<b>Топ интентов:</b>")
        for r in result["top_intents"]:
            lines.append(f"  • {r['intent']}: {r['count']}x")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Reload menu config from Admin sheet."""
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return
    lang = getattr(session, "lang", "ru")
    mc.invalidate()
    admin_id = os.environ.get("ADMIN_SHEETS_ID", "")
    mc.get_menu(sheets._gc, admin_id)  # pre-warm cache from sheet
    await update.message.reply_text(
        i18n.ts("menu_refreshed", lang),
        reply_markup=_with_menu_btn(lang=lang),
    )


# ── /admin_support ─────────────────────────────────────────────────────────────

async def cmd_admin_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/admin_support [status] — list open support requests (admin only)."""
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return
    if not auth.is_admin(session.user_id):
        await update.message.reply_text(i18n.ts("admin_only", "ru"))
        return

    args = ctx.args or []
    status_filter = args[0].upper() if args else "OPEN"

    from tools.support import tool_get_support_requests
    result = await tool_get_support_requests(
        {"status": status_filter, "limit": 20}, session, sheets, auth
    )

    if result.get("error"):
        await update.message.reply_text(f"❌ {result['error']}")
        return

    requests = result.get("requests", [])
    if not requests:
        await update.message.reply_text(
            f"📩 Нет запросов со статусом <b>{status_filter}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [f"📩 <b>Support — {status_filter}</b>  ({len(requests)} запросов)\n"]
    for r in requests:
        intent_icon = {"error": "🔴", "question": "🔵", "feedback": "🟡"}.get(r["intent"], "⚪")
        text_short = r["text"][:80].replace("<", "&lt;").replace(">", "&gt;")
        lines.append(
            f"{intent_icon} <code>#{r['id']}</code>  {r['ts']}  {r['user_name'] or r['user_id']}\n"
            f"   {text_short}"
        )

    full = "\n\n".join(lines)
    if len(full) > 4000:
        full = full[:4000] + "\n…"
    await update.message.reply_text(full, parse_mode=ParseMode.HTML)


# ── /idea ───────────────────────────────────────────────────────────────────────

async def cmd_idea(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/idea <text> — save an idea."""
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "ru")
    idea_text = " ".join(ctx.args or "").strip()
    if not idea_text:
        prompts = {
            "ru": "💡 Напишите идею после команды:\n<code>/idea ваша идея</code>",
            "uk": "💡 Напишіть ідею після команди:\n<code>/idea ваша ідея</code>",
            "en": "💡 Write your idea after the command:\n<code>/idea your idea</code>",
            "it": "💡 Scrivi la tua idea dopo il comando:\n<code>/idea la tua idea</code>",
        }
        await update.message.reply_text(
            prompts.get(lang, prompts["ru"]), parse_mode=ParseMode.HTML
        )
        return

    from tools.ideas import tool_save_idea
    result = await tool_save_idea(
        {"text": idea_text}, session, sheets, auth
    )

    if result.get("error"):
        await update.message.reply_text(f"❌ {result['error']}")
        return

    confirms = {
        "ru": f"💡 Идея сохранена (#{result['id']}):\n<i>{idea_text[:200]}</i>",
        "uk": f"💡 Ідею збережено (#{result['id']}):\n<i>{idea_text[:200]}</i>",
        "en": f"💡 Idea saved (#{result['id']}):\n<i>{idea_text[:200]}</i>",
        "it": f"💡 Idea salvata (#{result['id']}):\n<i>{idea_text[:200]}</i>",
    }
    await update.message.reply_text(
        confirms.get(lang, confirms["ru"]), parse_mode=ParseMode.HTML
    )


# ── /goal ──────────────────────────────────────────────────────────────────────

async def cmd_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/goal — show active goals; /goal add <type> <text>; /goal done #id."""
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "ru")
    args = ctx.args or []

    from tools.goals import tool_get_goals, tool_add_goal, tool_deactivate_goal, GOAL_TYPES, _progress_bar, _goal_type_label

    # /goal done <id>
    if args and args[0].lower() in ("done", "close", "закрыть", "готово"):
        raw_id = args[1].lstrip("#") if len(args) > 1 else ""
        if not raw_id.isdigit():
            await update.message.reply_text("Использование: /goal done <id>")
            return
        result = await tool_deactivate_goal({"id": int(raw_id)}, session, sheets, auth)
        msgs = {
            "ru": f"✅ Цель #{raw_id} закрыта.",
            "uk": f"✅ Ціль #{raw_id} закрита.",
            "en": f"✅ Goal #{raw_id} closed.",
            "it": f"✅ Obiettivo #{raw_id} chiuso.",
        }
        await update.message.reply_text(msgs.get(lang, msgs["ru"]))
        return

    # /goal add <type> <text>
    if args and args[0].lower() in ("add", "добавить", "новая", "нова"):
        goal_type = args[1].lower() if len(args) > 1 else "custom"
        goal_text = " ".join(args[2:]) if len(args) > 2 else ""
        if not goal_text:
            type_list = ", ".join(GOAL_TYPES.keys())
            await update.message.reply_text(
                f"Использование: /goal add <тип> <описание>\nТипы: {type_list}"
            )
            return
        result = await tool_add_goal(
            {"goal_type": goal_type, "goal_text": goal_text},
            session, sheets, auth,
        )
        if result.get("error"):
            await update.message.reply_text(f"❌ {result['error']}")
            return
        msgs = {
            "ru": f"🎯 Цель добавлена (#{result['id']}):\n<i>{goal_text}</i>",
            "uk": f"🎯 Ціль додано (#{result['id']}):\n<i>{goal_text}</i>",
            "en": f"🎯 Goal added (#{result['id']}):\n<i>{goal_text}</i>",
            "it": f"🎯 Obiettivo aggiunto (#{result['id']}):\n<i>{goal_text}</i>",
        }
        await update.message.reply_text(msgs.get(lang, msgs["ru"]), parse_mode=ParseMode.HTML)
        return

    # /goal — show current goals
    result = await tool_get_goals({}, session, sheets, auth)
    goals = result.get("goals", [])

    if not goals:
        empty = {
            "ru": "🎯 Активных целей нет.\n\nДобавить: /goal add custom Описание цели",
            "uk": "🎯 Активних цілей немає.\n\nДодати: /goal add custom Опис цілі",
            "en": "🎯 No active goals.\n\nAdd one: /goal add custom Goal description",
            "it": "🎯 Nessun obiettivo attivo.\n\nAggiungi: /goal add custom Descrizione obiettivo",
        }
        await update.message.reply_text(empty.get(lang, empty["ru"]))
        return

    titles = {"ru": "🎯 <b>Мои цели</b>", "uk": "🎯 <b>Мої цілі</b>",
              "en": "🎯 <b>My Goals</b>", "it": "🎯 <b>I miei obiettivi</b>"}
    lines = [titles.get(lang, titles["ru"]), ""]

    for g in goals:
        type_label = _goal_type_label(g["goal_type"], lang)
        pct = round(g["progress"] * 100)
        bar = _progress_bar(pct)
        lines.append(
            f"{type_label}  <code>#{g['id']}</code>\n"
            f"<i>{g['goal_text']}</i>\n"
            f"{bar}  {pct}%"
        )

    done_hint = {"ru": "Закрыть: /goal done #id", "uk": "Закрити: /goal done #id",
                 "en": "Close: /goal done #id", "it": "Chiudi: /goal done #id"}
    lines.append(f"\n{done_hint.get(lang, done_hint['ru'])}")

    await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)


# ── /menu ──────────────────────────────────────────────────────────────────────

async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "en")
    role = tg_user.get("role", "viewer")
    tree = mc.get_menu()
    kb = _build_inline_menu("", tree, role, lang)
    await update.message.reply_text(i18n.t_menu("menu_title", lang), reply_markup=kb)


# ── /settings ──────────────────────────────────────────────────────────────────

async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Show settings/service submenu (accessible to all users)."""
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "en")
    role = tg_user.get("role", "viewer")
    tree = mc.get_menu()
    kb = _build_inline_menu("settings", tree, role=role, lang=lang)
    await update.message.reply_text(i18n.ts("settings_title", lang), parse_mode=ParseMode.HTML,
                                    reply_markup=kb)


# ── /envelopes ─────────────────────────────────────────────────────────────────

async def cmd_envelopes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    try:
        envelopes = sheets.list_envelopes_with_links()
        # Filter to only envelopes the current user can access (T-039)
        envelopes = [e for e in envelopes if auth.can_access_envelope(session.user_id, e["id"])]
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при загрузке конвертов: {e}")
        return

    if not envelopes:
        await update.message.reply_text(
            i18n.ts("no_envelopes", getattr(session, "lang", "ru"))
        )
        return

    keyboard = []
    for i, e in enumerate(envelopes, 1):
        cap = f"{e['monthly_cap']:,} {e['currency']}" if e['monthly_cap'] else "—"
        active_mark = " ✅" if e["id"] == session.current_envelope_id else ""
        # Each envelope gets its own row with select button
        keyboard.append([
            InlineKeyboardButton(
                f"{i}. {e['name']}{active_mark}  ·  {cap}",
                callback_data=f"cb_env_{e['id']}"
            )
        ])

    active_name = next((e["name"] for e in envelopes if e["id"] == session.current_envelope_id), "—")
    header = f"📁 <b>Конверты</b>\nАктивный: <b>{active_name}</b>\n\nВыбери конверт:"

    await update.message.reply_text(
        header,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


# ── /envelope ──────────────────────────────────────────────────────────────────

async def cmd_envelope(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    if not ctx.args:
        envelopes = sheets.get_envelopes()
        active = [e for e in envelopes if str(e.get("Active", "TRUE")).upper() != "FALSE"]
        if not active:
            await update.message.reply_text("Конвертов нет. Создайте первый.")
            return

        lines = ["Доступные конверты:\n"]
        keyboard = []
        for e in active:
            eid = e.get("ID", "")
            ename = e.get("Name", eid)
            lines.append(f"• <code>{eid}</code> — {ename}")
            keyboard.append([InlineKeyboardButton(ename, callback_data=f"cb_env_{eid}")])

        await update.message.reply_text(
            "Использование: <code>/envelope ID</code>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    env_id = ctx.args[0].upper()
    envelopes = sheets.get_envelopes()
    match = next((e for e in envelopes if e.get("ID") == env_id), None)
    if not match:
        await update.message.reply_text(
            f"❌ Конверт <code>{env_id}</code> не найден.", parse_mode=ParseMode.HTML
        )
        return

    session.current_envelope_id = env_id
    try:
        ctx_mgr.set(update.effective_user.id, "active_envelope", env_id)
    except Exception:
        pass
    await update.message.reply_text(
        f"✅ Активный конверт: <b>{match['Name']}</b> (<code>{env_id}</code>)",
        parse_mode=ParseMode.HTML,
    )


# ── /status ────────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "ru")
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    html = await _build_status_html(session, lang)
    kb = _with_menu_btn(
        [InlineKeyboardButton(i18n.t_menu("report", lang), callback_data="cb_report"),
         InlineKeyboardButton(i18n.t_menu("transactions", lang), callback_data="cb_transactions")],
    )
    await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)


# ── /report ────────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "ru")
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Early in month with no data → auto-show previous month
    period = "current"
    if dt.date.today().day <= 10:
        try:
            from tools.summary import tool_get_summary
            check = await tool_get_summary({"period": "current"}, session, sheets, auth)
            if float(check.get("total_spent") or 0) == 0:
                period = "last"
        except Exception:
            pass

    html = await _build_report_html(session, period, lang)
    kb = _with_menu_btn(
        [InlineKeyboardButton(i18n.t_menu("rep_last", lang), callback_data="cb_report_last"),
         InlineKeyboardButton(i18n.t_menu("rep_curr", lang), callback_data="cb_report")],
    )
    await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)


# ── /week ──────────────────────────────────────────────────────────────────────

async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "ru")
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    html = await _build_week_html(session, lang)
    await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=_with_menu_btn(lang=lang))


# ── /month ─────────────────────────────────────────────────────────────────────

async def cmd_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "ru")
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # If early in month (≤10 days) and no data yet, auto-show previous month
    period = "current"
    if dt.date.today().day <= 10:
        try:
            from tools.summary import tool_get_summary
            check = await tool_get_summary({"period": "current"}, session, sheets, auth)
            if float(check.get("total_spent") or 0) == 0:
                period = "last"
        except Exception:
            pass

    html = await _build_report_html(session, period, lang)
    kb = _with_menu_btn(
        [InlineKeyboardButton(i18n.t_menu("rep_last", lang), callback_data="cb_report_last"),
         InlineKeyboardButton(i18n.t_menu("rep_curr", lang), callback_data="cb_report")],
    )
    await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)


# ── /transactions ──────────────────────────────────────────────────────────────

async def cmd_transactions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    lang = getattr(session, "lang", "ru")
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        from tools.transactions import tool_find_transactions
        result = await tool_find_transactions({"limit": 10}, session, sheets, auth)

        if result.get("error"):
            await update.message.reply_text(f"❌ {result['error']}")
            return

        txs = result.get("transactions", [])
        if not txs:
            await update.message.reply_text(
                i18n.ts("no_transactions", lang)
            )
            return

        html_body = _format_txn_list(txs, lang)

        # Inline delete buttons for last 5 transactions (1 per row)
        recent = list(reversed(txs))[:5]
        del_rows = []
        for tx in recent:
            tx_id = tx.get("ID", "")
            cat = tx.get("Category", "?")
            amt = tx.get("Amount_Orig", "?")
            date = tx.get("Date", "")[-5:]  # MM-DD
            del_rows.append([InlineKeyboardButton(
                f"🗑 {cat} · {amt} EUR · {date}", callback_data=f"cb_del_{tx_id}"
            )])

        markup = _with_menu_btn(*del_rows, lang=lang) if del_rows else _with_menu_btn(lang=lang)
        await update.message.reply_text(
            html_body,
            parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
    except Exception as e:
        logger.error(f"cmd_transactions failed: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {e}")


# ── /undo ──────────────────────────────────────────────────────────────────────

async def cmd_undo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    la = session.last_action
    if not la:
        await update.message.reply_text("Нет действий для отмены.")
        return

    try:
        if la.action == "add":
            envelopes = sheets.get_envelopes()
            file_id = next(
                (e["file_id"] for e in envelopes if e.get("ID") == la.envelope_id),
                None
            )
            if not file_id:
                await update.message.reply_text("❌ Конверт не найден.")
                return
            sheets.soft_delete_transaction(file_id, la.tx_id)
            snap = la.snapshot
            await update.message.reply_text(
                f"↩ Отменено: {snap.get('category', '')} · "
                f"{snap.get('amount', '')} {snap.get('currency', 'EUR')} · "
                f"{snap.get('date', '')}"
            )
        elif la.action == "edit":
            await update.message.reply_text(
                f"↩ Отмена изменения поля <code>{la.snapshot.get('field')}</code> не реализована.\n"
                f"Напишите, что нужно исправить.",
                parse_mode=ParseMode.HTML,
            )
        session.last_action = None
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось отменить: {e}")


# ── /help ──────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return
    lang = getattr(session, "lang", "ru")

    await update.message.reply_text(
        "📖 <b>Apolio Home — Справка</b>\n\n"
        "<b>Записать расход:</b>\n"
        "› кофе 3.50\n"
        "› продукты 85 EUR Esselunga\n"
        "› Marina купила одежду 120\n"
        "› oggi ho speso 45 euro\n\n"
        "<b>Доходы и переводы:</b>\n"
        "› получил зарплату 3000 EUR\n"
        "› перевёл 500 на сбережения\n\n"
        "<b>Отчёты:</b>\n"
        "› покажи отчёт за март\n"
        "› сколько потратили на еду\n"
        "› статус бюджета / сколько осталось?\n"
        "› покажи последние 5 записей\n\n"
        "<b>Конверты:</b>\n"
        "› /envelopes — список с ссылками\n"
        "› /envelope MM_BUDGET — выбрать\n"
        "› создай конверт «Отпуск» бюджет 2000 EUR\n\n"
        "<b>Исправления:</b>\n"
        "› не 45 а 54 / actually 90\n"
        "› это было вчера\n"
        "› /undo — отменить последнее\n\n"
        "<b>Команды:</b>\n"
        "/status · /report · /transactions\n"
        "/week · /month · /envelopes · /undo\n\n"
        "<i>Голос и фото чеков тоже работают 🎤📸</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=_with_menu_btn(lang=lang),
    )


# ── Inline keyboard callbacks ──────────────────────────────────────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tg_user = auth.get_user(query.from_user.id)
    if not tg_user:
        await query.edit_message_text(i18n.ts("access_denied", "ru"))
        return

    role = tg_user.get("role", "viewer")
    session = get_session(query.from_user.id, query.from_user.first_name, role)

    # Language: use cached value or load from UserContext
    if not getattr(session, "_lang_loaded", False):
        try:
            from user_context import UserContextManager
            ctx_mgr = UserContextManager(sheets._gc, _get_active_file_id())
            saved_lang = ctx_mgr.get(query.from_user.id, "language")
            if saved_lang and saved_lang in i18n.SUPPORTED_LANGS:
                session.lang = saved_lang
                session._lang_loaded = True
        except Exception:
            pass
        if not getattr(session, "_lang_loaded", False):
            tg_lang_cb = i18n.get_lang(getattr(query.from_user, "language_code", None) or "")
            if tg_lang_cb in ("uk", "it"):
                session.lang = tg_lang_cb
            elif not getattr(session, "lang", "") or session.lang == "en":
                session.lang = "ru"
            session._lang_loaded = True

    lang = session.lang
    data = query.data

    # ── Hard-delete confirmation ───────────────────────────────────────────
    if data.startswith("cb_confirm_del_"):
        await query.answer()
        pd = getattr(session, "pending_delete", None)
        if not pd:
            await query.edit_message_text("❌ Действие устарело. Повторите команду.")
            return
        try:
            count = sheets.delete_transaction_rows(
                pd["file_id"], pd["start_row"], pd["end_row"]
            )
            session.pending_delete = None
            n_word = "строка" if count == 1 else "строки" if count in (2, 3, 4) else "строк"
            await query.edit_message_text(
                f"✓ Удалено {count} {n_word} ({pd['start_row']}–{pd['end_row']})",
                reply_markup=_with_menu_btn(lang=lang),
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка удаления: {e}")
        return

    if data == "cb_cancel_del":
        await query.answer("Отменено")
        session.pending_delete = None
        try:
            await query.edit_message_text("Удаление отменено.", reply_markup=_with_menu_btn(lang=lang))
        except Exception:
            pass
        return

    # ── nav: dynamic menu navigation ───────────────────────────────────────
    if data.startswith("nav:"):
        node_id = data[4:]
        tree = mc.get_menu()

        # __menu__ / __root__ = show main menu (keyboard-only edit, keep message text)
        if node_id in ("__menu__", "__root__"):
            kb = _build_inline_menu("", tree, role, lang)
            try:
                await query.edit_message_reply_markup(reply_markup=kb)
            except BadRequest:
                pass
            return

        node = tree.get(node_id)
        if not node:
            await query.answer(i18n.ts("menu_not_found", lang), show_alert=True)
            return

        # Role check
        if not mc.node_visible_for_role(node, role):
            await query.answer(i18n.ts("no_rights", lang), show_alert=True)
            return

        ntype = node.get("type", "cmd")

        if ntype == "submenu":
            kb = _build_inline_menu(node_id, tree, role, lang)
            try:
                await query.edit_message_reply_markup(reply_markup=kb)
            except BadRequest:
                pass
            return

        if ntype == "cmd":
            command = node.get("command", "")
            params  = node.get("params", {})
            if command == "set_language":
                # Handle language switching
                target_lang = params.get("lang", "").lower()
                if target_lang in i18n.SUPPORTED_LANGS:
                    session.lang = target_lang
                    session._lang_loaded = True  # mark as resolved
                    # Save to UserContext
                    try:
                        from user_context import UserContextManager
                        ctx_mgr = UserContextManager(sheets._gc, _get_active_file_id())
                        ctx_mgr.set(query.from_user.id, "language", target_lang)
                    except Exception as e:
                        logger.debug(f"Could not save language to UserContext: {e}")
                    # Rebuild inline menu in new language
                    await query.answer(i18n.ts("lang_changed", target_lang), show_alert=False)
                    tree = mc.get_menu()
                    kb = _build_inline_menu("settings", tree, role, session.lang)
                    try:
                        await query.edit_message_reply_markup(reply_markup=kb)
                    except BadRequest:
                        pass
                    # Re-send the reply keyboard in the new language so buttons translate
                    try:
                        await query.message.reply_text(
                            i18n.ts("lang_changed", target_lang),
                            reply_markup=_build_main_keyboard(target_lang),
                        )
                    except Exception as e:
                        logger.debug(f"Could not refresh reply keyboard: {e}")
                    return
                else:
                    await query.answer(f"Unsupported language: {target_lang}", show_alert=True)
                    return
            elif command == "status":
                html = await _build_status_html(session, lang)
                kb = _with_menu_btn(
                    [InlineKeyboardButton(i18n.t_menu("report", lang),       callback_data="nav:report"),
                     InlineKeyboardButton(i18n.t_menu("transactions", lang), callback_data="nav:transactions")],
                )
            elif command == "report":
                period = params.get("period", "current")
                html = await _build_report_html(session, period, lang)
                # Compute month labels for nav buttons
                cur_m = _current_month_str()
                m1 = _offset_month(cur_m, -1)
                m2 = _offset_month(cur_m, -2)
                m3 = _offset_month(cur_m, -3)
                kb = _with_menu_btn(
                    [InlineKeyboardButton(_month_label(m3, lang)[:3], callback_data=f"cb_report_m:{m3}"),
                     InlineKeyboardButton(_month_label(m2, lang)[:3], callback_data=f"cb_report_m:{m2}"),
                     InlineKeyboardButton(_month_label(m1, lang)[:4], callback_data=f"cb_report_m:{m1}"),
                     InlineKeyboardButton("▶ " + _month_label(cur_m, lang)[:4], callback_data=f"cb_report_m:{cur_m}")],
                    lang=lang,
                )
            elif command == "week":
                html = await _build_week_html(session, lang)
                kb = _with_menu_btn(lang=lang)
            elif command == "transactions":
                limit_n = params.get("limit", 10)
                period  = params.get("period", "")
                try:
                    from tools.transactions import tool_find_transactions
                    find_params: dict = {"limit": limit_n}
                    if period == "current":
                        today_str = dt.date.today().strftime("%Y-%m")
                        find_params["date_from"] = f"{today_str}-01"
                    result = await tool_find_transactions(find_params, session, sheets, auth)
                    txs = result.get("transactions", [])
                    html = _format_txn_list(txs, lang) if txs else i18n.ts("no_transactions", lang)
                except Exception as e:
                    logger.error(f"transactions handler: {e}", exc_info=True)
                    html = f"❌ Ошибка: {e}"
                kb = _with_menu_btn(lang=lang)
            elif command == "envelopes":
                try:
                    envelopes = sheets.list_envelopes_with_links()
                    # Filter to only envelopes the current user can access (T-039)
                    envelopes = [e for e in envelopes if auth.can_access_envelope(session.user_id, e["id"])]
                    if envelopes:
                        active_name = next(
                            (e["name"] for e in envelopes if e["id"] == session.current_envelope_id), "—"
                        )
                        html = f"📁 <b>Конверты</b>\nАктивный: <b>{active_name}</b>\n\nВыбери конверт:"
                        def _env_btn_label(i, e, active_id):
                            cap = f"{e['monthly_cap']:,} {e['currency']}" if e.get('monthly_cap') else "—"
                            mark = "  ✅" if e["id"] == active_id else ""
                            return f"{i}. {e['name']}{mark}  ·  {cap}"
                        env_rows = [
                            [InlineKeyboardButton(
                                _env_btn_label(i, e, session.current_envelope_id),
                                callback_data=f"cb_env_{e['id']}"
                            )]
                            for i, e in enumerate(envelopes, 1)
                        ]
                        kb = _with_menu_btn(*env_rows, lang=lang)
                    else:
                        html = "📁 Нет конвертов."
                        kb = _with_menu_btn(lang=lang)
                except Exception as e:
                    html = f"❌ Ошибка: {e}"
                    kb = _with_menu_btn(lang=lang)
            elif command == "refresh":
                admin_id = os.environ.get("ADMIN_SHEETS_ID", "")
                mc.reset_to_defaults(sheets._gc, admin_id)
                tree = mc.get_menu(sheets._gc, admin_id)
                await query.answer(i18n.ts("menu_refreshed", lang), show_alert=False)
                kb = _build_inline_menu("settings", tree, role, lang)
                try:
                    await query.edit_message_reply_markup(reply_markup=kb)
                except BadRequest:
                    pass
                return
            elif command == "undo":
                la = session.last_action
                if not la:
                    await query.answer("Нет действий для отмены.", show_alert=True)
                    return
                try:
                    if la.action == "add":
                        envelopes = sheets.get_envelopes()
                        file_id = next(
                            (ev["file_id"] for ev in envelopes if ev.get("ID") == la.envelope_id),
                            None
                        )
                        if file_id:
                            sheets.soft_delete_transaction(file_id, la.tx_id)
                            snap = la.snapshot
                            html = (f"↩ Отменено: {snap.get('category', '')} · "
                                    f"{snap.get('amount', '?')} {snap.get('currency', 'EUR')}")
                            session.last_action = None
                        else:
                            html = "❌ Конверт не найден."
                    else:
                        html = "❌ Неизвестное действие."
                except Exception as e:
                    html = f"❌ Ошибка: {e}"
                kb = _with_menu_btn(lang=lang)
            elif command == "contribution":
                html = await _build_contribution_html(session, lang)
                kb = _with_menu_btn(
                    [InlineKeyboardButton(i18n.t_menu("rep_curr", lang), callback_data="nav:rep_curr"),
                     InlineKeyboardButton(i18n.t_menu("rep_trends", lang), callback_data="nav:rep_trends")],
                    lang=lang,
                )
            elif command == "trends":
                html = await _build_trends_html(session, lang)
                kb = _with_menu_btn(
                    [InlineKeyboardButton(i18n.t_menu("rep_curr", lang), callback_data="nav:rep_curr"),
                     InlineKeyboardButton(i18n.t_menu("rep_contribution", lang), callback_data="nav:rep_contribution")],
                    lang=lang,
                )
            elif command == "dashboard_refresh":
                if not auth.is_admin(session.user_id):
                    await query.answer("Только для администратора.", show_alert=True)
                    return
                try:
                    result = await agent._tool_refresh_dashboard({}, session, sheets, auth)
                    status_msg = result.get("status", "error")
                    html = "🔄 <b>Дашборд обновлён</b>" if status_msg == "ok" else f"❌ {result.get('error', 'Ошибка')}"
                except Exception as e:
                    html = f"❌ Ошибка: {e}"
                kb = _with_menu_btn(lang=lang)
            elif command == "mode_toggle":
                if not auth.is_admin(session.user_id):
                    await query.answer("Только для администратора.", show_alert=True)
                    return
                try:
                    cfg = sheets.get_dashboard_config()
                    current_mode = cfg.get("mode", "prod").lower()
                    new_mode = "test" if current_mode == "prod" else "prod"
                    sheets.write_dashboard_config("mode", new_mode)
                    html = i18n.tu("mode_test_on" if new_mode == "test" else "mode_prod_on", lang)
                except Exception as e:
                    html = f"❌ Ошибка: {e}"
                kb = _with_menu_btn(lang=lang)
            elif command == "config_view":
                if not auth.is_admin(session.user_id):
                    await query.answer("Только для администратора.", show_alert=True)
                    return
                try:
                    # Auto-init missing keys on every config view
                    env_id_for_init = session.current_envelope_id or "MM_BUDGET"
                    _init_result = sheets.ensure_envelope_config(env_id_for_init)
                    _was_init = bool(_init_result.get("written"))
                    env_id = env_id_for_init
                    # Resolve envelope name and file URL
                    envelopes = sheets.get_envelopes()
                    env_obj = next((e for e in envelopes if e.get("ID") == env_id), None)
                    env_name = env_obj.get("Name", env_id) if env_obj else env_id
                    env_file_id = env_obj.get("file_id", "") if env_obj else ""
                    env_url = (
                        f"https://docs.google.com/spreadsheets/d/{env_file_id}"
                        if env_file_id else ""
                    )

                    # Admin global config
                    admin_cfg = sheets.read_config()
                    # Envelope-specific config (from envelope's own Config tab)
                    env_config = sheets.read_envelope_config(env_file_id)
                    dash_cfg = sheets.get_dashboard_config()

                    lines = [f"⚙️ <b>Конфигурация</b>", ""]
                    lines.append(f"📁 <b>Активный файл:</b> {env_name}")
                    if env_url:
                        lines.append(f"🔗 <a href=\"{env_url}\">Открыть в Google Sheets</a>")
                    lines.append(f"🆔 <code>{env_id}</code>")
                    lines.append("")

                    # Envelope-specific settings
                    if env_config:
                        lines.append("<b>Настройки конверта:</b>")
                        for k in sorted(env_config):
                            lines.append(f"  <code>{k}</code> = {env_config[k]}")
                    else:
                        lines.append("<b>Настройки конверта:</b> пусто")
                        lines.append("  <i>Добавьте split_rule, split_threshold, split_users,</i>")
                        lines.append("  <i>base_contributor в Config вкладку файла конверта</i>")
                    lines.append("")

                    # Global admin config (non-envelope keys only)
                    global_keys = [k for k in admin_cfg if not any(
                        env_id_check in k for env_id_check in ["_MM_", "_TEST_"]
                    )]
                    if global_keys:
                        lines.append("<b>Admin Config (глобальные):</b>")
                        for k in sorted(global_keys):
                            lines.append(f"  <code>{k}</code> = {admin_cfg[k]}")
                        lines.append("")

                    lines.append("<b>Dashboard Config:</b>")
                    for k, v in sorted(dash_cfg.items()):
                        lines.append(f"  <code>{k}</code> = {v}")
                    html = "\n".join(lines)
                except Exception as e:
                    html = f"❌ Ошибка: {e}"
                kb = _with_menu_btn(lang=lang)
            elif command == "init_config":
                if not auth.is_admin(session.user_id):
                    await query.answer("Только для администратора.", show_alert=True)
                    return
                try:
                    env_id = session.current_envelope_id or "MM_BUDGET"
                    result = sheets.ensure_envelope_config(env_id)
                    if result.get("error"):
                        html = f"❌ Ошибка: {result['error']}"
                    else:
                        written = result.get("written", [])
                        skipped = result.get("skipped", [])
                        lines = [f"🔧 <b>Init Config: {env_id}</b>", ""]
                        if written:
                            lines.append(f"✅ <b>Записано ({len(written)}):</b>")
                            for k in written:
                                lines.append(f"  <code>{k}</code>")
                        else:
                            lines.append("✅ Все ключи уже присутствуют")
                        if skipped:
                            lines.append(f"⏭ <b>Пропущено (уже есть):</b> {', '.join(skipped)}")
                        lines.append("")
                        lines.append("Откройте Config вкладку конверта чтобы проверить.")
                        if _was_init:
                            lines.insert(2, f"🔧 <i>Авто-инициализировано: {', '.join(_init_result['written'])}</i>")
                    html = "\n".join(lines)
                except Exception as e:
                    html = f"❌ Ошибка: {e}"
                kb = _with_menu_btn(lang=lang)
            elif command == "users_view":
                if not auth.is_admin(session.user_id):
                    await query.answer("Только для администратора.", show_alert=True)
                    return
                try:
                    users = sheets._admin.get_users()
                    lines = [f"👥 <b>Пользователи</b>  ({len(users)} чел.)", ""]
                    for u in users:
                        name = u.get("name", "?")
                        role = u.get("role", "?")
                        tid = u.get("telegram_id", "—")
                        status = u.get("status", "active")
                        envelopes = u.get("envelopes", "")
                        status_icon = "✅" if status == "active" else "❌"
                        lines.append(f"{status_icon} <b>{name}</b>  [{role}]")
                        lines.append(f"   ID: <code>{tid}</code>")
                        if envelopes:
                            lines.append(f"   Конверты: {envelopes}")
                    html = "\n".join(lines)
                except Exception as e:
                    html = f"❌ Ошибка: {e}"
                kb = _with_menu_btn(lang=lang)
            elif command == "learning_summary":
                if not auth.is_admin(session.user_id):
                    await query.answer("Только для администратора.", show_alert=True)
                    return
                try:
                    import db as appdb
                    if appdb.is_ready():
                        # Use refresh_learning_summary tool result as text
                        ctx_text = await appdb.get_learning_context_for_prompt(session.user_id)
                        if ctx_text.strip():
                            html = f"🧠 <b>База знаний</b>\n\n<code>{ctx_text[:2000]}</code>"
                        else:
                            html = "🧠 <b>База знаний</b>\n\nДанных пока нет."
                    else:
                        html = "🧠 База знаний недоступна (БД не подключена)."
                except Exception as e:
                    html = f"❌ Ошибка: {e}"
                kb = _with_menu_btn(lang=lang)
            else:
                await query.answer(i18n.ts("cmd_not_supported", lang), show_alert=True)
                return
            # Send as NEW message (not edit) — keeps chat history
            await query.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)
            return

        if ntype == "free_text":
            prompt_text = node.get("params", {}).get("prompt", i18n.ts("input_prompt", lang))
            pending_key = node.get("params", {}).get("pending_key", "")
            if pending_key:
                session.pending_prompt = pending_key
            await query.message.reply_text(
                f"✏️ {prompt_text}",
                parse_mode=ParseMode.HTML,
            )
            return

    # ── cb_envelopes ───────────────────────────────────────────────────────
    if data == "cb_envelopes":
        try:
            envelopes = sheets.list_envelopes_with_links()
            # Filter to only envelopes the current user can access (T-039)
            envelopes = [e for e in envelopes if auth.can_access_envelope(session.user_id, e["id"])]
        except Exception as e:
            await query.edit_message_text(f"❌ {e}")
            return
        if not envelopes:
            await query.edit_message_text("Конвертов нет.")
            return
        lines = ["📁 <b>Список конвертов:</b>\n"]
        for e in envelopes:
            cap = f"{e['monthly_cap']:,} {e['currency']}" if e['monthly_cap'] else i18n.NO_LIMIT.get(lang, "no limit")
            url = e.get("url", "")
            link = f'  <a href="{url}">открыть</a>' if url else ""
            active_mark = " ✅" if e["id"] == session.current_envelope_id else ""
            lines.append(f"▸ <b>{e['name']}</b> (<code>{e['id']}</code>){active_mark} · {cap}{link}")
        keyboard = [[InlineKeyboardButton(e["name"], callback_data=f"cb_env_{e['id']}")] for e in envelopes]
        try:
            await query.edit_message_text(
                "\n\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True,
            )
        except BadRequest:
            pass  # message unchanged

    # ── cb_status ──────────────────────────────────────────────────────────
    elif data == "cb_status":
        html = await _build_status_html(session, lang)
        kb = _with_menu_btn(
            [InlineKeyboardButton(i18n.t_menu("report", lang), callback_data="cb_report"),
             InlineKeyboardButton(i18n.t_menu("transactions", lang), callback_data="cb_transactions")],
        )
        await query.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)

    # ── cb_report ──────────────────────────────────────────────────────────
    elif data == "cb_report":
        cur_m = _current_month_str()
        m1 = _offset_month(cur_m, -1)
        m2 = _offset_month(cur_m, -2)
        html = await _build_report_html(session, cur_m, lang)
        cat_rows = await _report_cat_rows(session, cur_m, lang)
        kb = _with_menu_btn(
            [InlineKeyboardButton(_month_label(m2, lang)[:4], callback_data=f"cb_report_m:{m2}"),
             InlineKeyboardButton(_month_label(m1, lang)[:4], callback_data=f"cb_report_m:{m1}"),
             InlineKeyboardButton("▶ " + _month_label(cur_m, lang)[:4], callback_data=f"cb_report_m:{cur_m}")],
            *cat_rows, lang=lang,
        )
        await query.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data == "cb_report_last":
        cur_m = _current_month_str()
        m1 = _offset_month(cur_m, -1)
        m2 = _offset_month(cur_m, -2)
        html = await _build_report_html(session, m1, lang)
        cat_rows = await _report_cat_rows(session, m1, lang)
        kb = _with_menu_btn(
            [InlineKeyboardButton(_month_label(m2, lang)[:4], callback_data=f"cb_report_m:{m2}"),
             InlineKeyboardButton("▶ " + _month_label(m1, lang)[:4], callback_data=f"cb_report_m:{m1}"),
             InlineKeyboardButton(_month_label(cur_m, lang)[:4], callback_data=f"cb_report_m:{cur_m}")],
            *cat_rows, lang=lang,
        )
        await query.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)

    elif data.startswith("cb_report_m:"):
        period = data.split(":", 1)[1]
        cur_m = _current_month_str()
        m1 = _offset_month(cur_m, -1)
        m2 = _offset_month(cur_m, -2)
        m3 = _offset_month(cur_m, -3)
        html = await _build_report_html(session, period, lang)

        # Month navigation row
        nav_months = [m3, m2, m1, cur_m]
        nav_btns = []
        for nm in nav_months:
            label = ("▶ " if nm == period else "") + _month_label(nm, lang)[:4]
            nav_btns.append(InlineKeyboardButton(label, callback_data=f"cb_report_m:{nm}"))

        # Category drill-down buttons
        cat_rows = await _report_cat_rows(session, period, lang)

        kb = _with_menu_btn(nav_btns, *cat_rows, lang=lang)
        await query.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)

    # ── cb_cat_drill ───────────────────────────────────────────────────────
    elif data.startswith("cb_cat_drill:"):
        # cb_cat_drill:{period}:{category}
        parts = data.split(":", 2)
        if len(parts) < 3:
            await query.answer("Bad callback", show_alert=False)
            return
        period = parts[1]
        category = parts[2]

        html = await _build_category_html(session, period, category, lang)
        # "Back to report" button
        back_labels = {"ru": "← Отчёт", "uk": "← Звіт", "en": "← Report", "it": "← Report"}
        back_btn = InlineKeyboardButton(
            back_labels.get(lang, "← Report"),
            callback_data=f"cb_report_m:{period}"
        )
        kb = _with_menu_btn([back_btn], lang=lang)
        await query.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)

    # ── cb_transactions ────────────────────────────────────────────────────
    elif data == "cb_transactions":
        try:
            from tools.transactions import tool_find_transactions
            result = await tool_find_transactions({"limit": 8}, session, sheets, auth)
            txs = result.get("transactions", [])
            if not txs:
                await query.message.reply_text(i18n.ts("no_transactions", lang), reply_markup=_with_menu_btn(lang=lang))
                return
            html_body = _format_txn_list(txs, lang)
            del_rows = []
            recent = list(reversed(txs))[:4]
            for tx in recent:
                tx_id = tx.get("ID", "")
                cat = tx.get("Category", "?")
                amt = tx.get("Amount_Orig", "?")
                del_rows.append([InlineKeyboardButton(
                    f"🗑 {cat} · {amt} EUR", callback_data=f"cb_del_{tx_id}"
                )])
            markup = _with_menu_btn(*del_rows, lang=lang) if del_rows else _with_menu_btn(lang=lang)
            await query.message.reply_text(
                html_body,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        except Exception as e:
            await query.message.reply_text(f"❌ {e}", reply_markup=_with_menu_btn(lang=lang))

    # ── cb_help ────────────────────────────────────────────────────────────
    elif data == "cb_help":
        try:
            await query.edit_message_text(
                "📖 <b>Справка</b>\n\n"
                "Просто пишите естественным языком:\n"
                "› «кофе 3.50» или «продукты 85 EUR»\n"
                "› «покажи отчёт за март»\n"
                "› «создай конверт Отпуск бюджет 2000 EUR»\n\n"
                "<b>Команды:</b> /menu /envelopes /status /report /transactions /week /undo /help",
                parse_mode=ParseMode.HTML,
            )
        except BadRequest:
            pass

    # ── cb_env_<ID> — select active envelope ──────────────────────────────
    elif data.startswith("cb_env_"):
        env_id = data[7:]
        envelopes = sheets.get_envelopes()
        match = next((e for e in envelopes if e.get("ID") == env_id), None)
        if not match:
            await query.edit_message_text(
                f"❌ Конверт <code>{env_id}</code> не найден.", parse_mode=ParseMode.HTML
            )
            return

        # Set in session
        session.current_envelope_id = env_id
        # Invalidate prefs so next _require_user reloads (not strictly needed
        # but safe when saving from this path)
        session._prefs_loaded = True

        # Persist to UserContext so it survives bot restarts
        try:
            from user_context import UserContextManager
            ctx_mgr = UserContextManager(sheets._gc, _get_active_file_id())
            ctx_mgr.set(query.from_user.id, "active_envelope", env_id)
        except Exception as e:
            logger.debug(f"Could not save active_envelope: {e}")

        # Build confirmation with envelope info + sheet link button
        cap = match.get("Monthly_Cap") or match.get("monthly_cap", 0)
        cap_str = f"{float(cap):,.0f} {match.get('Currency', 'EUR')}" if cap else i18n.NO_LIMIT.get(lang, "no limit")
        file_id_val = match.get("file_id", "")
        sheet_url = f"https://docs.google.com/spreadsheets/d/{file_id_val}" if file_id_val else ""
        extra_rows = []
        if sheet_url:
            extra_rows.append([InlineKeyboardButton("📊 Открыть таблицу", url=sheet_url)])
        try:
            await query.edit_message_text(
                f"✅ <b>Активный конверт: {match['Name']}</b>  (<code>{env_id}</code>)\n"
                f"Бюджет: {cap_str}",
                parse_mode=ParseMode.HTML,
                reply_markup=_with_menu_btn(*extra_rows, lang=lang),
            )
        except BadRequest:
            pass

    # ── cb_del_confirm_<tx_id> ─────────────────────────────────────────────
    elif data.startswith("cb_del_confirm_"):
        tx_id = data[15:]
        try:
            envelopes = sheets.get_envelopes()
            deleted = False
            for e in envelopes:
                if e.get("ID") == session.current_envelope_id:
                    deleted = sheets.hard_delete_transaction(e["file_id"], tx_id)
                    break
            if deleted:
                await query.edit_message_text(
                    f"🗑 Запись удалена из таблицы (<code>{tx_id}</code>)",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await query.edit_message_text(
                    f"⚠️ Запись не найдена в таблице: <code>{tx_id}</code>",
                    parse_mode=ParseMode.HTML,
                )
            session.last_action = None
        except Exception as ex:
            await query.edit_message_text(f"❌ Ошибка: {ex}")

    # ── cb_choice_<value> — agent choice buttons ───────────────────────────
    elif data.startswith("cb_choice_"):
        chosen_value = data[10:]
        await query.answer()
        # Pass chosen value back to agent as if the user sent it as text
        try:
            await ctx.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
            response = await agent.run(chosen_value, session)
            pending_ch2 = getattr(session, "pending_choice", None)
            if pending_ch2:
                session.pending_choice = None
                choice_rows2 = [
                    [InlineKeyboardButton(c["label"], callback_data=f"cb_choice_{c['value']}")]
                    for c in pending_ch2
                ]
                kb = _with_menu_btn(*choice_rows2, lang=lang)
            else:
                kb = _with_menu_btn(lang=lang)
            await ctx.bot.send_message(
                chat_id=query.message.chat_id,
                text=response,
                reply_markup=kb,
            )
        except Exception as e:
            await ctx.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ {e}",
            )

    # ── cb_del_<tx_id> ─────────────────────────────────────────────────────
    elif data.startswith("cb_del_"):
        tx_id = data[7:]
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Да, удалить", callback_data=f"cb_del_confirm_{tx_id}"),
                    InlineKeyboardButton("❌ Отмена", callback_data="cb_cancel"),
                ]])
            )
        except BadRequest:
            pass

    # ── cb_edit_<tx_id> ────────────────────────────────────────────────────
    elif data.startswith("cb_edit_"):
        tx_id = data[8:]
        session.pending_edit_tx = tx_id
        try:
            await query.edit_message_text(
                f"Что изменить в записи <code>{tx_id}</code>?\n\n"
                "Напишите например:\n"
                "«сумма 90» или «категория транспорт» или «дата вчера»",
                parse_mode=ParseMode.HTML,
            )
        except BadRequest:
            pass

    # ── cb_cancel ──────────────────────────────────────────────────────────
    elif data == "cb_cancel":
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except BadRequest:
            pass


# ── Main message handler ───────────────────────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text(i18n.ts("access_denied", "ru"))
        return

    # Ensure session has a session_id for conversation logging
    if not getattr(session, "session_id", None):
        session.session_id = make_session_id()

    msg = update.message
    text = ""
    media_type = "text"
    media_data = None
    media_file_id = ""  # Telegram file_id for photos — stored in DB for image memory

    role = tg_user.get("role", "viewer")
    lang = getattr(session, "lang", "en")

    if msg.text:
        text = msg.text.strip()

        # ── Pending free-text prompt handler ───────────────────────────────
        pending = getattr(session, "pending_prompt", None)
        if pending:
            session.pending_prompt = None  # consume immediately
            await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

            if pending == "report:custom_period":
                # Try YYYY-MM format directly; otherwise let agent interpret
                period_match = re.match(r'(\d{4}-\d{2})(?::(\d{4}-\d{2}))?', text.strip())
                if period_match:
                    period = text.strip().split()[0]  # take first token
                    html = await _build_report_html(session, period, lang)
                    kb = _with_menu_btn(
                        [InlineKeyboardButton(i18n.t_menu("rep_last", lang), callback_data="nav:rep_last"),
                         InlineKeyboardButton(i18n.t_menu("rep_curr", lang), callback_data="nav:rep_curr")],
                    )
                    await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=kb)
                else:
                    # Pass to agent — it understands "февраль", "march", etc.
                    response = await agent.run(f"покажи отчёт за {text}", session)
                    await _safe_reply(update.message, response, reply_markup=_with_menu_btn(lang=lang))
                return

            elif pending == "transactions:search":
                response = await agent.run(
                    f"найди записи по запросу: {text}", session
                )
                await _safe_reply(update.message, response, reply_markup=_with_menu_btn(lang=lang))
                return

            elif pending == "transactions:category":
                await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                try:
                    from tools.transactions import tool_find_transactions
                    result = await tool_find_transactions(
                        {"category": text.strip(), "limit": 20},
                        session, sheets, auth,
                    )
                    if result.get("error"):
                        await update.message.reply_text(f"❌ {result['error']}")
                        return
                    txs = result.get("transactions", [])
                    if not txs:
                        await update.message.reply_text(
                            f"📝 Записей по категории «{text}» нет."
                        )
                        return
                    total = sum(
                        float(r.get("Amount_EUR") or r.get("Amount_Orig") or 0) for r in txs
                    )
                    lines = [f"📝 <b>Категория «{text}»</b> — {len(txs)} записей · {total:,.0f} EUR\n"]
                    for tx in txs[-20:]:
                        date = tx.get("Date", "")
                        amt  = tx.get("Amount_Orig", tx.get("Amount_EUR", "?"))
                        curr = tx.get("Currency_Orig", "EUR")
                        note = tx.get("Note", "")
                        who  = tx.get("Who", "")
                        note_part = f"  <i>{note}</i>" if note else ""
                        who_part  = f" · {who}" if who else ""
                        lines.append(f"• {date}  {amt} {curr}{who_part}{note_part}")
                    await update.message.reply_text(
                        "\n".join(lines), parse_mode=ParseMode.HTML,
                        reply_markup=_with_menu_btn(lang=lang),
                    )
                except Exception as e:
                    logger.error(f"transactions:category failed: {e}", exc_info=True)
                    await update.message.reply_text(f"❌ Ошибка: {e}")
                return

        # ── Menu button intercept (catches lingering reply keyboard taps) ──
        _MENU_TRIGGERS = {"☰ меню", "≡ меню", "☰ menu", "меню", "/menu"}
        if text.strip().lower() in _MENU_TRIGGERS:
            tree = mc.get_menu()
            kb = _build_inline_menu("", tree, role, lang)
            await update.message.reply_text(i18n.t_menu("menu_title", lang), reply_markup=kb)
            return

        # ── Keyboard shortcut intercept (any language, via reverse map) ──
        action = i18n.KB_TEXT_TO_ACTION.get(text)
        if action:
            tree = mc.get_menu()
            role = tg_user.get("role", "viewer")
            if action in ("budget", "status"):
                # 💰 Бюджет (primary) or legacy 📊 Статус
                await cmd_status(update, ctx)
            elif action == "more":
                # ☰ Ещё — opens the full inline navigation menu
                kb = _build_inline_menu("", tree, role, lang)
                await update.message.reply_text(i18n.t_menu("menu_title", lang), reply_markup=kb)
            elif action == "report":
                kb = _build_inline_menu("report", tree, role, lang)
                await update.message.reply_text(i18n.ts("report_title", lang), reply_markup=kb)
            elif action == "records":
                kb = _build_inline_menu("transactions", tree, role, lang)
                await update.message.reply_text(i18n.ts("records_title", lang), reply_markup=kb)
            elif action == "add":
                await update.message.reply_text(i18n.t("", lang, i18n.ADD_PROMPT))
            elif action == "envelopes":
                await cmd_envelopes(update, ctx)
            elif action == "settings":
                kb = _build_inline_menu("settings", tree, role, lang)
                await update.message.reply_text(i18n.ts("settings_title", lang), reply_markup=kb)
            return

        # ── Greeting intercept ─────────────────────────────────────────────
        if text.lower() in GREETINGS:
            await update.message.reply_text(
                i18n.t("", lang, i18n.GREETING_MSG),
                parse_mode=ParseMode.HTML,
                reply_markup=_with_menu_btn(lang=lang),
            )
            return

    elif msg.voice or msg.audio:
        file_obj = await (msg.voice or msg.audio).get_file()
        audio_bytes = await file_obj.download_as_bytearray()
        text = await transcribe_audio(bytes(audio_bytes))
        # Echo transcription back so user knows what was heard
        try:
            await update.message.reply_text(
                f"🎤 <i>{text}</i>", parse_mode=ParseMode.HTML
            )
        except BadRequest:
            await update.message.reply_text(f"🎤 {text}")

    elif msg.photo:
        file_obj = await msg.photo[-1].get_file()
        media_data = bytes(await file_obj.download_as_bytearray())
        media_file_id = msg.photo[-1].file_id  # save Telegram file_id for memory
        # Default prompt used ONLY when there is no caption.
        # With a caption: the caption IS the instruction (e.g. "запиши взнос" → record immediately).
        # Without a caption: analyze, show findings, ask for confirmation before recording.
        _photo_auto_analyze = {
            "ru": (
                "Проанализируй это изображение полностью. "
                "Извлеки ВСЕ данные: суммы, даты, категории, кто платил — точно как на фото. "
                "Не записывай ничего сам. "
                "Покажи мне список всего, что ты увидел, и спроси что с этим сделать."
            ),
            "uk": (
                "Проаналізуй це зображення повністю. "
                "Витягни ВСІ дані: суми, дати, категорії, хто платив — точно як на фото. "
                "Нічого не записуй сам. "
                "Покажи мені список усього, що ти побачив, і спитай що з цим робити."
            ),
            "en": (
                "Analyze this image fully. "
                "Extract ALL data: amounts, dates, categories, who paid — exactly as shown. "
                "Do NOT record anything yet. "
                "Show me everything you found and ask what to do with it."
            ),
            "it": (
                "Analizza questa immagine completamente. "
                "Estrai TUTTI i dati: importi, date, categorie, chi ha pagato — esattamente come mostrato. "
                "Non registrare nulla da solo. "
                "Mostrami tutto ciò che hai trovato e chiedi cosa fare."
            ),
        }
        text = msg.caption or _photo_auto_analyze.get(lang, _photo_auto_analyze["en"])
        media_type = "photo"

    elif msg.document and msg.document.mime_type in ("text/csv", "application/csv"):
        file_obj = await msg.document.get_file()
        csv_bytes = await file_obj.download_as_bytearray()
        text = f"[CSV import]\n{csv_bytes.decode('utf-8', errors='replace')}"

    else:
        await update.message.reply_text(i18n.ts("unsupported_media", lang))
        return

    # ── Inject pending edit context ────────────────────────────────────────
    pending_tx = getattr(session, "pending_edit_tx", None)
    if pending_tx:
        session.pending_edit_tx = None
        text = f"[edit tx_id={pending_tx}] {text}"

    # ── Thinking indicator ────────────────────────────────────────────────
    # Send a visible "thinking" message so the user sees something immediately.
    # It will be deleted once the agent finishes.
    _thinking_phrases = {
        "ru": "🏠 _думаю..._",
        "uk": "🏠 _думаю..._",
        "en": "🏠 _thinking..._",
        "it": "🏠 _sto pensando..._",
    }
    _thinking_text = _thinking_phrases.get(lang, "🏠 _думаю..._")
    _thinking_msg = None
    try:
        _thinking_msg = await ctx.bot.send_message(
            chat_id=update.effective_chat.id,
            text=_thinking_text,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        pass  # Non-critical

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    async def _keep_typing():
        for _ in range(10):
            await asyncio.sleep(8)
            try:
                await ctx.bot.send_chat_action(
                    chat_id=update.effective_chat.id, action="typing"
                )
            except Exception:
                break

    typing_task = asyncio.create_task(_keep_typing())
    try:
        # Log user message before agent call
        try:
            if _db_ready:
                await appdb.log_message(
                    user_id=session.user_id,
                    direction="user",
                    message_type=media_type,
                    raw_text=text,
                    session_id=session.session_id,
                    envelope_id=session.current_envelope_id or "",
                    media_file_id=media_file_id if media_type == "photo" else "",
                )
        except Exception:
            pass  # Conversation logging is not critical
        # Mirror to Google Sheets
        try:
            if conv_logger:
                conv_logger.log_user(
                    user_id=session.user_id,
                    session_id=session.session_id or "",
                    envelope_id=session.current_envelope_id or "",
                    message_type=media_type,
                    raw_text=text,
                )
        except Exception:
            pass

        response = await agent.run(
            text, session,
            media_type=media_type,
            media_data=media_data if media_type == "photo" else None,
            telegram_bot=ctx.bot,
        )

        # Log bot response after agent call
        try:
            if _db_ready:
                await appdb.log_message(
                    user_id=session.user_id,
                    direction="bot",
                    message_type="response",
                    raw_text=response[:2000],
                    session_id=session.session_id,
                    envelope_id=session.current_envelope_id or "",
                )
        except Exception:
            pass  # Conversation logging is not critical
        # Mirror to Google Sheets
        try:
            if conv_logger:
                conv_logger.log_bot(
                    user_id=session.user_id,
                    session_id=session.session_id or "",
                    envelope_id=session.current_envelope_id or "",
                    response_text=response[:300],
                )
        except Exception:
            pass
    finally:
        typing_task.cancel()
        # Remove the thinking indicator
        if _thinking_msg:
            try:
                await ctx.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=_thinking_msg.message_id,
                )
            except Exception:
                pass

    # ── Post-response inline buttons ──────────────────────────────────────
    # Check pending_choice from agent's present_options tool call first
    pending_ch = getattr(session, "pending_choice", None)
    pd = getattr(session, "pending_delete", None)
    la = session.last_action

    if pending_ch:
        session.pending_choice = None  # consume
        choice_rows = [
            [InlineKeyboardButton(c["label"], callback_data=f"cb_choice_{c['value']}")]
            for c in pending_ch
        ]
        kb = _with_menu_btn(*choice_rows, lang=lang)
        await _safe_reply(update.message, response, reply_markup=kb)
    elif pd:
        # Pending hard-delete: show confirm/cancel buttons instead of standard menu
        s, e = pd["start_row"], pd["end_row"]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"✅ Да, удалить строки {s}–{e}",
                callback_data=f"cb_confirm_del_{s}_{e}",
            )],
            [InlineKeyboardButton("❌ Отмена", callback_data="cb_cancel_del")],
        ])
        await _safe_reply(update.message, response, reply_markup=kb)
    elif la and la.action == "add" and "✓" in response:
        tx_id = la.tx_id
        # T-058: Append budget remaining after every expense add
        try:
            from tools.summary import tool_get_budget_status
            budget = await tool_get_budget_status(
                {"envelope_id": session.current_envelope_id},
                session, sheets, auth,
            )
            if budget.get("status") == "ok":
                spent = budget["spent"]
                cap = budget["cap"]
                remaining = budget["remaining"]
                pct = budget["pct_used"]
                _bal_labels = {
                    "ru": "Осталось", "uk": "Залишилось",
                    "en": "Remaining", "it": "Rimanente",
                }
                bal_label = _bal_labels.get(lang, "Remaining")
                response += f"\n📊 {bal_label}: <b>{remaining:.0f}€</b> из {cap:.0f}€ ({pct}%)"
        except Exception:
            pass  # Non-critical — don't break the flow
        kb = _with_menu_btn(
            [InlineKeyboardButton("✏ Изменить", callback_data=f"cb_edit_{tx_id}"),
             InlineKeyboardButton("🗑 Удалить",  callback_data=f"cb_del_{tx_id}")],
            [InlineKeyboardButton("💰 Бюджет",   callback_data="cb_status")],
            lang=lang,
        )
        await _safe_reply(update.message, response, reply_markup=kb)
    else:
        await _safe_reply(update.message, response, reply_markup=_with_menu_btn(lang=lang))


# ── Weekly summary job ─────────────────────────────────────────────────────────

async def weekly_summary_job(context: ContextTypes.DEFAULT_TYPE):
    mikhail_id = int(os.environ.get("MIKHAIL_TELEGRAM_ID", 0))
    if not mikhail_id:
        return
    session = get_session(mikhail_id, "Mikhail", "admin")
    try:
        lang = getattr(session, "lang", "ru")
        html = await _build_week_html(session, lang)
        report_html = await _build_report_html(session, "current", lang)
        full = f"{i18n.tu('weekly_job_title', lang)}\n\n{html}\n\n{report_html}"
        await context.bot.send_message(
            chat_id=mikhail_id,
            text=full,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Weekly summary failed: {e}")


# ── Audio transcription ────────────────────────────────────────────────────────

async def transcribe_audio(audio_bytes: bytes) -> str:
    import openai
    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    transcript = await client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.ogg", audio_bytes, "audio/ogg"),
        language=None,
    )
    text = transcript.text.strip().rstrip(".")
    return re.sub(r"\s+", " ", text)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("menu",         cmd_menu))
    app.add_handler(CommandHandler("settings",     cmd_settings))
    app.add_handler(CommandHandler("envelopes",    cmd_envelopes))
    app.add_handler(CommandHandler("envelope",     cmd_envelope))
    app.add_handler(CommandHandler("status",       cmd_status))
    app.add_handler(CommandHandler("report",       cmd_report))
    app.add_handler(CommandHandler("transactions", cmd_transactions))
    app.add_handler(CommandHandler("week",         cmd_week))
    app.add_handler(CommandHandler("month",        cmd_month))
    app.add_handler(CommandHandler("undo",         cmd_undo))
    app.add_handler(CommandHandler("help",         cmd_help))
    app.add_handler(CommandHandler("refresh",      cmd_refresh))
    app.add_handler(CommandHandler("log",           cmd_log))
    app.add_handler(CommandHandler("stats",        cmd_stats))
    app.add_handler(CommandHandler("admin_support", cmd_admin_support))
    app.add_handler(CommandHandler("idea",         cmd_idea))
    app.add_handler(CommandHandler("goal",         cmd_goal))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND, handle_message
    ))

    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        app.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 8080)),
            webhook_url=webhook_url,
        )
    else:
        app.run_polling()


if __name__ == "__main__":
    main()
