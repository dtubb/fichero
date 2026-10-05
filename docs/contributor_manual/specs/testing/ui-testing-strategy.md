# UI Testing Strategy — Design Spec (#TBD)

> Milestone: ui-testing-strategy
> Manual: docs/contributor_manual/guide/11-testing.md
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

- `ui-testing.preview-render` [PARTIAL] (#4769) — the key surfaces' `#Preview`s render via `RenderPreview`
  per platform/size trait without crashing or blanking (catches the iOS stack-overflow class cheaply,
  no app launch). Grow the `*PreviewCatalog.swift` pattern beyond today's ~11% preview coverage.
- `ui-testing.preview-coverage-gate` [OK] — **blocker:** `scripts/check_preview_coverage.py` is a
  ratchet (292 backlog seeded in `check_preview_coverage_baseline.json`) that FAILS when a new file
  declaring a SwiftUI `View` ships without a `#Preview`. A surface cannot proceed until it has one, so
  preview coverage can only rise. Runs in `verify_all` with the other `check_*.py`. Pinned:
  `test_check_preview_coverage.py::test_view_without_preview_is_flagged`,
  `::test_view_with_preview_is_not_flagged`,
  `::test_non_view_struct_is_never_required_to_have_a_preview`.
- `ui-testing.a11y-audit` [PARTIAL] (#4770) — every XCUITest flow ends with `try app.performAccessibilityAudit()`
  (Apple-first-party), catching missing labels/identifiers + contrast. Once wired, it **retires**
  `check_accessibility.py`. Wired in one suite (`KGInspectorCRUDUITests`) of twelve; `check_accessibility.py`
  not yet retired.
- `ui-testing.crossplatform-plan` [PARTIAL] (#4771) — one `.xctestplan` runs the same identifier-driven flows
  on macOS **and** an iOS sim **and** an iPad sim, so the iOS 1 MB-stack crash class is caught (sims
  auto-consent — no Aqua-session gate). Per-platform plans + canary smoke exist for all three; the
  substantive flow (`InspectorFlowsUITests`) only runs on macOS today.
- `ui-testing.identifier-contract` [PARTIAL] (#4772) — every control a UI test drives has a stable,
  data-ID-anchored `.accessibilityIdentifier` matching this spec (never label/coordinate).
- `ui-testing.xcuitest-thin` [PARTIAL] (#4773) — the full-app XCUITest set is capped (~a dozen flows) and
  identifier-driven; waits use `waitForExistence`/`wait(for:)`, never poll-until-deadline.
- `ui-testing.deterministic-launch` [PARTIAL] (#4775) — UI tests seed all state via `launchArguments`/
  `launchEnvironment`, disable animations (`-DisableAnimations`), and set `continueAfterFailure=false`.
- `ui-testing.screenshot-capture` [MISSING] (#4776) — the `.xctestplan` captures screenshots per destination
  for review-by-eye + the guides (capture, not diff); the hand-rolled `SnapshotSupport.swift`
  pixel-diff engine is **deleted**. The engine deletion is done; the `.xctestplan` capture config is not.
- `ui-testing.evidence-on-failure` [PARTIAL] (#4777) — the harness persists engine stderr + a screenshot on
  failure (stop discarding the evidence needed to debug it). Implemented (`FicheroUISession.swift`,
  `UITestEngineHarness.swift`) but has no pinning test guarding the behavior.

## Driving the running app from outside (added 2026-09-28; DRAFT)

**Why.** An agent must be able to test what a person SEES, not what a store holds. On 2026-09-28,
72 of 72 end-to-end tests were green while the app showed an imported page with no boxes: the
engine tests proved the segments exist, and `ImportedPageDrawsItsBoxesTests` proved the Swift store
gets them. Nothing looked at the window. The requirement this section serves: **a check can say
"page X draws N boxes", with the ids, read from the drawn view hierarchy, and compare it with what
the engine holds.**

**What exists (grounded, this worktree).**
- **An AppleScript dictionary is already the agent loop (#4535):** `fichero/fichero/Fichero.sdef`,
  `Services/AppleScriptCommands.swift`, `Services/AppleScriptRunCommands.swift`.
  - The verbs include the UI verbs (`open project`, `open node`, `select nodes`, `reveal segments`,
    `show pane`, `show inspector tab`; `Services/AppleScriptUIVerbs.swift`, the same `UIVerbs` calls
    as the App Intents, #5453), workflow run/stop/status, and `screenshot`.
  - `screenshot` (`Services/FicheroUICapture.swift`) renders the front window, or one pane of it (by
    the frame the pane was laid out at), offscreen with `bitmapImageRepForCachingDisplay(in:)` +
    `cacheDisplay(in:to:)`. That needs no screen-recording permission.
  - `scripts/ux_smoke.py` drives the verbs through `osascript` against the built app and the
    spawn-per-run engine. Its window check is "a non-trivial PNG", which a window with no boxes
    passes.
  - `Tests/Unit/mac/AppleScriptSurfaceTests.swift` pins that the verbs are declared and every bound
    Cocoa class exists.
  - `NSAppleScriptEnabled` and `OSAScriptingDefinition` are unconditional in `Info.plist`, so the
    dictionary ships in Release.
- **App Intents exist:** `Intents/FicheroActionIntents.swift`, `FicheroAppEntities.swift`,
  `FicheroShortcuts.swift`.
- **Drawn boxes had NO identity** (as found 2026-09-28). No accessibility element or identifier, so
  no channel could say which segments a page drew. (The `ForEach` keyed by offset first cited here,
  `BoundingBoxOverlay.swift`, had no callers and is deleted; the boxes are drawn by
  `DocumentOverlayView`, where `drawn-boxes-are-elements` now puts the elements.)

**The options.** Each is judged on whether it can observe the DRAWN boxes, whether it can be kept out
of Release, its security story, and its cost.

| | (a) AppleScript / OSA (sdef + `NSScriptCommand`) | (b) App Intents / Shortcuts | (c) Debug-only control socket speaking MCP | (d) XCUITest (`XCUIAutomation`) |
|---|---|---|---|---|
| **Observes the window?** | Yes, if the verb reads the view hierarchy: it runs in-process, on the main actor, beside the views. It can walk the drawn per-box elements and render any view offscreen. | Only what `perform()` returns (`ReturnsValue`). It runs in-process, so it could read views, but the framework is built for user actions, not structured inspection. | Yes, in-process, the same as (a). | Yes: it reads the **accessibility tree**, which is the drawn UI. That is the right observation model. |
| **Debug-only?** | Yes. The test verbs' classes go under `#if DEBUG`, and a Debug-only sdef suite is selected per configuration through the `OSAScriptingDefinition` build setting. The user-facing verbs are unchanged. | Yes (`#if DEBUG` intents), but App Shortcuts metadata is extracted at build time, and running an intent from a shell needs a Shortcut by name (`shortcuts run`). | Yes: `#if DEBUG`, compiled out. | It's a test bundle, so it never ships. |
| **Security** | Apple events are gated by TCC Automation consent **on the sender** (one prompt per sending app). A hardened sender needs `com.apple.security.automation.apple-events`. Nothing listens on a port. | Runs through Shortcuts, under the user's permissions. | A new listener, even in Debug. It needs a socket in the app's container, owner-only, compiled out of Release, and a guard that it is. | None at runtime (test-only). |
| **Works for an agent in a shell?** | Yes, via `osascript`, in the logged-in session. No synthesized events, so it works when the screen is locked, unlike `CGEvent`-driven tools. | Awkward: it goes through the Shortcuts app's library. | Yes. Agents already speak MCP. | Poorly: it needs an unlocked Aqua GUI session, the runner owns the app's launch, and it's slow. It is the leg this strategy caps THIN. |
| **Cost** | **Low: extend what exists.** New verbs follow the existing command pattern, and the tests and smoke exist. | Medium, and it bends a user feature into a test channel. | **High:** a Swift MCP server (a new dependency, or a hand-rolled JSON-RPC over UDS) that duplicates (a)'s verbs, plus a new attack surface to guard. | Already paid; kept thin by ruling 2. |

**Recommendation: (a), extended.** This iterates, never replaces: #4535 already made the AppleScript
dictionary the agent and test loop, with a smoke and pinning tests. What it lacks is the ability to
READ what is drawn and to reach below a document. The agent's MCP reach is a thin `fichero-mcp` tool
that runs `osascript` (the "via MCP/CLI" half of #4535's title), so there's one app channel and no
second listener.
- (c) is rejected because it duplicates (a) with a new listener to secure.
- (b) is rejected because it bends a user feature into a test channel.
- (d) stays the thin XCUITest layer. It benefits from the same prerequisite (per-box accessibility
  elements) and needs no change of its own.

**The prerequisite, whichever option is chosen:** every drawn box is an accessibility element with a
data-ID identifier, `SegmentBox-<segmentId>`, and its frame. This follows this strategy's
identifier contract (`ui-testing.identifier-contract`). "What the window shows" then has one meaning
for AppleScript, XCUITest and VoiceOver alike, and an element exists only if its view was drawn.

**The new verbs (Debug-only suite).**
- `select page <document id>` (now the user dictionary's `open node`, #5453)
- `select segment <segment id>`: selects it in the Source view, the Reader and the Inspector (one
  selection).
- `show pane <name>`: the panes model (`modes-to-panes.md`); now the user dictionary's, #5453.
- `describe window`: returns JSON with the panes shown; the selection; and, for each page on screen,
  its id and the segment ids whose boxes are DRAWN, with their frames. All of it is read from the
  drawn elements, never from a store.

The regression check this enables is the one that was missing: import a page through the engine,
`select page`, `describe window`, and the drawn ids equal the engine's segment ids for that page's
working pass.

**Behaviours.**
- `ui-testing.drawn-boxes-are-elements` [PARTIAL] (#5192): every box drawn on a page is an accessibility
  element identified `SegmentBox-<segmentId>` with its frame; none is drawn without one, and none
  exists undrawn.
  **Built 2026-09-28 (f794976dc), tests not yet run:** the image overlay that draws the boxes
  (`DocumentOverlayView.accessibilityChildren`) and a PDF page's view (`PinchOwningPDFView`) each name
  every box drawn in view `SegmentBox-<segmentId>`, labelled by kind, with its drawn frame and selected
  state (`SegmentBoxAccessibility`). Pinned by
  `ImportedPageDrawsItsBoxesTests.testTheRealPreviewInTheLibraryWindowsTreeDrawsTheImportedPagesRegionsAndLines`
  (the real Preview in the window's environment: exactly the recorded page's 4 regions and 12 lines,
  read from the accessibility tree) and `…testAPDFPagesDrawnSegmentBoxesAreAccessibilityElements`. OK
  once those run green.
- `ui-testing.describe-window` [PARTIAL] (#5193): a Debug-only `describe window` verb reports panes,
  selection and, per page on screen, the drawn segment ids and frames, read from the drawn elements.
  **Built 2026-09-28, tests not yet run:** `WindowDescription.describe` walks the key window's views and
  accessibility elements -- panes by their `pane.<kind>` identifiers; each page by its drawing view
  (`SegmentPage-<id>` on the image overlay, the PDF view's page id); each page's `SegmentBox-<id>` elements
  with kind, screen frame and selected state -- as JSON. The verb is `describe window` in the Debug-only
  "Fichero Test Suite" of `FicheroDebug.sdef`, which XIncludes `Fichero.sdef`; Info.plist names the
  dictionary through `FICHERO_SCRIPTING_DEFINITION` (Debug: FicheroDebug.sdef; Release, Dev/Alpha/Beta
  Embedded: Fichero.sdef), and `FicheroDescribeWindowCommand` is `#if DEBUG`. Pinned by the hosted
  real-Preview test (`describe` finds doc-0001 and its 16 boxes) and
  `AppleScriptSurfaceTests.testTheDebugDictionaryIncludesTheUserOneAndAddsDescribeWindow`. Not yet: run
  from `osascript` against a built Debug app.
- `ui-testing.drive-below-a-document` [PARTIAL] (#5194): Debug-only `select page`, `select segment` and
  `show pane` verbs, each answering whether the request was accepted, in the style of the existing
  verbs.
  **Built 2026-09-28, tests not yet run:** in `FicheroDebug.sdef`'s test suite, through seams the app
  already has -- `select segment` through the sidebar's reveal (a segment is resolved to its live page
  by the engine's one resolver, following a merge or a split, as a citable reference is). `select page`
  and `show pane` moved to the user dictionary as the UI verbs `open node` and `show pane` (#5453;
  `AppleScriptSurfaceTests.testTheCommandsCallTheUIVerbs`). Not yet:
  run through `osascript`; `select segment` selects in the Source view only once a list that takes the
  pending selection (the Order list, the Segments pane) shows the page, as a citable reference does.
- `ui-testing.test-verbs-never-in-release` [GAP] (#5195): a Release build contains neither the test
  suite in its sdef nor the test verbs' command classes, and a guard over the built Release app fails
  if either appears.
- `ui-testing.window-matches-engine` [GAP] (#5196): the scripted smoke asserts, for an imported page,
  that the drawn box ids equal the engine's segment ids for its working pass. This is the check that
  would have failed on 2026-09-28.

**Open questions.**
1. The user-facing dictionary ships in Release today with write verbs (`import file`, `run workflow`).
   Do those go through the one audited action layer, and should a scriptable write stay in Release at
   all? It's a product decision, recorded here and not changed by this section.
2. Does `cacheDisplay` render the Metal-backed parts of the page (the image under the boxes)? The
   capture code calls which views are findable "empirical". `describe window` does not depend on
   pixels, but a screenshot attached to a failure would.

## Sources

Apple: [XCUIAutomation](https://developer.apple.com/documentation/xcuiautomation) and WWDC25 s344
([Record, replay, and review](https://developer.apple.com/videos/play/wwdc2025/344/));
[App Intents](https://developer.apple.com/documentation/appintents),
[ReturnsValue](https://developer.apple.com/documentation/appintents/returnsvalue),
[App Shortcuts](https://developer.apple.com/documentation/appintents/app-shortcuts),
[Run shortcuts from the command line](https://support.apple.com/guide/shortcuts-mac/run-shortcuts-from-the-command-line-apd455c82f02/mac);
[NSScriptCommand](https://developer.apple.com/documentation/foundation/nsscriptcommand) and the
Cocoa Scripting Guide
([Scriptable Cocoa applications](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/ScriptableCocoaApplications/));
[com.apple.security.automation.apple-events](https://developer.apple.com/documentation/bundleresources/entitlements/com.apple.security.automation.apple-events);
[NSView.cacheDisplay(in:to:)](https://developer.apple.com/documentation/appkit/nsview/cachedisplay(in:to:));
[accessibilityIdentifier(_:)](https://developer.apple.com/documentation/swiftui/view/accessibilityidentifier(_:)).

WWDC 2025 s344 "Record, replay, and review: UI automation with Xcode"; WWDC 2024 s10179 / WWDC 2026
s267 (Swift Testing); Apple docs: ImageRenderer, Previews in Xcode, performAccessibilityAudit,
"Organizing tests to improve feedback"; Apple DTS forum thread 765060 (GUI/Aqua-session requirement);
community: pointfreeco/swift-snapshot-testing, EmergeTools/SnapshotPreviews.

## Triaged from the backlog (2026-10-04)
- `uitest.every-surface-every-interaction` — **[GAP]** (#4464) every surface (library, sidebar, inspector lists) supports drag and drop, VoiceOver, arrow keys and menus, and a test per surface proves each interaction.
- `uitest.no-source-string-tests` — **[GAP]** (#4447, #4267, #4492) Swift guards assert behaviour, not source spelling; a source-string test must be rewritten to run the behaviour (17 of 18 gate failures in one run were spelling tests).
- `uitest.claim-annotation-store-instantiated` — **[GAP]** (#4510) ClaimStore and AnnotationStore are constructed and exercised in tests, not only source-text inspected.
- `uitest.split-subscript-guardrail` — **[GAP]** (#4534) scripts/check_split_subscript.py flags an unguarded [1] on components(separatedBy:)/split in test code, with a firing fixture (script does not exist).
- `uitest.drop-loader-chokepoint-guardrail` — **[GAP]** (#4543) scripts/check_drop_loader_chokepoint.py forbids NSItemProvider load calls outside ExternalFileDropLoader and SidebarDropProviderReader, with a firing fixture (script does not exist).
- `ui-testing.restored-state-launch` — **[GAP]** (#4761) a UI test relaunches with saved window state and the app is still running with library.content.ready after 40 s.
- `uitest.platform-lanes-mac-ipad-iphone` — **[GAP]** (#4173) real XCUITest suites for Mac, iPad and iPhone with a launch smoke test per platform and per-surface flows, run in a GUI session.
- `uitest.ipad-cli-mcp-legs` — **[GAP]** (#4250) fichero-ipad.xctestplan runs the real unit target plus a simulator smoke leg (gate ios), and a CLI and MCP pytest leg round-trips list/import/search/export on a seeded library.

## Future (ideas, not scheduled)
- (#4174) Measured pathway to 100% coverage: xccov and coverage.py in the gates, ratchet rule, deterministic seams for LangChain.
- (#4241) Two missing test layers (store-with-stubbed-transport, scenario tests) and a five-step coverage roadmap.
- (#4242) Small non-blocking follow-ups from the 2026-07-28 adversarial test review (compound-wait race in LibraryLoadingIsNotAnOutageUITests, etc.).
- (#4262) A gate perf leg with recorded launch and interaction baselines and ratchet semantics.
- (#4263) Long-horizon: extract host-free core packages and drive scenario tests as data.
- (#4420) Program: seam tests asserting every published signal has a consumer and every consumer a publisher.
- (#4618) Design-led testing discipline (Testing Constitution) and regression corpus, awaiting ratification.
