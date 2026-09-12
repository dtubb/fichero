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

## The strategy — four layers, most weight at the bottom

1. **Unit / logic — Swift Testing (`@Test`).** Pure rules, models, view-model logic. Fast, parallel.
   New non-UI tests go here. (Guardrail already pins `SWIFT_DEFAULT_ACTOR_ISOLATION=MainActor` so
   off-main `@Test` doesn't SIGTRAP on MainActor statics.)
2. **Snapshot / preview — the cheap deterministic layer that carries the BULK of UI coverage.**
   Render each `#Preview` to a PNG and diff against a committed baseline; the same render is the doc
   screenshot ("one render, two uses"). This runs **on every destination in the simulator** — so it
   catches the iOS 1 MB-stack crash class **without** full app automation. This layer is ~1% built
   today; building it out is the single highest-ROI move. **(Which snapshot engine = open question 1.)**
3. **UI automation — XCTest/XCUITest, kept THIN.** A handful of identifier-driven click-throughs of
   the real app over the existing UDS+seeded harness: launch → seeded data renders → a few core
   flows (open document → inspector → entities load). Data-ID accessibility identifiers only;
   `waitForExistence`/`wait(for:)` only — **the poll-until-120s pattern is retired**. One
   `.xctestplan` runs the same code on macOS, an iOS sim, and an iPad sim.
4. **Accessibility audit — `try app.performAccessibilityAudit()`** in the XCUITest layer: Apple's
   first-party check for missing identifiers/labels and contrast — and it enforces that our elements
   *have* the identifiers layer 3 depends on. **[MISSING today]** — it is used nowhere in the suite
   yet; we currently hand-roll static presence scanners (`check_accessibility.py`,
   `check_tooltips.py`) instead. Adopting the audit and letting it *replace* those scanners is a
   named deliverable of this strategy (prefer Apple's runtime audit over growing our own grep).

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

## Open questions for the design lead

1. **Snapshot engine (the pivotal call).** Apple ships none. Options: (a) **EmergeTools
   SnapshotPreviews** — harvests our ~92 `#Preview`s directly into XCTest snapshot cases (least new
   code, previews *are* the tests); (b) **Point-Free swift-snapshot-testing** — the de-facto
   standard, more explicit test authoring; (c) **keep our hand-rolled `ImageRenderer`+PNG**
   (`SnapshotSupport.swift`) and just build out consumers (no new dependency, but we maintain the
   diff engine ourselves). Recommendation: **(a)** — biggest coverage for least code, turns the 92
   idle previews into the bulk layer; it's a community dep, but it *replaces* hand-rolled infra
   rather than adding to it. Ponytail: prefer deleting our snapshot engine over maintaining it.
2. **How thin is the XCUITest layer?** Given the GUI-session + OOM history, recommend a **hard cap**
   (e.g. ≤ a dozen flows) and everything else pushed to layer 2. Confirm the appetite.
3. **Where does the Mac runner's Aqua session come from?** The build machine is the maintainer's Mac
   (no separate CI). Options: run the UI leg only in an interactive session (current reality), or
   set up a dedicated logged-in runner. This bounds how often layer 3 can run in the gate.
4. **Does layer 2 (snapshots) run in the default gate, or nightly?** It's cheap and cross-platform,
   so it *could* gate every push — but baseline churn on macOS 26 is a cost. Recommend: gate it.

## Behaviors (to fill once the approach is ratified)

`ui-testing.<behavior>` ids will be assigned when this flips from DRAFT to APPROVED (then it needs a
citing test per `check_specs_have_tests`). Draft leaves them open.

## Sources

WWDC 2025 s344 "Record, replay, and review: UI automation with Xcode"; WWDC 2024 s10179 / WWDC 2026
s267 (Swift Testing); Apple docs: ImageRenderer, Previews in Xcode, performAccessibilityAudit,
"Organizing tests to improve feedback"; Apple DTS forum thread 765060 (GUI/Aqua-session requirement);
community: pointfreeco/swift-snapshot-testing, EmergeTools/SnapshotPreviews.
