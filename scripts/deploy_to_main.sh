#!/bin/bash
# deploy_to_main.sh — ONLY way to push to main.
#
# Usage:
#   ./scripts/deploy_to_main.sh T-XXX                          # fast-forward dev:main
#   ./scripts/deploy_to_main.sh T-XXX --cherry-pick <sha>      # cherry-pick onto main (dev diverged)
#   ./scripts/deploy_to_main.sh T-XXX [--cherry-pick <sha>] --dry-run
#
# Always:
#   - Requires Confirm=GO for T-XXX in Task Log (set by Mikhail).
#   - Sets ALLOW_MAIN_PUSH=GO_CONFIRMED (the pre-push hook checks this).
#   - On FUSE-mount sandboxes (where .git/objects writes fail), falls back to a
#     fresh /tmp/apolio-deploy-T-XXX clone via HTTPS + GITHUB_PAT.
#
# Why cherry-pick mode exists (T-257):
#   When earlier task deploys went via cherry-pick, dev has commits not on main
#   and main has commits not on dev → `git push origin dev:main` is non-fast-
#   forward and blocked. Cherry-picking only the task's commit onto main keeps
#   PROD on the intended scope.
#
# Claude must NEVER run `git push origin dev:main` directly. ALWAYS use this script.

set -e

TASK_ID=""
SHA=""
DRY_RUN=0
MODE="ff"  # "ff" (default) or "cherry"

usage() {
    cat <<EOF
Usage: $0 T-XXX [--cherry-pick <sha>] [--dry-run]

Examples:
  $0 T-257                              # fast-forward dev:main (works when dev is direct successor of main)
  $0 T-257 --cherry-pick dc9fa2a       # cherry-pick dc9fa2a onto main (dev has diverged)
  $0 T-257 --cherry-pick dc9fa2a --dry-run    # everything except the actual push
EOF
    exit 1
}

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --cherry-pick)
            MODE="cherry"
            if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
                echo "❌ --cherry-pick requires <sha>"
                usage
            fi
            SHA="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        T-[0-9]*)
            TASK_ID="$1"
            shift
            ;;
        *)
            echo "❌ Unknown arg: $1"
            usage
            ;;
    esac
done

[[ -z "$TASK_ID" ]] && { echo "❌ TASK_ID missing"; usage; }
[[ "$MODE" == "cherry" && -z "$SHA" ]] && { echo "❌ --cherry-pick requires <sha>"; usage; }

# ── Verify Confirm=GO in Task Log ─────────────────────────────────────────────
echo "[1/4] Checking Confirm=GO for $TASK_ID in task log..."
CONFIRM=$(python3 -c "
from dotenv import load_dotenv; load_dotenv('.env')
from task_log import TaskLog
tl = TaskLog()
rows = tl.get_all_tasks()
t = next((r for r in rows if str(r.get('ID','')).strip().upper() == '$TASK_ID'.upper()), None)
if not t:
    print('NOT_FOUND')
elif str(t.get('Confirm','')).strip().upper() == 'GO':
    print('GO')
else:
    print('MISSING|' + str(t.get('Confirm','')).strip())
" 2>/dev/null)

if [[ "$CONFIRM" == "NOT_FOUND" ]]; then
    echo "❌ Task $TASK_ID not found in task log"
    exit 1
elif [[ "$CONFIRM" != "GO" ]]; then
    STATUS="${CONFIRM#MISSING|}"
    echo "❌ BLOCKED: $TASK_ID has Confirm='${STATUS:-empty}' — need Confirm=GO from Mikhail"
    exit 1
fi
echo "    ✓ Confirm=GO"

# ── Choose deploy strategy ────────────────────────────────────────────────────
DRY_RUN_LABEL=""
[[ $DRY_RUN -eq 1 ]] && DRY_RUN_LABEL=" DRY_RUN"
echo "[2/4] Strategy: $MODE${SHA:+ (sha=$SHA)}${DRY_RUN_LABEL}"

# Detect whether we're on a FUSE-mounted repo (.git/objects writes fail).
# Some FUSE mounts allow touch (creates a placeholder) but block rm — detect both.
FUSE_FALLBACK=0
_fuse_probe=".git/objects/.write_test_$$"
if ! touch "$_fuse_probe" 2>/dev/null; then
    FUSE_FALLBACK=1
    echo "    ⚠️  Local .git/objects is read-only (FUSE) — will use /tmp clone"
elif ! rm -f "$_fuse_probe" 2>/dev/null; then
    FUSE_FALLBACK=1
    echo "    ⚠️  Local .git/objects touch OK but rm fails (FUSE partial) — will use /tmp clone"
    # Best-effort: leave the probe file behind; on FUSE it's often a no-op write anyway.
fi

# ── Execute deploy ────────────────────────────────────────────────────────────
do_push_native_ff() {
    echo "[3/4] Native fast-forward push: dev → main"
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "    DRY_RUN: would run: ALLOW_MAIN_PUSH=GO_CONFIRMED git push origin dev:main"
        return 0
    fi
    ALLOW_MAIN_PUSH=GO_CONFIRMED git push origin dev:main
}

do_push_native_cherry() {
    echo "[3/4] Native cherry-pick: $SHA onto main"
    git fetch origin
    local cur_branch
    cur_branch=$(git rev-parse --abbrev-ref HEAD)
    git checkout main 2>/dev/null || git checkout -b main origin/main
    git reset --hard origin/main
    git cherry-pick "$SHA"
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "    DRY_RUN: would run: ALLOW_MAIN_PUSH=GO_CONFIRMED git push origin main"
        git checkout "$cur_branch"
        return 0
    fi
    ALLOW_MAIN_PUSH=GO_CONFIRMED git push origin main
    git checkout "$cur_branch"
}

do_push_fuse_fallback() {
    # Fresh clone in /tmp via HTTPS+PAT
    local tmpdir="/tmp/apolio-deploy-${TASK_ID}-$$"
    echo "[3/4] FUSE fallback: fresh clone at $tmpdir"

    if [[ -z "${GITHUB_PAT:-}" ]]; then
        # Try .env
        if [[ -f .env ]] && grep -q "^GITHUB_PAT=" .env; then
            export GITHUB_PAT=$(grep "^GITHUB_PAT=" .env | head -1 | cut -d= -f2-)
        fi
    fi
    if [[ -z "${GITHUB_PAT:-}" ]]; then
        echo "❌ FUSE fallback requires GITHUB_PAT env var (or in .env)"
        exit 1
    fi

    local repo_url="https://${GITHUB_PAT}@github.com/miroshnik0901-hub/apolio-home.git"
    git clone --quiet "$repo_url" "$tmpdir"
    pushd "$tmpdir" >/dev/null

    git config user.email "miroshnik0901@gmail.com"
    git config user.name  "Mikhail Miro"

    if [[ "$MODE" == "ff" ]]; then
        git push origin origin/dev:main
    else
        git checkout main
        git cherry-pick "$SHA"
        if [[ $DRY_RUN -eq 1 ]]; then
            echo "    DRY_RUN: cherry-pick applied; not pushing"
            popd >/dev/null
            return 0
        fi
        # The pre-push hook is not in this fresh clone, so ALLOW_MAIN_PUSH not strictly needed,
        # but we set it anyway in case the hook gets installed by future automation.
        ALLOW_MAIN_PUSH=GO_CONFIRMED git push origin main
    fi

    popd >/dev/null
    echo "    ✓ Pushed via /tmp clone. (Leaving $tmpdir for inspection — remove manually.)"
}

if [[ $FUSE_FALLBACK -eq 1 ]]; then
    do_push_fuse_fallback
elif [[ "$MODE" == "ff" ]]; then
    do_push_native_ff
else
    do_push_native_cherry
fi

# ── Post-deploy hint ──────────────────────────────────────────────────────────
echo "[4/4] Done."
echo "    Next steps (manual or via Claude):"
echo "      python3 scripts/ap_sync_prod.py     # verify PROD structure"
echo "      Update Task Log $TASK_ID: Status, Branch=main, Deploy=DEPLOYED"
echo "      Update DEV_PROD_STATE.md and SESSION_LOG.md"
