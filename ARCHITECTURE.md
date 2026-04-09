# Apolio Home — Architecture Reference

> **For Claude agents.** This document is the single source of truth for system architecture.
> Read this BEFORE making any changes. Updated: 2026-04-09.

---

## 1. System Overview

Apolio Home is a personal finance AI agent. Interface: Telegram bot. Stack: Python + Claude API + Google Sheets + PostgreSQL.

```
Telegram User
    ↕ (Telegram Bot API)
bot.py — routing, keyboards, deterministic handlers
    ↕
agent.py — Claude Sonnet, 30+ tools, agentic loop (max 5 iterations)
    ↕
tools/*.py — business logic
    ↕                  ↕
Google Sheets       PostgreSQL
(transactions,      (conversation log,
 config, users)      learning, receipts)
```

Deploy: Railway. `dev` branch → staging, `main` branch → production (auto-deploy).

---

## 2. Frontend (Telegram Bot)

### 2.1 Entry Point: bot.py

The bot uses `python-telegram-bot` library. Key handlers:

| Handler | Trigger | Function |
|---------|---------|----------|
| `/start` | Command | `cmd_start()` — welcome message + reply keyboard |
| `/report` | Command | `cmd_report()` — monthly spending report |
| Reply keyboard | "💰 Бюджет", "➕ Додати", "☰ Ще" | `handle_message()` → route by action |
| Inline buttons | `nav:*`, `cb_*` | `callback_handler()` — menu navigation, confirmations |
| Free text/photo | Any message | `handle_message()` → `agent.run()` |

### 2.2 Keyboard Architecture

Two layers:
- **Reply keyboard** (persistent, 3 buttons): Бюджет, Додати, Ще
- **Inline keyboard** (contextual, under messages): menu navigation, confirmation buttons

Menu structure defined in `menu_config.py`. Node IDs: `rep_curr`, `rep_last`, `txn_recent`, `txn_search`, `settings`, etc. Loaded from Admin BotMenu sheet, falls back to `DEFAULT_MENU`.

### 2.3 Deterministic Handlers (bypass LLM)

Critical operations are handled deterministically in bot.py — NOT routed through Claude:

| Operation | Callback | Handler |
|-----------|----------|---------|
| Receipt → add transaction | `cb_choice_yes_joint/yes_personal` | T-076 fix, calls `tool_add_transaction` directly |
| Delete confirmation | `cb_choice_confirm_delete` | BUG-008 fix, calls `tool_delete_transaction` directly |
| Delete by tx_id | `cb_del_confirm_<tx_id>` | Direct `tool_delete_transaction` call |
| Photo without buttons | BUG-010 fallback | Forces T-076 buttons if LLM skipped `present_options` |

**Why:** Claude sometimes fabricates tool results without calling tools (BUG-001 pattern). Deterministic handlers guarantee the operation actually executes.

### 2.4 Internationalization (i18n.py)

4 languages: RU, UK, EN, IT. All user-facing strings go through `i18n.ts()` / `i18n.t()` / `i18n.tu()`. Keyboard labels: `i18n.t_kb()`. Menu labels: `i18n.t_menu()`.

---

## 3. Backend (Agent + Tools)

### 3.1 Agent (agent.py)

- **Model:** Claude Sonnet (`claude-sonnet-4-20250514`)
- **Timeout:** 60s per API call
- **Max iterations:** 5 tool-use rounds per message
- **Context enrichment:** Intelligence snapshot, goals, contribution status, conversation history (last 12 turns)
- **System prompt:** Loaded from `ApolioHome_Prompt.md`

Agent loop:
1. Build enriched system prompt (intelligence, goals, contribution)
2. Load conversation history from PostgreSQL (last 12 turns)
3. Call Claude API with tools
4. If `stop_reason == "tool_use"` → execute tools → feed results back → loop
5. If `stop_reason == "end_turn"` → return text response
6. Fallback: if loop exhausts → check for errors, return summary

### 3.2 Tools (33 total)

**Transactions:**
- `add_transaction` — validates, writes to Sheets, returns tx_id
- `edit_transaction` — updates single field by tx_id
- `delete_transaction` — soft-delete (Deleted=TRUE) + parsed_data cleanup
- `find_transactions` — search by date/amount/category/note/who
- `sort_transactions` — reorder sheet rows

**Reports:**
- `get_summary` — expenses by category/who for period
- `get_budget_status` — current month: spent/cap/remaining/%
- `get_contribution_status` — who owes whom (balance model)
- `get_intelligence` — AI-generated insights snapshot

**User Management:**
- `add_authorized_user` / `remove_authorized_user`
- `update_config` — write to Admin Config
- `list_envelopes` / `create_envelope`

**Data & Learning:**
- `save_receipt` — itemized receipt → PostgreSQL parsed_data
- `get_receipt` — retrieve receipt details by tx_id
- `store_pending_receipt` — save to session for cross-message persistence
- `save_learning` — agent self-learning (corrections, vocabulary)
- `search_history` — query conversation log

**UI:**
- `present_options` — queue inline buttons for next message
- `refresh_dashboard` — update Dashboard sheet

**Reference:**
- `get_reference_data` — load categories/accounts/users before add

---

## 4. Data Layer

### 4.1 Google Sheets (primary storage)

**Admin File** (ADMIN_SHEETS_ID):

| Sheet | Purpose |
|-------|---------|
| Config | Key-value: currency, split rules, caps |
| DashboardConfig | Dashboard display settings |
| Envelopes | Budget file registry (ID, file_id, status) |
| Users | telegram_id, name, role, envelopes, language |
| Accounts | Joint / Personal payment accounts |
| BotMenu | Dynamic menu structure (optional) |
| Audit_Log | Action audit trail |
| FX_Rates | Monthly exchange rates |
| Learning | Agent learning summary |

**Budget Envelope File** (one per envelope):

| Sheet | Purpose |
|-------|---------|
| Transactions | All income/expense/transfer records |
| Categories | Valid category+subcategory list |
| Config | monthly_cap, split_rule, split_users, min contributions |
| Summary | Auto-computed monthly totals |
| Dashboard | Formatted status display |
| References | Who/Currency/Type reference lists |
| Maintenance | Sheet health checks |
| UserContext | Per-user goals and preferences |

**Transaction columns:** Date, Amount_Orig, Currency_Orig, Category, Subcategory, Note, Who, Amount_EUR, Type, Account, ID, Envelope, Source, Wise_ID, Created_At, Deleted

### 4.2 PostgreSQL (secondary storage)

7 tables. PostgreSQL is **optional** — bot works with Sheets alone, but loses learning/receipts/history.

| Table | Purpose | Key columns |
|-------|---------|-------------|
| conversation_log | Full message history | user_id, direction, raw_text, tool_called, session_id |
| parsed_data | Receipts, OCR data | user_id, data_type, payload_json, transaction_id |
| agent_learning | Self-learning records | event_type, trigger_text, learned_json, confidence |
| user_context | Goals, preferences | user_id, key, value |
| user_goals | Financial goals | goal_type, goal_text, rules_json, active |
| support_requests | User error/feedback | text, intent, status |
| ideas | User suggestions | text, tags_json, status |

**Important:** Transactions are stored ONLY in Google Sheets, NOT in PostgreSQL.

### 4.3 Caching

`SheetsCache` (sheets.py): TTL-based cache for admin reads. Default 60s. Methods: `get_envelopes()`, `get_users()`, `read_config()`, `get_dashboard_config()`, `read_envelope_config()`.

`AuthManager` (auth.py): 5-minute cache for user authorization data.

---

## 5. Authentication & Authorization

| Role | Can read | Can write | Can admin |
|------|----------|-----------|-----------|
| admin | ✓ | ✓ | ✓ |
| contributor | ✓ | ✓ | ✗ |
| readonly | ✓ | ✗ | ✗ |

Bootstrap: `MIKHAIL_TELEGRAM_ID` env var always gets admin access (even if Sheets unavailable).

Each user has assigned envelopes. Admin can access all envelopes.

---

## 6. Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| TELEGRAM_BOT_TOKEN | Yes | Bot API token |
| ADMIN_SHEETS_ID | Yes | Admin Google Sheet ID |
| GOOGLE_SERVICE_ACCOUNT | Yes | Base64 service account JSON |
| DATABASE_URL | No | PostgreSQL connection string |
| MIKHAIL_TELEGRAM_ID | No | Bootstrap admin user |
| MM_BUDGET_FILE_ID | No | Default budget (read from Admin if absent) |

---

## 7. File Map

```
apolio-home/
├── bot.py              — Telegram bot, message routing, keyboards
├── agent.py            — Claude agent, tool definitions, agentic loop
├── sheets.py           — Google Sheets client (Admin + Envelope)
├── auth.py             — AuthManager, SessionContext, LastAction
├── db.py               — PostgreSQL pool, schema, CRUD
├── intelligence.py     — Budget intelligence engine
├── i18n.py             — 4-language translations
├── menu_config.py      — Dynamic menu from BotMenu sheet
├── user_context.py     — UserContext sheet manager
├── ApolioHome_Prompt.md — Agent system prompt
├── CLAUDE_WORKING_GUIDE.md — Development guide
├── ARCHITECTURE.md     — This file
├── test_regression.py  — Regression test suite
├── setup_sheets_v2.py  — Initial Sheets setup
├── setup_admin.py      — Admin sheet bootstrap
├── tools/
│   ├── transactions.py — Add/edit/delete/find transactions
│   ├── summary.py      — Budget summaries
│   ├── envelope_tools.py — Envelope CRUD
│   ├── admin.py        — User/config management
│   ├── conversation_log.py — Message history
│   ├── receipt_store.py — DEPRECATED (PostgreSQL only now)
│   ├── goals.py        — Financial goals
│   ├── ideas.py        — User ideas
│   ├── fx.py           — Exchange rates
│   ├── wise.py         — Wise CSV import
│   ├── config_tools.py — Config updates
│   └── support.py      — Support requests
└── logs/               — Rotating log files
```

---

## 8. Known Patterns & Anti-Patterns

### Must do:
- All user-facing strings through `i18n.ts()` / `i18n.t()` — 4 languages
- Critical operations (add/delete transactions) → deterministic handlers in bot.py
- Tool errors → return `{"error": "..."}`, never crash
- New tool → add to TOOLS schema + dispatch dict + this document
- Numbers in Sheets Config → write as int/float, not string (T-120)

### Never do:
- Hardcode users / categories / accounts (always from Sheets reference data)
- Trust LLM to execute critical operations (it fabricates results — BUG-001)
- Use tx_id from conversation history for deletion (it may be fabricated — BUG-011)
- Skip `find_transactions` before delete (always verify tx_id exists)
- Leave tasks in IN PROCESS status after session ends (→ DISCUSSION)
