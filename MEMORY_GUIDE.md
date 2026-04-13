# Claude Cowork Memory — How It Works & How to Set It Up

Written by Claude based on direct experience in the Apolio Home project.
For use in any Claude Cowork project.

---

## The core problem

Claude has no persistent memory between sessions. Each new chat starts blank.
Within a session, context fills up and gets compressed — mid-task state is lost.
Claude doesn't know when its context window will end. It could be after this message.

---

## What doesn't work

- Relying on Claude to "remember" from the previous chat — it can't.
- Updating a state file only at "end of session" — there is no reliable end.
- Writing memory only after code actions — conversational decisions get lost too.
- Keeping memory in a structured file that requires editing — too much friction, Claude skips it.

---

## What works

**Two components, each doing one job:**

### 1. Project Instructions (Claude UI) — the trigger
This is the system prompt. It's read before every single response.
It must contain:
- The instruction to READ the log file before responding
- The instruction to WRITE one line to the log after every response
- The date command so the timestamp is correct

This is the only place that reliably fires every time.

### 2. SESSION_LOG.md (project folder) — the memory
An append-only file. One line per entry. Never edited, only appended.
Six entry types cover everything:

```
YYYY-MM-DD HH:MM | CHAT     | what was discussed / decided
YYYY-MM-DD HH:MM | ACTION   | what was done + result
YYYY-MM-DD HH:MM | DECISION | key technical or product decision
YYYY-MM-DD HH:MM | PENDING  | waiting on user — what exactly
YYYY-MM-DD HH:MM | STATE    | current system state snapshot
YYYY-MM-DD HH:MM | NEXT     | concrete next step if mid-task
```

Why append-only: editing an existing structured file requires finding the right section,
understanding the format, not breaking anything. That's enough friction to skip it.
Appending one line takes 3 seconds. Claude will actually do it.

---

## Project Instructions template

```
# [Project Name]
[One line description]

## Before responding to ANYTHING: read SESSION_LOG.md from the project folder. No exceptions.

## After every reply — mandatory:
1. Run `date '+%Y-%m-%d %H:%M'` to get the timestamp.
2. Append one line to SESSION_LOG.md:
   YYYY-MM-DD HH:MM | TYPE | content
   Types: CHAT | ACTION | DECISION | PENDING | STATE | NEXT

## Read in this order
1. **CLAUDE.md** — all operational rules. Single source of truth. Overrides everything here.
2. **CLAUDE_WORKING_GUIDE.md** — architecture and schemas. Read before any code change.
```

---

## CLAUDE.md template (folder instruction)

The folder instruction handles everything operational: deploy rules, test commands,
language rules, IDs, environment variables. It's git-versioned and auto-loaded.

Key section to include:

```markdown
**Start of every session — read in this order:**
1. `SESSION_LOG.md` — full history: actions, decisions, pending, state
2. `CLAUDE_WORKING_GUIDE.md` — architecture and schemas (before any code change)
3. Run relevant tests before every push

**After every reply** — append one line to `SESSION_LOG.md`. No exceptions.
Claude doesn't know when the context window ends, so every message could be the last.

Step 1: run `date '+%Y-%m-%d %H:%M'` to get the timestamp.
Step 2: append one line:
YYYY-MM-DD HH:MM | CHAT    | what was discussed
YYYY-MM-DD HH:MM | ACTION  | what was done + result
YYYY-MM-DD HH:MM | DECISION| key technical or product decision
YYYY-MM-DD HH:MM | PENDING | waiting on user — what exactly
YYYY-MM-DD HH:MM | STATE   | current system state snapshot
YYYY-MM-DD HH:MM | NEXT    | concrete next step if mid-task

Never rewrite past entries. Just append.
```

---

## SESSION_LOG.md starting template

```markdown
# Session Log — append only, never edit past entries
# Types: CHAT | ACTION | DECISION | PENDING | STATE | NEXT
# Time: always run `date '+%Y-%m-%d %H:%M'` before writing an entry

YYYY-MM-DD HH:MM | STATE | project started; [brief description of system state]
```

---

## Real examples

Project Instructions: `apolio-home` project in Claude UI
CLAUDE.md: `/apolio-home/CLAUDE.md` in project folder
SESSION_LOG.md: `/apolio-home/SESSION_LOG.md`

---

## Why not Google Sheets or a database?

- Extra API dependency — can fail, adds latency
- File is simpler, faster, always available
- Git-versioned automatically if folder is a repo

---

## The one rule that makes it work

The write trigger must be in Project Instructions (system prompt), not just in CLAUDE.md.
CLAUDE.md is a file Claude reads — it can be skipped or forgotten.
Project Instructions fire before every response, no exceptions.
