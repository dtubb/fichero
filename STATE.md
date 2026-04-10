# Current Focus
Backend implementation — 0.0.3 through 0.1.0 milestones

# Branch
- Active branch: `0.0.2`

# Completed
- #419: Migration framework core implemented — MigrationRunner with dry-run, rollback, audit trail (branch: feature/issue-419-migration)
- Created 21 backend-focused GitHub issues (#419-440) for 0.0.3, 0.0.4, 0.0.5, 0.1.0, and legacy tasks
- 0.0.2 release merged to main — all security PRs delivered
- Documentation in agent-work/ISSUES-CREATED.md for agent agent claiming

# Next Session — Start Here
**Task #419 (Migration Framework):**
1. Complete CLI script at `scripts/migrate.py` with full command set
2. Add comprehensive unit tests in `fichero-api/tests/unit/test_migrations.py`
3. Run pytest + ruff to validate before PR
4. Submit PR for review

**Other Backend-Only Work Ready:**
- #420: Reindex/repair workers
- #421: Multilingual baseline
- #422: Thin MCP adapters
- #425: Activity stream enhancements

**Reference:**
- Branch: `feature/issue-419-migration`
- Migration framework: `fichero-api/src/fichero/migrations.py`
