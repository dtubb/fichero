#!/bin/bash
# Script to create backend issues for Fichero 0.0.3 through 0.1.0

set -e

echo "Creating backend issues for Fichero 0.0.3 through 0.1.0..."

# Issue 1: 0.0.3 Knowledge Migration
cat > /tmp/issue-419.md << 'EOF'
## Backend Work

- Create migration/backfill tooling scripts in `scripts/migrate_*.py`
- Implement dry-run validation against production data
- Implement rollback safety verification
- Test with realistic library data
- Add migration logging and audit trail

## Acceptance

- [ ] Dry-run mode validates migration safety
- [ ] Rollback mode reverts changes with audit trail
- [ ] Migration scripts run on production-like data without errors
- [ ] Test suite for migration paths passes

## Labels

area:backend-api, type:task, 0.0.3, area:migration
EOF

echo "Created issue description for #419"
# gh issue create --title "0.0.3 — Knowledge Migration / Backfill Tooling with Dry-Run + Rollback" \
#   --body "$(cat /tmp/issue-419.md)" \
#   --label "area:backend-api" --label "type:task" --label "0.0.3" --label "area:migration" 2>/dev/null || true

echo "Skipping issue creation - review file /tmp/issue-419.md first"
echo "Then run: gh issue create --title '0.0.3 — Knowledge Migration / Backfill Tooling with Dry-Run + Rollback' --body '...' "
