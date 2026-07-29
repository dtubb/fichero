# Fichero Cron Script
# This script is intended to be run every 30 minutes via OpenClaw cron.

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
    echo "Usage: cron_check.sh"
    echo "Runs the Fichero cron health checks from the configured checkout."
    exit 0
fi

REPO_ROOT="${FICHERO_REPO_ROOT:-$HOME/code/fichero}"
cd "$REPO_ROOT"

echo "--- Fichero Cron Execution: $(date) ---"

# 1. Check Inbox
INBOX_COUNT=$(ls docs/agent-workflow/inbox/ | wc -l)
if [ $INBOX_COUNT -gt 0 ]; then
    echo "ALERT: $INBOX_COUNT new items in docs/agent-workflow/inbox/"
fi

# 2. Check TODO status
P0_TASKS=$(grep -c "\[ \] .*P0" docs/agent-workflow/TODO.md)
echo "Current P0 Tasks: $P0_TASKS"

# 3. Quick Health Check (SwiftLint)
# Note: This requires swiftlint to be in the PATH
if command -v swiftlint &> /dev/null; then
    LINT_ERRORS=$(swiftlint lint fichero-swiftui/fichero-swiftui/ --quiet | wc -l)
    echo "SwiftLint Violations: $LINT_ERRORS"
else
    echo "Warning: swiftlint not found."
fi

# 4. Backend Sync Check
# Check if openapi.json matches current code (conceptually)
# ./fichero-server/scripts/sync_openapi_schema.sh --check

echo "Cron check complete."
