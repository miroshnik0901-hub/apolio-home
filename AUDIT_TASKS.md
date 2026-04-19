# Apolio Home — Audit Tasks (growing list)

Format: `[ID] [severity] [iter] [area] title — status — fix summary`

Severity: P0 / P1 / P2 / P3
Status: OPEN → INVESTIGATING → FIXED-TEST → FIXED-PROD-PENDING-GO → VERIFIED → CLOSED
Areas: BOT | AGENT | SHEETS | DB | PROMPT | I18N | DOCS | INFRA | TESTS

---

## ITER 1 findings

### DOCS / INFRA drift

- `[A-001] P2 I1 DOCS` DEV_PROD_STATE.md stale — OPEN
  - Claims main=`5b662f6` (T-239 batch dup pre-fetch fallback); actual main per SESSION_LOG = `d74ddc0` (T-248 Revolut negative amounts) at 2026-04-15 16:25, plus later commits `e50fd46`, `6d4822f`, `5996562`. File dates itself 2026-04-15 but is out of sync.
  - Fix: regenerate DEV_PROD_STATE.md from `git log main` and `git log dev` after every push. Add automation hook or Claude-side rule in CLAUDE.md (already present — the rule exists, it's just not being followed).

- `[A-002] P3 I1 DOCS` CLAUDE_WORKING_GUIDE.md tool count drift — OPEN
  - Guide text says "26+1 tools"; actual agent.py TOOLS schema and dispatch dict both contain 30 entries (verified). 3 tools silently added without updating docs: `update_dashboard_config`, `present_options`, `store_pending_receipt` (and earlier `save_receipt`/`get_receipt` pair).
  - Fix: update Section 6 of CLAUDE_WORKING_GUIDE.md to list all 30 tools; enforce in CLAUDE.md the "After Every Code Change" rule.

### INFRA / safety

- `[A-003] P1 I1 TESTS` tests/run_all.py hardcodes PROD sheet IDs — OPEN
  - Lines 33-34: `ADMIN_ID = "1Pt5KwSL-..."`, `MM_ID = "1erXflb..."` — the production IDs. If someone runs this locally without reading, it touches PROD data. Also contradicts CLAUDE.md "NEVER mix environments".
  - Fix: switch to reading from env (`ADMIN_SHEETS_ID`, `MM_BUDGET_SHEETS_ID`) with fallback to TEST IDs, never to PROD IDs. Add a guard that refuses to run if IDs match the PROD constants unless `ALLOW_PROD_READ=1` is set.

### SHEETS data / Config

- `[A-004] P1 I1 SHEETS` Maryna Telegram ID mismatch between Config and Users tab — OPEN
  - Test Admin Config `contributor_users` JSON has Maryna `id=387654321`; Users tab has `telegram_id=219501159`. One is wrong; mismatch means the contributor routing logic reads the wrong ID depending on code path.
  - Fix: confirm the real ID with Mikhail, correct whichever entry is stale. Add a validator in `scripts/ap_sync_prod.py` (or equivalent) that cross-checks Config vs Users tab and warns on mismatch.

- `[A-005] P2 I1 SHEETS` Test Admin DashboardConfig `mode=prod` — OPEN
  - DashboardConfig in the **Test** Admin sheet has `mode='prod'`, which is contradictory. Either dashboards render using prod data source logic in test, or the value is ignored — either way, misleading.
  - Fix: set `mode='test'` in Test Admin DashboardConfig, or document that `mode` is unused.

- `[A-006] P2 I1 SHEETS` Test Budget Config has legacy + per_user model duplicated — OPEN
  - Config contains BOTH new per-user keys (`split_users`, `min_<user>`, `split_<user>`) AND legacy keys (`split_rule=50_50`, `split_threshold`, `base_contributor`, `monthly_cap`). If code reads the legacy keys as a fallback, behavior drifts from the per-user model.
  - Fix: audit intelligence.py + config readers for legacy-key fallbacks; remove deprecated keys from test Config once confirmed unused. Document in CLAUDE_WORKING_GUIDE.md which keys are canonical.

- `[A-007] P2 I1 SHEETS` Test Budget References tab missing Maryna in WHO column — OPEN
  - References > WHO column lists only Mikhail; Maryna absent. If dropdown validation is driven by References, Maryna transactions could be rejected in some UI paths.
  - Fix: add Maryna to WHO in References tab. Confirm dropdown validation source (sheets.py).

### DATA QUALITY

- `[A-008] P2 I1 SHEETS` 4 recent UAH transactions in test Budget without subcategory — OPEN
  - Transactions tab contains 4 UAH rows with `Subcategory` empty. This matches the class of issue T-245/T-246 already fixed for EUR/Il Mulattiere, but UAH path may not be covered by merchant memory or alias backfill.
  - Fix: extend `ap_backfill_subcategories.py` (or equivalent) to cover Category=UAH transactions; verify world-knowledge subcategory inference in the prompt works for Cyrillic notes.

### CODE / transactions.py

- `[A-009] P3 I1 AGENT` dead-branch in tool_add_transaction validation block — OPEN
  - Lines 387-390 of `tools/transactions.py`:
    ```python
    if batch_mode or params.get("force_new"):
        issues = {}
    else:
        issues = {}
    ```
    Both branches assign `{}`. Remnant of an older refactor. No behavior impact but confuses readers and static analysis.
  - Fix: delete the dead conditional; keep `issues = {}` above the try block.

- `[A-010] P2 I1 AGENT` dup detection treats empty category/who as match — OPEN
  - `tool_add_transaction` lines 580-584: `same_cat = (ex_cat == category.lower()) if category else True; same_who = (ex_who == who.lower()) if who else True`. When the agent doesn't set category or who on the new tx, dup detection becomes weaker — any existing tx with matching amount+date+note-overlap flags as duplicate regardless of its category/who. Could produce false positives when user adds a new tx with no category set.
  - Fix: require both category and who to be set on the new tx before running the same_cat/same_who comparison; if missing, skip the category/who gates only on the stricter token-overlap path.

### CODE / intelligence.py

- `[A-011] P2 I1 PROMPT` base_contributor defaults to hardcoded "Mikhail" — OPEN
  - `intelligence.py:256` `base_contributor = env_config.get("base_contributor", "Mikhail")`. For a bot intended to be mass-market (per project instructions), hardcoding the developer's name as default produces wrong per-user balances for any other user where Config is missing the key.
  - Fix: default to `split_users[0]` if set; otherwise raise a clear config error. Remove hardcoded "Mikhail".

- `[A-012] P2 I1 PROMPT` income/transfer with empty Account silently routed to Joint — OPEN
  - `intelligence.py:322-324` `if txn_type in ("income", "transfer"): if acct_type == "Joint" or not acct_type: top_up_joint[who] += amt`. Missing Account → treated as Joint top-up. This could misattribute income as a joint contribution when the user intended personal.
  - Fix: require Account to be set for income; if missing, log a warning and add to a `unaccounted_income` bucket rather than assuming Joint. Or force-prompt account in bot flow.

- `[A-013] P3 I1 PROMPT` phantom "Unknown" contributor possible — OPEN
  - `intelligence.py:307` `who_raw = t.get("Who", "Unknown")`. If a transaction has empty Who, the fallback is "Unknown" — which could then become a key in `balances`/`assets` dicts, appearing in dashboards.
  - Fix: skip transactions with no Who (or attribute to `base_contributor` with a warning log). Current behavior should be audited against test data.

- `[A-014] P3 I1 SHEETS` intelligence.py pokes at private `sheets._cfg_cache` — OPEN
  - `intelligence.py:249` `sheets._cfg_cache.invalidate(f"env_config_{file_id}")`. Private attribute access across module boundaries. If cache implementation changes, this breaks silently.
  - Fix: expose a public `sheets.invalidate_env_config(file_id)` helper.

### PROMPT

- `[A-015] P2 I1 PROMPT` ApolioHome_Prompt.md lists T-series IDs that are already deployed and should be normalized — OPEN
  - The prompt mixes product rules with task-ID archaeology (T-076, T-166, T-185, T-207, T-226, T-246, T-248). Useful for dev trace, noisy for agent. Over time this grows unbounded.
  - Fix: split the prompt into (1) canonical behavior rules (no T-IDs) and (2) a changelog in a separate file. Rotate T-IDs out of the prompt once they're stable for >30 days.

### OUTPUTS / DATA QUALITY (Step 4)

- `[A-016] P1 I1 SHEETS` Test Budget: 30 of 41 active transactions missing Subcategory — OPEN
  - Subcategory coverage is ~27% in test (vs PROD's ~99% after the T-245/T-246 + backfill). Test environment never received the same backfill pass.
  - Impact: Summary aggregates by Category only (still populated), but dashboards that roll up by Subcategory are effectively empty in test. Agent memory / merchant learning has fewer anchors to learn from.
  - Fix: run `ap_backfill_subcategories.py` against Test Budget (with explicit `--env test` flag). Verify keyword aliases + world-knowledge prompt path works for Cyrillic and Latin notes. Re-run after to check coverage ≥90%.

- `[A-017] P2 I1 SHEETS` Test Dashboard stale (3 days) — OPEN
  - `updated_at = 2026-04-14 10:03 UTC`. Today is 2026-04-17. Dashboard refresh hasn't run for 3 days on test. Either no test bot activity triggered it, or the auto-refresh hook isn't wired in staging.
  - Fix: confirm `refresh_dashboard` is called on every add/edit path in staging; or add a cron/scheduled refresh. Add a staleness warning in Dashboard cell when `updated_at` > 24h old.

- `[A-018] P3 I1 SHEETS` Test FX_Rates 2026-05 through 2026-12 all identical (4.25/50.5/1.15/0.86) — OPEN
  - Test FX_Rates table has constant future-month rates (clearly placeholders). Fine if intentional for stable test conversion, but undocumented.
  - Fix: add a header comment in the FX_Rates tab or a README note — "Test env uses frozen FX; rates identical after 2026-04 by design".

- `[A-019] P2 I1 DB` agent_learning contains stale non-canonical names — OPEN
  - Row id=1 has `learned_json.value = 'Marina'` (user_id 360466156 = Mikhail). Legacy data from before the Marina→Maryna alias fix. Acts as noise if the learning layer ever queries by value.
  - Fix: one-off cleanup SQL in PROD DB to normalize learned_json values through the same alias map. Add alias-normalization to the learning-write path so new rows can't regress.

- `[A-020] P3 I1 INFRA` 5 ON HOLD tasks stagnant since 2026-04-03..06 — OPEN
  - T-019, T-045, T-059, T-060, T-064 are all ON HOLD for 11+ days. Without a re-review cadence, ON HOLD becomes "forever-parked", indistinguishable from abandoned.
  - Fix: add a CLAUDE.md rule — every N days (e.g. 14) Claude surfaces ON HOLD tasks and asks Mikhail whether to resume, reject, or keep holding. Or convert to a periodic audit item.

- `[A-021] P2 I1 INFRA` Staging DB unreachable with PROD password — OPEN
  - `maglev.proxy.rlwy.net:17325` rejects the PROD password; no staging DB password present in `.env`. Claude cannot inspect staging state (agent_learning, conversation_log, error_log) without it.
  - Fix: add `STAGING_DATABASE_URL` to `.env` (template it via Railway CLI). Update CLAUDE.md testing section to reference the staging URL.

- `[A-022] P2 I1 SHEETS` Test Budget: 1 active row missing Account — OPEN
  - Column J (Account) empty on one active row. With A-012 behavior (`if not acct_type: treat income as Joint`), this row's impact on contribution math is silent.
  - Fix: manual patch of the test row; enforce Account as required in bot input validation going forward.

### Summary of ITER 1 findings

- **Total:** 22 findings (A-001..A-022)
- **By severity:** 0 × P0, 5 × P1, 12 × P2, 5 × P3
- **By area:** DOCS 3 | SHEETS 8 | AGENT/TRANS 2 | PROMPT 4 | INFRA 3 | TESTS 1 | DB 1
- **Top priorities to fix in ITER 1 / Step 6 (TEST MODE ONLY):**
  - A-001 regenerate DEV_PROD_STATE.md
  - A-002 fix tool-count drift in CLAUDE_WORKING_GUIDE.md
  - A-003 harden tests/run_all.py (no PROD IDs)
  - A-009 remove dead branch in tool_add_transaction
  - A-014 expose public invalidate_env_config helper
  - A-016 backfill Subcategory in Test Budget
- **Out of scope for autonomous fix (need Mikhail confirmation):**
  - A-004, A-011 (Maryna ID / base_contributor default — product-level)
  - A-006 (legacy Config keys removal)
  - A-012 (empty Account → Joint behavior change)
  - A-015 (prompt T-IDs normalization)
  - A-020 (ON HOLD task re-review cadence)
  - A-021 (staging DB URL in .env)

## ITER 2 findings

(Re-read with fresh eyes. Focus: deprecated/zombie code, prompt↔code drift, cleanup candidates.)

- `[B-001] P2 I2 AGENT` Dead tool files shipped in repo — OPEN
  - `tools/envelopes.py` and `tools/receipt_store.py` both start with `⚠️ DEPRECATED — DO NOT USE ⚠️` and are NOT imported anywhere (verified by grep). ~350 lines of dead code lying around, including an outdated `ENVELOPE_SHEETS` column order that could mislead a future reader or AI assistant.
  - Fix: delete both files in a `chore: cleanup deprecated tools` commit. Replace with a one-line note in CLAUDE_WORKING_GUIDE.md Section 4 ("envelope_tools.py is canonical; previous envelopes.py removed 2026-04-17").

- `[B-002] P3 I2 BOT` Zombie `receipt_store = None` declaration — OPEN
  - `bot.py:81` — `receipt_store = None # deprecated — kept for backward compat, not used`. Unused module-level None. Harmless but part of the noise signal.
  - Fix: delete the line when `tools/receipt_store.py` is removed (B-001).

- `[B-003] P2 I2 PROMPT` T-161 "atomic completion" enforced in prompt only, zero code-level guard — OPEN
  - Prompt (`ApolioHome_Prompt.md:192`) mandates "process ALL items in one pass" — but no code in bot/agent/tools enforces it. If the model drifts, bulk processing silently reverts to partial completion.
  - Fix: add an invariant check after batch processing — compare `len(items_input)` vs rows written in `session.last_batch_ids`. Log + raise if mismatch, unless session.failed_batch_items is populated. This hardens the rule beyond prompt guidance.

- `[B-004] P2 I2 DOCS` Stale analysis docs in root — OPEN
  - `PROD_AGENT_ANALYSIS.md` (30KB, 2026-04-13), `TEST_AGENT_ANALYSIS.md` (22KB, 2026-04-13) — one-off reports from 4 days ago. Not referenced in CLAUDE.md read-order; not dated; unclear whether still valid.
  - Fix: move to `docs/archive/` with date prefix (`2026-04-13_PROD_AGENT_ANALYSIS.md`). Add an index in `docs/archive/README.md` explaining provenance.

- `[B-005] P2 I2 BOT` Legacy Russian-only month helpers remain alongside lang-aware versions — OPEN
  - `bot.py:320` `_month_name_ru(...)` and `:325` `_month_label_ru(...)` — comments explicitly label them "legacy". New code uses `_month_name(lang, ...)`. Risk: future handler picks the legacy version, breaks i18n for UK/EN/IT users.
  - Fix: rename legacy to `_month_name_ru_LEGACY_DO_NOT_USE` (or delete if no callers). Grep confirms no calls in current code — safe to remove after verifying once more.

- `[B-006] P3 I2 DOCS` .md docs in project root not organized — OPEN
  - 11 .md files in root (AP_FILE_NAMING, AUDIT_*, ApolioHome_Prompt, CLAUDE*, DEV_PROD_STATE, MEMORY_GUIDE, PROD_AGENT_ANALYSIS, README, SESSION_LOG, TEST_AGENT_ANALYSIS). Mix of operational (read every session), reference, and one-off.
  - Fix: enforce folder structure — `docs/ops/` (CLAUDE, CLAUDE_WORKING_GUIDE, DEV_PROD_STATE, SESSION_LOG), `docs/prompts/` (ApolioHome_Prompt), `docs/archive/` (PROD/TEST analyses, MEMORY_GUIDE if stale). Root keeps README and AP_FILE_NAMING only.

- `[B-007] P2 I2 TESTS` test_regression.py hardcodes `MM_BUDGET` envelope, fails in TEST env — OPEN
  - Section 3.5 "add_transaction end-to-end writes to Sheets" fails with "Конверт MM_BUDGET не найден" because the test sheet's envelope is `TEST_BUDGET`. Same class of issue as A-003 (tests/run_all.py hardcoded PROD IDs).
  - Fix: read envelope name from env var `DEFAULT_ENVELOPE_ID` (fallback: first envelope in Admin sheet's `Envelopes` tab). Apply same hardening to `tests/run_all.py`.

### Summary of ITER 2

- 7 additional findings (B-001..B-007)
- Common theme: housekeeping — dead code, stale docs, prompt-only rules lacking code guards.
- Cumulative ITER 1+2: 29 findings. 0 × P0, 5 × P1, 17 × P2, 7 × P3.

## ITER 3 findings

(Audit-the-audit pass + final verification. Focus: things I missed in 1+2, verify fixes don't regress.)

- `[C-001] P2 I3 AGENT` Second cross-module access to private `sheets._cache` — OPEN
  - `agent.py:1467` — in `_tool_add_category`, direct `sheets._cache.pop(f"ref_{envelope['file_id']}", None)`. Same class of issue as A-014 but for the `ref_*` key, not `env_config_*`. My A-014 fix covered only one of two instances.
  - Fix: add a sibling public method `sheets.invalidate_reference_data(file_id)` and switch the agent.py call. Small, safe, same pattern as the A-014 fix.

- `[C-002] P3 I3 TESTS` test_regression uses `sc._cache.invalidate(...)` directly — OPEN
  - `test_regression.py:753`. Acceptable inside tests (whitebox), but once public invalidation helpers exist (A-014, C-001), the test is a natural place to exercise them.
  - Fix: once C-001 ships, switch the test to `sc.invalidate_reference_data(TEST_FILE_ID)` / `sc.invalidate_txns(TEST_FILE_ID)`.

- `[C-003] P2 I3 DOCS` MEMORY_GUIDE.md and CLAUDE.md may overlap — OPEN
  - MEMORY_GUIDE.md is 7.5 KB in root, not in the "Start of every session" read-order list. CLAUDE.md covers rotation/append rules already. Possible duplicated guidance.
  - Fix: diff MEMORY_GUIDE.md vs CLAUDE.md "Session Memory" section. If redundant, delete MEMORY_GUIDE. If unique (e.g. long-term memory strategy), add to CLAUDE.md read-order or move to docs/ops/.

- `[C-004] P3 I3 AGENT` Cross-currency dup check uses hardcoded `±5% or 0.5 EUR` tolerance — OPEN
  - `tools/transactions.py:538` `eur_tol = max(_pre_eur * 0.05, 0.5)`. 5% is generous for stable fiat but tight for UAH intraday swings. 0.5 EUR floor is arbitrary. The tolerance is a business rule but buried in code with no Config override.
  - Fix: expose `dup_cross_ccy_pct` and `dup_cross_ccy_floor_eur` in env Config with the current 5% / 0.5 as defaults. Low urgency — only matters when tuning dup detection.

- `[C-005] P2 I3 INFRA` No pre-commit or CI verification of "30 tools" vs docs — OPEN
  - A-002 was only findable because I manually compared doc text to code. A simple script that counts TOOLS schema entries and checks CLAUDE_WORKING_GUIDE.md contains that number would prevent recurrence.
  - Fix: add `scripts/ap_verify_docs.py` that asserts tool count matches. Wire into the pre-push hook.

### Verification of ITER 1 fixes (applied TEST MODE only)

- ✅ A-001: `DEV_PROD_STATE.md` — rewritten from live git state (`origin/main=d74ddc0`, `origin/dev=72d7a46`, local dev 1 commit ahead).
- ✅ A-002: `CLAUDE_WORKING_GUIDE.md:58` — "27 tools" → "30 tools", `1988` → `2005` lines.
- ✅ A-009: `tools/transactions.py:387-394` — dead `if/else issues={}` branch removed; `AST walker confirms pattern gone`.
- ✅ A-014: `sheets.invalidate_env_config(file_id)` public method added; `intelligence.py:249` switched from `sheets._cfg_cache.invalidate(...)` to the public helper.
- ✅ Regression: `test_regression.py` → 38/39 passed. The 1 failure is pre-existing (B-007: hardcoded `MM_BUDGET` in section 3.5, unrelated to any audit fix).
- ✅ py_compile: sheets.py, intelligence.py, tools/transactions.py all OK.

### Summary of ITER 3

- 5 additional findings (C-001..C-005).
- Main theme: the ITER 1+2 passes were themselves slightly incomplete — the A-014 fix had a sibling (C-001); docs discipline needs a bot-enforced check (C-005).
- **Cumulative total: 34 findings. 0 × P0, 5 × P1, 19 × P2, 10 × P3.**
