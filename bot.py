"""Apolio Home — Telegram Bot Entry Point"""
import asyncio
import logging
import os
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

from sheets import SheetsClient
from auth import AuthManager, get_session
from agent import ApolioAgent

# Initialise shared clients
sheets = SheetsClient()
auth = AuthManager(sheets)
agent = ApolioAgent(sheets, auth)

# ── Keyboards ──────────────────────────────────────────────────────────────────

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📊 Статус"), KeyboardButton("📋 Отчёт")],
        [KeyboardButton("💰 Добавить расход"), KeyboardButton("📁 Конверты")],
        [KeyboardButton("❓ Помощь")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

KEYBOARD_SHORTCUTS = {
    "📊 Статус":          "status",
    "📋 Отчёт":           "report",
    "📁 Конверты":        "envelopes",
    "💰 Добавить расход": "add_prompt",
    "❓ Помощь":          "help",
}

GREETINGS = {
    "привет", "hi", "hello", "ciao", "hey", "добрий день",
    "як справи", "как дела", "что умеешь", "help", "start", "хелп",
    "buongiorno", "salve", "allo",
}

# ── Bot command definitions ────────────────────────────────────────────────────

BOT_COMMANDS = [
    BotCommand("start",     "Начать / приветствие"),
    BotCommand("menu",      "Меню функций"),
    BotCommand("envelopes", "Список конвертов со ссылками"),
    BotCommand("envelope",  "Выбрать активный конверт"),
    BotCommand("status",    "Статус бюджета за текущий месяц"),
    BotCommand("report",    "Отчёт по категориям за месяц"),
    BotCommand("week",      "Расходы за эту неделю"),
    BotCommand("month",     "Расходы за этот месяц"),
    BotCommand("undo",      "Отменить последнее действие"),
    BotCommand("help",      "Справка и примеры"),
]


async def post_init(app: Application):
    """Register bot commands and schedule weekly summary."""
    await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Bot commands registered in Telegram")

    # Schedule weekly summary every Monday at 09:00 Rome time
    try:
        import pytz
        rome_tz = pytz.timezone("Europe/Rome")
        app.job_queue.run_daily(
            weekly_summary_job,
            time=dt.time(9, 0, tzinfo=rome_tz),
            days=(0,),  # Monday = 0
            name="weekly_summary",
        )
        logger.info("Weekly summary job scheduled: Monday 09:00 Rome")
    except Exception as e:
        logger.warning(f"Could not schedule weekly summary: {e}")


# ── Auth helper ────────────────────────────────────────────────────────────────

def _require_user(update: Update):
    """Return (tg_user, session) or (None, None) if access denied."""
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

    keyboard = [
        [InlineKeyboardButton("📁 Конверты", callback_data="cb_envelopes"),
         InlineKeyboardButton("📊 Статус бюджета", callback_data="cb_status")],
        [InlineKeyboardButton("📋 Отчёт за месяц", callback_data="cb_report"),
         InlineKeyboardButton("❓ Справка", callback_data="cb_help")],
    ]
    name = session.user_name or "Mikhail"
    await update.message.reply_text(
        f"👋 Привет, {name}!\n\n"
        "Я *Apolio Home* — ваш ИИ-помощник для семейного бюджета.\n\n"
        "Просто напишите мне:\n"
        "• «кофе 3.50» — запишу расход\n"
        "• «продукты 85 EUR Esselunga» — с заметкой\n"
        "• «покажи отчёт за март» — статистика\n\n"
        "Или нажмите кнопку ниже 👇",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=MAIN_KEYBOARD,
    )


# ── /menu ──────────────────────────────────────────────────────────────────────

async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    active_env = session.current_envelope_id or "не выбран"
    keyboard = [
        [InlineKeyboardButton("📁 Конверты", callback_data="cb_envelopes"),
         InlineKeyboardButton("📊 Статус", callback_data="cb_status")],
        [InlineKeyboardButton("📋 Отчёт", callback_data="cb_report"),
         InlineKeyboardButton("❓ Справка", callback_data="cb_help")],
    ]
    await update.message.reply_text(
        f"🏠 *Apolio Home — Меню*\n\n"
        f"Активный конверт: `{active_env}`\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard),
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

    lines = ["📁 *Список конвертов:*\n"]
    for e in envelopes:
        cap = f"{e['monthly_cap']} {e['currency']}" if e['monthly_cap'] else "без лимита"
        rule = e.get("split_rule", "solo")
        url = e.get("url", "")
        link = f"[открыть таблицу]({url})" if url else "нет ссылки"
        lines.append(
            f"▸ *{e['name']}* (`{e['id']}`)\n"
            f"  Лимит: {cap} · Правило: {rule}\n"
            f"  {link}"
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
        parse_mode=ParseMode.MARKDOWN,
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
            lines.append(f"• `{eid}` — {ename}")
            row.append(InlineKeyboardButton(ename, callback_data=f"cb_env_{eid}"))
            if len(row) == 2 or i == len(active) - 1:
                keyboard.append(row)
                row = []

        await update.message.reply_text(
            "Использование: `/envelope <ID>`\n\n" + "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    env_id = ctx.args[0].upper()
    envelopes = sheets.get_envelopes()
    match = next((e for e in envelopes if e.get("ID") == env_id), None)
    if not match:
        await update.message.reply_text(f"❌ Конверт `{env_id}` не найден.",
                                         parse_mode=ParseMode.MARKDOWN)
        return

    session.current_envelope_id = env_id
    await update.message.reply_text(
        f"✅ Активный конверт: *{match['Name']}* (`{env_id}`)",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /status ────────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = await agent.run(
        f"покажи статус бюджета для конверта {session.current_envelope_id}", session
    )
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


# ── /report ────────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = await agent.run(
        f"покажи отчёт по категориям за текущий месяц для конверта {session.current_envelope_id}",
        session,
    )
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


# ── /week ──────────────────────────────────────────────────────────────────────

async def cmd_week(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = await agent.run(
        f"покажи расходы за эту неделю для конверта {session.current_envelope_id}", session
    )
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


# ── /month ─────────────────────────────────────────────────────────────────────

async def cmd_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    response = await agent.run(
        f"покажи полный отчёт по категориям за текущий месяц для конверта {session.current_envelope_id}",
        session,
    )
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


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
            sheets.soft_delete_transaction(
                next(e["file_id"] for e in sheets.get_envelopes() if e.get("ID") == la.envelope_id),
                la.tx_id,
            )
            snap = la.snapshot
            await update.message.reply_text(
                f"↩ Отменено: {snap.get('category', '')} · "
                f"{snap.get('amount', '')} {snap.get('currency', 'EUR')} · "
                f"{snap.get('date', '')}"
            )
        elif la.action == "edit":
            await update.message.reply_text(
                f"↩ Отмена изменения поля `{la.snapshot.get('field')}` не реализована. "
                f"Напишите, что нужно исправить.",
                parse_mode=ParseMode.MARKDOWN,
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
        "📖 *Apolio Home — Справка*\n\n"
        "*Записать расход:*\n"
        "› кофе 3.50\n"
        "› продукты 85 EUR Esselunga\n"
        "› Marina купила одежду 120\n"
        "› oggi ho speso 45 euro\n\n"
        "*Доходы и переводы:*\n"
        "› получил зарплату 3000 EUR\n"
        "› перевёл 500 на сбережения\n\n"
        "*Отчёты:*\n"
        "› покажи отчёт за март\n"
        "› сколько потратили на еду\n"
        "› статус бюджета / сколько осталось?\n"
        "› покажи последние 5 записей\n\n"
        "*Конверты:*\n"
        "› /envelopes — список с ссылками\n"
        "› /envelope MM\\_BUDGET — выбрать\n"
        "› создай конверт «Отпуск» лимит 2000 EUR\n\n"
        "*Исправления:*\n"
        "› не 45 а 54 / actually 90\n"
        "› это было вчера\n"
        "› /undo — отменить последнее\n\n"
        "*Голос и фото чеков тоже работают* 🎤📸",
        parse_mode=ParseMode.MARKDOWN,
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

    if data == "cb_envelopes":
        envelopes = sheets.list_envelopes_with_links()
        if not envelopes:
            await query.edit_message_text("Конвертов нет.")
            return
        lines = ["📁 *Список конвертов:*\n"]
        for e in envelopes:
            cap = f"{e['monthly_cap']} {e['currency']}" if e['monthly_cap'] else "без лимита"
            url = e.get("url", "")
            link = f"[открыть]({url})" if url else ""
            lines.append(f"▸ *{e['name']}* (`{e['id']}`) · {cap}  {link}")
        keyboard = []
        row = []
        for i, e in enumerate(envelopes):
            row.append(InlineKeyboardButton(e["name"], callback_data=f"cb_env_{e['id']}"))
            if len(row) == 2 or i == len(envelopes) - 1:
                keyboard.append(row)
                row = []
        await query.edit_message_text(
            "\n\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )

    elif data == "cb_status":
        response = await agent.run(
            f"покажи статус бюджета для конверта {session.current_envelope_id}", session
        )
        await query.edit_message_text(response, parse_mode=ParseMode.MARKDOWN)

    elif data == "cb_report":
        response = await agent.run(
            f"покажи отчёт по категориям за текущий месяц для конверта {session.current_envelope_id}",
            session,
        )
        await query.edit_message_text(response, parse_mode=ParseMode.MARKDOWN)

    elif data == "cb_help":
        await query.edit_message_text(
            "📖 *Справка*\n\n"
            "Просто пишите естественным языком:\n"
            "› «кофе 3.50» или «продукты 85 EUR»\n"
            "› «покажи отчёт за март»\n"
            "› «создай конверт Отпуск лимит 2000 EUR»\n\n"
            "Команды: /menu /envelopes /status /report /week /undo /help",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data.startswith("cb_env_"):
        env_id = data[7:]
        envelopes = sheets.get_envelopes()
        match = next((e for e in envelopes if e.get("ID") == env_id), None)
        if not match:
            await query.edit_message_text(f"❌ Конверт `{env_id}` не найден.",
                                           parse_mode=ParseMode.MARKDOWN)
            return
        session.current_envelope_id = env_id
        await query.edit_message_text(
            f"✅ Активный конверт: *{match['Name']}* (`{env_id}`)\n\n"
            "Теперь пишите расходы прямо в чат!",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data.startswith("cb_del_confirm_"):
        tx_id = data[15:]
        try:
            envelopes = sheets.get_envelopes()
            for e in envelopes:
                if e.get("ID") == session.current_envelope_id:
                    sheets.soft_delete_transaction(e["file_id"], tx_id)
                    break
            await query.edit_message_text(f"🗑 Удалено ({tx_id})")
            session.last_action = None
        except Exception as ex:
            await query.edit_message_text(f"❌ Ошибка: {ex}")

    elif data.startswith("cb_del_"):
        tx_id = data[7:]
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"cb_del_confirm_{tx_id}"),
                InlineKeyboardButton("❌ Отмена", callback_data="cb_cancel"),
            ]])
        )

    elif data.startswith("cb_edit_"):
        tx_id = data[8:]
        session.pending_edit_tx = tx_id
        await query.edit_message_text(
            f"Что изменить в записи `{tx_id}`?\n\n"
            "Напишите например:\n"
            "«сумма 90» или «категория транспорт» или «дата вчера»",
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "cb_cancel":
        await query.edit_message_reply_markup(reply_markup=None)


# ── Main message handler ───────────────────────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not tg_user:
        await update.message.reply_text("⛔ Access denied.")
        return

    msg = update.message

    if msg.text:
        text = msg.text.strip()
        media_type = "text"
        media_data = None

        # ── Keyboard shortcut intercept ────────────────────────────────────
        shortcut = KEYBOARD_SHORTCUTS.get(text)
        if shortcut == "status":
            await cmd_status(update, ctx)
            return
        elif shortcut == "report":
            await cmd_report(update, ctx)
            return
        elif shortcut == "envelopes":
            await cmd_envelopes(update, ctx)
            return
        elif shortcut == "help":
            await cmd_help(update, ctx)
            return
        elif shortcut == "add_prompt":
            await update.message.reply_text(
                "Напишите расход в свободной форме:\n"
                "Например: «кофе 3.50» или «продукты 85 EUR Esselunga»",
                reply_markup=MAIN_KEYBOARD,
            )
            return

        # ── Greeting intercept (no API call needed) ────────────────────────
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
        media_type = "text"
        media_data = None
        await update.message.reply_text(f"🎤 _{text}_",
                                         parse_mode=ParseMode.MARKDOWN)

    elif msg.photo:
        file_obj = await msg.photo[-1].get_file()
        media_data = bytes(await file_obj.download_as_bytearray())
        text = msg.caption or ""
        media_type = "photo"

    elif msg.document and msg.document.mime_type in ("text/csv", "application/csv"):
        file_obj = await msg.document.get_file()
        csv_bytes = await file_obj.download_as_bytearray()
        text = f"[CSV import]\n{csv_bytes.decode('utf-8', errors='replace')}"
        media_type = "text"
        media_data = None

    else:
        await update.message.reply_text("Не поддерживаемый тип сообщения.")
        return

    # ── Typing indicator — keep alive during long calls ───────────────────
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    async def _keep_typing():
        for _ in range(10):  # max 80 seconds
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
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN,
                                         reply_markup=keyboard)
    else:
        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)


# ── Weekly summary job ─────────────────────────────────────────────────────────

async def weekly_summary_job(context: ContextTypes.DEFAULT_TYPE):
    """Sends weekly budget summary to Mikhail every Monday 09:00 Rome time."""
    mikhail_id = int(os.environ.get("MIKHAIL_TELEGRAM_ID", 0))
    if not mikhail_id:
        return

    session = get_session(mikhail_id, "Mikhail", "admin")
    try:
        text = await agent.run(
            "покажи краткий отчёт по расходам за эту неделю", session
        )
        await context.bot.send_message(
            chat_id=mikhail_id,
            text=f"📅 *Еженедельный отчёт*\n\n{text}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error(f"Weekly summary failed: {e}")


# ── Audio transcription ────────────────────────────────────────────────────────

async def transcribe_audio(audio_bytes: bytes) -> str:
    import openai, re
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

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("menu",      cmd_menu))
    app.add_handler(CommandHandler("envelopes", cmd_envelopes))
    app.add_handler(CommandHandler("envelope",  cmd_envelope))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("report",    cmd_report))
    app.add_handler(CommandHandler("week",      cmd_week))
    app.add_handler(CommandHandler("month",     cmd_month))
    app.add_handler(CommandHandler("undo",      cmd_undo))
    app.add_handler(CommandHandler("help",      cmd_help))
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
