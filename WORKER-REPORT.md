# Worker Report — API Surface & Test Harness batch

**Worker:** Claude (opus) · **Date:** 2026-06-28 · **Branch:** `lane/archdocs`
**Base:** reset to `origin/main` (`9eb8a6ce`) · **Milestone:** API Surface & Test Harness (#70)
**Not pushed.** Gates: Swift → swiftlint only; Python → ruff + pytest.

## Triage (11 open in #70)

| # | Verdict |
|---|---|
| **#1672** | ✅ **DONE** — fixed (service + consumer) |
| **#1671** | ⚠️ **PARTIAL** — service layer fixed; 2 view consumers flagged (build-gated) |
| **#1670** | ✅ **already fixed on main** (verified — no change) |
| #1848 | skip — EPIC |
| #1810 | skip — backend test gaps already well-covered (`test_routes_settings.py` is thorough incl. the tier-preserve invariant; extraction/dedup have existing tests); XCUITest part is GUI |
| #1709 | skip — 4 Swift test failures; can't run Swift tests (no xcodebuild, GUI rule) |
| #1666 | skip — `status:in-progress` |
| #1443 | skip — 385-endpoint mega-task |

## Shipped

### `fix(workflow): entity-type registry calls non-silent + status-aware (#1672)` — `c0b29467`
- `listLibraryEntityTypes` returned `[]` on nil-path/bad-URL/non-2xx/decode-failure;
  `removeLibraryEntityType` used `try?` and the UI dropped the chip regardless — silently
  losing custom ontology types and making rejected deletes look successful.
- **Service** (signatures already `async throws`, no caller ripple): throw on each failure
  mode, reusing existing `EntityServiceGenerated.ServiceError` cases.
- **Consumer** (`ExtractEntitiesNodeConfig`): load surfaces the error via the existing
  `addError` banner instead of empty chips; failed delete keeps the chip (drops it only
  after backend confirms), mirroring the existing `addCustomType` do/catch.
- Gate: **swiftlint clean**.

### `fix(inspector): hermeneutics/classification loads non-silent (#1671 service layer)` — `a369adb3`
- `listDocumentPrototypes` / `listDocumentInterpretations` / `listFrameworks` had the same
  silent pattern (`else { return [] }`, ignored HTTP status, `(try? decode)?.items ?? []`)
  → 401/422/500/malformed rendered as "No types defined" / empty hermeneutics.
- All three now throw on nil-path / bad-URL / non-2xx / decode failure. Immediately surfaces
  errors on the `InterpretationStore` path (it already `try await`s + holds `loadError`).
- **Follow-up (build-gated):** the two view consumers still `(try?) ?? []` —
  `DocumentInspectorInfoTab+Prototype` and `DocumentInspectorArtifactsTab+Interpretations`.
  Both are extension-based views needing new `@State`+UI to show an error state; too risky to
  add blind under a swiftlint-only gate. **#1671 stays open** for a Swift build lane.
- Gate: **swiftlint clean**.

## Notes
- **#1670** can be **closed** — already migrated to the generated client + status switch on main.
- The Swift work here used signature-preserving service changes (no caller ripple) + a
  consumer change mirroring an existing in-file pattern, to stay compile-safe without a build.
  Manager/integrator should build-verify before merge (swiftlint-only gate this batch).
- Backend test coverage in this milestone is already strong; no net-new Python gaps found.

## Auto-advance → AI Backend Hardening (#2507 silent-fallback sweep)

After #70 drained, auto-advanced past Swift/GUI-only milestones (#82 Test Coverage,
#77 Observable Data Layer, #74 Remote, #64 Dev-Experience are SwiftUI/iOS/epic-heavy —
not gateable under swiftlint-only) to **#2507** ("replace silent fallbacks with
raised/logged errors") — the backend twin of the bug class I just fixed in Swift.

**Finding: #2507's high-risk backend work is largely already done.** Verified:
- The #2430 exemplar write paths are fixed: `llm_base.py:562-585` explicitly refuses the
  file_path→parent fallback when an id was given and fails loud (returns None + warning);
  `vision_base.py:2205-2260` splits per-page / fails loud instead of writing the whole-PDF
  transcript onto the parent.
- `_entity_writer.py:1424` already carries a `#2507`-tagged loud-log (was silent).
- Sampled residual catches (e.g. `db.py:479` closing a poisoned connection during reconnect)
  are **legitimate** defensive code — "fixing" them to raise would regress.

The remaining sweep is broad + judgment-heavy; the issue itself says to **pair it with the
silent-failure-hunter review pass** (full-suite-gated), which a changed-tests-only worktree
can't safely do without risking regressions on legitimate defensive catches. **No safe
net-new backend change made; #2507 stays open for a review-driven lane.**

**Frontend half of #2507 advanced this session:** the #1671/#1672 commits above are exactly
its frontend acceptance ("no empty catch hiding a save/merge failure; surface the error, not
a silent empty state").

## Session commits (not pushed)
- `c0b29467` fix(workflow): entity-type registry non-silent + status-aware (#1672)
- `a369adb3` fix(inspector): hermeneutics/classification loads non-silent (#1671 service layer)
- this report.
