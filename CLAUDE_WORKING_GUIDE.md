# Apolio Home — Claude Working Guide
# Version: 1.3 | Updated: 2026-04-02

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
| Mikhail Telegram ID | `360466156` |

Env vars: `TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GOOGLE_SERVICE_ACCOUNT_B64`, `MM_BUDGET_FILE_ID`, `ADMIN_SHEET_ID`, `DATABASE_URL`

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

## 6. AGENT TOOLS (20 total)

| # | Tool | Description |
|---|------|-------------|
| 1 | `add_transaction` | Add transaction; validated against reference data; `force_new` bypasses |
| 2 | `edit_transaction` | Edit a field by ID |
| 3 | `delete_transaction` | Soft-delete (Deleted=TRUE); 2-step confirmation |
| 4 | `delete_transaction_rows` | Physical row deletion (2-step!) |
| 5 | `find_transactions` | Search by filters |
| 6 | `get_summary` | Aggregated report |
| 7 | `get_budget_status` | Current month snapshot |
| 8 | `import_wise_csv` | Import Wise CSV |
| 9 | `set_fx_rate` | Exchange rate (admin) |
| 10 | `update_config` | Config (admin) |
| 11 | `add_authorized_user` | Add user (admin) |
| 12 | `remove_authorized_user` | Remove user (admin) |
| 13 | `list_envelopes` | List envelopes |
| 14 | `create_envelope` | Create envelope (admin) |
| 15 | `save_goal` | Save financial goal |
| 16 | `get_intelligence` | Trends, anomalies, forecast analysis |
| 17 | `get_reference_data` | Reference data: categories / accounts / users / currencies (TTL cache 60s) |
| 18 | `save_receipt` | Save receipt data to Receipts tab after photo transaction confirmed |
| 19 | `save_learning` | Write learning event to agent_learning (PostgreSQL) |
| 20 | `refresh_learning_summary` | Write agent_learning summary to Admin sheet Learning tab |

**Rule:** a new tool must be added to BOTH `TOOLS` schema AND `dispatch` dict.

---

## 7. GOOGLE SHEETS STRUCTURE

### Admin sheet (separate file)
Tabs: `Config`, `Users`, `Envelopes`, `FX_Rates`, `UserContext`

- **Users** → list of authorized users with roles
- **Envelopes** → envelope list: `ID`, `name`, `file_id`, `monthly_cap`, `currency`
- **FX_Rates** → exchange rates by month (headers = currencies)
- **UserContext** → user goals and language preferences

### MM_BUDGET and each envelope (separate files)
Tabs: `Transactions`, `Summary`, `Dashboard`, `Categories`, `Accounts`,
`ConversationLog`, `Receipts` (created on first use)

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

## 8. BACKLOG

| Feature | Description | Status |
|---------|-------------|--------|
| **Post-deploy tests** | Run After pushing checklist — buttons, photo, history | ❌ Not verified |
| **Hetzner migration** | Move deployment from Railway to Hetzner | 🔜 Future |

---

## 9. WORKING RULES

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

---

## 10. LANGUAGE LOGIC (3 tiers)

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

## 11. GIT WORKFLOW

```bash
# Check actual code state
git log --oneline -5
git status

# After changes — add specific files, not everything at once
git add bot.py agent.py tools/transactions.py
git commit -m "short description"
git push
# Railway deploys automatically after push to main
```

> ⚠️ If a context summary from a previous session describes a commit not in git log —
> those changes were never saved. Check git log, not the summary.

---

## 12. HOW TO UPDATE THIS FILE

Update after any of these events:
- New tool added → section 6
- New file created → section 4
- Architectural change → sections 5, 7
- Backlog feature completed → remove from section 8, add to relevant section
- IDs or env vars changed → section 3
