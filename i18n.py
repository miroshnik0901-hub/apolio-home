"""
Apolio Home — Internationalisation (i18n)
Supported: ru, uk, en, it
Priority: Telegram client language → user stored preference → English fallback
"""

SUPPORTED_LANGS = {"ru", "uk", "en", "it"}
DEFAULT_LANG = "ru"


def get_lang(code: str) -> str:
    """Normalise a BCP-47 language code to a supported 2-letter code or default."""
    short = (code or "").lower()[:2]
    return short if short in SUPPORTED_LANGS else DEFAULT_LANG


# ── Reply keyboard button labels ───────────────────────────────────────────────
# Action keys must match the routing in handle_message.

KB_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "status":    "📊 Статус",
        "report":    "📋 Отчёт",
        "add":       "💰 Добавить расход",
        "envelopes": "📁 Конверты",
        "help":      "❓ Помощь",
    },
    "uk": {
        "status":    "📊 Статус",
        "report":    "📋 Звіт",
        "add":       "💰 Додати витрату",
        "envelopes": "📁 Конверти",
        "help":      "❓ Допомога",
    },
    "en": {
        "status":    "📊 Status",
        "report":    "📋 Report",
        "add":       "💰 Add Expense",
        "envelopes": "📁 Envelopes",
        "help":      "❓ Help",
    },
    "it": {
        "status":    "📊 Stato",
        "report":    "📋 Report",
        "add":       "💰 Aggiungi spesa",
        "envelopes": "📁 Buste",
        "help":      "❓ Aiuto",
    },
}

# ── Inline menu node labels ────────────────────────────────────────────────────
# Keys match node IDs in DEFAULT_MENU / BotMenu sheet.
# Do NOT include trailing "›" — _build_inline_menu adds it for submenus.

MENU_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        # top level
        "status":        "📊 Статус",
        "report":        "📋 Аналитика",
        "transactions":  "📝 Записи",
        "envelopes_top": "📁 Конверты",
        "settings":      "⚙️ Система",
        # analytics submenu
        "rep_curr":      "▶ Этот месяц",
        "rep_last":      "◀ Прошлый месяц",
        "rep_week":      "📅 Эта неделя",
        # records submenu
        "txn_recent":    "📋 Последние 10",
        "txn_week":      "📅 За неделю",
        "txn_month":     "📆 За месяц",
        # system submenu
        "set_undo":      "↩️ Отменить",
        "set_envelopes": "📁 Конверты",
        "set_refresh":   "🔄 Обновить меню",
        # navigation
        "back":          "◀ Назад",
        # headings
        "menu_title":    "Меню:",
    },
    "uk": {
        "status":        "📊 Статус",
        "report":        "📋 Аналітика",
        "transactions":  "📝 Записи",
        "envelopes_top": "📁 Конверти",
        "settings":      "⚙️ Система",
        "rep_curr":      "▶ Цей місяць",
        "rep_last":      "◀ Минулий місяць",
        "rep_week":      "📅 Цей тиждень",
        "txn_recent":    "📋 Останні 10",
        "txn_week":      "📅 За тиждень",
        "txn_month":     "📆 За місяць",
        "set_undo":      "↩️ Скасувати",
        "set_envelopes": "📁 Конверти",
        "set_refresh":   "🔄 Оновити меню",
        "back":          "◀ Назад",
        "menu_title":    "Меню:",
    },
    "en": {
        "status":        "📊 Status",
        "report":        "📋 Analytics",
        "transactions":  "📝 Records",
        "envelopes_top": "📁 Envelopes",
        "settings":      "⚙️ System",
        "rep_curr":      "▶ This Month",
        "rep_last":      "◀ Last Month",
        "rep_week":      "📅 This Week",
        "txn_recent":    "📋 Last 10",
        "txn_week":      "📅 This Week",
        "txn_month":     "📆 This Month",
        "set_undo":      "↩️ Undo",
        "set_envelopes": "📁 Envelopes",
        "set_refresh":   "🔄 Refresh Menu",
        "back":          "◀ Back",
        "menu_title":    "Menu:",
    },
    "it": {
        "status":        "📊 Stato",
        "report":        "📋 Analisi",
        "transactions":  "📝 Voci",
        "envelopes_top": "📁 Buste",
        "settings":      "⚙️ Sistema",
        "rep_curr":      "▶ Questo Mese",
        "rep_last":      "◀ Mese Scorso",
        "rep_week":      "📅 Questa Settimana",
        "txn_recent":    "📋 Ultimi 10",
        "txn_week":      "📅 Questa Settimana",
        "txn_month":     "📆 Questo Mese",
        "set_undo":      "↩️ Annulla",
        "set_envelopes": "📁 Buste",
        "set_refresh":   "🔄 Aggiorna Menu",
        "back":          "◀ Indietro",
        "menu_title":    "Menu:",
    },
}

# ── /start welcome message ─────────────────────────────────────────────────────

START_MSG: dict[str, str] = {
    "ru": (
        "👋 Привет, {name}!\n\n"
        "Я <b>Apolio Home</b> — ваш ИИ-помощник для семейного бюджета.\n\n"
        "Просто напишите что потратили:\n"
        "• <i>«кофе 3.50»</i> — запишу расход\n"
        "• <i>«продукты 85 EUR Esselunga»</i> — с заметкой\n"
        "• <i>«покажи отчёт за март»</i> — статистика\n\n"
        "Используйте кнопки внизу для навигации 👇"
    ),
    "uk": (
        "👋 Привіт, {name}!\n\n"
        "Я <b>Apolio Home</b> — ваш ШІ-помічник для сімейного бюджету.\n\n"
        "Просто напишіть що витратили:\n"
        "• <i>«кава 3.50»</i> — запишу витрату\n"
        "• <i>«продукти 85 EUR Esselunga»</i> — з нотаткою\n"
        "• <i>«покажи звіт за березень»</i> — статистика\n\n"
        "Використовуйте кнопки внизу для навігації 👇"
    ),
    "en": (
        "👋 Hi, {name}!\n\n"
        "I'm <b>Apolio Home</b> — your AI assistant for family budgeting.\n\n"
        "Just write what you spent:\n"
        "• <i>«coffee 3.50»</i> — I'll log the expense\n"
        "• <i>«groceries 85 EUR Esselunga»</i> — with a note\n"
        "• <i>«show report for March»</i> — statistics\n\n"
        "Use the buttons below to navigate 👇"
    ),
    "it": (
        "👋 Ciao, {name}!\n\n"
        "Sono <b>Apolio Home</b> — il tuo assistente IA per il budget familiare.\n\n"
        "Scrivi semplicemente cosa hai speso:\n"
        "• <i>«caffè 3.50»</i> — registrerò la spesa\n"
        "• <i>«spesa 85 EUR Esselunga»</i> — con nota\n"
        "• <i>«mostra il report di marzo»</i> — statistiche\n\n"
        "Usa i pulsanti in basso per navigare 👇"
    ),
}

# ── Greeting reply ─────────────────────────────────────────────────────────────

GREETING_MSG: dict[str, str] = {
    "ru": "Привет! 👋\n\nПросто напишите что потратили:\n«кофе 3.50» или «продукты 85 EUR»\n\nИспользуйте кнопки внизу 👇",
    "uk": "Привіт! 👋\n\nПросто напишіть що витратили:\n«кава 3.50» або «продукти 85 EUR»\n\nВикористовуйте кнопки внизу 👇",
    "en": "Hi! 👋\n\nJust write what you spent:\n«coffee 3.50» or «groceries 85 EUR»\n\nUse the buttons below 👇",
    "it": "Ciao! 👋\n\nScrivi semplicemente cosa hai speso:\n«caffè 3.50» o «spesa 85 EUR»\n\nUsa i pulsanti in basso 👇",
}

# ── Add-expense prompt ─────────────────────────────────────────────────────────

ADD_PROMPT: dict[str, str] = {
    "ru": "Напишите расход в свободной форме:\nНапример: «кофе 3.50» или «продукты 85 EUR Esselunga»",
    "uk": "Напишіть витрату у вільній формі:\nНаприклад: «кава 3.50» або «продукти 85 EUR Esselunga»",
    "en": "Write your expense freely:\nExample: «coffee 3.50» or «groceries 85 EUR Esselunga»",
    "it": "Scrivi la spesa in forma libera:\nEsempio: «caffè 3.50» o «spesa 85 EUR Esselunga»",
}


# ── Lookup helpers ─────────────────────────────────────────────────────────────

def t_menu(node_id: str, lang: str) -> str:
    """Translated label for a menu node. Falls back to RU then node_id."""
    lg = get_lang(lang)
    return (
        MENU_LABELS.get(lg, {}).get(node_id)
        or MENU_LABELS.get("ru", {}).get(node_id)
        or node_id
    )


def t_kb(action: str, lang: str) -> str:
    """Translated label for a reply keyboard button."""
    lg = get_lang(lang)
    return (
        KB_LABELS.get(lg, {}).get(action)
        or KB_LABELS.get("en", {}).get(action)
        or action
    )


def t(key: str, lang: str, mapping: dict) -> str:
    """Generic translation from a mapping dict."""
    lg = get_lang(lang)
    return mapping.get(lg) or mapping.get("en") or ""


# ── Reverse map: any language's button text → action key ──────────────────────

def _build_reverse() -> dict[str, str]:
    result: dict[str, str] = {}
    for lang_dict in KB_LABELS.values():
        for action, text in lang_dict.items():
            result[text] = action
    return result


KB_TEXT_TO_ACTION: dict[str, str] = _build_reverse()
