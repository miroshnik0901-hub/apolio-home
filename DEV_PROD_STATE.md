# Apolio Home — Dev / Prod State Tracker
# Updated by Claude after every `git push` to dev or main.
# Read this at the START of every session to understand what's deployed where.

---

## Current State (2026-04-18)

### 🟢 MAIN (Production) — @ApolioHomeBot
**origin/main:** `7b2325e` — T-254 + T-255: batch recap after dup resolution + consolidate items on save-as-one
**Status:** ✅ DEPLOYED on 2026-04-18 19:43 via cherry-pick onto main (ALLOW_MAIN_PUSH=GO_CONFIRMED, Confirm=GO for both)
**Post-deploy sync:** scripts/ap_sync_prod.py — 9/9 checks passed at 19:45

### 🔵 DEV (Staging) — @ApolioHomeTestBot
**origin/dev:** `9527593` — T-254 + T-255 (cherry-picked source) on top of `c9991ad` (T-256) and `0be0234` (AP_FILE_NAMING)

**Commits on dev not yet on main (newest → oldest):**

| Commit | Task | Description | Deploy status |
|--------|------|-------------|---------------|
| `c9991ad` | T-256 | task_log.add_task uses insert_row(index=2) — new rows above CLOSED block | OPEN, Deploy=READY, no Confirm=GO |
| `0be0234` | AP_FILE_NAMING | scripts/ + mcp/sheets_mcp.py renamed ap_* | no linked task — tooling-only |
| `72d7a46` | T-252 | dup question FloodWait fix | DISCUSSION — waiting GO |
| `6a4614e` | T-249 | income 'Income' → 'Top-up' fix | DISCUSSION — waiting GO |

**OPEN/DISCUSSION tasks in Task Log (as of 2026-04-18):**

| Task ID | Status | Topic |
|---------|--------|-------|
| T-256 | OPEN | task_log insert_row(index=2) — fix already on dev, needs GO |
| T-253 | OPEN | refund pair auto-detection (pending implementation) |
| T-252 | DISCUSSION | dup question FloodWait |
| T-250 | DISCUSSION | malformed income row (PROD search negative) |
| T-249 | DISCUSSION | Income→Top-up category fix |
| T-019, T-045, T-059, T-060, T-064 | ON HOLD | stagnant 11+ days — review cadence needed (A-020) |

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
| DB | maglev.proxy.rlwy.net:17325 (no password in .env — A-021) | interchange.proxy.rlwy.net:19732 |
| Railway env ID | `1e6973d7-2c9c-48a3-8197-b61fd4174ba4` | `08e40bf3-cbe4-4a80-be54-1f291c21fe0d` |

⚠️ NEVER mix test and prod resources. Test data → Test Admin only.

---

## Data / Health Snapshot (2026-04-17)

| Metric | PROD | TEST |
|--------|------|------|
| error_log last 24h | 0 | unreachable (A-021) |
| conversation_log total / max ts | 646 / 2026-04-16 19:37 UTC | unreachable |
| Transactions active | ~86 | 41 |
| Transactions missing Subcategory | ~1% (backfilled) | ~73% (30/41) — A-016 |
| Dashboard updated_at | fresh per deploy | stale (2026-04-14 10:03 UTC) — A-017 |

---

## Audit notes (ITER 1 — 2026-04-17)

See `AUDIT_PLAN.md` / `AUDIT_TASKS.md` for the 22 findings from this iteration.
Top TEST-MODE-only fixes applied on this pass:
- A-001: this file (regenerated from real git state)
- A-002: CLAUDE_WORKING_GUIDE.md tool count (26+1 → 30)
- A-009: dead branch in tools/transactions.py:387-390 removed
- Others pending ITER 2/3 or Mikhail confirmation.
