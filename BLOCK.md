BLOCKED: All actionable tasks completed or blocked — autonomous loop should stop

## Summary
- Tasks completed this iteration: 2
  - #363: Library snapshots + restore with DuckDB Parquet export
  - #361: XMP sidecar support with libxmp + regex fallback
- Tasks skipped (blocked): 0

## What Remains (all blocked)

### 0.0.1 regression gate (#382-#386)
- Requires manual QA testing — not actionable autonomously
- See `docs/qa/0.0.1-manual-qa-checklist.md`

### Phase 1 PyKEEN wiring (#387)
- Blocked: needs `pykeen` package added to project dependencies
- Requires Daniel to approve dependency addition

### Phase 2-5 (#388-#391)
- All blocked on Phase 1 completing first

## Next Steps
1. Daniel reviews #363 and #361 PRs
2. Daniel adds `pykeen` dependency to unblock #387
3. Daniel runs manual QA from `docs/qa/0.0.1-manual-qa-checklist.md`
