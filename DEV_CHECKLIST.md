# Apolio Home — Dev Checklist

Read this file BEFORE making any change. Check everything AFTER the change, before pushing.

---

## BEFORE making a change

- [ ] Read ALL files the change touches (not just the obvious ones)
- [ ] Traced the full chain: where it's initialized → where it's used → where it renders
- [ ] Checked for duplicate logic elsewhere
- [ ] Stated the target end-state (exactly what should be true after the change)

---

## AFTER the change, before pushing

### Language / i18n
- [ ] `SessionContext.lang` defaults to `"ru"` (auth.py)
- [ ] `_require_user` overrides lang ONLY for `uk`/`it` — NOT for `en` (bot.py)
- [ ] `callback_handler` uses the same language logic (bot.py)
- [ ] All new user-facing strings go through `i18n.ts()` or `i18n.t()` — never hardcoded
- [ ] All 4 languages (ru/uk/en/it) covered in any new dictionary entries

### Reply keyboard
- [ ] `_build_main_keyboard` builds 3×2: Status/Report, Records/Add, Envelopes/Settings
- [ ] `is_persistent=True` present
- [ ] All 6 action keys exist in `KB_LABELS` for all 4 languages
- [ ] `KB_TEXT_TO_ACTION` reverse map auto-covers new keys (no manual update needed)
- [ ] All 6 actions routed in `handle_message`

### Inline menu
- [ ] New items added to BOTH `DEFAULT_MENU` and `_DEFAULT_ROWS` (menu_config.py)
- [ ] `free_text` items have a non-empty `pending_key` in params
- [ ] `callback_handler` handles `ntype == "free_text"` with `if pending_key:` guard
- [ ] All `nav:` commands handled: status / report / week / envelopes / refresh / undo

### Pending prompt flow
- [ ] `pending_prompt` field exists in `SessionContext` (auth.py)
- [ ] In `handle_message`: `session.pending_prompt = None` set immediately after reading
- [ ] All 3 keys handled: `report:custom_period`, `transactions:search`, `transactions:category`

### Transactions / Sheets
- [ ] Column order for new rows: Date→Amount→Currency→Category→Subcategory→Note→Who→Amount_EUR→Type→Account→ID→Envelope→Source→Wise_ID→Created_At→Deleted
- [ ] Cache invalidated on writes (`_cache.invalidate`)
- [ ] Envelope errors return Russian-language messages

### Agent / Tools
- [ ] New tools added to BOTH `TOOLS` schema AND `dispatch` dict (agent.py)
- [ ] `_execute_tool` returns `{"error": ...}` on exception — never crashes

### Bot handlers
- [ ] Typing indicator sent BEFORE the agent call
- [ ] `_keep_typing` task cancelled in `finally`
- [ ] `post_init` uses `hasattr` before calling `set_my_menu_button`
- [ ] New commands registered with `app.add_handler`

### Photo / media
- [ ] Photo without caption gets a language-aware default receipt prompt (not empty string)
- [ ] `_photo_prompts` dict covers ru/uk/en/it and falls back to ru

### Conversation logging
- [ ] `ConversationLogger` started in `post_init` (non-blocking)
- [ ] `session.session_id` assigned on first message in `handle_message`
- [ ] User message logged BEFORE agent call (so it's always recorded even if agent crashes)
- [ ] Bot response logged AFTER agent call
- [ ] Logging exceptions are silently swallowed — must never crash the bot

### Receipt storage (tools/receipt_store.py)
- [ ] `ReceiptStore` creates Receipts sheet on first use if not present
- [ ] Receipt saved after photo analysis confirmation
- [ ] `items_json` contains list of `{name, amount, category}` objects
- [ ] `ai_summary` is human-readable one-liner (Mikhail's style: "Esselunga weekly shop, 12 items")

---

## Project structure

| File | Responsibility |
|------|----------------|
| `auth.py` | SessionContext, get_session, AuthManager |
| `bot.py` | Handlers, keyboards, routing, callbacks |
| `i18n.py` | KB_LABELS, MENU_LABELS, SYS, ADD_PROMPT, START_MSG |
| `menu_config.py` | DEFAULT_MENU, _DEFAULT_ROWS, BotMenu sheet loader |
| `agent.py` | Agentic loop, tool dispatch, system prompt |
| `sheets.py` | SheetsClient, SheetsCache, AdminSheets, EnvelopeSheets |
| `tools/transactions.py` | add / edit / delete / find transaction |
| `tools/summary.py` | get_summary, get_budget_status |
| `tools/wise.py` | Wise CSV import (Date first in column order!) |
| `tools/envelope_tools.py` | create_envelope, list_envelopes |

### Files NOT to touch unless explicitly instructed
`tools/wise.py`, `tools/fx.py`, `tools/config_tools.py`, `setup_admin.py`,
`test_bot.py`, `encode_service_account.py`, `get_telegram_id.py`

---

## Language detection chain

```
Telegram user.language_code
    ↓
i18n.get_lang(code)  →  "ru" / "uk" / "en" / "it"
    ↓
_require_user():
  if lang in ("uk", "it") → session.lang = lang
  else → keep "ru" (do NOT switch to "en")
    ↓
session.lang = "ru"  (default in SessionContext)
    ↓
_build_main_keyboard(lang)  → i18n.t_kb(action, lang)
_build_inline_menu(lang)    → i18n.t_menu(nid, lang)
error replies               → i18n.ts(key, lang)
_photo_prompts[lang]        → receipt analysis prompt
```

---

## Transactions sheet column order

```
A: Date          B: Amount_Orig    C: Currency_Orig
D: Category      E: Subcategory    F: Note
G: Who           H: Amount_EUR     I: Type
J: Account       K: ID             L: Envelope
M: Source        N: Wise_ID        O: Created_At
P: Deleted
```

Columns A–G are user-editable. H–P are auto-filled by the bot or by Sheet formulas.

---

## Key IDs (production)

| Resource | ID |
|----------|-----|
| MM_BUDGET file_id | `1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ` |
| Admin sheet | `1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk` |
| Mikhail Telegram ID | `360466156` |
| Bot | `@ApolioHomeBot` |
| Deployment | Railway (worker, polling mode) |

---

## After pushing

- [ ] Railway deployed — check logs, no import errors
- [ ] Send `/start` — keyboard appears in Russian
- [ ] Send a photo without caption — bot responds (not silent)
- [ ] If new menu items added — tap ⚙️ Settings → Refresh Menu
