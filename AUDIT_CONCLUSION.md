# Apolio Home — 3-Iteration Audit: Conclusion

**Date:** 2026-04-17
**Mode:** TEST ONLY (dev branch, test sheets `1YAVd…` / `196AL…`, staging env)
**Scope:** full product — docs, prompts, bot, agent, sheets, DB, outputs
**Output artifacts:** `AUDIT_PLAN.md`, `AUDIT_TASKS.md`, `AUDIT_CONCLUSION.md` (this)

## What I found

34 distinct findings across three iterations (A-001..A-022, B-001..B-007, C-001..C-005).

| Severity | Count | Meaning |
|----------|-------|---------|
| P0 | 0 | No data corruption or wrong-account risk found |
| P1 | 5 | UX- or safety-impacting: hardcoded PROD IDs in tests, Maryna ID mismatch, Subcategory gap in test |
| P2 | 19 | Medium: doc drift, cache-coupling, legacy config keys, dead code, hardcoded defaults |
| P3 | 10 | Low: cosmetic, dead assignments, arbitrary tolerances |

### Top 5 risks (ranked)

1. **A-003 — `tests/run_all.py` hardcodes PROD sheet IDs.** A careless local run hits PROD data. Test tooling should default to TEST, refuse PROD unless explicit opt-in.
2. **A-004 — Maryna's Telegram ID mismatch between Admin Config and Users tab.** Silently routes wrong data in contributor logic depending on code path.
3. **A-016 — 30 of 41 test transactions lack Subcategory.** Test env never received the backfill pass applied to PROD; tests using Subcategory rollups are not representative.
4. **A-011 — `base_contributor` defaults to hardcoded `"Mikhail"`.** Blocks the "mass-market" product goal stated in the project brief.
5. **A-012 — empty Account on income silently treated as Joint.** Masks bad data, produces wrong obligation math.

### Themes that emerged across iterations

- **Doc drift is chronic.** `DEV_PROD_STATE.md` was 10+ commits stale; `CLAUDE_WORKING_GUIDE.md` claimed 27 tools when there are 30. The CLAUDE.md rule "after every push update DEV_PROD_STATE" exists but isn't enforced. **C-005 proposes a verify-docs script in the pre-push hook** to make this mechanical rather than cultural.
- **Prompt-only rules are fragile.** T-161 atomic completion, T-248 positive amounts, T-226 no mental math — all live in `ApolioHome_Prompt.md` with zero code-level enforcement. Works as long as the model follows the prompt; fails silently when it drifts. **B-003 proposes a code invariant** for at least T-161.
- **Test/Prod boundary is leaky.** `tests/run_all.py` hardcodes PROD IDs (A-003); `test_regression.py` hardcodes `MM_BUDGET` (B-007); TEST Admin's `DashboardConfig.mode = 'prod'` (A-005). These individually seem small; together they mean a distracted engineer or a CI misconfig can cross environments.
- **Legacy code is accumulating.** `tools/envelopes.py` + `tools/receipt_store.py` are explicitly marked DEPRECATED but shipped (B-001). Both `legacy` and `per_user` split-models coexist in Config (A-006). `_month_name_ru` vs `_month_name(lang, …)` (B-005). Each individual piece is fine; the pile grows.
- **Cross-module private-cache access.** Four call sites reach into `sheets._cfg_cache` / `sheets._cache` from other modules (A-014 partially fixed; C-001 is the second instance). Makes cache implementation changes risky.

## What I fixed (TEST MODE only, uncommitted locally)

| ID | Change | File(s) | Verification |
|----|--------|---------|--------------|
| A-001 | `DEV_PROD_STATE.md` rewritten from live git state | `DEV_PROD_STATE.md` | Cross-checked against `git rev-parse origin/main origin/dev` |
| A-002 | Tool count `27 → 30`, LOC `1988 → 2005` | `CLAUDE_WORKING_GUIDE.md:58` | Matches `agent.py` TOOLS schema count (regex verified) |
| A-009 | Dead `if/else issues={}` branch removed | `tools/transactions.py:387-394` | AST walker confirms pattern gone |
| A-014 | Public `sheets.invalidate_env_config(file_id)` helper added; `intelligence.py` switched to use it | `sheets.py:1221`, `intelligence.py:249` | py_compile OK, regression 38/39 |

**Regression:** `python3 test_regression.py` → 38/39 (the 1 fail is pre-existing B-007, unrelated).
**Self-tests passed:** py_compile on all touched files, behavior-invariant AST check on A-009.
**NOT pushed** — local dev branch only, as per TEST MODE directive and CLAUDE.md "dev needs no GO but main does".

## What I did NOT fix (needs your input)

These are flagged as product/behavior decisions, not bugs in the strict sense:

| ID | Needs | Why I stopped |
|----|-------|---------------|
| A-004 | Correct Maryna Telegram ID | Only you know which of `387654321` or `219501159` is real |
| A-006 | Whether to delete legacy `split_rule/threshold/base_contributor` keys from Config | Removal is irreversible; may impact historical snapshots |
| A-011 | Whether to keep `base_contributor="Mikhail"` default | Tied to mass-market product intent |
| A-012 | Behavior change for empty-Account income | Current silent-default is bad, but the fix needs a UX decision (block vs. warn vs. bucket) |
| A-015 | Prompt T-ID normalization policy | Prompt engineering tradeoff — readable vs traceable |
| A-020 | ON HOLD tasks review cadence | Product decision |
| A-021 | `STAGING_DATABASE_URL` in `.env` | Requires Railway credential |

## Suggested GO sequence (if you agree)

**Batch 1 — doc + cleanup fixes (zero runtime risk):**
- Commit my ITER 1 fixes (A-001, A-002, A-009, A-014) to `dev`
- Add B-001 / B-002 (delete `tools/envelopes.py`, `tools/receipt_store.py`, remove `receipt_store = None` from `bot.py`)
- Add B-004 (move `PROD_AGENT_ANALYSIS.md` + `TEST_AGENT_ANALYSIS.md` to `docs/archive/`)
- Push to `dev`. Staging auto-deploys. No PROD impact.

**Batch 2 — test hardening (TEST env only):**
- A-003 + B-007: harden `tests/run_all.py` and `test_regression.py` against accidental PROD access.
- A-005: fix `DashboardConfig.mode='test'` in Test Admin.
- A-007: add Maryna to References `WHO` column in Test Budget.
- A-008 + A-016: run Subcategory backfill on Test Budget.

**Batch 3 — requires your approval:**
- A-004 / A-011 / A-012 / A-006 / A-015 / A-020 / A-021: decisions listed above.
- C-001: second `_cache` pop in agent.py — trivial code fix, pairs with A-014.
- C-005: add `scripts/ap_verify_docs.py` + pre-push hook wire-up.

**Never in this batch:** anything that touches PROD data, PROD sheet, or `main` branch.

## Answer to your framing questions

> **What is main priority, what is low and not important.**

- **Main priority:** product correctness under mass-market intent — A-011 (hardcoded developer name), A-004 (user ID mismatch), A-012 (silent account defaults), A-016 (test env not representative of PROD).
- **Low:** P3 cosmetic items (B-002 zombie assignment, C-004 arbitrary tolerance, A-018 documented FX placeholders). Fix opportunistically.
- **Not important for now:** the 5 ON HOLD tasks (A-020) can stay parked; decide cadence later.

> **Read all docs, understand targets.**

Apolio Home's stated target (project brief): "Personal finance AI bot — developer & first user, built for personal use, with mass-market potential." Every finding above is scored against that dual target. The single biggest gap between the code and the stated target is the hardcoded `"Mikhail"` defaults — those say "personal use only" at the code level even while the brief says "mass-market potential."

> **Final conclusion after 3 iterations.**

The product is healthy — no P0 incidents, no data corruption risk, 0 PROD errors in last 24h, PROD sync script passing. But it's accumulating friction in four places: doc drift, prompt-only rules, legacy config, and test/prod boundary leaks. None are urgent; all are compounding. Fixing Batch 1 + Batch 2 above eliminates the majority of the noise with zero PROD risk. Batch 3 needs your calls.

Ready for your GO on any subset.
