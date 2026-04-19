# Apolio Home — 3-Iteration Audit Plan

**Started:** 2026-04-16 23:00 (local)
**Mode:** TEST ONLY (dev branch, test sheets, staging env)
**Autonomy:** no intermediate approvals — proceed through iterations

## Constraints
- Never touch `main` branch or PROD resources
- PROD Admin ID: `1Pt5KwSL-...` → FORBIDDEN
- PROD Budget ID: `1erXflbF...` → FORBIDDEN
- PROD DB `interchange.proxy.rlwy.net:19732` → READ-ONLY (error_log check only)
- Work against:
  - Test Admin: `1YAVdvRI-CHwk_WdISzTAymfhzLAy4pC_nTFM13v5eYM`
  - Test Budget: `196ALLnRbAeICuAsI6tuGr84IXg_oW4GY0ayDaUZr788`
  - Staging bot: `@ApolioHomeTestBot`
  - Dev branch auto-deploys to Railway staging
- Task Log (shared): `1Un1IHa6ScwZZPhAvSd3w5q31LU_JmeEuATPZZvSkZb4` — new issues written here with clear "TEST" tag

## Iteration structure

Each iteration = these phases:
1. **Read** — docs, code, prompts
2. **Tools** — bot handlers, agent tools, DB schema, sheets structure
3. **Outputs** — bot responses, sheet writes, logs, error patterns
4. **Findings** — append to AUDIT_TASKS.md (never overwrite)
5. **Fix** — apply fixes on dev branch, verify on staging

Between iterations: re-read everything with new understanding.

## Deliverables
- `AUDIT_PLAN.md` (this)
- `AUDIT_TASKS.md` (growing list — inconsistencies, bugs, deprecated)
- `AUDIT_ITER1_NOTES.md` / `ITER2` / `ITER3` (findings per pass)
- `AUDIT_CONCLUSION.md` (final)

## Priority framework (derived from CLAUDE.md + chat history)
- **P0 blockers**: data corruption, wrong account ops, GO-bypass
- **P1 high**: UX broken (dup question missing, malformed display), rate-limit failures
- **P2 medium**: i18n gaps, deprecated code, redundant paths
- **P3 low**: doc drift, naming inconsistencies, unused files
