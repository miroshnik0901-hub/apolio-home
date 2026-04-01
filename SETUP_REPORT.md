# Apolio Home — SETUP REPORT
**Last updated:** 2026-04-01
**Maintained by:** Cowork AI Agent

This document is a complete technical handoff for any Claude session continuing work on this project. Read this before touching any code.

---

## 1. What This Is

**Apolio Home** is a Telegram bot + AI agent for Mikhail Miro's personal/family budget management. Built on: Python 3.12, python-telegram-bot 20.7, Anthropic Claude API (claude-sonnet-4-20250514), Google Sheets API, Google Drive API. Deployed on Railway (worker process, polling mode).

**Owner:** Mikhail Miro (`miroshnik0901@gmail.com`), Telegram ID: `360466156`
**Bot:** [@ApolioHomeBot](https://t.me/ApolioHomeBot)
**Bot token:** stored in `TELEGRAM_BOT_TOKEN` env var on Railway

---

## 2. Project Folder Location

Mac local path: `Google Drive > My Drive > Personal > AI > apolio-home`
Contains: `.py` files, `tools/`, `.env`, `requirements.txt`, `Procfile`, `.python-version`
Also contains `.gsheet` shortcuts to Google Sheets files (these are 178-byte Drive Desktop aliases, not the actual sheets).

---

## 3. File Structure

```
apolio-home/
├── bot.py                    # Telegram bot entry point, all handlers
├── agent.py                  # Claude AI agent with tool loop
├── auth.py                   # AuthManager + SessionContext (+ lang field)
├── sheets.py                 # SheetsClient (facade over AdminSheets + EnvelopeSheets)
├── menu_config.py            # Dynamic inline menu from Admin BotMenu sheet
├── i18n.py                   # Multilingual strings (RU/UK/EN/IT): keyboards, menus, messages
├── reports.py                # Formatting helpers (CATEGORY_EMOJI, format_bar, format_report)
├── tools/
│   ├── transactions.py       # add / edit / delete / find transactions
│   ├── summary.py            # get_summary + get_budget_status
│   ├── envelope_tools.py     # create_envelope + list_envelopes
│   ├── wise.py               # Wise CSV import
│   ├── fx.py                 # FX rate tools (ECB auto-fetch)
│   ├── config_tools.py       # update_config, add_user, remove_user
│   └── envelopes.py          # (old/legacy, replaced by envelope_tools.py — IGNORE)
├── setup.py                  # one-off setup script (creates Admin sheets structure)
├── setup_admin.py            # one-off Admin sheet seeder
├── encode_service_account.py # utility: base64-encode SA credentials for env var
├── get_oauth_token.py        # utility: get OAuth refresh token for Mikhail's Google
├── get_telegram_id.py        # utility: print own Telegram user ID
├── test_bot.py               # manual test script
├── requirements.txt
├── Procfile                  # "worker: python bot.py"
├── .python-version           # "3.12"
├── .env                      # local secrets (NOT committed)
├── .env.example              # template (no secrets)
└── Apolio Home — Admin.gsheet     # Drive shortcut to Admin sheet
└── Apolio Home — MM Budget.gsheet # Drive shortcut to MM Budget sheet
```

**Note:** `tools/envelopes.py` is legacy and not imported anywhere. Active envelope logic is in `tools/envelope_tools.py`.

---

## 4. Google Sheets Structure

### 4a. Admin Sheet
**File:** Apolio Home — Admin
**URL:** https://docs.google.com/spreadsheets/d/1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk
**Owner:** miroshnik0901@gmail.com
**Service account has Editor access:** apolio-home-bot@apolio-home.iam.gserviceaccount.com

Sheets/tabs:
- **Envelopes** — registry of all envelope files. Columns: `ID, Name, file_id, Owner_TG, Currency, Monthly_Cap, Split_Rule, Active, Created_At`
- **Users** — authorized Telegram users. Columns: `telegram_id, name, role, envelopes, created_at, language, status, notes, updated_at`. Status `suspended` blocks access. Language: RU/UK/EN/IT.
- **Config** — key/value config with Description column. Keys: `alert_threshold_pct`, `default_currency`, `fx_fallback`, `budget_MM_BUDGET_monthly`, `default_envelope`, `bot_version`, `current_envelope_mikhail`
- **Audit_Log** — log of all state-changing bot operations. Columns: `Timestamp, Telegram_ID, Name, Action, Details`. Bold header, frozen row 1, alternating row colors.
- **BotMenu** — dynamic inline /menu structure loaded on deploy. Columns: `ID, Label, Parent, Type, Command, Params, Order, Visible, Roles`. Reset to defaults on every deploy via `menu_config.reset_to_defaults()`.

### 4b. MM Budget Envelope
**File:** Apolio Home — MM Budget
**URL:** https://docs.google.com/spreadsheets/d/1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ
**Envelope ID in Admin:** `MM_BUDGET`
**Monthly cap:** 2500 EUR

Sheets/tabs:
- **Transactions** — main ledger. Column order (A→P): `Date, Amount_Orig, Currency_Orig, Category, Subcategory, Note, Who, Amount_EUR, Type, Account, ID, Envelope, Source, Wise_ID, Created_At, Deleted`. Columns K-P hidden. Row 1 + Col A frozen. Dropdowns on C (currency), D (category from sheet), G (who), I (type), J (account from sheet). Conditional formatting: FX_MISSING rows → light red; Deleted=TRUE rows → gray+strikethrough. Col H: number format 2dp.
- **Summary** — monthly summary with SUMIFS formulas. Columns: `Month, Total_Expenses, Total_Income, Balance, Housing, Food, Transport, Health, Entertainment, Personal, Household, Travel, Other, Cap, Remaining, Used_%`. Jan–Dec 2026 pre-filled.
- **Categories** — category list. Columns: `Category, Subcategory, Type, Emoji`
- **FX_Rates** — monthly FX rates. Columns: `Month, PLN, UAH, GBP, USD, Source`
- **Accounts** — account list. Columns: `Account, Owner, Currency, Description, Active`. Pre-filled: Wise Family, Wise Mikhail, Cash IT, Cash PL.
- **Config** — per-envelope config (optional overrides)
- **Dashboard** — visual summary sheet (manual layout)

### 4c. Семья (SEMYA) Envelope
**File:** Apolio Home — Семья
**URL:** https://docs.google.com/spreadsheets/d/1UNhBQqM5L0fhFMef_f6y-QBYrGAK0csCsLksnAwi-So
**Envelope ID in Admin:** `SEMYA`
**⚠️ ISSUE:** No `.gsheet` shortcut exists in the `apolio-home` Mac/Drive folder for this file.
**Reason:** The SEMYA file was created via `tool_create_envelope` which used the service account's Drive context. The SA's Drive folder (`Apolio Home`) is separate from Mikhail's Drive folder. The file itself is owned by the SA, not by Mikhail.

---

## 5. Environment Variables

These must be set in Railway (Settings → Variables) and in local `.env`:

| Variable | Value / Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key (for Whisper voice transcription) |
| `GOOGLE_SERVICE_ACCOUNT` | **Base64-encoded** JSON of the SA credentials file. Use `encode_service_account.py` to generate. SA email: `apolio-home-bot@apolio-home.iam.gserviceaccount.com` |
| `ADMIN_SHEETS_ID` | `1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk` |
| `MIKHAIL_TELEGRAM_ID` | `360466156` — bootstrap admin bypass (works even if Users sheet is empty) |
| `WEBHOOK_URL` | Leave empty for polling mode. Set to public HTTPS URL for webhook mode. |
| `PORT` | `8080` (used only in webhook mode) |
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth2 client ID (for creating files as Mikhail, not SA) |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth2 client secret |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | OAuth2 refresh token (get with `get_oauth_token.py`) |

OAuth credentials (`GOOGLE_OAUTH_*`) are used only by `sheets.py::create_spreadsheet_as_owner()` — for creating new Google Sheets files that appear in Mikhail's Drive, not the SA's.

---

## 6. Railway Deployment

**Project:** Apolio Home
**Service:** apolio-home-bot
**Process type:** `worker` (from Procfile: `worker: python bot.py`)
**Runtime:** Python 3.12 (from `.python-version`)
**Branch:** main
**Status:** Active, polling mode

**CRITICAL:** Python 3.13 breaks python-telegram-bot 20.7 with `AttributeError: __slots__`. The `.python-version` file pins 3.12. Do NOT upgrade.

To trigger a deploy: push a commit to `main`. Railway picks it up automatically.
If Railway doesn't pick up the latest commit: use Railway CLI or API with `latestCommit: true`.

---

## 7. How the Bot Works

### 7a. Startup
`bot.py::main()` builds a PTB Application, registers all handlers, calls `post_init` which registers bot commands in Telegram (the slash-command menu).

### 7b. Auth Flow
Every handler calls `_require_user(update)` which:
1. Gets `user.id` from the Telegram update
2. Calls `auth.get_user(user.id)`
3. If `user.id == MIKHAIL_TELEGRAM_ID` env var → always returns admin (bootstrap bypass)
4. Otherwise checks the Users sheet (cached 5 min)
5. Returns `(tg_user, session)` or `(None, None)` if not authorized

### 7c. Session
`SessionContext` (per user, in-memory dict) holds:
- `user_id`, `user_name`, `role`
- `lang` — detected from Telegram `language_code` on each message (ru/uk/en/it, default en)
- `current_envelope_id` — which envelope is "active" for this user (auto-set to MM_BUDGET for admin)
- `last_action` — for undo support (records last tx_id + snapshot)
- `pending_edit_tx` — tx_id of a transaction being edited via free text

Session persists as long as the bot process is running. After restart, `current_envelope_id` is auto-restored for admin users (MM_BUDGET default).

### 7d. Commands

| Command | Handler | Description |
|---|---|---|
| `/start` | `cmd_start` | Welcome + shows reply keyboard in user's language |
| `/menu` | `cmd_menu` | Opens inline menu (2-level, from BotMenu sheet) |
| `/envelopes` | `cmd_envelopes` | Lists all active envelopes with links + select buttons |
| `/envelope [ID]` | `cmd_envelope` | No args: show list with buttons; with arg: set active envelope |
| `/status` | `cmd_status` | Budget status for current month (direct render, no agent) |
| `/report` | `cmd_report` | Category breakdown for current/last month (direct render) |
| `/week` | `cmd_week` | Expenses for current week |
| `/month` | `cmd_month` | Expenses for current month (same as /report) |
| `/transactions` | `cmd_transactions` | Last 10 transactions with delete buttons |
| `/undo` | `cmd_undo` | Undo last add/edit action |
| `/help` | `cmd_help` | Usage examples |
| `/refresh` | `cmd_refresh` | Reload BotMenu from Admin sheet |
| `/settings` | `cmd_settings` | Show settings submenu (admin only) |

**Reply keyboard** (shown after /start, user can hide/show with 🟦 button): Add / Status / Report / Records / Help — all labels translated via `i18n.py`. Language auto-detected from Telegram `language_code`.

**Inline /menu** (from BotMenu sheet): 2-level hierarchy. Root: Status, Analytics ›, Records ›, Envelopes, Settings › (admin). All labels translated via `i18n.MENU_LABELS`.

### 7e. Inline Callbacks
`callback_handler` handles:
- `cb_envelopes` — show envelope list
- `cb_status` — show budget status
- `cb_report` — show monthly report
- `cb_help` — show help
- `cb_env_<ID>` — set current envelope to `<ID>`

### 7f. Message Handler
`handle_message` processes everything that isn't a command:
- Text → passed directly to agent
- Voice/Audio → transcribed via Whisper, echoed back, passed to agent
- Photo → passed to agent as base64 image (for receipt scanning)
- CSV document → passed to agent as text (for Wise import)

---

## 8. How the AI Agent Works

`agent.py::ApolioAgent.run()` implements a Claude tool-use loop:
1. Build system prompt with today's date, user info, active envelope
2. Send user message (with optional image) to `claude-sonnet-4-20250514`
3. If Claude calls a tool → `_execute_tool()` dispatches to the appropriate handler
4. Tool result is fed back as a `tool_result` message
5. Loop up to 5 iterations, then return final text response

**Available tools (13 total):**

| Tool | File | Description |
|---|---|---|
| `add_transaction` | transactions.py | Record expense/income/transfer |
| `edit_transaction` | transactions.py | Edit one field of existing tx |
| `delete_transaction` | transactions.py | Soft-delete (sets Deleted=TRUE) |
| `find_transactions` | transactions.py | Search with filters |
| `get_summary` | summary.py | Category/who breakdown for a period |
| `get_budget_status` | summary.py | Month snapshot: spent/remaining/% |
| `import_wise_csv` | wise.py | Parse and import Wise CSV export |
| `set_fx_rate` | fx.py | Set ECB FX rate for month + currency |
| `update_config` | config_tools.py | Update Admin Config key/value |
| `add_authorized_user` | config_tools.py | Grant bot access to user |
| `remove_authorized_user` | config_tools.py | Revoke bot access |
| `list_envelopes` | envelope_tools.py | List all active envelopes with links |
| `create_envelope` | envelope_tools.py | Create new envelope (Google Sheets + register) |

**Agent system prompt behavior:**
- Auto-selects envelope: mentions of Polina/Поліна/дочка/Bergamo/liceo → switch to Polina envelope; everything else → current envelope
- Missing date → today
- Missing category → best guess (stated in reply)
- Missing currency → EUR
- Responds in the user's language (RU/UK/EN/IT all supported)

---

## 9. Transaction Data Flow

1. User writes "потратил 45 EUR на продукты" in Telegram
2. `handle_message` → `agent.run(text, session)`
3. Claude interprets: amount=45, currency=EUR, category=Food/Groceries, type=expense
4. Claude calls `add_transaction` tool
5. `tool_add_transaction` in `transactions.py`:
   - Resolves envelope file_id from Admin sheet
   - Generates tx_id (8-char hex)
   - For EUR: amount_eur = amount directly
   - For non-EUR: looks up FX_Rates sheet for current month, calculates
   - Builds row list and calls `sheets.add_transaction(file_id, row)`
6. `SheetsClient.add_transaction()` detects list input → `ws.append_row(row)` directly
7. Row written to Transactions sheet in the envelope file
8. Audit log entry written to Admin sheet
9. `last_action` saved on session (for undo support)
10. Claude returns confirmation text → bot sends to user

---

## 17. Changes Made in Session 3 (2026-04-01)

### Multilingual support (i18n)
- **i18n.py** (new) — full translations for RU/UK/EN/IT: reply keyboard labels (`KB_LABELS`), inline menu node labels (`MENU_LABELS`), start/greeting/add-expense messages. Reverse map `KB_TEXT_TO_ACTION` routes any language's button text to action key. Helper functions: `get_lang()`, `t_menu()`, `t_kb()`, `t()`.
- **auth.py** — added `lang: str = "en"` to `SessionContext`. Set by `_require_user()` from Telegram `language_code` on every message.
- **menu_config.py** — fixed double-arrow bug: removed `›` from submenu labels in `DEFAULT_MENU` and `_DEFAULT_ROWS`. `_build_inline_menu()` adds `›` suffix itself.
- **bot.py** — replaced hardcoded `MAIN_KEYBOARD` + `KEYBOARD_SHORTCUTS` with: `_build_main_keyboard(lang)` (language-aware), `i18n.KB_TEXT_TO_ACTION` routing, `_build_inline_menu(lang=lang)` with translated labels and Back button. `/start`, greeting, add-prompt use `i18n` strings. `callback_handler` and `cmd_menu` pass `lang` through.

### Google Sheets formatting (applied via scripts, not committed to repo)
- **MM Budget — Transactions**: Dropdowns on C/D/G/I/J, columns K-P hidden, row 1 + col A frozen, FX_MISSING and Deleted conditional formatting, column widths A-J, blue header row, Amount_EUR formula in H2:H1000.
- **Admin — Config**: Blue header, col widths, bold key column. Fixed `current_envelope_mikhail` value → MM_BUDGET.
- **Admin — Users**: Blue header, col widths, dropdowns on role/status/language. Fixed Mikhail's `envelopes` field → MM_BUDGET.
- **Admin — Audit_Log**: Dark header, alternating row colors, col widths.

### Railway
- Verified all 3 OAuth vars (`GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN`) already set in Railway.
- Deployment: `feat(i18n): multilingual menus and keyboards` — active, successful.

---

## 16. Changes Made in Session 2 (2026-04-01 — continued)

### Code changes (all files committed together)
- **auth.py** — `DEFAULT_ENVELOPE = "MM_BUDGET"`. `get_session()` auto-assigns MM_BUDGET for admin on first login. `_reload()` reads `language`, `status` columns from Users sheet; suspended users are skipped.
- **bot.py** — Full rewrite: `ReplyKeyboardMarkup` (persistent bottom keyboard with 5 buttons), greeting interceptor (no API call for "привет"), keyboard shortcut router, keep-alive typing task (8s loop), `/undo`, `/week`, `/month` commands, post-transaction inline buttons (✏ Edit / 🗑 Delete / 📊 Status), confirmation flow for delete, weekly summary scheduled job (Monday 09:00 Rome via APScheduler/JobQueue).
- **agent.py** — System prompt now loaded from `ApolioHome_Prompt.md` at startup. Silent bot fix: fallback text extraction if tool-use loop returns no text. `max_tokens` raised from 1024 → 2048.
- **sheets.py** — Added `SheetsCache` class (60s TTL). `get_transactions` caches unflitered results; invalidated on `add_transaction`. `EnvelopeSheets.add_transaction()` dict-path updated to new 16-column order.
- **tools/transactions.py** — `tool_add_transaction` row list reordered: Date/Amount_Orig/Currency_Orig/Category/Subcategory/Note/Who/Amount_EUR/Type/Account/ID/Envelope/Source/Wise_ID/Created_At/Deleted.
- **reports.py** — New file: `CATEGORY_EMOJI`, `format_bar`, `format_budget_status`, `format_report`, `format_transactions_list`, `to_html`.
- **requirements.txt** — Added `pytz==2024.1`; changed `python-telegram-bot==20.7` → `python-telegram-bot[job-queue]==20.7`.

### Google Sheets changes (applied via setup_sheets_v2.py)
- **MM Budget — Transactions**: Columns reordered A-P, Amount_EUR formula in H2:H1000, columns K-P hidden, row 1 + col A frozen, dropdowns on Currency/Who/Type, column widths set, FX_MISSING conditional formatting.
- **MM Budget — Summary**: Rebuilt with SUMPRODUCT formulas for all 12 months of 2026.
- **MM Budget — Accounts**: New sheet with 4 pre-filled accounts (Wise Family, Wise Mikhail, Cash IT, Cash PL).
- **Admin — Config**: Added Description column; 6 key entries filled.
- **Admin — Users**: Added columns `language`, `status`, `notes`, `updated_at`; Mikhail's row updated.
- **Admin — Audit_Log**: Bold headers, frozen row 1, timestamp column 200px wide.

### New commands
`/undo`, `/week`, `/month` (all registered in Telegram command menu)

### New keyboard
Persistent bottom keyboard: 📊 Статус / 📋 Отчёт / 💰 Добавить расход / 📁 Конверты / ❓ Помощь

---

## 10. Known Issues & Pending Tasks

### Issue 1: SEMYA file not in Mikhail's Drive folder
The `apolio-home` Drive folder (Mac: `My Drive > Personal > AI > apolio-home`) contains `.gsheet` shortcuts for Admin and MM Budget, but NOT for SEMYA.

**Root cause:** `tool_create_envelope` creates files using the service account's `gspread.create()`. SA-created files live in the SA's Drive root, invisible in Mikhail's Drive. The `get_or_create_drive_folder()` function in `sheets.py` also uses SA credentials → creates an "Apolio Home" folder in SA's Drive, not Mikhail's.

**Correct approach:** New envelope files should be created with `sheets.create_spreadsheet_as_owner()` which uses Mikhail's OAuth credentials. This is already implemented in `sheets.py`. `tool_create_envelope` needs to call this instead of `gc.create()`.

**For SEMYA specifically:** The file already exists. Mikhail needs to manually add it to the `apolio-home` Drive folder (or just keep the direct link). The file URL is: https://docs.google.com/spreadsheets/d/1UNhBQqM5L0fhFMef_f6y-QBYrGAK0csCsLksnAwi-So

### Issue 2: tool_create_envelope uses SA for file creation
`tools/envelope_tools.py::tool_create_envelope()` calls `gspread.authorize(creds)` and `gc.create()` with SA credentials. New files end up in SA's Drive.

**Fix needed:** Replace `gc.create(f"Apolio Home — {name}")` with `sheets.create_spreadsheet_as_owner(f"Apolio Home — {name}")` and then populate via `gc.open_by_key(file_id)`.

**Prerequisite:** OAuth env vars must be set (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`). ✅ All three are now set in Railway and verified working.

### ~~Issue 3: Envelope sessions reset on restart~~ ✅ FIXED
`get_session()` now auto-assigns `current_envelope_id = "MM_BUDGET"` when `role == "admin"` on every session creation or envelope loss. Admin never needs to run `/envelope` after restart.

### Issue 4: FX rates for non-EUR transactions not auto-populated
`auto_update_fx_rates()` in `fx.py` is never called automatically. It must be triggered manually or via a cron job. Without FX rates, all non-EUR transactions have `Amount_EUR = ""` which breaks reporting.

### Issue 5: Polina envelope not created yet
The agent's system prompt auto-routes Polina/Bergamo/liceo keywords to the "Polina" envelope, but this envelope doesn't exist in the Admin sheet yet. Creating it will require `create_envelope` tool call or manual setup.

---

## 11. Fixes Applied Across All Sessions

1. **Python 3.12 pin** — `.python-version` added. PTB 20.7 incompatible with 3.13's `__slots__` change.
2. **Bootstrap admin in `get_user()`** — `auth.py` returns admin user for `MIKHAIL_TELEGRAM_ID` even if Sheets unavailable.
3. **Budget status field fix** — `summary.py::tool_get_budget_status` reads `Monthly_Cap` column directly, not a nonexistent JSON `settings` field.
4. **Amount_EUR filled in Python** — `transactions.py::tool_add_transaction` calculates EUR value before `append_row` (gspread doesn't evaluate formulas).
5. **Cyrillic envelope ID** — `envelope_tools.py` uses `re.sub(r"[^A-Z0-9_]", "", raw_id)` to strip non-ASCII. SEMYA Admin row was manually patched from `_____` to `SEMYA`.
6. **list vs dict in `add_transaction`** — `SheetsClient.add_transaction()` detects list input and calls `append_row` directly.
7. **`file_id` column name** — Envelopes sheet column renamed from `sheet_id` to `file_id`. `register_envelope()` updated to match.
8. **parse_mode = Markdown (not MarkdownV2)** — All `reply_text()` calls use `ParseMode.MARKDOWN` to avoid entity parse errors.
9. **Bot command menu** — `post_init` calls `set_my_commands` on startup; menu visible in Telegram.
10. **Inline keyboards** — `/start`, `/menu`, `/envelopes`, `/envelope` all return inline buttons.
11. **`tool_list_envelopes`** — Added to tools, agent.py dispatch, and TOOLS schema.
12. **Railway deploy** — `Procfile` uses `worker:` type; `serviceInstanceDeploy` with `latestCommit: true` needed to pick up latest commit.

---

## 12. How to Add a New Envelope (Manual Process)

Until `tool_create_envelope` is fixed to use OAuth, follow this process:
1. Create a Google Sheets file manually in Mikhail's Drive, inside the `apolio-home` folder
2. Share it with the SA as Editor: `apolio-home-bot@apolio-home.iam.gserviceaccount.com`
3. Add sheets: Transactions, Summary, Categories, FX_Rates (headers from `ENVELOPE_TEMPLATE` in `envelope_tools.py`)
4. Add a row to the Admin Envelopes sheet: `ID, Name, file_id, Owner_TG, Currency, Monthly_Cap, Split_Rule, Active, Created_At`
5. Alternatively, ask the bot: "создай конверт <Name> лимит <N> EUR" — it will work IF OAuth env vars are set

---

## 13. Quick Reference: Admin Sheet IDs

| Item | Google Sheets ID |
|---|---|
| Admin file | `1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk` |
| MM Budget | `1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ` |
| Семья (SEMYA) | `1UNhBQqM5L0fhFMef_f6y-QBYrGAK0csCsLksnAwi-So` |

---

## 14. Testing Locally

```bash
cd apolio-home
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in all values
python bot.py          # runs in polling mode
```

Send `/start` to the bot in Telegram, then test a transaction: "потратил 10 EUR на кофе"

---

## 15. Service Account Info

**Email:** `apolio-home-bot@apolio-home.iam.gserviceaccount.com`
**GCP Project:** `apolio-home`
**Credential format:** JSON key file, base64-encoded for `GOOGLE_SERVICE_ACCOUNT` env var
**Scopes needed:** `spreadsheets`, `drive`
**Current Drive status:** SA's Drive quota may be near limit — avoid creating files via SA. Use OAuth (Mikhail's account) for all new Google Sheets files.
