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
