# Session Log — append only, never edit past entries
# Types: CHAT | ACTION | DECISION | PENDING | STATE | NEXT
# Format: YYYY-MM-DD HH:MM | TYPE | content
# Time: always run `date '+%Y-%m-%d %H:%M'` before writing an entry
# ROTATED from: logs/SESSION_LOG_ARCHIVE_2026-04-13_23-12.md

2026-04-13 23:09 | STATE   | dev at 6502bc2. T-172–T-177 all DISCUSSION. 38/39 tests. Transaction 03824543 found in TEST (Housing/Rent/1365/Maryna — duplicate). Delete was failing due to session.language crash. Fixed in T-177.
2026-04-13 17:04 | DECISION| SESSION_LOG rotation threshold 16384 bytes; write new file FIRST then archive old (atomicity)
2026-04-13 17:07 | DECISION| SESSION_LOG читається перед кожним відповіддю — це навмисно (mid-session context compression)
2026-04-13 16:53 | DECISION| після кожної задачі перевіряти і видаляти temp файли до коміту
2026-04-13 17:00 | DECISION| Project Instructions: читати logs/ цілком — покриває будь-яку глибину ротацій
2026-04-13 | DECISION    | Config write must use write_config() with value_input_option='USER_ENTERED'
2026-04-13 | DECISION    | bot_version stays string '2.0' — written with text prefix in Sheets
2026-04-13 | DECISION    | CLAUDE_SESSION.md видалено; SESSION_LOG.md єдиний файл пам'яті
2026-04-13 22:58 | DECISION| T-173: account=Joint = shared bank pool, not personal money; only income (top_up) and Personal account expenses affect balance
2026-04-13 23:09 | DECISION| T-172/T-173/T-174 помилково CLOSED → повернуто DISCUSSION. Claude MUST NOT set CLOSED ever.
2026-04-13 21:49 | PENDING | 16 historical DEPLOYED-without-GO (T-024,T-028–T-030,T-033–T-035,T-037,T-039–T-042,T-044,T-046,T-069,T-150) — ждём решения Mikhail
2026-04-13 21:49 | PENDING | Push to main: ждём GO від Mikhail
2026-04-13 23:12 | ACTION  | CLAUDE_WORKING_GUIDE.md оновлено до v1.7: _sheets_retry, session.lang, compute_contribution_history data-driven, auto-sort, Dashboard [HISTORY] layout; Commit 25661c4
2026-04-13 23:12 | ACTION  | SESSION_LOG rotated → logs/SESSION_LOG_ARCHIVE_2026-04-13_23-12.md (16.5KB exceeded 16384 threshold)
2026-04-13 23:18 | ACTION  | TEST Transactions відсортовано по Date asc вручну (17 рядків); авто-сортування після add тепер активне (T-176)
2026-04-13 23:18 | ACTION  | TEST Dashboard оновлено: [HISTORY] 2026-03 + 2026-04 + TOTAL, обидва юзери (T-175); дублікат 03824543 (Maryna exp_joint=2027) все ще є в TEST
2026-04-13 23:18 | STATE   | dev at f5db016. Staging повинен бути актуальним. Pending GO від Mikhail для push main.
2026-04-13 23:23 | ACTION  | T-178 DISCUSSION: T-168 split-choice не спрацьовував для банківських виписок — merchant="Bank Statement Ukraine" не проходив умову "multiple"/"merchants"; виправлено на len(items)>=3; Commit d29ab72
2026-04-13 23:32 | ACTION  | T-178 fixed: smart bank stmt detection — len>=2 + per-item merchant/date diff. Restaurant receipts false-positive free. Commit 125eb5e
2026-04-13 23:32 | ACTION  | T-179 done: РОЗРАХУНКИ header, per-user min pool per block, no Зобов'язання, consistent Переплата/Борг/Баланс. i18n.py+intelligence.py+bot.py. Commit 125eb5e
2026-04-13 23:32 | ACTION  | T-178+T-179 Task Log → DISCUSSION, Deploy=READY
2026-04-13 23:32 | STATE   | dev at 125eb5e. T-172–T-179 all DISCUSSION+READY. Waiting GO from Mikhail for main push.
2026-04-13 23:41 | DECISION| T-178: no heuristic — always show items list for len>=2 + two buttons. User sees context, decides themselves.
2026-04-13 23:41 | ACTION  | T-178 reworked: items preview (merchant/amount/date) + split/single choice. Commit ac4cdf4, pushed dev.
2026-04-13 23:50 | ACTION  | T-180: skip category+subcategory validation for income txs; strip AI-set subcategory="Top-up". tools/transactions.py. Commit b92e5f9.
2026-04-13 23:50 | STATE   | dev at b92e5f9. T-172–T-180 all DISCUSSION+READY. Waiting GO from Mikhail.
2026-04-13 23:55 | ACTION  | T-181: echo account+split choices fixed; amount field total_amount added to lookup (was causing 4/7). Commit 3524255.
2026-04-13 23:55 | STATE   | dev at 3524255. T-172–T-181 DISCUSSION+READY. Waiting GO від Mikhail.
2026-04-14 00:05 | ACTION  | T-182: dup detection — currency match + ±5% non-EUR + note token check. tools/transactions.py. Commit d78f2ca.
2026-04-14 00:05 | STATE   | dev at d78f2ca. T-172–T-182 DISCUSSION+READY. Waiting GO.
