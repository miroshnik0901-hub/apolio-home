# Apolio Home — Dev / Prod State Tracker
# Updated by Claude after every `git push` to dev or main.
# Read this at the START of every session to understand what's deployed where.

---

## Current State (2026-04-20 12:35)

### 🟢 MAIN (Production) — @ApolioHomeBot
**origin/main:** `2cd9257` — T-272: wrap workbook open in _sheets_retry (data loss fix).
**Status:** ✅ DEPLOYED on 2026-04-20 11:20 via cherry-pick of dev `2ec22c0` onto main=36db8fa → `2cd9257`. Mikhail Confirm=GO set on T-272, authorized via chat "do READY-GO". sync_prod_after_deploy 9/9 OK (Transactions 161 rows at 2-162 incl. backfilled rows 161+162). error_log clean 45s post-deploy. `/sessions/compassionate-exciting-cray/deploy/apolio-t272-main` clone (/tmp was full, relocated).
**Recent main history:** `2cd9257` T-272 → `36db8fa` T-271 → `5a30b2d` T-268+T-269+T-270 → `3dcff85` T-267 → `3bad49e` T-266 → `52b5e20` T-265 → `56bb895` T-264 → `d8d8dc6` T-261+T-264 prompt/JSON → `7ed1632` T-261 follow-up → `e3e3dd9` T-261 → `4c090e5` T-259+T-260+A-011 → `8f62c26` T-258 → `7cc46e4` T-257 fixup → `0c51f0e` T-257 → `813256e` T-253 → `7b2325e` T-254+T-255.
**Post-deploy sync (2026-04-20 11:20):** `scripts/sync_prod_after_deploy.py` 9/9 OK. Transactions sparse layout OK (161 rows at 2-162, gap≤0). FX_Rates 12 rows. No #REF! in Summary.

### 🔵 DEV (Staging) — @ApolioHomeTestBot
**origin/dev:** `414fbeb` — T-273+T-274 PRIMARY LAYER: bot.py:4314/4528 row-builder carries subcategory; sheets.py 5 more _sheets_retry-wrapped READ sites; 2 integration tests added. Prev: `44652c6` (docs), `0c7c0ae` (T-273 secondary), `961bc32` (T-274 aliases secondary), `2ec22c0` (T-272 — now on main as `2cd9257`).

**Commits on dev not yet represented on main (newest → oldest):**

| Commit | Task | Description | Deploy status |
|--------|------|-------------|---------------|
| `414fbeb` | T-273+T-274 | PRIMARY: bot.py:4314 batch params dict + bot.py:4528 single-row path carry subcategory. sheets.py: 5 more read-path wraps (read_config/get_dashboard_config/get_categories_with_subs/get_accounts_with_types/get_rows_raw) → 12 total _sheets_retry read sites. Added tests/t273_read_retry_selftest.py (5/5) + tests/t274_plumbing_selftest.py (8/8). Regression 58/58. | READY — awaiting GO |
| `0c7c0ae` | T-273 | enrich_transaction 429 → i18n friendly msg + error_log persistence + retry budget bumped (sheets.py get_all_values max_attempts=3/delay=5s) — secondary layer | READY — awaiting GO |
| `961bc32` | T-274 | tools/transactions: car-wash aliases (мойка/мийка/lavaggio/carwash → Fuel) + bare `parking` + bigram pass in _infer_subcategory — secondary layer | READY — awaiting GO |
| `e1c4fa4` | — | docs: DEV_PROD_STATE + SESSION_LOG rotate | no task — docs only |
| `da4d110` | T-267 | docs: SESSION_LOG T-267 implementation | no task — docs only |
| `6b331ba` | — | SESSION_LOG + DEV_PROD_STATE docs | no task — docs only |
| `7cc19bc` | AUDIT | AUDIT_PLAN/TASKS/CONCLUSION + docs/google_sheets_access.md + WORKING_GUIDE tool count | audit-iter-1 deliverables — no GO |
| `4dd1137` | apps_script | archiveClosed → physical bottom archive | container-bound Apps Script, not auto-deployed from git |
| `94c60ba` | A-009 | tools/transactions dead-branch cleanup | audit refactor — no Confirm=GO |
| `9ca1b8f` | A-014 | SheetsClient.invalidate_env_config() public hook | audit refactor — no Confirm=GO |
| `0be0234` | AP_FILE_NAMING | scripts/ + mcp/sheets_mcp.py renamed ap_* | no linked task — tooling-only |
| `c9991ad` | T-256 | task_log insert_row(index=2) — new tasks above CLOSED block | DISCUSSION — no Confirm=GO yet |

**OPEN / DISCUSSION tasks in Task Log (as of 2026-04-20 12:35):**

| Task ID | Status | Deploy | Blocker |
|---------|--------|--------|---------|
| T-273 | OPEN | READY | on dev as `414fbeb` (PRIMARY) + `0c7c0ae` (secondary). 6 READ sites newly wrapped + friendly 429 i18n + error_log. Integration test 5/5. Awaiting Mikhail GO for PROD cherry-pick. |
| T-274 | OPEN | READY | on dev as `414fbeb` (PRIMARY row-builder plumbing at bot.py:4314/4528) + `961bc32` (secondary aliases). Integration test 8/8. Awaiting Mikhail GO. |
| T-275 | DISCUSSION | — | Agent clarification UX feature. Design spec written into Apolio Comment (2026-04-20 11:55). MVP slice: triggers 1+2, filtered batch, `agent_learning` reuse. Awaiting Mikhail spec review. |
| T-256 | DISCUSSION | READY | on dev as `c9991ad`. task_log insert_row(index=2). Awaiting Mikhail GO for PROD cherry-pick. |
| T-262 | OPEN | — | Unblocked by T-261 PROD deploy 2026-04-20. Ready for retest on @ApolioHomeBot. |
| T-263 | DISCUSSION | — | Phase 1 prompt refactor (trim -28%, no T-261 dep) awaiting Mikhail GO. Phase 2 unblocked by T-261 in PROD. |
| T-019, T-045, T-059, T-060, T-064 | ON HOLD | — | Mikhail's own backlog, not Claude's concern (confirmed 2026-04-19). |

**Closed on 2026-04-20 11:20 per Mikhail "resolve status of DEPLOYED-GO":** T-271 (Mix Markt), T-272 (workbook retry data-loss fix). All other prior DISCUSSION/DEPLOYED/GO tasks (T-253, T-257–T-261, T-267–T-270) already CLOSED by Mikhail earlier.

---

## How to Read This File

- **Before any session:** check what's on dev vs main to understand current deploy gap.
- **After `git push dev`:** add a row to the DEV table above with commit hash + task + description.
- **After `git push main` (on GO):** move DEV rows to MAIN section, update "last commit on main".
- **Never merge to main without GO from Mikhail** (see CLAUDE.md).

---

## Quick Reference: Test vs Prod Resources

| Resource | Test (Staging) | Prod (Production) |
|----------|---------------|-------------------|
| Bot | @ApolioHomeTestBot | @ApolioHomeBot |
| Admin Sheet | `1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM` | `1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk` |
| Budget File | `196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788` | `1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ` |
| Envelope ID | `TEST_BUDGET` | `MM_BUDGET` |
| DB | maglev.proxy.rlwy.net:17325 | interchange.proxy.rlwy.net:19732 |
| Railway env ID | `1e6973d7-2c9c-48a3-8197-b61fd4174ba4` | `08e40bf3-cbe4-4a80-be54-1f291c21fe0d` |

⚠️ NEVER mix test and prod resources. Test data → Test Admin only.
