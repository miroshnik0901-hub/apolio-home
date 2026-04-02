# Apolio Home — Claude Working Guide
# Версия: 1.2 | Актуально на: 2026-04-02

Этот документ — рабочая инструкция для Claude при работе в проекте.
Читать ПЕРЕД тем, как писать или менять любой код.

> ⚠️ Документ отражает РЕАЛЬНОЕ состояние кода. Если summary из предыдущей сессии
> противоречит этому файлу — доверять этому файлу и git log, не summary.

---

## 1. ЧТО ЭТО ЗА ПРОЕКТ

**Apolio Home** — Telegram-бот для управления семейным бюджетом Михаила Миро
(Pino Torinese, Италия). Часть продуктовой линейки Apolio.

**Пользователи:** Mikhail (admin), Marina (contributor)
**Языки:** RU / UK / EN / IT — все смешанно, в любом порядке
**Бот:** `@ApolioHomeBot`
**Деплой:** Railway (worker, polling mode, без webhook)

---

## 2. СТЕК

| Компонент | Технология |
|-----------|-----------|
| Бот | python-telegram-bot |
| AI агент | Anthropic claude-sonnet-4-20250514 |
| Транскрипция голоса | OpenAI Whisper |
| История диалогов | PostgreSQL (primary) + Google Sheets ConversationLog (fallback) |
| База данных | PostgreSQL (Railway), asyncpg |
| Таблицы | Google Sheets API (gspread) |
| Деплой | Railway (переход на Hetzner в будущем) |

---

## 3. КЛЮЧЕВЫЕ ID (ПРОДАКШН)

| Ресурс | ID |
|--------|-----|
| MM_BUDGET file_id | `1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ` |
| Admin sheet | `1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk` |
| Mikhail Telegram ID | `360466156` |

Env vars: `TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GOOGLE_SERVICE_ACCOUNT_B64`, `MM_BUDGET_FILE_ID`, `ADMIN_SHEET_ID`

---

## 4. СТРУКТУРА ФАЙЛОВ

```
bot.py              — точка входа; хендлеры, клавиатуры, роутинг, callbacks
agent.py            — агентный цикл, 19 инструментов, system prompt, context build
db.py               — PostgreSQL: conversation_log, sessions, agent_learning; learning context
sheets.py           — SheetsClient, SheetsCache, AdminSheets, EnvelopeSheets + get_reference_data
auth.py             — SessionContext, get_session, AuthManager
i18n.py             — KB_LABELS, MENU_LABELS, SYS, ADD_PROMPT, START_MSG
menu_config.py      — DEFAULT_MENU, _DEFAULT_ROWS, BotMenu sheet loader
intelligence.py     — IntelligenceEngine: снапшот бюджета, тренды, аномалии
user_context.py     — UserContextManager: цели пользователя (UserContext sheet)
ApolioHome_Prompt.md — системный промпт агента (читается при старте)
DEV_CHECKLIST.md    — чеклист ПЕРЕД и ПОСЛЕ каждого изменения
CLAUDE_WORKING_GUIDE.md — этот файл

tools/
  transactions.py   — add / edit / delete / find; _fuzzy_suggest; _validate_transaction_params
  summary.py        — get_summary, get_budget_status
  wise.py           — Wise CSV import (НЕ ТРОГАТЬ без явной инструкции)
  envelope_tools.py — create_envelope, list_envelopes
  conversation_log.py — ConversationLogger (async, Queue, Google Sheets fallback)
  receipt_store.py  — ReceiptStore (подключён: инициализируется в bot.py, save_receipt tool в agent.py)
  fx.py             — курсы валют (НЕ ТРОГАТЬ)
  config_tools.py   — конфиг бота (НЕ ТРОГАТЬ)
```

**Файлы, которые НЕЛЬЗЯ трогать без явной инструкции:**
`tools/wise.py`, `tools/fx.py`, `tools/config_tools.py`,
`setup_admin.py`, `setup_sheets_v2.py`, `test_bot.py`,
`encode_service_account.py`, `get_telegram_id.py`

---

## 5. АРХИТЕКТУРА АГЕНТА

### Как формируется контекст (agent.py → `_build_context()`)

```
System Prompt = ApolioHome_Prompt.md
              + {intelligence_context}   ← budget snapshot, trends, anomalies
              + {goals_context}          ← цели пользователя (UserContext sheet)
              + {conversation_context}   ← последние N сообщений (Google Sheets ConversationLog)
```

Всё это собирается в `_build_context()` перед каждым вызовом Claude API.

### Conversation history

**PostgreSQL (primary):** `db.log_message()` → `conversation_log` table.
`db.get_recent_messages_for_api()` → возвращает последние 20 сообщений как `messages[]`.
Для фото с `media_file_id` — скачивает повторно через `telegram_bot.get_file(file_id)` и
включает как base64 image block → Claude видит фото из истории.

**Google Sheets (fallback):** `ConversationLogger` → `ConversationLog` tab в MM_BUDGET.
Используется если PostgreSQL недоступен (но в messages[] не попадает).

### Агентный цикл

```python
max_iterations = 10       # ← именно 10
max_tokens = 4096         # ← 4096 (нужно для фото в истории)
model = "claude-sonnet-4-20250514"
```

```
1. _build_context() → system prompt
2. messages = [{"role": "user", "content": user_content}]  # только текущее сообщение
3. Claude API call (tools enabled)
4. Tool dispatch → execute → tool_result
5. Если ещё tool_calls → repeat (до 5 итераций)
6. Финальный ответ → пользователю
7. Write-only tools логируются через write_audit() в sheets
```

### Фото

```python
# bot.py — текущая реализация
if msg.photo:
    file_obj = await msg.photo[-1].get_file()
    media_data = await file_obj.download_as_bytearray()
    _photo_prompts = {
        "ru": "...",  "uk": "...",  "en": "...",  "it": "..."
    }
    text = msg.caption or _photo_prompts.get(lang, _photo_prompts["en"])
    media_type = "photo"
```

Фото передаётся в Claude только для ТЕКУЩЕГО сообщения.
`media_file_id` (Telegram file_id для повторной загрузки) — **НЕ сохраняется**.

---

## 6. ИНСТРУМЕНТЫ АГЕНТА (19 штук)

| # | Инструмент | Описание |
|---|-----------|---------|
| 1 | `add_transaction` | Добавить транзакцию; с валидацией по справочнику; `force_new` обходит |
| 2 | `edit_transaction` | Изменить поле по ID |
| 3 | `delete_transaction` | Soft-delete (Deleted=TRUE); 2-шаговый подтверждение |
| 4 | `delete_transaction_rows` | Физическое удаление строк (2-шаговый!) |
| 5 | `find_transactions` | Поиск по фильтрам |
| 6 | `get_summary` | Агрегированный отчёт |
| 7 | `get_budget_status` | Снапшот текущего месяца |
| 8 | `import_wise_csv` | Импорт Wise CSV |
| 9 | `set_fx_rate` | Курс валюты (admin) |
| 10 | `update_config` | Конфиг (admin) |
| 11 | `add_authorized_user` | Добавить пользователя (admin) |
| 12 | `remove_authorized_user` | Удалить пользователя (admin) |
| 13 | `list_envelopes` | Список конвертов |
| 14 | `create_envelope` | Создать конверт (admin) |
| 15 | `save_goal` | Сохранить финансовую цель |
| 16 | `get_intelligence` | Анализ трендов, аномалий, прогноз |
| 17 | `get_reference_data` | Справочники: категории / счета / юзеры / валюты (TTL cache 60s) |
| 18 | `save_receipt` | Сохранить данные чека в Receipts tab после фото транзакции |
| 19 | `save_learning` | Записать обучающее событие в agent_learning (PostgreSQL) |

**Правило:** новый инструмент добавляется В ОБА места: `TOOLS` schema + `dispatch` dict.

---

## 7. GOOGLE SHEETS — СТРУКТУРА

### Admin sheet (отдельный файл)
Вкладки: `Config`, `Users`, `Envelopes`, `FX_Rates`, `UserContext`

- **Users** → список авторизованных пользователей с ролями
- **Envelopes** → список конвертов: `ID`, `name`, `file_id`, `monthly_cap`, `currency`
- **FX_Rates** → курсы по месяцам (заголовки = валюты)
- **UserContext** → цели и языковые предпочтения пользователей

### MM_BUDGET и каждый конверт (отдельные файлы)
Вкладки: `Transactions`, `Summary`, `Dashboard`, `Categories`, `Accounts`,
`ConversationLog`, `Receipts` (создаётся при первом использовании)

### Порядок колонок Transactions (СТРОГО СОБЛЮДАТЬ)
```
A: Date       B: Amount_Orig  C: Currency_Orig
D: Category   E: Subcategory  F: Note
G: Who        H: Amount_EUR   I: Type
J: Account    K: ID           L: Envelope
M: Source     N: Wise_ID      O: Created_At
P: Deleted
```
Колонки A–G — редактируемые пользователем. H–P — автоматические.

---

## 8. ОСТАВШИЙСЯ BACKLOG

| Фича | Описание | Статус |
|------|---------|--------|
| **Railway: DATABASE_URL** | Проверить что PostgreSQL подключён и env var выставлен | ❌ Требует деплоя |
| **refresh_learning_summary** | Tool: записать сводку из agent_learning в Admin Learning tab | ❌ Не реализован |
| **Тесты на Railway** | Пройти After pushing checklist — кнопки, фото, история | ❌ Требует деплоя |

---

## 9. ПРАВИЛА РАБОТЫ

### Перед любым изменением
1. Прочитать ВСЕ файлы, которых касается изменение (не только очевидные)
2. Проверить: не дублирует ли логику что-то уже существующее
3. Пройти DEV_CHECKLIST.md для соответствующего раздела
4. Сформулировать: что именно должно быть правдой после изменения

### Хардкод — ЗАПРЕЩЁН
- Имена пользователей → не хардкодить `["Mikhail", "Marina"]`
- Категории → не хардкодить список категорий
- Счета → не хардкодить список счетов
- Все эти данные должны идти из Google Sheets справочников

### Ошибки и исключения
- Tool errors → `{"error": "..."}` — агент никогда не падает
- Пользователю → friendly message на его языке, без traceback
- Logger → `logger.warning(...)` или `logger.error(...)`

### После изменения
1. Пройти DEV_CHECKLIST.md для затронутых разделов
2. Push → проверить Railway logs (нет import errors, нет traceback)
3. Обновить этот файл если изменилась архитектура

---

## 10. ЯЗЫКОВАЯ ЛОГИКА (3 уровня)

```
1. UserContext sheet (сохранённый выбор) → наивысший приоритет
2. Telegram user.language_code
   → "uk" или "it" → использовать
   → любой другой → оставить "ru" (НЕ переключаться на "en")
3. По умолчанию: "ru"
```

Все строки через `i18n.ts(key, lang)` или `i18n.t(key, lang)`.
Новые строки → добавлять во все 4 словаря (ru/uk/en/it).

---

## 11. GIT WORKFLOW

```bash
# Проверить реальное состояние кода
git log --oneline -5
git status

# После изменений — добавлять конкретные файлы, не всё сразу
git add bot.py agent.py tools/transactions.py  # конкретно
git commit -m "краткое описание"
git push
# Railway деплоит автоматически после push в main
```

> ⚠️ Если context summary из предыдущей сессии описывает коммит которого нет в git log —
> значит те изменения не были сохранены. Проверяй git log, не summary.

---

## 12. КАК ОБНОВЛЯТЬ ЭТОТ ФАЙЛ

Обновить после любого из событий:
- Новый инструмент добавлен → раздел 6
- Новый файл создан → раздел 4
- Архитектурное изменение → разделы 5, 7
- Backlog-фича реализована → убрать из раздела 8 и добавить в соответствующий раздел
- Изменились ID или env vars → раздел 3
