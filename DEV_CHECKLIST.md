# Apolio Home — Dev Checklist

Этот файл читается ПЕРЕД каждым изменением и ПОСЛЕ, до пуша.

---

## ПЕРЕД изменением

- [ ] Прочитал ВСЕ файлы, которые затронет изменение (не только очевидные)
- [ ] Понял полную цепочку: где инициализируется → где используется → где рендерится
- [ ] Проверил что нет дублирующей логики в других местах
- [ ] Описал финальное состояние (что именно должно быть после изменения)

---

## ПОСЛЕ изменения, до пуша

### Язык / i18n
- [ ] `SessionContext.lang` = `"ru"` по умолчанию (auth.py)
- [ ] `_require_user` переключает lang только на `uk`/`it`, не на `en` (bot.py)
- [ ] `callback_handler` использует ту же логику (bot.py)
- [ ] Все новые строки для пользователя — через `i18n.ts()` или `i18n.t()`, не захардкожены
- [ ] Все 4 языка (ru/uk/en/it) покрыты в новых словарях

### Клавиатура (reply keyboard)
- [ ] `_build_main_keyboard` строит 3×2: Статус/Отчёт, Записи/Добавить, Конверты/Настройки
- [ ] `is_persistent=True` присутствует
- [ ] Все 6 action-ключей есть в `KB_LABELS` для всех 4 языков
- [ ] `KB_TEXT_TO_ACTION` автоматически покрывает новые ключи (reverse map)
- [ ] Все 6 action-ов роутятся в `handle_message`

### Inline меню
- [ ] Новые пункты добавлены и в `DEFAULT_MENU`, и в `_DEFAULT_ROWS`
- [ ] `free_text` пункты имеют `pending_key` в params
- [ ] `callback_handler` обрабатывает `ntype == "free_text"` с `if pending_key:` проверкой
- [ ] Все `nav:` команды обработаны (status/report/week/envelopes/refresh/undo)

### Pending prompt flow
- [ ] `pending_prompt` в `SessionContext` (auth.py)
- [ ] В `handle_message` — `session.pending_prompt = None` сразу после чтения
- [ ] Все 3 ключа обработаны: `report:custom_period`, `transactions:search`, `transactions:category`

### Данные / Sheets
- [ ] Порядок колонок в новых записях: Date→Amount→Currency→Category→Subcategory→Note→Who→Amount_EUR→Type→Account→ID→Envelope→Source→Wise_ID→Created_At→Deleted
- [ ] Кеш инвалидируется при записи (`_cache.invalidate`)
- [ ] Ошибки конверта — на русском

### Agent / Tools
- [ ] Новые инструменты добавлены и в `TOOLS` schema, и в `dispatch` dict
- [ ] `_execute_tool` возвращает `{"error": ...}` при исключении, не падает

### Bot handlers
- [ ] Typing indicator отправляется ДО вызова агента
- [ ] `_keep_typing` task отменяется в `finally`
- [ ] `post_init` использует `hasattr` перед `set_my_menu_button`
- [ ] Новые команды зарегистрированы в `app.add_handler`

---

## Структура проекта (что где лежит)

| Файл | Зона ответственности |
|------|---------------------|
| `auth.py` | SessionContext, get_session, AuthManager |
| `bot.py` | Хэндлеры, клавиатуры, роутинг, callbacks |
| `i18n.py` | KB_LABELS, MENU_LABELS, SYS, ADD_PROMPT, START_MSG |
| `menu_config.py` | DEFAULT_MENU, _DEFAULT_ROWS, BotMenu sheet loader |
| `agent.py` | Agentic loop, tool dispatch, system prompt |
| `sheets.py` | SheetsClient, SheetsCache, AdminSheets, EnvelopeSheets |
| `tools/transactions.py` | add/edit/delete/find transaction |
| `tools/summary.py` | get_summary, get_budget_status |
| `tools/wise.py` | Wise CSV import (колонки: Date first!) |
| `tools/envelope_tools.py` | create_envelope, list_envelopes |

---

## Полная цепочка языка

```
Telegram user.language_code
    ↓
i18n.get_lang(code)  →  "ru"/"uk"/"en"/"it"
    ↓
_require_user():  только uk/it переключают, иначе → "ru"
    ↓
session.lang = "ru"  (default в SessionContext)
    ↓
_build_main_keyboard(lang)  →  i18n.t_kb(action, lang)
_build_inline_menu(lang)    →  i18n.t_menu(nid, lang)
reply_text errors           →  i18n.ts(key, lang)
```

---

## Колонки Transactions sheet

```
A: Date          B: Amount_Orig    C: Currency_Orig
D: Category      E: Subcategory    F: Note
G: Who           H: Amount_EUR     I: Type
J: Account       K: ID             L: Envelope
M: Source        N: Wise_ID        O: Created_At
P: Deleted
```

---

## После пуша

- [ ] Railway задеплоил (проверить логи — нет ошибок импорта)
- [ ] `/start` отправлен — клавиатура появилась на русском
- [ ] Если новые пункты меню — нажать ⚙️ Настройки → Обновить меню
