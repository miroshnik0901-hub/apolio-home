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
- Test Budget file_id: `196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788`
- Staging DB: maglev.proxy.rlwy.net:17325
- Production DB: interchange.proxy.rlwy.net:19732
