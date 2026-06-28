# Test/QA Worker Report — Test Coverage batch (Swift)

Worker: Claude. Branch: `lane/tests` (worktree `ms-tests`), reset to `origin/main`
(`40736aab`) at start. Commits authored as Claude (`noreply@anthropic.com`) with
`Co-Authored-By: Daniel Tubb`. **Not pushed** — manager merges.

## Issues picked

The two Python Test Coverage issues from prior batches are closed; the milestone
now has **only Swift** items left. Per the brief ("Swift → swiftlint only"), I
picked the **safely unit-testable** ones — pure value types / enums / Codable
DTOs — and skipped the rest (see "Not picked"):

- **#1990 — swift/Models (340 untested)** — advanced
- **#1989 — swift/App (36 untested)** — advanced
- **#1991 — swift/Services (804 untested)** — advanced

These are umbrella counts; this batch chips real, pure-logic coverage off each.

## What was added (6 test files, ~33 test methods)

New files dropped into `fichero/fichero-tests/` (a `PBXFileSystemSynchronized`
group, so they auto-join the test target — no `project.pbxproj` edit needed).

| Issue | File | Type(s) under test | Coverage |
|-------|------|--------------------|----------|
| #1990 | `RepresentationTests.swift` | `Representation` enum | every case has title + SF Symbol + stable id; 7 cases; only image/markdown renderable; `from(artifactType:)` mapping incl. nil cases |
| #1990 | `KGFocusStateTests.swift` | `KGFocusState` (@MainActor) | focusing entity clears claim + resets stale source; `focusClaim` co-sets entity; `clear()` resets all; fresh instances (not the shared singleton) |
| #1990 | `ViewContextsTests.swift` | `LibraryContext`/`WorkflowContext`/`ChatContext`/`SearchContext` | defaults; **WorkflowContext hand-rolled Codable flattens CGPoint → canvasPositionX/Y**, decodes flat keys, lossless round-trip; ChatContext round-trip |
| #1989 | `WindowSeedTests.swift` | `WindowSeed` (Duplicate-Window payload) | Codable round-trip with all fields and with optionals nil; JSON decode; Hashable value equality |
| #1989 | `ViewSettingsEnumsTests.swift` | `LibraryLayout`, `PreviewMode`⇆`PreviewLayout` | raw values/icons/Codable; **the PreviewMode↔PreviewLayout facade maps both ways + round-trips bijectively + equal cardinality** |
| #1991 | `IntegrationsServiceTypesTests.swift` | `AppIntegration`, `IntegrationItem`, `ImportResult`/`ExportResult`, DEVONthink/Bookends/Tinderbox, `IntegrationsError` | snake_case decode; `isAvailable`; **AppIntegration name-only identity** (Set dedup); `id` fallbacks (uuid??name, path??name); localized error strings |

Chosen for real consequence, not happy-path: the WorkflowContext CGPoint
flattening and the PreviewMode↔PreviewLayout facade are hand-written mappings
where a silent bug misplaces UI state; AppIntegration's name-only equality is a
subtle Set-dedup behavior worth locking.

## Gate results (run from this worktree)

- **swiftlint** on all 6 new files → **clean** (0 warnings/errors).
- No Python/`fichero-engine/src` changes this batch, so `ruff`/`pytest` N/A.
- **Caveat:** per the brief, the Xcode build/test gate is the manager's — this
  lane cannot compile/run XCTest here. I matched each type's real
  signature/Codable keys from source to minimize compile risk, but **the manager
  should run the Swift test gate to confirm compilation + green** before merge.
  (The `No such module 'Fichero'` SourceKit notes are expected without a build.)

## Commits (newest first)

```
test(swift): cover IntegrationsServiceTypes DTOs (#1991 Test Coverage)
test(swift): cover WindowSeed Codable + ViewSettings view-mode enums (#1989 Test Coverage)
test(swift): cover ViewContexts persistence + WorkflowContext custom Codable (#1990 Test Coverage)
test(swift): cover Representation enum + KGFocusState transitions (#1990 Test Coverage)
```

## Not picked (and why)

- **#1988 swift/<root>** — `FicheroApp`/`FicheroApp_iOS` are SwiftUI `App` scenes +
  `NetService` delegates; not unit-testable as pure logic.
- **#1993 swift/Views** — SwiftUI views need ViewInspector/snapshot infra.
- **#1939** — XCUITest GUI suite wiring; needs the Xcode/verify --full harness.
- Service files that are live endpoint clients (most of #1991) need a mocked
  `APIClient`; I limited #1991 to a pure DTO module to stay verifiable.

Nothing pushed.
