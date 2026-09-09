# RESUME — design-led testing + spec/milestone/tag tracking (2026-09-09 overnight)

**claude-mem is OUT** (allowance exhausted since 13:15Z) — this file is the handoff instead of memory. Do NOT restart the mem worker.

Branch: `integration` worktree. Commits this session: `62d7851df`, `486fb09f0` (both local, NOT pushed).

## Done + VERIFIED (headless)
- **3 design-led specs**, all APPROVED, in `docs/contributor/specs/`:
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
