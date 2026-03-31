# Apolio Home — Setup Report
**Date:** 2026-03-31
**Completed by:** Cowork AI Agent

---

## Results

### Bot
- **Username:** @ApolioHomeBot
- **Link:** https://t.me/ApolioHomeBot
- **Status:** Running (polling mode)

### Admin Sheets
- **File:** Apolio Home — Admin
- **URL:** https://docs.google.com/spreadsheets/d/1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk
- **Sheets:** Envelopes, Users, Config (seeded), Audit_Log

### MM Budget Envelope
- **File:** Apolio Home — MM Budget
- **URL:** https://docs.google.com/spreadsheets/d/1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ
- **Envelope ID:** MM_BUDGET
- **Limit:** 2500 EUR / month
- **Rule:** solo
- **Sheets:** Transactions, Summary, Categories (seeded), FX_Rates, Config

---

## Issues Encountered & Workarounds

### 1. Service Account Drive Storage Quota Exceeded
**Problem:** The service account `apolio-home-bot@apolio-home.iam.gserviceaccount.com` has exceeded its Google Drive storage quota. Any operation that creates a new Google Sheets file via the service account fails with `storageQuotaExceeded`.

**Affected flows:**
- `setup_admin.py` — can't create Admin file
- `tools/envelope_tools.py` → `tool_create_envelope` — bot can't create envelope files

**Workaround applied:** Both the Admin file and the MM Budget envelope were created manually via Mikhail's Google account (miroshnik0901@gmail.com), then shared with the service account as Editor. Structure was set up via a Python script using the service account credentials after sharing.

**What needs to be done manually (or fixed):** The service account's Drive quota needs to be resolved before the bot can create new envelopes on its own. Options:
- Free up space in the service account's Drive
- Switch to Mikhail's OAuth credentials for file creation (requires OAuth2 flow implementation)
- Create envelopes manually using the workaround script above

### 2. Missing Classes in Codebase
**Problem:** `sheets.py` was missing the `SheetsClient` class and `get_credentials()` function, both imported by bot.py, agent.py, and all tool files. `auth.py` was missing `SessionContext`, `LastAction`, and `get_session()`.

**Fix:** Added the missing code to `sheets.py` (appended `get_credentials()` + `SheetsClient`) and `auth.py` (appended `LastAction`, `SessionContext`, `get_session()`).

### 3. Anthropic Library Version Too Old
**Problem:** Installed version was 0.20.0, which doesn't support the `tools` parameter in `messages.create()`. The agent uses tool calling, so all AI interactions failed.

**Fix:** Upgraded to `anthropic>=0.87.0`.

### 4. MarkdownV2 Formatting in Bot Replies
**Problem:** `bot.py` sends all replies with `parse_mode="MarkdownV2"`, but the agent's responses contain unescaped characters (dots, hyphens in URLs, etc.). Telegram rejects the message with `BadRequest: Can't parse entities`.

**Status:** Not fixed (would require modifying bot.py). Bot processes requests correctly but the reply fails to send when the response contains unescaped MarkdownV2 characters. Plain text messages (like `/start`) work fine.

**What needs to be done:** Either change `parse_mode="MarkdownV2"` to `parse_mode="Markdown"` in bot.py, or add an escaping utility to the agent's response formatting.

### 5. Users Sheet Bootstrap
**Problem:** On first run, Users sheet is empty. The bot's `get_user()` check denies access to everyone, including Mikhail, even though `is_admin()` correctly recognizes MIKHAIL_TELEGRAM_ID from env.

**Fix:** Added Mikhail (telegram_id=360466156, role=admin) to the Users sheet directly via Python.

---

## Additional Fixes Applied (Session 2)

### 6. Envelopes Column `sheet_id` vs `file_id` Mismatch
**Problem:** The Envelopes sheet had a column named `sheet_id` (written during setup), but all tools (`transactions.py`, `summary.py`, `wise.py`) referenced `envelope["file_id"]`. Every tool call failed with `KeyError: 'file_id'`.

**Fix:**
- Renamed the column header in the Envelopes sheet from `sheet_id` → `file_id` via Python
- Updated `SheetsClient.register_envelope()` in `sheets.py` to write `"file_id"` key

### 7. `add_transaction` List vs Dict Interface Mismatch
**Problem:** `tools/transactions.py` builds a pre-formatted list (already includes tx_id, timestamp) and passes it to `SheetsClient.add_transaction()`, but `EnvelopeSheets.add_transaction()` expected a dict and generated its own tx_id. Result: `'list' object has no attribute 'get'`.

**Fix:** Updated `SheetsClient.add_transaction()` to detect list vs dict — if list, calls `ws.append_row(row)` directly and returns `row[0]` as tx_id; if dict, delegates to `EnvelopeSheets.add_transaction()` as before.

### 8. parse_mode Removed from bot.py
**Fix (applied in previous session):** Removed `parse_mode` argument from all `reply_text()` calls to avoid Telegram MarkdownV2/Markdown parse errors.

---

## Transaction Flow — VERIFIED WORKING ✓
- `/envelope MM_BUDGET` → sets active envelope
- "потратил 45 EUR на продукты сегодня" → agent calls `add_transaction` → row written to Transactions sheet
- "покажи расходы за март" → agent calls summary tool → returns formatted breakdown

---

## Additional Fixes Applied (Session 3)

### 9. `tool_create_envelope` — Wrong Calling Convention
**Problem:** `tools/envelopes.py` used the old 3-arg signature `(params, user_context: dict, app_context: dict)` but `agent.py` calls all tools as `(params, session: SessionContext, sheets: SheetsClient, auth: AuthManager)`. The function also accessed `app_context["admin_sheets"]`, `app_context["auth_manager"]`, etc. which don't exist in the new calling pattern.

**Fix:** Rewrote `tool_create_envelope` with the correct 4-arg signature matching all other tools. Also fixed the `"sheet_id"` → `"file_id"` key bug in the `register_envelope` call.

### 10. OAuth Envelope Creation — Fully Working
**Status:** ✅ Verified. `tool_create_envelope` with `name="Семья"` created a new Google Sheets file in Mikhail's Drive via OAuth, built all sheets from template, seeded Config, and registered in Admin.

**Test sheet:** https://docs.google.com/spreadsheets/d/1UNhBQqM5L0fhFMef_f6y-QBYrGAK0csCsLksnAwi-So

### 11. Cyrillic Slug Support in `_slugify()`
**Problem:** `_slugify("Семья")` returned `"_____"` — all Cyrillic characters were stripped.

**Fix:** Added full Russian + Ukrainian Cyrillic transliteration table (а→a, б→b, ... я→ya, і→i, ї→yi, є→ye, ґ→g) before the ASCII-only regex filter.

---

## What Still Needs to Be Done

1. **Deploy to Railway** — bot currently runs in local polling mode. Deployment to Railway (or Hetzner) with a webhook URL is needed for production.

2. **Set WEBHOOK_URL in .env** — leave empty for local polling, set for production deployment.

---

## .env Summary

```
TELEGRAM_BOT_TOKEN=✓ set
ANTHROPIC_API_KEY=✓ set
OPENAI_API_KEY=✓ set
GOOGLE_SERVICE_ACCOUNT=✓ set (apolio-home-bot@apolio-home.iam.gserviceaccount.com)
ADMIN_SHEETS_ID=1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk
MIKHAIL_TELEGRAM_ID=360466156
WEBHOOK_URL=(empty — polling mode)
PORT=8080
```
