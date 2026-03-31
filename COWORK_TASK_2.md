# Apolio Home — Technical Task v2
**Date:** 2026-04-01
**Priority:** All items mandatory before next deployment

Read SETUP_REPORT.md first. This task references it heavily.

---

## Context

Single active envelope: MM_BUDGET (file_id: 1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ)
Bot: @ApolioHomeBot, deployed on Railway (worker, polling mode)
Admin sheet: 1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk
Python: 3.12 (do NOT upgrade — breaks PTB 20.7)

---

## TASK 1 — Persistent Session (session survives bot restart)

**Problem:** `_sessions` dict in `auth.py` is in-memory. After Railway restart/deploy,
all users lose their `current_envelope_id` and must re-select.

**Fix:** Auto-assign `MM_BUDGET` as default envelope in `get_session()` when
`current_envelope_id` is None AND user is admin (Mikhail).

**Implementation in `auth.py`, function `get_session()`:**

```python
def get_session(user_id: int, user_name: str, role: str) -> SessionContext:
    if user_id not in _sessions:
        session = SessionContext(user_id, user_name, role)
        # Auto-set default envelope for admin after restart
        if role == "admin":
            session.current_envelope_id = "MM_BUDGET"
        _sessions[user_id] = session
    else:
        _sessions[user_id].user_name = user_name
        _sessions[user_id].role = role
        # If envelope was lost (e.g. after process restart via shared state),
        # restore default for admin
        if not _sessions[user_id].current_envelope_id and role == "admin":
            _sessions[user_id].current_envelope_id = "MM_BUDGET"
    return _sessions[user_id]
```

Also add a `DEFAULT_ENVELOPE` constant at top of `auth.py`:
```python
DEFAULT_ENVELOPE = "MM_BUDGET"
```

**Test:** Stop and restart the bot. Send "статус" without selecting envelope first.
Should respond with MM_BUDGET status, not "envelope not selected" error.

---

## TASK 2 — Telegram Persistent Menu (no need to type /start)

**Problem:** Telegram's bottom menu only shows slash-commands. User must type /start
or a command to see the menu. For a bot used daily, the UX should be immediate.

**What to do:**

### 2a. Keep the existing slash-command menu (already working)
`post_init` already registers commands. Do NOT remove this.

### 2b. Add a persistent Reply Keyboard (always visible at bottom of chat)
This is different from InlineKeyboard. A `ReplyKeyboardMarkup` with `resize_keyboard=True`
stays visible in the chat input area permanently, like a phone keyboard.

Add to `bot.py` — new constant:
```python
from telegram import ReplyKeyboardMarkup, KeyboardButton

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📊 Статус"), KeyboardButton("📋 Отчёт")],
        [KeyboardButton("💰 Добавить расход"), KeyboardButton("📁 Конверты")],
        [KeyboardButton("❓ Помощь")],
    ],
    resize_keyboard=True,
    is_persistent=True,  # stays visible even when user types
)
```

Modify `cmd_start` to send this keyboard:
```python
await update.message.reply_text(
    "...", 
    parse_mode=ParseMode.MARKDOWN,
    reply_markup=MAIN_KEYBOARD,  # <-- add this
)
```

Also modify `handle_message` to intercept keyboard button texts:

```python
# At the start of handle_message, before other logic:
KEYBOARD_SHORTCUTS = {
    "📊 Статус": lambda s: f"покажи статус бюджета для конверта {s.current_envelope_id}",
    "📋 Отчёт": lambda s: f"покажи отчёт по категориям за текущий месяц для конверта {s.current_envelope_id}",
    "📁 Конверты": lambda s: "list_envelopes",
    "💰 Добавить расход": lambda s: "ADD_EXPENSE_PROMPT",
    "❓ Помощь": lambda s: "HELP",
}

text = msg.text or ""
if text in KEYBOARD_SHORTCUTS:
    fn = KEYBOARD_SHORTCUTS[text]
    shortcut = fn(session)
    if shortcut == "ADD_EXPENSE_PROMPT":
        await update.message.reply_text(
            "Напишите расход в свободной форме:\n"
            "Например: «кофе 3.50» или «продукты 85 EUR Esselunga»"
        )
        return
    elif shortcut == "HELP":
        await cmd_help(update, ctx)
        return
    elif shortcut == "list_envelopes":
        await cmd_envelopes(update, ctx)
        return
    else:
        text = shortcut  # pass to agent
```

### 2c. Verify Telegram Bot Menu Button
Set the bot's menu button to open commands via BotFather:
In BotFather: /mybots → @ApolioHomeBot → Bot Settings → Menu Button
Set it to show the command list (this is the "/" button in chat).

This is a one-time manual step — note in report when done.

---

## TASK 3 — OAuth Credentials in Railway

**Problem:** `create_spreadsheet_as_owner()` in `sheets.py` requires OAuth env vars
not yet set in Railway. Without them, new envelopes are created in SA's Drive.

**What to do:**

### 3a. Get OAuth credentials
Run locally:
```bash
cd apolio-home
python get_oauth_token.py
```
This will open a browser for Google OAuth consent. After approval, it prints:
- GOOGLE_OAUTH_CLIENT_ID
- GOOGLE_OAUTH_CLIENT_SECRET  
- GOOGLE_OAUTH_REFRESH_TOKEN

### 3b. Add to Railway
Go to Railway project → apolio-home-bot → Variables → Add:
- GOOGLE_OAUTH_CLIENT_ID = <value>
- GOOGLE_OAUTH_CLIENT_SECRET = <value>
- GOOGLE_OAUTH_REFRESH_TOKEN = <value>

### 3c. Also add to local .env
Same three variables to `.env` file.

### 3d. Test
Send to bot: "создай конверт Тест лимит 100 EUR"
Verify the new Google Sheet appears in Mikhail's Drive (miroshnik0901@gmail.com)
under My Drive, NOT in a service account's Drive.
Delete the test envelope from Admin sheet and the test file from Drive after verification.

---

## TASK 4 — MM Budget Sheet: Simplify Structure + Add Formulas + Formatting

**Problem:** The current MM Budget sheet has 16 columns in Transactions.
When editing manually, user must fill: ID, Date, Envelope, Amount_Orig, Currency_Orig,
Amount_EUR, Category, Subcategory, Who, Account, Type, Note, Source, Wise_ID, Created_At, Deleted.
That's 16 fields — most of which are auto-populated by the bot. But for manual editing
it's confusing and error-prone.

### 4a. Reorganize Transactions sheet for human readability

**New column order** (reorganized so the most-used columns are leftmost):

| Col | Name | Notes |
|-----|------|-------|
| A | Date | Editable. Format: YYYY-MM-DD |
| B | Amount_Orig | Editable. The raw amount |
| C | Currency_Orig | Editable. Dropdown: EUR/PLN/UAH/GBP/USD |
| D | Category | Editable. Dropdown from Categories sheet |
| E | Subcategory | Editable. Dependent dropdown |
| F | Note | Editable. Free text |
| G | Who | Editable. Dropdown: Mikhail/Marina/Joint |
| H | Amount_EUR | AUTO. Formula (see below) |
| I | Type | AUTO. Default "expense". Dropdown: expense/income/transfer |
| J | Account | Editable (optional). Dropdown from Accounts tab |
| K | ID | AUTO. Generated by bot. Hidden by default |
| L | Envelope | AUTO. Always "MM_BUDGET". Hidden |
| M | Source | AUTO. "bot" or "manual". Hidden |
| N | Wise_ID | AUTO. From CSV import. Hidden |
| O | Created_At | AUTO. Timestamp. Hidden |
| P | Deleted | AUTO. FALSE/TRUE. Hidden |

**Key change:** User only needs to fill columns A–G (7 fields).
Columns H–P are auto-populated or hidden.

**Implementation steps:**

1. Open MM Budget sheet (https://docs.google.com/spreadsheets/d/1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ)
2. Reorganize column headers to match the new order above
3. Move existing data (if any) to match new column positions
4. IMPORTANT: Update `transactions.py` — the `row` list in `tool_add_transaction`
   must match the new column order:

```python
row = [
    date,           # A - Date
    amount,         # B - Amount_Orig
    currency,       # C - Currency_Orig
    category,       # D - Category
    subcategory,    # E - Subcategory
    note,           # F - Note
    who,            # G - Who
    amount_eur,     # H - Amount_EUR
    tx_type,        # I - Type
    account,        # J - Account
    tx_id,          # K - ID
    envelope["ID"], # L - Envelope
    "bot",          # M - Source
    "",             # N - Wise_ID
    now,            # O - Created_At
    "FALSE",        # P - Deleted
]
```

Also update `edit_transaction`, `delete_transaction`, and `get_transactions`
in `sheets.py` and `transactions.py` to use column names (not positions)
for all lookups — so future column reordering doesn't break things.
Use `headers = ws.row_values(1)` + `headers.index(field)` approach (already in edit_transaction).

5. Update `SheetsClient.add_transaction()` in `sheets.py` to accept list and use
   `append_row` as it does now — no changes needed there.

### 4b. Add Amount_EUR formula

In Transactions sheet, column H (Amount_EUR), add formula for all existing rows
and set it as the default for new rows:

```
=IF(C2="EUR", B2, IFERROR(B2 / VLOOKUP(TEXT(A2,"YYYY-MM"), FX_Rates!$A:$F, MATCH(C2, FX_Rates!$1:$1, 0), 0), "FX_MISSING"))
```

Set this formula in H2 and extend it down to H1000.

**IMPORTANT:** The bot (`tool_add_transaction`) currently calculates `amount_eur`
in Python and writes the value directly. Keep this behavior (write the calculated value).
The formula is a fallback for rows added manually where Amount_EUR is left blank.
Do NOT change the bot to rely on formula evaluation — gspread reads cell values, not formula results.

### 4c. Add data validation (dropdowns)

Use Google Sheets API (via gspread or googleapiclient) to add data validation:

**Column C (Currency_Orig):** Dropdown list: EUR, PLN, UAH, GBP, USD
**Column D (Category):** Dropdown from Categories!$A:$A
**Column G (Who):** Dropdown list: Mikhail, Marina, Joint
**Column I (Type):** Dropdown list: expense, income, transfer

Python code using gspread to set validation (run once):
```python
import gspread
from gspread.utils import rowcol_to_a1

def set_dropdown(ws, col_letter, row_start, row_end, values_list=None, range_ref=None):
    """Set dropdown validation on a column range."""
    from googleapiclient.discovery import build
    # Use Sheets API v4 directly for validation
    spreadsheet_id = ws.spreadsheet.id
    ...
```

Use the Sheets API v4 `batchUpdate` with `setDataValidation` request.
Refer to: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#SetDataValidationRequest

### 4d. Hide technical columns

Hide columns K through P (ID, Envelope, Source, Wise_ID, Created_At, Deleted)
using Sheets API `updateDimensionProperties` with `hiddenByUser: true`.

These columns are still writable by the bot but invisible to the user during manual editing.

### 4e. Freeze rows and columns

- Freeze row 1 (headers)
- Freeze column A (Date) — so when scrolling right, date is always visible

### 4f. Add conditional formatting

- Row highlighted light red if Amount_EUR = "FX_MISSING"
- Row highlighted light gray if Deleted = TRUE
- Column H (Amount_EUR) formatted as number with 2 decimal places, EUR symbol

### 4g. Column widths

Set sensible column widths:
- A (Date): 120px
- B (Amount_Orig): 100px
- C (Currency): 80px
- D (Category): 150px
- E (Subcategory): 150px
- F (Note): 250px
- G (Who): 100px
- H (Amount_EUR): 120px

### 4h. Summary sheet

Add a proper Summary sheet that auto-calculates from Transactions:

Row per month. Columns:
| Month | Total_Expenses | Total_Income | Balance | Housing | Food | Transport | Health | Entertainment | Personal | Other |

Each cell uses QUERY or SUMIFS formula. Example for Total_Expenses:
```
=SUMPRODUCT((TEXT(Transactions!A2:A1000,"YYYY-MM")=A2)*(Transactions!I2:I1000="expense")*(Transactions!P2:P1000="FALSE")*(Transactions!H2:H1000))
```

Populate rows for Jan 2026 through Dec 2026 automatically.
Add a chart: bar chart of monthly expenses by category, placed in Summary sheet.

### 4i. Add "Accounts" sheet

Headers: Account, Owner, Currency, Description, Active

Pre-fill with:
```
Wise Family | Joint | EUR | Семейный счёт Wise | TRUE
Wise Mikhail | Mikhail | EUR | Личный счёт Михаила | TRUE
Cash IT | Mikhail | EUR | Наличные Италия | TRUE
Cash PL | Mikhail | PLN | Наличные Польша | TRUE
```

Add dropdown for Account column J in Transactions from Accounts!$A:$A.

---

## TASK 5 — Admin Sheet: Settings and User Management

**Problem:** Admin sheet has Config tab with raw key/value pairs.
This is hard to manage. Need proper structure for settings and user permissions.

### 5a. Restructure Config sheet

Current Config is key/value rows. Keep this format (bot reads it).
But add a "Settings" section with clear grouping. Add comment column:

| Key | Value | Description |
|-----|-------|-------------|
| alert_threshold_pct | 80 | Alert when spending reaches X% of monthly budget |
| default_currency | EUR | Default currency for new transactions |
| fx_fallback | nearest | FX rate fallback: nearest or previous month |
| budget_MM_BUDGET_monthly | 2500 | Monthly cap for MM Budget envelope |
| default_envelope | MM_BUDGET | Default envelope for admin user |
| bot_version | 2.0 | Current bot version |

Add column C header "Description" and fill in descriptions for each row.
Format row 1 as bold header.

### 5b. Restructure Users sheet

Current headers: `telegram_id, name, role, envelopes, created_at`

Add columns:
```
telegram_id | name | role | envelopes | language | status | notes | created_at | updated_at
```

New columns:
- `language`: RU/UK/EN/IT — preferred language for reports (default RU)
- `status`: active/suspended — to temporarily block without deleting
- `notes`: free text for admin use

Pre-fill Mikhail's row:
```
360466156 | Mikhail | admin | MM_BUDGET | RU | active | Owner | <created> | <now>
```

### 5c. Add Audit_Log formatting

Format Audit_Log sheet:
- Row 1: bold headers, frozen
- Alternating row colors (light gray / white)
- Column widths: Timestamp 180px, rest auto
- Sort by timestamp descending (newest first) — NOTE: this is a visual sort only,
  new rows are always appended at bottom. Add a note/instruction at top:
  "New rows appended at bottom. Use Data → Sort to see latest."

### 5d. Update AuthManager to read new Users sheet columns

In `auth.py`, `_reload()` method — add reading of `language` and `status`:

```python
for u in users:
    tid = int(u.get("telegram_id", 0))
    if not tid:
        continue
    # Skip suspended users
    if u.get("status", "active").lower() == "suspended":
        continue
    envelopes = [e.strip() for e in str(u.get("envelopes", "")).split(",") if e.strip()]
    self._cache[tid] = {
        "id": tid,
        "name": u.get("name", ""),
        "role": u.get("role", "readonly"),
        "envelopes": envelopes,
        "language": u.get("language", "RU"),
        "status": u.get("status", "active"),
    }
```

---

## TASK 6 — Bot Functionality: Analysis and Improvements

Based on analysis of best budget Telegram bots (Wallet, CoinKeeper, MoneyManager,
Spendee), implement the following improvements:

### 6a. Quick expense entry — inline buttons after adding transaction

When the agent successfully adds a transaction, send a follow-up message with
action buttons:

```
✓ Groceries · 85 EUR · Mikhail · today

[✏ Edit] [🗑 Delete] [📊 Status]
```

Implementation: After `tool_add_transaction` returns successfully, the agent
response includes the tx_id. Bot detects this and appends inline keyboard.

Modify `handle_message` in `bot.py`:
```python
response = await agent.run(text, session, ...)

# Check if response contains a successful add
if "✓" in response and session.last_action and session.last_action.action == "add":
    tx_id = session.last_action.tx_id
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✏ Изменить", callback_data=f"cb_edit_{tx_id}"),
        InlineKeyboardButton("🗑 Удалить", callback_data=f"cb_del_{tx_id}"),
        InlineKeyboardButton("📊 Статус", callback_data="cb_status"),
    ]])
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN,
                                     reply_markup=keyboard)
else:
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)
```

Add handlers in `callback_handler`:
```python
elif data.startswith("cb_del_"):
    tx_id = data[7:]
    # Ask for confirmation
    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"cb_del_confirm_{tx_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data="cb_cancel"),
        ]])
    )

elif data.startswith("cb_del_confirm_"):
    tx_id = data[15:]
    # Execute soft delete
    ...

elif data == "cb_cancel":
    await query.edit_message_reply_markup(reply_markup=None)

elif data.startswith("cb_edit_"):
    tx_id = data[8:]
    await query.edit_message_text(
        f"Что изменить в записи `{tx_id}`? Напишите например:\n"
        f"«сумма 90» или «категория транспорт» или «дата вчера»",
        parse_mode=ParseMode.MARKDOWN,
    )
    # Store pending edit in session
    session.pending_edit_tx = tx_id
```

### 6b. Monthly report as formatted table

When user asks for report, format response as a proper table with bars:

```
📊 Апрель 2026 — MM Budget

Потрачено: 1,840 EUR из 2,500 EUR (74%)
[████████░░░░░░] 

🏠 Жильё        1,200  ████████  65%
🍕 Еда            380  ███       21%
🚗 Транспорт      180  ██        10%
💊 Здоровье        80  █          4%

vs Март: +8% ↑  |  Осталось: 660 EUR
```

Implement `format_report()` in a new file `reports.py`:

```python
CATEGORY_EMOJI = {
    "Housing": "🏠", "Food": "🍕", "Transport": "🚗",
    "Health": "💊", "Entertainment": "🎬", "Personal": "👤",
    "Household": "🔧", "Education": "🎓", "Other": "📦",
    "Income": "💰", "Transfer": "↔️",
}

def format_bar(pct: float, width: int = 8) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

def format_report(summary: dict) -> str:
    ...
```

Call `format_report` in agent response processing. The agent should return structured
data (already does via `tool_get_summary`), and `reports.py` formats it for Telegram.

### 6c. Undo command

Add `/undo` command that reverses the last action in the session:

```python
async def cmd_undo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tg_user, session = _require_user(update)
    if not session.last_action:
        await update.message.reply_text("Нет действий для отмены.")
        return
    
    la = session.last_action
    if la.action == "add":
        # Soft-delete the added transaction
        ...
        await update.message.reply_text(f"✓ Отменено: {la.snapshot}")
    elif la.action == "edit":
        # Revert to old value
        ...
    
    session.last_action = None
```

Register handler: `app.add_handler(CommandHandler("undo", cmd_undo))`
Add to BOT_COMMANDS: `BotCommand("undo", "Отменить последнее действие")`

### 6d. Weekly summary — automatic

Every Monday at 09:00 (Europe/Rome timezone), send Mikhail a weekly summary.

Use `APScheduler` or `python-telegram-bot`'s `JobQueue`:

```python
from telegram.ext import JobQueue
import pytz

async def weekly_summary(context):
    """Sends weekly summary to Mikhail every Monday 09:00 Rome time."""
    mikhail_id = int(os.environ.get("MIKHAIL_TELEGRAM_ID", 0))
    if not mikhail_id:
        return
    
    # Get current week summary
    session = get_session(mikhail_id, "Mikhail", "admin")
    session.current_envelope_id = "MM_BUDGET"
    
    from agent import ApolioAgent
    agent_instance = ApolioAgent(sheets, auth)
    text = await agent_instance.run(
        "покажи краткий отчёт по расходам за эту неделю",
        session
    )
    await context.bot.send_message(chat_id=mikhail_id, text=text,
                                    parse_mode=ParseMode.MARKDOWN)

# In post_init:
async def post_init(app: Application):
    await app.bot.set_my_commands(BOT_COMMANDS)
    
    # Schedule weekly summary: every Monday at 09:00 Rome time
    rome_tz = pytz.timezone("Europe/Rome")
    app.job_queue.run_daily(
        weekly_summary,
        time=datetime.time(9, 0, tzinfo=rome_tz),
        days=(0,),  # Monday = 0 in PTB
    )
```

Add to requirements.txt: `pytz==2024.1`

### 6e. /week and /month shortcuts

```python
async def cmd_week(update, ctx):
    """Quick report for current week"""
    ...

async def cmd_month(update, ctx):
    """Quick report for current month — same as /report"""
    ...
```

Register both commands. Add to BOT_COMMANDS:
- `BotCommand("week", "Расходы за эту неделю")`
- `BotCommand("month", "Расходы за этот месяц")`

---

## TASK 7 — Code Quality Fixes

### 7a. Fix `SYSTEM_PROMPT` envelope auto-routing bug

In `agent.py`, the system prompt says to route Polina keywords to "Polina envelope"
but this envelope doesn't exist. Change the instruction:

```python
SYSTEM_PROMPT = """...
ENVELOPE ROUTING:
- If message contains: Polina, Поліна, Полина, дочка, daughter, Bergamo, liceo
  → inform user that Polina envelope is not yet created, ask if they want to create it
- All other messages → use current_envelope_id: {envelope_id}
..."""
```

### 7b. Add error handling for missing envelope

In `tool_add_transaction`, if `session.current_envelope_id` is None or not found:
Return clear error message in Russian:
```python
if not env_id:
    return {"error": "Конверт не выбран. Используйте /envelope для выбора."}
```

### 7c. Improve Sheets caching

`get_transactions` reads all records from Sheets every call. For status and report
within the same minute, this is redundant. Add a simple 60-second cache:

```python
class SheetsCache:
    def __init__(self, ttl_seconds=60):
        self._cache = {}
        self._timestamps = {}
        self.ttl = ttl_seconds
    
    def get(self, key):
        if key in self._cache:
            if time.time() - self._timestamps[key] < self.ttl:
                return self._cache[key]
        return None
    
    def set(self, key, value):
        self._cache[key] = value
        self._timestamps[key] = time.time()
    
    def invalidate(self, key=None):
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()
```

Add `_cache = SheetsCache()` to `SheetsClient`.
Use in `get_transactions`: check cache first, invalidate on `add_transaction`.

### 7d. Fix ParseMode in reports

All `reply_text` calls use `ParseMode.MARKDOWN`. For formatted reports with
special characters (parentheses, dashes, dots), switch to `ParseMode.MARKDOWN`
but escape problem characters, OR use `ParseMode.HTML` for reports specifically.

Create helper in `reports.py`:
```python
def to_html(text: str) -> str:
    """Convert simple markdown-style text to HTML for Telegram."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r'\*(.+?)\*', r'<b>\1</b>', text)
    text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text
```

Use `parse_mode=ParseMode.HTML` for report messages, `ParseMode.MARKDOWN` for
short confirmations.

---

## TASK 8 — Deploy and Verify

After all code changes:

1. Commit all changes with message: "v2: persistent sessions, persistent menu,
   OAuth env, sheet restructure, admin improvements, bot UX"

2. Push to main branch → Railway auto-deploys

3. Add OAuth env vars to Railway (from Task 3)

4. Test sequence:
   a. Send /start → should show welcome + reply keyboard at bottom
   b. Press "📊 Статус" button → should show MM_BUDGET status without selecting envelope
   c. Send "кофе 5 EUR" → should add transaction + show edit/delete buttons
   d. Press "🗑 Удалить" → should ask confirmation
   e. Send voice: "потратил сорок пять евро на продукты" → should transcribe + add
   f. Send /report → should show formatted report with bars
   g. Send /undo → should undo last action
   h. Kill and restart bot process → send "статус" → should still show MM_BUDGET status

5. Verify Transactions sheet manually:
   - Open MM Budget sheet
   - Check columns A-G visible, H-P hidden
   - Check dropdowns work on C, D, G, I
   - Add a row manually with only A-G filled
   - Verify H (Amount_EUR) fills via formula
   - Check Summary sheet has formulas and chart

---

## TASK 9 — Report

Update SETUP_REPORT.md after all tasks are complete:
- Update section 10 (Known Issues) — mark fixed items as resolved
- Add section 16: Changes made in this session
- Add all new Railway env vars to section 5
- Update section 8 (Bot Commands) with new /undo, /week, /month

---

## Files to modify

- `auth.py` — Tasks 1, 5d
- `bot.py` — Tasks 2, 6a, 6b, 6c, 6d, 6e
- `agent.py` — Tasks 7a, 7b
- `sheets.py` — Tasks 7c, 4a (column order constant)
- `tools/transactions.py` — Task 4a (new column order in row list)
- `tools/summary.py` — no changes needed
- `tools/envelope_tools.py` — Task 7a (Polina routing)
- `reports.py` — Task 6b, 7d (new file, create it)
- `requirements.txt` — add pytz
- `SETUP_REPORT.md` — Task 9

## Files to NOT modify
- `tools/wise.py`
- `tools/fx.py`
- `tools/config_tools.py`
- `setup_admin.py`
- `test_bot.py`
- `encode_service_account.py`
- `get_telegram_id.py`
