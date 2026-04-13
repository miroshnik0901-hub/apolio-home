# Apolio Home — PROD Agent Analysis
**Source:** PROD.pdf (28 pages, @ApolioHomeBot)
**Test period:** April 3–13, 2026 (screenshots from production session)
**Purpose:** Detailed QA breakdown. Cross-compared with TEST agent behavior.
**Status:** COMPLETE — see SECTION 13 for cross-comparison and task seeds.

---

## ANALYSIS FRAMEWORK

Each observation is tagged:
- `[BUG]` — incorrect behavior, crash, wrong output
- `[UX]` — awkward flow, confusing message, missing confirmation
- `[DATA]` — wrong data stored or displayed
- `[LANG]` — language inconsistency
- `[OK]` — behavior correct and clean
- `[NOTE]` — neutral observation
- `[REGRESSION]` — works in TEST, broken in PROD
- `[PROD-ONLY]` — bug or issue not observed in TEST

Severity: `CRIT` / `HIGH` / `MED` / `LOW`

---

## SECTION 1: RECEIPT PARSING

### 1.1 Mercato Chieri — 34.20 EUR (Apr 3)
**Source:** Receipt photo forwarded

`[OK]` **IMPROVEMENT vs TEST:** All 9 items parsed correctly (TEST only showed 7).
  - Хлеб LIZZI, Батончики KELLOGG, Батончики ПИУ, Оливковое масло, Лосось ICER, Мёд,
    Салат, + 2 additional items that TEST missed.
  - Delta: 34.20€ balanced. B-04 (item count mismatch) appears fixed in PROD.

`[OK]` НДС rates per item shown (more verbose than TEST).
`[OK]` Technical document info, table/waiter details parsed.

---

### 1.2 Armonia Dentale Sas — 132 EUR
**Source:** Dental clinic receipt (part of Maryna April 3 batch)

`[OK]` Correctly categorized as Здоровье / стоматология.
`[OK]` Correct amount, date, merchant.
`[NOTE]` This receipt appeared in duplicate detection check — worked correctly.

---

### 1.3 Classique Cafe / Vecchia Dogana — April 9–10
**Source:** Restaurant receipts + Nexi/UC slips

`[BUG][HIGH]` **B-03 CONFIRMED in PROD: Intermittent "Что-то пошло не так"**
  - Page 21: User sent 2 receipt photos → got "⚠️ Что-то пошло не так. Попробуй ещё раз."
  - Same pattern as TEST — transient failure, no user-visible reason.
  - Same fix needed: retry logic + error classification.

---

## SECTION 2: BANK STATEMENT PROCESSING

### 2.1 Ukrainian Bank Statement — Currency Confusion
**Source:** Bank statement screenshot (pages 1–10 of PROD.pdf)

`[BUG][HIGH]` **P-03 PROD-ONLY: UAH transactions recorded as EUR**
  - Bot processed a UAH bank statement and recorded 7 transactions in EUR instead of UAH.
  - User had to manually correct currency and delete 7 wrong entries.
  - Not observed in TEST (TEST correctly handled UAH → EUR with exchange rate).
  - **Root cause suspected:** PROD has different currency detection logic, or a regression was
    introduced between TEST deployment and PROD deployment.
  - **Impact:** Direct data integrity loss — wrong currency in DB.

---

### 2.2 Family Account (Wise/Bank App) — March 31
**Source:** Screenshot of Wise Family Account forwarded by Mikhail (page 22)

`[DATA][HIGH]` **P-04 PROD-ONLY: Incoming transfers counted as expenses**
  - Screenshot showed: Gardaland 208€ + Int'l School 662€ + Capitolo Emanuele 1,365€
    + From EUR +400€ (incoming) + From Maryna +100€ (incoming).
  - Real expenses: 208 + 662 + 1,365 = **2,235 EUR**.
  - Bot reported "Итого расходов: 2,235 EUR" correctly in the text summary.
  - Bot then **recorded** the entry as **2,735.0 EUR** (= 2,235 + 400 + 100).
  - Incoming transfers (+400 + +100) were added to expenses in the DB write.
  - This is different from what was shown to the user in the confirmation screen.
  - **Impact:** 500 EUR overcounting. User saw 2,235 confirmed, 2,735 stored. Undetectable
    without opening the raw transaction.

`[BUG][CRIT]` **B-01 CONFIRMED in PROD: float('2,735.00') crash**
  - The 2,735.0 entry stored with comma format crashes report loading.
  - Visible on page 21: "❌ Не удалось загрузить отчёт: could not convert string to float: '2,735.00'"
  - Exact same error as TEST. Same root cause. Fix is the same.

`[DATA][MED]` **Balance distortion cascade**
  - The 2,735 EUR overcounted entry causes Mikhail's balance to show -2,192 EUR (должен).
  - This is clearly wrong — inflated by the 500 EUR transfer overcounting + the inflated
    entry itself being double the real expense total.
  - Every balance shown to user after this point is wrong.

---

### 2.3 Maryna April 3 Batch — Duplicate Loop
**Source:** Pages 22–26

`[BUG][HIGH]` **P-05 PROD-ONLY: Session loop — same transactions reprocessed 3+ times**
  - The April 3 Maryna batch (6 transactions, 481.47 EUR) was processed through at least
    3 separate flows in PROD:
    1. First attempt: bot canceled by user (page 23)
    2. Second pass from bank app screenshot (pages 25–26): partial add (2/6)
    3. Third pass: same screenshot again, all 6 shown as "ready to record" (page 26)
  - Bot didn't track that these were already processed in the same session.
  - Duplicate detection fired correctly (Pam Panorama caught as duplicate after first adds).
  - But the bot kept offering to record them again on every new message.
  - **Root cause:** No session-level "already processed" flag. Each photo triggers fresh parse.
  - **UX cost:** User had to manually track state — bot gave no clear "all done, nothing new."

`[BUG][MED]` **B-05 CONFIRMED in PROD: Batch add partially completes, stops at first duplicate**
  - First attempt: added JYSK (133.45) only, stopped because стоматология was duplicate.
  - Second attempt: added 4 more, skipped JYSK (now duplicate from first attempt).
  - The flow is technically correct but the UX is broken:
    - User sees "Добавил 1 из 6" → "Добавил 4 из 5 remaining" → thinks something failed.
    - Should be a single atomic operation with one summary: "Added 5/6. Stomatologia skipped (duplicate)."
  - PROD behavior matches TEST (same partial completion issue).

`[OK]` Duplicate detection itself is working — correctly identifies Пам Панорама, Armonia Dentale.
`[OK]` Bot explains why items were skipped (better than TEST which was silent).
`[OK]` User cancel (Отмена) works correctly — "Отменено. Транзакции не записаны."

---

## SECTION 3: CRITICAL INFRASTRUCTURE BUGS (PROD-ONLY)

### 3.1 Google Sheets API Rate Limit
**Source:** Pages 1–10 of PROD.pdf

`[BUG][CRIT]` **P-01 PROD-ONLY: RESOURCEEXHAUSTED 429 — Sheets API quota exceeded**
  - Error: "Google Sheets API quota exceeded: ReadRequestsPerMinutePerUser"
  - Appeared during normal usage, not high-load scenario.
  - Not observed in TEST (likely because TEST has lower traffic / fewer Sheets reads).
  - **Impact:** Bot becomes unresponsive mid-session. User sees generic error or no response.
  - **Fix needed:** Implement read caching, reduce Sheets reads per operation, or batch reads.
    Consider caching Dashboard/Config data for 60 seconds between refreshes.

### 3.2 Raw XML/Invoke Code Leaked to Chat
**Source:** Pages 1–10 of PROD.pdf

`[BUG][CRIT]` **P-02 PROD-ONLY: Tool invocation XML shown to user in chat**
  - Bot sent raw text like:
    `<invoke name="present_options"><parameter name="choices">[...]</parameter></invoke>`
  - This is internal tool call syntax exposed directly in the Telegram message.
  - Not observed at all in TEST — this is a PROD-only regression.
  - **Root cause:** Likely a model response where the tool call was placed in the text body
    instead of being intercepted and executed. The output parser didn't strip it.
  - **Impact:** Confusing UX, exposes system internals, breaks user trust.
  - **Fix needed:** Add output sanitization layer — strip/catch any `<invoke>` or XML tags
    before sending to Telegram. Check `agent.py` response handling.

---

## SECTION 4: BUDGET & FINANCIAL DISPLAY

### 4.1 Budget Widget
**Source:** Pages 27–28

`[BUG][MED]` **P-06 PROD-ONLY: Budget percentage math is wrong**
  - Page 27 shows: `783 / 1,500 EUR (22%)` — but 783/1500 = **52.2%**, not 22%.
  - The percentage displayed doesn't match the numbers displayed.
  - Page 28 shows: `783 / 2,500 EUR (31%)` — 783/2500 = **31.3%** ✓ This one is correct.
  - Two dashboards in the same session show different budget caps (1,500 vs 2,500).
  - **Root cause likely:** The 1,500 EUR is the TEST monthly_cap (overwritten from 3,500 to 1,500
    in the Config tab by earlier session). Prod Config has wrong value. See PENDING section.
  - The percentage shown with the 1,500 cap appears to be calculated against a different denominator.

`[NOTE]` Budget cap inconsistency confirms the PENDING item: prod Budget file → Config tab
  → monthly_cap was overwritten with test value. Mikhail needs to correct manually.

`[OK]` Page 28 dashboard (2,500 EUR cap): categories, percentages, and totals all correct.
  - Food: 509/783 = 65% ✓, Home: 133/783 = 17% ✓, Здоровье: 132/783 = 17% ✓, Personal: 8/783 = 1% ✓
`[OK]` Progress bar shows correct number of filled segments for the 2,500 cap version.

### 4.2 Category Name Language Inconsistency
**Source:** Pages 24, 27–28

`[LANG][MED]` **P-07 PROD-ONLY: Categories shown in mixed RU/EN without pattern**
  - Page 27–28: "Food" (EN), "Home" (EN), "Personal" (EN), "Здоровье" (RU).
  - In TEST: categories consistently shown in Russian (Еда, Жильё, Здоровье, Личное).
  - PROD shows a mix — some translated, some not, no discernible rule.
  - Also: page 25 bot asks "Housing (жильё) или Household (домашние товары) или Home?" —
    three category options all in English despite user writing in Russian.
  - **Fix:** All category names must be run through i18n and displayed in user's set language.

### 4.3 JYSK — Duplicate Category Assignment
**Source:** Page 21 ("Последние 10" list)

`[DATA][MED]` **P-08: JYSK 133.45 EUR appears twice with different categories**
  - "Последние 10" list shows:
    - `Жильё 133.45 EUR — Maryna 2026-04-03 — JYSK`
    - `Быт 133.45 EUR — Maryna 2026-04-03 — JYSK`
  - Same amount, same date, same merchant — two different categories.
  - Could be: (a) genuine duplicate entry in DB, or (b) single entry shown twice due to
    display bug.
  - In context of the batch flow (pages 23–26), JYSK was added once during the first batch
    pass. The second appearance suggests a duplicate was created.
  - **Impact:** Inflates Maryna's spend by 133.45 EUR. Shows wrong totals in reports.
  - **Verify:** Query DB for JYSK entries on 2026-04-03 for Maryna.

---

## SECTION 5: LANGUAGE & LOCALIZATION

### 5.1 Language Switching to English Mid-Russian Session
**Source:** Page 24

`[LANG][HIGH]` **P-09 PROD-ONLY: Bot switches to English without trigger**
  - Session was entirely in Russian. User wrote in Russian throughout.
  - After failed batch add, bot responded in English:
    "I tried to record the transactions from April 3rd, but the system detected that they
    are already recorded as duplicates."
  - No `/language` command, no language change request from user.
  - This was a standalone English message in an otherwise Russian conversation.
  - In TEST: B-07 was system/error messages staying in English after explicit language switch.
    In PROD: English appears even without any language switch — more severe.
  - **Root cause:** Likely a fallback error path that ignores i18n entirely.
  - **Fix:** All bot output paths, including duplicate detection messages, must use i18n.t().

### 5.2 Category Confirmation in English
**Source:** Page 24

`[LANG][MED]` **P-10 PROD-ONLY: Mass recategorization accepted without verification**
  - Bot proposed: "Понял, все 5 оставшихся транзакций Марула записать в категорию Housing?"
    Listing: JYSK → Housing, Pam Panorama → Housing, Mercato → Housing, Mix Markt → Housing,
    Cm Moda → Housing.
  - All 5 transactions proposed as "Housing" — including food (Mercato, Pam Panorama, Mix Markt)
    and clothing (Cm Moda). Only JYSK is actually housing-related.
  - User selected `record_all_housing` — bot accepted without warning.
  - This would have written wrong categories to DB (was blocked only by duplicate detection).
  - **Root cause:** Bot accepted user's category override for all items without checking
    whether the category is plausible for each merchant type.
  - **Fix:** At minimum, warn when applying a single category to items that were previously
    assigned different categories.

---

## SECTION 6: MULTI-STEP WORKFLOW

### 6.1 Duplicate Detection
`[OK]` Duplicate detection fires correctly for:
  - Armonia Dentale Sas (Maryna batch)
  - JYSK (after first batch pass)
  - Pam Panorama (after records from first pass)
`[OK]` Bot explains reason for skip (better than TEST which was silent).

### 6.2 Cancel Flow
`[OK]` Отмена button works — "Отменено. Транзакции не записаны."
`[OK]` Bot checks for existing records before processing (page 23 — found April 3 already recorded, didn't re-add).

### 6.3 Context Loss Between Sessions/Messages
`[BUG][MED]` **B-08 CONFIRMED in PROD: Context state lost between turns**
  - Same behavior as TEST: bot reprocesses already-handled transactions.
  - In PROD this is more impactful because it triggered a 3-pass loop (pages 23–26).

---

## SECTION 7: WELCOME & NAVIGATION

### 7.1 /start command
**Source:** Page 28

`[OK]` Welcome message in Russian, shows user's name (Mikhail).
`[OK]` Examples shown in Russian: «кофе 3.50», «продукти 85 EUR Esselunga», «покажи звіт за март».
`[NOTE]` Example "продукти" is Ukrainian (not Russian) — minor inconsistency when user language is EN.
`[OK]` Navigation buttons appear immediately after welcome.

### 7.2 Main Menu
`[OK]` Menu buttons: Этот месяц / Прошлый месяц / Последние 10 / Поиск / Взносы и расчёты / Система.
`[OK]` All buttons present and functional.

---

## SECTION 8: SUMMARY — PROD BUG CATALOG

### 8.1 Bugs confirmed from TEST (same in both)

| # | ID | Severity | Description | TEST | PROD |
|---|---|---|---|---|---|
| 1 | B-01 | CRIT | `float('2,735.00')` crashes report loading | ✓ | ✓ |
| 2 | B-02 | HIGH | tx_id mismatch on delete (bot reconstructs wrong ID) | ✓ | likely ✓ |
| 3 | B-03 | HIGH | Nexi slip: intermittent "что-то пошло не так" | ✓ | ✓ |
| 4 | B-04 | MED | Mercato: 2 items missing from 9-item receipt | ✓ | **FIXED** |
| 5 | B-05 | MED | Batch add stops at first duplicate, requires re-confirm | ✓ | ✓ |
| 6 | B-06 | MED | Duplicate transactions on batch record + retry | ✓ | ✓ |
| 7 | B-07 | MED | System/error messages in English after language switch | ✓ | worse (no switch needed) |
| 8 | B-08 | MED | Context state lost — bot re-derives already-done state | ✓ | ✓ worse |

### 8.2 PROD-ONLY bugs (regressions or new issues)

| # | ID | Severity | Description |
|---|---|---|---|
| 1 | P-01 | CRIT | Google Sheets API 429 quota exceeded mid-session |
| 2 | P-02 | CRIT | Raw `<invoke>` XML leaked into Telegram chat |
| 3 | P-03 | HIGH | UAH bank statement → transactions recorded in EUR (wrong currency) |
| 4 | P-04 | HIGH | Incoming transfers (+400 +100) counted as expenses (500 EUR overcounted) |
| 5 | P-05 | HIGH | Session loop — same batch reprocessed 3+ times |
| 6 | P-06 | MED | Budget percentage math wrong (783/1500 shown as 22% vs actual 52%) |
| 7 | P-07 | MED | Categories displayed in mixed EN/RU with no pattern |
| 8 | P-08 | MED | JYSK appears twice in "Last 10" with different categories (possible duplicate in DB) |
| 9 | P-09 | HIGH | Bot switches to English mid-Russian session without trigger |
| 10 | P-10 | MED | Mass recategorization accepted without plausibility check |

---

## SECTION 9: WHAT WORKS WELL IN PROD (vs TEST baseline)

1. **B-04 FIXED**: Mercato receipt — all 9 items parsed (TEST only got 7). Improvement.
2. **Duplicate detection** — firing correctly and with explanation (better than TEST).
3. **Family account parsing** — correctly identifies categories, payers, dates.
4. **Cancel flow** — works cleanly.
5. **Welcome message** — correct language, correct name, good examples.
6. **Budget dashboard categories math** — when budget cap is correct (2500 EUR view), all % correct.
7. **Menu navigation** — all buttons functional.
8. **Batch-add with explanation** — PROD explains WHY items were skipped (TEST was silent).
   This is an improvement in transparency even if the flow still has B-05 issue.

---

## SECTION 10: TEST vs PROD COMPARISON — REGRESSIONS

| Feature | TEST | PROD | Status |
|---|---|---|---|
| Receipt: Mercato item count | 7/9 items | 9/9 items | **FIXED in PROD** |
| float('2,735.00') crash | BUG | BUG | Same |
| tx_id delete failure | BUG | BUG (expected) | Same |
| Nexi slip intermittent error | BUG | BUG | Same |
| Batch add partial completion | BUG | BUG | Same |
| Batch add skip explanation | Silent | Explains why | **Better in PROD** |
| System error language | EN after language switch | EN without switch | **REGRESSION** |
| Sheets API quota | No | RESOURCEEXHAUSTED | **REGRESSION** |
| XML invoke leak | No | Yes | **REGRESSION** |
| Currency handling (UAH→EUR) | Correct | Wrong currency | **REGRESSION** |
| Incoming transfers vs expenses | N/A | Miscounted | **REGRESSION** |
| Session context retention | Poor | Poor + loop | **REGRESSION** |
| Category language (RU) | Consistent RU | Mixed EN/RU | **REGRESSION** |
| Budget percentage display | N/A tested | Math error (1500 cap) | **REGRESSION** |
| JYSK duplicate in DB | No | Possible yes | **REGRESSION** |

---

## SECTION 11: ROOT CAUSE HYPOTHESES

### Why PROD has more bugs than TEST?

1. **Sheets API quota (P-01):** PROD has more traffic. TEST was a single-user isolated session.
   Each bot interaction reads Sheets multiple times — this compounds under real usage.

2. **XML leak (P-02):** The `present_options` tool call is being passed through the response
   body instead of being intercepted. This could be a model behavior change or an error in
   `agent.py` where the response isn't parsed before sending to Telegram.

3. **Currency bug (P-03):** The PROD bot may have received a bank statement in a different
   format than what TEST processed. Or the currency detection was regressed in a commit
   between TEST deployment and PROD deployment. Need to check git diff dev→main for
   any changes to currency parsing logic.

4. **Transfer vs expense (P-04):** The Wise/family account parser doesn't distinguish between
   debit (expense) and credit (incoming transfer) — sums everything. Same image in TEST was
   parsed correctly. Either the PROD version has a different prompt/parser, or the specific
   screenshot format here wasn't handled.

5. **Session loop (P-05):** Each new photo message triggers a fresh tool chain. Without
   session-level state, the bot can't know "I already processed this image." This is a
   fundamental architecture issue — needs explicit session state per chat_id.

---

## SECTION 12: PENDING (requires Mikhail action)

1. **Budget Config prod** — monthly_cap and split_rule overwritten with test values.
   Edit manually: Google Sheets prod Budget file → Config tab → set correct monthly_cap.
   After edit: refresh Dashboard.

2. **Verify JYSK duplicate** — check if two JYSK 133.45 EUR entries exist on 2026-04-03
   for Maryna in PROD DB. If yes, delete one.
   ```sql
   SELECT * FROM transactions
   WHERE merchant ILIKE '%JYSK%'
   AND date = '2026-04-03'
   AND payer = 'Maryna';
   ```

3. **Apps Script** — manual update required (from previous session):
   Task Log → Extensions → Apps Script → paste task_log_automation.js → Save → setupTriggers()

---

## SECTION 13: UNIFIED TASK SEEDS (TEST + PROD combined)

Ready to be written to Task Log. Ordered by severity.

```
──────────────────────────────────────────────────────────────────
CRIT priority
──────────────────────────────────────────────────────────────────

T-NEW | Fix float conversion for European number format
  Symptom: "could not convert string to float: '2,735.00'" crashes all report screens.
  Root cause: Python float('2,735.00') fails on comma-as-thousands-separator format.
  Files: Any place amounts are read from Sheets and converted — check reports.py,
         sheets.py (SheetsClient), analytics tool in agent.py.
  Fix: str.replace(',', '') before float(), or use locale-aware parser.
  Verify: Record a transaction with amount 2735.0, open report — no crash.

T-NEW | Fix XML/invoke code leaking into Telegram messages (PROD-ONLY)
  Symptom: Users see raw <invoke name="present_options">...</invoke> in chat.
  Root cause: Tool call output not intercepted before Telegram send.
  Files: agent.py (response handling), bot.py (send_message wrapper).
  Fix: Add output sanitization — strip any <invoke>...</invoke> or XML tags before send.
       Or fix the dispatch so tool calls never reach the text body.
  Verify: Trigger a flow that uses present_options — user sees choices, not XML.

T-NEW | Implement Sheets API read caching to prevent 429 quota errors (PROD-ONLY)
  Symptom: RESOURCEEXHAUSTED on ReadRequestsPerMinutePerUser during normal usage.
  Root cause: Too many Sheets reads per minute — quota is 60 reads/min/user.
  Files: sheets.py (SheetsClient), any place that calls read_config() or
         reads Dashboard/Transactions on every message.
  Fix: Cache Config/Dashboard data in memory for 60s. Only re-read if cache stale.
       Or batch: read once per operation, not once per tool call.
  Verify: Send 10 messages in 60s — no 429 errors.

──────────────────────────────────────────────────────────────────
HIGH priority
──────────────────────────────────────────────────────────────────

T-NEW | Fix tx_id lookup on delete — use stored ID, not reconstructed
  Symptom: "TX_2026_04_09_01 not found" / "2026-04-09income..." — both wrong.
  Root cause: Bot constructs tx_id string instead of using the actual ID from creation.
  Files: agent.py (delete_transaction tool), db.py or sheets.py (transaction store).
  Fix: At creation, return tx_id and store in session or conversation state.
       On delete, reference stored tx_id directly. Never reconstruct from fields.
  Verify: Add transaction, delete it by reference — succeeds first try.

T-NEW | Fix currency detection on bank statement processing (PROD-ONLY)
  Symptom: UAH bank statement transactions recorded in EUR instead of UAH.
  Root cause: Currency parser defaulting to EUR when currency symbol not explicitly matched.
  Files: intelligence.py (bank statement parsing), agent.py (record_transaction tool).
  Fix: Detect currency from statement header/amounts before recording.
       If ambiguous, ask user: "В какой валюте записать?" before confirming.
  Verify: Send UAH bank statement screenshot — entries recorded as UAH.

T-NEW | Fix incoming transfers vs expenses split in family account parsing (PROD-ONLY)
  Symptom: +400 EUR and +100 EUR incoming transfers added to expense total (500 EUR overcounting).
  Root cause: Parser sums all amounts regardless of debit/credit direction.
  Files: intelligence.py (family account / shared account parsing prompt).
  Fix: Detect transaction direction (+ = incoming, no sign or - = expense).
       Only sum expenses. Show transfers separately in confirmation screen.
  Verify: Send Wise family account screenshot with incoming transfers — transfers shown
          separately, not added to expense total.

T-NEW | Fix bot language switching to English without trigger (PROD-ONLY, worse than TEST)
  Symptom: Bot sends English message mid-Russian conversation with no language change command.
  Root cause: Fallback/error paths in agent.py or intelligence.py hardcoded in English,
              bypassing i18n entirely.
  Files: agent.py (all error handlers, duplicate detection messages), i18n.py.
  Fix: Every bot.send_message() call must pass text through i18n.t() with user's language.
       No hardcoded English strings in any response path.
  Verify: Set user language = RU, trigger duplicate detection — message in Russian.

T-NEW | Add retry logic for Nexi/receipt processing (confirmed both TEST + PROD)
  Symptom: "Что-то пошло не так. Попробуй ещё раз." on valid receipt photos.
  Root cause: Transient API timeout or upstream vision error — not a bad image.
  Files: intelligence.py (receipt processing), bot.py (error handler).
  Fix: Auto-retry up to 2x with exponential backoff before showing user error.
       Log actual error to Railway logs for debugging.
       Distinguish: retry-able (timeout) vs permanent (unsupported format).
  Verify: Mock a timeout in the vision API call — bot retries silently, user never sees error.

──────────────────────────────────────────────────────────────────
MED priority
──────────────────────────────────────────────────────────────────

T-NEW | Fix batch record_all — atomic completion with single summary
  Symptom: record_all adds 1, stops; then adds 4, stops; user asks "и остальные?" repeatedly.
  Root cause: Process exits on first duplicate, doesn't continue to remaining items.
  Files: agent.py (record_all or batch_add tool).
  Fix: Process all items in one pass. Collect results (success / skipped / failed).
       Return single summary: "Добавлено 5/6. Пропущено: Armonia Dentale (дубликат)."
  Verify: Batch record 6 transactions where 1 is duplicate — one response, correct count.

T-NEW | Fix session loop — track processed batches within a session (worse in PROD)
  Symptom: Same 6 transactions offered for recording 3+ times in one session.
  Root cause: No session-level state. Every photo triggers fresh parse.
  Files: agent.py (session state), db.py (or in-memory per chat_id).
  Fix: Store a "processed_sources" set per chat_id per session.
       If same image hash (or same date+merchant list) already processed this session,
       respond: "Эти транзакции уже были добавлены — Armonia, JYSK, ... в 10:45."
  Verify: Send same bank screenshot twice — second time bot says "already processed."

T-NEW | Standardize category names to user's language in all UI surfaces
  Symptom: Budget shows "Food", "Home", "Personal" (EN) mixed with "Здоровье" (RU).
  Root cause: Category names not passed through i18n — stored in EN internally, shown raw.
  Files: sheets.py (category read), agent.py (category display), i18n.py.
  Fix: All category display strings → i18n.t('category.food') etc. with 4-language support.
  Verify: Set language = RU — all categories show in Russian everywhere.

T-NEW | Verify and fix JYSK duplicate in PROD DB (2026-04-03, Maryna)
  Symptom: "Последние 10" shows two JYSK 133.45 EUR entries on same date with different categories.
  Root cause: JYSK was added once in first batch pass, possibly re-added in retry flow.
  Files: PROD DB (interchange.proxy.rlwy.net:19732), transaction table.
  Fix: Query DB (see Section 12 query), delete duplicate if exists.
       Add dedup check BEFORE inserting: same merchant + same amount + same date + same payer.
  Verify: "Последние 10" shows one JYSK entry for 2026-04-03.

T-NEW | Add plausibility check before mass recategorization
  Symptom: Bot proposes to set all 5 transactions to "Housing" including food and clothing.
  Root cause: Bot accepts user-provided category override for all items without checking.
  Files: agent.py (category assignment flow).
  Fix: If applying single category to batch with mixed inferred categories, warn:
       "Pam Panorama и Mercato обычно еда — точно записать как Housing?"
  Verify: Batch 5 transactions (mixed categories), try to force all to Housing —
          bot warns before accepting.

──────────────────────────────────────────────────────────────────
LOW priority
──────────────────────────────────────────────────────────────────

T-NEW | Improve file type rejection message specificity
  Symptom: "Тип файла не поддерживается." — too generic.
  Fix: "Это изображение не похоже на чек или выписку. Отправьте фото чека или скриншот
       банковской выписки."

T-NEW | Ask upfront: bulk or separate for multi-item bank statements
  Symptom: Family account with 5 items recorded as one bulk entry — user had to correct.
  Fix: When statement has 3+ items: "Записать как одну общую транзакцию или отдельно по каждой?"
```

---

*Analysis complete. 28 PROD pages reviewed. 10 PROD-only issues + 8 confirmed from TEST.*
*Cross-comparison: 1 fix (B-04), 7 regressions, 8 shared bugs.*
*Task seeds ready for Task Log — 15 tasks total.*
