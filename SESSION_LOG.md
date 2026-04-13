# Session Log — append only, never edit past entries
# Types: CHAT | ACTION | DECISION | PENDING | STATE | NEXT
# Format: YYYY-MM-DD HH:MM | TYPE | content
# Time: always run `date '+%Y-%m-%d %H:%M'` before writing an entry

2026-04-13 | ACTION | topic validation fix in add_task() — empty string raises ValueError; Bug Fix + Process removed from _FALLBACK_TOPICS
2026-04-13 | ACTION | Dashboard format reset in sheets.py — repeatCell+numberFormat clear via batch_update before writing; fixes % and date corruption after ws.clear()
2026-04-13 | DECISION | Config write must use write_config() with value_input_option='USER_ENTERED'; direct ws.update() creates text cells with ' prefix
2026-04-13 | DECISION | bot_version stays string '2.0' — written with text prefix in Sheets, not numeric
2026-04-13 | ACTION | ~20 obsolete files deleted; active docs: CLAUDE.md, CLAUDE_WORKING_GUIDE.md, SESSION_LOG.md, ApolioHome_Prompt.md, SELF_LEARNING_ALGORITHM.md
2026-04-13 | ACTION | CLAUDE.md rewritten in English — all operational rules live here; Project Instructions (Claude UI) is a pointer only
2026-04-13 | PENDING | Budget Config (prod) — monthly_cap and split_rule overwritten with test values (3500, 50/50); Mikhail edits manually in Sheets, then refresh Dashboard
2026-04-13 | PENDING | Apps Script — manual update: Task Log → Extensions → Apps Script → paste task_log_automation.js → Save → run setupTriggers()
2026-04-13 | STATE | sandbox init: load_dotenv('.env'), sys.path.insert(0, repo_root), from sheets import SheetsClient (NOT SheetManager)
2026-04-13 | CHAT | обсуждаем механизм памяти: пишем в SESSION_LOG после каждого ответа
2026-04-13 | DECISION | CLAUDE_SESSION.md избыточен — удалён; SESSION_LOG.md единственный файл памяти
2026-04-13 | ACTION | CLAUDE_SESSION.md deleted, SESSION_LOG.md updated with types CHAT/ACTION/DECISION/PENDING/STATE
2026-04-13 | ACTION | CLAUDE.md updated: "after every reply" rule moved into session start block; pushed dev 3497e2e
2026-04-13 | ACTION | Project Instructions (Claude UI) updated — DEV_CHECKLIST removed, SESSION_LOG read trigger + after-every-reply rule added
2026-04-13 14:48 | CHAT | исправлен формат записей: время обязательно; получать через date '+%Y-%m-%d %H:%M'
