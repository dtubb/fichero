# Test/QA Worker Report — Test Coverage batch (Views logic)

Worker: Claude. Branch: `lane/tests` (worktree `ms-tests`), reset to `origin/main`
(`186a438b`) at start. Commits authored as Claude (`noreply@anthropic.com`) with
`Co-Authored-By: Daniel Tubb`. **Not pushed** — manager merges.

## Issues picked

Milestone Test Coverage now has only 3 open issues, all Swift:

- **#1993 — swift/Views (963 untested)** — **WORKED** (the only one actionable from this lane)
- #1988 — swift/<root> (3 untested) — **not actionable here** (see below)
- #1939 — Run the XCUITest GUI suite in verify --full — **not actionable here** (needs Xcode harness)

Per the brief ("3-5 actionable, skip design-blocked"), I worked the one genuinely
actionable issue (#1993) and went deep on its **unit-testable pure logic**. Most
of #1993's 963 symbols are real SwiftUI (`var body`, modifiers, view-bound
methods) that need a build + snapshot/ViewInspector harness — out of scope for a
swiftlint-only lane — so I targeted the pure helpers buried in Views/ that no
test referenced yet.

## What was added (3 files, 18 tests)

New files in `fichero/fichero-tests/` (a `PBXFileSystemSynchronized` group → auto-join the test target; no `project.pbxproj` edit).

| Issue | File | Under test | Coverage |
|-------|------|-----------|----------|
| #1993 | `LibrarySortFieldTests.swift` | `LibrarySortField` (`LibraryView+Sorting`) | cases/raw values/icons/id; `comparator(ascending:)` **actually orders Documents** by name (asc+desc), createdAt by date, status by raw value; single key path each |
| #1993 | `EdgeFanRoleTests.swift` | `EdgeFanRole` + `EdgeFanRoleResolver` (`WorkflowEdgeView`) | label formatting (`→ N files`/`fan-out`, `∑ N files`/`merge`, none=""); resolver **fan-in-target-wins-over-fan-out-source priority**; unknown/nil → none |
| #1993 | `ActivityDataProcessingHelpersTests.swift` | pure fns in `ActivityDataProcessing` | `ActivityWorkflowGroup.key` fallback; `activityCleanWorkflowName` prefix strip; `activityCleanFilename` 6–12-hex storage-hash stripping (with non-hash/short/long/no-underscore edges); `activityHumanNodeName` hides UUID/dunder/fan_out, Title-cases real ids |

All chosen for real consequence, not happy-path: the sort comparators are
verified by sorting; the edge-fan resolver's priority rule and the filename
hash-detection bounds are exactly where silent UI bugs hide. I deliberately
skipped helpers already covered (`KGSurfaceTab`, `ArtifactRichTextCodec`,
`ChatScopeBuilder`/`ChatWithDocsRouter`, `activityMap*`, `activityHumanizeMessage`).

## Gate results (run from this worktree)

- **swiftlint** on all 3 new files → **clean** (0 warnings/errors).
- No Python/`fichero-engine/src` changes → `ruff`/`pytest` N/A this batch.
- **Caveat:** the Xcode build/test gate is the manager's — this lane cannot
  compile/run XCTest. I matched each symbol's real signature from source (verified
  `Document` init params, the enum cases, the resolver tool names) to minimize
  compile risk, but **the manager should run the Swift test gate before merge**.
  The `No such module 'Fichero'` SourceKit notes are expected without a build.

## Commits (newest first)

```
test(swift): cover ActivityDataProcessing pure string helpers (#1993 Test Coverage)
test(swift): cover LibrarySortField comparator + EdgeFanRole resolver (#1993 Test Coverage)
```

## Not picked (and why)

- **#1988 swift/<root>** — `FicheroApp`/`FicheroApp_iOS` are SwiftUI `App` scenes,
  `NSApplicationDelegate`, and `NetService` delegates; the one value-type helper
  (`BonjourHostRecord.hasReachableURL`) is on a `private` struct, unreachable even
  via `@testable import`. Nothing pure-unit-testable.
- **#1939** — XCUITest GUI suite wiring into `verify --full`; needs the Xcode
  harness the manager owns.

The remaining #1993 surface is genuine SwiftUI requiring a rendering/snapshot
test harness (e.g. ViewInspector) — recommend a Swift-capable lane or adding that
harness before further #1993 work.

Nothing pushed.
