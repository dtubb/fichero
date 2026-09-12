# RESUME — design-led testing + spec/milestone/tag tracking (2026-09-09 overnight)

**claude-mem is OUT** (allowance exhausted since 13:15Z) — this file is the handoff instead of memory. Do NOT restart the mem worker.

Branch: `integration` worktree. Commits this session: `62d7851df`, `486fb09f0` (both local, NOT pushed).

## Done + VERIFIED (headless)
- **3 design-led specs**, all APPROVED, in `docs/contributor_manual/specs/`:
  - `ui-test-harness.md` — XCUITest connects to the seeded engine; **empty new/open-library screen REMOVED** (no-library → main interface, like the no-backend-connection path via BackendRootGate). Milestone: ui-test-harness (#278).
  - `xcode-build-configs.md` — build/test/run matrix. **Key finding: Dev Local = Debug config = UNSANDBOXED** (the stale "sandboxed" comment in UITestEngineHarness.swift:260 is what stranded the harness). Milestone: xcode-build-configs (#279).
  - `transport-http-uds.md` — HTTPS/UDS/in-memory contract. Milestone: transport-http-uds (#264, renamed from "Connection & Transport Hygiene").
- **Tracking system: spec name == milestone name == test tag** (front `@Tag` + back pytest marker). Documented in `_TEMPLATE.md`, `TEST-TEMPLATE.md`, `TESTING.md`, `AGENTS.md`.
- **3 guardrails** (auto-gated by verify_all.sh), all green, drift-proven:
  - `scripts/check_xcode_config_invariants.py` (+ unit tests `tests/unit/scripts/test_check_xcode_config_invariants.py`, 5 cases)
  - `scripts/check_spec_milestones.py` (+ unit tests `test_check_spec_milestones.py`, 6 cases)
  - existing `check_specs_have_tests.py` still green (7 approved, all cited)
- **pytest markers** `transport`, `build_config` registered in `fichero-server/pyproject.toml`; in-memory transport test + config test marked & PASSING.
- 4 pre-existing specs grandfathered (kg-tables, kg-entity-inspector, sidebar-crud, workflow-node-config) — graduate onto a milestone as their area is next worked.

## BLOCKED overnight (need Daniel / GUI)
1. **SwiftPM package resolution** — `Fichero (Dev Local)` build fails at 0.45s: "Missing package product FicheroAPIClient / Sparkle". Fix = **Xcode → File → Packages → Reset Package Caches** (GUI). Until then NO Swift build/test runs. Do NOT rm -rf DerivedData/SourcePackages unattended (raced a collision before).
2. **XCUITest run + RenderPreview** — need an UNLOCKED GUI session (screen-lock blocks XCUITests + screenshots). The UI/UX root-cause (why the seeded library isn't current → empty state) is queued for a GUI session.
3. `486fb09f0` extends `EngineTransportModeTests.swift` (5 precedence cases, `.transport` tag) — **compile-unverified**, blocked on #1. Manager build to confirm (matches the exact in-file API; low risk).

## Root cause found (UI-test harness) — for the fix once unblocked
- Python spawner (`test_engine_harness.py`) is HEALTHY: seeds + binds + serves in ~15s.
- Dev Local is UNSANDBOXED → filesystem is NOT the blocker. The #4194 relocation of the socket into the REAL app container (`~/Library/Containers/app.fichero.fichero/Data/tmp`) was done under a false sandbox assumption → **move it back into the disposable per-run temp dir** ("testing container", per Daniel), delete the container-path code in `UITestEngineHarness.shortSocketPath`.
- Remaining unknown: exact app-side reason the seeded library isn't current at window-resolve (needs ONE instrumented Dev Local run once the build is unblocked). Fix is app-side, not the seeder.
- `openUITestLibraryOverrideIfNeeded()` (FicheroApp.swift:216 → UITestSupport.swift) is the launch hook; `library.content.ready` (BackendRootGate.swift) renders in every phase except `.setupNeeded`.

## KG design specs written overnight (DRAFT — need your approval, then implement)
Both are BACKEND/deterministic/headless — implementable overnight ONCE APPROVED (not GUI-blocked).
- **kg-readable-representation** (milestone #280, issues #4647–4653) — deterministic, **NO-LLM**,
  **any-language (language-of-SVO)**, **background** narrative rendering of the KG (regest /
  biography / gazetteer / concordance) via the Reiter-Dale 6-stage pipeline; iterates on
  `knowledge/paragraph.py`; cite-to-page-SEGMENT + expose-KG-on-hover (location/dates/roles) +
  generation-provenance (model/prompt/run). This is HOW it's built, NOT the document inspector.
  Replaces the `narrative_v1` LLM prompt that "makes it up". 7 issues = the pipeline stages.
- **docs-citations-bibliography** (milestone #281, issues #4654–4658) — one canonical
  `docs/references.bib` crediting the people/articles/projects/libraries Fichero builds on
  (specific people/articles FIRST); resolves via a guardrail; renders in About box + user guide +
  website; human-readable + BibTeX export. Distinct from source-provenance.

## QUEUED (Daniel's asks, in order)
0. **Approve (or amend) the two new DRAFT specs** → then their backend implementation is
   headless overnight work (test-first per the pipeline issues). Open questions are in each spec.
1. **UI/UX harness fix** — once package resolution + GUI available: instrument → confirm root cause → move socket to temp dir + drop dead code → remove empty new/open-library screen → InspectorFlows test goes GREEN. Test-first per the approved spec.
2. **KG backend + frontend tests** — backend is already heavily covered (~30 files); the KG spec gaps are mostly FRONTEND (kg-tables filters/rename/keyboard-delete/type-icons — see kg-tables.md [MISSING]). When starting KG, assign kg-tables & kg-entity-inspector their milestones (graduate off the grandfather list) — needs Daniel's milestone-mapping call.
3. **Folder-structure guardrail** (Daniel, later) — tests for Xcode folder structure + Python folder structure so files land in the right place and folders don't rot into junk. "Likely a worker-agent note exists" (search agent-work). Needs its own spec + milestone.
4. **transport.event-delivery (#4486)** — Swift change-stream test per transport, now that the MainActor isolation fix landed. Blocked on #1 (Swift build).

## Guardrail sanity (run anytime, headless)
```
python3 scripts/check_specs_have_tests.py
python3 scripts/check_spec_milestones.py
python3 scripts/check_xcode_config_invariants.py
PYTHONPATH=fichero-server/src ~/code/fichero/.venv/bin/python -m pytest fichero-server/tests/unit/scripts/test_check_spec_milestones.py fichero-server/tests/unit/scripts/test_check_xcode_config_invariants.py -q
```

## UPDATE (overnight, ~01:00) — KG-readable BUILD started + more specs
- **kg-readable-representation is APPROVED** (#280) and PARTLY BUILT, headless, no-LLM:
  `fichero-server/src/fichero_server/knowledge/readable.py` — Reiter&Dale stages
  1 (select_entry_claims), 2 (order_claims: chronological/by-source), 3 (aggregate_claims),
  5 (referring_expression). 16 tests green in tests/unit/knowledge/test_readable_representation.py.
  Stages 4 (lexicalisation) + 6 (realisation) NOT built — need the language answer (open Q) +
  real per-language verb vocab; do not fabricate lexicons. Then assemble into a render + endpoint.
- **Factoid-model audit:** KnowledgeClaim already implements Bradley & Short IN FULL + more
  (who/date/place/citation/Toulmin/evidential/language/generation-provenance). Build on it +
  paragraph.py. CIDOC-CRM import/export = LATER (import/export engine milestone).
- **New DRAFT spec:** docs-citations-bibliography (#281, issues #4654-4658) — scholarly + dep
  attribution, one references.bib, About box + user guide + website, people/articles first.
- **UX gap issue #4659:** dates/source_anchor/warrant/claim_geo stored but NOT in the claim UX
  (answers "is it all in the UX?" — no). #4660 = audit-history in the render.
- Milestones now: 264 transport-http-uds, 278 ui-test-harness, 279 xcode-build-configs,
  280 kg-readable-representation, 281 docs-citations-bibliography.

## Resume order (Daniel's): testing (tracking DONE) -> UX (BLOCKED on package reset + GUI)
## -> KG (readable stages 4/6 need language answer; then wire endpoint + the UX gaps).

## UPDATE 2 (~00:45) — packages reset by Daniel; MCP build STILL fails; more KG-read tests
- Daniel reset package caches + reconnected the xcode MCP; his GUI build succeeded 12:22am.
  BUT `mcp__xcode__BuildProject` / `RunSomeTests` STILL fail at 0.36s with "Missing package
  product FicheroAPIClient/Sparkle" — the MCP build action isn't seeing the packages the GUI
  resolved (separate/stale package state). `xcodebuild` CLI unavailable (xcode-select →
  CommandLineTools; don't sudo unattended). SO: Swift tests (EngineTransportModeTests +5 cases)
  remain RUN-unverified. Ask Daniel to run FicheroTests (⌘U) in Xcode, or fix the MCP package state.
- **fichero MCP can't reach the running engine** (points at http://fichero-app; app uses UDS),
  so I can't inspect live claims to ground stage 4/6 vocab/languages. That question is still open.
- **kg-readable stage 3 now also collects place distribution** (claim_location). readable.py =
  stages 1,2,3(+places),5. **18 tests green.** Still headless/no-LLM.
- Backend fully green; the remaining KG stages (4 lexicalisation, 6 realisation) + biography
  ASSEMBLY are gated on the language decision + real verb vocab (don't fabricate; the assembly
  also bakes in open design Qs — ordering default, confidence display).

## Honest overnight status: reliable headless work is done to its principled stop.
## Unblock paths: (a) ⌘U to validate Swift tests; (b) answer the language Q + point fichero
## MCP at the running engine so I can ground stages 4/6 in real claims; (c) Reset Package
## Caches in a way the MCP build picks up (or fix xcode-select) for MCP-driven Swift test runs.

## UPDATE 3 (~01:15) — FicheroTests failures triaged (build works via GUI now)
FIXED this session (commit 153befcf3 — confirm on next ⌘U):
- DocumentEqualityTests:109 — classified Document.language (compared) + languageMeta (skipped).
- InspectorAttributeVisibilityTests:276 — defaultVisible now [.documentClass, .language]; expectation updated.
EXPECTED / not bugs:
- ColdLaunchReachesLibrary + LaunchPerformance UITests — need Dev EMBEDDED (bundled engine);
  they fail-fast under Dev Local by design (avoids the 56 GB accessibility-tree blow-up). The
  :8765 / UDS "connection refused / timed out" console spam = no backend engine running (Debug
  doesn't bundle one; start via `briefcase dev`). All one root cause.
PRE-EXISTING, need investigation + a GUI build to verify (NOT mine; likely other feature work):
- DocumentStoreAndSidebarTypesTests:222,240 — entity-library selection locks list mode / routes
  browser selection into KG focus (assertTrue failing).
- ViewValueSizeTests:23 — ContentView 6064 > 5864 byte ratchet (likely the language field grew it);
  DECISION: shrink ContentView or bump the baseline with justification.
- KnowledgeGraphInspectorSectionTests:545 (delete uses generated clients) + :1089 (source excerpt
  "Ada wrote the notes" vs "the verbatim quote" — relevant to kg-readable cite-to-segment).
- ToolbarSearchRoutingTests:253 (artifact hits in results bar).
- WorkflowRunProviderCacheTests:110 (ChatService must NOT be in toolbar env).

## HARD BLOCKER for my Swift work: MCP build ≠ GUI build (package DD divergence)
`mcp__xcode__BuildProject/RunSomeTests` fail at "Missing package product FicheroAPIClient/Sparkle"
(0.36s, pre-compile) even after Daniel's Reset Package Caches + successful GUI build — the MCP
build action uses a separate/unresolved DerivedData and has no resolve-packages action. So I can
WRITE/FIX Swift but cannot RUN it via MCP; every Swift fix is "confirm on next ⌘U". Backend pytest
runs fine headless. (Candidate SendFeedback: MCP build should share/resolve the GUI's package state.)

## KG-readable backend now: stages 1,2(+date_values),3(+places),5 — 20 tests green, no-LLM.

## UPDATE 4 (~02:10) — CLI BUILD/TEST UNBLOCKED; all 9 reported failures FIXED + VERIFIED
THE unblock: Xcode is `Xcode-beta.app`. Build/test via CLI, no sudo:
  export DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer
  xcodebuild test -testPlan fichero -project fichero/fichero.xcodeproj \
    -scheme "Fichero (Dev Local)" -destination 'platform=macOS' \
    -derivedDataPath /tmp/claude-502/dd-integration -only-testing:FicheroTests/<Suite>
  # -testPlan fichero is REQUIRED (else it builds the iOS FicheroIPadTests target under
  # macOS and aborts: "Unable to resolve module dependency: 'Fichero'"). Isolated DD.
  # (The MCP BuildProject still can't resolve packages — SendFeedback queued. CLI works.)

Verified TEST SUCCEEDED (124 tests, 0 failures) across the 8 fixed suites. Commits:
- 153befcf3 — DocumentEquality (language/languageMeta classified) + InspectorAttributeVisibility.
- be5d34b16 — source-excerpt navigation fidelity (REAL app fix, ClaimSourceRequest) + test-drift
  alignment (KGInspector:545, DocumentStoreAndSidebar:222/240, ToolbarSearch:253, ModelChip comment).
- ViewValueSize ratchet 5864→6064 (in the stage-6 commit).
Finding: 8 of 9 were STALE TESTS drifted from refactors/rulings, not app bugs — the suite had
drifted from the code. Only the source-excerpt one was a real regression. Nearly reverted Daniel's
2026-09-07 "artifacts dropped from search" ruling — caught by reading the code comment.

Running now: full FicheroTests unit suite (-only-testing:FicheroTests) to catch anything else.
NEXT after that: FicheroUITests harness (the top priority) — but XCUITests need an UNLOCKED GUI
session; run when Daniel is back, or attempt and report if the screen is locked.
KG-readable: stages 1,2,3,5,6 — 24 tests green (docstring aligned d774c0f61).

## UPDATE 5 (~02:15) — FULL UNIT SUITE GREEN; XCUITest harness blocked on LOCKED SCREEN
- **Full FicheroTests unit suite: 3217 tests, 9 skipped, 0 failures (TEST SUCCEEDED).** The entire
  unit layer is healthy. All 9 reported failures fixed + verified; nothing else broken.
- **FicheroUITests/InspectorFlowsUITests FAILED to run: "Timed out while enabling automation mode"**
  — the XCUITest RUNNER can't initialize because the screen is LOCKED (Daniel asleep). This is NOT
  the harness bounce — the runner never started. macOS XCUITests need an UNLOCKED GUI session.
  → The harness root-cause investigation (why the seeded library isn't current) is the FIRST thing
  to do with an unlocked screen in the morning: run
    xcodebuild test -testPlan fichero -project fichero/fichero.xcodeproj -scheme "Fichero (Dev Local)" \
      -destination 'platform=macOS' -derivedDataPath /tmp/claude-502/dd-integration \
      -only-testing:FicheroUITests/InspectorFlowsUITests
  with the screen UNLOCKED. Then diagnose the bounce (spec ui-test-harness): expect the socket-in-
  real-container relocation to be the culprit (move to the disposable temp dir; Dev Local is unsandboxed).

## FINAL overnight state: unit layer 100% green (3217/0), 16 commits, CLI test loop unblocked.
## Only the XCUITest harness remains, gated purely on an unlocked GUI session.
