**Start of every session — read in this order:**
1. `SESSION_LOG.md` — full history: actions, decisions, pending, state
2. `DEV_PROD_STATE.md` — what's on dev vs main, what's waiting GO, test/prod resource table
3. `CLAUDE_WORKING_GUIDE.md` — architecture and schemas (before any code change)
4. Run relevant tests before every push

## ⚠️ Mandatory Self-Testing After EVERY Fix

**Claude must test its own fixes before declaring them done. No exceptions.**

### After EVERY code fix:
1. **Unit test**: run `python3 -m py_compile <changed_files>` + `python3 test_regression.py`
2. **Integration test**: write and run a Python script that directly simulates the fix against live test data
   - For dup detection fixes: simulate the dup check against test Sheets data and verify matches found
   - For FX/conversion fixes: verify actual FX read returns expected values
   - For balance calculation fixes: compute expected result and compare with actual
3. **Push only after test PASSES** with concrete output proving it works
4. **Log test result** in SESSION_LOG.md: `YYYY-MM-DD | TEST | what was tested + result`

### Pattern: "зафіксовано" without testing = violation

If a fix is pushed without self-testing:
- The commit message must say `⚠️ NOT SELF-TESTED`
- A follow-up task must be created immediately to test and verify
- Mikhail should be warned that the fix is unverified

### What counts as a valid self-test:
- ✅ Python script running against live test data with concrete output showing the fix works
- ✅ Simulation of the exact bug scenario (not just compilation passing)
- ❌ "The logic looks correct" — not a test
- ❌ "py_compile passes" — not a test for logic bugs
- ❌ "regression tests pass" — not sufficient for logic changes in business rules

**After every `git push`** — update `DEV_PROD_STATE.md`:
- `git push dev` → add row to DEV table with commit hash + task + description
- `git push main` → move DEV rows to MAIN section, update "last commit on main"

**After every reply** — append one line to `SESSION_LOG.md`. No exceptions.

## Session Memory — mandatory

**After every reply** — append one line to `SESSION_LOG.md`. No exceptions. Claude doesn't know when the context window ends, so every message could be the last.

Step 1: run `date '+%Y-%m-%d %H:%M'` to get the timestamp.
Step 2: check log size: `wc -c SESSION_LOG.md`
Step 3: if size > 16384 bytes → rotate (see Rotation below). Otherwise append one line:
```
YYYY-MM-DD HH:MM | CHAT    | what was discussed
YYYY-MM-DD HH:MM | ACTION  | what was done + result
YYYY-MM-DD HH:MM | DECISION| key technical or product decision
YYYY-MM-DD HH:MM | PENDING | waiting on Mikhail — what exactly
YYYY-MM-DD HH:MM | STATE   | current system state snapshot
YYYY-MM-DD HH:MM | NEXT    | concrete next step if mid-task
```

Never rewrite past entries. Just append.

### Rotation (triggered when SESSION_LOG.md > 16384 bytes)

**Order is critical — write new file FIRST, then archive old. Never the reverse.**

1. Get timestamp: `TS=$(date '+%Y-%m-%d_%H-%M')`
2. Create `SESSION_LOG_NEW.md` with mechanical summary — no interpretation, verbatim copy:

```
# Session Log — append only, never edit past entries
# Types: CHAT | ACTION | DECISION | PENDING | STATE | NEXT
# Format: YYYY-MM-DD HH:MM | TYPE | content
# Time: always run `date '+%Y-%m-%d %H:%M'` before writing an entry
# ROTATED from: logs/SESSION_LOG_ARCHIVE_${TS}.md

YYYY-MM-DD HH:MM | STATE    | [last STATE entry from current log — verbatim]
YYYY-MM-DD HH:MM | DECISION | [each DECISION from current log — one line each, verbatim]
YYYY-MM-DD HH:MM | PENDING  | [all unclosed PENDING from current log — verbatim]
YYYY-MM-DD HH:MM | NEXT     | [last NEXT entry from current log — verbatim]
```

3. Move old log to archive: `mv SESSION_LOG.md logs/SESSION_LOG_ARCHIVE_${TS}.md`
4. Rename new: `mv SESSION_LOG_NEW.md SESSION_LOG.md`
5. Append the current entry that triggered the rotation to the new `SESSION_LOG.md`

Rules for summary:
- Extract by type only — `grep "| STATE\|DECISION\|PENDING\|NEXT"` from current log
- For STATE and NEXT: take only the last occurrence
- For DECISION and PENDING: take all occurrences
- No paraphrasing, no omissions, no interpretation

## Languages

Mikhail writes in RU / UK / EN / IT freely, in any order, mixed in one message.
All new user-facing strings go through `i18n.ts()` / `i18n.t()` — all 4 languages required.
Never hardcode UI strings. Match Mikhail's language in replies.

## Task Log — comment rule

Every comment written to "Apolio Comment" field must be **self-contained**.
The next Claude session has zero chat context — the comment must be enough to understand everything.

Required:
- **What** — exact symptom, not just "fix X"
- **Why** — root cause if known
- **Files/functions** involved
- **What was tried** and result
- **Next step** — concrete and actionable

❌ `[2026-04-13] Fixed topic validation`
✅ `[2026-04-13] Empty topic passed validation because "if topic and ..." is falsy for "". Fixed: changed to "if not topic or topic not in VALID_TOPICS" in add_task(). Same fix in update_task(). Deployed to prod. Verify: add_task with topic="" should raise ValueError.`

## Git & Deploy

- Git: push to `main` for production, `dev` for staging. Never `master`.
- Railway auto-deploys: `main` → production, `dev` → staging.
- Never push to `main` without Confirm=GO from Mikhail. Staging (`dev`) needs no confirmation.

## Dev Workflow (mandatory sequence)

### Before writing code
- [ ] Read ALL files the change touches
- [ ] Trace full chain: initialization → usage → rendering
- [ ] State target end-state explicitly

### Before pushing to `dev`
```bash
python3 -m py_compile bot.py auth.py sheets.py intelligence.py agent.py  # L1
python3 test_regression.py                                                 # L2 unit tests
```
All must pass. Then push to `dev`.

### After pushing to `dev`
```bash
python3 tests/run_all.py   # L1–L3: static + unit + live Sheets (48 checks)
```
Check Railway staging logs — no import errors. Verify bot responds on @ApolioHomeTestBot.
Only after this passes → ask Mikhail for GO → push `main`.

### After pushing to `main`
Check Railway production logs. Spot-check bot on @ApolioHomeBot.

## After Every Code Change

- If architecture changed → update `CLAUDE_WORKING_GUIDE.md` (file map, tools, schemas).
- New agent tool → add to TOOLS schema + dispatch dict + section 6 of `CLAUDE_WORKING_GUIDE.md`.

## Google Sheets IDs

| Resource | Environment | ID |
|----------|------------|-----|
| Admin sheet | **Production** | `1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk` |
| Admin sheet | **Test** | `1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM` |
| Budget file | **Production** (MM_BUDGET) | `1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ` |
| Budget file | **Test** | `196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788` |
| Task Log | **Shared** | `1Un1IHa6ScwZZPhAvSd3w5q31LU_JmeEuATPZZvSkZb4` |

| Mikhail Telegram ID | — | `360466156` |
| Railway project ID | — | `55240cdd-2cbc-4451-b6c9-ca97ce595c18` |
| Railway service ID (bot) | — | `8ec97839-6d49-4cdd-a012-1f6d54853454` |
| Railway env ID | **Production** | `08e40bf3-cbe4-4a80-be54-1f291c21fe0d` |
| Railway env ID | **Staging** | `1e6973d7-2c9c-48a3-8197-b61fd4174ba4` |

**NEVER mix environments.** Test data → Test Admin only. Production data → Production Admin only.

## Google Sheets Access

- Credentials: `GOOGLE_SERVICE_ACCOUNT` env var (base64-encoded service account JSON)
- Service account: `apolio-home-bot@apolio-home.iam.gserviceaccount.com`
- OAuth (for sheet creation): `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`
- All env vars are in `.env` file in project root (gitignored)
- `task_log.py` uses the same `GOOGLE_SERVICE_ACCOUNT` to read/write Task Log sheet
- To use in Cowork/sandbox: load `.env` from mounted folder before importing project modules

## Testing

- **Claude is QA. Never ask Mikhail to test.** After every push to `dev`, Claude must verify staging works — check deploy logs, query staging DB, test bot responses.
- All dev/testing happens on staging (@ApolioHomeTestBot, `dev` branch).
- Staging DB: maglev.proxy.rlwy.net:17325
- Production DB: interchange.proxy.rlwy.net:19732
