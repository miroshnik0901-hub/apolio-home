# Apolio Home — Project Instruction

## What this is

Apolio Home is a personal AI agent for Mikhail Miro (Pino Torinese, Italy). Part of the Apolio product family. Current interface: Telegram (@ApolioHomeBot). Stack: Python, Claude API, Google Sheets, PostgreSQL. Deployed on Railway.

## Documentation — read in this order

**1. CLAUDE_WORKING_GUIDE.md** — current system state
Architecture, file map, agent tools (20 total), Google Sheets schema, production IDs, git workflow.
If a previous session summary conflicts with this file — trust the file and git log, not the summary.

**2. DEV_CHECKLIST.md** — what to verify before and after every change
Checklists by area: i18n, UI, menu, transactions, agent tools, photo handling, PostgreSQL, Sheets formulas.
Run the relevant sections before every push.

## Working rules

- Act, don't ask. If the task is clear — execute.
- Before any change: read ALL files the change touches, not just the obvious ones.
- After any change: update CLAUDE_WORKING_GUIDE.md if architecture changed.
- New agent tool → add to TOOLS schema + dispatch dict + section 6 of CLAUDE_WORKING_GUIDE.
- No hardcoded users / categories / accounts. Everything comes from Google Sheets reference data.
- Tool errors → return `{"error": "..."}`, never crash the bot.
- Deploy → Railway deploys automatically after push to `main`.

## Languages

RU / UK / EN / IT — mixed freely, in any order. Mikhail writes in all four.
All new user-facing strings go through `i18n.ts()` / `i18n.t()` — all 4 languages required.
