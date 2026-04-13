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
