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
        # ── Primary 3-button keyboard (T-028) ──
        "budget":    "💰 Бюджет",
        "add":       "➕ Добавить",
        "more":      "☰ Ещё",
        # ── Legacy keys — kept for KB_TEXT_TO_ACTION reverse map ──
        # (so old messages / taps still route correctly)
        "status":    "📊 Статус",
        "report":    "📋 Отчёт",
        "records":   "📝 Записи",
        "envelopes": "📁 Конверты",
        "settings":  "⚙️ Настройки",
    },
    "uk": {
        "budget":    "💰 Бюджет",
        "add":       "➕ Додати",
        "more":      "☰ Ще",
        "status":    "📊 Статус",
        "report":    "📋 Звіт",
        "records":   "📝 Записи",
        "envelopes": "📁 Конверти",
        "settings":  "⚙️ Налаштування",
    },
    "en": {
        "budget":    "💰 Budget",
        "add":       "➕ Add",
        "more":      "☰ More",
        "status":    "📊 Status",
        "report":    "📋 Report",
        "records":   "📝 Records",
        "envelopes": "📁 Envelopes",
        "settings":  "⚙️ Settings",
    },
    "it": {
        "budget":    "💰 Budget",
        "add":       "➕ Aggiungi",
        "more":      "☰ Altro",
        "status":    "📊 Stato",
        "report":    "📋 Report",
        "records":   "📝 Voci",
        "envelopes": "📁 Buste",
        "settings":  "⚙️ Impostazioni",
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
        "set_lang":      "🌍 Язык",
        "set_lang_ru":   "🇷🇺 Русский",
        "set_lang_uk":   "🇺🇦 Українська",
        "set_lang_en":   "🇬🇧 English",
        "set_lang_it":   "🇮🇹 Italiano",
        "set_envelope":  "📁 Активный конверт",
        "set_undo":      "↩️ Отменить",
        "set_refresh":   "🔄 Обновить меню",
        # admin panel
        "admin_panel":   "🔧 Управление",
        "set_dashboard": "🔄 Обновить панель",
        "set_mode":      "🧪 Режим работы",
        "set_config_view": "⚙️ Настройки конверта",
        "set_init_config": "🔧 Создать настройки",
        "set_users":     "👥 Пользователи",
        "set_learning":  "🧠 База знаний",
        # contribution & trends
        "rep_contribution": "💸 Взносы и расчёты",
        "rep_trends":    "📈 Тренды",
        "rep_custom":    "🗓 Другой период…",
        "txn_search":    "🔍 Поиск…",
        "txn_category":  "🏷 По категории…",
        "txn_who":       "👤 По кому…",
        # help
        "help_top":      "❓ Помощь",
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
        "set_lang":      "🌍 Мова",
        "set_lang_ru":   "🇷🇺 Русский",
        "set_lang_uk":   "🇺🇦 Українська",
        "set_lang_en":   "🇬🇧 English",
        "set_lang_it":   "🇮🇹 Italiano",
        "set_envelope":  "📁 Активний конверт",
        "set_undo":      "↩️ Скасувати",
        "set_refresh":   "🔄 Оновити меню",
        # admin panel
        "admin_panel":   "🔧 Керування",
        "set_dashboard": "🔄 Оновити панель",
        "set_mode":      "🧪 Режим роботи",
        "set_config_view": "⚙️ Налаштування конверта",
        "set_init_config": "🔧 Створити налаштування",
        "set_users":     "👥 Користувачі",
        "set_learning":  "🧠 База знань",
        # contribution & trends
        "rep_contribution": "💸 Внески та розрахунки",
        "rep_trends":    "📈 Тренди",
        "rep_custom":    "🗓 Інший період…",
        "txn_search":    "🔍 Пошук…",
        "txn_category":  "🏷 За категорією…",
        "txn_who":       "👤 За ким…",
        "help_top":      "❓ Допомога",
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
        "set_lang":      "🌍 Language",
        "set_lang_ru":   "🇷🇺 Русский",
        "set_lang_uk":   "🇺🇦 Українська",
        "set_lang_en":   "🇬🇧 English",
        "set_lang_it":   "🇮🇹 Italiano",
        "set_envelope":  "📁 Active Envelope",
        "set_undo":      "↩️ Undo",
        "set_refresh":   "🔄 Refresh Menu",
        # admin panel
        "admin_panel":   "🔧 Administration",
        "set_dashboard": "🔄 Refresh Dashboard",
        "set_mode":      "🧪 Test / Prod Mode",
        "set_config_view": "⚙️ Envelope Config",
        "set_init_config": "🔧 Init Config",
        "set_users":     "👥 Users",
        "set_learning":  "🧠 Knowledge Base",
        # contribution & trends
        "rep_contribution": "💸 Contributions",
        "rep_trends":    "📈 Trends",
        "rep_custom":    "🗓 Other Period…",
        "txn_search":    "🔍 Search…",
        "txn_category":  "🏷 By Category…",
        "txn_who":       "👤 By Person…",
        "help_top":      "❓ Help",
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
        "set_lang":      "🌍 Lingua",
        "set_lang_ru":   "🇷🇺 Русский",
        "set_lang_uk":   "🇺🇦 Українська",
        "set_lang_en":   "🇬🇧 English",
        "set_lang_it":   "🇮🇹 Italiano",
        "set_envelope":  "📁 Busta Attiva",
        "set_undo":      "↩️ Annulla",
        "set_refresh":   "🔄 Aggiorna Menu",
        # admin panel
        "admin_panel":   "🔧 Gestione",
        "set_dashboard": "🔄 Aggiorna Pannello",
        "set_mode":      "🧪 Modalità Test/Prod",
        "set_config_view": "⚙️ Config. Busta",
        "set_init_config": "🔧 Crea Config.",
        "set_users":     "👥 Utenti",
        "set_learning":  "🧠 Base Conoscenza",
        # contribution & trends
        "rep_contribution": "💸 Contributi",
        "rep_trends":    "📈 Tendenze",
        "rep_custom":    "🗓 Altro Periodo…",
        "txn_search":    "🔍 Cerca…",
        "txn_category":  "🏷 Per Categoria…",
        "txn_who":       "👤 Per Persona…",
        "help_top":      "❓ Aiuto",
        "back":          "◀ Indietro",
        "menu_title":    "Menu:",
    },
}

# ── Month names (localized) ────────────────────────────────────────────────────

# MONTH_LABELS: standalone month name, e.g. "Апрель 2026" / "April 2026"
MONTH_LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "01": "Январь",  "02": "Февраль", "03": "Март",
        "04": "Апрель",  "05": "Май",     "06": "Июнь",
        "07": "Июль",    "08": "Август",  "09": "Сентябрь",
        "10": "Октябрь", "11": "Ноябрь",  "12": "Декабрь",
    },
    "uk": {
        "01": "Січень",  "02": "Лютий",   "03": "Березень",
        "04": "Квітень", "05": "Травень", "06": "Червень",
        "07": "Липень",  "08": "Серпень", "09": "Вересень",
        "10": "Жовтень", "11": "Листопад","12": "Грудень",
    },
    "en": {
        "01": "January",  "02": "February", "03": "March",
        "04": "April",    "05": "May",      "06": "June",
        "07": "July",     "08": "August",   "09": "September",
        "10": "October",  "11": "November", "12": "December",
    },
    "it": {
        "01": "Gennaio",  "02": "Febbraio", "03": "Marzo",
        "04": "Aprile",   "05": "Maggio",   "06": "Giugno",
        "07": "Luglio",   "08": "Agosto",   "09": "Settembre",
        "10": "Ottobre",  "11": "Novembre", "12": "Dicembre",
    },
}

# MONTH_NAMES: prepositional form ("in April"), used inside sentences
MONTH_NAMES: dict[str, dict[str, str]] = {
    "ru": {
        "01": "январе",   "02": "феврале",  "03": "марте",
        "04": "апреле",   "05": "мае",      "06": "июне",
        "07": "июле",     "08": "августе",  "09": "сентябре",
        "10": "октябре",  "11": "ноябре",   "12": "декабре",
    },
    "uk": {
        "01": "січні",    "02": "лютому",   "03": "березні",
        "04": "квітні",   "05": "травні",   "06": "червні",
        "07": "липні",    "08": "серпні",   "09": "вересні",
        "10": "жовтні",   "11": "листопаді","12": "грудні",
    },
    "en": {
        "01": "January",  "02": "February", "03": "March",
        "04": "April",    "05": "May",      "06": "June",
        "07": "July",     "08": "August",   "09": "September",
        "10": "October",  "11": "November", "12": "December",
    },
    "it": {
        "01": "gennaio",  "02": "febbraio", "03": "marzo",
        "04": "aprile",   "05": "maggio",   "06": "giugno",
        "07": "luglio",   "08": "agosto",   "09": "settembre",
        "10": "ottobre",  "11": "novembre", "12": "dicembre",
    },
}

# ── Misc UI strings ────────────────────────────────────────────────────────────

NO_LIMIT: dict[str, str] = {
    "ru": "без бюджета",
    "uk": "без бюджету",
    "en": "no budget",
    "it": "senza budget",
}

# ── /start welcome message ─────────────────────────────────────────────────────

START_MSG: dict[str, str] = {
    "ru": (
        "🏠 Привет, {name}!\n\n"
        "Я <b>Apolio Home</b> — ваш ИИ-помощник для семейного бюджета.\n\n"
        "Просто напишите что потратили:\n"
        "• <i>«кофе 3.50»</i> — запишу расход\n"
        "• <i>«продукты 85 EUR Esselunga»</i> — с заметкой\n"
        "• <i>«покажи отчёт за март»</i> — статистика\n\n"
        "Используйте кнопки внизу для навигации 👇"
    ),
    "uk": (
        "🏠 Привіт, {name}!\n\n"
        "Я <b>Apolio Home</b> — ваш ШІ-помічник для сімейного бюджету.\n\n"
        "Просто напишіть що витратили:\n"
        "• <i>«кава 3.50»</i> — запишу витрату\n"
        "• <i>«продукти 85 EUR Esselunga»</i> — з нотаткою\n"
        "• <i>«покажи звіт за березень»</i> — статистика\n\n"
        "Використовуйте кнопки внизу для навігації 👇"
    ),
    "en": (
        "🏠 Hi, {name}!\n\n"
        "I'm <b>Apolio Home</b> — your AI assistant for family budgeting.\n\n"
        "Just write what you spent:\n"
        "• <i>«coffee 3.50»</i> — I'll log the expense\n"
        "• <i>«groceries 85 EUR Esselunga»</i> — with a note\n"
        "• <i>«show report for March»</i> — statistics\n\n"
        "Use the buttons below to navigate 👇"
    ),
    "it": (
        "🏠 Ciao, {name}!\n\n"
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


# ── System messages (errors, confirmations, prompts) ──────────────────────────

SYS: dict[str, dict[str, str]] = {
    "access_denied": {
        "ru": "⛔ Доступ запрещён.",
        "uk": "⛔ Доступ заборонено.",
        "en": "⛔ Access denied.",
        "it": "⛔ Accesso negato.",
    },
    "admin_only": {
        "ru": "⛔ Только для администратора.",
        "uk": "⛔ Тільки для адміністратора.",
        "en": "⛔ Admin only.",
        "it": "⛔ Solo per amministratori.",
    },
    "no_rights": {
        "ru": "⛔ Недостаточно прав.",
        "uk": "⛔ Недостатньо прав.",
        "en": "⛔ Insufficient permissions.",
        "it": "⛔ Permessi insufficienti.",
    },
    "menu_not_found": {
        "ru": "Пункт меню не найден.",
        "uk": "Пункт меню не знайдено.",
        "en": "Menu item not found.",
        "it": "Voce di menu non trovata.",
    },
    "menu_refreshed": {
        "ru": "🔄 Меню обновлено.",
        "uk": "🔄 Меню оновлено.",
        "en": "🔄 Menu refreshed.",
        "it": "🔄 Menu aggiornato.",
    },
    "dashboard_refreshed": {
        "ru": "🔄 <b>Дашборд обновлён</b>",
        "uk": "🔄 <b>Дашборд оновлено</b>",
        "en": "🔄 <b>Dashboard refreshed</b>",
        "it": "🔄 <b>Pannello aggiornato</b>",
    },
    "glossary_empty": {
        "ru": "🧠 <b>База знаний</b>\n\nДанных пока нет.",
        "uk": "🧠 <b>База знань</b>\n\nДаних поки немає.",
        "en": "🧠 <b>Knowledge base</b>\n\nNo data yet.",
        "it": "🧠 <b>Base di conoscenza</b>\n\nNessun dato.",
    },
    "config_title": {
        "ru": "⚙️ <b>Конфигурация</b>",
        "uk": "⚙️ <b>Конфігурація</b>",
        "en": "⚙️ <b>Configuration</b>",
        "it": "⚙️ <b>Configurazione</b>",
    },
    "config_active_file": {
        "ru": "📁 <b>Активный файл:</b>",
        "uk": "📁 <b>Активний файл:</b>",
        "en": "📁 <b>Active file:</b>",
        "it": "📁 <b>File attivo:</b>",
    },
    "config_open_sheets": {
        "ru": "Открыть в Google Sheets",
        "uk": "Відкрити в Google Sheets",
        "en": "Open in Google Sheets",
        "it": "Apri in Google Sheets",
    },
    "config_envelope_settings": {
        "ru": "<b>Настройки конверта:</b>",
        "uk": "<b>Налаштування конверта:</b>",
        "en": "<b>Envelope settings:</b>",
        "it": "<b>Impostazioni busta:</b>",
    },
    "config_admin_global": {
        "ru": "<b>Admin Config (глобальные):</b>",
        "uk": "<b>Admin Config (глобальні):</b>",
        "en": "<b>Admin Config (global):</b>",
        "it": "<b>Admin Config (globali):</b>",
    },
    "config_init_title": {
        "ru": "🔧 <b>Init Config: {env_id}</b>",
        "uk": "🔧 <b>Init Config: {env_id}</b>",
        "en": "🔧 <b>Init Config: {env_id}</b>",
        "it": "🔧 <b>Init Config: {env_id}</b>",
    },
    "config_init_written": {
        "ru": "✅ <b>Записано ({count}):</b>",
        "uk": "✅ <b>Записано ({count}):</b>",
        "en": "✅ <b>Written ({count}):</b>",
        "it": "✅ <b>Scritto ({count}):</b>",
    },
    "config_init_all_present": {
        "ru": "✅ Все ключи уже присутствуют",
        "uk": "✅ Усі ключі вже присутні",
        "en": "✅ All keys already present",
        "it": "✅ Tutte le chiavi già presenti",
    },
    "config_init_skipped": {
        "ru": "⏭ <b>Пропущено (уже есть):</b>",
        "uk": "⏭ <b>Пропущено (вже є):</b>",
        "en": "⏭ <b>Skipped (already exist):</b>",
        "it": "⏭ <b>Saltato (già presente):</b>",
    },
    "config_init_check": {
        "ru": "Откройте Config вкладку конверта чтобы проверить.",
        "uk": "Відкрийте Config вкладку конверта щоб перевірити.",
        "en": "Open the Config tab of the envelope to verify.",
        "it": "Apri la scheda Config della busta per verificare.",
    },
    "users_title": {
        "ru": "👥 <b>Пользователи</b>  ({count} чел.)",
        "uk": "👥 <b>Користувачі</b>  ({count} осіб)",
        "en": "👥 <b>Users</b>  ({count} people)",
        "it": "👥 <b>Utenti</b>  ({count} persone)",
    },
    "users_envelopes": {
        "ru": "Конверты",
        "uk": "Конверти",
        "en": "Envelopes",
        "it": "Buste",
    },
    "config_envelope_empty": {
        "ru": "Добавьте split_rule, split_threshold, split_users, base_contributor в Config вкладку файла конверта",
        "uk": "Додайте split_rule, split_threshold, split_users, base_contributor у Config вкладку файлу конверта",
        "en": "Add split_rule, split_threshold, split_users, base_contributor to the Config tab of the envelope file",
        "it": "Aggiungi split_rule, split_threshold, split_users, base_contributor nella scheda Config del file busta",
    },
    "no_envelopes": {
        "ru": "Конверты ещё не созданы.\n\nНапишите: «создай конверт Название, бюджет N EUR»",
        "uk": "Конверти ще не створені.\n\nНапишіть: «створи конверт Назва, бюджет N EUR»",
        "en": "No envelopes yet.\n\nWrite: «create envelope Name, budget N EUR»",
        "it": "Nessuna busta ancora.\n\nScrivi: «crea busta Nome, budget N EUR»",
    },
    "no_transactions": {
        "ru": "Записей пока нет.\n\nПросто напишите что потратили, например: «кофе 3.50»",
        "uk": "Записів поки немає.\n\nПросто напишіть що витратили, наприклад: «кава 3.50»",
        "en": "No records yet.\n\nJust write what you spent, e.g.: «coffee 3.50»",
        "it": "Nessun record ancora.\n\nScrivi cosa hai speso, es.: «caffè 3.50»",
    },
    "cmd_not_supported": {
        "ru": "Команда не поддерживается.",
        "uk": "Команда не підтримується.",
        "en": "Command not supported.",
        "it": "Comando non supportato.",
    },
    "unsupported_media": {
        "ru": "Тип файла не поддерживается.",
        "uk": "Тип файлу не підтримується.",
        "en": "Unsupported media type.",
        "it": "Tipo di file non supportato.",
    },
    "undo_nothing": {
        "ru": "Нет действий для отмены.",
        "uk": "Немає дій для скасування.",
        "en": "Nothing to undo.",
        "it": "Nessuna azione da annullare.",
    },
    "undo_done": {
        "ru": "↩ Отменено",
        "uk": "↩ Скасовано",
        "en": "↩ Undone",
        "it": "↩ Annullato",
    },
    "envelope_not_found": {
        "ru": "❌ Конверт не найден.",
        "uk": "❌ Конверт не знайдено.",
        "en": "❌ Envelope not found.",
        "it": "❌ Busta non trovata.",
    },
    "undo_edit_not_impl": {
        "ru": "↩ Отмена изменения поля не реализована.\nНапишите, что нужно исправить.",
        "uk": "↩ Скасування зміни поля не реалізовано.\nНапишіть, що треба виправити.",
        "en": "↩ Field edit undo is not yet implemented.\nTell me what to fix.",
        "it": "↩ Annullamento modifica campo non implementato.\nDimmi cosa correggere.",
    },
    "load_error": {
        "ru": "❌ Ошибка загрузки: {detail}",
        "uk": "❌ Помилка завантаження: {detail}",
        "en": "❌ Load error: {detail}",
        "it": "❌ Errore caricamento: {detail}",
    },
    "input_prompt": {
        "ru": "✏️ Введите значение:",
        "uk": "✏️ Введіть значення:",
        "en": "✏️ Enter value:",
        "it": "✏️ Inserisci valore:",
    },
    "report_title": {
        "ru": "📋 Отчёт — выберите период:",
        "uk": "📋 Звіт — оберіть період:",
        "en": "📋 Report — choose period:",
        "it": "📋 Report — scegli periodo:",
    },
    "records_title": {
        "ru": "📝 Записи — выберите фильтр:",
        "uk": "📝 Записи — оберіть фільтр:",
        "en": "📝 Records — choose filter:",
        "it": "📝 Voci — scegli filtro:",
    },
    "settings_title": {
        "ru": "⚙️ Настройки:",
        "uk": "⚙️ Налаштування:",
        "en": "⚙️ Settings:",
        "it": "⚙️ Impostazioni:",
    },
    "lang_changed": {
        "ru": "✅ Язык изменён на русский.",
        "uk": "✅ Мова змінена на українську.",
        "en": "✅ Language changed to English.",
        "it": "✅ Lingua cambiata in italiano.",
    },
    # ── T-133: Balance / contribution i18n ────────────────────────────────
    "bal_expenses": {
        "ru": "расходы", "uk": "витрати", "en": "expenses", "it": "spese",
    },
    "bal_overpaid": {
        "ru": "переплата", "uk": "переплата", "en": "overpaid", "it": "eccedenza",
    },
    "bal_owes": {
        "ru": "должен", "uk": "борг", "en": "owes", "it": "deve",
    },
    "bal_header": {
        "ru": "⚖️ Баланс:", "uk": "⚖️ Баланс:", "en": "⚖️ Balance:", "it": "⚖️ Bilancio:",
    },
    "bal_joint_topup": {
        "ru": "Внёс на joint", "uk": "Вніс на joint", "en": "Joint top-up", "it": "Versamento joint",
    },
    "bal_personal_exp": {
        "ru": "Оплатил лично", "uk": "Оплатив особисто", "en": "Paid personally", "it": "Pagato personalmente",
    },
    # ── T-139: Duplicate transaction options ──
    "dup_update": {
        "ru": "📝 Обновить существующую", "uk": "📝 Оновити існуючу", "en": "📝 Update existing", "it": "📝 Aggiorna esistente",
    },
    "dup_add_new": {
        "ru": "➕ Добавить как новую", "uk": "➕ Додати як нову", "en": "➕ Add as new", "it": "➕ Aggiungi come nuova",
    },
    "dup_cancel": {
        "ru": "❌ Отмена", "uk": "❌ Скасувати", "en": "❌ Cancel", "it": "❌ Annulla",
    },
    "dup_cancelled": {
        "ru": "Операция отменена.", "uk": "Операцію скасовано.", "en": "Operation cancelled.", "it": "Operazione annullata.",
    },
    # ── T-143: Bulk delete ──
    "del_bulk": {
        "ru": "Удалить все ({n})", "uk": "Видалити всі ({n})", "en": "Delete all ({n})", "it": "Elimina tutti ({n})",
    },
    "del_bulk_result": {
        "ru": "Удалено: {deleted} из {total}", "uk": "Видалено: {deleted} із {total}",
        "en": "Deleted: {deleted} of {total}", "it": "Eliminati: {deleted} di {total}",
    },
    "del_bulk_errors": {
        "ru": "Ошибки:", "uk": "Помилки:", "en": "Errors:", "it": "Errori:",
    },
    "del_single_result": {
        "ru": "Удалено: {tx_id}", "uk": "Видалено: {tx_id}",
        "en": "Deleted: {tx_id}", "it": "Eliminato: {tx_id}",
    },
    "del_session_expired": {
        "ru": "Сессия обновилась. Повторите удаление.",
        "uk": "Сесія оновилася. Повторіть видалення.",
        "en": "Session expired. Please retry the deletion.",
        "it": "Sessione scaduta. Ripetere l'eliminazione.",
    },
    "del_unknown_result": {
        "ru": "Неизвестный результат: {result}",
        "uk": "Невідомий результат: {result}",
        "en": "Unknown result: {result}",
        "it": "Risultato sconosciuto: {result}",
    },
    "error_generic": {
        "ru": "Ошибка: {err}", "uk": "Помилка: {err}",
        "en": "Error: {err}", "it": "Errore: {err}",
    },
    "error_something_wrong": {
        "ru": "Что-то пошло не так. Попробуй ещё раз.",
        "uk": "Щось пішло не так. Спробуй ще раз.",
        "en": "Something went wrong. Please try again.",
        "it": "Qualcosa è andato storto. Riprova.",
    },
    "bal_obligation": {
        "ru": "Обязательство", "uk": "Зобов'язання", "en": "Obligation", "it": "Obbligo",
    },
    "bal_credit": {
        "ru": "Кредит", "uk": "Кредит", "en": "Credit", "it": "Credito",
    },
    "bal_debt": {
        "ru": "Долг", "uk": "Борг", "en": "Debt", "it": "Debito",
    },
    "bal_zero": {
        "ru": "Баланс", "uk": "Баланс", "en": "Balance", "it": "Bilancio",
    },
}

# ── Category translations (Sheets store English names) ────────────────────────
# Key = English category name (as in Google Sheets Categories tab).
# Value = {lang: translated name}.
# English falls back to the key itself, so only ru/uk/it needed.

CAT_NAMES: dict[str, dict[str, str]] = {
    "Food":           {"ru": "Еда",           "uk": "Їжа",            "it": "Cibo"},
    "Housing":        {"ru": "Жильё",         "uk": "Житло",          "it": "Casa"},
    "Transport":      {"ru": "Транспорт",     "uk": "Транспорт",      "it": "Trasporto"},
    "Health":         {"ru": "Здоровье",      "uk": "Здоров'я",       "it": "Salute"},
    "Entertainment":  {"ru": "Развлечения",   "uk": "Розваги",        "it": "Svago"},
    "Education":      {"ru": "Образование",   "uk": "Освіта",         "it": "Istruzione"},
    "Travel":         {"ru": "Путешествия",   "uk": "Подорожі",       "it": "Viaggi"},
    "Savings":        {"ru": "Сбережения",    "uk": "Заощадження",    "it": "Risparmi"},
    "Other":          {"ru": "Другое",        "uk": "Інше",           "it": "Altro"},
    "Transfer":       {"ru": "Перевод",       "uk": "Переказ",        "it": "Trasferimento"},
    "Children":       {"ru": "Дети",          "uk": "Діти",           "it": "Bambini"},
    "Personal":       {"ru": "Личное",        "uk": "Особисте",       "it": "Personale"},
    "Household":      {"ru": "Быт",           "uk": "Побут",          "it": "Domestico"},
    "Subscriptions":  {"ru": "Подписки",      "uk": "Підписки",       "it": "Abbonamenti"},
    "Income":         {"ru": "Доход",         "uk": "Дохід",          "it": "Entrate"},
    "Top-up":         {"ru": "Пополнение",   "uk": "Поповнення",     "it": "Ricarica"},
}


def t_cat(category: str, lang: str) -> str:
    """Translate a category name from English (Sheets) to user language."""
    if not category:
        return category
    lg = get_lang(lang)
    if lg == "en":
        return category
    entry = CAT_NAMES.get(category)
    if entry:
        return entry.get(lg) or entry.get("ru") or category
    return category


def ts(key: str, lang: str) -> str:
    """Translate a system message key. Falls back to ru then en."""
    lg = get_lang(lang)
    return (
        SYS.get(key, {}).get(lg)
        or SYS.get(key, {}).get("ru")
        or SYS.get(key, {}).get("en")
        or key
    )


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


# ── UI display strings (HTML responses) ────────────────────────────────────────
# Use tu(key, lang, **kwargs) to retrieve and optionally format.

UI: dict[str, dict[str, str]] = {
    # ── Status ─────────────────────────────────────────────────────────────
    "status_title": {
        "ru": "💰 <b>Бюджет · {label}</b>  ·  📁 {env}{mode}",
        "uk": "💰 <b>Бюджет · {label}</b>  ·  📁 {env}{mode}",
        "en": "💰 <b>Budget · {label}</b>  ·  📁 {env}{mode}",
        "it": "💰 <b>Budget · {label}</b>  ·  📁 {env}{mode}",
    },
    "status_remaining": {
        "ru": "Осталось: <b>{remaining:,.0f} EUR</b>  ·  {days} дн.",
        "uk": "Залишилось: <b>{remaining:,.0f} EUR</b>  ·  {days} дн.",
        "en": "Remaining: <b>{remaining:,.0f} EUR</b>  ·  {days}d",
        "it": "Rimanente: <b>{remaining:,.0f} EUR</b>  ·  {days}g",
    },
    "status_spent": {
        "ru": "Потрачено: <b>{spent:,.0f} EUR</b>",
        "uk": "Витрачено: <b>{spent:,.0f} EUR</b>",
        "en": "Spent: <b>{spent:,.0f} EUR</b>",
        "it": "Speso: <b>{spent:,.0f} EUR</b>",
    },
    "status_pace": {
        "ru": "Темп: <i>{rate:,.0f} EUR/день → прогноз {proj:,.0f} EUR ({delta})</i>",
        "uk": "Темп: <i>{rate:,.0f} EUR/день → прогноз {proj:,.0f} EUR ({delta})</i>",
        "en": "Pace: <i>{rate:,.0f} EUR/day → forecast {proj:,.0f} EUR ({delta})</i>",
        "it": "Ritmo: <i>{rate:,.0f} EUR/giorno → previsione {proj:,.0f} EUR ({delta})</i>",
    },
    "status_error": {
        "ru": "❌ Не удалось загрузить статус: {detail}",
        "uk": "❌ Не вдалося завантажити статус: {detail}",
        "en": "❌ Failed to load status: {detail}",
        "it": "❌ Impossibile caricare lo stato: {detail}",
    },
    # ── Report ─────────────────────────────────────────────────────────────
    "report_heading": {
        "ru": "📋 <b>Аналитика · {label}</b>  ·  📁 {env}{mode}",
        "uk": "📋 <b>Аналітика · {label}</b>  ·  📁 {env}{mode}",
        "en": "📋 <b>Analytics · {label}</b>  ·  📁 {env}{mode}",
        "it": "📋 <b>Analisi · {label}</b>  ·  📁 {env}{mode}",
    },
    "report_no_records": {
        "ru": "Записей за этот период нет.",
        "uk": "Записів за цей період немає.",
        "en": "No records for this period.",
        "it": "Nessun record per questo periodo.",
    },
    "report_total_vs": {
        "ru": "Итого: <b>{total:,.0f} EUR</b>  <i>{arrow}{pct}% vs {prev_label}</i>",
        "uk": "Разом: <b>{total:,.0f} EUR</b>  <i>{arrow}{pct}% vs {prev_label}</i>",
        "en": "Total: <b>{total:,.0f} EUR</b>  <i>{arrow}{pct}% vs {prev_label}</i>",
        "it": "Totale: <b>{total:,.0f} EUR</b>  <i>{arrow}{pct}% vs {prev_label}</i>",
    },
    "report_total": {
        "ru": "Итого расходов: <b>{total:,.0f} EUR</b>",
        "uk": "Разом витрат: <b>{total:,.0f} EUR</b>",
        "en": "Total expenses: <b>{total:,.0f} EUR</b>",
        "it": "Totale spese: <b>{total:,.0f} EUR</b>",
    },
    "report_of_budget": {
        "ru": "{pct}% от бюджета ({cap:,.0f} EUR)",
        "uk": "{pct}% від бюджету ({cap:,.0f} EUR)",
        "en": "{pct}% of budget ({cap:,.0f} EUR)",
        "it": "{pct}% del budget ({cap:,.0f} EUR)",
    },
    "report_error": {
        "ru": "❌ Не удалось загрузить отчёт: {detail}",
        "uk": "❌ Не вдалося завантажити звіт: {detail}",
        "en": "❌ Failed to load report: {detail}",
        "it": "❌ Impossibile caricare il report: {detail}",
    },
    # ── Week ───────────────────────────────────────────────────────────────
    "week_title": {
        "ru": "📅 <b>Эта неделя</b>  ({week_label})",
        "uk": "📅 <b>Цей тиждень</b>  ({week_label})",
        "en": "📅 <b>This Week</b>  ({week_label})",
        "it": "📅 <b>Questa Settimana</b>  ({week_label})",
    },
    "week_no_expenses": {
        "ru": "За эту неделю расходов ещё нет.",
        "uk": "Цього тижня витрат ще немає.",
        "en": "No expenses this week yet.",
        "it": "Nessuna spesa questa settimana.",
    },
    "week_total": {
        "ru": "Итого: <b>{total:,.0f} EUR</b>  ·  {n} записей",
        "uk": "Разом: <b>{total:,.0f} EUR</b>  ·  {n} записів",
        "en": "Total: <b>{total:,.0f} EUR</b>  ·  {n} records",
        "it": "Totale: <b>{total:,.0f} EUR</b>  ·  {n} voci",
    },
    "week_daily_avg": {
        "ru": "В среднем: <i>{avg:,.0f} EUR/день</i>",
        "uk": "В середньому: <i>{avg:,.0f} EUR/день</i>",
        "en": "Average: <i>{avg:,.0f} EUR/day</i>",
        "it": "Media: <i>{avg:,.0f} EUR/giorno</i>",
    },
    "week_error": {
        "ru": "❌ Ошибка загрузки недели: {detail}",
        "uk": "❌ Помилка завантаження тижня: {detail}",
        "en": "❌ Failed to load week: {detail}",
        "it": "❌ Errore caricamento settimana: {detail}",
    },
    # ── Contribution ───────────────────────────────────────────────────────
    "contrib_title": {
        "ru": "💸 <b>Взносы — {label}</b>",
        "uk": "💸 <b>Внески — {label}</b>",
        "en": "💸 <b>Contributions — {label}</b>",
        "it": "💸 <b>Contributi — {label}</b>",
    },
    "contrib_unavailable": {
        "ru": "Данные о взносах недоступны.",
        "uk": "Дані про внески недоступні.",
        "en": "Contribution data unavailable.",
        "it": "Dati contributi non disponibili.",
    },
    "contrib_contributed": {
        "ru": "<b>Внесено:</b>",
        "uk": "<b>Внесено:</b>",
        "en": "<b>Contributed:</b>",
        "it": "<b>Contribuito:</b>",
    },
    "contrib_total_exp": {
        "ru": "Общие расходы: <b>{total:,.0f} {cur}</b>",
        "uk": "Загальні витрати: <b>{total:,.0f} {cur}</b>",
        "en": "Total expenses: <b>{total:,.0f} {cur}</b>",
        "it": "Spese totali: <b>{total:,.0f} {cur}</b>",
    },
    "contrib_solo": {
        "ru": "Схема: всё на {user}",
        "uk": "Схема: все на {user}",
        "en": "Scheme: all on {user}",
        "it": "Schema: tutto su {user}",
    },
    "contrib_below_threshold": {
        "ru": "До порога ({thr:,.0f} {cur}) — всё на {user}",
        "uk": "До порогу ({thr:,.0f} {cur}) — все на {user}",
        "en": "Below threshold ({thr:,.0f} {cur}) — all on {user}",
        "it": "Sotto soglia ({thr:,.0f} {cur}) — tutto su {user}",
    },
    "contrib_excess": {
        "ru": "Порог: {thr:,.0f} {cur}  →  превышение: <b>{excess:,.0f} {cur}</b>\nКаждый платит: {per:,.0f} {cur} (плюс доля {user})",
        "uk": "Поріг: {thr:,.0f} {cur}  →  перевищення: <b>{excess:,.0f} {cur}</b>\nКожен платить: {per:,.0f} {cur} (плюс частка {user})",
        "en": "Threshold: {thr:,.0f} {cur}  →  excess: <b>{excess:,.0f} {cur}</b>\nEach pays: {per:,.0f} {cur} (plus {user}'s share)",
        "it": "Soglia: {thr:,.0f} {cur}  →  eccesso: <b>{excess:,.0f} {cur}</b>\nOgnuno paga: {per:,.0f} {cur} (più quota {user})",
    },
    "contrib_shares": {
        "ru": "<b>Доля каждого:</b>",
        "uk": "<b>Частка кожного:</b>",
        "en": "<b>Each person's share:</b>",
        "it": "<b>Quota di ciascuno:</b>",
    },
    "contrib_balance": {
        "ru": "<b>Итог (внесено − доля):</b>",
        "uk": "<b>Підсумок (внесено − частка):</b>",
        "en": "<b>Balance (contributed − share):</b>",
        "it": "<b>Saldo (contribuito − quota):</b>",
    },
    "contrib_in_plus": {
        "ru": "✅ в плюсе",
        "uk": "✅ в плюсі",
        "en": "✅ in surplus",
        "it": "✅ in attivo",
    },
    "contrib_owes": {
        "ru": "⚠️ должен",
        "uk": "⚠️ винен",
        "en": "⚠️ owes",
        "it": "⚠️ deve",
    },
    "contrib_even": {
        "ru": "≈ ровно",
        "uk": "≈ рівно",
        "en": "≈ even",
        "it": "≈ pari",
    },
    # ── Trends ─────────────────────────────────────────────────────────────
    "trends_title": {
        "ru": "📈 <b>Тренды — {label}</b>",
        "uk": "📈 <b>Тренди — {label}</b>",
        "en": "📈 <b>Trends — {label}</b>",
        "it": "📈 <b>Tendenze — {label}</b>",
    },
    "trends_by_cat": {
        "ru": "<b>Изменения по категориям (vs пред. месяц):</b>",
        "uk": "<b>Зміни по категоріях (vs поп. місяць):</b>",
        "en": "<b>Category changes (vs prev. month):</b>",
        "it": "<b>Variazioni per categoria (vs mese prec.):</b>",
    },
    "trends_empty": {
        "ru": "Трендов пока нет (нужны данные за 2+ месяца).",
        "uk": "Трендів поки немає (потрібні дані за 2+ місяці).",
        "en": "No trends yet (need 2+ months of data).",
        "it": "Nessuna tendenza (servono 2+ mesi di dati).",
    },
    "trends_anomalies": {
        "ru": "⚠️ <b>Аномалии (значительно выше среднего):</b>",
        "uk": "⚠️ <b>Аномалії (значно вище середнього):</b>",
        "en": "⚠️ <b>Anomalies (significantly above average):</b>",
        "it": "⚠️ <b>Anomalie (significativamente sopra la media):</b>",
    },
    "trends_anomaly_detail": {
        "ru": "(среднее {avg:,.0f}, ×{ratio})",
        "uk": "(середнє {avg:,.0f}, ×{ratio})",
        "en": "(avg {avg:,.0f}, ×{ratio})",
        "it": "(media {avg:,.0f}, ×{ratio})",
    },
    "trends_large": {
        "ru": "💸 <b>Крупные расходы (7 дней):</b>",
        "uk": "💸 <b>Великі витрати (7 днів):</b>",
        "en": "💸 <b>Large expenses (7 days):</b>",
        "it": "💸 <b>Spese grandi (7 giorni):</b>",
    },
    "trends_over_pace": {
        "ru": "\n⚠️ Темп: прогноз {proj:,.0f} {cur} при бюджете {cap:,.0f} {cur}",
        "uk": "\n⚠️ Темп: прогноз {proj:,.0f} {cur} при бюджеті {cap:,.0f} {cur}",
        "en": "\n⚠️ Pace: forecast {proj:,.0f} {cur} vs budget {cap:,.0f} {cur}",
        "it": "\n⚠️ Ritmo: previsione {proj:,.0f} {cur} vs budget {cap:,.0f} {cur}",
    },
    "trends_under_pace": {
        "ru": "\n✅ Темп: расходы ниже плана",
        "uk": "\n✅ Темп: витрати нижче плану",
        "en": "\n✅ Pace: spending below target",
        "it": "\n✅ Ritmo: spesa sotto obiettivo",
    },
    "trends_error": {
        "ru": "❌ Ошибка: {detail}",
        "uk": "❌ Помилка: {detail}",
        "en": "❌ Error: {detail}",
        "it": "❌ Errore: {detail}",
    },
    # ── Shared section headers ──────────────────────────────────────────────
    "by_category": {
        "ru": "<b>По категориям:</b>",
        "uk": "<b>По категоріях:</b>",
        "en": "<b>By category:</b>",
        "it": "<b>Per categoria:</b>",
    },
    "by_person": {
        "ru": "<b>По кому:</b>",
        "uk": "<b>По кому:</b>",
        "en": "<b>By person:</b>",
        "it": "<b>Per persona:</b>",
    },
    "by_day": {
        "ru": "<b>По дням:</b>",
        "uk": "<b>По днях:</b>",
        "en": "<b>By day:</b>",
        "it": "<b>Per giorno:</b>",
    },
    # ── Weekly job ─────────────────────────────────────────────────────────
    "weekly_job_title": {
        "ru": "📅 <b>Еженедельный отчёт</b>",
        "uk": "📅 <b>Щотижневий звіт</b>",
        "en": "📅 <b>Weekly Report</b>",
        "it": "📅 <b>Report Settimanale</b>",
    },
    # ── Mode toggle (T-040) ───────────────────────────────────────────────
    "mode_test_on": {
        "ru": "🧪 <b>Тестовый режим включён</b>\n\nБот работает с тестовыми данными.\nИзменения не влияют на реальный бюджет.\n\nДля возврата — нажми эту кнопку ещё раз.",
        "uk": "🧪 <b>Тестовий режим увімкнено</b>\n\nБот працює з тестовими даними.\nЗміни не впливають на реальний бюджет.\n\nДля повернення — натисни цю кнопку ще раз.",
        "en": "🧪 <b>Test mode enabled</b>\n\nBot is using test data.\nChanges won't affect the real budget.\n\nTo switch back — press this button again.",
        "it": "🧪 <b>Modalità test attivata</b>\n\nIl bot usa dati di test.\nLe modifiche non influenzano il budget reale.\n\nPer tornare — premi di nuovo questo pulsante.",
    },
    "mode_prod_on": {
        "ru": "🟢 <b>Рабочий режим включён</b>\n\nБот работает с реальными данными бюджета.",
        "uk": "🟢 <b>Робочий режим увімкнено</b>\n\nБот працює з реальними даними бюджету.",
        "en": "🟢 <b>Production mode enabled</b>\n\nBot is using real budget data.",
        "it": "🟢 <b>Modalità produzione attivata</b>\n\nIl bot usa dati reali del budget.",
    },
    # ── Transaction list (T-046) ──────────────────────────────────────────
    "txn_list_title": {
        "ru": "📝 <b>Последние {count} записей:</b>",
        "uk": "📝 <b>Останні {count} записів:</b>",
        "en": "📝 <b>Last {count} records:</b>",
        "it": "📝 <b>Ultime {count} voci:</b>",
    },
    "txn_section_expense": {
        "ru": "\n💸 <b>Расходы:</b>",
        "uk": "\n💸 <b>Витрати:</b>",
        "en": "\n💸 <b>Expenses:</b>",
        "it": "\n💸 <b>Spese:</b>",
    },
    "txn_section_income": {
        "ru": "\n💰 <b>Поступления:</b>",
        "uk": "\n💰 <b>Надходження:</b>",
        "en": "\n💰 <b>Income:</b>",
        "it": "\n💰 <b>Entrate:</b>",
    },
    # ── Inline keyboard button labels ─────────────────────────────────────────
    "btn_edit": {
        "ru": "✏ Изменить",
        "uk": "✏ Змінити",
        "en": "✏ Edit",
        "it": "✏ Modifica",
    },
    "btn_delete": {
        "ru": "🗑 Удалить",
        "uk": "🗑 Видалити",
        "en": "🗑 Delete",
        "it": "🗑 Elimina",
    },
    "btn_budget": {
        "ru": "💰 Бюджет",
        "uk": "💰 Бюджет",
        "en": "💰 Budget",
        "it": "💰 Budget",
    },
    "btn_cancel": {
        "ru": "❌ Отмена",
        "uk": "❌ Скасувати",
        "en": "❌ Cancel",
        "it": "❌ Annulla",
    },
    "btn_yes_delete": {
        "ru": "✅ Да, удалить",
        "uk": "✅ Так, видалити",
        "en": "✅ Yes, delete",
        "it": "✅ Sì, elimina",
    },
    "btn_yes_delete_rows": {
        "ru": "✅ Да, удалить строки {s}–{e}",
        "uk": "✅ Так, видалити рядки {s}–{e}",
        "en": "✅ Yes, delete rows {s}–{e}",
        "it": "✅ Sì, elimina righe {s}–{e}",
    },
}

# ── Day-of-week abbreviations (Mon/Tue/... → localized) ────────────────────────

DAY_ABBREVS: dict[str, dict[str, str]] = {
    "ru": {"Mon": "Пн", "Tue": "Вт", "Wed": "Ср", "Thu": "Чт", "Fri": "Пт", "Sat": "Сб", "Sun": "Вс"},
    "uk": {"Mon": "Пн", "Tue": "Вт", "Wed": "Ср", "Thu": "Чт", "Fri": "Пт", "Sat": "Сб", "Sun": "Нд"},
    "en": {"Mon": "Mon", "Tue": "Tue", "Wed": "Wed", "Thu": "Thu", "Fri": "Fri", "Sat": "Sat", "Sun": "Sun"},
    "it": {"Mon": "Lun", "Tue": "Mar", "Wed": "Mer", "Thu": "Gio", "Fri": "Ven", "Sat": "Sab", "Sun": "Dom"},
}


def tu(key: str, lang: str, **kwargs) -> str:
    """Translate a UI string, optionally formatting with kwargs.

    Falls back: lang → ru → en → key.
    kwargs are passed to str.format() if provided.
    """
    lg = get_lang(lang)
    tpl = (
        UI.get(key, {}).get(lg)
        or UI.get(key, {}).get("ru")
        or UI.get(key, {}).get("en")
        or key
    )
    return tpl.format(**kwargs) if kwargs else tpl


def day_abbrev(eng_day: str, lang: str) -> str:
    """Translate a 3-letter English day abbreviation (Mon/Tue/...) to lang."""
    lg = get_lang(lang)
    return DAY_ABBREVS.get(lg, DAY_ABBREVS["en"]).get(eng_day, eng_day)
