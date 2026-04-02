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
- [ ] `_require_user` loads saved language from UserContext (cached via `_lang_loaded`)
- [ ] `_require_user` fallback: `uk`/`it` from Telegram → override; otherwise keep `"ru"`
- [ ] `callback_handler` uses the same language logic (bot.py)
- [ ] All new user-facing strings go through `i18n.ts()` or `i18n.t()` — never hardcoded
- [ ] All 4 languages (ru/uk/en/it) covered in any new dictionary entries
- [ ] `set_language` tool in agent.py TOOLS schema + dispatch dict
- [ ] Language saved to UserContext sheet on change (both via menu and agent)

### UI navigation (dual: reply keyboard + inline buttons)
- [ ] Reply keyboard: `is_persistent=False` — hidden by default, available via toggle icon
- [ ] `/start` sends `_build_main_keyboard(lang)` as non-persistent reply keyboard
- [ ] Welcome message followed by inline buttons (Status, Report) + ☰ Меню
- [ ] Inline navigation used for menus, settings, language switching
- [ ] `_with_menu_btn()` appends ☰ Меню row to any inline keyboard

### Inline menu
- [ ] New items added to BOTH `DEFAULT_MENU` and `_DEFAULT_ROWS` (menu_config.py)
- [ ] `free_text` items have a non-empty `pending_key` in params
- [ ] `callback_handler` handles `ntype == "free_text"` with `if pending_key:` guard
- [ ] All `nav:` commands handled: status / report / week / envelopes / refresh / undo
- [ ] Settings accessible to ALL users (`"roles": []`), not admin-only
- [ ] Language submenu: set_lang → set_lang_ru/uk/en/it (cmd: set_language)
- [ ] `set_language` command handled in `callback_handler` with UserContext persistence

### Pending prompt flow
- [ ] `pending_prompt` field exists in `SessionContext` (auth.py)
- [ ] In `handle_message`: `session.pending_prompt = None` set immediately after reading
- [ ] All 3 keys handled: `report:custom_period`, `transactions:search`, `transactions:category`

### Transactions / Sheets
- [ ] Column order for new rows: Date→Amount→Currency→Category→Subcategory→Note→Who→Amount_EUR→Type→Account→ID→Envelope→Source→Wise_ID→Created_At→Deleted
- [ ] Cache invalidated on writes (`_cache.invalidate`)
- [ ] Envelope errors return Russian-language messages
- [ ] No hardcoded category/who/account defaults — only `"Other"` for category is acceptable short-term

### Agent / Tools
- [ ] New tools added to BOTH `TOOLS` schema AND `dispatch` dict (agent.py)
- [ ] `_execute_tool` returns `{"error": ...}` on exception — never crashes
- [ ] Tool count: currently 19 — update CLAUDE_WORKING_GUIDE.md section 6 when adding new tools
- [ ] No hardcoded user/category/account lists — use `get_reference_data` tool
- [ ] `max_tokens = 4096`
- [ ] `max_iterations = 10` in agentic loop
- [ ] `save_learning` and `save_receipt` excluded from audit write (_read_only set)

### Bot handlers
- [ ] Typing indicator sent BEFORE the agent call
- [ ] `_keep_typing` task cancelled in `finally`
- [ ] `post_init` uses `hasattr` before calling `set_my_menu_button`
- [ ] New commands registered with `app.add_handler`

### Photo / media
- [ ] Photo without caption gets language-aware prompt: find ALL transactions, show findings, ask confirmation
- [ ] `_photo_prompts` dict covers ru/uk/en/it and falls back to ru
- [ ] `media_file_id = msg.photo[-1].file_id` saved to conversation_log (PostgreSQL) when photo received
- [ ] `get_recent_messages_for_api()` re-downloads photos by file_id for multimodal history (db.py)
- [ ] `save_receipt` tool called by agent after photo transaction confirmed

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
| `agent.py` | Agentic loop, tool dispatch (19 tools), system prompt with intelligence + learning context |
| `db.py` | PostgreSQL: conversation_log, sessions, agent_learning; learning context builder |
| `sheets.py` | SheetsClient, SheetsCache, AdminSheets, EnvelopeSheets |
| `intelligence.py` | IntelligenceEngine — budget snapshot, trends, anomalies for prompt injection |
| `user_context.py` | UserContextManager — goals, preferences in UserContext sheet |
| `tools/transactions.py` | add / edit / delete / find transaction |
| `tools/summary.py` | get_summary, get_budget_status |
| `tools/wise.py` | Wise CSV import (Date first in column order!) |
| `tools/envelope_tools.py` | create_envelope, list_envelopes |
| `tools/conversation_log.py` | ConversationLogger — async background writer with Queue |
| `tools/receipt_store.py` | ReceiptStore — save receipt details + AI summary |

### Files NOT to touch unless explicitly instructed
`tools/wise.py`, `tools/fx.py`, `tools/config_tools.py`, `setup_admin.py`,
`setup_sheets_v2.py`, `test_bot.py`, `encode_service_account.py`, `get_telegram_id.py`

---

## Language detection chain (3-tier)

```
1. UserContext sheet (saved preference, cached via _lang_loaded)
    ↓ if found → session.lang = saved_lang, done
2. Telegram user.language_code
    ↓
   i18n.get_lang(code)  →  "ru" / "uk" / "en" / "it"
    ↓
   _require_user():
     if lang in ("uk", "it") → session.lang = lang
     else → keep "ru" (do NOT switch to "en")
3. Default: session.lang = "ru"  (SessionContext)
    ↓
_build_inline_menu(lang)    → i18n.t_menu(nid, lang)
_with_menu_btn(lang)        → ☰ Меню / ☰ Menu button
error replies               → i18n.ts(key, lang)
_photo_prompts[lang]        → receipt analysis prompt
```

Language change flow:
- Settings → Language → select flag → `set_language` callback → UserContext.set() + session update
- Free text "switch to English" → agent calls `set_language` tool → same persistence

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

### Intelligence layer (agent.py, intelligence.py, user_context.py)
- [ ] `_build_context()` computes intelligence_context, goals_context (conversation_context = "" intentionally)
- [ ] System prompt has `{intelligence_context}`, `{goals_context}`, `{conversation_context}`, `{learning_context}` placeholders
- [ ] `_load_system_prompt()` auto-appends missing placeholders
- [ ] Lazy singletons: `_get_intelligence_engine()`, `_get_user_context_mgr()`, `_get_conv_logger()`
- [ ] `save_goal` tool in TOOLS schema + dispatch dict
- [ ] `get_intelligence` tool in TOOLS schema + dispatch dict + excluded from audit
- [ ] IntelligenceEngine.compute_snapshot returns structured dict (budget, pace, trends, anomalies)
- [ ] format_snapshot_for_prompt handles missing data / errors gracefully
- [ ] `learning_context` fetched async in `run()` via `appdb.get_learning_context_for_prompt()`
- [ ] Conversation history in `messages[]` via `appdb.get_recent_messages_for_api()` (limit=20)

### Input validation
- [ ] `get_reference_data` tool → loads categories/accounts/users/currencies from Sheets (TTL cache 60s)
- [ ] `_validate_transaction_params()` in tools/transactions.py → fuzzy-match against reference data
- [ ] `_fuzzy_suggest()` → case-insensitive substring match, returns up to 3 matches
- [ ] `force_new=true` param on `add_transaction` bypasses validation
- [ ] `category` default is `""` (not `"Other"`)

### Self-learning
- [ ] `db.py` with PostgreSQL: `conversation_log`, `sessions`, `agent_learning` tables
- [ ] `agent_learning` schema: event_type, trigger_text, learned_json, confidence, times_seen
- [ ] `save_learning` tool (event_type: vocabulary/correction/confirmation/pattern/new_category/new_user)
- [ ] Confidence: 0.7 initial, +0.1 confirmation, -0.3 correction, cap 0.98
- [ ] `get_learning_context_for_prompt()` → compact text block injected as `{learning_context}`
- [ ] Pattern detection: `check_and_save_pattern()` called async after each `add_transaction`
- [ ] `correct_learning()` reduces confidence by 0.3; removes entry if < 0.2

### PostgreSQL (db.py)
- [ ] `DATABASE_URL` env var set in Railway
- [ ] `init_db()` called in `post_init` — logs warning (not error) if unavailable
- [ ] `log_message()` called for EVERY user + bot message (before/after agent call)
- [ ] `media_file_id` stored in conversation_log for photo messages
- [ ] `get_recent_messages_for_api()` returns multimodal content blocks for photos
- [ ] All db functions silently swallow errors — never crash the bot

### Google Sheets formulas
- [ ] Summary sheet formulas use `value_input_option="USER_ENTERED"` (not RAW)
- [ ] Dashboard formulas reference Summary cells (N=Cap, O=Remaining, P=Used_%)
- [ ] Dynamic month in Dashboard B6: `=TEXT(TODAY(),"YYYY-MM")`
- [ ] No `#ERROR!` / `#REF!` / `#NAME?` cells in any sheet

---

## After pushing

- [ ] Railway deployed — check logs, no import errors
- [ ] Send `/start` — reply keyboard available via toggle (not persistent), inline buttons appear
- [ ] Welcome message shows Status + Report buttons + ☰ Меню
- [ ] Keyboard toggle icon visible on right side of input field
- [ ] Send a photo without caption — bot responds (not silent)
- [ ] Send "как дела с бюджетом?" — bot responds with budget intelligence
- [ ] If new menu items added — tap ⚙️ Settings → Refresh Menu
- [ ] Check Google Sheet: UserContext, ConversationLog, Receipts tabs auto-created on first use

### Telegram button testing
- [ ] ☰ Меню → opens main menu (Status, Analytics, Records, Envelopes, System)
- [ ] Status → shows budget summary with progress bar, categories, per-person
- [ ] Analytics (Report) → shows period selector (This month, Last month, This week, Custom)
- [ ] Records → opens records submenu
- [ ] Envelopes → lists envelopes with links
- [ ] System (Settings) → opens settings submenu
- [ ] Settings → Language → shows 4 flags (🇷🇺 🇺🇦 🇬🇧 🇮🇹)
- [ ] Language switch → menu labels update to selected language
- [ ] ◀ Back / ◀ Назад → returns to parent menu
- [ ] Free text "coffee 3.50" → expense added, confirm/edit/delete buttons shown
- [ ] Delete button → confirmation prompt → "Да, удалить" → transaction deleted
- [ ] Free text "переключи язык на русский" → agent switches language via tool
