#!/bin/bash
# Pre-push hook: blocks push to main without Confirm=GO
# Install: cp scripts/pre-push-hook.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push
# Claude must install this at the START of every session.

while read local_ref local_sha remote_ref remote_sha; do
    if [[ "$remote_ref" == "refs/heads/main" ]]; then
        if [[ "$ALLOW_MAIN_PUSH" != "GO_CONFIRMED" ]]; then
            echo ""
            echo "❌❌❌ BLOCKED: direct push to main is FORBIDDEN"
            echo "   Use: ./scripts/deploy_to_main.sh T-XXX"
            echo "   This checks Confirm=GO in task log before deploying."
            echo ""
            exit 1
        fi
    fi
done
exit 0
