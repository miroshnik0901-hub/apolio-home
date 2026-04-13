# CLAUDE_SESSION.md — Live Work Context

> **Read this first at the start of every chat.**
> Update immediately after every significant action — not "at end of session",
> but after every deploy, data change, key decision, or unfinished task.
> Written for the next Claude with zero chat context.

---

## Last Updated

**Date:** 2026-04-13
**What happened:** Project cleanup, T-150 fixes, Sheets formatting fixes, documentation restructure

---

## Current State

| | |
|---|---|
| Prod bot | @ApolioHomeBot — running |
| Staging bot | @ApolioHomeTestBot — running |
| Branches | `main` = `dev` = `541062d` |
| Active tasks | 0 |
| Prod Sheets | Synced with test |

---

## In Progress

*Nothing. All work completed.*

If anything is written here — it is the top priority for the next chat.
Format:
```
**[T-NNN] Task name**
Done: ...
Remaining: concrete next step
Files: bot.py:line, sheets.py:function
Stopped because: ...
```

---

## Pending — Mikhail's decision

1. **Budget Config (prod)** — `monthly_cap` and `split_rule` were overwritten with test values (3500, 50_50). Mikhail edits manually. After edit, refresh Dashboard:
   ```python
   sc.update_dashboard_sheet(file_id, snap, contrib_snap, contrib_history)
   ```

2. **Apps Script** — manual update required: Task Log → Extensions → Apps Script → paste `apps_script/task_log_automation.js` → Save → run `setupTriggers()`. Change: Resolved At format is now `yyyy-mm-dd hh:mm`.

---

## Recent Changes (last session — 2026-04-13)

| What changed | File | Detail |
|---|---|---|
| Topic validation fix | `task_log.py` | `add_task()`: empty string now raises ValueError. `_FALLBACK_TOPICS` has 6 items (Bug Fix and Process removed) |
| Dashboard format reset | `sheets.py` | `update_dashboard()`: added `repeatCell` + empty `numberFormat` via `batch_update` before writing — fixes % and date format corruption after `ws.clear()` |
| Config write method | `sheets.py` | Must use `write_config()` with `value_input_option='USER_ENTERED'` — direct `ws.update()` creates text cells with `'` prefix |
| `bot_version` type | Config sheet | Must stay as string `'2.0'` — written with `'` text prefix in Sheets, not numeric |
| Docs cleanup | project root | ~20 files deleted. Active docs: CLAUDE.md, CLAUDE_WORKING_GUIDE.md, CLAUDE_SESSION.md, ApolioHome_Prompt.md, SELF_LEARNING_ALGORITHM.md |
| CLAUDE.md | project root | Fully rewritten in English. All operational rules are here now |
| CLAUDE_SESSION.md | project root | New file (this file). Replaces scattered context files |
| Project Instructions (Claude UI) | — | Now a lean pointer only — CLAUDE.md is authoritative |

---

## Sandbox Initialization (Cowork / local work)

Repo is mounted at: `/sessions/.../mnt/apolio-home`
`.env` is at: `/sessions/.../mnt/apolio-home/.env`

To work with project code from sandbox:
```python
import sys, os
from dotenv import load_dotenv
load_dotenv('/sessions/gallant-relaxed-lamport/mnt/apolio-home/.env')
sys.path.insert(0, '/sessions/gallant-relaxed-lamport/mnt/apolio-home')
from task_log import TaskLog
from sheets import SheetsClient  # NOT SheetManager — that name doesn't exist
```

Git remote needs token (stored in `.git/config` remote URL). To push:
```bash
cd /sessions/gallant-relaxed-lamport/mnt/apolio-home
git push origin dev   # staging — no confirmation needed
git push origin main  # production — needs Mikhail's GO
```

---

## Key Technical Decisions

- **`value_input_option='USER_ENTERED'`** when writing to Sheets — otherwise numbers are stored as strings with `'` prefix. Happens when writing Config via `ws.update()` directly instead of `write_config()`.

- **Dashboard formatting reset** — `ws.clear()` does not clear cell formats. Need `repeatCell` with empty `numberFormat` via `batch_update` before writing. Without this, old formats (date, %) corrupt formula results.

- **Topic values** — 6 only: Interface, Features, Data, Infrastructure, AI, Docs. Bug Fix and Process removed from config sheet and from fallback in code.

- **CLAUDE.md** — single source of truth for operational rules. Project Instructions in Claude UI — pointer only.

---

## Not Yet Implemented (spec exists)

- **`SELF_LEARNING_ALGORITHM.md`** — agent self-learning spec. Not implemented. File is in project folder.

---

## File Map (quick reference)

| File | Purpose |
|------|---------|
| `CLAUDE_SESSION.md` | This file. Current context, in-progress work, decisions |
| `CLAUDE.md` | Operational rules: deploy, git, tests, languages, comment rules |
| `CLAUDE_WORKING_GUIDE.md` | Architecture, schemas, agent tools, Task Log API |
| `ApolioHome_Prompt.md` | Bot system prompt |
| `SELF_LEARNING_ALGORITHM.md` | Self-learning spec — needs implementation |
