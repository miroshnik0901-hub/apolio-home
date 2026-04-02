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

### Agent / Tools
- [ ] New tools added to BOTH `TOOLS` schema AND `dispatch` dict (agent.py)
- [ ] `_execute_tool` returns `{"error": ...}` on exception — never crashes

### Bot handlers
- [ ] Typing indicator sent BEFORE the agent call
- [ ] `_keep_typing` task cancelled in `finally`
- [ ] `post_init` uses `hasattr` before calling `set_my_menu_button`
- [ ] New commands registered with `app.add_handler`

### Photo / media
- [ ] Photo without caption gets a language-aware default prompt that says "extract ALL transactions, use exact dates from image"
- [ ] `_photo_prompts` dict covers ru/uk/en/it and falls back to en
- [ ] `media_file_id = msg.photo[-1].file_id` extracted and passed to `appdb.log_message()`
- [ ] Photo without caption: Claude performs auto-analysis, returns findings + asks for confirmation before writing
- [ ] Photo WITH explicit action caption (e.g. "запиши взнос"): Claude executes directly
- [ ] `telegram_bot=ctx.bot` passed to `agent.run()` for all message types

### Conversation logging (PostgreSQL via db.py)
- [ ] `appdb.init_db()` called in `post_init` — creates tables if needed
- [ ] Graceful degradation: if no `DATABASE_URL`, logs warning and disables (no crash)
- [ ] `session.session_id` assigned on first message in `handle_message`
- [ ] User message logged BEFORE agent call via `appdb.log_message(direction="user")`
- [ ] For photo messages: `media_file_id` (Telegram file_id) saved to `conversation_log`
- [ ] Bot final response logged AFTER agent call via `appdb.log_message(direction="bot")`
- [ ] Tool calls (write-only: add/edit/delete/set_fx etc.) logged as `direction="bot", message_type="tool"` inside agentic loop — skip read-only tools (get_summary, find_transactions, etc.)
- [ ] Logging exceptions are silently swallowed — must never crash the bot
- [ ] User goals: `appdb.ctx_get_all()` with fallback to Google Sheets `UserContextManager`
- [ ] `save_goal` tool: writes to PostgreSQL via `appdb.ctx_set()` (fallback to Sheets)

### Contribution & Split Rules (intelligence.py, tools/summary.py, agent.py)
- [x] Config keys written to Admin sheet: split_rule_*, split_threshold_*, split_users_*, base_contributor_*
- [x] `compute_contribution_status()` in intelligence.py reads Config keys, falls back to Monthly_Cap
- [x] `format_contribution_for_prompt()` returns compact text block; returns "" on error
- [x] `tool_get_contribution_status` in tools/summary.py — permission-checked, async
- [x] Tool registered in agent.py TOOLS schema + dispatch dict
- [x] Tool excluded from audit log (`get_contribution_status` in the no-audit list)
- [x] `_build_context()` includes step 4: contribution_context via compute_contribution_status()
- [x] `{contribution_context}` placeholder in FALLBACK_PROMPT and ApolioHome_Prompt.md
- [x] system prompt `format()` call passes `contribution_context=` kwarg
- [ ] If split_rule == "solo" or split_users empty → solo mode, no split shown (handled in compute)
- [x] Threshold from Config; fallback to Monthly_Cap if config key missing
- [x] Balance = contributed − share (positive = credit, negative = owes)

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
| `agent.py` | Agentic loop, tool dispatch (17 tools), system prompt with intelligence context |
| `sheets.py` | SheetsClient, SheetsCache, AdminSheets, EnvelopeSheets |
| `intelligence.py` | IntelligenceEngine — budget snapshot, trends, anomalies for prompt injection |
| `user_context.py` | UserContextManager — goals, preferences in UserContext sheet |
| `tools/transactions.py` | add / edit / delete / find transaction |
| `tools/summary.py` | get_summary, get_budget_status |
| `tools/wise.py` | Wise CSV import (Date first in column order!) |
| `tools/envelope_tools.py` | create_envelope, list_envelopes |
| `db.py` | PostgreSQL layer — conversation_log + user_context tables (asyncpg) |
| `tools/conversation_log.py` | DEPRECATED — Google Sheets logger, kept for make_session_id() |
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

### Data architecture
- **PostgreSQL (Railway):** `conversation_log`, `user_context` — history, goals, patterns, preferences
- **Google Sheets:** transactions, budgets, summary formulas, receipts — human-accessible
- `db.py` handles all PostgreSQL operations (async via asyncpg)
- `sheets.py` handles all Google Sheets operations (sync via gspread)
- Intelligence engine reads from Sheets (transaction data), user context from PostgreSQL

### Intelligence layer / Context architecture
Two-layer context model (do NOT mix them):
- **Layer 1 — System prompt:** static derived data — intelligence snapshot, goals, contribution status
  `{intelligence_context}`, `{goals_context}`, `{contribution_context}` placeholders
- **Layer 2 — messages[] array:** actual conversation history from PostgreSQL, passed as proper
  role/content turns by `get_recent_messages_for_api()`. Photo messages with `media_file_id`
  are re-downloaded from Telegram and included as base64 images.
- `{conversation_context}` placeholder is intentionally empty — history is in messages[], not here

Checks:
- [ ] `_build_context()` returns `conversation_context=""` — intentional, NOT a bug
- [ ] System prompt template has `{intelligence_context}`, `{goals_context}`, `{contribution_context}`
- [ ] `get_recent_messages_for_api(telegram_bot=bot)` called with bot instance for image memory
- [ ] History starts with a user turn (drops leading assistant turns)
- [ ] History size: n_turns=6 turns (≈12 rows), max_tokens=4096
- [ ] Lazy singletons: `_get_intelligence_engine()`, `_get_user_context_mgr()`, `_get_conv_logger()`
- [ ] `save_goal` tool in TOOLS schema + dispatch dict
- [ ] `get_intelligence` tool in TOOLS schema + dispatch dict + excluded from audit
- [ ] IntelligenceEngine.compute_snapshot returns structured dict (budget, pace, trends, anomalies)
- [ ] format_snapshot_for_prompt handles missing data / errors gracefully

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
- [ ] Check Railway logs: `[DB] PostgreSQL connected, tables ready`
- [ ] Send 2+ messages → check PostgreSQL `conversation_log` table has rows
- [ ] Check Google Sheet: Receipts tab auto-created on first use (transactions stay in Sheets)

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

### PostgreSQL testing (requires Railway DATABASE_URL)
- [ ] Test 1: Graceful degradation without DATABASE_URL — all ops no-op, no crash ✅ PASSED
- [ ] Test 2: format_context_for_prompt renders mock conversation correctly ✅ PASSED
- [ ] Test 3: Google Sheets connection works (transactions, envelopes) ✅ PASSED
- [ ] Test 4: IntelligenceEngine computes snapshot from Sheets ✅ PASSED
- [ ] Test 5: System prompt template has all placeholders + CONVERSATION MEMORY section ✅ PASSED
- [ ] Test 6: agent._build_context() async — intelligence from Sheets, empty conv without DB ✅ PASSED
- [ ] Test 7: LIVE — PostgreSQL tables created on Railway deploy (check logs)
- [ ] Test 8: LIVE — Send message → conversation_log row appears
- [ ] Test 9: LIVE — Send 2nd message → agent system prompt includes history
- [ ] Test 10: LIVE — Bot does NOT say "I don't remember" anymore
- [ ] Test 11: LIVE — save_goal tool writes to user_context table
- [ ] Test 12: LIVE — Google Sheets transactions still work after PostgreSQL migration
