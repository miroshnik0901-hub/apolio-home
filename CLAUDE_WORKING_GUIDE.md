# Apolio Home — Claude Working Guide
# Version: 1.6 | Updated: 2026-04-08

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
| Mikhail Telegram ID | `360466156` |
| Railway project ID | `55240cdd-2cbc-4451-b6c9-ca97ce595c18` |
| Railway service ID (bot) | `8ec97839-6d49-4cdd-a012-1f6d54853454` |
| Railway production env ID | `08e40bf3-cbe4-4a80-be54-1f291c21fe0d` |
| Railway staging env ID | `1e6973d7-2c9c-48a3-8197-b61fd4174ba4` |
| @ApolioHomeTestBot token | `8298458285:AAHm8doTLplljbrErzCo9FAMhhwnhvamaP8` |

Env vars: `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GOOGLE_SERVICE_ACCOUNT`, `ADMIN_SHEETS_ID`, `DATABASE_URL`,
`MM_BUDGET_FILE_ID` (fallback only — budget file_id resolves from Admin → Envelopes)

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
  receipt_store.py  — DEPRECATED, not used. Receipts stored in PostgreSQL parsed_data only.
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

### Receipt confirmation flow (T-076 deterministic handler)

When user clicks `yes_joint` or `yes_personal` after receipt analysis:
1. `bot.py` callback handler intercepts the button click
2. If `session.pending_receipt` exists → calls `tool_add_transaction` directly (NO LLM)
3. Then calls `save_receipt` to store items in Receipts tab + parsed_data
4. Logs to conversation_log + audit
5. Clears `session.pending_receipt`

**Important:** The write path is deterministic — it does NOT go through Claude.
Only `correct` and `cancel` buttons still route through the LLM via `agent.run()`.

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
| 21 | `save_receipt` | Save receipt data to PostgreSQL parsed_data after photo transaction confirmed |
| 22 | `get_receipt` | Retrieve receipt items from parsed_data by tx_id or merchant |
| 23 | `save_learning` | Write learning event to agent_learning (PostgreSQL) |
| 24 | `refresh_learning_summary` | Write agent_learning summary to Admin sheet Learning tab |
| 25 | `get_reference_data` | Reference data: categories / accounts / users / currencies (TTL cache 60s) |
| 26 | `update_dashboard_config` | Update DashboardConfig in Admin sheet (history months, mode, etc.) |
| 27 | `present_options` | Store inline choice buttons to attach to next bot message |

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

**Financial model (per-user, updated 2026-04-09 — xlsx formula):**

Reference: `ApolioHome_UserBalance_formula.xlsx` (4 example sheets)

```
# Per-user data from transactions:
top_up_joint = income/transfer to Joint account by user
personal_exp = expenses from Personal account by user
total_expenses = ALL expenses (joint + personal, all users)

# From Config:
total_min_pool = sum(min_<user> for all users)
split_base = total_expenses - total_min_pool

# Obligation = how much user still needs to contribute
obligation = (min_user - top_up_joint)
           + max(0, split_base) * split_user% / 100
           - personal_exp

# Credit = -obligation (positive = overpaid / owed to you, negative = you owe)
credit = -obligation
```

Three components of obligation:
1. `(min - top_up)` — remaining minimum commitment
2. `max(0, split_base) * split%` — share of overflow above min pool
3. `- personal_exp` — already paid from personal account

Works for all combinations: min+split, min-only, split-only, no rules (Example1-4 in xlsx).

Transaction classification:
- Income to Joint (Type=income, Account=Joint or empty): counted in top_up_joint
- Personal expense (Type=expense, Account=Personal): counted in personal_exp AND total_expenses
- Joint expense (Type=expense, Account=Joint or empty): counted in total_expenses only

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
**Python module:** `task_log.py` → `TaskLog` class

### Column layout — EXACT sheet header names (col index, 1-based)
```
Col 1  A: ID               — auto: T-NNN (text, not number)
Col 2  B: Date             — auto: YYYY-MM-DD when task created
Col 3  C: Task             — task description (Mikhail writes here)
Col 4  D: Status           — OPEN / IN PROCESS / ON HOLD / BLOCKED / DISCUSSION / CLOSED
Col 5  E: Apolio Comment   — Claude's dated log (newest entry at top)
Col 6  F: Branch           — git branch name if code was pushed, else empty
Col 7  G: Resolved At      — YYYY-MM-DD set automatically when Status → CLOSED
Col 8  H: Topic            — category for grouping
Col 9  I: Deploy           — N/A / READY / DEPLOYED / FAILED
Col 10 J: Confirm          — GO / HOLD / (empty)
```

> ⚠️ CRITICAL: The column header in the sheet is **"Apolio Comment"**, not "AI Comment".
> The HEADER list in `task_log.py` must match exactly. Never mix these up — a mismatch
> causes `get_all_records()` to raise an exception and all updates will silently fail or
> write to wrong columns.

### Status values
`OPEN` → `IN PROCESS` → `ON HOLD` / `BLOCKED` / `DISCUSSION` → `CLOSED`

### Topic values (pick exactly one)
`Interface` | `Features` | `Data` | `Infrastructure` | `AI` | `Docs` | `Admin` | `Финансы`

Both Status and Topic have dropdown validation in the sheet.
Valid values are also in the `config` sheet tab (col A = statuses, col B = topics).

---

### How Claude works with the Task Log — step by step

**Step 1 — Read the current state**
```python
from task_log import TaskLog
tl = TaskLog()
tasks = tl.get_all_tasks()
open_tasks = [t for t in tasks if t.get("Status") != "CLOSED"]
```
For each open task, read ALL fields fully:
- `Task` (C) — **read in full every time**; Mikhail adds new notes/context directly into the Task body when reopening or updating a task
- `Apolio Comment` (E) — prior history to understand what was already done
- `Status` (D), `Deploy` (I), `Confirm` (J)

> ⚠️ **CRITICAL RULE — Reopened tasks:**
> When Mikhail changes Status back to OPEN (reopen), he **adds new text to the Task body (C)**.
> Claude MUST re-read the full Task (C) text — the new content appears below the original text.
> Do NOT rely on prior Apolio Comment (E) history alone. React to the new content in C first.
> This is the core feedback loop: Mikhail writes in C → Claude reads C → Claude acts → writes in E.

**Step 2 — Determine action**
- Status = `OPEN`, no prior Apolio Comment → fresh task, start working
- Status = `OPEN`, has prior Apolio Comment → Mikhail reopened it; read new text in Task (C) first
- Status = `IN PROCESS` → task is in progress; if code is NOT written yet → write it now, do not leave "начинаю реализацию" without actual implementation
- Status = `DISCUSSION` → write architectural comment in E, set next step, no code until Mikhail confirms
- Status = `ON HOLD` → **DO NOT process. Skip.** Mikhail will reopen when ready.
- `Confirm` = `GO` and `Deploy` = `READY` → push to main, set Deploy = `DEPLOYED`, Status = `DISCUSSION`

> ⚠️ **CRITICAL RULE — Who closes tasks (T-047):**
> Claude NEVER sets Status = CLOSED. Only Mikhail closes tasks.
> After completing work, Claude sets Status = `DISCUSSION`.
> Mikhail reviews → sets CLOSED himself.
> This applies to ALL tasks: code, docs, discussions, explanations.

> ⚠️ **CRITICAL RULE — No deploy without GO (T-048):**
> Claude NEVER pushes to main without Confirm = GO from Mikhail.
> Workflow: code on dev → Deploy=READY → wait for Mikhail's GO → then push.
> No exceptions.

> ⚠️ **"IN PROCESS" means work is actively happening, not planned.**
> Never set Status = IN PROCESS without immediately doing the actual work in the same session.
> If a task is IN PROCESS and code was not written — write it now before moving to the next task.
> **MANDATORY: As soon as work is done and pushed to dev → set Status = DISCUSSION immediately.**
> IN PROCESS is a TEMPORARY status. Never leave it after the session ends.
> Workflow: OPEN → IN PROCESS (while working) → DISCUSSION (done, on staging) → CLOSED (Mikhail only)

**Step 3 — Write updates via task_log.py API**
```python
# Always use keyword arguments. Never pass positional args to update_task.
tl.update_task(
    "T-007",
    status="IN PROCESS",          # optional
    comment="[2026-04-03] ...",   # optional — prepended to existing comment
    topic="Interface",             # optional
    branch="dev",                  # optional — only if code was pushed
    deploy="READY",               # optional
    confirm="",                    # optional — clear when reopening after deploy
)
```

**Step 4 — Mandatory fields checklist** (before every `update_task` or `add_task`)

| Field | Rule |
|-------|------|
| **Topic** (H) | Always set — never leave empty |
| **Apolio Comment** (E) | Always write `[YYYY-MM-DD] что сделано`. New entries prepended at top. |
| **Branch** (F) | Fill if code was committed/pushed; leave empty for admin/discussion tasks |
| **Deploy** (I) | Always set — `N/A` for tasks with no code deploy; `READY` when code done |
| **Status** (D) | Reflects actual current state — update as work progresses |

**Step 5 — Verify after writing**
After every batch of updates: call `tl.get_all_tasks()` again and spot-check that
Topic / Status / Deploy are in the correct columns for at least 2–3 rows.
If any value appears in the wrong column — fix immediately using direct `ws.update_cell(row, col, value)`.

---

### Python API reference

```python
from task_log import TaskLog
tl = TaskLog()

# Add new task
task_id = tl.add_task(
    title="Fix onboarding flow",
    topic="Interface",   # REQUIRED
    deploy="N/A",        # or "READY"
    comment="[2026-04-03] Initial description",
)  # → "T-NNN"

# Update existing task (all kwargs optional except task_id)
tl.update_task(
    "T-007",
    status="CLOSED",
    comment="[2026-04-03] Done",
    branch="dev",
    deploy="N/A",
    confirm="",
)

# Read tasks
all_tasks   = tl.get_all_tasks()    # all rows
open_tasks  = tl.get_open_tasks()   # Status != CLOSED
```

Auto-numbering: `task_log.py` → `_next_id()` on every `add_task()` call.
Parses both text ("T-007") and numeric (7) IDs to avoid collision.

---

### Deploy workflow

| Step | Who | Action |
|------|-----|--------|
| 1 | Claude | Code done on `dev` → sets Deploy (I) = `READY`, sets Status = `IN PROCESS` |
| 2 | Mikhail | Tests on @ApolioHomeTestBot → sets Confirm (J) = `GO` (or `HOLD` to pause) |
| 3 | Claude | Sees `GO` → `git checkout main && git merge dev && git push origin main` |
| 4 | Claude | Sets Deploy = `DEPLOYED`, adds to Apolio Comment: `[date] deployed to main, commit=...` |

**Deploy values (I):** `N/A` · `READY` · `DEPLOYED` · `FAILED`
**Confirm values (J):** `GO` · `HOLD` · *(empty = not yet reviewed)*

**When to set Deploy = N/A:** ONLY tasks with zero code changes — documentation, discussion,
admin, config sheet edits, Apps Script only. If ANY Python file was committed to git → Deploy ≠ N/A.

**Status vs Deploy lifecycle for code tasks:**
```
Code written + pushed to dev  → Status=IN PROCESS, Deploy=READY
Mikhail sets Confirm=GO       → Claude pushes to main
Pushed to main + deployed     → Status=DISCUSSION, Deploy=DEPLOYED, Resolved At=today
Mikhail reviews               → sets Status=CLOSED (only Mikhail!)
```
Claude NEVER sets CLOSED. Only DISCUSSION after completing work.
Never close a code task with Deploy=N/A. That combination says "nothing was deployed" which
is false if code is on dev. DISCUSSION + N/A is only correct for admin/discussion tasks.

> 🔒 **HARD RULE: Claude NEVER pushes to `main` without Confirm = `GO`.**
> If Deploy = `READY` and Confirm is empty or `HOLD` — Claude waits.
> The check sequence when reviewing tasks:
> 1. Read all tasks where Deploy = `READY`
> 2. For each: check Confirm (J) in the sheet
> 3. If `GO` → push to main, update Deploy = `DEPLOYED`, clear Confirm logic is N/A (Mikhail resets)
> 4. If empty or `HOLD` → skip, add note to Apolio Comment if Mikhail needs to be reminded

> ⚠️ **Never set Deploy = `READY` before code is actually written and pushed to `dev`.**
> Setting READY prematurely (before implementation) gives false signal to Mikhail.

### Reopen-after-deploy rule

If Mikhail reopens a task after a deploy (bug found or more work needed):
1. Claude reads full Task (C) + Apolio Comment history (E)
2. Claude fixes the issue, pushes to `dev`
3. Claude resets: **Deploy (I) → `READY`**, **Confirm (J) → empty** — previous GO is void
4. Mikhail sets GO again → Claude pushes to main, updates Deploy = `DEPLOYED`

---

### Apps Script (sheet UI automation)

Installed in the Task Log sheet. Handles:
- Auto-assigns ID + Date + Status = OPEN on new rows
- Sets `Resolved At` (G) automatically when Status → CLOSED
- 🏠 Apolio menu: Sort by Date / Sort by Status / Archive CLOSED / Setup filter row

**To reinstall:** Open Task Log → Extensions → Apps Script →
paste `apps_script/task_log_automation.js` → Save → Run `setupTriggers()` once.

---

## 9. BACKLOG (tracked separately in Task Log)

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
- Budget file IDs → resolve from Admin → Envelopes tab (`_get_active_file_id()` in bot.py, `_resolve_budget_file_id()` in agent.py)
- All reference data comes from Google Sheets

### Errors and exceptions
- Tool errors → `{"error": "..."}` — agent never crashes
- User-facing → friendly message in their language, no traceback
- Logger → `logger.warning(...)` or `logger.error(...)`

### After any change
1. Run relevant DEV_CHECKLIST.md sections
2. Push → check Railway logs (no import errors, no traceback)
3. Update this file if architecture changed

### Autonomous testing — Claude is QA, never ask Mikhail to test
All testing is done by Claude without asking the user:
- **After every change**: run `python test_regression.py` — all tests must pass
- **Quick (no network)**: run `python test_regression.py --no-sheets` — static + unit only
- **With Sheets**: run `python test_regression.py` — includes live roundtrip test
- **After every push to `dev`**: verify staging deploy — check Railway logs, query staging DB, test bot responses. Report results to Mikhail, never ask him to test.
- **Bot behavior**: call `ApolioAgent.run()` directly with a Mikhail session (360466156) — no Telegram needed
- **UI/UX**: read Railway logs after deploy — check error rate drops, `[AuthManager] Loaded N users` present
- **Railway logs**: read via Chrome MCP (javascript on the Railway logs page)
- The user NEVER has to manually test or check logs — the AI does it all autonomously

### MANDATORY: keep test files current
**Every time a bug is fixed or feature is added**, update `test_regression.py`:
1. Add a new test (section 1 static check OR section 2 unit test) that would have caught the bug
2. Add the bug to the "Known bugs fixed" table in `QA_CHECKLIST.md`
3. If a new tool is added → add a test for its error path (what happens if Sheets fails?)
4. If a new prompt rule is added → add a static check that the rule is present in `ApolioHome_Prompt.md`

This ensures regressions are caught immediately and the test suite grows with the product.

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
  - `ADMIN_SHEETS_ID` → `1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM` (Test Admin)
  - `DATABASE_URL` → `${{Postgres-pCvV.DATABASE_URL}}` (separate staging DB)
  - `DATABASE_PUBLIC_URL` → `${{Postgres-pCvV.DATABASE_PUBLIC_URL}}`
  - Budget file_id resolves automatically from Test Admin → Envelopes (no MM_BUDGET_FILE_ID override needed)
- **Auto-switch**: if bot token starts with `8298458285:` and ADMIN_SHEETS_ID points to prod, bot auto-switches to Test Admin at startup
- **Separate PostgreSQL**: Postgres-pCvV (service `81b39ec8-3f97-4a10-8e55-d052f64ef1fd`) — staging DB fully isolated from prod

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

## 14. REGRESSION ANALYSIS STUDIO

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

