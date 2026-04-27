# Apolio Home — Dev / Prod State Tracker
# Updated by Claude after every `git push` to dev or main.
# Read this at the START of every session to understand what's deployed where.

---

## Current State (2026-04-20 13:53)

### 🟢 MAIN (Production) — @ApolioHomeBot
**origin/main:** `a68d1e3` — T-276 per-item list in cross-dup drain (restore pre-T-254 UX).
**Status:** ✅ DEPLOYED on 2026-04-20 13:22–13:25. Two commits cherry-picked onto main=dc771cd: `9af2c16` (T-277 T-265-regression safety net — hint hardening + bot.py synth), `a68d1e3` (T-276 per-item drain list). Mikhail Confirm=GO via chat "do GO / for T-275 - put status to DEPLOY". scripts/ap_sync_prod.py 9/9 OK (Transactions 174 rows at 2-175, gap≤0). PROD error_log clean 30min post-deploy (no new entries since deploy).
**Recent main history:** `a68d1e3` T-276 → `9af2c16` T-277 → `dc771cd` T-273+T-274 primary → `3913c85` T-273 → `9721c6b` T-274 → `2cd9257` T-272 → `36db8fa` T-271 → `5a30b2d` T-268+T-269+T-270 → `3dcff85` T-267 → `3bad49e` T-266 → `52b5e20` T-265 → `56bb895` T-264 → `d8d8dc6` T-261+T-264 prompt/JSON → `7ed1632` T-261 follow-up → `e3e3dd9` T-261.
**Post-deploy sync (2026-04-20 13:25):** `scripts/ap_sync_prod.py` 9/9 OK. Transactions sparse layout OK (174 rows at 2-175). FX_Rates 12 rows. Summary no #REF!. CategoryAliases 86 aliases, UserAliases 13.

### 🔵 DEV (Staging) — @ApolioHomeTestBot
**origin/dev:** `07070dd` — T-278: lock receipt who to session.user_name (block LLM bias). Prev: `c4cb469` (docs corrections), `fa72fdd` (T-276/T-277 status), `287d3bb` (T-276), `a19db6e` (T-277), `414fbeb` (T-273/T-274 primary).

**Commits on dev not yet represented on main (newest → oldest):**

| Commit | Task | Description | Deploy status |
|--------|------|-------------|---------------|
| `07070dd` | T-278 | agent.py: store_pending_receipt schema drops `who` field; receipt_data["who"] = session.user_name only. bot.py: all photo-callback paths collapse who to session.user_name (was receipt.get("who", session.user_name)); cmd_start drops `or "Mikhail"` literal; bulk per-item path drops receipt.who chain (per-item items[].who from aggregate_bank_statement T-261 still preserved). ApolioHome_Prompt.md: line 319 drops "(Mikhail)" hardcode + new OMIT-fallback rule; example outputs use placeholders. tests/t278_who_attribution_selftest.py 7/7 + 3 regression checks (61/61). | READY for PROD |
| `287d3bb` | T-276 | bot.py: accumulate _batch_recap_items across phase-1 add + cross-dup drain. Render items list above compact T-254 tally on drain. Adds ↻/✓/✗ markers. tests/t276_recap_items_selftest.py 7/7. Regression 58/58. | DEPLOYED as `a68d1e3` on main |
| `a19db6e` | T-277 | agent.py: hardened hint_for_agent in _tool_aggregate_bank_statement (MANDATORY tool chain, FORBIDDEN plain text). Session marker triple stashed. _tool_present_options clears marker on T-076 buttons. bot.py: pre-BUG-010 safety net — if markers set + pending_choice empty + response non-empty → synthesize pending_receipt from fact_expense_rows + force T-076 buttons (RU/UK/EN/IT). tests/t277_safety_net_selftest.py 7/7. Regression 58/58. | DEPLOYED as `9af2c16` on main |
| `414fbeb` | T-273+T-274 | PRIMARY: bot.py:4314 batch params dict + bot.py:4528 single-row path carry subcategory. sheets.py: 5 more read-path wraps (read_config/get_dashboard_config/get_categories_with_subs/get_accounts_with_types/get_rows_raw) → 12 total _sheets_retry read sites. Added tests/t273_read_retry_selftest.py (5/5) + tests/t274_plumbing_selftest.py (8/8). Regression 58/58. | DEPLOYED as `dc771cd` on main |
| `0c7c0ae` | T-273 | enrich_transaction 429 → i18n friendly msg + error_log persistence + retry budget bumped (sheets.py get_all_values max_attempts=3/delay=5s) — secondary layer | DEPLOYED as `3913c85` on main |
| `961bc32` | T-274 | tools/transactions: car-wash aliases (мойка/мийка/lavaggio/carwash → Fuel) + bare `parking` + bigram pass in _infer_subcategory — secondary layer | DEPLOYED as `9721c6b` on main |
| `e1c4fa4` | — | docs: DEV_PROD_STATE + SESSION_LOG rotate | no task — docs only |
| `da4d110` | T-267 | docs: SESSION_LOG T-267 implementation | no task — docs only |
| `6b331ba` | — | SESSION_LOG + DEV_PROD_STATE docs | no task — docs only |
| `7cc19bc` | AUDIT | AUDIT_PLAN/TASKS/CONCLUSION + docs/google_sheets_access.md + WORKING_GUIDE tool count | audit-iter-1 deliverables — no GO |
| `4dd1137` | apps_script | archiveClosed → physical bottom archive | container-bound Apps Script, not auto-deployed from git |
| `94c60ba` | A-009 | tools/transactions dead-branch cleanup | audit refactor — no Confirm=GO |
| `9ca1b8f` | A-014 | SheetsClient.invalidate_env_config() public hook | audit refactor — no Confirm=GO |
| `0be0234` | AP_FILE_NAMING | scripts/ + mcp/sheets_mcp.py renamed ap_* | no linked task — tooling-only |
| `c9991ad` | T-256 | task_log insert_row(index=2) — new tasks above CLOSED block | DISCUSSION — no Confirm=GO yet |

**OPEN / DISCUSSION tasks in Task Log (as of 2026-04-27 19:00):**

| Task ID | Status | Deploy | Blocker |
|---------|--------|--------|---------|
| T-278 | DISCUSSION | READY | on dev as `07070dd`. Wrong contributor attribution fixed (Maryna's photos no longer get Who=Mikhail). 7/7 self-test + 3 regression checks pass. Awaiting Mikhail Confirm=GO for PROD cherry-pick. After GO: also fix 4 stray PROD rows (177-180, Mikhail → Maryna). |
| T-273 | DISCUSSION | DEPLOYED | on main as `3913c85` (secondary) + `dc771cd` (primary). Awaiting Mikhail resolve-status. |
| T-274 | DISCUSSION | DEPLOYED | on main as `9721c6b` (secondary) + `dc771cd` (primary). Awaiting Mikhail resolve-status. |
| T-276 | DISCUSSION | DEPLOYED | on main as `a68d1e3` (cherry-picked from dev `287d3bb`). bot.py drain accumulates _batch_recap_items (phase-1 adds + per-dup-resolution lines) and renders above compact T-254 tally. Awaiting Mikhail resolve-status. |
| T-277 | DISCUSSION | DEPLOYED | on main as `9af2c16` (cherry-picked from dev `a19db6e`). agent.py hint_for_agent hardened + bot.py safety net synthesizes pending_receipt + forces T-076 buttons. Awaiting Mikhail resolve-status. |
| T-275 | IN PROCESS | — | Agent clarification UX feature. Mikhail directive 2026-04-20 14:xx: субкатегория менее критична чем Категория — если агент не может легко определить subcategory, пропустить поле (leave blank). RESCOPE: drop subcategory clarify from v1; either narrow to category-only clarify or close entirely. Awaiting Mikhail decision. |
| T-263 | ON HOLD | — | ApolioHome_Prompt.md revision/split/partial extraction to code (475 lines, 26 KB). On hold per Mikhail. |
| T-019, T-045, T-059, T-060, T-064 | ON HOLD | — | Mikhail's own backlog, not Claude's concern (confirmed 2026-04-19). |

**Closed on 2026-04-20 11:20 per Mikhail "resolve status of DEPLOYED-GO":** T-271 (Mix Markt), T-272 (workbook retry data-loss fix). All other prior DISCUSSION/DEPLOYED/GO tasks (T-253, T-257–T-261, T-267–T-270) already CLOSED by Mikhail earlier.

**Also CLOSED (as of 2026-04-20):** T-256 (task_log insert_row, closed 4/19), T-262 (PROD vs TEST Privatbank screen, closed 4/20). Earlier entries claiming OPEN/DISCUSSION were stale.

**Deploy-state sync note (2026-04-20 13:53):** During the T-276/T-277 push, discovered a stale local `origin/main` ref (showed `9721c6b`) while true remote was at `dc771cd`. `git ls-remote origin main` returned the correct SHA; `git fetch origin` silently skipped the ref update. Worked around with explicit `git fetch origin main:refs/remotes/origin/main`. Prior session's claim that `dc771cd` was pushed at 12:45 is CONFIRMED correct — only the local ref was stale.

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
