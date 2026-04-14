# Apolio Home — Project Index
# Read this to quickly orient in the codebase. Updated: 2026-04-15.

---

## Root files — core runtime

| File | Lines | Role |
|------|-------|------|
| `bot.py` | 5522 | **Entry point.** All PTB handlers, callback routing, keyboards. Key callbacks: `cb_split_separate` (batch add), `cb_dup_*` (enrich/skip dup), `cb_force_reprocess` (T-233 retry), `cb_del_bulk` (batch delete) |
| `agent.py` | 1988 | **Agentic loop.** 27 tools, Claude API call, `_build_context()`, system prompt assembly, `_tool_refresh_dashboard`, `_tool_update_dashboard_config` |
| `sheets.py` | 1569 | **All Sheets API.** `SheetsClient` (main), `AdminSheets`, `EnvelopeSheets`, `SheetsCache`. Cache TTLs: txns=120s, static=600s, config=600s |
| `intelligence.py` | 666 | **Budget logic.** `IntelligenceEngine`, `compute_contribution_status`, `compute_contribution_history` (reads actual months), `compute_cumulative_balance` |
| `db.py` | 1316 | **PostgreSQL.** `conversation_log`, `error_log`, `parsed_data`, `agent_learning`. `log_message()`, `log_error()`, `get_recent_messages_for_api()` |
| `auth.py` | 179 | **Session & auth.** `SessionContext`, `get_session()`, `AuthManager`. Always use `session.lang` (not `.language`) |
| `i18n.py` | 1140 | **All UI strings.** `i18n.ts()`, `i18n.tu()`, `MENU_LABELS`, `MONTH_SHORT`, `MONTH_LABELS`. 4 languages: RU/UK/EN/IT |
| `intelligence.py` | 666 | Budget snapshot, per-user contribution, cumulative balance, history |
| `menu_config.py` | 304 | `DEFAULT_MENU`, `_DEFAULT_ROWS`, `BotMenu` sheet loader, `reset_to_defaults()` |
| `reports.py` | 152 | Report formatting — structures agent tool output into Telegram-ready text |
| `user_context.py` | 172 | User goals and behavioral patterns. Reads/writes `UserContext` sheet tab |
| `task_log.py` | 288 | **Task Log API.** `TaskLog` class — only correct way to read/write task log. Deploy: READY/DEPLOYED/N/A/FAILED |

---

## Root files — setup & ops

| File | Role |
|------|------|
| `setup_sheets_v2.py` | Creates/initializes all Sheets tabs. ⚠️ DO NOT TOUCH without instruction |
| `setup_admin.py` | Admin sheet setup. ⚠️ DO NOT TOUCH without instruction |
| `test_regression.py` | 39 regression tests (L1-L2 static + L3 live). Run before every push |
| `requirements.txt` | Python dependencies |
| `Procfile` | Railway: `worker: python bot.py` |

---

## tools/ — agent tool implementations

| File | Role |
|------|------|
| `transactions.py` | `tool_add_transaction`, `tool_enrich_transaction`, `tool_delete_transaction`, `tool_find_transactions`. Dup detection (same-currency + cross-currency T-192) |
| `summary.py` | `tool_get_summary`, `tool_get_budget_status` |
| `envelope_tools.py` | `create_envelope`, `list_envelopes` |
| `envelopes.py` | Envelope data access helpers |
| `goals.py` | User goals management |
| `ideas.py` | Ideas/wishlist feature |
| `support.py` | Support request handling |
| `conversation_log.py` | `ConversationLogger` (async, Queue, Sheets fallback) |
| `admin.py` | Admin commands |
| `config_tools.py` | Bot config. ⚠️ DO NOT TOUCH without instruction |
| `fx.py` | Exchange rates. ⚠️ DO NOT TOUCH without instruction |
| `wise.py` | Wise CSV import. ⚠️ DO NOT TOUCH without instruction |
| `receipt_store.py` | DEPRECATED — receipts now in PostgreSQL `parsed_data` only |

---

## tests/ — test suite

| File | Role |
|------|------|
| `run_all.py` | L1–L3 tests runner (25/25). Run after push to dev: `python3 tests/run_all.py` |

---

## scripts/ — ops scripts

| File | Role |
|------|------|
| `sync_prod_after_deploy.py` | Post-PROD deploy verifier (9 checks: headers, aliases, FX, config). Read-only by default. **Run after every `git push main`** |
| `setup.py` | Initial environment setup |
| `encode_service_account.py` | Encodes service account JSON to base64 for env var |
| `get_oauth_token.py` | OAuth token helper |
| `get_telegram_id.py` | Get Telegram user ID |

---

## Docs & config files

| File | Role |
|------|------|
| `CLAUDE.md` | **Single source of truth.** All IDs, deploy rules, TaskLog API, language rules, session start order |
| `CLAUDE_WORKING_GUIDE.md` | Architecture reference: stack, agent loop, Sheets schema, tool list. Read before code changes |
| `PROJECT_INDEX.md` | **This file.** File map for quick orientation |
| `DEV_PROD_STATE.md` | Current dev vs main state: what's deployed, what's pending GO |
| `SESSION_LOG.md` | Append-only session log. Rotate at 16384 bytes |
| `ApolioHome_Prompt.md` | Agent system prompt (loaded at startup). Currency, dup, and batch rules |
| `MEMORY_GUIDE.md` | Memory snapshot format guide |
| `README.md` | Public-facing project readme |
| `PROD.docx` / `TEST.docx` | Architecture diagrams (Word) |
| `PROD.pdf` / `TEST.pdf` | Architecture diagrams (PDF) |
| `PROD_AGENT_ANALYSIS.md` | Agent behavior analysis for PROD |
| `TEST_AGENT_ANALYSIS.md` | Agent behavior analysis for TEST |
| `ApolioHome_UserBalance_formula.xlsx` | Balance formula reference |

---

## logs/ — session log archive

| File | Role |
|------|------|
| `SESSION_LOG_ARCHIVE_*.md` | Rotated session logs (older sessions) |
| `bot.log` | Railway bot process log (if local) |

---

## source_files/ — reference materials

| Path | Role |
|------|------|
| `source_files/task_log_automation.js` | Google Apps Script for Task Log (auto-numbering, topic validation) |
| `source_files/_archive/` | Archived screenshots and old snapshots |

---

## apolio_home_logo/ — brand assets

SVG and PNG logos (dark/light variants, mark). Used for marketing/docs.

---

## Memory snapshots (root)

Files matching `apolio-home_MEMORY_*.md` — session context snapshots created by `/pm create`.
Stored in root and in `/mnt/AI/` folder. Use `/pm restore` to load.

---

## Google Sheets (shortcuts in root)

`.gsheet` files are local shortcuts to Google Sheets — open in browser:
- `Apolio Home — Admin.gsheet` → PROD Admin sheet
- `Apolio Home - Test Admin.gsheet` → TEST Admin sheet
- `Apolio Home — MM Budget.gsheet` → PROD Budget
- `Apolio Home — Test Budget.gsheet` → TEST Budget
- `Apolio Home — Task Log.gsheet` → Task Log (use via `task_log.py`)

---

## Key cross-references

| Need to... | Go to |
|-----------|-------|
| Add/update task | `task_log.py` → `TaskLog` class |
| Check what's deployed | `DEV_PROD_STATE.md` |
| Deploy to PROD | `CLAUDE.md` → Git & Deploy + post-deploy: `scripts/sync_prod_after_deploy.py` |
| Change UI strings | `i18n.py` (all 4 languages required) |
| Add new agent tool | `agent.py` (TOOLS schema + dispatch dict) + `CLAUDE_WORKING_GUIDE.md` section 6 |
| Touch Sheets schema | `CLAUDE_WORKING_GUIDE.md` section 7 (Sheets schema) |
| Session start | Read: SESSION_LOG.md → DEV_PROD_STATE.md → CLAUDE_WORKING_GUIDE.md |
