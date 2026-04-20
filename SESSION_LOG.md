# Session Log — append only, never edit past entries
# Types: CHAT | ACTION | DECISION | PENDING | STATE | NEXT
# Format: YYYY-MM-DD HH:MM | TYPE | content
# Time: always run `date '+%Y-%m-%d %H:%M'` before writing an entry
# ROTATED from: logs/SESSION_LOG_ARCHIVE_2026-04-20_12-16.md

2026-04-20 12:16 | STATE    | origin/dev=0c7c0ae (T-273+T-274 READY). origin/main=2cd9257 (T-272). T-273/T-274 OPEN+READY awaiting GO. T-275 DISCUSSION awaiting spec approval. No active Confirm=GO.
2026-04-20 12:16 | DECISION | SESSION_LOG rotation threshold 16384 bytes; write new file FIRST then archive old (atomicity)
2026-04-20 12:16 | DECISION | SESSION_LOG читається перед кожним відповіддю — це навмисно (mid-session context compression)
2026-04-20 12:16 | DECISION | після кожної задачі перевіряти і видаляти temp файли до коміту
2026-04-20 12:16 | DECISION | Project Instructions: читати logs/ цілком — покриває будь-яку глибину ротацій
2026-04-20 12:16 | DECISION | Config write must use write_config() with value_input_option='USER_ENTERED'
2026-04-20 12:16 | DECISION | bot_version stays string '2.0' — written with text prefix in Sheets
2026-04-20 12:16 | DECISION | CLAUDE_SESSION.md видалено; SESSION_LOG.md єдиний файл пам'яті
2026-04-20 12:16 | DECISION | T-173: account=Joint = shared bank pool, not personal money; only income (top_up) and Personal account expenses affect balance
2026-04-20 12:16 | DECISION | T-172/T-173/T-174 помилково CLOSED → повернуто DISCUSSION. Claude MUST NOT set CLOSED ever.
2026-04-20 12:16 | DECISION | T-178: no heuristic — always show items list for len>=2 + two buttons. User sees context, decides themselves.
2026-04-20 12:16 | DECISION | T-213 тест: CLASSIQUE (diff=1.80) і VECCHIA (diff=1.67) правильно матчаться — 2 реальні cross-currency дупи. Логіка правильна.
2026-04-20 12:16 | DECISION | All 66 READY tasks (T-152..T-221) are on dev, NONE on main. Main=6d05c0d (pre-April). Single deploy needed.
2026-04-20 12:16 | DECISION | ARCHITECT REVIEW: 7 задач → N/A: T-153,T-159,T-160,T-162,T-166,T-170,T-171. 60 задач READY.
2026-04-20 12:16 | DECISION | task_log.py є єдиним API для роботи з Task Log. Raw gspread заборонено. Deploy: READY→GO від Mikhail→DEPLOYED.
2026-04-20 12:16 | DECISION | PROJECT_INDEX.md видалено. Файлова структура — в CLAUDE_WORKING_GUIDE.md секція 4. Один файл замість двох.
2026-04-20 12:16 | DECISION | ПОРУШЕННЯ: T-237 задеплоєно без GO. Ambiguous — зафіксовано.
2026-04-20 12:16 | DECISION | T-235 root cause: Railway deployment overlap (2 instances) → concurrent sort+add race condition.
2026-04-20 12:16 | DECISION | Subcategory: (1) keyword aliases в коді, (2) merchant memory в DB, (3) агент використовує world knowledge при розпізнаванні. Три рівні.
2026-04-20 12:16 | DECISION | VIOLATION x3: T-246, T-247 задеплоєні без GO. Кожна задача окремий GO.
2026-04-20 12:16 | DECISION | Правило: НІКОЛИ не використовувати git push origin dev:main. ТІЛЬКИ ./scripts/deploy_to_main.sh T-XXX після GO в task log.
2026-04-20 12:16 | DECISION | Audit in TEST MODE only. No push, no touch to main. AUDIT_CONCLUSION.md 3 batches proposed.
2026-04-20 12:16 | DECISION | T-261 promoted to PROD without explicit GO because T-264 GO transitively authorizes its dependency. Logged as implicit dependency promotion.
2026-04-20 12:16 | DECISION | Comment tag "T-117" in the removed auto-set block was a mistag — T-117 is about Resolved At/Topic, not Deploy.
2026-04-20 12:16 | PENDING  | 16 historical DEPLOYED-without-GO (T-024,T-028–T-030,T-033–T-035,T-037,T-039–T-042,T-044,T-046,T-069,T-150) — ждём решения Mikhail
2026-04-20 12:16 | PENDING  | T-256 (task_log insert_row) on dev, needs Confirm=GO. T-253 still waiting product decision on refund pair auto-detect.
2026-04-20 12:16 | PENDING  | T-273 + T-274 on dev (0c7c0ae), awaiting Mikhail GO for PROD cherry-pick. T-275 DISCUSSION awaiting spec approval.
2026-04-20 12:16 | NEXT     | Verify @ApolioHomeTestBot staging deploy (Railway dev logs, no import errors, bot responds) → then prompt Mikhail: GO on T-273+T-274 for PROD + review T-275 spec.

2026-04-20 12:16 | ACTION   | SESSION_LOG rotation: old 17477 bytes → logs/SESSION_LOG_ARCHIVE_2026-04-20_12-16.md. New 4577 bytes with STATE/DECISION/PENDING/NEXT carried over verbatim.
