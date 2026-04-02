# Apolio Home — Dev Checklist

Read CLAUDE_WORKING_GUIDE.md first. Then use this checklist before and after every change.

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
- [ ] Column order matches spec in CLAUDE_WORKING_GUIDE.md section 7 (A=Date … P=Deleted)
- [ ] Cache invalidated on writes (`_cache.invalidate`)
- [ ] Envelope errors return Russian-language messages
- [ ] No hardcoded category/who/account defaults — only `"Other"` for category is acceptable short-term

### Agent / Tools
- [ ] New tools added to BOTH `TOOLS` schema AND `dispatch` dict (agent.py)
- [ ] `_execute_tool` returns `{"error": ...}` on exception — never crashes
- [ ] Tool count updated in CLAUDE_WORKING_GUIDE.md section 6 when adding new tools
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

### Intelligence layer
- [ ] `_build_context()` computes intelligence_context, goals_context
- [ ] System prompt has `{intelligence_context}`, `{goals_context}`, `{conversation_context}`, `{learning_context}` placeholders
- [ ] `_load_system_prompt()` auto-appends missing placeholders
- [ ] `save_goal` and `get_intelligence` tools in TOOLS schema + dispatch dict

### Self-learning / PostgreSQL
- [ ] `DATABASE_URL` env var set in Railway
- [ ] `init_db()` called in `post_init` — logs warning (not error) if unavailable
- [ ] `log_message()` called for EVERY user + bot message
- [ ] All db functions silently swallow errors — never crash the bot
- [ ] `save_learning` tool: event_type in (vocabulary/correction/confirmation/pattern/new_category/new_user)
- [ ] Confidence rules: 0.7 initial, +0.1 confirmation, -0.3 correction, cap 0.98

### Google Sheets formulas
- [ ] Summary sheet formulas use `value_input_option="USER_ENTERED"` (not RAW)
- [ ] No `#ERROR!` / `#REF!` / `#NAME?` cells in any sheet

---

## After pushing

- [ ] Railway deployed — check logs, no import errors
- [ ] Send `/start` — reply keyboard available via toggle (not persistent), inline buttons appear
- [ ] Welcome message shows Status + Report buttons + ☰ Меню
- [ ] Send a photo without caption — bot responds (not silent)
- [ ] Send "как дела с бюджетом?" — bot responds with budget intelligence
- [ ] Check Google Sheet: UserContext, ConversationLog, Receipts tabs auto-created on first use

### Telegram button testing
- [ ] ☰ Меню → opens main menu (Status, Analytics, Records, Envelopes, System)
- [ ] Status → shows budget summary with progress bar, categories, per-person
- [ ] Analytics (Report) → shows period selector
- [ ] Envelopes → lists envelopes with links
- [ ] System (Settings) → opens settings submenu
- [ ] Settings → Language → shows 4 flags (🇷🇺 🇺🇦 🇬🇧 🇮🇹)
- [ ] Language switch → menu labels update to selected language
- [ ] ◀ Back / ◀ Назад → returns to parent menu
- [ ] Free text "coffee 3.50" → expense added, confirm/edit/delete buttons shown
- [ ] Delete button → confirmation prompt → "Да, удалить" → transaction deleted
- [ ] Free text "переключи язык на русский" → agent switches language via tool

### Config architecture (envelope-specific vs global)
- [ ] `compute_contribution_status()` reads from `sheets.read_envelope_config(file_id)` — NOT `sheets.read_config()`
- [ ] Keys in envelope Config tab are unprefixed: `split_rule`, `split_threshold`, `split_users`, `base_contributor`
- [ ] Admin Config tab has global settings only (no `split_rule_MM_BUDGET` etc.)
- [ ] `SheetsClient.read_envelope_config(file_id)` returns `{}` on error — never raises
- [ ] Each new envelope gets its own Config tab with split settings populated

### Thinking indicator
- [ ] "🏠 _думаю..._" message sent BEFORE `agent.run()`, stored as `_thinking_msg`
- [ ] Thinking message deleted in `finally` block after agent returns
- [ ] `_thinking_msg` deletion silently swallowed on error (message already deleted, etc.)
- [ ] Thinking phrase is language-aware (ru/uk/en/it variants)

### Admin config_view
- [ ] Shows active envelope name (not just ID)
- [ ] Shows Google Sheets URL with clickable link
- [ ] Shows envelope Config tab keys separately from Admin global keys
- [ ] Shows hint when envelope Config is empty (what keys to add)

---

## TESTING SCHEME — Best Practices

> Run before every deployment. Levels: L1 (static) → L5 (live E2E).

---

### L1 — Static Analysis (always, takes < 30s)

```bash
python3 -m py_compile bot.py auth.py sheets.py intelligence.py agent.py
```

- [ ] All .py files compile without SyntaxError
- [ ] `{contribution_context}` placeholder in ApolioHome_Prompt.md
- [ ] No `FINANCIAL CONTEXT` hardcode in prompt
- [ ] No hardcoded amounts (2500, 650) in prompt or intelligence.py
- [ ] `read_envelope_config` in intelligence.py (not `read_config`)
- [ ] `_thinking_msg` + `delete_message` in bot.py
- [ ] `ensure_envelope_config` in sheets.py AND bot.py
- [ ] `set_init_config` in menu_config.py
- [ ] `DEFAULT_ENVELOPE` assigned in auth.py for contributors

---

### L2 — Unit Tests (logic, no network)

- [ ] `auth._reload`: empty `telegram_id` → skipped, no crash
- [ ] `auth._reload`: `"suspended"` status → excluded from cache
- [ ] `auth._reload`: valid int ID → enters cache
- [ ] `auth._reload`: string `"219501159"` → parsed as int 219501159
- [ ] Config split: `ensure_envelope_config` writes only missing keys
- [ ] Regression math: OLS `β = (X'X)⁻¹X'y` — check with known dataset
- [ ] `_offset_month("2026-01", 2)` → `"2026-03"` (no overflow)
- [ ] `_offset_month("2026-12", 1)` → `"2027-01"` (year rollover)

---

### L3 — Integration Tests (Google Sheets live)

- [ ] Admin/Users: Mikhail (360466156) admin + active
- [ ] Admin/Users: Maryna (219501159) contributor + active + MM_BUDGET
- [ ] Admin/Users: no empty rows with blank telegram_id that could crash _reload
- [ ] Admin/Envelopes: MM_BUDGET registered with file_id
- [ ] MM_BUDGET/Config: `split_rule=50_50`, `split_threshold=2500`, `split_users=Mikhail,Maryna`, `base_contributor=Mikhail`
- [ ] MM_BUDGET/Transactions: schema has Date, Amount_EUR, Category, Who, Type, ID
- [ ] MM_BUDGET: tabs Transactions, Categories, Accounts, Config all exist
- [ ] `ensure_envelope_config(MM_BUDGET)` → skipped (all keys already present)

---

### L4 — Bot Behaviour Tests (send real messages)

**Auth / Access:**
- [ ] Mikhail `/start` → welcome message + inline buttons
- [ ] Maryna `/start` → welcome (not "access denied")
- [ ] Unknown user → "доступ запрещён"

**Thinking indicator:**
- [ ] Free text message → "🏠 _думаю..._" appears briefly, then disappears
- [ ] Long agent call → thinking message stays until response arrives

**Core flows:**
- [ ] "кофе 3.50" → agent adds expense 3.50 EUR, confirms in one line
- [ ] Photo without caption → agent lists found items, asks confirmation
- [ ] "отмени" → reverses last transaction
- [ ] "покажи статус" → budget status with progress bar
- [ ] "как дела?" → warm response (not robotic)

**Menu navigation:**
- [ ] ☰ Меню → main menu (5 items)
- [ ] Analytics → sub-menu with Report, Week, Contribution, Trends
- [ ] ⚙️ Администрирование (admin only) → sub-submenu
- [ ] ⚙️ Конфигурация → shows file name, URL, Config keys (auto-inits if needed)
- [ ] 🔧 Инит Config → shows written/skipped keys
- [ ] Language switch → bot responds in new language next message
- [ ] ◀ Back → returns to parent menu correctly

**Maryna specifically:**
- [ ] Maryna sends any message → gets response (not "access denied")
- [ ] Maryna sees own expenses only (no admin panel)
- [ ] Maryna can add transaction and view status

---

### L5 — UI/UX Quality Checks (visual + subjective)

**Response quality:**
- [ ] Confirmations are 1 line: `✓ Category · Amount EUR · Who · date`
- [ ] Reports have visual progress bars (████████)
- [ ] Thinking indicator is visible for ≥1 second before response
- [ ] Error messages are friendly Russian, no Python tracebacks
- [ ] No raw JSON in any response

**Response time:**
- [ ] Simple text message → first thinking message within 1s
- [ ] Full agent response → within 10s for simple queries

**Menu layout:**
- [ ] Buttons are single-column (no truncation)
- [ ] Back button always visible in submenus
- [ ] Admin items hidden for non-admins

---

### Automated Test Runner

```bash
# From apolio-home/ directory:
python3 tests/run_all.py
```

Tests: 48 checks across L1–L3. Results → `/tmp/test_results_latest.json`.

---

### Marina Troubleshooting Checklist

If Maryna (219501159) gets "доступ запрещён":
1. [ ] Her telegram_id = 219501159 is in Users sheet
2. [ ] Status = active (not suspended)
3. [ ] auth.py has `if not str(raw_id).strip(): continue` fix
4. [ ] Railway deployed latest main (check Railway logs for startup)
5. [ ] No other Users rows with blank telegram_id (would crash _reload for all)
6. [ ] She starts with `/start`, NOT by typing to old bot version
7. [ ] If still failing: check Railway logs for `[AuthManager] Loaded N users` — N should be 2

