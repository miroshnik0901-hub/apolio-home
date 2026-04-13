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
- Reading multiple archive files before every message — absurd cost, wrong architecture.

---

## What works

**Two layers, each doing one job:**

### Layer 1: SESSION_LOG.md — always-on, lightweight memory

An append-only file in the project folder. One line per entry. Never edited, only appended.
Read before every response (via Project Instructions system prompt).
Handles both mid-session context compression and cross-session continuity.

When the log grows large, it rotates: all critical entries are carried forward into the new file.
You never need to read archives during normal work — the rotation summary covers everything.

### Layer 2: pm-create snapshots — comprehensive, on-demand

Full-context snapshots created manually when you want a deeper save point
(approaching token limit, before a risky change, end of a major milestone).
Lives in the project folder as `.md` snapshot files. Reads SESSION_LOG + archives during creation.

---

## SESSION_LOG entry types

```
YYYY-MM-DD HH:MM | CHAT     | what was discussed / decided
YYYY-MM-DD HH:MM | ACTION   | what was done + result
YYYY-MM-DD HH:MM | DECISION | key technical or product decision
YYYY-MM-DD HH:MM | PENDING  | waiting on user — what exactly
YYYY-MM-DD HH:MM | STATE    | current system state snapshot
YYYY-MM-DD HH:MM | NEXT     | concrete next step if mid-task
```

Why append-only: editing a structured file requires finding the right section, understanding
the format, not breaking anything. That's enough friction to skip it.
Appending one line takes 3 seconds. Claude will actually do it.

---

## Rotation — how the log stays small forever

**Trigger:** when `SESSION_LOG.md` exceeds 16384 bytes (~100–120 lines, ~3–4 weeks of active dev).

**Atomicity rule:** write the new file FIRST, then move the old one. Never the reverse.
If Claude crashes mid-rotation, at least one complete file always exists.

**Steps:**
1. `TS=$(date '+%Y-%m-%d_%H-%M')`
2. Create `SESSION_LOG_NEW.md` with mechanical summary extracted from current log:
   - Last STATE entry (verbatim)
   - All DECISION entries (verbatim)
   - All unclosed PENDING entries (verbatim)
   - Last NEXT entry (verbatim)
3. `mv SESSION_LOG.md logs/SESSION_LOG_ARCHIVE_${TS}.md`
4. `mv SESSION_LOG_NEW.md SESSION_LOG.md`
5. Append the current entry that triggered the rotation

**Result:** new SESSION_LOG.md starts with a compact summary of all critical history.
All DECISIONs are carried forward. Archives live in `logs/` — never read routinely.

---

## Project Instructions template

```
# [Project Name]
[One line description]

## Before responding to ANYTHING: read SESSION_LOG.md from the project folder. No exceptions.

## After every reply — mandatory:
1. Run `date '+%Y-%m-%d %H:%M'` to get the timestamp.
2. Check log size: `wc -c SESSION_LOG.md`
3. If size > 16384 bytes → rotate (see rotation rules in CLAUDE.md). Otherwise append one line:
   YYYY-MM-DD HH:MM | TYPE | content
   Types: CHAT | ACTION | DECISION | PENDING | STATE | NEXT

## Read in this order
1. **CLAUDE.md** — all operational rules. Single source of truth. Overrides everything here.
2. **CLAUDE_WORKING_GUIDE.md** — architecture and schemas. Read before any code change.
```

---

## CLAUDE.md — session memory section

```markdown
**After every reply** — append one line to `SESSION_LOG.md`. No exceptions.
Claude doesn't know when the context window ends, so every message could be the last.

Step 1: run `date '+%Y-%m-%d %H:%M'` to get the timestamp.
Step 2: check log size: `wc -c SESSION_LOG.md`
Step 3: if size > 16384 bytes → rotate (see Rotation below). Otherwise append one line:
YYYY-MM-DD HH:MM | CHAT    | what was discussed
YYYY-MM-DD HH:MM | ACTION  | what was done + result
YYYY-MM-DD HH:MM | DECISION| key technical or product decision
YYYY-MM-DD HH:MM | PENDING | waiting on user — what exactly
YYYY-MM-DD HH:MM | STATE   | current system state snapshot
YYYY-MM-DD HH:MM | NEXT    | concrete next step if mid-task

Never rewrite past entries. Just append.

### Rotation (triggered when SESSION_LOG.md > 16384 bytes)

**Order is critical — write new file FIRST, then archive old. Never the reverse.**

1. Get timestamp: `TS=$(date '+%Y-%m-%d_%H-%M')`
2. Create `SESSION_LOG_NEW.md` with mechanical summary — no interpretation, verbatim copy:
   - Last STATE entry from current log
   - All DECISION entries
   - All unclosed PENDING entries
   - Last NEXT entry
3. `mv SESSION_LOG.md logs/SESSION_LOG_ARCHIVE_${TS}.md`
4. `mv SESSION_LOG_NEW.md SESSION_LOG.md`
5. Append the current entry that triggered the rotation

Rules for summary:
- Extract by type only — `grep "| STATE\|DECISION\|PENDING\|NEXT"` from current log
- For STATE and NEXT: take only the last occurrence
- For DECISION and PENDING: take all occurrences
- No paraphrasing, no omissions, no interpretation
```

---

## SESSION_LOG.md starting template

```markdown
# Session Log — append only, never edit past entries
# Types: CHAT | ACTION | DECISION | PENDING | STATE | NEXT
# Format: YYYY-MM-DD HH:MM | TYPE | content
# Time: always run `date '+%Y-%m-%d %H:%M'` before writing an entry

YYYY-MM-DD HH:MM | STATE | project started; [brief description of system state]
```

---

## Folder structure

```
project/
├── SESSION_LOG.md          ← active log (always present, always < 16KB)
├── CLAUDE.md               ← operational rules incl. rotation steps
├── CLAUDE_WORKING_GUIDE.md ← architecture, schemas, file map
└── logs/
    ├── SESSION_LOG_ARCHIVE_2026-04-13_16-11.md
    └── SESSION_LOG_ARCHIVE_2026-04-20_10-05.md
```

---

## Why not read archives on every message?

Archives are append-only history. Reading them before every response means:
- Multiple file reads per message → token waste → slower context fill
- The whole point of rotation is to NOT need the archive in normal flow

The rotation summary carries all DECISIONs forward. If the new SESSION_LOG says
`# ROTATED from: logs/SESSION_LOG_ARCHIVE_...`, the critical history is already in the file.
Archives are only read during `pm-create` snapshots — once, intentionally, with full context.

---

## Why not Google Sheets or a database?

- Extra API dependency — can fail, adds latency
- File is simpler, faster, always available
- Git-versioned automatically if folder is a repo

---

## The one rule that makes it work

The write trigger must be in Project Instructions (system prompt), not just in CLAUDE.md.
CLAUDE.md is a file Claude reads — it can be skipped or forgotten mid-session.
Project Instructions fire before every response, no exceptions.
The rotation size check must also be in Project Instructions for the same reason.
