# QA Checklist — Apolio Home
# Version: 1.0 | Updated: 2026-04-08

This file defines the testing protocol I follow for EVERY change to this codebase.
No exceptions. "It looks right" is not a test.

---

## RULE: TEST FILES MUST STAY CURRENT

Every bug fix or new feature → update `test_regression.py` BEFORE closing the task:
- Fix a bug → add a test that would have caught it
- Add a tool → add a test for its error path
- Add a prompt rule → add a static check that the rule exists in Prompt.md
- Add to Known Bugs table below

If `test_regression.py` doesn't cover something that just broke — it's your fault, not bad luck.

---

## 0. BEFORE ANY CHANGE

- [ ] Read `CLAUDE_WORKING_GUIDE.md` — confirm current architecture
- [ ] Read `DEV_CHECKLIST.md` — confirm relevant sections
- [ ] Read ALL files the change touches, not just the obvious ones
- [ ] Check current branch: `git branch` — must be on `dev`, never `main`
- [ ] Check for uncommitted changes: `git status`
- [ ] No `.git/index.lock` file blocking git: `ls .git/index.lock`

---

## 1. AFTER EVERY CHANGE — ALWAYS RUN

```bash
cd /apolio-home && python test_regression.py
```

All tests must PASS before commit. Zero tolerance for regressions.

---

## 2. AREA CHECKLISTS

### 2.1 Transaction Add (`add_transaction`)

Critical bugs history:
- tx_9b2f4ac1: `sheets.add_transaction` threw, `_execute_tool` caught it silently,
  Claude fallback generated success text anyway. Fixed 2026-04-08.

After any change to `tools/transactions.py`, `agent.py`, `sheets.py`:

- [ ] `test_regression.py::test_add_transaction_success` passes
- [ ] `test_regression.py::test_add_transaction_error_surfaces` passes — tool MUST return
  `{"error": "TRANSACTION FAILED: ..."}` on Sheets failure, not silently succeed
- [ ] `test_regression.py::test_fallback_does_not_generate_success_on_error` passes
- [ ] Manually in TEST bot: send "10 кофе" → verify row appears in TEST Google Sheet
- [ ] tx_id in response matches row in Sheets (column K)

### 2.2 Transaction Delete (`delete_transaction`)

Critical bugs history:
- tx_8d6ca189: bot said "deleted", still in Sheets, parsed_data record remained.
  Fixed: "DELETION FAILED" prefix + parsed_data cleanup.

After any change to `tool_delete_transaction`:

- [ ] `test_regression.py::test_delete_returns_deleted_true` passes
- [ ] `test_regression.py::test_delete_cleans_parsed_data` passes
- [ ] Error messages MUST start with "DELETION FAILED" to block Claude summary
- [ ] On Sheets API failure: returns `{"error": "DELETION FAILED: ..."}`, NOT `{"status": "ok"}`

### 2.3 Receipt Flow (T-076 buttons)

Required flow: photo → `store_pending_receipt` → `present_options` with 4 buttons →
user taps yes_joint or yes_personal → `add_transaction` with Account="Joint"/"Personal" →
IMMEDIATELY `save_receipt` with tx_id.

After any change to `ApolioHome_Prompt.md`, `agent.py`, receipt flow:

- [ ] 4 buttons shown: yes_joint, yes_personal, correct, cancel
- [ ] yes_joint → Account stored as literal "Joint" (NOT account name)
- [ ] yes_personal → Account stored as literal "Personal" (NOT account name)
- [ ] save_receipt called AFTER add_transaction succeeds (not before)
- [ ] `test_regression.py::test_receipt_buttons_present` passes
- [ ] Manually: send receipt photo to TEST bot → confirm buttons appear

### 2.4 Account Types (T-087)

Architecture: Accounts table lives in ADMIN sheet, NOT in budget envelope.
Default values: Joint, Personal only. No invented names.

After any change to `sheets.py`, `setup_sheets_v2.py`:

- [ ] `get_account_types()` reads from Admin sheet Accounts tab
- [ ] Fallback returns ONLY `[{"name":"Joint","type":"Joint"},{"name":"Personal","type":"Personal"}]`
- [ ] Budget envelope files have NO Accounts tab
- [ ] `test_regression.py::test_account_types_from_admin` passes
- [ ] NO invented account names (Wise Mikhail, Wise Family, etc.) in any setup script

### 2.5 Intelligence / Contributions (T-093)

After any change to `intelligence.py`:

- [ ] `_normalize_who()` is called in contributions loop
- [ ] Assets calculated correctly: income→Joint adds to who, expense→Personal adds to who
- [ ] `has_account_types` flag reflected in output
- [ ] `test_regression.py::test_intelligence_no_crash` passes
- [ ] Balance = Assets - Obligations (not just contributions)

### 2.6 Agent Error Handling

After any change to `agent.py`:

- [ ] `tool_results = []` initialized BEFORE the for loop (prevents NameError in fallback)
- [ ] Tool errors with "TRANSACTION FAILED" / "DELETION FAILED" / "SAVE FAILED" prefixes
  are returned immediately without asking Claude to summarize
- [ ] Fallback does NOT generate success text when last tool result has `"error"` key
- [ ] `test_regression.py::test_agent_surfaces_tool_errors` passes

### 2.7 i18n

After any change adding user-facing strings:

- [ ] All new strings added to `i18n.ts()` / `i18n.t()` with all 4 languages: RU, UK, EN, IT
- [ ] No hardcoded Russian-only strings in bot responses
- [ ] `test_regression.py::test_i18n_keys_complete` passes

### 2.8 Google Sheets Schema

After any change to `setup_sheets_v2.py` or sheet structure:

- [ ] Column order: A:Date B:Amount_Orig C:Currency_Orig D:Category E:Subcategory
  F:Note G:Who H:Amount_EUR I:Type J:Account K:ID L:Envelope M:Source N:Wise_ID
  O:Created_At P:Deleted
- [ ] No columns added without updating all writers (add_transaction row list)
- [ ] TEST file updated BEFORE PROD
- [ ] Data validation on Account column (J) — dropdown from Admin Accounts

### 2.9 PostgreSQL

After any change to `db.py` or DB usage:

- [ ] `parsed_data` cleanup happens when transaction is deleted
- [ ] No orphaned `parsed_data` rows after delete
- [ ] `test_regression.py::test_db_is_ready` passes (DB connection works)

---

## 3. DEPLOYMENT PROTOCOL

```
local test → commit → push dev → Railway staging auto-deploys
→ test on TEST bot → confirm OK → merge dev→main → Railway prod auto-deploys
→ verify with /version command on prod bot
```

Rules:
- NEVER push to `main` directly
- NEVER merge to `main` without explicit GO from Mikhail
- After staging deploy: run at minimum tests in Section 2.1, 2.2, 2.3
- Use `/version` command in bot to confirm correct commit is running

---

## 4. RED FLAGS — STOP AND INVESTIGATE

If any of these happen during development, STOP and fix before proceeding:

- Bot responds "✓ ... Transaction saved" but nothing in Google Sheet
- Bot responds "Deleted" but row still visible in Sheet
- `_execute_tool` returns `{"error": "..."}` for a write operation
- Agent fallback fires on a write operation (means Claude got no text from last iteration)
- `sheets.add_transaction` or `sheets.hard_delete_transaction` throws any exception
- `parsed_data` row remains after transaction delete
- Account name "Wise Mikhail", "Wise Family", or any invented name appears anywhere
- Buttons (yes_joint / yes_personal) not shown after receipt analysis

---

## 5. KNOWN BUGS FIXED (do not reintroduce)

| Bug ID | Description | Fixed In | File |
|--------|-------------|----------|------|
| BUG-001 | add_transaction false success — sheets.add_transaction exception caught silently, Claude fallback generated success text | 2026-04-08 | agent.py, tools/transactions.py |
| BUG-002 | delete_transaction false success — no "DELETION FAILED" prefix, parsed_data not cleaned | 2026-04 | tools/transactions.py |
| BUG-003 | Invented account names (Wise Mikhail etc.) hardcoded in setup script | 2026-04 | setup_sheets_v2.py |
| BUG-004 | Accounts tab created in budget envelope instead of Admin | 2026-04 | setup_sheets_v2.py |
| BUG-005 | .git/index.lock blocking commits — leftover from interrupted session | 2026-04 | (process issue) |
| BUG-006 | T-076 buttons not confirming receipt — prompt didn't have correct button values | 2026-04 | ApolioHome_Prompt.md |

---

## 6. RUNNING TESTS

```bash
# Full regression suite
python test_regression.py

# Quick smoke test (sheets connectivity only)
python -c "from sheets import SheetsClient; s=SheetsClient(); print('OK')"

# Specific test
python -m pytest test_regression.py::TestTransactions::test_add_success -v
```

Test file: `test_regression.py`
Previous fix tests: `test_fixes.py` (specific to commit 7d55a00)
