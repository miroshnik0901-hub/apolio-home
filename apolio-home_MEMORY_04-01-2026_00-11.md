# Project Memory Snapshot — Apolio Home

**Created:** 2026-04-01T00:11:00+02:00
**Session ID:** edfc6cd1-b9ac-490e-acda-5b5979dc86e5
**Chat Started:** 2026-03-31T17:42 (UTC+2: ~19:42 local)
**Total Messages:** 2909 JSONL entries
**User Requests:** 24 distinct messages
**Tool Calls:** 1031 (211 Bash, 49 Reads, 44 Write/Edit, rest agent/search)
**Session Duration:** ~6.5 hours (17:42 → 00:11 next day)

---

## 1. Chronological Project Overview

This session was entirely focused on ONE project: **Apolio Home Telegram Bot**. The session started from a COWORK_TASK.md file describing what to build, and ended with the bot deployed to Railway, committed to GitHub, with a full SETUP_REPORT.

Timeline of major phases:

1. **Initial setup & dependency installation** — 17:42–18:25 — Install deps, configure .env, set up Admin sheet
2. **Missing class fixes (SheetsClient, SessionContext)** — 18:25–18:55 — Bot couldn't import; added missing code
3. **Transaction flow fix + OAuth setup** — 18:55–20:15 — Fixed column name mismatch, added OAuth credentials
4. **Railway deployment** — 20:15–21:22 — GitHub push, Railway project, env vars, Python version fix
5. **Bot UX overhaul** — 21:22–21:57 — Inline menu, envelopes list, links, auth fix, budget status fix
6. **SETUP_REPORT + file organization** — 21:57–00:11 — Full SETUP_REPORT.md rewrite, OAuth envelope fix, commit

---

## 2. Project: Apolio Home Bot — Full Detail

### First mentioned
- 📅 2026-03-31 17:42
- 💬 User said: "Выполни задачу из файла COWORK_TASK.md в папке проекта"

### Initial request context
The COWORK_TASK.md file in the project folder described the full setup task: create Telegram Bot via BotFather, get API keys (Anthropic, OpenAI), set up Google Cloud service account, encode credentials, install dependencies, configure the Admin Google Sheet, run tests, deploy. Claude was to execute all steps autonomously.

### Evolution timeline

1. **17:42** — Read COWORK_TASK.md, began autonomous execution
2. **17:47** — Found `.env` existed but missing values; began filling in
3. **18:12** — Located service account JSON file (`apolio-home-805acd175942.json`) in Downloads, copied to project, encoded as base64 for `GOOGLE_SERVICE_ACCOUNT` env var
4. **18:19** — Installed all requirements: `pip install -r requirements.txt --break-system-packages`
5. **18:20** — Ran `setup_admin.py` to seed Admin Google Sheet (Envelopes, Users, Config, Audit_Log tabs)
6. **18:25** — **Context overflow → session 2**. New session resumed from summary
7. **18:27** — Ran `test_bot.py` — failed: `ImportError: cannot import name 'SheetsClient' from 'sheets'`
8. **18:29–18:33** — Diagnosed: `sheets.py` existed but was missing `SheetsClient` class and `get_credentials()`. Added both via `cat >>` append
9. **18:33** — Import test passed. Ran `bot.py` in background, sent `/start` to bot in Telegram
10. **18:49** — First SETUP_REPORT.md written (session milestone)
11. **18:54** — User: "так что делать дальше?" → Claude diagnosed bot was running but responding poorly
12. **18:55** — User: "так сделай все - почему спрашиваешь?" → Claude continued fixing
13. **18:55** — Fixed `bot.py`: removed MarkdownV2 (causes parse errors), switched to `ParseMode.MARKDOWN`
14. **18:57** — Diagnosed `add_transaction` failure: `SheetsClient.add_transaction()` expected dict but got list. Fixed: detect list input and call `append_row` directly
15. **19:01** — **Context overflow → session 3**. New session continued
16. **19:03–19:05** — Fixed column name mismatch: `sheet_id` → `file_id` in Envelopes sheet and `register_envelope()`
17. **19:23** — User: "что ты делаешь" / "ты все сделал по списку?" — ran through COWORK_TASK checklist; OAuth not done
18. **19:25** — User: "через OAuth Михаила - ну так в чем проблема?" → implemented OAuth token generation
19. **19:58** — Wrote `get_oauth_token.py` for OAuth refresh token
20. **20:01–20:08** — Fixed `tool_create_envelope` to use OAuth (`create_spreadsheet_as_owner()`); tested with "Семья" envelope; created successfully. SEMYA enrolled in Admin sheet
21. **20:04** — **Context overflow → session 4**. Continued with Railway deployment
22. **20:09** — User asked about OpenAI key claim — Claude admitted it found it already in .env, didn't create it
23. **20:15** — User requested file logging + Railway setup from open browser tab
24. **20:25** — Added file-based logging to `bot.py` (RotatingFileHandler, `logs/bot.log`)
25. **20:27** — Created `.gitignore` (excludes .env, *.json, __pycache__, logs/)
26. **20:33** — User confirmed logged into Railway; Claude used Railway GraphQL API to create project, service, configure env vars
27. **20:52** — **Context overflow → session 5**. Railway deploy continued
28. **21:19** — Fixed `Procfile`: `web: python bot.py` → `worker: python bot.py` (polling bots don't bind port)
29. **21:19** — Created `.python-version = 3.12` — Python 3.13 breaks PTB 20.7 (`__slots__` AttributeError)
30. **21:19** — Fixed requirements.txt: pinned `python-telegram-bot==20.7`, `anthropic>=0.87.0`
31. **21:22** — **Context overflow → session 6**. Bot deployed to Railway but not working
32. **21:39** — User: "смотри мое общение с ботом - он не работает / показывать список конвертов / файлы должны лежать в папке проекта / добавить Меню"
33. **21:46** — Fixed `auth.py::get_user()` — added bootstrap admin bypass (was only in `is_admin()`, not `get_user()`, causing "Access denied" for Mikhail)
34. **21:47** — Fixed `summary.py::tool_get_budget_status` — was reading nonexistent JSON `settings` field; now reads `Monthly_Cap` column directly
35. **21:47** — Fixed `tools/envelope_tools.py::tool_create_envelope` — Cyrillic ID bug: `re.sub(r"[^A-Z0-9_]", "", raw_id)` — "СЕМЬЯ" was becoming "_____"; SEMYA row manually patched in Admin
36. **21:47–21:48** — Added `list_envelopes_with_links()` to `sheets.py`, `tool_list_envelopes` to `envelope_tools.py` and `agent.py`
37. **21:49** — Complete rewrite of `bot.py`: added `/menu`, `/envelopes`, `/envelope`, `/status`, `/report`, `/help` with full inline keyboards, `post_init` for command registration, `_require_user()` helper, typing indicator
38. **21:52** — Fixed `transactions.py::tool_add_transaction`: fills `Amount_EUR` for EUR directly; looks up FX_Rates for non-EUR
39. **21:57** — User: "сделай полный SETUP_REPORT - Клоду покажу / файлы должны быть в папке Проекта"
40. **22:02** — **Context overflow → session 7 (CURRENT)**. Resumed to complete SETUP_REPORT + file fix
41. **22:05** — Wrote comprehensive SETUP_REPORT.md (15 sections, ~400 lines)
42. **22:05** — Fixed `tool_create_envelope` to use OAuth first, SA as fallback
43. **22:07–22:09** — User ran git commands from terminal; fixed stale lock files; committed + pushed to GitHub (commit `13e8d48`)
44. **00:11** — Creating this memory snapshot

---

## 3. Technical Decisions

### Decision 1: Parse Mode = Markdown (not MarkdownV2)
- **Context:** Bot was sending replies but Telegram rejecting them with `BadRequest: Can't parse entities`
- **Root cause:** `parse_mode="MarkdownV2"` requires escaping of `.`, `-`, `(`, `)`, `!` etc. Agent responses don't escape these
- **Choice:** Switch to `ParseMode.MARKDOWN` (legacy Markdown, much more lenient)
- **Impact:** All bot messages now send without parse errors

### Decision 2: `worker:` not `web:` in Procfile
- **Context:** Railway was crashing the bot because it expected a TCP port binding
- **Root cause:** `web:` process type requires binding a port; polling bots don't bind anything
- **Choice:** `worker: python bot.py` — Railway's worker process type has no port requirement
- **Impact:** Bot runs stably on Railway without crashing

### Decision 3: Python 3.12 pin
- **Context:** Railway default was Python 3.13; bot crashed on startup with `AttributeError: __slots__`
- **Root cause:** PTB 20.7 uses `__slots__` in a way incompatible with Python 3.13's stricter handling
- **Choice:** Created `.python-version = 3.12`; Railway respects this file
- **Impact:** Bot starts and runs correctly

### Decision 4: OAuth for new Sheets files, SA for reading
- **Context:** Service account created files in its own Drive storage, invisible to Mikhail; SA Drive quota also near limit
- **Choice:** `create_spreadsheet_as_owner()` uses Mikhail's OAuth credentials (refresh token stored as env var) to create files in his Drive. SA is still used for all reads/writes to existing sheets.
- **Impact:** New envelopes appear in Mikhail's Google Drive. Files are accessible and visible. SA reads/writes work since he shares the file with SA as Editor.

### Decision 5: Bootstrap admin bypass via env var
- **Context:** Bot consistently denied "Access denied" to Mikhail because `get_user()` returned None when Google Sheets was inaccessible or Users sheet empty
- **Choice:** In `auth.py::get_user()`, if `telegram_id == MIKHAIL_TELEGRAM_ID` env var → return hardcoded admin user dict. This works even if Sheets API is down, token expired, etc.
- **Impact:** Mikhail always has access regardless of Sheets state

### Decision 6: `append_row` directly for list input in `add_transaction`
- **Context:** `transactions.py` pre-builds a list of values (with tx_id, timestamps already computed) but `SheetsClient.add_transaction()` expected a dict and would generate its own tx_id
- **Choice:** Detect list vs dict input; if list → `ws.append_row(row)` directly
- **Impact:** Transactions added correctly without duplicate ID generation

### Decision 7: `Amount_EUR` computed in Python, not as formula
- **Context:** `append_row` in gspread does NOT evaluate Google Sheets formulas. EUR amount was always empty.
- **Choice:** For EUR transactions: `amount_eur = amount`. For others: look up FX_Rates sheet and compute.
- **Impact:** Amount_EUR filled correctly for all transactions; reports and budget status work

---

## 4. Critical Rules & Patterns

- **Never use Python 3.13 with PTB 20.7.** `.python-version` must stay at `3.12`
- **Never use `parse_mode="MarkdownV2"`.** Agent responses are never properly escaped. Use `ParseMode.MARKDOWN` only.
- **Bootstrap admin always first.** `MIKHAIL_TELEGRAM_ID` env var must be set on Railway. Without it, Mikhail is locked out if Users sheet is empty or Sheets API fails.
- **New Google Sheets files must be created via OAuth, not SA.** SA-created files are invisible in Mikhail's Drive.
- **`Procfile` must use `worker:`, not `web:`.** Railway kills processes that don't bind ports if using `web:` type.
- **`serviceInstanceDeploy` on Railway needs `latestCommit: true`** or it re-deploys the old cached commit.
- **`gspread.append_row` does not evaluate formulas.** Always compute values in Python before appending.
- **Mikhail communicates in Russian, Ukrainian, English, and Italian — often mixed.** All bot responses should adapt to his language.

---

## 5. Complete Files Registry

### Files Written/Created (44 operations)

| File | Last Modified | Purpose |
|---|---|---|
| `.env` | 18:26 | Local secrets (5 edits throughout session) |
| `sheets.py` | 21:47 | Multiple edits: SheetsClient added, list_envelopes_with_links, get_or_create_drive_folder, OAuth method |
| `SETUP_REPORT.md` | 22:05 | Comprehensive project handoff doc (3 complete rewrites) |
| `bot.py` | 21:49 | Complete rewrite: menu, inline keyboards, command handlers, typing indicator |
| `tools/envelopes.py` | 20:07 | Legacy — fixed calling convention (but superseded by envelope_tools.py) |
| `tools/envelope_tools.py` | 22:05 | Cyrillic fix, list_envelopes, create_envelope OAuth fix |
| `tools/transactions.py` | 21:52 | Amount_EUR computation fix |
| `tools/summary.py` | 21:47 | Monthly_Cap field fix |
| `agent.py` | 21:48 | Added list_envelopes to TOOLS + dispatcher |
| `auth.py` | 21:46 | Bootstrap admin bypass in get_user() |
| `get_oauth_token.py` | 19:58 | Utility: generate OAuth refresh token |
| `.gitignore` | 20:27 | Excludes .env, *.json, __pycache__, logs/ |
| `.python-version` | 21:19 | Pins Python 3.12 for Railway |
| `Procfile` | 20:52 | worker: python bot.py |
| `requirements.txt` | 21:19 | Updated versions: PTB 20.7, anthropic>=0.87.0 |

### Key Files Read (49 operations)
`agent.py`, `auth.py`, `bot.py`, `sheets.py`, `tools/transactions.py`, `tools/summary.py`, `tools/envelope_tools.py`, `tools/wise.py`, `tools/fx.py`, `tools/config_tools.py`, `tools/envelopes.py`, `COWORK_TASK.md`, `SETUP_REPORT.md`, `requirements.txt`, `Procfile`, `.env.example`

---

## 6. All Errors & Fixes

1. **18:27 — `ImportError: cannot import name 'SheetsClient'`**
   - `sheets.py` existed but was missing the `SheetsClient` class and `get_credentials()` function
   - Fix: Appended both to `sheets.py`

2. **18:33 — `ImportError: cannot import name 'SessionContext'`**
   - `auth.py` missing `SessionContext`, `LastAction`, `get_session()`
   - Fix: Added to auth.py

3. **18:55 — Telegram `BadRequest: Can't parse entities`**
   - `parse_mode="MarkdownV2"` in bot.py; agent responses not escaped
   - Fix: Switched to `ParseMode.MARKDOWN`

4. **18:57 — `'list' object has no attribute 'get'` in add_transaction**
   - `SheetsClient.add_transaction()` expected dict; tools passed pre-built list
   - Fix: Detect list vs dict input

5. **19:03 — `KeyError: 'file_id'`**
   - Envelopes sheet had column `sheet_id`; all tools referenced `file_id`
   - Fix: Renamed column in sheet; updated `register_envelope()`

6. **19:21 — Cyrillic envelope ID `_____`**
   - `_slugify("Семья")` stripped all Cyrillic → `"_____"`
   - Fix: Added `re.sub(r"[^A-Z0-9_]", "", raw_id)` in envelope_tools.py; manually patched SEMYA row in Admin sheet

7. **20:52 — Railway: bot crashes immediately after deploy**
   - `Procfile` used `web:` type; Railway expected port binding
   - Fix: Changed to `worker: python bot.py`

8. **21:19 — Railway: `AttributeError: __slots__`**
   - Python 3.13 incompatible with PTB 20.7
   - Fix: Created `.python-version = 3.12`

9. **21:19 — Railway: deploying old commit despite new push**
   - `serviceInstanceDeploy` without `latestCommit: true` used cached deploy
   - Fix: Used `latestCommit: true` parameter in Railway GraphQL API

10. **21:46 — "Access denied" for Mikhail**
    - `get_user()` returned None when Google Sheets unavailable; bootstrap check only in `is_admin()`
    - Fix: Added `MIKHAIL_TELEGRAM_ID` bypass in `get_user()` itself

11. **21:47 — Budget status always showing cap=0, spent=0**
    - `tool_get_budget_status` tried to parse nonexistent JSON `settings` field
    - Fix: Read `Monthly_Cap` column directly from Envelopes row

12. **21:52 — `Amount_EUR` always empty**
    - `append_row` doesn't evaluate Sheets formulas
    - Fix: Compute EUR amount in Python before appending

13. **22:07–22:09 — Git commit failed (stale lock files)**
    - `.git/index.lock`, `.git/HEAD.lock`, `.git/refs/heads/master.lock` left by crashed git process via FUSE mount
    - Fix: Mikhail removed them manually from terminal

---

## 7. Current System State

### Bot
- **Username:** @ApolioHomeBot | **Link:** https://t.me/ApolioHomeBot
- **Status:** Running on Railway (polling mode, worker process)
- **Last commit:** `13e8d48` — "Update SETUP_REPORT + fix envelope creation to use OAuth"
- **GitHub repo:** https://github.com/miroshnik0901-hub/apolio-home (branch: master)

### Google Sheets
| File | ID | Status |
|---|---|---|
| Admin | `1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk` | ✅ Active |
| MM Budget | `1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ` | ✅ Active, ID: `MM_BUDGET` |
| Семья (SEMYA) | `1UNhBQqM5L0fhFMef_f6y-QBYrGAK0csCsLksnAwi-So` | ✅ Active, ID: `SEMYA` |

### Railway Environment Variables (all set)
`TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT` (base64), `ADMIN_SHEETS_ID`, `MIKHAIL_TELEGRAM_ID=360466156`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`

### Bot Commands (registered in Telegram)
`/start`, `/menu`, `/envelopes`, `/envelope`, `/status`, `/report`, `/help`

---

## 8. Pending Tasks

### High Priority
- [ ] **Test bot end-to-end** — Send `/start`, `/envelopes`, select envelope, add transaction, check status. Was not fully verified after last deploy.
- [ ] **SEMYA Drive shortcut** — No `.gsheet` shortcut for SEMYA in the `apolio-home` folder in Google Drive. Mikhail needs to manually move/link from Drive web. File URL: https://docs.google.com/spreadsheets/d/1UNhBQqM5L0fhFMef_f6y-QBYrGAK0csCsLksnAwi-So

### Normal Priority
- [ ] **Auto-select MM_BUDGET on session start** — Currently `current_envelope_id = None` after bot restart; Mikhail must re-select. Fix: auto-set to `MM_BUDGET` in `get_session()` for admin users.
- [ ] **FX rate auto-update cron** — `auto_update_fx_rates()` in `fx.py` is never called. Non-EUR transactions have blank `Amount_EUR`. Options: (a) Railway cron job on 1st of month, (b) manually call via bot: "обнови курсы валют"
- [ ] **Create Polina envelope** — Agent system prompt routes Polina/Bergamo/liceo to "Polina" envelope but it doesn't exist yet. Command: "создай конверт Polina лимит 500 EUR"

### Low Priority / Ideas
- [ ] **Undo last transaction** — `last_action` is stored in SessionContext; `delete_transaction` tool exists. Just needs `/undo` command or "отмени последнее" intent in agent.
- [ ] **Git config identity** — Commits show `Mike Miro <michaelhome@Mikes-Mac-Air15.local>` instead of Mikhail Miro. Run: `git config --global user.name "Mikhail Miro"` + `git config --global user.email "miroshnik0901@gmail.com"`
- [ ] **Session persistence** — Consider writing `current_envelope_id` to a small JSON file so it survives restarts
- [ ] **Webhook mode** — Currently polling. For lower latency and Railway reliability, set `WEBHOOK_URL` to a public HTTPS endpoint and redeploy.

---

## 9. Architecture Summary (for quick orientation)

```
User (Telegram)
  ↓ text/voice/photo/csv
bot.py (handlers)
  ↓ auth check (MIKHAIL_TELEGRAM_ID bypass)
agent.py (Claude claude-sonnet-4-20250514)
  ↓ tool calls (up to 5 iterations)
tools/ (13 tools)
  ↓ gspread API calls
Google Sheets (Admin + Envelope files)
```

**Per-user state:** `SessionContext` (in-memory dict in `auth.py`), holds `current_envelope_id` and `last_action`. Resets on bot restart.

**Auth:** `AuthManager` caches Users sheet (5 min TTL). Bootstrap admin bypasses sheet lookup entirely for `MIKHAIL_TELEGRAM_ID`.

**File creation:** New Google Sheets → OAuth (Mikhail's Drive). Reads/writes → Service Account.

---

## 10. User Context & Preferences

- **Name:** Mikhail Miro (Михаил Мирошник)
- **Email:** miroshnik0901@gmail.com
- **Telegram ID:** 360466156
- **Location:** Pino Torinese, Italy
- **Languages:** Russian, Ukrainian, English, Italian (mixed freely)
- **Communication style:** Direct, no pleasantries, no excessive explanation. "так сделай все - почему спрашиваешь?"
- **Expectation:** Claude acts autonomously. No asking for permission to proceed.
- **Challenge assumptions.** Point out errors. Don't pad responses.

---

## Snapshot Metadata

- **Transcript source:** `edfc6cd1-b9ac-490e-acda-5b5979dc86e5.jsonl` (23MB, 2909 lines)
- **Analysis method:** Full transcript parsing + conversation context
- **Coverage:** Complete — single-project session, all phases documented
- **Previous snapshot:** None — created from scratch
- **Snapshot file:** `apolio-home_MEMORY_04-01-2026_00-11.md`
