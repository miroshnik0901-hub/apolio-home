**Начало каждой сессии — читать в этом порядке:**
1. `CLAUDE_SESSION.md` — живой журнал: что сделано, что в процессе, отложенные вопросы
2. `CLAUDE_WORKING_GUIDE.md` — архитектура и схемы (перед любым изменением кода)
3. `DEV_CHECKLIST.md` — релевантные секции перед каждым push

`CLAUDE_SESSION.md` обновлять в конце каждой сессии.

## Languages

Mikhail writes in RU / UK / EN / IT freely, in any order, mixed in one message.
All new user-facing strings go through `i18n.ts()` / `i18n.t()` — all 4 languages required.
Never hardcode UI strings. Match Mikhail's language in replies.

## Git & Deploy

- Git: push to `main` for production, `dev` for staging. Never `master`.
- Railway deploys automatically: `main` → production, `dev` → staging.
- Never push to `main` without Confirm=GO from Mikhail. Staging (`dev`) needs no confirmation.

## Dev Workflow (mandatory sequence)

### Before writing code
- [ ] Read ALL files the change touches
- [ ] Trace full chain: initialization → usage → rendering
- [ ] State target end-state explicitly

### Before pushing to `dev`
```bash
python3 -m py_compile bot.py auth.py sheets.py intelligence.py agent.py  # L1
python3 test_regression.py                                                 # L2 unit tests
```
All must pass. Then push to `dev`.

### After pushing to `dev`
```bash
python3 tests/run_all.py   # L1–L3: static + unit + live Sheets (48 checks)
```
Check Railway staging logs — no import errors. Verify bot responds on @ApolioHomeTestBot.
Only after this passes → ask Mikhail for GO → push `main`.

### After pushing to `main`
Check Railway production logs. Spot-check bot on @ApolioHomeBot.

## After Every Code Change

- If architecture changed → update CLAUDE_WORKING_GUIDE.md (file map, tools, schemas).
- New agent tool → add to TOOLS schema + dispatch dict + section 6 of CLAUDE_WORKING_GUIDE.md.

## Google Sheets IDs

| Resource | Environment | ID |
|----------|------------|-----|
| Admin sheet | **Production** | `1Pt5KwSL-9Zgr-tREg6Ek5mlDQhi86rMKIQmLPR4wzOk` |
| Admin sheet | **Test** | `1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM` |
| Budget file | **Production** (MM_BUDGET) | `1erXflbF2V7HyxjrJ9-QKU4u68HJBBQmUkjZDLE_RhpQ` |
| Budget file | **Test** | `196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788` |
| Task Log | **Shared** | `1Un1IHa6ScwZZPhAvSd3w5q31LU_JmeEuATPZZvSkZb4` |

| Mikhail Telegram ID | — | `360466156` |
| Railway project ID | — | `55240cdd-2cbc-4451-b6c9-ca97ce595c18` |
| Railway service ID (bot) | — | `8ec97839-6d49-4cdd-a012-1f6d54853454` |
| Railway env ID | **Production** | `08e40bf3-cbe4-4a80-be54-1f291c21fe0d` |
| Railway env ID | **Staging** | `1e6973d7-2c9c-48a3-8197-b61fd4174ba4` |

**NEVER mix environments.** Test data → Test Admin only. Production data → Production Admin only.

## Google Sheets Access

- Credentials: `GOOGLE_SERVICE_ACCOUNT` env var (base64-encoded service account JSON)
- Service account: `apolio-home-bot@apolio-home.iam.gserviceaccount.com`
- OAuth (for sheet creation): `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`
- All env vars are in `.env` file in project root (gitignored)
- `task_log.py` uses the same `GOOGLE_SERVICE_ACCOUNT` to read/write Task Log sheet
- To use in Cowork/sandbox: load `.env` from mounted folder before importing project modules

## Testing

- **Claude is QA. Never ask Mikhail to test.** After every push to `dev`, Claude must verify the staging bot works — check deploy logs, query staging DB, test bot responses.
- All dev/testing happens on staging (@ApolioHomeTestBot, `dev` branch).
- Staging DB: maglev.proxy.rlwy.net:17325
- Production DB: interchange.proxy.rlwy.net:19732
