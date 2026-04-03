# Apolio Home — Claude Working Guide
# Version: 1.4 | Updated: 2026-04-03

This document is the technical reference for Claude when working on this project.
Read it BEFORE writing or modifying any code.

> ⚠️ This document reflects the ACTUAL state of the code. If a previous session summary
> contradicts this file — trust this file and git log, not the summary.

---

## 1. WHAT THIS PROJECT IS

**Apolio Home** is a personal AI agent for Mikhail Miro (Pino Torinese, Italy).
Part of the Apolio product family. Current interface: Telegram (@ApolioHomeBot).

**Users:** Mikhail (admin), Marina (contributor)
**Languages:** RU / UK / EN / IT — mixed freely, in any order
**Deploy:** Railway (worker, polling mode, no webhook)

---

## 2. STACK

| Component | Technology |
|-----------|-----------|
| Interface | python-telegram-bot |
| AI agent | Anthropic claude-sonnet-4-20250514 |
| Voice transcription | OpenAI Whisper |
| Conversation history | PostgreSQL (primary) + Google Sheets ConversationLog (fallback) |
| Database | PostgreSQL (Railway), asyncpg |
| Spreadsheets | Google Sheets API (gspread) |
| Deploy | Railway (migration to Hetzner planned) |

---

## 3. PRODUCTION IDs

| Resource | ID |
|----------|-----|
| MM_BUDGET file_id | `1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ` |
| Admin sheet | `1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk` |
| Test Budget file_id | `196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788` |
| Test Admin sheet | `1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM` |
| Task Log sheet | `1Un1IHa6ScwZZPhAvSd3w5q31LU_JmeEuATPZZvSkZb4` |
| Mikhail Telegram ID | `360466156` |
| Railway project ID | `55240cdd-2cbc-4451-b6c9-ca97ce595c18` |
| Railway service ID (bot) | `8ec97839-6d49-4cdd-a012-1f6d54853454` |
| Railway production env ID | `08e40bf3-cbe4-4a80-be54-1f291c21fe0d` |
| Railway staging env ID | `1e6973d7-2c9c-48a3-8197-b61fd4174ba4` |
| @ApolioHomeTestBot token | `8298458285:AAHm8doTLplljbrErzCo9FAMhhwnhvamaP8` |

Env vars: `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GOOGLE_SERVICE_ACCOUNT`, `ADMIN_SHEETS_ID`, `DATABASE_URL`,
`MM_TEST_FILE_ID` (optional, for test mode)

---

## 4. FILE STRUCTURE

```
bot.py              — entry point; handlers, keyboards, routing, callbacks
agent.py            — agentic loop, 20 tools, system prompt, context build
db.py               — PostgreSQL: conversation_log, sessions, agent_learning; learning context
sheets.py           — SheetsClient, SheetsCache, AdminSheets, EnvelopeSheets + get_reference_data
auth.py             — SessionContext, get_session, AuthManager
i18n.py             — KB_LABELS, MENU_LABELS, SYS, ADD_PROMPT, START_MSG
menu_config.py      — DEFAULT_MENU, _DEFAULT_ROWS, BotMenu sheet loader
intelligence.py     — IntelligenceEngine: budget snapshot, trends, anomalies
user_context.py     — UserContextManager: user goals (UserContext sheet)
ApolioHome_Prompt.md — agent system prompt (read at startup)
DEV_CHECKLIST.md    — checklist BEFORE and AFTER every change
CLAUDE_WORKING_GUIDE.md — this file

tools/
  transactions.py   — add / edit / delete / find; _fuzzy_suggest; _validate_transaction_params
  summary.py        — get_summary, get_budget_status
  wise.py           — Wise CSV import (DO NOT TOUCH without explicit instruction)
  envelope_tools.py — create_envelope, list_envelopes
  conversation_log.py — ConversationLogger (async, Queue, Google Sheets fallback)
  receipt_store.py  — ReceiptStore (initialized in bot.py, save_receipt tool in agent.py)
  fx.py             — exchange rates (DO NOT TOUCH)
  config_tools.py   — bot config (DO NOT TOUCH)
```

**Files NOT to touch without explicit instruction:**
`tools/wise.py`, `tools/fx.py`, `tools/config_tools.py`,
`setup_admin.py`, `setup_sheets_v2.py`, `test_bot.py`,
`encode_service_account.py`, `get_telegram_id.py`

---

## 5. AGENT ARCHITECTURE

### How context is built (agent.py → `_build_context()`)

```
System Prompt = ApolioHome_Prompt.md
              + {intelligence_context}   ← budget snapshot, trends, anomalies
              + {goals_context}          ← user goals (UserContext sheet)
              + {learning_context}       ← learned patterns from agent_learning
              + {conversation_context}   ← recent N messages (Google Sheets ConversationLog)
```

All assembled in `_build_context()` before every Claude API call.

### Conversation history

**PostgreSQL (primary):** `db.log_message()` → `conversation_log` table.
`db.get_recent_messages_for_api()` → returns last 20 messages as `messages[]`.
For photos with `media_file_id` — re-downloads via `telegram_bot.get_file(file_id)` and
includes as base64 image block → Claude sees photos from history.

**Google Sheets (fallback):** `ConversationLogger` → `ConversationLog` tab in MM_BUDGET.
Used if PostgreSQL is unavailable (but does not appear in messages[]).

### Agentic loop

```python
max_iterations = 10
max_tokens = 4096
model = "claude-sonnet-4-20250514"
```

```
1. _build_context() → system prompt
2. messages = [{"role": "user", "content": user_content}]
3. Claude API call (tools enabled)
4. Tool dispatch → execute → tool_result
5. If more tool_calls → repeat (up to 10 iterations)
6. Final response → user
7. Write-only tools logged via write_audit() in sheets
```

### Photo handling

```python
if msg.photo:
    file_obj = await msg.photo[-1].get_file()
    media_data = await file_obj.download_as_bytearray()
    _photo_prompts = {
        "ru": "...",  "uk": "...",  "en": "...",  "it": "..."
    }
    text = msg.caption or _photo_prompts.get(lang, _photo_prompts["en"])
    media_type = "photo"
```

Photo passed to Claude for the CURRENT message only.
`media_file_id` (Telegram file_id for re-download) is saved to conversation_log.

---

## 6. AGENT TOOLS (26 total)

| # | Tool | Description |
|---|------|-------------|
| 1 | `add_transaction` | Add transaction; validated against reference data; `force_new` bypasses |
| 2 | `edit_transaction` | Edit a field by ID |
| 3 | `delete_transaction` | Soft-delete (Deleted=TRUE); 2-step confirmation |
| 4 | `delete_transaction_rows` | Physical row deletion (2-step!) |
| 5 | `sort_transactions` | Sort Transactions tab by date |
| 6 | `find_transactions` | Search by filters |
| 7 | `get_summary` | Aggregated report |
| 8 | `get_budget_status` | Current month snapshot |
| 9 | `import_wise_csv` | Import Wise CSV |
| 10 | `set_fx_rate` | Exchange rate (admin) |
| 11 | `update_config` | Config (admin) |
| 12 | `add_authorized_user` | Add user (admin) |
| 13 | `remove_authorized_user` | Remove user (admin) |
| 14 | `list_envelopes` | List envelopes |
| 15 | `create_envelope` | Create envelope (**contributor or admin**; clones Categories/Accounts from master template) |
| 16 | `search_history` | Search conversation history in PostgreSQL |
| 17 | `save_goal` | Save financial goal |
| 18 | `get_intelligence` | Trends, anomalies, forecast analysis |
| 19 | `get_contribution_status` | Household split contribution status |
| 20 | `refresh_dashboard` | Write Dashboard tab from budget snapshot + config |
| 21 | `save_receipt` | Save receipt data to Receipts tab after photo transaction confirmed |
| 22 | `save_learning` | Write learning event to agent_learning (PostgreSQL) |
| 23 | `refresh_learning_summary` | Write agent_learning summary to Admin sheet Learning tab |
| 24 | `get_reference_data` | Reference data: categories / accounts / users / currencies (TTL cache 60s) |
| 25 | `update_dashboard_config` | Update DashboardConfig in Admin sheet (history months, mode, etc.) |
| 26 | `present_options` | Store inline choice buttons to attach to next bot message |

**Rule:** a new tool must be added to BOTH `TOOLS` schema AND `dispatch` dict.

---

## 7. GOOGLE SHEETS STRUCTURE

### Admin sheet (separate file)
Tabs: `Config`, `Users`, `Envelopes`, `FX_Rates`, `UserContext`, `DashboardConfig`, `Learning`

- **Users** → list of authorized users with roles (`admin` / `contributor` / `readonly`)
- **Envelopes** → envelope list: `ID`, `name`, `file_id`, `monthly_cap`, `currency`
- **FX_Rates** → exchange rates by month (headers = currencies)
- **UserContext** → user goals and language preferences
- **DashboardConfig** → key-value dashboard settings (created on first `update_dashboard_config` call):
  - `auto_refresh_on_transaction` — TRUE/FALSE
  - `show_contribution_history` — TRUE/FALSE
  - `history_months` — number (default 3)
  - `budget_warning_pct` — number (default 80)
  - `master_template_id` — file ID of master template (empty = MM_BUDGET_FILE_ID)
  - `mode` — `prod` or `test`
  - `test_file_id` — file ID for test mode
- **Learning** → dumped by `refresh_learning_summary` tool

### MM_BUDGET and each envelope (separate files)
Tabs: `Transactions`, `Summary`, `Dashboard`, `Categories`, `Accounts`,
`ConversationLog`, `Receipts` (created on first use)

### Envelope Config tab — per-user contribution model

Each envelope has its own `Config` tab (key-value). Keys:

| Key | Example | Description |
|-----|---------|-------------|
| `split_rule` | `per_user` | `per_user` (new) or `50_50` / `solo` (legacy) |
| `split_threshold` | `2500` | Legacy threshold (not used in per_user mode) |
| `split_users` | `Mikhail,Maryna` | Comma-separated list of users in split |
| `base_contributor` | `Mikhail` | Legacy base contributor |
| `monthly_cap` | `5000` | Monthly budget cap |
| `currency` | `EUR` | Budget currency |
| `min_<user>` | `min_Mikhail=2500` | Monthly minimum contribution per user |
| `split_<user>` | `split_Mikhail=50` | % share of overflow expenses per user |

**Obligation formula (per-user model):**
```
total_min_pool = sum(min_<user> for all users)
overflow = max(0, total_expenses - total_min_pool)
obligation_user = (expenses * user_min / total_min_pool) + overflow * split_user%
```

**Auto-init:** `ensure_envelope_config(file_id)` writes missing keys on first use.
It reads active users from Admin/Users and sets `min_<user>=0` (non-admin) or threshold (admin), `split_<user>=50/N`.

**Detection in intelligence.py:** If any `min_<user>` key exists in Config → per-user model.
Otherwise falls back to legacy `split_rule` model.

**Dashboard tab:** Formulas use `LET()` + `VLOOKUP(Config)` to pull min/split values live.
No Python needed for display — agent reads from Dashboard or computes via `get_contribution_status`.

### Transactions column order (STRICTLY FOLLOW)
```
A: Date       B: Amount_Orig  C: Currency_Orig
D: Category   E: Subcategory  F: Note
G: Who        H: Amount_EUR   I: Type
J: Account    K: ID           L: Envelope
M: Source     N: Wise_ID      O: Created_At
P: Deleted
```
Columns A–G are user-editable. H–P are automatic.

---

## 8. TASK LOG WORKFLOW

**File:** `Apolio Home — Task Log` (ID: `1Un1IHa6ScwZZPhAvSd3w5q31LU_JmeEuATPZZvSkZb4`)
**Shared with:** `apolio-home-bot@apolio-home.iam.gserviceaccount.com` (Editor)

Columns: `ID | Date | Task | Status | AI Comment | Branch | Resolved At`

Status values: `OPEN` → `IN_PROGRESS` → `DONE`

### How it works
1. **On-demand:** Mikhail says "go check the task log" → Claude reads all OPEN rows,
   processes each task, writes AI Comment + updates Status, sets Branch where applicable.
2. **Daily morning check (automated):** Scheduled task runs every morning, reads all OPEN rows,
   processes them the same way.

### Claude's behavior when checking Task Log
- Read all rows where Status = `OPEN`
- For each: write a comment in `AI Comment` column (what was done / what I think / blockers)
- Change Status to `IN_PROGRESS` while working, `DONE` when complete
- Fill `Branch` if code was pushed, `Resolved At` when done

---

## 9. BACKLOG

| Feature | Description | Status |
|---------|-------------|--------|
| **Post-deploy tests** | Run After pushing checklist — buttons, photo, history | ❌ Not verified |
| **Hetzner migration** | Move deployment from Railway to Hetzner | 🔜 Future |

---

## 10. WORKING RULES

### Before any change
1. Read ALL files the change touches (not just the obvious ones)
2. Check for duplicate logic elsewhere
3. Run the relevant section of DEV_CHECKLIST.md
4. State the exact target end-state

### No hardcoding
- User names → do not hardcode `["Mikhail", "Marina"]`
- Categories → do not hardcode category lists
- Accounts → do not hardcode account lists
- All reference data comes from Google Sheets

### Errors and exceptions
- Tool errors → `{"error": "..."}` — agent never crashes
- User-facing → friendly message in their language, no traceback
- Logger → `logger.warning(...)` or `logger.error(...)`

### After any change
1. Run relevant DEV_CHECKLIST.md sections
2. Push → check Railway logs (no import errors, no traceback)
3. Update this file if architecture changed

### Autonomous testing — the AI does this, not the user
All testing is done by the AI without asking the user:
- **L1–L3**: run `python3 tests/run_all.py` (static + unit + Sheets live) — always automated
- **L4 bot behaviour**: call `ApolioAgent.run()` directly with a Mikhail session (360466156) — no Telegram needed
- **L5 UI/UX**: read Railway logs after deploy — check error rate drops, `[AuthManager] Loaded N users` present
- **Railway logs**: read via Chrome MCP (javascript on the Railway logs page)
- The user NEVER has to manually test or check logs — the AI does it all autonomously

---

## 11. LANGUAGE LOGIC (3 tiers)

```
1. UserContext sheet (saved preference) → highest priority
2. Telegram user.language_code
   → "uk" or "it" → use it
   → anything else → keep "ru" (do NOT switch to "en")
3. Default: "ru"
```

All strings through `i18n.ts(key, lang)` or `i18n.t(key, lang)`.
New strings → add to all 4 dictionaries (ru/uk/en/it).

---

## 12. GIT WORKFLOW + STAGING ENVIRONMENT

### Branches
| Branch | Environment | Bot | Purpose |
|--------|-------------|-----|---------|
| `main` | production (Railway) | @ApolioHomeBot | Live bot, Mikhail + Marina use it |
| `dev`  | staging (Railway)   | @ApolioHomeTestBot | Testing before merge |

### Staging environment (Railway)
- **Environment ID:** `1e6973d7-2c9c-48a3-8197-b61fd4174ba4`
- **Test bot token:** `8298458285:AAHm8doTLplljbrErzCo9FAMhhwnhvamaP8`
- **Bot username:** @ApolioHomeTestBot
- Deploys automatically on push to `dev` branch
- **Overridden env vars in staging:**
  - `TELEGRAM_BOT_TOKEN` → @ApolioHomeTestBot token
  - `MM_BUDGET_FILE_ID` → `196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788` (Test Budget)
  - `ADMIN_SHEETS_ID` → `1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM` (Test Admin)
- Uses same PostgreSQL DB as production (conversation history shared)

### Dev workflow
```bash
# 1. Make changes on dev branch
git checkout dev
git add bot.py agent.py  # specific files
git commit -m "feat: description"
git push origin dev
# → Railway staging deploys automatically

# 2. Test on @ApolioHomeTestBot in Telegram

# 3. Merge to main when ready
git checkout main
git merge dev
git push origin main
# → Railway production deploys automatically
```

```bash
# Check actual code state
git log --oneline -5
git status
```

> ⚠️ If a context summary from a previous session describes a commit not in git log —
> those changes were never saved. Check git log, not the summary.

---

## 13. HOW TO UPDATE THIS FILE

Update after any of these events:
- New tool added → section 6
- New file created → section 4
- Architectural change → sections 5, 7
- Backlog feature completed → remove from section 8, add to relevant section
- IDs or env vars changed → section 3
---

## 10. REGRESSION ANALYSIS STUDIO

**File:** `regression_studio.html` — standalone tool, no dependencies outside of cdnjs (Chart.js).
Open directly in any browser.

### What it is
A full OLS regression analysis tool built for Apolio Home budget data exploration.
No backend required — all math runs client-side in JavaScript.

### Models supported
- Simple linear regression
- Polynomial regression (degree 2–8)
- Multiple linear regression (n features)

### Statistics computed
- R², Adjusted R², RMSE
- F-statistic with p-value
- Per-coefficient: estimate, SE, t-statistic, p-value, 95% CI
- Significance stars: `***` `**` `*` `·`

### Diagnostic plots
- Scatter + regression curve
- Residuals vs Fitted
- Normal Q-Q
- Residual histogram
- Scale-Location (√|res| vs fitted)

### Using with Apolio Home data
Export from Google Sheets → paste CSV into the tool:
- For **spending trends**: columns `month, category, amount_eur` — regression of amount vs month
- For **pace analysis**: columns `day_of_month, cumulative_spend` — linear forecast to month-end
- For **per-person split**: columns `month, mikhail_share, marina_share` — regression of contributions
- Sample format: `date,amount_eur,category` (one row per transaction)

The tool auto-detects CSV headers and shows column selectors.

### When Claude runs regression
1. Export data using `get_summary` agent tool (or direct Sheets read)
2. Convert to CSV
3. Reference this tool as the analysis method
4. Record anomalies / trend breaks found in `save_learning`

