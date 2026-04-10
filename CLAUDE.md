Read CLAUDE_WORKING_GUIDE.md before any change.

## Git & Deploy

- Git: push to `main` for production, `dev` for staging. Never `master`.
- Railway deploys automatically: `main` → production, `dev` → staging.
- Never push to `main` without Confirm=GO from Mikhail. Staging (`dev`) needs no confirmation.

## After Every Change

- If architecture changed → update CLAUDE_WORKING_GUIDE.md (file map, tools, schemas).
- Run `python3 test_regression.py` — all section 1 and 2 tests must pass.
- After push to `dev` → check staging DB / logs to confirm deploy works.
- **No hardcoding.** Never hardcode buttons/labels/UI. Use existing methods (present_options, i18n, etc.).
- **Regression test ALL flows** — not just the one you changed. See DEV_CHECKLIST.md and CLAUDE_WORKING_GUIDE.md §14.

## Testing

- **Claude is QA. Never ask Mikhail to test.** After every push to `dev`, Claude must verify the staging bot works — check deploy logs, query staging DB, test bot responses.
- All dev/testing happens on staging (@ApolioHomeTestBot, `dev` branch).
- Test Budget file_id: `196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788`
- Staging DB: maglev.proxy.rlwy.net:17325
- Production DB: interchange.proxy.rlwy.net:19732
