# UI Testing Strategy — Design Spec (#TBD)

> Milestone: ui-testing-strategy
>
> Design-led. **Status: DRAFT — for the design lead's review.** How Fichero verifies its UI across
> **macOS, iOS, and iPadOS** without the fragility we have today. Grounded in an honest assessment of
> the current harness and Apple's official 2024–2026 UI-testing guidance (WWDC 2025 session 344, the
> Swift Testing sessions, and Apple DTS forum guidance). 2026-09-12.

## Intent

Verification should be **mostly cheap, deterministic, and cross-platform**, with expensive full-app
UI automation kept **thin and identifier-driven**. Today it is the opposite: near-zero cheap
coverage (1 snapshot consumer despite ~92 `#Preview`s), a single real XCUITest that has never gone
green end-to-end, zero functional iOS/iPad coverage, and an automation model that has twice OOM'd the
machine. The redesign inverts that, and aligns every layer with what Apple actually supports.

## What we learned (the two inputs)

**Our harness is architecturally sound but unfinished** (see [`ui-test-harness.md`](ui-test-harness.md),
[`xcode-build-configs.md`](xcode-build-configs.md)): UDS socket + disposable per-run temp + one
Python seeder + one app launch is the right shape. What's broken: layer 4 (`harness.content-renders`)
never landed, engine stderr is discarded on failure, per-test isolation is fragile menu-nav, and the
whole XCUITest layer polls a11y-tree queries until a 120s deadline — which serialized the full tree
4×/sec and hit **56 GB, twice**. iOS/iPad are canary-only (don't even launch the app) — yet iOS
carries the one fatal class Mac literally cannot see (the 1 MB-stack `swift_getTypeByMangledNode`
overflow).

**Apple's official guidance (2024–2026):**
- **Framework split is settled:** Swift Testing (`@Test`) for unit/logic (parallel, in-process);
  **XCTest + XCUIAutomation for all UI** — `XCUIApplication` is *not* supported in Swift Testing and
  won't be (architecturally incompatible: serial, out-of-process via the Accessibility server).
- **Reliability rests on three pillars:** (1) **accessibility-identifier queries**, data-ID-anchored
  (`"DocRow-\(id)"`), never label/coordinate/localized-text; (2) **`waitForExistence` /
  `wait(for:toEqual:)`, never sleep or poll-until-deadline**; (3) **launch-argument/environment
  seeded deterministic state** on every `launch()`.
- **Same automation code runs on Mac + iOS + iPad** *if* identifier-based — via **one
  `.xctestplan`** with a configuration per `-destination`.
- **macOS UI tests require a real GUI (Aqua) login session** — headless is architecturally broken
  (the Accessibility server lives in the `gui/<UID>` bootstrap namespace; SSH/daemons can't reach
  it). This is a **constraint to design around**, not a bug to fix.
- **Apple ships no snapshot-diff assertion.** `#Preview` is not a test runner; `ImageRenderer` is for
  export. The only first-party visual-correctness primitive is **`performAccessibilityAudit()`**.
  Pixel-diff snapshotting requires a **community** library.

## The strategy — Apple-first, four layers, most weight at the bottom

Ruling: **use Apple's own tools; add no snapshot dependency and delete the hand-rolled diff engine.**
Apple ships no pixel-diff assertion, so we do NOT do automatic pixel-regression — we use Apple's
`RenderPreview` (Xcode Previews) for cheap render checks, `performAccessibilityAudit()` for a11y
correctness, and `.xctestplan` screenshot **capture** for review-by-eye. The cheap cross-platform
layer is **Xcode Previews rendered without launching the app** (layer 2) — so the pyramid is NOT
top-heavy; full-app XCUITest (layer 3) stays thin.

1. **Unit / logic — Swift Testing (`@Test`).** Pure rules, models, view-model logic. Fast, parallel.
   New non-UI tests go here. This is where the bulk of *logic* coverage lives and stays cheap.
   (Guardrail already pins `SWIFT_DEFAULT_ACTOR_ISOLATION=MainActor` so off-main `@Test` doesn't
   SIGTRAP on MainActor statics.)
2. **Xcode Previews rendered via `RenderPreview` — the CHEAP cross-platform layer (no app launch).**
   Apple-native: a `#Preview` renders in isolation, without the UDS+seeded full-app harness. Render
   the key surfaces' previews per size class / platform trait and confirm they render (a preview that
   crashes or shows nothing is a real bug — this is exactly how the iOS 1 MB-stack `swift_getType…`
   overflow surfaces, which Mac XCUITest cannot see), and capture the image for review + the guides.
   Grow the `*PreviewCatalog.swift` pattern (today only Sidebar + Library — ~11% of views have any
   preview) to cover every surface with a visual design to defend. This is the layer that carries the
   bulk of *visual* coverage cheaply. **[largely MISSING today]** — 120 previews exist but ~3 have
   verification catalogs; the win is growing coverage + wiring the render check.
3. **UI automation + accessibility audit — XCTest/XCUITest, kept THIN, one plan across destinations.**
   Identifier-driven click-throughs of the real app over the existing UDS+seeded harness: launch →
   seeded data renders → a few core flows (open document → inspector → entities load). Data-ID
   accessibility identifiers only; `waitForExistence`/`wait(for:)` only — **the poll-until-120s
   pattern is retired**. Each flow ends with `try app.performAccessibilityAudit()` (Apple-first-party
   — catches missing identifiers/labels + contrast, and enforces the identifiers the tests depend
   on). One `.xctestplan` runs the same code on macOS, an iOS sim, and an iPad sim. **[performAccessibilityAudit
   is MISSING today]** — adopting it lets us **retire the hand-rolled `check_accessibility.py` scanner**
   (adopt the audit first, then delete the scanner — never leave a gap between).
4. **Visual review — Apple `.xctestplan` screenshot capture ("keep all") + `RenderPreview` captures.**
   Capture (for review-by-eye + the guides), **not** auto-diff. This **replaces** the hand-rolled
   `SnapshotSupport.swift` PNG-diff engine, which is deleted. Doc screenshots (the "two uses" idea)
   come from these captures, not from a diff test.

**iOS/iPad crash class:** caught at layer 2 (render each preview on the iOS/iPad simulator trait —
cheap, no full-app launch) AND at layer 3 (sims auto-consent to automation, no Mac Aqua-session
problem). Layer 2 is the cheaper first line.

**Accessibility identifiers are the spec contract.** `.accessibilityIdentifier("DocRow-\(id)")` is a
stable behavioral id: a test breaks only when the *behavior* changes, not when copy or layout does —
exactly the "tests pin the spec, not the implementation" principle from the Testing Constitution.
Each XCUITest cites a spec behavior id; the identifier in the SwiftUI view is the same id.

## Fixes this strategy folds in (from the assessment)

- Finish harness **layer 4** (seeded content actually drives the UI) and **persist engine stderr** on
  failure (stop discarding the evidence).
- Add a first-class **app-side reset hook** (`FICHERO_UITEST_RESET`) so per-test isolation isn't menu-nav.
- **`-DisableAnimations`** launch arg → `setAnimationsEnabled(false)` app-side for determinism.
- **`continueAfterFailure = false`**; seed all state via `launchArguments`/`launchEnvironment`.
- Make **iOS/iPad first-class**: real launch + the shared snapshot layer, not canaries.
- Document the **Aqua-session requirement** for the Mac runner (logged-in session +
  `automationmodetool enable-automationmode-without-authentication`); never pretend headless works.
- **XCTSkip must not read as green** — a provisioning failure fails loud (finish `harness.fail-fast-loud`).

## Rulings (design lead, 2026-09-12 — "please proceed")

1. **Visual/a11y layer: Apple tools only — no pixel-diff, no snapshot dependency.** Adopt Apple's
   `performAccessibilityAudit()` (a11y correctness) + `.xctestplan` screenshot capture (visual
   review by eye). **Delete the hand-rolled `SnapshotSupport.swift`** pixel-diff engine. No community
   snapshot lib (EmergeTools/Point-Free) — automatic pixel-regression is deliberately out of scope;
   Apple provides no such tool and we won't hand-roll one. Sequence: adopt the audit, then retire
   `check_accessibility.py`.
2. **XCUITest layer is capped THIN** — a small, fixed set of identifier-driven full-app flows (order
   ~a dozen, not per-feature). Everything else is pushed down to the snapshot layer. No
   poll-until-deadline; `waitForExistence`/`wait(for:)` only.
3. **Mac runner uses the interactive (logged-in Aqua) session** — current reality; no separate CI
   runner for now. This bounds the XCUITest leg to interactive/manager runs, which is acceptable
   because the bulk of coverage lives in the snapshot layer (sim, gateable).
4. **The snapshot layer gates every push.** It's cheap and cross-platform; baseline churn on macOS 26
   is the accepted cost. The XCUITest leg stays out of the per-push gate (interactive session).

## Behaviors

- `ui-testing.preview-render` [PARTIAL] — the key surfaces' `#Preview`s render via `RenderPreview`
  per platform/size trait without crashing or blanking (catches the iOS stack-overflow class cheaply,
  no app launch). Grow the `*PreviewCatalog.swift` pattern beyond today's ~11% preview coverage.
- `ui-testing.preview-coverage-gate` [OK] — **blocker:** `scripts/check_preview_coverage.py` is a
  ratchet (292 backlog seeded in `check_preview_coverage_baseline.json`) that FAILS when a new file
  declaring a SwiftUI `View` ships without a `#Preview`. A surface cannot proceed until it has one, so
  preview coverage can only rise. Runs in `verify_all` with the other `check_*.py`.
- `ui-testing.a11y-audit` [MISSING] — every XCUITest flow ends with `try app.performAccessibilityAudit()`
  (Apple-first-party), catching missing labels/identifiers + contrast. Once wired, it **retires**
  `check_accessibility.py`.
- `ui-testing.crossplatform-plan` [MISSING] — one `.xctestplan` runs the same identifier-driven flows
  on macOS **and** an iOS sim **and** an iPad sim, so the iOS 1 MB-stack crash class is caught (sims
  auto-consent — no Aqua-session gate).
- `ui-testing.identifier-contract` [PARTIAL] — every control a UI test drives has a stable,
  data-ID-anchored `.accessibilityIdentifier` matching this spec (never label/coordinate).
- `ui-testing.xcuitest-thin` [PARTIAL] — the full-app XCUITest set is capped (~a dozen flows) and
  identifier-driven; waits use `waitForExistence`/`wait(for:)`, never poll-until-deadline.
- `ui-testing.deterministic-launch` [PARTIAL] — UI tests seed all state via `launchArguments`/
  `launchEnvironment`, disable animations (`-DisableAnimations`), and set `continueAfterFailure=false`.
- `ui-testing.screenshot-capture` [MISSING] — the `.xctestplan` captures screenshots per destination
  for review-by-eye + the guides (capture, not diff); the hand-rolled `SnapshotSupport.swift`
  pixel-diff engine is **deleted**.
- `ui-testing.evidence-on-failure` [MISSING] — the harness persists engine stderr + a screenshot on
  failure (stop discarding the evidence needed to debug it).

## Sources

WWDC 2025 s344 "Record, replay, and review: UI automation with Xcode"; WWDC 2024 s10179 / WWDC 2026
s267 (Swift Testing); Apple docs: ImageRenderer, Previews in Xcode, performAccessibilityAudit,
"Organizing tests to improve feedback"; Apple DTS forum thread 765060 (GUI/Aqua-session requirement);
community: pointfreeco/swift-snapshot-testing, EmergeTools/SnapshotPreviews.
