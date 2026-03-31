# Apolio Home — Cowork Setup Task

## Project folder
/Users/michaelhome/Library/CloudStorage/GoogleDrive-miroshnik0901@gmail.com/My Drive/Personal/AI/apolio-home

## Known values (do not ask user for these)
- Mikhail's Telegram: @miroshnik0901
- Mikhail's Telegram ID: 360466156
- Google account: miroshnik0901@gmail.com
- Project name: Apolio Home

---

## Your job

Complete the full setup of Apolio Home bot. Do everything autonomously.
Open browser when needed. Use Terminal for commands.
Update `.env` file as you get each value.

---

## Step 1 — Create Telegram Bot

1. Open browser → https://t.me/BotFather
2. Send: /newbot
3. Name: Apolio Home
4. Username: ApolioHomeBot (or ApolioHome_Bot if taken)
5. Copy the token
6. Write to `.env`: TELEGRAM_BOT_TOKEN=<token>

---

## Step 2 — Get API keys

### Anthropic
1. Open https://console.anthropic.com/settings/keys
2. Create new key named "apolio-home"
3. Copy key
4. Write to `.env`: ANTHROPIC_API_KEY=<key>

### OpenAI
1. Open https://platform.openai.com/api-keys
2. Create new key named "apolio-home"
3. Copy key
4. Write to `.env`: OPENAI_API_KEY=<key>

---

## Step 3 — Google Cloud Setup

1. Open https://console.cloud.google.com
2. Create new project: "apolio-home"
3. Enable APIs:
   - Go to APIs & Services → Library
   - Search "Google Sheets API" → Enable
   - Search "Google Drive API" → Enable

4. Create Service Account:
   - IAM & Admin → Service Accounts → Create Service Account
   - Name: apolio-home-bot
   - Role: Editor
   - Create and download JSON key
   - Save the JSON file to: /Users/michaelhome/Downloads/apolio-home-sa.json

5. Encode credentials:
   Open Terminal:
   ```
   cd "/Users/michaelhome/Library/CloudStorage/GoogleDrive-miroshnik0901@gmail.com/My Drive/Personal/AI/apolio-home"
   python3 encode_service_account.py /Users/michaelhome/Downloads/apolio-home-sa.json
   ```
   Copy the encoded value → write to `.env`: GOOGLE_SERVICE_ACCOUNT=<encoded>

---

## Step 4 — Install dependencies

Open Terminal:
```bash
cd "/Users/michaelhome/Library/CloudStorage/GoogleDrive-miroshnik0901@gmail.com/My Drive/Personal/AI/apolio-home"
pip3 install -r requirements.txt
```

---

## Step 5 — Write known values to .env

Write these to `.env`:
```
MIKHAIL_TELEGRAM_ID=360466156
PORT=8080
```
Leave WEBHOOK_URL empty for now (local polling mode).

---

## Step 6 — Create Admin Google Sheets file

In Terminal:
```bash
cd "/Users/michaelhome/Library/CloudStorage/GoogleDrive-miroshnik0901@gmail.com/My Drive/Personal/AI/apolio-home"
python3 setup_admin.py
```

This will:
- Create "Apolio Home — Admin" spreadsheet in Google Drive
- Set up all sheets (Envelopes, Users, Config, Audit_Log)
- Automatically write ADMIN_SHEETS_ID to .env

---

## Step 7 — Run system check

In Terminal:
```bash
python3 test_bot.py
```

All 6 checks must pass. Fix any failures before continuing.

---

## Step 8 — Start bot

In Terminal:
```bash
python3 bot.py
```

Bot starts in polling mode.

---

## Step 9 — Test bot

Open https://t.me/ApolioHomeBot (or whatever username was created)
Send: /start

Expected response:
```
👋 Apolio Home

You have access to: (none yet)
Just send me a message, voice, or photo of a receipt.
```

---

## Step 10 — Create first Envelope via bot

Send to bot:
```
создай конверт "MM Budget" с лимитом 2500 EUR, правило solo
```

Bot should:
- Create new Google Sheets file "Apolio Home — MM Budget"
- Register it in Admin
- Reply with link to the file

---

## Step 11 — Report back

When complete, write a summary file:
/Users/michaelhome/Library/CloudStorage/GoogleDrive-miroshnik0901@gmail.com/My Drive/Personal/AI/apolio-home/SETUP_REPORT.md

Include:
- Bot username and link
- Admin Sheets URL
- MM Budget Sheets URL
- Any issues encountered
- What still needs to be done manually

---

## Notes
- If any browser step requires 2FA or phone verification, stop and note it in the report
- If a service requires payment info to get API key, skip it and note in report
- .env file is at: /Users/michaelhome/Library/CloudStorage/GoogleDrive-miroshnik0901@gmail.com/My Drive/Personal/AI/apolio-home/.env
- All code is already written — do not modify any .py files
- If test_bot.py fails on a step, debug and fix before proceeding
