# Apolio Home — Dev / Prod State Tracker
# Updated by Claude after every `git push` to dev or main.
# Read this at the START of every session to understand what's deployed where.

---

## Current State (2026-04-20)

### 🟢 MAIN (Production) — @ApolioHomeBot
**origin/main:** `3bad49e` — T-266: persist tool failures to error_log (agent + tool_add_transaction).
**Status:** ✅ DEPLOYED on 2026-04-20 09:06 via 6-commit cherry-pick chain onto main (T-261 deps + T-264 + T-265 + T-266). Mikhail Confirm=GO set on T-264/T-265/T-266; staging screenshot validated full chain (4 trans, 12,915 UAH, buttons). FUSE /tmp clone fallback used (.env GITHUB_PAT).
**Recent main history:** `3bad49e` T-266 → `52b5e20` T-265 → `56bb895` T-264 → `d8d8dc6` T-261+T-264 prompt/JSON → `7ed1632` T-261 follow-up → `e3e3dd9` T-261 → `4c090e5` T-259+T-260+A-011 → `8f62c26` T-258 → `7cc46e4` T-257 fixup → `0c51f0e` T-257 → `813256e` T-253 → `7b2325e` T-254+T-255.
**Post-deploy sync (2026-04-20 09:07):** `scripts/ap_sync_prod.py` 9/9 OK. Transactions sparse layout OK (151 rows at 2-152). FX_Rates 12 rows. No #REF! in Summary.

### 🔵 DEV (Staging) — @ApolioHomeTestBot
**origin/dev:** `517229a` — T-266: persist tool failures to error_log. T-261/T-264/T-265/T-266 content also on main via cherry-pick chain 2026-04-20 09:06.

**Commits on dev not yet represented on main (newest → oldest):**

| Commit | Task | Description | Deploy status |
|--------|------|-------------|---------------|
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
