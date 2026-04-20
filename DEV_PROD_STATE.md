# Apolio Home — Dev / Prod State Tracker
# Updated by Claude after every `git push` to dev or main.
# Read this at the START of every session to understand what's deployed where.

---

## Current State (2026-04-20 11:15)

### 🟢 MAIN (Production) — @ApolioHomeBot
**origin/main:** `36db8fa` — T-271: Mix Markt + IT grocery chains → Groceries subcategory.
**Status:** ✅ DEPLOYED on 2026-04-20 10:55 via single cherry-pick of dev `063dcb8` onto main=5a30b2d → `36db8fa`. Mikhail Confirm=GO set on T-271 ("сам решай и делай" authorization). sync_prod_after_deploy 9/9 OK. error_log clean 45s post-deploy. FUSE /tmp/apolio-t271 clone.
**Recent main history:** `36db8fa` T-271 → `5a30b2d` T-268+T-269+T-270 → `3dcff85` T-267 → `3bad49e` T-266 → `52b5e20` T-265 → `56bb895` T-264 → `d8d8dc6` T-261+T-264 prompt/JSON → `7ed1632` T-261 follow-up → `e3e3dd9` T-261 → `4c090e5` T-259+T-260+A-011 → `8f62c26` T-258 → `7cc46e4` T-257 fixup → `0c51f0e` T-257 → `813256e` T-253 → `7b2325e` T-254+T-255.
**Post-deploy sync (2026-04-20 10:55):** `scripts/sync_prod_after_deploy.py` 9/9 OK. Transactions sparse layout OK (159 rows at 2-160, gap≤0). FX_Rates 12 rows. No #REF! in Summary.

### 🔵 DEV (Staging) — @ApolioHomeTestBot
**origin/dev:** `2ec22c0` — T-272: wrap workbook open in _sheets_retry (data loss fix). Previous: `da821ec` (docs T-271), `b0c65d1` (PROD deploy docs 04-20 09:57), `e1c4fa4` (docs), `72d0ea1` (T-268+T-269+T-270).

**Commits on dev not yet represented on main (newest → oldest):**

| Commit | Task | Description | Deploy status |
|--------|------|-------------|---------------|
| `2ec22c0` | T-272 | sheets.py add_transaction: wrap workbook+worksheet resolution inside _sheets_retry. Regression §6.7. | Deploy=READY, awaiting Confirm=GO |
| `e1c4fa4` | — | docs: DEV_PROD_STATE + SESSION_LOG rotate | no task — docs only |
| `da4d110` | T-267 | docs: SESSION_LOG T-267 implementation | no task — docs only |
| `6b331ba` | — | SESSION_LOG + DEV_PROD_STATE docs | no task — docs only |
| `7cc19bc` | AUDIT | AUDIT_PLAN/TASKS/CONCLUSION + docs/google_sheets_access.md + WORKING_GUIDE tool count | audit-iter-1 deliverables — no GO |
| `4dd1137` | apps_script | archiveClosed → physical bottom archive | container-bound Apps Script, not auto-deployed from git |
| `94c60ba` | A-009 | tools/transactions dead-branch cleanup | audit refactor — no Confirm=GO |
| `9ca1b8f` | A-014 | SheetsClient.invalidate_env_config() public hook | audit refactor — no Confirm=GO |
| `0be0234` | AP_FILE_NAMING | scripts/ + mcp/sheets_mcp.py renamed ap_* | no linked task — tooling-only |
| `c9991ad` | T-256 | task_log insert_row(index=2) — new tasks above CLOSED block | DISCUSSION — no Confirm=GO yet |

**OPEN / DISCUSSION tasks in Task Log (as of 2026-04-20 09:07):**

| Task ID | Status | Deploy | Blocker |
|---------|--------|--------|---------|
| T-253 | DISCUSSION | DEPLOYED | on main as `813256e`. Awaiting Mikhail CLOSE. |
| T-256 | DISCUSSION | READY | on dev as `c9991ad`. Awaiting Mikhail GO for PROD cherry-pick. |
| T-257 | DISCUSSION | DEPLOYED | on main as `0c51f0e` + fixup `7cc46e4`. Awaiting Mikhail CLOSE. |
| T-258 | DISCUSSION | DEPLOYED | on main as `8f62c26`. Test-tooling only. Awaiting Mikhail CLOSE. |
| T-259 | DISCUSSION | DEPLOYED | on main as `4c090e5` (cherry-pick of dev `1305662`). Awaiting Mikhail CLOSE. |
| T-260 | DISCUSSION | DEPLOYED | same commit `4c090e5`. Awaiting Mikhail CLOSE. |
| T-261 | DISCUSSION | DEPLOYED | on main as `e3e3dd9`+`7ed1632`+`d8d8dc6` (cherry-pick chain 2026-04-20 09:06). Promoted implicitly with T-264 GO (T-264 depends on T-261). Awaiting Mikhail CLOSE + retro GO acknowledgment. |
| T-262 | OPEN | — | Unblocked by T-261 PROD deploy 2026-04-20. Ready for retest on @ApolioHomeBot. |
| T-263 | DISCUSSION | — | Phase 1 prompt refactor (trim -28%, no T-261 dep) awaiting Mikhail GO. Phase 2 now unblocked by T-261 in PROD. |
| T-264 | CLOSED | DEPLOYED | on main as `56bb895` (2026-04-20 09:06). Staging-validated via Mikhail screenshot. |
| T-265 | CLOSED | DEPLOYED | on main as `52b5e20` (2026-04-20 09:06). Staging-validated (buttons after aggregation). |
| T-266 | CLOSED | DEPLOYED | on main as `3bad49e` (2026-04-20 09:06). Staging self-test wrote 2 rows to error_log. |
| T-267 | DISCUSSION | DEPLOYED | on main as `3dcff85` (2026-04-20 09:57). Awaiting Mikhail CLOSE. |
| T-268 | DISCUSSION | DEPLOYED | on main as `5a30b2d` (2026-04-20 09:57). Awaiting Mikhail CLOSE. |
| T-269 | DISCUSSION | DEPLOYED | on main as `5a30b2d` (2026-04-20 09:57). Awaiting Mikhail CLOSE. |
| T-270 | DISCUSSION | DEPLOYED | on main as `5a30b2d` (2026-04-20 09:57). Awaiting Mikhail CLOSE. |
| T-271 | DISCUSSION | DEPLOYED | on main as `36db8fa` (2026-04-20 10:55). Awaiting Mikhail CLOSE. |
| T-272 | DISCUSSION | READY | on dev as `2ec22c0`. Fixes silent data loss (PROD 08:22 UTC — 2 UAH tx lost). Backfill already done (rows 161+162). Awaiting Mikhail Confirm=GO for PROD cherry-pick. |
| T-019, T-045, T-059, T-060, T-064 | ON HOLD | — | Mikhail's own backlog, not Claude's concern (confirmed 2026-04-19). |

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
