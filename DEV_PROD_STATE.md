# Apolio Home — Dev / Prod State Tracker
# Updated automatically by Claude after every `git push` to dev or main.
# Read this at the START of every session to understand what's deployed where.

---

## Current State (2026-04-14)

### 🟢 MAIN (Production) — @ApolioHomeBot
**Last commit on main:** `6d05c0d` (merge: sync main with master, task log v1.5)
**Status:** Stable. Contains tasks up to ~T-171 (pre-April 2026 session).

Notable features on production:
- Task Log integration (TaskLog class, Apps Script)
- Google Sheets: Transactions, Summary, Dashboard, Categories, Accounts tabs
- Staging environment setup (separate Test Admin sheet, Railway staging vars)

**⚠️ NOT yet on production (waiting GO):**
- T-172 to T-194 — all listed below in DEV section

---

### 🔵 DEV (Staging) — @ApolioHomeTestBot
**Last commit on dev:** `564097b` (T-194: batch bulk delete)
**Branch:** `dev`

Tasks on dev but NOT yet on main (newest first):

| Commit | Task | Description |
|--------|------|-------------|
| `564097b` | T-194 | Batch bulk delete: 1 read + N deletes. Eliminates 429 quota errors on bulk delete |
| `f46cf5b` | T-192 | Batch dup enrichment prompt: queues dups after batch, shows Update/Add/Cancel one by one |
| `873ca63` | T-192 | Cross-currency dup detection: EUR vs UAH compared via Amount_EUR ±5% |
| `91cb469` | T-190+T-191 | BUG-010 suppressed by stale bulk state fix; agent stops mid-batch fix |
| `bde3949` | T-188+T-189 | No currency conversion in prompt; bulk delete pre-parse IDs from user message |
| `fe4ec91` | T-185+T-186 | Income type=expense fix; Maryna who detection from item note |
| `83642a9` | T-187 | Bulk delete regression fix (1-of-N) |
| `fd8c17b` | T-184+T-185 | cb_split_separate: receipt type, per-item who, batch_mode skips N×2 quota |
| `e1e9ddb` | T-183 | Batch write: _sheets_retry on append_row, skip_sort in loop + 1 sort after |
| `d78f2ca` | T-182 | Dup detection: currency match + ±5% tolerance for non-EUR + note token overlap |
| `3524255` | T-181 | Echo account+split choices in chat; fix amount field variants in cb_split_separate |
| *(earlier)* | T-172..T-180 | Various fixes: sheets retry, contribution history, dashboard redesign |

**Deploy status:** All DISCUSSION+READY, waiting Mikhail's GO (Confirm=GO in Task Log)

---

## How to Read This File

- **Before any session**: check what's on dev vs main to understand current deploy gap
- **After `git push dev`**: add a row to the DEV table above
- **After `git push main`** (on GO): move all DEV rows to MAIN, update last commit
- **Never merge to main without GO from Mikhail** (see CLAUDE.md)

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

---

## Known Differences: Staging vs Production

| Area | Staging | Production | Since |
|------|---------|-----------|-------|
| Bulk delete | Batch (1 read) | Sequential (N reads) | T-194 pending |
| Cross-currency dup | EUR vs UAH via Amount_EUR ±5% | No cross-currency check | T-192 pending |
| Income type detection | 3-layer: schema+category+prompt | Broken (type=expense) | T-185 pending |
| Bulk delete ID parsing | Pre-parsed from user text | Comma-only check | T-187 pending |
| Dashboard | 2-section: SNAPSHOT+HISTORY | Same structure | T-174 (deployed) |
