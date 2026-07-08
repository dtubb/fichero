# Durable Lessons Learned / Decisions

## Cross-platform SwiftUI gating: prefer `canImport(AppKit)` over `os(macOS)` when AppKit symbols are involved — 2026-06-18

During the iOS compile gate, several files still triggered `Unable to resolve module dependency: 'AppKit'` or unresolved AppKit symbol errors even after broad macOS gating work. The most robust pattern for files or modifiers that reference concrete AppKit APIs (`AppKit`, `NSApplication`, `NSSavePanel`, `NSMenuItem`, `NSFindPanelAction`, `NSTextView`, `.onModifierKeysChanged`) is to gate those imports/blocks with `#if canImport(AppKit)` rather than only `#if os(macOS)`. This matches the existing `PlatformAliases` strategy and avoids mixed-platform type-checking surprises while iOS/visionOS targets are being brought up.

## Xcode indexing can surface stale pre-edit diagnostics during platform-gate work — 2026-06-18

When Xcode is still indexing or typechecking, the errors list may continue to show line/column diagnostics for code that has already been fixed on disk (for example `Text + Text` deprecations or imported-type `Identifiable` warnings after adding `@retroactive`). Before chasing a repeated iOS/macOS gate error, verify the current file contents on disk. If the source is already updated, treat the diagnostic as stale until a fresh build/clean pass reruns that file.

## OCR geometry must be provider-normalized, not Apple-specific — 2026-06-14

Apple Vision now has deterministic OCR line/word geometry, but VLMs and cloud/local OCR APIs should feed the same typed contract rather than each inventing bbox shapes. Future OCR/transcription geometry work should define one Pydantic result model for page/line/word boxes, then write adapters for Apple Vision, prompted VLM JSON (Qwen/Gemini/GPT/Claude), Google Vision/Document AI, AWS Textract, optional Azure, and local Python OCR/layout tools. Cloud OCR adapters must be blocked by local-only/no-cloud policy unless explicit consent allows upload; tests should use fixtures only.

## Guardrails should scan synthetic architecture failure modes directly — 2026-06-14

For recurring backend data-loss or reactivity bugs, prefer small AST guardrails plus synthetic unit fixtures over one-time manual review. Recent examples: Pydantic persistence writes that vanish on `model_dump()`, Swift `additionalProperties` misuse for OpenAPI-typed fields, and non-route observable `save()` calls without nearby `emit_change()`. Keep scanners high-signal with explicit allow comments/baselines and run them through `verify_all` via `scripts/check_*.py`.

## Codex worker model ladder for manager lanes — 2026-06-10

For Fichero manager dispatch, use tmux-based Codex workers in external worktrees under `~/code/fichero-worktrees/<name>` and prefer `gpt-5.3-codex-spark` for most issue-scoped workers. Escalate only when needed: `gpt-5.4-mini` if Spark struggles, `gpt-5.4` for complex keystones, and `gpt-5.5` only for truly hard/high-blast work. Prompts should tell workers to use jcodemunch first, claim issues before coding, continue within the same milestone until context fills only when file sets remain disjoint, and report verification/commit SHA before manager integration.

## SwiftUI storage image display must be keyed by document identity — 2026-06-06

Imported image pages should render through storage endpoints (`/api/storage/thumbnail/{id}` and `/api/storage/display/{id}`), not image-edit preview endpoints. SwiftUI lazy grids/lists must key async image loads by `(document_id, image_type)`; a plain `.task` can leave stale placeholders or images when cells are reused even though the backend returned real JPEG bytes. Keep Library/List, Document Canvas, Reading/WebKit, and Inspector as independently toggled panes. Folder/group selection should render a canvas container placeholder, while selected image/PDF page children still win.

## Marshall import workflow should be staged, not hidden behind Catalogue — 2026-06-05

For IIIF/W3C imports, preserve the existing `Catalogue` workflow and add new staged workflows/chains beside it. The desired contract is explicit user-reviewable layers: imported transcript artifacts, imported W3C entities, additional extractor-generated entities, reversible page/folder entity cleanup, SVO/KVO claims, ontological KG, then catalogue/narrative outputs. Do not hide missing stages with SwiftUI fallbacks; backend persists each layer, SwiftUI displays/reviews it through typed/generated API clients.

## W3C entity annotations need importer-level canonical entity persistence — 2026-06-05

Marshall W3C annotation files can already carry entity annotations. The standalone `~/code/marshall_diaries/build_manifest.py` converter should emit canonical page `entities[]` from those annotation bodies so `fichero import-iiif` creates page-scoped `KnowledgeEntity` rows before any workflow runs. This preserves import provenance separately from later spaCy/Apple/LLM extraction and lets entity cleanup compare imported vs extracted layers.

## Workflow scale testing must advance 5 → 10 → 20 with progress evidence — 2026-06-05

Marshall smoke testing showed 5-page and 10-page IIIF/W3C imports plus Catalogue can finish green, but 20 pages exposed a long `Extract All Entities` progress/checkpoint visibility failure where claims and folder catalogue artifacts were not produced. Do not scale to the full corpus until 20-page workflow progress, terminal status, and KG write completion are reliable and observable.

## viewDisplayMode toolbar sync — reverse direction was missing — 2026-06-01

`viewDisplayMode` (@SceneStorage) drives `LibraryView.displayMode` directly, but mutations to `viewDisplayMode` from the toolbar picker were NOT propagated back to `viewSettings.libraryLayout`. The `handleLibraryLayoutChange` → `viewDisplayMode` path existed (View menu → toolbar); the reverse (toolbar → View menu) didn't. Pattern: any time you add a `Picker` bound to `@SceneStorage`, check whether the OTHER direction needs an `onChange` handler too.

## @ToolbarContentBuilder escapes the SwiftUI type-checker budget — 2026-06-01

`ContentView.swift` is deliberately split across `navigationSplitColumn` + `decoratedNavigationSplitColumn` to stay within Swift's view-chain complexity limit. Adding any generic type (e.g. `Label<Text, Image>`) to those view bodies pushes them over budget. Use `@ToolbarContentBuilder` functions instead — they use a different type resolver with no budget limit. Already used for `ToolbarItem(.principal)` (#323); confirmed for segmented `Picker` in navigation group (#1215).

## Shared graph-RAG engine now spans Chat + Researcher — 2026-05-31

`fichero.retrieval.graph_rag.GraphAwareRetriever` is now the common retrieval path for chat (`/api/chat`) and researcher workflow search (`workflows/tools/sources.py::search_tool`). Keep future retrieval changes centralized there to avoid divergence in ranking, KG augmentation, and telemetry behavior.

## Retrieval telemetry contract for manager/QA visibility — 2026-05-31

Chat and researcher retrieval flows now emit comparable diagnostics:
- Chat response: `kg_claims_used`, `kg_entities_used`, `document_count`, `context_count`
- Research search tool output: same KG fields plus `document_count` + `context_count` (with legacy `count` retained)
Structured logs (`chat_retrieval`, `research_search`) carry graph knobs and counts; use these markers for runtime verification before blaming model quality.

## Public vs full MCP surface split — 2026-05-30

For external agents, keep a small stable MCP contract in `fichero/mcp_public.py` (typed request/response models, narrow tool list). Put broader app-control and spatial tooling in a separate `fichero/mcp_full.py` surface. This avoids coupling third-party agents to internal tool churn while still enabling full-capability local agents.

## Mind Palace scene_render contract is wire-stable before native renderer — 2026-05-30

`POST /api/mindpalace/render` now provides a stable response shape (`png_base64`, optional `mp4_base64`, metadata) even while backend rendering is placeholder-grade. Keep the API contract stable so multimodal agent loops (render → act → re-render) can be tested now; swap in RealityKit/native rendering behind the same schema later.

## NSTrackingArea owner mouseMoved must be @objc, not override — 2026-05-25

When `NSObject` (not `NSResponder`) owns a tracking area, AppKit delivers mouse events via Objective-C informal protocol — the owner just needs an `@objc func mouseMoved(with event: NSEvent)` method. Using `override` is a compile error since `NSObject` doesn't declare `mouseMoved`. Pattern used in `PDFPageView.Coordinator` for PDF loupe cursor tracking.

## Shared AppStorage keys auto-sync across separate SwiftUI views — 2026-05-25

Two views with `@AppStorage("same.key")` in separate structs (e.g. `PDFPageView` and `PDFPageWithToolbar`) share the same underlying UserDefaults value and stay in sync automatically. Use this pattern to avoid threading state manually when both a rendering view and its toolbar wrapper need to read the same persistent setting.

## Subagent-driven development: two-stage review (spec + quality) — 2026-05-25

When executing implementation plans via superpowers:subagent-driven-development, the two-stage review pattern (spec compliance reviewer → code quality reviewer) is highly effective for catching both requirement gaps and quality issues before code quality review. Implementer may report DONE prematurely; spec reviewer catches missing code. If spec reviewer checks before implementer has applied edits, the check will report gaps — re-dispatch the same spec reviewer after implementer completes the fixes. Moved implementer to Task 2 (cursor tracking) after both reviews passed Task 1 (loupe state management in PDFPageView).

## Backend lane verification stays targeted; manager owns the full gate — 2026-05-25

For backend lane work on `codex`, run only the targeted ruff pass on changed backend files plus the single regression test for the issue being touched. The manager owns the authoritative serial `verify_python.sh` + full suite at merge/post-merge, so repeating the full gate in the lane creates DuckDB single-writer contention without adding signal. Keep backend commits small and issue-scoped.

## KG paragraph rendering should be SVO-first, citation-preserving, and deterministic — 2026-05-25

When composing KG prose for any surface, prefer structured claim fields (`subject_canonical` / `predicate_verb` / `object_phrase` or SVO aliases) over legacy `text`, and preserve source provenance on every citation marker (`source_document_id`, `source_page_label`, `source_excerpt`, `source_char_start/end`, `source_bbox`). If consecutive claims share the same subject and verb, fold them into a single sentence instead of emitting repeated subjects. This keeps the renderer deterministic while still round-tripping exact source metadata for downstream arrows, footnotes, and inspectors.

## Digest route tests must override the exact dependency path — 2026-05-25

When a route uses a dependency wrapper around `get_library_database`, positive tests can accidentally pass through same-thread `db_manager` cache reuse instead of the intended isolated fixture path. Prefer either reusing `get_library_database` directly or registering the exact wrapper in the test fixture's `dependency_overrides` so the test client exercises the same dependency chain as production.

## xcodeproj 1.27.0 needs a monkey-patch for Xcode 16+ projects — 2026-05-25

xcodeproj 1.27.0 raises `RuntimeError: Type checking error: got 'Array'` when opening any Xcode 16+ project because those projects store `shellScript` as an Array. Fix: monkey-patch `Xcodeproj::Project::Object::AbstractObjectAttribute#validate_value` to warn instead of raise when `type == :simple` and the value class is unexpected. This patch is already baked into `scripts/add-swift-file.rb`. Also: when calling the script with `fichero/fichero/Views/...`, the script now strips the outer `fichero/` prefix so it navigates the existing group tree instead of creating a duplicate `fichero > fichero` hierarchy.

## Batch SwiftLint cleanup in small groups, not single-file gates — 2026-05-25

For warning-only cleanup work, 5-10 small fixes per `bash scripts/verify_all.sh` run is the right cadence. It keeps feedback tight without wasting a full Xcode/Python gate on every single line wrap or comment conversion.

## Never overlap `xcodebuild` gate runs in the same build tree — 2026-05-25

The Xcode build database under `fichero/build/xcode/Intermediates/XCBuildData/` locks if two `xcodebuild test` processes share the same workspace. If a gate fails with `database is locked`, check for stray `xcodebuild` processes and kill the overlap before rerunning. This is a tooling issue, not necessarily a code regression.

## Codex skill discovery needs `SKILL.md`; Claude plugin-qualified skills can use `skill.md` — 2026-05-22

Claude's plugin marketplace can expose skills like `/fs_session:bug` from `plugins/fs_session/skills/bug/skill.md`, but Codex's local skill loader expects `~/.codex/skills/<name>/SKILL.md`. If a skill exists in `fichero-skills` but is missing from Codex's session skill list, install a symlink under `~/.codex/skills/<name>/SKILL.md` pointing at the canonical plugin skill. Added symlinks for `bug`, `feature`, `feature-future`, `autonomous-loop`, and `extract-bib`. A Codex restart is required for automatic trigger discovery; within an existing session, read the skill file manually and follow it.

## Autoloop pi workers need explicit skill loading — 2026-05-22

`agent-autonomous-loop.py --agent pi` does not honor Claude-style `--plugin-dir` skill loading. To make `/fs_autoloop:session-worker` execute as a real skill instead of prose, launch pi workers with `--only-skills --allow-skill /fs_autoloop:session-worker`. Also pass `--skip-end-phase`; otherwise the runner may invoke its default `/session-end` after the worker path and burn context reading broad project history. `cascade_loop.py` dry-runs should use a copied queue and advance simulated statuses, or diagnostics misleadingly reprocess the first pending item forever.

## Migrated from trace-mcp to jcodemunch — 2026-05-17

Code-intelligence MCP server replaced. **Why:** trace-mcp's `search` returned zero results on the parent monorepo index despite 246k indexed symbols — a real upstream bug, not a configuration issue (CLI worked, MCP didn't). Migrated to `jcodemunch-mcp` (`pipx install`, `uvx jcodemunch-mcp init`). Tool-name mapping: `search` → `search_symbols`, `get_outline` → `get_file_outline`, `get_symbol` → `get_symbol_source`, `find_usages` → `find_references`, `get_change_impact` → `get_blast_radius`. Same tree-sitter approach, same persistence model, ~95% token savings vs Read/Grep. Backups of trace-mcp state preserved at `/tmp/trace-mcp-*` (30d TTL). Worker's `minimal-mcp.json` now points at jcodemunch — if you re-enable trace-mcp later, restore that file too.

## Briefcase build/ dirs must be in .gitignore AND code-index ignore — 2026-05-17

`fichero-engine/build/` (1.4GB) and `fichero/build/` (4.7GB) contain bundled `Python.framework`, embedded `app_packages/`, and Xcode XCBuildData — all regenerable, but if they leak into the code-index they (a) blow past file-count limits (jcodemunch defaults to 10k), (b) trigger "Sensitive file blocked" warnings per file (briefcase bundles litellm secret managers, etc.), and (c) destroy search relevance with bundled-Python symbol pollution. Pre-emptively delete before re-indexing if briefcase has run recently; ensure `.gitignore` + project-level `.traceignore` / equivalent both list `build/` and `dist/`. Added `fichero-engine/.gitignore` + `.traceignore` covering both. The macOS app's Resources/app_packages/ ARE bundled python — don't confuse them for source.

## .venv symlink rot — diagnose before "fix" — 2026-05-17

A `.venv/` that exists and activates does NOT mean it works. The symbol `.venv` at the project root can be a symlink into another worktree's venv (e.g. `../fichero/fichero-api/.briefcase-venv`). Check `ls -la .venv` and `.venv/bin/python -c "import sys; print(sys.executable, sys.prefix)"` — if the prefix points outside this project, every `pip install` and pytest run targets the wrong site-packages. Briefcase venvs are for packaging, not development — never alias `.venv` to a briefcase venv. Canonical rebuild: `~/code/fichero-0.0.2/scripts/venv-sync.sh`. Worker iter-1's pytest failure (#840 work) was 100% environment rot, not bad code — its `catalogue.py` edits passed 72/72 tests once the venv was rebuilt.

## When MCP `search` returns zero, fall through immediately — 2026-05-17

Confirmed in worker iter-1: when `mcp__<tool>__search` returns `items: [], total: 0` for a symbol you know exists, don't keep retrying with different query terms (cost ramps, signal stays zero). Fall through to: `search_text` (FTS regex on file content), `get_outline` on the known directory, then `get_file_outline` on a guessed path. The worker recovered #840 via this exact chain after the curator's `workflows/nodes/catalogue.py` path guess was wrong (real path: `workflows/tools/catalogue.py`). Curator's `files: [...]` in queue.md is a HINT, not ground truth — worker must verify.

## No-migration window for 0.0.x — 2026-05-16

The 0.0.x window has no users; libraries can be nuked + recreated freely. Schema changes go directly into `db.py` CREATE TABLE; do NOT write `db_migrations.py` migrations for new fields. Once 0.1.0 ships, the schema locks and migrations become mandatory. This simplifies new-field work (e.g. SVO attribution, claim attribution taxonomy): just add Pydantic field + base CREATE TABLE column.

## Database.save() must be a real upsert, not INSERT OR REPLACE — 2026-05-16

DuckDB documents `INSERT OR REPLACE INTO` but does NOT implement it as a reliable PK upsert (unlike SQLite). Under the column-store append path — especially against tables that gained columns mid-flight via `ADD COLUMN` migrations — it raises `Constraint Error: PRIMARY KEY violation` which escalates to `INTERNAL Error: Failed to append to PRIMARY_…_0`, a `FatalException` that tears down the whole uvicorn process (#1120 crash). Use native `INSERT … VALUES … ON CONFLICT (id) DO UPDATE SET col = EXCLUDED.col, …`. Key-only tables degenerate to `ON CONFLICT (id) DO NOTHING`. The typed `Database.save(model)` layer wraps this so callers stay clean.

## initialize_token() must be idempotent — 2026-05-16

`api/auth.py::initialize_token` runs at module import time. pytest's `TestClient(app)` re-imports the app, which re-runs `initialize_token`. If it rotates the token on every call, concurrent processes (live uvicorn + pytest + a second uvicorn) clobber each other's `.api-key` and start returning 401s to the legitimate client. Default behaviour: reuse the existing on-disk token if present. Opt-in rotation via `force_rotate=True` or `FICHERO_FORCE_ROTATE_AUTH=1` when "stale token after crash" hardening is needed. (#1110)

## Container fallback in workflow tools — 2026-05-16

`_resolve_container_doc()` returns None for selections that don't include a folder/group. Four call sites (`extract_all.py`, `extractors.py`, `catalogue.py`, `cleanup.py`) gated KG persistence + artifact saves on `if container and library_path:` — so single-file selections (md / txt / jpg / individual PDF) silently skipped all writes including the LLM call's output (#1087, #1105). New `_resolve_write_target()` helper (catalogue.py) prefers folder container, falls back to the first selected doc. Catalogue's LLM call now short-circuits BEFORE the expensive work if no target resolves at all. The folder-preference contract of `_resolve_container_doc` is unchanged; the fallback is a layer above it.

## SVO via LLM-noun-phrase + heuristic verb/object split — 2026-05-16

Apple Intelligence and other constrained-output LLMs don't reliably populate strict verb/object fields when added to the structured-output schema. The hybrid approach (#1113): LLM extracts noun phrases + descriptions; deterministic heuristic in `_synthesize_svo_fallback()` splits "X: Y" / "X — Y" forms into subject/verb/object; typed default ("X is a {entity_type}.") fills bare keywords. Provider attribution must be honest: when the heuristic ran, suffix the model name with `+heuristic-svo` (e.g. `apple-intelligence+heuristic-svo`, confidence 0.5). When the LLM supplied SVO directly (e.g. gpt-4o-mini), no suffix, confidence 0.7. Users see the difference per claim in `KnowledgeClaim.model`.

## Hermeneutics and KG are separate epistemic layers — 2026-05-16

KG (`api/routes/entities.py`, `claims.py`, `kg_*.py`) = ontological / fact layer. What the document asserts: entities, claims, relations, sources. Predicates are about the world ("X is_located_in Y"). Hermeneutics (`api/routes/hermeneutics.py`) = interpretive layer. How we read what's asserted: frameworks, interpretations, readings, contested glosses. Predicates are about interpretive moves ("Reading A centers women's labor"). Needs its own controlled vocabulary distinct from KG verbs (#1124). Hermeneutic objects reference KG primitives by id (`claim_ids`, `entity_ids`) — bidirectional but not folded into one model. The Wave 1 fold attempt broke 15 existing hermeneutics tests via shape drift; deferred to #1126 to redo properly with the existing test contract preserved.

## Subagent cost vs context-protection tradeoff — 2026-05-16

Manager pattern (orchestrator dispatches per-task subagents) uses MORE total tokens than inline work — each subagent reloads project context (~15-20k tokens) and writes its own transcript. But it protects the orchestrator's context, which is the binding constraint for multi-wave work. The right metric isn't tokens-per-task; it's useful-commits-per-credit. Subagents that ship a commit pay their way; subagents that explore-and-report waste their cost. Always tell subagents to "execute, don't plan" unless you explicitly want a design doc. Run subagents on **sonnet** (~5× cheaper than opus), orchestrator on opus for judgment. When orchestrator context hits 200%+, /session-end is cheaper than continuing.

## Agent docs: dedupe and point to live sources, don't inventory — 2026-05-24

`CLAUDE.md` (project + `.claude/` + global), `AGENTS.md`, and `docs/CLAUDE.md` overlap heavily; guidance copied between them rots and double-loads context. Rules that held during the cleanup: (1) State the jCodemunch policy in ONE place and point to it — don't restate it per file. (2) Never assert "100% SwiftUI / NO AppKit" — the app intentionally ships ~8 `NSViewRepresentable` bridges (PDFKit, magnifier, scroll-zoom, Quick Look, text editors) + an `NSEvent` swipe monitor; the doc said the opposite. (3) Don't hand-maintain tool catalogues or file-count stats — they drift; point to the live tool list / `find`. (4) `bash scripts/verify_all.sh` is the canonical gate (= ⌘U); OpenAPI sync (`sync_openapi_schema.sh`) is a SEPARATE step the gate only *checks*, never runs. Pre-GitHub planning docs now live in `docs/archive/`; GitHub Issues is the canonical backlog.

## Fichero verification gate is sensitive to live DuckDB locks — 2026-05-24

`bash scripts/verify_python.sh` runs ruff, backend unit tests, the GET-contract walk, a backend start-smoke, CLI import/help smoke, and the live CLI<->engine contract test. It will fail if another local `uvicorn` or test process is already holding the temp DuckDB database lock used by the suite. Before rerunning a failed gate, stop the background backend process and confirm no stale Python server is still attached to the temp database.

## Page-content edit state tests live in `InspectorLayoutTests.swift` — 2026-05-24

The `PageContentPaneEditState` helper now has focused regression coverage in `fichero-tests/InspectorLayoutTests.swift`. The tests verify draft seeding, save-on-blur behavior, and that backend refreshes do not overwrite an active edit. Keep future page-content changes aligned with those state transitions instead of testing the SwiftUI view by rendering alone.

## FastAPI tag double-count via APIRouter + include_router collision — 2026-05-12

If an `APIRouter` is constructed with `tags=["foo"]` AND main.py's `include_router(router, tags=["foo"])` also passes the same tag, FastAPI appends both to every operation. The OpenAPI export then lists each route's tags as `["foo", "foo"]`. Any tag-grouped tooling (export scripts, UI tag pickers) double-counts the endpoint.

**Fix**: keep tags on ONE side only. In Fichero, the canonical source is `main.py`'s `_DEV_ROUTE_SPECS` tuple — `(router, prefix, tags)`. New routers should construct `APIRouter(prefix=...)` without tags. The tag-doubling was a real bug that landed Sat night during the KG concept blast and got fixed at `029d91d3`.

## Concept-overlap policy — canonical route owns the surface — 2026-05-12

When old + new routers expose the same concept (e.g. `/api/interpretations` + `/api/hermeneutics/interpretations` + `/api/kg/interpretations`), the new KG-namespaced route is the canonical home. Old routes are deprecated then removed once Swift services migrate. Take richer endpoints from the old surfaces (e.g. hermeneutics' PatternInstance / Framework taxonomy lookup) and merge into the canonical route — don't keep multiple code paths doing similar things.

Pairs to consolidate:
- Interpretations: 3 routers → `/api/kg/interpretations`
- Notes: `/api/notes` (new Zettelkasten) vs mind-palace/notes (spatial) vs research/notes — canonical is `/api/notes`; mind-palace stays for spatial placement; research stays for checklists
- Projects: `/api/projects` (new) vs research/projects — canonical is `/api/projects`
- Graph traversal: `/api/kg/graph` (new) vs old `/api/graph/*` — canonical is `/api/kg/graph`; pull pathfinding helpers forward
- Predictions: `/api/kg/pykeen` (new, trained model) vs `/api/predictions` (legacy heuristic) — keep both, name them clearly

Tracked at #919 slice 5b.

## Pydantic v2 schema-required + before-validator pattern — 2026-05-12

To make a field required in the JSON schema (so grammar-constrained LLMs emit it) AND still gracefully parse legacy items that lack the field, use this two-step pattern:

```python
NEW_FIELD = Field(description="...")  # no default → required in schema

class MySection(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _fill_defaults(cls, data):
        if isinstance(data, dict):
            data.setdefault("new_field", "fallback")
        return data
    new_field: str = NEW_FIELD
```

Pydantic generates `"required": ["new_field"]` in the schema → fm-bridge / Apple Intelligence grammar forces emission. The before-validator fills the default in legacy dicts before validation runs, so `model_validate({"name": "Juan"})` still parses.

The straight-forward `Field(default=..., json_schema_extra={"required": True})` does NOT work — Pydantic puts the marker on the field but doesn't change the parent's required array, and grammar engines still treat it as optional.

Live evidence: Apple Intelligence on tubb2020shift Preface went from `[tentative/fact] source=""` to `[confirmed/fact] source="<verbatim quote>"` after the change. See #894.

## spaCy-as-pre-pass to LLM, not replacement — 2026-05-12

For NER in the catalogue extractor, run spaCy first (deterministic span detection) and feed the spans to the LLM as a "pre-detected mentions: use these as the canonical set" hint. The LLM still produces SVO predicate, epistemic_status, claim_type — spaCy owns "where in the text is a name", LLM owns "what is the predicate / how firmly is it asserted."

This split:
- Catches parenthetical aliases at the span level (Davidson + [Deibinson] → one cluster) so the LLM doesn't emit 6 items for one name (#896 root cause).
- Cuts LLM token spend on the easy NER part — the on-device 4K window can focus on the hard parts.
- Falls through to LLM-only NER when spaCy fails (model not downloaded, language not supported, etc.) — the failure is logged but the catalogue keeps running.

Implementation: `fichero/kg/spacy_ner.py` provides `extract_entities(text, language?)` + `cluster_aliases(spans)`. Wired into `_run_extractor` in `extractors.py` for people / places / organizations / events sections only. See #899 Phase C.

## Pydantic defaults make fields optional in JSON schema → LLMs skip them — 2026-05-11

A `Field(default=...)` in a Pydantic v2 model is NOT in the JSON schema's `required` array. Grammar-constrained decoding (fm-bridge, Apple Intelligence, structured-output endpoints) treats those fields as skippable and the model backfills with the default — so the LLM never actually emits a value.

Symptom: Apple Intelligence returned `epistemic_status="tentative"`, `claim_type="fact"`, `source_text=""` on every item, because those were the defaults. SVO `verb` / `object` worked despite also having `default=""` only because the prompt reinforced them so heavily.

Options when adding new fields to extractor schemas:
1. Drop the default → fields become required → grammar forces emission. Breaks `model_validate` on any legacy artifact missing the field.
2. Keep default + `Field(json_schema_extra={"required": True})` — Pydantic v2 honors per-field overrides when generating the schema. Best of both worlds: graceful Pydantic parsing for synthetic items, strict schema for the LLM. (Note: a naive `{"x-required": True}` doesn't work — `required` lives on the parent object, not the field; only the explicit Pydantic v2 schema-extra override surfaces it.)
3. Strengthen the prompt only — least durable.

Tracked at #894.

## ClaimType vs EpistemicStatus — two-axis classification on KnowledgeClaim — 2026-05-11

`KnowledgeClaim` has two peer classification fields, easy to confuse:
- **`claim_type`** (ontological status) — what KIND of knowledge: `fact / analysis / interpretation / argument / historiography / theory`. Don't repurpose for "how firm".
- **`epistemic_status`** (epistemic status) — how firmly asserted: `tentative / confirmed / rejected`.

The KG inspector filter strips drive both axes independently via `@AppStorage("inspector.kg.hiddenEpistemic")` + `@AppStorage("inspector.kg.hiddenClaimTypes")`. Nil values fall back to model defaults ("tentative" / "fact") when filtering so an unclassified claim doesn't disappear.

## Latent enum-case mismatch hidden by incremental builds — 2026-05-11

`CurationStateBadge` was switching on `.approved` / `.pending` — cases that don't exist on the generated `ClaimCurationState` (which has `unreviewed / shortlisted / curated / rejected`). The enum was renamed in an earlier OpenAPI regen but Xcode's incremental build kept skipping the file, so the broken switch never recompiled.

Lesson: when an OpenAPI enum renames, grep the whole tree for old cases — incremental builds can't be trusted to surface dead matches. Better still: `mcp__xcode__XcodeListNavigatorIssues` after any schema change.

## AppleUnavailableError hierarchy — 2026-05-06/07

When Apple Intelligence raises a typed error from `_raise_from_bridge_stderr`, classify it as either:
- **AppleUnavailableError subclass** → triggers $large fallback in `chat_with_fallback` / `chat_structured_with_fallback`
- **bare RuntimeError** → caller retries / chunks in place (transient, not Apple-can't)

Subclasses today: `GuardrailViolationError` (safety), `UnsupportedLocaleError` (es-LatAm on es-ES-only model). Adding a new "Apple can't proceed" reason = new subclass + new bridge `kind` mapping. Don't catch GuardrailViolationError specifically anywhere — catch the base so future siblings auto-route.

## Apple Intelligence locale matrix evolves per macOS release — 2026-05-06

- macOS 15.1: en-US only
- macOS 15.2: + en-GB/AU/CA/IE/NZ/ZA/IN
- macOS 15.4: + Spanish-Spain, French, German, Italian, Japanese, Korean, simplified Chinese
- macOS 26+: broader

Even on a supported language, regional variant matters: es-ES ≠ es-LatAm. The model rejects out-of-set prompts with `unsupportedLanguageOrLocale`. Don't precheck locale to avoid the call — let it fire and route via the AppleUnavailableError fallback. The precheck function `apple_intelligence_supports_locale` exists but isn't used in production code today.

## ChatOpenRouter (langchain-openrouter 0.2.3) async hang — 2026-05-06

LangChain's late-2025 docs recommend `ChatOpenRouter` for OpenRouter routing, but its `ainvoke` hangs indefinitely on Claude Sonnet 4.6 calls. Direct `curl` to the same endpoint with the same model + key returns in <1s, isolating the bug to the SDK. Use `ChatOpenAI` + `base_url="https://openrouter.ai/api/v1"` instead. Documented in `get_langchain_model` as a known workaround.

## _compute_timeout is the single source of truth — 2026-05-07

Wall-clock timeouts on every LLM call path go through `_compute_timeout(config, kind, *, schema_chars=None)` with three kinds: `langchain`, `apple_chat`, `apple_structured`. Each scales by `config.timeout`, `max_tokens` (output_factor), and (apple_structured only) schema size (schema_factor). Don't add a fourth formula somewhere else.

## Reasoning routing is per-provider — 2026-05-07

`LLMConfig.reasoning_effort` ∈ {`off`, `low`, `medium`, `high`}. Each provider exposes the knob differently:
- anthropic native: `thinking={'type':'enabled', 'budget_tokens':N}` AND must force `temperature=1`
- openai (o-series): `reasoning_effort` kwarg directly
- openrouter: `extra_body={'reasoning':{'effort':...}}` (works for Claude AND gpt-5)
- apple intelligence: silently ignored (no reasoning surface)

Wired ON only for synthesis-style calls (catalogue narrative). Keep mechanical extraction OFF — pattern matching doesn't benefit and adds latency. Default OFF on LLMConfig.

## fm-bridge is canonical, apple-fm-sdk deferred — 2026-05-07

Decision: stay on the fm-bridge subprocess (`bin/fm-bridge/FmBridge.swift`) as the production Apple Intelligence path. apple-fm-sdk 0.1.1 requires Apple-flavored JSON Schema (additionalProperties + x-order keys) that Pydantic doesn't emit; migration would need a custom schema-format converter — not worth it until SDK 1.0. Don't add a second Apple path without explicit approval.

File rename: `main.swift` → `FmBridge.swift` to silence SourceKit's "@main attribute cannot be used in a module that contains top-level code" warning. Files named `main.swift` are interpreted as Swift scripts, which conflicts with @main.

## collect_usage() context-managed cost tracking — 2026-05-07

`fichero.llm.collect_usage()` is the contextvars-based primitive for capturing per-call LLM token usage:

```python
with collect_usage() as bucket:
    result = await tool_fn(inputs)
# bucket = list[dict[provider, model, kind, input_tokens, output_tokens, total_tokens, estimated]]
```

All four call paths (chat, chat_structured, apple chat, apple structured) push entries via `_record_usage` which logs at INFO and appends to the active collector. asyncio.Task inherits the active context so fan-out nodes' children's calls land in the parent's bucket.

Apple Intelligence entries are `estimated: True` (chars-based — Foundation Models' transcriptEntries surface needs verified API + Swift plumbing). LangChain entries with provider-reported `usage_metadata` are `estimated: False`.

Don't `logger.info("LLM usage ...")` directly anywhere — go through `_record_usage` so the contextvar collector picks it up.

## _pydantic_to_apple_schema fail-loud guarantee — 2026-05-07

The converter (`fichero/llm.py`) raises `ValueError` with a field-pointing message on unsupported shapes (discriminated unions, Literal/enum, JSON Schema format keywords, recursive types, malformed $ref). Don't silently emit partial schema trees — fm-bridge then raises an opaque "GenerationSchema init failed" downstream that's painful to diagnose. If a tool needs an unsupported shape, decompose into supported primitives or extend the converter.

## Calling Swift-only macOS frameworks from Python — 2026-04-28

Apple's newer macOS frameworks (Foundation Models / Apple Intelligence, Speech's SpeechAnalyzer, ImagePlayground, Translation, etc.) are **Swift-native**, not `@objc`-bridged. pyobjc can `loadBundle` and `lookUpClass` on them — instances exist — but calling their public methods raises `does not implement methodSignatureForSelector:`. The Objective-C runtime can't reach Swift-only entry points.

**The bridge pattern: tiny Swift CLI + subprocess.** Concretely:

1. Write a single-file Swift program (`@main` + `-parse-as-library`) that takes a JSON request on stdin and emits a JSON response on stdout.
2. Compile with `swiftc -O -parse-as-library -o bridge main.swift` — 2-second build, ~100 KB Mach-O.
3. Python `subprocess.create_subprocess_exec(...)` it; pipe JSON in, parse JSON out.
4. Surface structured error JSON via stderr so the caller can distinguish "framework unavailable on this device" from "generation failed."

Reference implementation: `fichero-api/bin/fm-bridge/` (Apple Intelligence). 90 LOC Swift, ~80 LOC Python wrapper in `llm.py:_apple_intelligence_chat`. Total round-trip ~150ms cold, ~50ms warm.

**Diagnostic for picking the bridge:**

```python
import objc
objc.loadBundle('FrameworkName', globals(),
                bundle_path='/System/Library/Frameworks/FrameworkName.framework')
cls = objc.lookUpClass('FrameworkName.SomeClass')
# Then try a known method:
try:
    cls.alloc().init().someMethod_(arg)
    # → works → use pyobjc directly (e.g. Vision.framework / VNRecognizeTextRequest)
except objc.NSObjectError:
    # → "does not implement methodSignatureForSelector" → Swift-only → subprocess bridge
```

**Why this matters for estimates**: I previously estimated Apple Intelligence integration at "3 weeks" assuming a Swift HTTP/IPC service. Reality was 2 hours of focused work because the subprocess pattern is dirt cheap once you know to reach for it. When estimating Swift-framework integrations, ask: "is the public API @objc-exposed or Swift-only?" — the answer dictates a 50× difference in effort.

## Audit existing infra before locking schema — 2026-04-28

When a feature plan calls for new tables or new Pydantic models, **grep the codebase for existing equivalents first**. A 30-minute audit can save 3-4 days of throwaway implementation.

Concrete example from this session: the typed entity storage plan (#728) was about to build six new entity tables (people, places, organizations, events, dates, keywords) plus a registry table from scratch. A 10-minute audit revealed `knowledge_models.py` already shipped `KnowledgeEntity` with an `EntityType` enum (person/location/organization/event/concept/other), `KnowledgeClaim` with full document/page provenance fields, `EntityMergeAudit` for dedup machinery, and `/api/entities` + `/api/claims` + `/api/graph_*` routes. The whole 0.2.x KG substrate was already built. The actual work was *connecting* catalogue extractors to the existing layer — a one-day refactor instead of a 7-10 day greenfield build.

**Practical heuristic before any non-trivial schema/model work:**
- `grep -rn "class.*Entity\|class.*Person\|class.*Document" src/ | grep -v __pycache__` — does someone already have this model?
- `ls api/routes/` — is there already a router that does this?
- `git log --diff-filter=A --name-only -- "*Models.py" "*models.py"` — was an architectural layer added that I'd be duplicating?

This belongs in the `writing-plans` skill checklist as a prerequisite step, not a nice-to-have.

## OpenAPI generates two enum types per Python enum — 2026-04-28

For a single Python enum used in both query params and response bodies, the swift-openapi-generator emits TWO Swift types — input and output. Same cases, different generated names.

Example with `EntityType` (knowledge_models.py):
- `Components.Schemas.FicheroKnowledgeModelsEntityType` — used in input/query params (`/api/entities?entity_type=person`).
- `Components.Schemas.EntityTypeOutput` — used in response bodies (`KnowledgeEntity.entity_type`).

If you see "cannot convert value of type 'EntityTypeOutput?' to expected argument type 'FicheroKnowledgeModelsEntityType?'" — that's why. Map between them in your Swift conversion layer; don't try to unify them in the OpenAPI spec.

## Swift main target uses traditional file references — 2026-04-28 (refresher)

The `fichero-swiftui` main target uses traditional PBXFileReference, not PBXFileSystemSynchronizedRootGroup. New `.swift` files don't auto-include — they need pbxproj edits OR appending to existing files in the target.

Practical pattern: append new content to an existing file in the same logical area. e.g. EntityServiceGenerated lives appended in `ArtifactServiceGenerated.swift`; KnowledgeGraphInspectorSection lives appended in `DocumentInspectorArtifactsTab.swift`. Splits into proper standalone files happen later when target membership patterns are revisited.

Confirmed via `grep -A 3 "PBXFileSystemSynchronizedRootGroup" *.xcodeproj/project.pbxproj` — only the test targets use sync groups.

## Pydantic + OpenAPI contract — three silent-failure shapes — 2026-04-28

The two-stack OpenAPI round-trip has three known failure modes that are all *silent* (no exception, no failing test, just data that disappears or filters that hide rows). All three are the same underlying shape: **schema and data drift apart**. Treat them as load-bearing rules.

## Activity API time filters must normalize ISO Z timestamps to naive UTC — 2026-05-23

`/api/activity` can receive `since/until` as ISO-8601 with `Z` (UTC). DuckDB filter queries in this codepath use naive datetimes; mixing aware+naive can surface as route-level 500s in live polling. Route layer should parse and normalize to **naive UTC** before building `ActivityFilter` (e.g. `dt.astimezone(timezone.utc).replace(tzinfo=None)`), and keep a unit test for `since=...Z`.

## xcodebuild scheme name is case-sensitive in this repo — 2026-05-23

The project scheme is `Fichero`, not `fichero`. Using lowercase scheme silently breaks build/test automation with "project does not contain a scheme named ...". Any scripts/autoloop checks should use `-scheme Fichero`.

**1. Pydantic field must be declared.** `extra="allow"` lets unknown keys *write* to the DB at runtime, but `model_dump()` only serializes declared fields, so the next read drops them. When adding a column, ship (a) the DB migration, (b) the Pydantic model field, (c) the OpenAPI request/response schema field — in the same commit. See `commit 31fc4141`, `feedback_pydantic_field_must_be_declared.md`, and the user-edit timestamp pattern at `MEMORY.md:79`.

**2. OpenAPI-typed fields, not `additionalProperties`, in Swift wrappers.** When a Swift `Services/*Generated.swift` wrapper builds a request body, every field declared in `openapi.json` must be set via the typed `Components.Schemas.*` field. Stuffing declared fields into `additionalProperties` compiles, round-trips through `extra="allow"`, and is then dropped by Pydantic — write lost, no error. See `docs/contributor/architecture/swiftui/api_client.md`.

**3. Endpoint filter defaults vs. seed-data drift.** A query-param default that strict-equality filters against rows (e.g. `folder_path: str = "/"`) silently hides data the moment seed JSONs gain a non-default value. Default filter params to `Optional[T] = None`; only WHERE-clause when the caller passes a value. **Whenever you change seed-data shape (default JSON resources, migration defaults, fixture rows), audit every endpoint that filters that field — and add a regression test that seeds a row outside the old default.** See #722 → #723, `commit 968602e7`, `feedback_filter_default_seed_drift.md`.

The repeating motif: each half of the contract changed in a different commit, and the breakage didn't surface until a *third* event (a Reset, a re-read, a fresh install) brought the halves back together. Audit both halves on every shape-changing commit.

## SwiftUI Text registers NSDraggingSource — `.textSelection(.disabled)` doesn't kill it — 2026-04-28

SwiftUI `Text` on macOS registers itself as `NSDraggingSource` at AppKit level for selectable text. That AppKit drag source intercepts presses on the Text BEFORE a SwiftUI `.draggable` on a parent ancestor sees them, producing a generic text drag (with the row's name as content) that bypasses any `.dropDestination(for: T.self)` and produces a `.inetloc` artifact when dropped on Finder.

**`.textSelection(.disabled)` does NOT unregister the AppKit drag source** — it only controls whether the user can interactively select the text. `.allowsHitTesting(false)` on a *parent* doesn't propagate to disable AppKit-level drag registration on children either.

Working suppression: **`.allowsHitTesting(false)` directly on the `Text` element** (not on a parent). Click-through still works because the parent's `.contentShape(Rectangle())` becomes the only hit target for drag/select.

For sidebar rows specifically (file: `SidebarItemRow+Label.swift`): apply on both Image and Text inside the inner `HStack` so neither child claims AppKit-level drags.

## SwiftUI .draggable + .onMove on same ForEach is broken on macOS — 2026-04-28

SwiftUI's `.draggable(T)` runs its own drag session that bypasses `NSTableView`'s automatic row-drag mechanism. On a List, `.onMove(perform:)` requires the NSTableView row-drag path — when `.draggable` wins the gesture arena, `.onMove` doesn't fire. Same for `.dropDestination(for: T.self)` between rows.

**Apple's `ArticleAccelerator` sample sidesteps this** by separating drag source (a different view, with `.draggable`) from drop destination (a List with `.onMove` + `.dropDestination`). Same-list "row is both drag source and drop target" is the unsupported case.

Production fix path is `NSViewRepresentable<NSOutlineView>` (#713). Don't waste time chasing more SwiftUI workarounds for sidebar drag — the SwiftUI surface genuinely can't deliver Finder-grade drop targeting in this configuration.

## Inspector strict per-document scope — `includeDescendants: false` is not the API default — 2026-04-28

Two artifact-loading paths in the SwiftUI inspector:
- `DocumentInspectorContentV2` (file: `DocumentInspector.swift`) — passes `includeDescendants: false` correctly.
- `DocumentInspectorArtifactsTab` (file: `Views/Library/DocumentInspector/DocumentInspectorArtifactsTab.swift`) — was using the API default (true), causing folder container artifacts to bleed onto child page inspectors.

**Always pass `includeDescendants: false` for V2 inspector callers.** The default is `true` for V1 backwards-compat.

Backend endpoint: `GET /api/artifacts/document/{doc_id}?include_descendants=false`. Tests in `fichero-api/tests/unit/test_routes_artifacts.py` lock both modes (strict + legacy). Don't unify the default — V1 callers depend on aggregation.

## Workflow templates: backend JSON is canonical, Swift defaults empty — 2026-04-28

Two systems used to ship default workflows:
- Swift `WorkflowStore.swift::DefaultWorkflowTemplate` — created `Default · Transcribe Files` and `Default · Transcribe Collection`.
- Backend `fichero-api/src/fichero/resources/default_workflows/*.json` — ships `Transcribe`, `Catalogue`, `Catalogue (composable)`.

The two were duplicating the Transcribe template. **Backend is now canonical**; `defaultWorkflowTemplates` in Swift is empty. New default templates: add a JSON file in the backend resources dir.

`reinstall-defaults` endpoint with `force=True` deletes is_template=True rows by name and re-inserts from current JSON. Safe to ship template updates this way.

## Workflow templates use `folder_path` for context menu grouping — 2026-04-28

Run-Workflow context menus (sidebar `SidebarItemRow.swift`, grid `LibraryView+FilterAndBatch.swift`) group workflows by `folderPath`. Top-level workflows (`/`) appear flat; deeper paths (e.g. `/Transcribe`, `/Catalogue`) become `Menu("<folder>") { ... }` submenus. Folder label is the last path component (Finder convention).

To organize a new template, set its `folder_path` in the JSON. Don't need to touch the menu code.

## inspectorDocument precedence — sidebar > grid stale > detail — 2026-04-28

`ContentView.inspectorDocument` (file: `ContentView+State.swift`) computes the doc to show in the inspector. Order matters:

1. Grid selection (`browserSelection.first`) — but ONLY if the doc is a child of the current sidebar folder. Stale `browserSelection` ids must NOT shadow the sidebar selection — fall through if the doc's `parentId != currentSidebarFolder.id`.
2. `viewMode.library(let doc)` — the folder the user has open in the sidebar.
3. `detailDocument` — legacy fallback for navigated-into doc state.

Also: `ContentView.swift` clears `browserSelection.removeAll()` on `selectedSidebarItemId` change so a leaf id from a previous folder doesn't accidentally match a child of the new folder.

## NSTextView Ruler + Format Strip — 2026-04-27

**Tinderbox's "format bar" is just AppKit's `NSTextRulerView`.** Setting `textView.usesRuler = true` + `scrollView.rulersVisible = true` shows the segmented Styles / alignment / Spacing / Lists strip plus the numeric ruler. No custom SwiftUI bar needed; no `addFloatingSubview` dance. Tried both, both were inferior. Use the native ruler.

**`NSTextView.usesInspectorBar` is a different thing — and a trap.** It draws Apple's inline format bar (¶ B I U S, font picker, size, etc.). When enabled, AppKit attaches it at the *window scope* (above tab bar), not above the per-textview scrollview. Wrong place for a per-panel inspector. Leave it `false`.

**`NSTextView.textContainerInset` is symmetric.** `width` pads BOTH left and right. For asymmetric horizontal padding (e.g. left margin only, scrollbar flush right), use `NSScrollView.contentInsets` (left/right are independent) and set `automaticallyAdjustsContentInsets = false`. Set `textContainerInset.width = 0` and let the scroll view's contentInsets carry the leading/trailing padding.

## Sidebar Drag — Symptom of TapGesture/Drag Anti-Pattern — 2026-04-27

The existing memory `feedback_list_selection_vs_tapgesture.md` already warns about `List(selection:) + .draggable + TapGesture`. The symptom on icon/text specifically: when the simultaneousGesture exists for click reliability, AppKit's underlying `NSTableView` row-drag wins on icon/text presses, producing an empty file URL that escapes the sidebar's `.onDrop(of: [.utf8PlainText])` filters and leaks to the window-level URL drop handler. Diagnostic signal: `Files dropped: [""]` in the console. Stacking a second `.onDrag` to "fix" it makes routing worse — one `.onDrag` per row, period. Fix path is migrating to `.draggable(item.id)` Transferable (filed as #711).

## Content Editor Data Integrity — 2026-04-22

**`NSAttributedString` normalizers must never set attributes on a full range unconditionally.** `addAttribute(.foregroundColor, value: NSColor.labelColor, range: fullRange)` wipes any user-set color. Use `enumerateAttribute(...)` and only fill in defaults where the attribute is `nil`. Same pattern for `.font`. Root cause of #671's color/font loss — the RTF round-trip worked; the client normalizer was stripping attributes before rendering.

**`AttributedTextEditor.updateNSView` typography-signature branch overrides RTF fonts on initial load.** The signature starts empty and becomes "System|14|4" on first update, which is technically "a change" — so the code force-applied defaults to all existing text, wiping decoded RTF. Skip the force-apply when `lastTypographySignature.isEmpty` (initial load from decoded RTF); still apply on subsequent user preference changes.

**`onDisappear` must not cancel the debounced auto-save task.** The 600ms debounce + `autoSaveTask?.cancel()` on disappear is a silent data-loss path: user types, navigates within 600ms, edit never flushes. Leave the task alone (let it complete in background) and additionally fire an immediate `saveContent()` if `hasChanges` on disappear.

**`DocumentStore.updateLocal` has cross-folder remove logic — don't use for content-only updates.** When `document.parentId != selectedCollection.id`, `updateLocal` strips the document from `currentDocuments` (correct for move ops, wrong for saves). Use the `refreshLocalContent` helper for content updates: replace-in-place in every cache without the folder-membership check. `updateLocal` is for move operations only.

**User-edit protection via metadata timestamp (no schema migration).** When the API update route writes `page_content`, stamp `metadata["page_content_user_edited_at"] = datetime.now().isoformat()`. Tools with `tool_config.update_page_content` check this flag in `save_artifact` and skip the promotion over user text. The artifact IS still saved — users can see it on the Artifacts tab and manually promote. Document has `extra="allow"` so the key persists without schema changes (#672).

## Catalogue Workflow Architecture — 2026-04-22

**0.0.2 catalogue is a single reduce step on aggregated text, not a chain.** Context windows are large enough that one LLM call can produce all nine sections (Resumen, Palabras Clave, Personas Clave, Fechas, Referencias Legales, Ríos, Eventos Clave, Minas, Propiedades) from concatenated transcriptions. Legacy `use_previous` chaining isn't needed for the demo. Chain/pipeline with use-previous stays deferred for users who want custom multi-step flows.

**Each populated catalogue section becomes its own artifact.** `catalogue` tool yields `(type, {content, data})` tuples for every non-empty section: `summary`, `keywords`, `people`, `dates`, `legal_references`, `rivers`, `events`, `mines`, `properties`. `.content` is a readable list/paragraph (inspector-friendly); `.data` is the structured JSON for downstream use. A combined `catalogue` artifact with the full markdown is also saved for export. Researchers browse each list independently rather than decoding one JSON blob.

**Catalogue container resolution from `state.selected_doc_ids`.** `_resolve_container_doc` priority: exactly one folder in selection → that folder; all files share a parent → that parent; fallback → first folder found or first doc's parent. Lets the same tool work from right-click-on-folder, right-click-on-multiple-files, or explicit folder selection.

**Skip-if-done guard must check `isinstance(content, str)`.** Without it, a test mock returning a `MagicMock` for `.content` flows into `"\n\n".join(texts)` and crashes. Truthy-check alone isn't enough since MagicMock is truthy. Applies to any cached-output reuse branch.

**Default workflow presets seeded from `fichero/resources/default_workflows/*.json`.** `seed_default_workflows(db)` reads every JSON in the dir and inserts workflows by name if missing. Called from `db_manager.get_database` after migrations — idempotent, deleted presets don't resurrect. Tests set `FICHERO_SKIP_DEFAULT_WORKFLOWS=1` in conftest so fixtures that assert "empty library" keep working.

**Batch API uses `selected_doc_ids`, not `document_id`.** When creating batch items in Swift, use `["selected_doc_ids": [documentId]]` so `files_tool` resolves them via the same state channel as SSE runs. Mixing `document_id` in batch items silently produces zero files (files_tool only reads `selected_doc_ids`).

**Context menu vs toolbar: inline submenu vs picker sheet.** Context-menu "Run Workflow" is an inline `Menu { ForEach(workflows)... }` — right-click already indicates target, picker sheet would add friction. Toolbar / menu bar keep the picker because "open workflow list" is the deliberate action there. `workflowStore.workflows` returns `[WorkflowSidebarItem]` (not `[Workflow]`), both have `.id` and `.name`.

**Workflow edge JSON schema: UI expects `source`/`target`/`source_port`/`target_port`.** NOT `source_node_id` / `source_port_id`. The backend (`builder.py`) accepts either via `edge.get("source") or edge.get("source_node_id")`, but the Swift `Edge` decoder (`WorkflowTypes.swift`) only reads `source`/`target` and falls back to empty string — so an edge with `source_node_id` loads with empty `sourceNodeId` and doesn't render. When writing preset JSON or any workflow payload that needs to render in the editor, use the UI schema. Each edge should also have an `id`. Default `source_port` in UI is `"output"`, not `"files"` — always set the port explicitly.

## SwiftUI / SwiftLint Conventions — 2026-04-22

**Exhaustive switch → static dictionary lookup for SwiftLint cyclomatic complexity.** Any switch with >10 cases trips the `cyclomatic_complexity` rule. Cleaner than `// swiftlint:disable`: extract a `private static let iconByType: [String: String] = [...]` and read with `Self.iconByType[type] ?? default`. Same applies to display-name maps.

**SwiftLint `inclusive_language` flags "whitelist".** Use "allowlist" in type/function/variable names. Error, not warning — required for CI.

**`fileSystemSynchronized` Xcode projects auto-discover new Swift files.** No pbxproj edit needed for new files in `fichero-swiftui/` or test targets. Check via `grep fileSystemSynchronized project.pbxproj` before worrying about manual target membership.

## MCP / Peekaboo Setup — 2026-04-17

**`disabledMcpServers` is scope-agnostic.** In `~/.claude.json`, each project key holds a `disabledMcpServers` array that overrides servers from *any* scope — user-level, project `.mcp.json`, or plugin. Don't confuse with `disabledMcpjsonServers`, which only filters project `.mcp.json` entries. To disable a user-scope MCP for one project (e.g., tbx/tinderbox here), add its ID to the per-project `disabledMcpServers` array.

**npm-packaged MCPs usually need a subcommand.** `npx -y @steipete/peekaboo` launches the CLI which prints help and exits — that's why Claude Code reported "Failed to reconnect to peekaboo" repeatedly. The MCP server mode is `npx -y @steipete/peekaboo mcp`. **Debug pattern:** when an MCP shows "failed to reconnect" immediately on launch, run the command manually; if it prints usage text and exits cleanly, a subcommand is missing.

**MCP spawn PATH doesn't include `/opt/homebrew/bin`.** Use absolute `command` paths (`/opt/homebrew/bin/npx`) in `.mcp.json`. Same applies to any tool installed via Homebrew.

**Peekaboo vision-model captions can hallucinate.** The inline `question:` parameter on `mcp__peekaboo__image` feeds the screenshot to Ollama/OpenAI/Anthropic and returns a caption. In testing, it fabricated a file path ("ProvidersView+ProviderSettingsRow.swift compiling for arm64") that wasn't on screen. **Ground-truth rule:** when a claim matters, use `Read` on the saved PNG — Claude Code displays images into context directly, no middle layer. Reserve the caption path for headless/bulk triage.

**Peekaboo `path` is a prefix, not a filename.** Apps with multiple windows (Xcode has 8) produce one PNG per window, suffixed `<prefix>-<AppName>-<WindowTitle>-<index>.png`. For a single file, target a specific window ID, use `app_target: "frontmost"`, or target by PID.

**Ollama `:cloud` tags are remote-proxied pointers.** Local "model" file is ~380 bytes; every inference round-trips to ollama.com. `qwen3.5:cloud` resolves to the 397B flagship via `remote_model`. Not offline-capable. Good for large vision models you can't run locally, but treat latency like any remote API and reorder `PEEKABOO_AI_PROVIDERS` fallback chain if it's too slow for interactive use.

## File-Splitting Patterns — 2026-04-14

**Mixin pattern for large class splits.** When splitting a large class (e.g., `TaskQueue`), extract method groups into a `*Mixin` class. The mixin references `self.database`, `self._save_task` etc. without owning them — Python resolves `self` at call time, so the mixin works as long as the concrete class provides those attributes. Pattern used in `task_workers.py` / `TaskWorkersMixin`.

**Re-export pattern for backward compatibility.** After splitting a module, add at the bottom of the original file:
```python
from fichero.new_module import func_a, func_b  # noqa: F401, E402 (re-exported)
```
This keeps all existing import paths working. Use `# noqa: F401` because ruff sees these as unused.

**Thin combiner router for split route modules.** When splitting a large route file into sub-modules, make the original a thin combiner:
```python
from fastapi import APIRouter
from .sub_module_a import router as a_router
router = APIRouter()
router.include_router(a_router)
```
This preserves all existing `include_router(research_agents_router)` call sites in `main.py`.

**Schemas module for Pydantic models.** When splitting a route module, move all Pydantic request/response models to a `schemas.py` sibling. Other modules (`core.py`, `runner.py`, `threads.py`) all import from `schemas.py`. This prevents circular imports and keeps models findable.

## .iffy.json Sidecar Support — 2026-05-25

Added support for parsing .iffy.json sidecar metadata files during document ingestion. These files contain archival metadata for documents and are automatically paired with their corresponding image/PDF files during import. The system looks for sibling files with the same base name but with .iffy.json extension (e.g., document.jpg pairs with document.iffy.json). Metadata fields are mapped to document metadata keys with special handling for list fields like notes which are converted to comma-separated strings. .iffy.json metadata is merged with existing document metadata without overwriting existing values.

## Route Test Patterns — 2026-04-14

**Double-prefix gotcha:** When a router has `prefix="/X"` AND is mounted at `/api/X`, actual paths are `/api/X/X/...`. Affects: `tasks`, `migrations`, `iiif`, `review_queue`. Always check `grep "router\b" main.py` and `router = APIRouter(prefix=...)` together.

**Patch lazy imports at the source module, not the route module.** `from fichero.storage import stats` inside a route function body must be patched as `fichero.storage.stats`, not `fichero.api.routes.storage.stats`. But `from fichero.multilingual import detect_language` at module top must be patched as `fichero.api.routes.multilingual.detect_language` (bound name).

**Route return values must be real Pydantic instances.** When a route returns a model directly (FastAPI serializes it), patching must return a real model instance — not `MagicMock(spec=...)`. Pydantic's C-extension serializer rejects `_SentinelObject`.

**Async mock pattern for cleanup routes.** Routes that call `tracker.store.delete_old(dt)` need `tracker.store = MagicMock()` with `tracker.store.delete_old = AsyncMock(return_value=0)` — the store sub-attribute must exist before setting the async mock.

**DocType vs FileType confusion.** `DocType` describes hierarchy role (file, folder, chunk, page). `FileType` describes media format (image, pdf, audio). The IIIF route had this wrong: `DocType.image` doesn't exist — use `doc.file_type` against `FileType.image/pdf`.

**FK-free store.** DuckDB store has no foreign key constraints. `create_plan(project_id="missing")` succeeds (200) — don't write tests expecting 404 on missing parents unless the route explicitly validates them.

## OpenAPI / Swift Client Codegen Patterns — 2026-04-14

**`-> dict` handlers produce empty OpenAPI schemas.** FastAPI only emits named `$ref` schemas for handlers with a `BaseModel` return annotation. `-> dict` / `-> dict[str, Any]` produces `{}` in the spec — `swift-openapi-generator` gets no schema and can't synthesize Swift types. Fix: add a named `BaseModel` subclass as return type on every route handler.

**`gt=0` causes `exclusiveMinimum` parse error in swift-openapi-generator.** FastAPI/Pydantic emits `exclusiveMinimum: 0` (JSON Schema Draft 2020-12 / OpenAPI 3.1 style). The Swift generator targets OpenAPI 3.0 which expects `exclusiveMinimum` as a Bool. Fix: use `ge=1` instead of `gt=0` for integer fields — semantically identical but emits `minimum: 1`.

**Duplicate header from Depends + explicit Header param.** `get_library_database` already declares `x_fichero_library_path: str = Header(...)`. If a route handler also declares it explicitly, FastAPI inlines it twice in the OpenAPI spec — `swift-openapi-generator` generates two Swift properties with the same name and the build fails with "invalid redeclaration". Fix: remove the explicit `Header(...)` param from any handler that also calls `Depends(get_library_database)`.

**Pydantic v2: never name a field `json`.** `json` shadows `BaseModel.json()` — Pydantic emits a `UserWarning` and the field behaves unexpectedly. Use `json_data` or similar. Tests calling `r.json()["json"]` will also break.

**Class ordering matters for return type annotations.** A `BaseModel` used as a return type annotation must be defined at module level BEFORE the function. If placed after (even logically nearby), Python raises `NameError` at import time. Place new response models at the top of the file, after `router = APIRouter()`.

## FastAPI Route Registration Pattern — 2026-04-12

**Pattern:** Adding new API routes to the FastAPI application

**Required Steps:**
1. Create route module with FastAPI router in `fichero-api/src/fichero/api/routes/`
2. Add module to `fichero-api/src/fichero/api/routes/__init__.py` `__all__` list
3. Import router in `fichero-api/src/fichero/api/main.py` from routes package
4. Add tuple to `_CORE_ROUTE_SPECS` or `_DEV_ROUTE_SPECS`: `(router, "/api/prefix", ["feature-flag-tags"])`

**Verification:**
- Check `/openapi.json` for new endpoints
- Run: `PYTHONPATH=fichero-api/src python -c "from fichero.api.main import app; print([r.path for r in app.routes])"`

**Test Pattern:**
- Create `test_<feature>_api.py` in `fichero-api/tests/unit/`
- Test Pydantic models, route handlers, and integration points
- Avoid TestClient for simple unit tests (test logic directly)

## Multilingual NLP Pattern — 2026-04-12

**Pattern:** Cross-language text processing using cld3 and custom utilities

**Language Detection:**
```python
from fichero.multilingual import detect_language
result = detect_language("Hello world")  # LanguageDetectionResult
# Returns: language (ISO 639-1), confidence (0-1), is_reliable (confidence > 0.7)
```

**Text Normalization:**
```python
from fichero.multilingual import normalize_text
normalized = normalize_text(text, language_code)  # NFKC Unicode + lowercase (Latin only)
```

**Cross-Language Matching:**
```python
from fichero.multilingual import calculate_cross_language_similarity, find_cross_language_matches
score = calculate_cross_language_similarity(text1, lang1, text2, lang2)
matches = find_cross_language_matches(query, candidates, threshold=0.5)
```

**Language Persistence:**
- `KnowledgeEntity.language`: entity's primary language (ISO 639-1)
- `KnowledgeClaim.language`: claim text language
- `KnowledgeClaim.source_languages`: list of source document languages
- `KnowledgeEntity.aliases`: supports transliterations (e.g., ["東京", "Tokyo"])

**Supported Languages:** 20+ including en, es, fr, de, it, pt, ja, ko, zh, ar, ru, hi, th, he

## MCP Knowledge Adapter Pattern — 2026-04-12

**Pattern:** Thin MCP adapters that map 1:1 to canonical Knowledge API operations

**Purpose:** Enable Claude Code and other MCP clients to manipulate knowledge graph entities and claims through standardized tools.

**Architecture:**
```
MCP Client (Claude Code)
    ↓
MCP Server (fichero/mcp_server.py)
    ↓ HTTP request
FastAPI MCP Tools Routes (fichero/api/routes/mcp_tools.py)
    ↓ direct DB access
Database (DuckDB)
```

**Key Principle:** No business-logic divergence between MCP and HTTP paths. MCP tools are thin wrappers that:
1. Validate input (Pydantic models)
2. Call canonical Knowledge API (or equivalent DB operations)
3. Return standardized response

**Endpoints:**
- `POST /mcp/tools/knowledge/entities/upsert` — Create or update entity
- `POST /mcp/tools/knowledge/claims/create` — Create claim
- `GET /mcp/tools/knowledge/entities/{id}` — Retrieve entity
- `GET /mcp/tools/knowledge/claims/{id}` — Retrieve claim
- `DELETE /mcp/tools/knowledge/entities/{id}` — Soft-delete entity
- `DELETE /mcp/tools/knowledge/claims/{id}` — Soft-delete claim
- `GET /mcp/tools/knowledge/entities` — List entities (with filters)
- `GET /mcp/tools/knowledge/claims` — List claims (with filters)

**MCP Server Tool Handlers:**
Call canonical API endpoints via `FicheroAPIClient`:
```python
async def call_tool(name, args):
    if name == "fichero_kg_upsert_entity":
        return await api_client.request("POST", "/knowledge-graph/entities", data=args)
```

**Testing Strategy:**
- Unit tests for adapter logic (validation, mapping)
- Integration tests for end-to-end workflow
- Verify both direct route access and MCP server invocation

*   **SSRF Security Pattern for Research Tools (2026-04-10):** Security audit of research tools (research.py) revealed critical SSRF vulnerabilities:
    - `follow_redirects=True` without redirect chain validation allows open redirect attacks
    - `_is_sandbox_violation()` using `startswith()` is insufficient — must validate resolved IPs
    - Must block RFC1918 ranges (10.x, 172.16-31.x, 192.168.x), loopback (127.x), link-local (169.254.x), cloud metadata
    - URL scheme checks are case-sensitive — need case-normalization
    - DNS rebinding requires resolution-time IP validation, not just hostname checks
    - Security tests should be written *before* fixes to document known vulnerabilities

*   **Agent Research Pattern**: Following the established pattern from knowledge_graph.py, hermeneutics.py, and mind_palace.py, the Agent Research implementation uses:
    - Pydantic models with `model_config = ConfigDict(from_attributes=True, extra="allow")`
    - Separate request/response models for API endpoints
    - Full CRUD with soft-delete (archiving) pattern
    - Status tracking with enums matching other modules
    - Placeholder tool implementations that return example data

*   **Skills Relocation:** Skills moved from `.agents/skills/` to `plugins/fs_session/skills/`. All script invocations now use `SCRIPT_ROOT` resolver that checks both `$HOME/.pi/agent/skills/fs_session/scripts` and repo `plugins/fs_session/skills/...`.

*   **Backend Task Prioritization (2026-04-10):** Created 21 backend-focused GitHub issues for milestones 0.0.3 through 0.1.0. All issues use only pre-configured labels (`area:backend-api`, `type:task`) since custom labels like `area:operations` don't exist in the project. Issues are properly organized by milestone and ready for AI agent claiming. Backend-only work available: #419-440 excluding Swift-requiring tasks.

*   **Branch Convention (2026-04-10):** Implementation work happens on milestone branches (e.g., `0.0.2`, `feature/388-hermeneutics`), not planning branches. The `0.0.2` branch IS the active implementation branch. State is now tracking backend implementation work for 0.0.3-0.1.0 milestones with 21 issues created for AI agent claiming.

*   **Canonical Knowledge Route Module Pattern (2026-04-12):** Splitting knowledge_graph.py into dedicated modules:
    - entities.py: POST/GET/PATCH /entities, aliasing, resolution
    - claims.py: POST/GET/PATCH /claims, referential integrity
    - claim_links.py: POST/GET/PATCH/DELETE claim linking (bidirectional)
    - Register in _CORE_ROUTE_SPECS with tuple: (router, "/api", ["tag"])
    - Referential integrity: entities must exist before claim creation
    - No soft-delete for links (hard delete only)
    - Patterns extracted from knowledge_graph.py lines ~950-1150

## NetworkX Graph Reasoning Pattern — 2026-04-12

**Pattern:** Algorithmic graph analysis using NetworkX on knowledge graph data

**Graph Construction:**
```python
# Entities become nodes with metadata
G.add_node(entity.id, type="entity", label=entity.canonical_name)

# Claims become nodes connected to entities
G.add_node(claim.id, type="claim", label=claim.text, confidence=claim.confidence)
for entity_id in claim.entity_ids:
    G.add_edge(entity_id, claim.id, relation="mentions", weight=claim.confidence)

# Claim links connect claims to claims
for link in links:
    G.add_edge(link.claim_id, link.related_claim_id, relation=link.relation_type, weight=link.link_quality)
```

**Centrality Algorithms:**
- degree_centrality: Count of edges per node
- betweenness_centrality: Nodes on most shortest paths
- closeness_centrality: Inverse of average distance to others
- eigenvector_centrality: Importance from important neighbors
- pagerank: Iterative importance with damping factor

**Community Detection:**
- louvain: Modularity optimization, O(n log n) complexity
- greedy_modularity: Hierarchical modularity maximization
- label_propagation: Fast O(m) complexity, good for large graphs

**Graceful Degradation:**
- Optional dependency - works without NetworkX installed
- Enabled/disabled via endpoint
- All functions check `reasoner.is_available()` before use
- Tests skip when NetworkX not available

**Metrics:**
- Density: fraction of possible edges present
- Clustering: probability that neighbors are connected
- Connected components: number of disconnected subgraphs
- Modularity: community detection quality (0 = random, 1 = perfect)

**Sources Routes Registration Issue — 2026-04-12**

**Problem:** Attempting to add `/api/sources` routes for issue #364, routes were not appearing in running API despite:
- sources.py file created with FastAPI router
- router registered in main.py _CORE_ROUTE_SPECS
- sources module added to routes/__init__.py __all__

**Findings:**
- Routes appeared in /openapi.json but 404 on actual requests
- sources module import was failing during main.py import
- Workaround: sources routes working via POST/GET with proper `X-Fichero-Library-Path` header when tested directly

**Status:** Routes implemented but runtime registration needs further debugging

## Backend-First Autonomous Loop Policy — 2026-04-11

- For cheap-model `/session-start-auto` loops, **persist execution policy in repo files** (`STATE.md`, `MEMORY.md`, `AGENTS.md`) and GitHub issue comments; chat-only instructions are not durable.
- Backend delivery order is milestone-sequenced: **0.0.3 → 0.0.4 → 0.0.5 → 0.1.0** before frontend re-expansion.
- Per-issue execution gate: claim issue → add/update tests (including security tests if network/file/model code) → implement → run pytest + ruff evidence → PR/merge → close issue.
- Existing repo-wide Ruff test debt can fail global lint despite backend correctness; treat this as separate cleanup scope instead of blocking backend issue completion.

## Sources/API Runtime Drift Lesson — 2026-04-11

- `scripts/start-backend.sh` must prefer project-local `.venv` over ambient `$VIRTUAL_ENV`; otherwise cross-worktree imports can produce route drift (e.g., OpenAPI/routes mismatch and 404 confusion).
- When route appears in code but not runtime, verify importing file path with `python -c 'import fichero.api.main as m; print(m.__file__)'` and inspect live `/openapi.json` before deeper refactors.

## Cherry-Pick Conflict Patterns — 2026-04-13

**When cherry-picking onto an evolved branch, these patterns recur:**

- **research_agents.py + research_models.py must stay in sync**: If you take `--ours` on `research_agents.py` (to keep SSRF security hardening), you must also restore `research_models.py` and the test file to match. The two files form a coherent set — mixed versions break imports.
- **project.pbxproj file references**: Cherry-pick may try to add references to files that don't exist in HEAD (e.g., `BatchDetailView.swift`, `BatchRow.swift`). Always check with `find` before accepting `--theirs` on project.pbxproj; take `--ours` if referenced files don't exist.
- **`@SceneStorage` vs `@AppStorage` for view state**: Bug fix #330 deliberately changed `iconViewScale` from `@SceneStorage` (per-window) to `@AppStorage` (app-wide persistent). When this conflict appears, take `--theirs` — it's the intentional fix.
- **Empty cherry-picks**: When a cherry-pick resolves as empty ("possibly due to conflict resolution"), use `git cherry-pick --skip` — HEAD already contains equivalent changes.

## Branch Cleanup Lesson — 2026-04-13

- After consolidation, verify branch count with `git branch -r` — only `origin/0.0.2` and `origin/main` should remain.
- `git worktree remove --force` still fails if the directory has content git can't delete itself. Follow up with `git worktree prune && rm -rf <path>`.
- `.kreuzberg/extraction/*.msgpack` binary files appear as modified during cherry-picks of branches that processed documents. Always resolve with `--theirs` — these are cache files.

## macOS Settings Layout — 2026-04-16

- `Form { Section(...) }` in a `TabView`-based Settings window **needs `.formStyle(.grouped)`** on macOS 14+. Without it, the default `.automatic` style renders labels right-aligned in an invisible column that pushes all content into the right ~40% of the window and clips right-edge content.
- `.grouped` provides its own insets — remove `.padding()` when switching.
- Matches the native macOS Settings.app look (System Settings → Appearance, Language & Region, etc.).

## SidebarItemBuilder Filter — 2026-04-16

- `SidebarItemBuilder.buildLibraryHierarchy` intentionally filters the document list — it does NOT show every doc. Current filter includes folders, PDFs (`.isNavigableContainer`), and `.page` children. Everything else (text, images, docx, mp3) lives in the main grid only.
- Any future work on "which doc types appear in the sidebar" goes in exactly one place: the `visibleDocs` filter at the top of `buildLibraryHierarchy`. Don't scatter filter logic across the tree-building functions.
- Sidebar children sort via shared `childOrder(_:_:)` comparator: `sequence` (page number) first, case-insensitive name fallback.

## NSItemProvider vs Transferable for file drops — 2026-04-17

- **Folder drops**: `.dropDestination(for: URL.self)` (Transferable) **unwraps a Finder folder drag into the child-file URLs**. URL-as-Transferable expects a file resource; SwiftUI enumerates the folder's contents instead of giving you the folder itself. Result: folder drops import the images but not the folder — #587.
- **The older `.onDrop(of: [UTType.fileURL], isTargeted:, perform: ([NSItemProvider]) -> Bool)` preserves the folder URL.** `provider.loadObject(ofClass: URL.self)` returns the folder URL intact; `FileManager.fileExists(atPath:isDirectory:)` correctly reports `isDirectory == true`; the import service routes to `importFolderAndWait(recursive: true)`.
- **Rule:** use `.onDrop(of:isTargeted:perform:)` for ANY URL drop target. Keep `.dropDestination(for: String.self)` for internal sidebar drags (String Transferable has no unwrap issue).

## `.onInsert(of:)` inside DisclosureGroup crashes on macOS 14+ — 2026-04-16

- `.onInsert(of:perform:)` on a nested `ForEach` **inside a `DisclosureGroup` inside a `List`** triggers `SwiftUICore/HomogeneousCollection.swift:179: Fatal error: index -1 out of bounds` on external folder drops. Reliably reproducible; Apple's radar.
- Don't use `.onInsert` in that nesting shape. For between-row drop UX, use either `DropDelegate` (with `DropInfo.location.y` thresholds for above/on/below regions) or `.onDrop(of:isTargeted:perform:)` with the `([NSItemProvider], CGPoint) -> Bool` variant that gives drop location. Both paths avoid the crash.

## `.focusEffectDisabled()` for keyboard-handler views — 2026-04-16

- When you need `.focusable()` on a container (so `.onKeyPress` handlers fire — ScrollView would otherwise swallow arrow keys), macOS 14+ also draws the system focus ring around that whole container. That's visually misleading if per-cell selection is expressed separately (e.g., accent overlay on the selected cell).
- **`.focusEffectDisabled()`** (macOS 14+) suppresses the container ring while keeping `.focusable()` behavior. Applied to `iconsView` in `LibraryView+DisplayModes.swift` (#575).

## `.formStyle(.grouped)` for macOS Settings — 2026-04-16

- Bare `Form { Section(...) }` in a TabView-based Settings window renders with the default `.automatic` style on macOS 14+, which right-aligns labels in an invisible column and pushes content into the right ~40% of the window. Fix: `.formStyle(.grouped)` on each Form. Drop the outer `.padding()` since `.grouped` provides its own insets.

## `.listRowBackground` caches per-row view — 2026-04-16

- `.listRowBackground(dynamicColor)` in a sidebar-style List **does not reliably re-render** when the color is driven by a plain `@State Bool` inside a row (e.g., drop-hover state). The List caches the row background view per-row identity; only identity changes (tag/id) invalidate it.
- Drop-target highlight: use `.overlay` inside the row view itself with `.allowsHitTesting(false)`. Overlay redraws on every body re-evaluation and layers on top of any sidebar List chrome.

## SidebarItemBuilder is the single source of truth for "what appears in the sidebar" — 2026-04-17

- `SidebarItemBuilder.buildLibraryHierarchy` has one filter (`$0.isNavigableContainer`) that decides which Documents become sidebar rows. Folders + PDFs currently qualify; everything else lives in the main grid only.
- `Document.isNavigableContainer` (defined in `Document.swift`) is also the gate for double-click routing (`canNavigateInto`) AND single-click-drills-into-pages (`ContentViewModifiers.swift:242`). Three call sites, one definition — always grep that property when changing drill-in semantics.
- Pages (`docType=.page`) are **not** in the sidebar; they appear in the main grid when their parent PDF is selected (via `loadChildren(of: pdf)`).

## PDFView page-change notification — 2026-04-17

- `PDFViewPageChanged` is the notification PDFView posts on every page navigation. Prefer this over `PDFViewDelegate.pdfViewPageChanged(_:)` — the delegate method's availability varies across PDFKit versions on macOS.
- For an `NSViewRepresentable<PDFView>`, install a `Coordinator` as delegate + notification observer in `makeNSView`, tear down in `dismantleNSView` via `NotificationCenter.removeObserver`.
- To distinguish genuine page changes from the initial programmatic navigation, compare against `owner.pageIndex` in the observer and skip when equal.

## `xcodebuild` lock when Xcode.app is open — 2026-04-17

- Xcode.app holds an exclusive lock on `build/xcode/Intermediates/XCBuildData/build.db`. Raw `xcodebuild build` fails with "database is locked" even when `-derivedDataPath /tmp/...` is specified (Xcode's build system may still touch the project's default build dir).
- Workaround: `xcodebuild ... clean build -IDEBuildOperationQueueDisableLogging=YES` — the `clean` phase recreates the build db fresh. Slower on first run but reliable. Don't ask Daniel to quit Xcode.

## SwiftUI Drop-Zone Visual Feedback — 2026-04-16

- `.listRowBackground(dynamicColor)` with dynamic @State in sidebar-style Lists **does NOT reliably re-render** on hover-state flips. The List caches the row background view per-row identity; only identity changes (tag/id) invalidate the cache. Selection highlighting works because `selectedItemId` change triggers re-identification; drop-hover state doesn't have that.
- **Fix for dynamic drop-hover highlights**: put `.background(RoundedRectangle.fill(dropTint))` *inside* the row view (where the drop-destination is), not via `.listRowBackground` on the outer DisclosureGroup/row. A plain body re-render repaints it — no caching middleman.
- **Drop hit-region follows view frame, not `.contentShape`**: a `Label { icon; text }` has a narrow natural size — dropDestination on it only fires when the cursor is over the icon/text. Wrap in `.frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())` before `.dropDestination(...)` so the entire row responds.
- **Between-row drops**: use `.onInsert(of: [UTType.fileURL, UTType.utf8PlainText]) { offset, providers in ... }` on the `ForEach`. SwiftUI draws a native blue insertion line for free; handler fires on release with the 0-based offset and `[NSItemProvider]`. Works inside `DisclosureGroup { ForEach ... }`.

## Xcode.app + Manual pbxproj Edits — 2026-04-16

- When Xcode.app has the project open AND you edit `project.pbxproj` by hand, `git status` may show *unintentional* deletions Xcode made on its own (e.g. removing missing `FicheroBackend.app` references, pruning orphaned groups).
- Workflow: `git diff project.pbxproj` BEFORE staging. If the diff shows more than your intentional changes, `git checkout HEAD -- project.pbxproj` and re-apply only what you wanted. Don't trust `git commit -a`.
- Adding a new `.swift` file to the main `Fichero` target requires 4 pbxproj entries with a unique 24-char hex UID: PBXBuildFile (Sources build phase ref), PBXFileReference (file description), PBXGroup children member, Sources build phase member. Pattern is in MEMORY under "Swift main target not file-sync'd".

## Swift Target File Sync — 2026-04-16

- Only `fichero-swiftui-tests/` and `fichero-swiftui-ui-tests/` are `PBXFileSystemSynchronizedRootGroup`. The **main `Fichero` target is not** — new `.swift` files inside `fichero-swiftui/fichero-swiftui/…` must be added to `project.pbxproj` explicitly or they won't compile into the app (SourceKit will even error with `Cannot find type 'X' in scope`).
- Workaround when adding a small extension: merge it into an existing file already in the target (e.g. append `extension Document { … }` to the bottom of `Document.swift`) rather than creating a new file. Avoids touching the pbxproj.
- If you *must* create a new file in the main target: edit pbxproj manually (add `PBXFileReference` + `PBXBuildFile` entries and list the file in the target's `PBXSourcesBuildPhase`) or use Xcode.app to add it.

## Swift Tests — Pattern for Testing View Logic — 2026-04-16

- SwiftUI `View` types can't practically be instantiated in unit tests — they need bindings, observed objects, environment values. **Extract pure logic onto the model** (e.g. `Document.isNavigableContainer` instead of `LibraryView.canNavigateInto(_:)`) and have the view call into it. The test then just builds a `Document` value and asserts against the computed property.
- **"All cases" tripwire pattern**: when a function's contract is "only X is true", assert `FileType.allCases.filter { … } == [.pdf]` rather than enumerating every false case. If someone adds a new case and accidentally makes it match, the test fires without needing maintenance.
- **PDF fixtures at test time, not on disk**: build multi-page PDFs with `PDFDocument() + PDFPage(image: NSImage)` drawn with `NSColor.setFill()`. Different colors per page let you pixel-diff TIFF representations to prove the renderer honors `pageIndex`. Tear down in `defer { try? FileManager.default.removeItem(at: url) }` — no binary fixtures to check in.
- **`build.db is locked`** during `xcodebuild` means Xcode.app is holding the lock (`lsof` shows `SWBBuildS`). Run with `-derivedDataPath /tmp/some-dir` to use a separate build database rather than asking the user to quit Xcode.

## Milestone Worktree Convention — 2026-04-15

**Each milestone gets its own worktree at `~/code/fichero-<version>/`** (e.g. `~/code/fichero-0.0.3`). Never per-task branches — commit all milestone work directly to the milestone branch.

**Two-ahead rule:** Never more than one milestone ahead of what Daniel is testing. Layout at any time:
- Released: N
- Daniel testing: N+1 (`~/code/fichero-<N+1>`)
- Claude building: N+2 (`~/code/fichero-<N+2>`)
- Do NOT start N+3 until Daniel approves N+1.

**Create worktree:** `git worktree add ~/code/fichero-0.0.X -b 0.0.X` (from the current milestone's repo)

## Milestone + Release Architecture — 2026-04-15

**40 milestones, one testable feature each (0.0.1–0.9.0).** Each milestone has one `release-gate` issue with Daniel's human test checklist. Testing pipeline: backend tests → SwiftLint + Xcode build → MCP API tests → Peekaboo screenshots → Daniel human test → bug loop → tag+ship. See `docs/contributor/architecture/release-process.md`.

**Bug priority rule in `.claude/agent-briefing.md`:** autonomous sessions (`/session-start-auto`) always fix `type:bug` issues before picking feature work. Daniel files bugs via `/bug` skill → GitHub issue with `type:bug` label → auto-prioritised next session.

**Skills live in plugins only.** `~/.claude/skills/` has been deleted. All skills are in `fichero-skills/plugins/`. Never copy skills back to `~/.claude/skills/` — that creates duplicates in the skill picker.

## PyKEEN Knowledge Graph Embedding Pattern — 2026-04-12

**Pattern:** Latent inference for knowledge graphs using PyKEEN embeddings and link prediction

**Graph Construction:**
```python
# Entities -> mentions -> Claims
(entity_id, "mentions", claim_id)

# Claims -> related -> Claims  
(claim1_id, "supports", claim2_id)

# Entities -> co_mentioned_with -> Entities
(entity1_id, "co_mentioned_with", entity2_id)  # via shared claims
```

**Model Types:**
- TransE: Translation-based embeddings (geometric)
- RotatE: Rotation-based in complex space
- DistMult: Bilinear interaction (fast, good benchmark)
- ComplEx: Complex-valued embeddings (asymmetric relations)
- ConvE: Convolutional encoder (captures interactions)

**Prediction Types:**
- head_prediction: Given (?, relation, tail), predict head
- tail_prediction: Given (head, relation, ?), predict tail  
- relation_prediction: Given (head, ?, tail), predict relation

**Training Pipeline:**
1. Build triples from knowledge graph
2. Split: 80% train / 10% test / 10% validation
3. Train with early stopping (patience + min_improvement)
4. Evaluate: hits@10, mean_rank, MRR
5. Store model for inference

**Heuristic Fallback:**
When PyKEEN unavailable, use co-occurrence counts:
- tail_prediction: entities co-mentioned with source
- head_prediction: entities that co-mention target
- relation_prediction: most common relation types

**Storage & Verification:**
- Predictions stored with metadata and confidence scores
- User verification: verified=True/False with notes
- Filterable by model_id and verified status

## 2026-05-01 — Token auth, catalog-driven UI, gesture races

### Auth + raw URLSession
Every raw URLSession callsite that talks to the engine MUST add the Bearer token. Use `URLRequest.addEngineAuth(libraryPath:)` (helper at the bottom of `fichero/fichero/Services/APIClient.swift`). Health-check polling to `/api/health` is the only deliberate exception — `AuthTokenMiddleware._UNAUTHENTICATED_PATHS` is the canonical list. The OpenAPI-generated client gets auth via middleware in FicheroClient; APIClient.configureRequest gets it via the same helper. Adding any third HTTP path means using `addEngineAuth` — anything else 401s in production.

### Catalog over hardcoded enums
When listing providers anywhere in the Swift app, drive from `/providers/catalog` and filter — never hardcode a Swift enum. The catalog already carries `name`, `description`, `api_key_url`, `default_model`, `supports_vision`, `is_local`, `is_builtin`, `logo_asset`, `sort_order`. `ProviderLogoView` (Views/Components/) renders the bundled logo asset. `AddProviderSheet` is the canonical example: same pattern. Hardcoded provider lists drift the moment the engine adds a new provider and break "we support X" claims silently.

### `AddProviderSheet` already implements first-launch onboarding semantics
`AddProviderSheet(isFirstLaunch: Bool)` exists with the parameter wired through to its choose/configure/models steps. Future onboarding work should embed or extend that sheet rather than re-implementing a parallel wizard.

### `@Binding` write vs `updateNSView` ordering
SwiftUI `NSViewRepresentable.updateNSView` can fire between a gesture-end handler and the `Task @MainActor` it schedules to write a `@Binding`. If `updateNSView` reads the binding to compute layout, it sees the *pre-gesture* value. Two fixes work:
1. Mark a "we just wrote this" watermark BEFORE the binding write, gate `updateNSView`'s sync logic on the watermark (e.g. `lastSeededContent` in DocumentInspector RTF flow).
2. Defer the post-gesture flag flip into a `Task { @MainActor in await Task.yield(); flag = false }` so the binding-write task runs first (Swift Concurrency preserves FIFO on the main actor).
Both patterns avoid the visible flash where the view briefly snaps back to the pre-gesture state.

### Folder docs in EditorView render `FolderContentsGrid`
EditorView has an `if doc.docType == .folder { FolderContentsGrid(folder: doc) }` branch. In a side-by-side layout (widescreen), this means a folder selection renders the children twice: once in the main grid, once in the side pane. Whenever a layout decision uses `detailDocument`, treat folder docs as "no detail" so the layout collapses to single-pane. (#749)

### SwiftLint `type_body_length` on naturally-large views
Wizards / multi-screen views legitimately exceed the 500-line type body limit. Using `// swiftlint:disable:next type_body_length` on the struct declaration is preferred to artificially splitting state across files just to satisfy lint. Pair with `// swiftlint:disable line_length file_length` at the top of the file (and `// swiftlint:enable` at the bottom) when user-facing UI strings push lines over 140 chars — splitting them in source hurts readability.

### Pbxproj-edit avoidance
The main `fichero` target uses traditional file references, not synchronized groups (only `fichero-tests` and `fichero-ui-tests` are sync'd). Adding a new `.swift` file requires three coordinated pbxproj entries (PBXFileReference + PBXBuildFile + PBXGroup membership). Prefer appending into an existing target file when the new code is one logical concern. The wizard appended to `App/WelcomeView.swift` (already in target, related concern) — no pbxproj edit, no risk of stale-build-system breakage.

### `is_builtin` providers don't need a config row
Provider types where `is_builtin: true` (today: only `apple`) don't require a row in the providers table. The engine recognizes them as always-available without any config. Wizard skips `createProvider` for built-ins and just sets the AI defaults. Future built-ins (e.g. on-device Whisper) follow the same pattern.

### OpenAPI sync is manual; release script does it
`fichero-engine/scripts/sync_openapi_schema.sh` exports the engine's openapi.json and copies it into the Swift package. Running this before any release build is now step 0/4 of `scripts/build-release.sh`. The SwiftPM OpenAPIGenerator plugin regenerates Swift types from the *checked-in* openapi.json on every Xcode build — so a stale openapi.json silently ships old bindings. Daniel's wizard work hit this when adding the Apple-Intelligence probe route; sync ran cleanly. The "swift build" tail of the sync script can fail on stale `.build` cache after directory renames — `rm -rf fichero/fichero-api-client/.build` fixes it; SwiftPM regenerates.

### OpenAPI sync must use the trunk venv when the repo root has no usable `.venv`
In worker worktrees, `sync_openapi_schema.sh` can fall through to system `python3` and fail importing Pydantic if there is no local `.venv`. Set `FICHERO_PYTHON_BIN` to a `.venv/bin/python` that has the deps (e.g. the main checkout's `.venv`) for schema syncs from those worktrees. The script still exports into the current repo and runs SwiftPM generation there.

### Declared fields replace computed properties for persisted Pydantic data
When turning a convenience property into real persisted/OpenAPI data, remove any `@property` with the same name. A Pydantic model field named `bibtex` plus an existing `Document.bibtex` property triggers a redefinition/lint failure and can hide serialization mistakes. Use a `@model_validator(mode="after")` to backfill the declared field from legacy nested metadata instead.

### SourceKit module-resolution false alarms
SourceKit consistently fails to resolve `FicheroAPIClient` (the SwiftPM-generated module) and reports cascading "Cannot find type X" diagnostics across files that import it. The actual `xcodebuild` resolves the module fine and builds cleanly. Rule: trust `xcodebuild`'s exit code, not SourceKit's red squigglies, on Swift Package Manager modules. Don't waste time chasing SourceKit-only failures.

### Per-page extractor cache must key on page doc id, not container
Earlier extractors checked the cache once per (container, section, provider, model) tuple and returned the cached folder-level artifact even when called per-page. Result: claims accumulated on the folder doc, not on each file. Per-page records flow now keys cache lookup AND artifact save on the page doc id; falls back to container path only when records carry no doc_ids. Any future per-page tool that wants per-file artifacts needs the same shape.

### Aggregate emits per-file records only when text+documents are paired
`aggregate._coerce_records` zips `inputs["text"]` (LIST) with `inputs["documents"]` (LIST of {id, name, path}) by index. When upstream sends `text` as a concat STRING (default `transcribe.text` port), aggregate produces ONE record with empty doc_id, breaking every downstream tool that wants per-page provenance. The Catalogue preset wires `transcribe.texts` (plural array) → `aggregate.text` AND `files-source.documents` → `aggregate.documents` so records carry real doc_ids. Any new composable workflow needs both edges.

### Embed Fichero Engine script must skip Debug
Embedding the briefcase bundle on every Debug build wasted 10+ seconds of cp -R and competed with concurrent briefcase rebuilds (race left half-copied bundles). Debug developers run the engine externally; the in-process EmbeddedBackendService probes :8765 first and uses whatever's there. The Embed phase script now `exit 0`s on `CONFIGURATION != "Release"`. Don't re-enable for Debug.

### EmbeddedBackendService never SIGTERMs in Debug
`terminateOrphanEngines()` was indiscriminately killing any process matching "Fichero Engine.app/Contents/MacOS" — including the developer's externally-launched engine on every Debug app launch. Now `#if !DEBUG` around the orphan sweep. Also bumped DEBUG external-backend probe from 2s → 5s so the connect doesn't race a freshly-started external engine and fall through to the embedded path.

### SwiftUI Previews launch the entire host app
There is no isolated preview server on macOS. `#Preview` macros build + launch `Fichero.app`, then evaluate the preview block inside the live process. Any blocking work in `FicheroApp.init` (modal alerts, DB opens, file IO) hangs the 30s preview launch timeout. Gate those behind `XCODE_RUNNING_FOR_PREVIEWS == "1" || XCODE_RUNNING_FOR_PLAYGROUNDS == "1"` (Apple sets the latter for the preview executor). Don't leave heavy startup uncon­ditional.

### SPM previews not worth it for app-coupled views
Briefly extracted KG preview views into a Swift Package to get sub-3s previews. Shelved because: (a) views referencing FicheroAPIClient types can't import cleanly from outside the app, (b) the SPM duplicate would drift, and (c) after the Embed-skip + preview-mode short-circuits landed, regular `xcodebuild` + relaunch is ~5s end to end — fast enough that the SPM upkeep cost outweighs the second-or-two gain. Default to xcodebuild MCP `BuildProject` + `open <bundle>` instead.

### KG inspector: Finder Get Info, not chips with click-actions
First pass made entity rows clickable buttons that copied to pasteboard, with a clipboard icon affordance. Daniel rejected this as "not Mac OS X style" — clicking should never trigger an action; copying is `⌘C` on selected text via `.textSelection(.enabled)`. Each entity kind is a `DisclosureGroup` (open by default, persisted via `@AppStorage` "inspector.kg.expandedKinds"), rows are plain selectable Text. Only keywords get the lozenge treatment — they're short tag-like strings, naturally suited to capsule chips wrapped via FlowLayout.

### Apple model dedup: collapse by model_id at startup
`_seed_builtin_providers` now dedupes Apple models by `model_id` BEFORE seeding (keeps the row with the richest capabilities, deletes the rest). Earlier code only checked `model_id not in existing` before inserting — which prevented NEW duplicates but never cleaned up rows that were inserted by a previous code version. Same pattern (one-shot dedup at boot, then guard the insert) applies to any future built-in seed.

## kg/_common.py — shared helpers across KG submodules — 2026-05-13

`fichero/kg/_common.py` is the consolidation point for three primitives reused across `triples.py`, `graph.py`, `triangulation.py`, `entity_vectors.py`, and `pykeen_predictor.py`:

- `enum_value(x)` — `x.value if hasattr(x, "value") else str(x)`. Use this everywhere KG code stringifies an `EntityType` / `EpistemicStatus` / `ClaimType` / `SourceAuthority`. The inline pattern existed in 9 places before consolidation.
- `slug_verb(verb)` — canonical predicate slug. `triples._predicate_uri` wraps it with the FICHERO namespace; `triangulation` and `pykeen_predictor` use the bare slug. Adding any new module that needs the predicate slug MUST call `slug_verb` directly — never re-implement the slugifier, or SPARQL queries over the RDF graph will silently disagree with the in-Python aggregation in triangulation.
- `extract_svo(claim)` — returns `(verb, object_text)` tuple from `claim.metadata`. Standard SVO pull; replaced 4 inline copies.

`graph._build_cached(db, builder, cache)` and `entity_vectors._l2_normalized(vec)` are local helpers in the same spirit — collapsed near-twin functions in those files.

**Lesson**: when a docstring explicitly warns that two functions "must stay in lockstep" (this was the case for `triples._predicate_uri` ↔ `triangulation._predicate_slug`), treat it as a strong signal to consolidate immediately. The warning meant the prior author already knew it was wrong but didn't have time to fix it.

## SF Symbol lint + Canvas @State — 2026-05-14

### SF Symbols catalog lives in the OS, not a package
The authoritative SF Symbol name list is `/System/Library/CoreServices/CoreGlyphs.bundle/Contents/Resources/name_availability.plist` (`symbols` dict, ~9,184 names) plus `name_aliases.strings` (legacy → current, a binary plist). `fichero-engine/tests/unit/test_sf_symbol_names.py` reads it directly so the lint stays accurate as macOS ships new symbols, and `pytest.skip`s where the bundle is absent (non-mac CI). When validating SF Symbol names anywhere, read this — don't hard-code or hand-maintain a list.

### Never mutate @State inside a Canvas / TimelineView render closure
`ForceDirectedGraphView` (OntologyBrowser.swift) wrote `@State` (`nodes`, `lastTick`) from inside its `Canvas` draw closure — the textbook trigger for "Modifying state during view update" (#1019, same view-switch path as #998). Fix pattern: hold the per-frame-mutated state in a **plain (non-`@Observable`) reference type** kept in `@State` only for instance stability — mutating the object's properties doesn't notify SwiftUI. `TimelineView` still drives the redraw cadence; use a separate observed counter (`graphRevision`) to flip any branch (`isEmpty` checks) that genuinely needs a re-render after async loads. Note: inside a `@ViewBuilder`, `let _ = x` works as a no-op statement but bare `_ = x` does not (`Type '()' cannot conform to 'View'`).

## jcodemunch MCP: single-source at the pipx binary; codex skills can be copies — 2026-05-25

jcodemunch MCP must be defined ONCE per tool, all pointing at `~/.local/bin/jcodemunch-mcp` (a pipx install, outside the worktrees → no PyPI at launch). `uvx jcodemunch-mcp` FAILS during the PyPI false-positive quarantine. Per tool: Claude → `~/.claude.json` **user scope only** (remove project/local scopes — `.mcp.json` is gitignored here); Codex → `~/.codex/config.toml`; pi → `~/.pi/agent/mcp.json` (keeps the 11-tool `directTools` tiering; clear `~/.pi/agent/mcp-cache.json` if it shows a stale server like `chrome-devtools`). Two gotchas when syncing skills to Codex: (1) `~/.codex/skills/<name>` entries are sometimes **copies, not symlinks** — re-link them to `fichero-skills` so edits propagate; (2) the repo mixes case — `session-start-*` use `SKILL.md` but `bug`/`feature` use `skill.md`. On the case-insensitive macOS FS, `git add .../SKILL.md` silently **no-ops** against a tracked `skill.md`; stage the exact tracked case or the commit captures nothing.

## Multi-worktree coordination: the active lane may live in the shared trunk checkout — 2026-05-25

For Fichero, do not assume the dedicated `~/code/fichero-pi` or `~/code/fichero-codex` desk is the active worker. The live lane can temporarily be the shared `~/code/fichero-0.0.2` checkout, so always confirm the tmux pane before merging or resyncing. When forwarding trunk into lane worktrees, `HISTORY.md` merge conflicts are usually doc-only and should preserve both frontend and backend session summaries rather than dropping either side.

## #1362 DuckDB index FATAL — the real fix is a table rebuild, not a guard — 2026-05-31

`workflow_runs` carries an ART index (thread_id PK + 2 secondary). After a crash/WAL replay the index desyncs from the heap; ANY in-place indexed `DELETE`/`UPDATE` (e.g. startup recovery's `UPDATE ... SET status='failed' WHERE status='running'`) raises `Invalid Input Error: Failed to delete all rows from index. Only deleted 0 out of N rows`, which DuckDB escalates to a **`FatalException` that invalidates the entire connection** — every later query 500s with "database has been invalidated", bricking the library. The morning guard only protected `CREATE INDEX` and missed the UPDATE → it recurred. **Correct fix (`activity_store._recover_stale_workflow_runs` + `_rebuild_workflow_runs_flipping_stale`, commit b5ca7c2b):** try the in-place UPDATE, and on ANY `duckdb.Error` discard the poisoned conn and rebuild the table on a FRESH conn via `CREATE TABLE __new AS SELECT * (status flipped via CASE); DROP; RENAME; recreate indexes`. CREATE-AS-SELECT never does an indexed in-place delete, so it sidesteps the ART bug. Never re-raise from startup recovery. The raw FATAL can't be reproduced on a clean DuckDB 1.5.3 file — test by monkeypatching `execute` to raise `FatalException` at the seam and asserting the rebuild fallback leaves a usable conn.

## WindowServer watchdog crashes are GPU starvation, not a backend bug — 2026-05-31

Full-UI crashes (logs/restart.txt: `bug_type 409`, `WATCHDOG`, "monitoring timed out for service", "WindowServer main thread unresponsive") are the macOS display compositor being starved — a GPU-load event, NOT Fichero Python/pytest. On Daniel's M1 (MacBookPro17,1) they recurred only during active work sessions. Prime suspect: the **broken RealityKit/spatial view (#1376)** rendering a failed-texture scene (giant blue blob) in a runaway Metal loop; secondary: KG "hairball" graph (#1368) continuously redrawing hundreds of nodes. Mitigation: default the `mindPalace` RealityKit flag OFF until #1376 lands; don't leave the 3D view open during long sessions. Tracked in #1400.

## Entities carry native per-page scope; node-class is the architectural north star — 2026-06-02

`KnowledgeEntity` now has **`source_document_ids: list[str]`** (#1562, commit in PR #1573): entities are deduped global nodes that **accumulate every page/doc id they're extracted from** (idempotent append across *every* `upsert_entity` return branch — existing / 3× type-conflict / alias-fold / embedding-match / fresh-create / race-survivor). Before this, entity→page was only derivable by walking claims (`KnowledgeClaim.source_document_id` was page-scoped, entities had no scope at all). A page's table view should now filter entities by `source_document_ids contains page_id`; the parent aggregates via `_descendant_doc_ids`. Added as a Pydantic field only (no ALTER — 0.0.x rule); OpenAPI regen required (additive optional field, old Swift client unaffected).

**Design-of-record for the whole workspace/thinking-layer build is `docs/contributor/architecture/thinking-layer.md`** (locked 2026-06-02). The north star: **everything is a typed node** — collapse `DocType`/`EntityType`/`NoteKind` into ONE user-extensible class/prototype registry (generalising #874's entity-type registry); grouping + hierarchy are the universal mechanism for "these pages = a chapter / these files = an archival box / these sources = a workspace". Workspace AND ResearchProject are both first-class container **nodes in the library tree**, distinguished by class (not by where they live in the UI). Build phased in epic #1570: Phase 1 = workspace items only (god-nodes untouched), Phase 2 = generalise across Documents/entities/pages.

## Salvage a session-limited subagent's worktree — don't re-dispatch — 2026-06-02

When an `Agent(isolation:"worktree")` subagent hits a session limit mid-task, its **file changes remain intact and uncommitted in its worktree** (`.claude/worktrees/agent-<id>`). Recover by: `git -C <wt> diff` to review, run the gate yourself (ruff/pytest or swiftlint/xcodebuild) in that worktree, then `git checkout -b ms/<branch>` + commit + push + PR from inside it. Far cheaper than re-running the whole implementation. (The #1562 backend was fully written by a frozen subagent and just needed the manager to gate + merge.) SourceKit "Cannot find type" diagnostics from an un-indexed agent worktree are false positives — trust the actual `xcodebuild` result.

## Live transcription gotchas (2026-06-14, ICANH)
- **Transcribe is SLOW**: the `Transcribe (cloud)` node runs a real Gemini vision call **per page** ≈ 100–420s for a multi-page doc. CLI `workflow run ... --wait --timeout` must be ≥ 480s or it falsely "times out" while the legit call is still running. A timeout is NOT a stall.
- **uvicorn --reload does NOT reliably reload deep modules** (e.g. `vision_base.py`). After merging backend fixes, RESTART the backend process; a long-lived backend can serve stale pre-fix code and reproduce already-fixed bugs (this caused the false "#2215 regressed" / empty-page-children result).
- **Per-page propagation**: transcribe writing the combined transcript to the PARENT doc with empty page children = the #2215 signature. Confirm the backend is on post-#2215 code (restart) before concluding a per-page bug exists.
- **is_blank=True on scanned PDF pages is EXPECTED** (no embedded text layer) and is deterministic on fresh import — it is NOT stale data and a fresh library reproduces it identically. It must NOT cause transcription to skip image-only pages.
- **Multi-line tmux send-keys to claude workers often does NOT auto-submit** — it queues as `[Pasted text]`. Always send a second `Enter` and confirm the pane shows `esc to interrupt` (not an idle `❯` with a grayed paste).
- **Agents over-report completion**: the CLI lane repeatedly reported "done" that the manager poll disproved (unsubmitted paste, fire-and-forget deadlock, re-export of stale rows, exit-0 on empty data). Verify the DB/artifacts yourself; never trust a worker's "completed".

## Cross-platform SwiftUI gating: prefer typealias + shim over per-site #if — 2026-06-18

For Fichero's single-codebase Mac / iOS / visionOS drive, the right granularity is **one canonical shim per API** in `Models/Platform/PlatformAliases.swift`, not per-call-site `#if os(macOS)` blocks. The split-view sweep across 14 files was clean because `PlatformHSplitView` and `PlatformVSplitView` are `typealias HSplitView` on macOS and an `HStack` shim on iOS — Mac behavior is byte-identical through the typealias, iOS compiles clean, and visionOS gets a new branch in one place. Same pattern for `PlatformImage`/`PlatformColor`/`PlatformFont`/`PlatformViewRepresentable` and the new `NSColor.platform*` / `UIColor.platform*` color aliases (`platformQuaternaryLabel`, `platformSelectedControl`) — iOS renamed `quaternaryLabelColor` to `quaternaryLabel` so the shim is the only sane way to keep call sites readable.

Use `#if canImport(AppKit)` / `#elseif canImport(UIKit)` rather than `#if os(macOS)` for the **typealias definitions themselves** so Catalyst and future Apple platforms slot in without extra branches. Reserve `#if os(macOS)` for call sites that genuinely need platform-conditional logic (e.g. `.onMoveCommand`, `NSOpenPanel`, `.alternatingRowBackgrounds`) — those are real behavioral gates, not type shims.

For representable types with shared coordinator logic (FicheroWebView / WKWebView pattern): declare the struct under both `#if os(macOS)` / `#elseif os(iOS)` and lift the coordinator to a top-level type (e.g. `FicheroWebViewCoordinator`) so both branches share one `WKNavigationDelegate` implementation. Trying to nest the coordinator inside both struct branches breaks parsing (Swift sees the inner class as nested in whichever branch is active).

## Xcode MCP BuildProject required for the iOS gate — xcodebuild CLI doesn't share Xcode.app's cache — 2026-06-18

`xcodebuild` CLI under this repo's setup stalls on package resolution + build.db lock contention when run outside Xcode.app. `SWBBuildService` (Xcode's build service, PID 5395 in the test session) held `fichero/build/xcode/Intermediates/XCBuildData/build.db` for 30 minutes of CPU and a cold `xcodebuild -destination 'generic/platform=iOS Simulator'` call ran 8 minutes before producing errors. **Manager gate for iOS must use `mcp__xcode__BuildProject`** (tab `windowtab3` per STATE.md) so the build shares Xcode.app's cache and avoids the lock. `xcodebuild` CLI is fine for occasional verification — fast enough at ~5 min per cold build — but not for iteration. If CLI does block on `build.db` lock, `rm -f fichero/build/xcode/Intermediates/XCBuildData/build.db` unblocks it (SWBBuildService reopens).

## Chat owns first-party sidebar/chat work — 2026-06-18

Sidebar/chat/drag-drop review filed focused issues #2336-#2346 and updated roadmap ownership. `Chat` is the owning milestone for `Chat with Docs` routing, chat document-scope drag/drop payloads, stale `SidebarChatSurface`, command-vs-selection semantics, `onCreateChatWithDocuments`, and model-comparison sidebar visibility. `Library & Reading Surface` owns sidebar/library drag-drop correctness (transactional cross-folder moves, Finder temp cleanup, mixed-provider classification). `Multiplatform — iOS / iPadOS / Mac` owns compact/touch alternatives for sidebar/chat drag-drop.

## Stale worker worktrees: never merge wholesale; "closed" ≠ fixed — 2026-06-22

Workers spawned before a big push sit on a base 50-110 commits behind `0.0.2`. On a worker hand-off, check `git rev-list --count worker/X..0.0.2` (how far BEHIND) FIRST. A large behind-count + a `git diff 0.0.2..worker/X` full of DELETIONS = stale base, NOT new work — merging it reverts the interim work. Examples this session: `ios-reader-polish` (110 behind) would have re-added `db_writer.py`, deleted `change_stream.py` + the HTR tests, −5007 lines; `pdf-page-save` re-solved an already-fixed bug (`save_artifact` + `find_existing_artifact` already had the `and not document_id` guard on 0.0.2). For a stale branch with a real net delta: re-implement the delta fresh on current 0.0.2 or capture it as an issue — do NOT cherry-pick.

Corollary: a CLOSED GitHub issue is NOT proof the fix is in the code. #2445 (help-text font) was closed but `DynamicConfigView+FieldRendering.swift` still had `.caption2`. Always grep the actual code before trusting "closed"; reopen if the code disagrees.
