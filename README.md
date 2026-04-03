# Apolio Home — Setup Guide

## What's built

```
apolio-home/
├── bot.py           # Telegram bot, entry point
├── agent.py         # Claude AI agent with tool use
├── db.py            # PostgreSQL layer (conversation log, user context)
├── auth.py          # Authorization manager
├── sheets.py        # Google Sheets client (Admin + Envelope)
├── tools/
│   ├── transactions.py   # add/edit/delete/find
│   ├── summary.py        # get_summary, get_budget_status
│   ├── config_tools.py   # update_config, add/remove users
│   ├── fx.py             # set_fx_rate
│   ├── wise.py           # Wise CSV import
│   └── envelopes.py      # create_envelope (full Google Sheets setup)
├── requirements.txt
├── Procfile
└── .env.example
```

---

## Step 1: Telegram Bot

1. Open Telegram → find @BotFather → /newbot
2. Follow prompts, get TOKEN
3. Save as `TELEGRAM_BOT_TOKEN`

To get your Telegram ID: message @userinfobot

---

## Step 2: Google Cloud Service Account

1. Go to console.cloud.google.com
2. Create project "Apolio Home"
3. Enable: Google Sheets API + Google Drive API
4. IAM & Admin → Service Accounts → Create
5. Download JSON key
6. Base64 encode:
   ```
   base64 -i service_account.json | tr -d '\n'
   ```
7. Save result as `GOOGLE_SERVICE_ACCOUNT`

---

## Step 3: Admin Google Sheets file

1. Create new Google Sheets at sheets.google.com
2. Name it "Apolio Home — Admin"
3. Create these sheets (tabs):
   - **Envelopes** — headers: ID, Name, sheet_id, Owner_TG, Currency, Monthly_Cap, Split_Rule, Active, Created_At
   - **Users** — headers: telegram_id, name, role, envelopes, created_at
   - **Config** — headers: Key, Value
   - **Audit_Log** — headers: Timestamp, Telegram_ID, Name, Action, Details
4. Share the file with your service account email (Editor access)
5. Copy the Spreadsheet ID from URL → save as `ADMIN_SHEETS_ID`

---

## Step 4: Seed Config sheet

Add these rows to Config sheet:
```
alert_threshold_pct  |  80
fx_fallback          |  nearest
```

---

## Step 5: Environment variables

Copy `.env.example` to `.env` and fill in:
```
TELEGRAM_BOT_TOKEN=your_token
ANTHROPIC_API_KEY=your_key
OPENAI_API_KEY=your_key
GOOGLE_SERVICE_ACCOUNT=base64_encoded_json
ADMIN_SHEETS_ID=spreadsheet_id
MIKHAIL_TELEGRAM_ID=your_telegram_id
PORT=8080
```

---

## Step 6: Run locally

```bash
cd apolio-home
pip install -r requirements.txt
python bot.py
```

Bot will start in polling mode (no WEBHOOK_URL needed locally).

---

## Step 7: Create first Envelope via bot

Message your bot:
```
создай конверт "MM Budget" с лимитом 2500 EUR, правило solo
```

Bot will:
- Create Google Sheets file automatically
- Set up all sheets with correct structure
- Register in Admin
- Return link to the file

---

## Step 8: Deploy to Railway

1. railway.app → New Project → Deploy from GitHub
2. Add environment variables in Railway dashboard
3. Set `WEBHOOK_URL=https://your-app.railway.app`
4. Deploy

## Step 9: Add PostgreSQL (conversation history + user context)

1. In Railway dashboard → your project → **+ New** → **Database** → **PostgreSQL**
2. Railway auto-creates `DATABASE_URL` variable and links it to your service
3. Verify: go to service **Variables** tab → `DATABASE_URL` should be set
4. Redeploy — bot will auto-create tables (`conversation_log`, `user_context`) on startup
5. Check logs for: `[DB] PostgreSQL connected, tables ready`

Data architecture:
- **PostgreSQL** (Railway): conversation history, user goals, patterns, preferences
- **Google Sheets**: transactions, budgets, reports (human-accessible)

---

## Usage examples

```
кофе 3.50                          → adds expense Food·Coffee 3.50 EUR
заплатив 200 злотих за продукти    → adds expense Food·Groceries 200 PLN with conversion
это для Полины — школа 380 евро    → adds to Polina envelope
[photo of receipt]                  → extracts and adds automatically
[voice message]                     → transcribes and adds
отчёт за март                      → monthly summary
сколько осталось                   → budget status
/adduser 123456 Marina contributor MM
```
