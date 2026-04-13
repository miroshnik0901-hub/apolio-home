# Apolio Home — TEST Agent Analysis
**Source:** TEST.pdf (46 pages, @ApolioHomeTestBot)
**Test period:** April 1–11, 2026 (screenshots from test session)
**Purpose:** Detailed QA breakdown. To be compared with PROD agent behavior.
**Status:** TEST only — PROD comparison pending

---

## ANALYSIS FRAMEWORK

Each observation is tagged:
- `[BUG]` — incorrect behavior, crash, wrong output
- `[UX]` — awkward flow, confusing message, missing confirmation
- `[DATA]` — wrong data stored or displayed
- `[LANG]` — language inconsistency
- `[OK]` — behavior correct and clean
- `[NOTE]` — neutral observation, may become task depending on PROD comparison

Severity: `CRIT` / `HIGH` / `MED` / `LOW`

---

## SECTION 1: RECEIPT PARSING (Photos & Forwarded Receipts)

### 1.1 Mercato Chieri — 34.20 EUR (Apr 1)
**Source:** Forwarded photo from Mikhail Miro
**Receipt:** DIMAR S.P.A., Via Buschetti 4 Chieri (TO)

`[OK]` Merchant name, address, total amount parsed correctly.
`[OK]` Payment type (безналичная) parsed correctly.
`[OK]` НДС 2.58€ parsed correctly.
`[NOTE]` Receipt said "9 позиций" but bot listed only 7 items:
  - Оливковое масло экстра — 9.99€
  - Копчёный лосось ICER — 4.70€
  - Батончики злаковые ПИУ 2x — 1.95€
  - Хлеб LIZZI — 1.05€
  - Батончики KELLOGG 2x — 2.49€
  - Мёд PIEMONTE — 6.59€
  - Салат CAS.CAPP — 2.99€
  → **2 items missing from the parsed list.** Sum of 7 items = 29.76€, receipt total = 34.20€. Delta = 4.44€ unaccounted.
  → **[BUG][MED]** Parser drops some line items. Needs verification whether items are parsed but not displayed, or genuinely lost.

`[OK]` Duplicate detection worked — found existing "Food · Mikhail · Mercato Chieri · 34.20€".
`[OK]` Offered to enrich existing or add new — correct flow.

---

### 1.2 La Cantina del Convento — 93 EUR (Apr 1)
**Source:** Direct photo
**Receipt:** Via Broglia 13, Chieri (TO), 01 aprile 2026 21:59, безналичная

`[OK]` Merchant, address, date, total parsed correctly.
`[OK]` All 9 order items parsed with correct amounts:
  - Guancia Brasata (тушёная щека) — 14€
  - Quater Nostro — 15€
  - Fra Pantagruelle — 16€
  - Hamburger + картошка — 14€
  - B. Arneis (вино) — 7€
  - Coca Zero — 5€
  - Газированная вода большая 2 бут — 5€
  - Coeur Colant Fondente (шоколадный фондан) — 8€
  - Сервисный сбор 3 персоны — 9€
`[OK]` НДС 8.45€ parsed.
`[OK]` Asked "С какого счёта записать?" with buttons Общий/Личный/Изменить/Отменить — correct flow.
`[OK]` Duplicate detection found existing transaction, offered enrich.

**Observation:** After processing both receipts, bot performed `enrich_existing` on TWO transactions simultaneously — Mercato (34.20€) and La Cantina (93€). This is correct behavior if both were pending enrichment.

---

### 1.3 Classique Cafe Restaurant — 122 EUR (Apr 10)
**Source:** Direct restaurant receipt photo

`[OK]` Full itemized dinner for 3 parsed (10 positions):
  - Coperto 3x — 10.50€
  - Tris di Sarde (sardины) — 16.50€
  - Polpo Griglia (осьминог гриль) — 22.50€
  - Tonno Scottato (тунец) — 24€
  - Tortino Cioccolato Fondente — 8€
  - Sant'Honore (торт) — 6.50€
  - 1/2 Bianco (вино) — 10€
  - Вода 0.7л — 4€
  - Coca-cola Zero — 4€
  - Gorgonzola + орехи + груши — 14€
`[OK]` НДС 11€, оплата Bancomat (Visa contactless) parsed.
`[OK]` Found matching transaction in budget, offered to enrich.
`[OK]` After enrichment: note=Classique Cafe Restaurant, category=Food, subcategory=Restaurants, who=Mikhail

---

### 1.4 Classique Cafe — UC Visa Payment Slip (Apr 10)
**Source:** UC Visa contactless payment slip photo (different from Nexi)

`[OK]` UC Visa slip correctly identified (different from Nexi format).
`[OK]` Merchant: RISTORANTE CLASSIQUE, Via Albarello 33, Lazise (VR).
`[OK]` Date 10/04/26 at 21:32, amount 122.00 EUR, status TRANSAZIONE ESEGUITA.
`[OK]` Card: Visa Contactless, correct merchant code extracted.
`[OK]` "Additional payment slip found for the same dinner" — correctly linked to existing transaction.
`[OK]` Enriched with Visa contactless details, card ending 3297, authorization 020208, terminal data, UniCredit processing info.
`[NOTE]` Two slips for same transaction (restaurant VAT receipt + payment slip) — bot handled correctly, enriched once.

---

### 1.5 Vecchia Dogana — Restaurant VAT Receipt (Apr 9)
**Source:** Direct photo of official VAT receipt

`[OK]` Full parse:
  - VECCHIA DOGANA di Limonhaya srl, Piazzetta A. Partenio 10-12, 37017 Lazise (VR)
  - P.Iva 05085760238, Doc N. 1937-0053, Crin 8, Officiant BEATRICE
  - Date: 09-04-2026 o 22:07
`[OK]` 8 itemized positions:
  - COPERTO 2x3.50€ — 7€
  - GEDECK C** — 20€
  - TENT.POLPO PAT.DOLCI (осьминог с сладким картофелем) 2x14€ — 28€
  - GUAZZETTO PESCE (рыбное рагу) — 22€
  - FILETTO OMBRINA (филе умбрины) — 7€
  - VERDURE GRIGLIA (овощи гриль) — 24€
  - CUSTOZA CAVALCHINA (вино) — 5€
  - ACQUA NATURALE (вода) — 5€
`[OK]` Total 113€, НДС 10.27€, BANCOMAT CC payment.
`[OK]` Found existing transaction, offered to enrich.

---

### 1.6 Vecchia Dogana — Nexi Payment Slip (Apr 9)
**Source:** Nexi terminal slip photo (multiple attempts)

`[BUG][HIGH]` **Intermittent "Something went wrong / Что-то пошло не так"**
  - Same Nexi slip sent 3-4 times across different attempts
  - First 1-2 attempts: generic error, no details
  - Last attempt: parsed correctly
  - Pattern: NOT related to image quality (same image fails then succeeds)
  - Likely: API timeout or upstream error in vision/processing pipeline
  - No error details shown to user — just generic retry message
  - **Needs:** retry logic, error logging, distinguish transient vs permanent errors

`[OK]` When finally parsed:
  - Nexi, VISA DEVICE ACQUISTO (Visa Card Purchase)
  - Merchant: RISTORANTE VECCHIA DOGAN, Lazise
  - Date: 09/04/26 at 22:07, Amount: 113.00 EUR
  - Card: Visa Credit ••••3297, Bank: Banca Popolare di Sondrio
  - Terminal: TML 85072463, Auth: AUT.920207, STAN: 001101
  - OPER. 001155, Eserc. 100000154194, A.I.C.: 00000000034
`[OK]` Found matching transaction in budget, offered to enrich.
`[OK]` Categorized: Food / Restaurants / Mikhail.

`[NOTE]` Nexi slips are consistently harder to parse than restaurant VAT receipts — smaller print, thermal paper, worse contrast in photos.

---

## SECTION 2: BANK STATEMENT PROCESSING

### 2.1 Ukrainian Bank Statement (Apr 7–9)
**Source:** Forwarded screenshot from Mikhail Miro showing family account transactions

`[OK]` Bot correctly identified 7 transactions totaling 26,568₴ = 665 EUR (by exchange rate):
  - 9 APRIL (вчера): RISTORANTE CLASSIQUE — 6,252₴, RISTORANTE VECCHIA DOGAN — 5,791₴, BAR RIVIERA — 1,971₴
  - 8 APRIL: GEORGE FISH & CHIPS — 1,584₴, FRANTOIO VERONESI S.R.L. — 4,863₴, GIPS BAR — 768₴
  - 7 APRIL: ESSO ЗАПРАВКА БАРДОЛИНО — 4,139₴ (топливо)
`[OK]` Bot correctly noted some transactions already exist in EUR in budget.
`[OK]` Asked "Записать все 7 операций? С какого счёта оплачивались?" — correct question.
`[OK]` User said "Оплатив особисто" → recorded as Food · 26568.0 UAH · Mikhail · 2026-03-31 · Multiple restaurants · Bank statement.

`[BUG][HIGH]` **DELETION FAILED — tx_id mismatch**
  After processing the UAH statement, when trying to delete the bulk UAH entry and replace with individual EUR transactions:
  - Attempt 1: `TX_2026_04_09_01` not found in any envelope (TEST_BUDGET)
  - Attempt 2: `2026-04-09income526.10ukrainian-banks-transactions` not found in any envelope (TESTBUDGET)
  - Both attempts: Row was NOT removed
  - **Root cause:** Bot is guessing tx_id formats. The actual tx_id assigned during creation (e.g., `d21f2f36`) differs from what bot constructs when trying to delete.
  - **Impact:** Duplicate data — bulk UAH entry stays + individual EUR entries added. Data integrity issue.
  - **Fix needed:** Delete should use the actual tx_id returned at creation time, not reconstruct it.

`[NOTE]` Envelope name inconsistency in errors: `TEST_BUDGET` vs `TESTBUDGET` — two different spellings appear in error messages. May indicate bot is also confused about envelope name format.

---

### 2.2 Family Account Statement — March 31
**Source:** Screenshot of family account app (Mikhail forwarded)

`[OK]` Bot identified 5 operations from family account:
  - Gardaland — 208 EUR (Mikhail) → Развлечения
  - Capitolo Emanuele — 1,365 EUR (Maryna) → Жильё/Аренда
  - International School Of — 662 EUR (Maryna) → Образование
  - From EUR — +400 EUR (Mikhail) → Пополнение
  - От Maryna — +100 EUR (Maryna) → Пополнение
`[OK]` Correctly showed total: 1,835 EUR expenses, 500 EUR пополнения, net 1,335 EUR.
`[OK]` Asked which account — user said "Вніс на joint".
`[DATA]` Bot recorded as single line: `2735.0 EUR · Mikhail · 2026-03-31 · Family account transactions` — **all 5 operations as one transaction instead of 5 separate.**
`[UX]` User immediately said "Это как отдельные транзакции должно быть" → bot corrected and broke into 5 separate transactions. Correct recovery, but should have asked upfront.

`[BUG][CRIT]` **`could not convert string to float: '2,735.00'`**
  - The bulk entry `2,735.00` (2735 EUR with comma as thousands separator) crashes report loading.
  - Appears in weekly/monthly stats screen: "Не вдалося завантажити звіт: could not convert string to float: '2,735.00'"
  - Reproduces every time stats are opened after this entry exists.
  - **Root cause:** European/Italian number format uses comma as thousands separator. `float('2,735.00')` fails in Python.
  - **Fix:** Normalize before `float()` conversion: `value.replace(',', '')` or use locale-aware parsing.
  - **Affects:** Any stat/report that touches this transaction's amount field.

---

## SECTION 3: MARYNA PURCHASES — APRIL 3 BATCH

### 3.1 Initial processing
**Source:** Screenshot of banking app showing 6 purchases

`[OK]` Bot correctly identified 6 purchases totaling 481.47 EUR:
  1. Armonia Dentale — 132€ (Health/Dental)
  2. Mix Markt — 19.10€ (Food/Groceries)
  3. Mercato — 31.37€ (Food/Groceries)
  4. JYSK — 133.45€ (Home/Furniture)
  5. Pam Panorama — 146.11€ (Food/Groceries)
  6. Cm Moda — 19.44€ (Personal/Clothing)

`[BUG][MED]` **"ЗАПИСАНО 4 з 6 ТРАНЗАКЦІЙ"** on first record_all attempt.
  - Bot recorded 4 of 6, left Pam Panorama and Cm Moda unrecorded.
  - Message: "Успішно додав витрати Марини від 3 квітня: стоматологія (132€), продукти Mix Markt (19.1€) та Mercato (31.37€), меблі JYSK (133.45€). Залишилось записати ще 2 витрати: Pam Panorama та Cm Moda."
  - Required second `record_all` call to complete.
  - **Expected:** All 6 in single operation or clear explanation why 2 were skipped.
  - No error shown for the 2 skipped items — silent partial completion.

### 3.2 Duplicate detection in Maryna batch
`[BUG][MED]` **Duplicates created for Mix Markt and Mercato**
  - Bot initially recorded Mix Markt 19.10€ and Mercato 31.37€ twice (rows 10-11 and 13-14).
  - Bot detected this after the fact: "ПРОБЛЕМА: Есть дубли Mix Markt и Mercato (строки 10-11 и 13-14). ИТОГО ЗАПИСАНО: 266,39€ вместо 481,47€"
  - Bot self-identified and proposed fix: delete rows 10-11, add Pam Panorama + Cm Moda.
  - **Root cause:** Record operation ran twice or partial completion + retry created duplicates.
  - **UX:** Bot handled recovery well, but the duplication should not occur.

`[OK]` Delete + re-add flow worked correctly after user confirmation.
`[OK]` Final result matched screenshot: 481.47€ exactly.

---

## SECTION 4: BUDGET & FINANCIAL DISPLAY

### 4.1 Budget widget
`[OK]` Budget · Квітень 2026 · Test Budget shown correctly:
  - Progress bar (filled squares + empty)
  - X/3,500 EUR (percentage)
  - Remaining + days left
  - Pace (EUR/день → прогноз EUR)
  - Mikhail / Maryna contribution split

`[NOTE]` Progress bar uses emoji squares. Looks clean. No issues observed.

### 4.2 Contributions (Внески) widget
`[OK]` Shows per-person breakdown:
  - Вніс на joint / Оплатив особисто / Зобов'язання / Борг
`[BUG][CRIT]` (see 3.2 above) Float conversion crashes this screen when '2,735.00' value exists.

### 4.3 Balance display
`[OK]` After each transaction: показывает total spent, Mikhail owes, Maryna balance.
`[NOTE]` Balance evolution during session:
  - Start: 415€ spent, Mikhail -1,885€ owes
  - After Vecchia Dogana: 528€
  - After Classique + more: 537€ → 650€ → 967€ → 1,131€

### 4.4 Analytics widget
`[OK]` Total expenses, category breakdown (pie bar), balance (contributed − share per person).
`[NOTE]` "Knowledge base — No data yet" appeared in one analytics view. Unclear what this section is supposed to show.

---

## SECTION 5: TRANSACTION MANAGEMENT

### 5.1 Delete last transaction
`[OK]` "Удали последнюю запись" / "Delete last transaction" — found correct transaction, showed confirmation.
`[OK]` Confirmed → deleted, balance updated immediately.
`[OK]` Used in multiple test cycles without issue.

### 5.2 Confirm delete flow
`[OK]` "Это действие нельзя отменить. Подтвердить удаление?" — warning shown before irreversible action.
`[OK]` Yes/No buttons shown.

### 5.3 Batch delete + add
`[OK]` Complex flow: preview → confirm → delete duplicates → add missing → show final state.
`[OK]` Bot maintains plan state across multiple confirmation steps.
`[NOTE]` After successful delete of d21f2f36, bot later tried to delete same entity again with different tx_id format (TX_2026_04_09_01). Suggests **state loss between conversation turns** — bot re-analyzes instead of remembering what was already done.

---

## SECTION 6: LANGUAGE & LOCALIZATION

### 6.1 Language switching
`[OK]` Language changed to Ukrainian — bot confirmed "Мова змінена на українську."
`[OK]` Main messages appeared in Ukrainian after switch.

`[BUG][MED]` **System/error messages stay in English after language switch**
  - "Something went wrong. Please try again." — English, even when bot language set to Ukrainian.
  - "This action cannot be undone. Confirm deletion?" — English.
  - Generic error handler does not apply user language setting.
  - **Fix:** Error messages and system prompts must go through i18n.

### 6.2 Mixed language responses
`[NOTE]` Within the same session, responses appear in RU, UK, and EN without clear trigger.
  - User writes in RU → bot sometimes responds in UK
  - This may be intentional (bot mirrors user input language) but appears inconsistent.

---

## SECTION 7: FILE TYPE HANDLING

### 7.1 Non-receipt image
`[OK]` Easter greeting sticker/image (Promodo branding) sent to bot.
`[OK]` "Тип файла не поддерживается." — correct rejection.
`[UX][LOW]` Message could be more specific: "Це зображення не схоже на чек. Надішліть фото чека або слипу." Current message is too generic.

---

## SECTION 8: WELCOME / ONBOARDING

`[NOTE]` `/start` command triggered multiple times during session (bot restarted or context reset).
`[OK]` Welcome message shown in correct language (adapts to EN/UK based on last language set).
`[OK]` Examples shown: «кава 3.50» / «продукти 85 EUR Esselunga» / «покажи звіт за березень».
`[NOTE]` After `/start`, bot loses any pending context (e.g., was mid-receipt processing → session lost). This is expected behavior for `/start` but worth noting for UX.

---

## SECTION 9: MULTI-STEP WORKFLOW OBSERVATIONS

### 9.1 Plan → Confirm → Execute pattern
`[OK]` Bot consistently shows plan before destructive operations:
  ```
  ПЛАН ДІЙСТВ:
  1. ❌ Удалить дубли (жду подтверждения)
  2. + Добавить недостающие Pam Panorama + Cm Moda
  3. ✅ Всё готово
  ```
`[OK]` Waits for confirmation before proceeding.
`[OK]` Shows final state after completion.

### 9.2 Context retention across turns
`[BUG][MED]` **Bot re-analyzes already-processed data on follow-up question**
  - After deleting d21f2f36 (UAH duplicate) and user asks "Добавил транзакции?", bot says "НЕТ, ЕЩЁ НЕ ДОБАВИЛ" and tries to delete the same entry again with wrong tx_id.
  - Bot should remember: "deletion already completed, next step is adding EUR transactions."
  - **Root cause:** No persistent state between conversation turns — bot re-derives state from DB query each time, but uses wrong tx_id format.

---

## SECTION 10: SUMMARY — BUG CATALOG

| # | Type | Severity | Description | Reproduction |
|---|---|---|---|---|
| B-01 | BUG | CRIT | `float('2,735.00')` crashes report/stats | Record any transaction with amount formatted as X,XXX.XX |
| B-02 | BUG | HIGH | DELETION FAILED — bot constructs wrong tx_id | Delete bulk UAH entry after bank statement processing |
| B-03 | BUG | HIGH | Nexi slip: intermittent "something went wrong" | Send Nexi thermal slip photo (especially low contrast) |
| B-04 | BUG | MED | 2 items missing in Mercato receipt parse (9 listed, 7 shown) | Send Mercato receipt with 9+ line items |
| B-05 | BUG | MED | record_all records 4/6, silently skips 2 | Batch record 6+ transactions in one operation |
| B-06 | BUG | MED | Duplicate transactions created on batch record + retry | Partial completion → user retries → duplicates |
| B-07 | BUG | MED | System/error messages stay in English after language switch | Set language to UK/RU, trigger error condition |
| B-08 | BUG | MED | Context state lost between turns — bot re-derives state | Complete multi-step operation, ask follow-up question |
| B-09 | UX | LOW | File type error message too generic | Send non-receipt image |
| B-10 | UX | LOW | Family account: bot should ask "separate or bulk?" upfront | Forward family account statement screenshot |

---

## SECTION 11: WHAT WORKS WELL (for PROD comparison baseline)

These features worked consistently in TEST — any deviation in PROD is a regression:

1. Restaurant VAT receipt parsing (Classique, Vecchia Dogana, La Cantina) — full itemized parse
2. Nexi slip parsing when successful — complete card/terminal data extraction
3. UC Visa slip parsing — correctly identified as different format from Nexi
4. Duplicate detection — both receipt+existing and slip+existing patterns
5. Enrich existing transaction flow — single click, immediate confirmation
6. Delete last transaction — confirmed, immediate, balance updated
7. Budget / Contributions / Analytics widgets — correct numbers
8. Multi-step plan → confirm → execute pattern
9. Language switching itself (mova changed OK)
10. Batch bank statement processing (UAH → EUR conversion with correct rate)
11. Complex multi-transaction recovery (delete duplicates + add missing in one flow)

---

## SECTION 12: OPEN QUESTIONS FOR PROD COMPARISON

These are areas where TEST and PROD **might** behave differently — to verify:

1. Do Nexi slips fail intermittently in PROD too, or is this TEST-specific?
2. Does PROD also crash on float('2,735.00')? (Same codebase should reproduce)
3. Does PROD use same tx_id generation? (Same deletion bug should exist)
4. Does PROD handle language switching correctly for error messages?
5. Does PROD record_all complete all items in one pass?
6. Are there features present in PROD that don't appear in TEST (version drift)?
7. Does PROD show any different categorization behavior for same receipts?
8. Does PROD handle `/start` context reset the same way?

---

## SECTION 13: TASK SEEDS (to be formalized after PROD comparison)

```
T-XXX | Fix float conversion for European number format (2,735.00 → 2735.00)
       Files: reports.py or wherever budget/stats amounts are processed
       Fix: str.replace(',', '') before float() or locale-aware parsing

T-XXX | Fix tx_id lookup on delete — use actual stored ID, not reconstructed
       Files: agent.py (delete_transaction tool), sheets.py
       Fix: Store and retrieve tx_id from DB/Sheets, don't reconstruct

T-XXX | Add retry logic for Nexi slip processing with error classification
       Files: intelligence.py (receipt processing), bot.py (error handler)
       Fix: Distinguish transient (retry) vs permanent (user message) errors

T-XXX | Fix record_all to complete all items or explain why items skipped
       Files: agent.py (record_all or batch_add tool)
       Fix: Run in chunks, log each result, report failures explicitly

T-XXX | Apply i18n to system/error messages
       Files: bot.py (error handlers), i18n.py
       Fix: All hardcoded English error strings → i18n.t() with all 4 languages

T-XXX | Persist operation state across conversation turns
       Files: agent.py, db.py (session state)
       Fix: Store completed steps in session, check before re-deriving

T-XXX | Ask upfront: bulk entry or separate transactions for multi-item statements
       Files: agent.py (bank statement processing tool)
       Fix: When processing statement with 2+ items, always ask preference
```

---

*Analysis complete. Awaiting PROD PDF for cross-comparison and task formalization.*
