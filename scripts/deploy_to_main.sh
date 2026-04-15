#!/bin/bash
# deploy_to_main.sh — ONLY way to push to main.
# Requires: 1) task ID, 2) explicit GO confirmation in task log.
#
# Usage: ./scripts/deploy_to_main.sh T-XXX
# Claude must NEVER run `git push origin dev:main` directly.
# ALWAYS use this script.

set -e

TASK_ID="$1"
if [[ -z "$TASK_ID" ]]; then
    echo "❌ Usage: ./scripts/deploy_to_main.sh T-XXX"
    exit 1
fi

echo "Checking Confirm=GO for $TASK_ID in task log..."
CONFIRM=$(python3 -c "
from dotenv import load_dotenv; load_dotenv('.env')
from task_log import TaskLog
tl = TaskLog()
rows = tl.get_all_tasks()
t = next((r for r in rows if r['ID'] == '$TASK_ID'), None)
if not t:
    print('NOT_FOUND')
elif t.get('Confirm','').strip().upper() == 'GO':
    print('GO')
else:
    print(f'MISSING|{t.get(\"Confirm\",\"empty\")}')
" 2>/dev/null)

if [[ "$CONFIRM" == "NOT_FOUND" ]]; then
    echo "❌ Task $TASK_ID not found in task log"
    exit 1
elif [[ "$CONFIRM" != "GO" ]]; then
    STATUS="${CONFIRM#MISSING|}"
    echo "❌ BLOCKED: $TASK_ID has Confirm='$STATUS' — need Confirm=GO from Mikhail"
    echo "   Mikhail must set Confirm=GO in the task log before deployment."
    exit 1
fi

echo "✅ $TASK_ID has Confirm=GO — deploying to main..."
ALLOW_MAIN_PUSH=GO_CONFIRMED git push origin dev:main
echo "✅ Deployed. Update task: Deploy=DEPLOYED, Branch=main"
