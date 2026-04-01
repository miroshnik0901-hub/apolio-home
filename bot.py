"""Apolio Home — Telegram Bot Entry Point"""
import asyncio
import logging
import os
import re
import datetime as dt
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

from telegram import (
    Update, BotCommand,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
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

# Initialise shared clients
sheets = SheetsClient()
auth = AuthManager(sheets)
agent = ApolioAgent(sheets, auth)

# ── Keyboards ──────────────────────────────────────────────────────────────────

def _build_reply_keyboard() -> ReplyKeyboardMarkup:
    """Build the persistent bottom keyboard from menu config (top-level nodes)."""
    tree = mc.get_menu()
    roots = mc.root_nodes(tree)
    rows = []
    row: list[KeyboardButton] = []
    for nid, node in roots:
        label = node["label"]
        # Submenus get a › suffix so the user knows it opens more options
        if node["type"] == "submenu":
            label = label + " ›"
        row.append(KeyboardButton(label))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def _get_keyboard_shortcuts() -> dict[str, str]:
    """Map button label → node_id for the message handler."""
    tree = mc.get_menu()
    result: dict[str, str] = {}
    for nid, node in tree.items():
        label = node["label"]
        result[label] = nid
        # Also accept the › version (submenus)
        if node["type"] == "submenu":
            result[label + " ›"] = nid
    return result


def _build_submenu_keyboard(parent_id: str, tree: dict) -> InlineKeyboardMarkup:
    """Build an inline keyboard for a submenu node."""
    children = mc.sorted_children(tree, parent_id)
    rows = []
    row: list[InlineKeyboardButton] = []
    for nid, node in children:
        label = node["label"]
        if node["type"] == "submenu":
            label = label + " ›"
        row.append(InlineKeyboardButton(label, callback_data=f"nav:{nid}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    # Add Back button if parent has a parent (not root level)
    parent_node = tree.get(parent_id, {})
    grandparent = parent_node.get("parent", "")
    if grandparent:
        rows.append([InlineKeyboardButton("◀ Назад", callback_data=f"nav:{grandparent}")])
    return InlineKeyboardMarkup(rows)


MAIN_KEYBOARD = _build_reply_keyboard()

# Legacy map kept for compatibility; rebuilt on /refresh
KEYBOARD_SHORTCUTS = _get_keyboard_shortcuts()

GREETINGS = {
    "привет", "hi", "hello", "ciao", "hey", "добрий день",
    "як справи", "как дела", "что умеешь", "help", "start", "хелп",
    "buongiorno", "salve", "allo",
}

# ── Bot command definitions ────────────────────────────────────────────────────

BOT_COMMANDS = [
    BotCommand("start",        "Начать / приветствие"),
    BotCommand("menu",         "Меню функций"),
    BotCommand("envelopes",    "Список конвертов со ссылками"),
    BotCommand("envelope",     "Выбрать активный конверт"),
    BotCommand("status",       "Статус бюджета за текущий месяц"),
    BotCommand("report",       "Отчёт по категориям за месяц"),
    BotCommand("transactions", "Последние записи с кнопками"),
    BotCommand("week",         "Расходы за эту неделю"),
    BotCommand("month",        "Расходы за этот месяц"),
    BotCommand("undo",         "Отменить последнее действие"),
    BotCommand("help",         "Справка и примеры"),
    BotCommand("refresh",      "Обновить меню из Admin-таблицы"),
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


def _month_name_ru(period: str) -> str:
    """Convert YYYY-MM to 'апреле 2026'."""
    try:
        y, m = period.split("-")
        return f"{MONTH_NAMES_RU.get(m, m)} {y}"
    except Exception:
        return period


def _month_label_ru(period: str) -> str:
    """Convert YYYY-MM to 'Апрель 2026'."""
    try:
        y, m = period.split("-")
        return f"{MONTH_LABELS_RU.get(m, m)} {y}"
    except Exception:
        return period


def _progress_bar(current: float, total: float, width: int = 10) -> str:
    """Emoji block progress bar."""
    if not total or total <= 0:
        return "░" * width
    pct = min(current / total, 1.0)
    filled = round(pct * width)
    return "█" * filled + "░" * (width - filled)


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

async def _build_status_html(session) -> str:
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

        label = _month_label_ru(month)
        env_id = session.current_envelope_id or "?"
        bar = _progress_bar(spent, cap)
        warn = " ⚠️" if alert else ("  ✅" if 0 < pct < 80 else ("  🔴" if pct >= 100 else ""))

        lines = [
            f"📊 <b>Бюджет {label}</b>  ·  {env_id}",
            "",
            f"<b>{spent:,.0f}</b> / {cap:,.0f} EUR  ({pct:.0f}%){warn}",
            f"<code>{bar}</code>",
            f"Осталось: <b>{remaining:,.0f} EUR</b>",
        ]

        if summary.get("status") == "ok":
            cats = summary.get("categories", {})
            by_who = summary.get("by_who", {})

            if cats:
                lines.append("")
                lines.append("<b>По категориям:</b>")
                for cat, amt in sorted(cats.items(), key=lambda x: -x[1])[:10]:
                    icon = _cat_icon(cat)
                    lines.append(f"  {icon} {cat}: {amt:,.0f} EUR")

            if len(by_who) > 1:
                lines.append("")
                lines.append("<b>По кому:</b>")
                for who, amt in sorted(by_who.items(), key=lambda x: -x[1]):
                    lines.append(f"  👤 {who}: {amt:,.0f} EUR")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"_build_status_html failed: {e}", exc_info=True)
        return f"❌ Не удалось загрузить статус: {e}"


async def _build_report_html(session, period: str = "current") -> str:
    """Render monthly report as HTML without going through the agent."""
    try:
        from tools.summary import tool_get_summary
        summary = await tool_get_summary(
            {"breakdown_by": "category", "period": period},
            session, sheets, auth
        )
        if summary.get("error"):
            return f"❌ {summary['error']}"

        total = float(summary.get("total_spent") or 0)
        period_str = summary.get("period", period)
        label = _month_label_ru(period_str)
        cats = summary.get("categories", {})
        by_who = summary.get("by_who", {})

        lines = [
            f"📋 <b>Отчёт за {label}</b>",
            "",
            f"Итого расходов: <b>{total:,.0f} EUR</b>",
        ]

        if cats:
            lines.append("")
            lines.append("<b>Расходы по категориям:</b>")
            for cat, amt in sorted(cats.items(), key=lambda x: -x[1]):
                pct = round(amt / total * 100) if total else 0
                icon = _cat_icon(cat)
                bar = _progress_bar(amt, total, width=6)
                lines.append(
                    f"  {icon} <b>{cat}</b>: {amt:,.0f} EUR  ({pct}%)\n"
                    f"     <code>{bar}</code>"
                )

        if len(by_who) > 1:
            lines.append("")
            lines.append("<b>По кому:</b>")
            for who, amt in sorted(by_who.items(), key=lambda x: -x[1]):
                pct = round(amt / total * 100) if total else 0
                lines.append(f"  👤 {who}: {amt:,.0f} EUR  ({pct}%)")

        if not cats and not by_who:
            lines.append("\nЗаписей за этот период нет.")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"_build_report_html failed: {e}", exc_info=True)
        return f"❌ Не удалось загрузить отчёт: {e}"


async def _build_week_html(session) -> str:
    """Render this-week expenses as HTML."""
    try:
        from tools.transactions import tool_find_transactions
        today = dt.date.today()
        # Monday of current week
        monday = today - dt.timedelta(days=today.weekday())
        result = await tool_find_transactions(
            {"date_from": monday.isoformat(), "date_to": today.isoformat(), "limit": 50},
            session, sheets, auth
        )
        if result.get("error"):
            return f"❌ {result['error']}"

        txs = [r for r in result.get("transactions", []) if r.get("Type") == "expense"]
        if not txs:
            return "За эту неделю расходов ещё нет."

        total = sum(float(r.get("Amount_EUR") or r.get("Amount_Orig") or 0) for r in txs)
        cats: dict = {}
        for r in txs:
            cat = r.get("Category", "Other")
            cats[cat] = cats.get(cat, 0) + float(r.get("Amount_EUR") or r.get("Amount_Orig") or 0)

        week_label = f"{monday.strftime('%d.%m')} — {today.strftime('%d.%m')}"
        lines = [
            f"📅 <b>Эта неделя</b>  ({week_label})",
            "",
            f"Итого: <b>{total:,.0f} EUR</b>  ({len(txs)} {_ru_plural(len(txs), 'запись', 'записи', 'записей')})",
        ]
        if cats:
            lines.append("")
            lines.append("<b>По категориям:</b>")
            for cat, amt in sorted(cats.items(), key=lambda x: -x[1]):
                icon = _cat_icon(cat)
                lines.append(f"  {icon} {cat}: {amt:,.0f} EUR")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"_build_week_html failed: {e}", exc_info=True)
        return f"❌ Ошибка: {e}"


# ── Post init ──────────────────────────────────────────────────────────────────

async def post_init(app: Application):
    """Register bot commands, ensure BotMenu sheet exists, schedule weekly summary."""
    await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Bot commands registered in Telegram")

    # Ensure BotMenu tab exists in Admin sheet (creates with defaults if absent)
    try:
        admin_id = os.environ.get("ADMIN_SHEETS_ID", "")
        created = mc.ensure_sheet(sheets._gc, admin_id)
        if created:
            logger.info("BotMenu sheet created in Admin spreadsheet with defaults")
        # Pre-load menu into cache
        mc.get_menu(sheets._gc, admin_id)
    except Exception as e:
        logger.warning(f"Could not init BotMenu sheet: {e}")

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


# ── Auth helper ────────────────────────────────────────────────────────────────

def _require_user(update: Update):
    user = update.effective_user
    tg_user = auth.get_user(user.id)
    if not tg_user:
        return None, None
    session = get_session(user.id, user.first_name, tg_user["role"])
    return tg_user, session


# ── Menu navigation helper ─────────────────────────────────────────────────────

async def _handle_menu_node(node_id: str, update: Update, ctx) -> bool:
    """Handle a menu node tap. Returns True if the message was fully handled."""
    tree = mc.get_menu()
    node = tree.get(node_id)
    if not node:
        return False

    ntype = node.get("type", "cmd")

    if ntype == "submenu":
        # Show inline keyboard with children
        kb = _build_submenu_keyboard(node_id, tree)
        label = node["label"].replace(" ›", "")
        await update.message.reply_text(
            f"{label}:",
            reply_markup=kb,
        )
        return True

    if ntype == "free_text":
        await update.message.reply_text(
            "Напишите расход в свободной форме:\n"
            "Например: «кофе 3.50» или «продукты 85 EUR Esselunga»",
            reply_markup=_build_reply_keyboard(),
        )
        return True

    if ntype == "cmd":
        command = node.get("command", "")
        params  = node.get("params", {})
        # Dispatch to the right handler based on command name + params
        if command == "status":
            await cmd_status(update, ctx)
        elif command == "report":
            period = params.get("period", "current")
            tg_user, session = _require_user(update)
            if tg_user:
                await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                html = await _build_report_html(session, period)
                nav_kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀ Пред. месяц", callback_data="nav:rep_last"),
                    InlineKeyboardButton("▶ Тек. месяц",  callback_data="nav:rep_curr"),
                ]])
                await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=nav_kb)
        elif command == "transactions":
            await cmd_transactions(update, ctx)
        elif command == "week":
            await cmd_week(update, ctx)
        elif command == "help":
            await cmd_help(update, ctx)
        elif command == "envelopes":
            await cmd_envelopes(update, ctx)
        else:
            return False
        return True

    return False
    user = update.effective_user
    tg_user = auth.get_user(user.id)
    if not tg_user:
        return None, None
    session = get_session(user.id, user.first_name, tg_user["role"])
    return tg_user, session


# ── /start ─────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    name = session.user_name or "Mikhail"
    kb = _build_reply_keyboard()
    await update.message.reply_text(
        f"👋 Привет, {name}!\n\n"
        "Я <b>Apolio Home</b> — ваш ИИ-помощник для семейного бюджета.\n\n"
        "Просто напишите мне:\n"
        "• <i>«кофе 3.50»</i> — запишу расход\n"
        "• <i>«продукты 85 EUR Esselunga»</i> — с заметкой\n"
        "• <i>«покажи отчёт за март»</i> — статистика\n\n"
        "Или используйте кнопки меню ниже 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


async def cmd_refresh(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Reload menu config from Admin sheet."""
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return
    mc.invalidate()
    admin_id = os.environ.get("ADMIN_SHEETS_ID", "")
    mc.get_menu(sheets._gc, admin_id)  # pre-warm cache from sheet
    global MAIN_KEYBOARD, KEYBOARD_SHORTCUTS
    MAIN_KEYBOARD = _build_reply_keyboard()
    KEYBOARD_SHORTCUTS = _get_keyboard_shortcuts()
    await update.message.reply_text(
        "🔄 Меню обновлено из Admin-таблицы.",
        reply_markup=MAIN_KEYBOARD,
    )


# ── /menu ──────────────────────────────────────────────────────────────────────

async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    active_env = session.current_envelope_id or "не выбран"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Конверты", callback_data="cb_envelopes"),
         InlineKeyboardButton("📊 Статус", callback_data="cb_status")],
        [InlineKeyboardButton("📋 Отчёт", callback_data="cb_report"),
         InlineKeyboardButton("📝 Записи", callback_data="cb_transactions")],
        [InlineKeyboardButton("❓ Справка", callback_data="cb_help")],
    ])
    await update.message.reply_text(
        f"🏠 <b>Apolio Home — Меню</b>\n\n"
        f"Активный конверт: <code>{active_env}</code>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


# ── /envelopes ─────────────────────────────────────────────────────────────────

async def cmd_envelopes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    try:
        envelopes = sheets.list_envelopes_with_links()
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при загрузке конвертов: {e}")
        return

    if not envelopes:
        await update.message.reply_text(
            "Конверты ещё не созданы.\n\nНапишите: «создай конверт Название, лимит N EUR»"
        )
        return

    lines = ["📁 <b>Список конвертов:</b>\n"]
    for e in envelopes:
        cap = f"{e['monthly_cap']:,} {e['currency']}" if e['monthly_cap'] else "без лимита"
        rule = e.get("split_rule", "solo")
        url = e.get("url", "")
        link = f'  <a href="{url}">открыть таблицу</a>' if url else ""
        active_mark = " ✅" if e["id"] == session.current_envelope_id else ""
        lines.append(
            f"▸ <b>{e['name']}</b> (<code>{e['id']}</code>){active_mark}\n"
            f"  Лимит: {cap} · Правило: {rule}{link}"
        )

    keyboard = []
    row = []
    for i, e in enumerate(envelopes):
        row.append(InlineKeyboardButton(e["name"], callback_data=f"cb_env_{e['id']}"))
        if len(row) == 2 or i == len(envelopes) - 1:
            keyboard.append(row)
            row = []

    await update.message.reply_text(
        "\n\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        disable_web_page_preview=True,
    )


# ── /envelope ──────────────────────────────────────────────────────────────────

async def cmd_envelope(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    if not ctx.args:
        envelopes = sheets.get_envelopes()
        active = [e for e in envelopes if str(e.get("Active", "TRUE")).upper() != "FALSE"]
        if not active:
            await update.message.reply_text("Конвертов нет. Создайте первый.")
            return

        lines = ["Доступные конверты:\n"]
        keyboard = []
        row = []
        for i, e in enumerate(active):
            eid = e.get("ID", "")
            ename = e.get("Name", eid)
            lines.append(f"• <code>{eid}</code> — {ename}")
            row.append(InlineKeyboardButton(ename, callback_data=f"cb_env_{eid}"))
            if len(row) == 2 or i == len(active) - 1:
                keyboard.append(row)
                row = []

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
    await update.message.reply_text(
        f"✅ Активный конверт: <b>{match['Name']}</b> (<code>{env_id}</code>)",
        parse_mode=ParseMode.HTML,
    )


# ── /status ────────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    html = await _build_status_html(session)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Отчёт", callback_data="cb_report"),
        InlineKeyboardButton("📝 Записи", callback_data="cb_transactions"),
    ]])
    await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ── /report ────────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

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

    html = await _build_report_html(session, period)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("◀ Пред. месяц", callback_data="cb_report_last"),
        InlineKeyboardButton("▶ Тек. месяц", callback_data="cb_report"),
    ]])
    await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ── /week ──────────────────────────────────────────────────────────────────────

async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    html = await _build_week_html(session)
    await update.message.reply_text(html, parse_mode=ParseMode.HTML)


# ── /month ─────────────────────────────────────────────────────────────────────

async def cmd_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

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

    html = await _build_report_html(session, period)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("◀ Пред. месяц", callback_data="cb_report_last"),
        InlineKeyboardButton("▶ Тек. месяц", callback_data="cb_report"),
    ]])
    await update.message.reply_text(html, parse_mode=ParseMode.HTML, reply_markup=keyboard)


# ── /transactions ──────────────────────────────────────────────────────────────

async def cmd_transactions(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

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
                "📝 Записей пока нет.\n\nПросто напишите что потратили, например: «кофе 3.50»"
            )
            return

        lines = ["📝 <b>Последние записи:</b>\n"]
        # Show newest first
        for tx in reversed(txs):
            date = tx.get("Date", "")
            cat = tx.get("Category", "?")
            amt = tx.get("Amount_Orig", tx.get("Amount_EUR", "?"))
            curr = tx.get("Currency_Orig", "EUR")
            amt_eur = tx.get("Amount_EUR", "")
            who = tx.get("Who", "")
            note = tx.get("Note", "")
            tx_id = tx.get("ID", "")
            icon = _cat_icon(cat)

            # Amount display: show original + EUR if different currency
            if curr != "EUR" and amt_eur:
                amt_str = f"{amt} {curr} ({amt_eur} EUR)"
            else:
                amt_str = f"{amt} EUR"

            who_str = f" · {who}" if who and who not in ("Mikhail", "") else ""
            note_str = f"\n     📎 {note}" if note else ""
            lines.append(
                f"{icon} <b>{cat}</b>  {amt_str}{who_str}  <i>{date}</i>"
                f"{note_str}"
            )
            lines.append("")

        # Inline delete buttons for last 5 transactions
        keyboard = []
        row = []
        recent = list(reversed(txs))[:5]
        for i, tx in enumerate(recent):
            tx_id = tx.get("ID", "")
            cat = tx.get("Category", "?")[:7]
            amt = tx.get("Amount_Orig", "?")
            row.append(InlineKeyboardButton(
                f"🗑 {cat} {amt}", callback_data=f"cb_del_{tx_id}"
            ))
            if len(row) == 2 or i == len(recent) - 1:
                keyboard.append(row)
                row = []

        markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await update.message.reply_text(
            "\n".join(lines),
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
        await update.message.reply_text("⛔ Access denied.")
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
    tg_user, _ = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

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
        "› создай конверт «Отпуск» лимит 2000 EUR\n\n"
        "<b>Исправления:</b>\n"
        "› не 45 а 54 / actually 90\n"
        "› это было вчера\n"
        "› /undo — отменить последнее\n\n"
        "<b>Команды:</b>\n"
        "/status · /report · /transactions\n"
        "/week · /month · /envelopes · /undo\n\n"
        "<i>Голос и фото чеков тоже работают 🎤📸</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_KEYBOARD,
    )


# ── Inline keyboard callbacks ──────────────────────────────────────────────────

async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tg_user = auth.get_user(query.from_user.id)
    if not tg_user:
        await query.edit_message_text("⛔ Access denied.")
        return

    session = get_session(query.from_user.id, query.from_user.first_name, tg_user["role"])
    data = query.data

    # ── nav: dynamic menu navigation ───────────────────────────────────────
    if data.startswith("nav:"):
        node_id = data[4:]
        tree = mc.get_menu()
        node = tree.get(node_id)
        if not node:
            await query.answer("Пункт меню не найден", show_alert=True)
            return

        ntype = node.get("type", "cmd")

        if ntype == "submenu":
            kb = _build_submenu_keyboard(node_id, tree)
            label = node["label"].replace(" ›", "")
            try:
                await query.edit_message_text(f"{label}:", reply_markup=kb)
            except BadRequest:
                pass
            return

        if ntype == "cmd":
            command = node.get("command", "")
            params  = node.get("params", {})
            if command == "status":
                html = await _build_status_html(session)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("📋 Отчёт", callback_data="nav:report"),
                    InlineKeyboardButton("📝 Записи", callback_data="nav:transactions"),
                ]])
            elif command == "report":
                period = params.get("period", "current")
                html = await _build_report_html(session, period)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀ Пред. месяц", callback_data="nav:rep_last"),
                    InlineKeyboardButton("▶ Тек. месяц",  callback_data="nav:rep_curr"),
                ]])
            elif command == "week":
                html = await _build_week_html(session)
                kb = None
            else:
                await query.answer("Команда не поддерживается в инлайн-режиме", show_alert=True)
                return
            try:
                await query.edit_message_text(
                    html, parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            except BadRequest:
                pass
            return

    # ── cb_envelopes ───────────────────────────────────────────────────────
    if data == "cb_envelopes":
        try:
            envelopes = sheets.list_envelopes_with_links()
        except Exception as e:
            await query.edit_message_text(f"❌ {e}")
            return
        if not envelopes:
            await query.edit_message_text("Конвертов нет.")
            return
        lines = ["📁 <b>Список конвертов:</b>\n"]
        for e in envelopes:
            cap = f"{e['monthly_cap']:,} {e['currency']}" if e['monthly_cap'] else "без лимита"
            url = e.get("url", "")
            link = f'  <a href="{url}">открыть</a>' if url else ""
            active_mark = " ✅" if e["id"] == session.current_envelope_id else ""
            lines.append(f"▸ <b>{e['name']}</b> (<code>{e['id']}</code>){active_mark} · {cap}{link}")
        keyboard = []
        row = []
        for i, e in enumerate(envelopes):
            row.append(InlineKeyboardButton(e["name"], callback_data=f"cb_env_{e['id']}"))
            if len(row) == 2 or i == len(envelopes) - 1:
                keyboard.append(row)
                row = []
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
        html = await _build_status_html(session)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Отчёт", callback_data="cb_report"),
            InlineKeyboardButton("📝 Записи", callback_data="cb_transactions"),
        ]])
        try:
            await query.edit_message_text(
                html, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
        except BadRequest:
            pass

    # ── cb_report ──────────────────────────────────────────────────────────
    elif data == "cb_report":
        html = await _build_report_html(session, "current")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ Пред. месяц", callback_data="cb_report_last"),
            InlineKeyboardButton("▶ Тек. месяц", callback_data="cb_report"),
        ]])
        try:
            await query.edit_message_text(
                html, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
        except BadRequest:
            pass

    elif data == "cb_report_last":
        html = await _build_report_html(session, "last")
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("◀ Пред. месяц", callback_data="cb_report_last"),
            InlineKeyboardButton("▶ Тек. месяц", callback_data="cb_report"),
        ]])
        try:
            await query.edit_message_text(
                html, parse_mode=ParseMode.HTML, reply_markup=keyboard
            )
        except BadRequest:
            pass

    # ── cb_transactions ────────────────────────────────────────────────────
    elif data == "cb_transactions":
        try:
            from tools.transactions import tool_find_transactions
            result = await tool_find_transactions({"limit": 8}, session, sheets, auth)
            txs = result.get("transactions", [])
            if not txs:
                await query.edit_message_text("Записей пока нет.")
                return
            lines = ["📝 <b>Последние записи:</b>\n"]
            for tx in reversed(txs):
                date = tx.get("Date", "")
                cat = tx.get("Category", "?")
                amt = tx.get("Amount_Orig", tx.get("Amount_EUR", "?"))
                curr = tx.get("Currency_Orig", "EUR")
                note = tx.get("Note", "")
                tx_id = tx.get("ID", "")
                icon = _cat_icon(cat)
                note_str = f" · {note}" if note else ""
                lines.append(
                    f"{icon} <b>{cat}</b>  {amt} {curr}  <i>{date}</i>{note_str}"
                )
                lines.append("")
            keyboard = []
            row = []
            recent = list(reversed(txs))[:4]
            for i, tx in enumerate(recent):
                tx_id = tx.get("ID", "")
                cat = tx.get("Category", "?")[:7]
                row.append(InlineKeyboardButton(
                    f"🗑 {cat}", callback_data=f"cb_del_{tx_id}"
                ))
                if len(row) == 2 or i == len(recent) - 1:
                    keyboard.append(row)
                    row = []
            markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await query.edit_message_text(
                "\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
        except Exception as e:
            await query.edit_message_text(f"❌ {e}")

    # ── cb_help ────────────────────────────────────────────────────────────
    elif data == "cb_help":
        try:
            await query.edit_message_text(
                "📖 <b>Справка</b>\n\n"
                "Просто пишите естественным языком:\n"
                "› «кофе 3.50» или «продукты 85 EUR»\n"
                "› «покажи отчёт за март»\n"
                "› «создай конверт Отпуск лимит 2000 EUR»\n\n"
                "<b>Команды:</b> /menu /envelopes /status /report /transactions /week /undo /help",
                parse_mode=ParseMode.HTML,
            )
        except BadRequest:
            pass

    # ── cb_env_<ID> ────────────────────────────────────────────────────────
    elif data.startswith("cb_env_"):
        env_id = data[7:]
        envelopes = sheets.get_envelopes()
        match = next((e for e in envelopes if e.get("ID") == env_id), None)
        if not match:
            await query.edit_message_text(
                f"❌ Конверт <code>{env_id}</code> не найден.", parse_mode=ParseMode.HTML
            )
            return
        session.current_envelope_id = env_id
        try:
            await query.edit_message_text(
                f"✅ Активный конверт: <b>{match['Name']}</b> (<code>{env_id}</code>)\n\n"
                "Теперь пишите расходы прямо в чат!",
                parse_mode=ParseMode.HTML,
            )
        except BadRequest:
            pass

    # ── cb_del_confirm_<tx_id> ─────────────────────────────────────────────
    elif data.startswith("cb_del_confirm_"):
        tx_id = data[15:]
        try:
            envelopes = sheets.get_envelopes()
            for e in envelopes:
                if e.get("ID") == session.current_envelope_id:
                    sheets.soft_delete_transaction(e["file_id"], tx_id)
                    break
            await query.edit_message_text(f"🗑 Удалено (<code>{tx_id}</code>)", parse_mode=ParseMode.HTML)
            session.last_action = None
        except Exception as ex:
            await query.edit_message_text(f"❌ Ошибка: {ex}")

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
        await update.message.reply_text("⛔ Access denied.")
        return

    msg = update.message
    text = ""
    media_type = "text"
    media_data = None

    if msg.text:
        text = msg.text.strip()

        # ── Keyboard shortcut intercept (dynamic menu) ────────────────────
        node_id = KEYBOARD_SHORTCUTS.get(text)
        if node_id:
            handled = await _handle_menu_node(node_id, update, ctx)
            if handled:
                return

        # ── Greeting intercept ─────────────────────────────────────────────
        if text.lower() in GREETINGS:
            await update.message.reply_text(
                "Привет! 👋\n\n"
                "Просто напишите что потратили:\n"
                "«кофе 3.50» или «продукты 85 EUR»\n\n"
                "Или нажмите кнопку ниже 👇",
                reply_markup=MAIN_KEYBOARD,
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
        text = msg.caption or ""
        media_type = "photo"

    elif msg.document and msg.document.mime_type in ("text/csv", "application/csv"):
        file_obj = await msg.document.get_file()
        csv_bytes = await file_obj.download_as_bytearray()
        text = f"[CSV import]\n{csv_bytes.decode('utf-8', errors='replace')}"

    else:
        await update.message.reply_text("Не поддерживаемый тип сообщения.")
        return

    # ── Inject pending edit context ────────────────────────────────────────
    pending_tx = getattr(session, "pending_edit_tx", None)
    if pending_tx:
        session.pending_edit_tx = None
        text = f"[edit tx_id={pending_tx}] {text}"

    # ── Typing indicator ───────────────────────────────────────────────────
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
        response = await agent.run(
            text, session,
            media_type=media_type,
            media_data=media_data if media_type == "photo" else None,
        )
    finally:
        typing_task.cancel()

    # ── Post-transaction inline buttons ───────────────────────────────────
    la = session.last_action
    if la and la.action == "add" and "✓" in response:
        tx_id = la.tx_id
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✏ Изменить", callback_data=f"cb_edit_{tx_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"cb_del_{tx_id}"),
            InlineKeyboardButton("📊 Статус", callback_data="cb_status"),
        ]])
        await _safe_reply(update.message, response, reply_markup=keyboard)
    else:
        await _safe_reply(update.message, response)


# ── Weekly summary job ─────────────────────────────────────────────────────────

async def weekly_summary_job(context: ContextTypes.DEFAULT_TYPE):
    mikhail_id = int(os.environ.get("MIKHAIL_TELEGRAM_ID", 0))
    if not mikhail_id:
        return
    session = get_session(mikhail_id, "Mikhail", "admin")
    try:
        html = await _build_week_html(session)
        report_html = await _build_report_html(session, "current")
        full = f"📅 <b>Еженедельный отчёт</b>\n\n{html}\n\n{report_html}"
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
