# Repo Hygiene Plan — Open-Sourcing Readiness

**Date:** 2026-07-13 · **Status:** PLAN ONLY — executes AFTER the Mac App Store + TestFlight builds ship. Nothing in this document has been applied.
**Milestones:** #177 "Hygiene & Structure - Engine and Python", #178 "Hygiene & Structure - Frontend and SwiftUI".
**Acceptance test for every proposal here:** *a stranger — human or AI — can read the repo cold and know where everything is and where a new file goes.*

Every factual claim below was verified against the working tree at `main` (83cc2dc61) on 2026-07-13; citations are `file:line`. Where I could not verify, I say so in §11.

---

## 1. Verified current state

### 1.1 Backend (`fichero-engine/src/fichero/`)

- **77 top-level `.py` modules**, of which **10 are already 1-line shims** from prior reorg stages (`iiif_import.py`, `ingest.py`, `knowledge_models.py`, `hermeneutics_models.py`, `manifest_import.py`, `slipbox_import.py`, `source_archive_import.py`, `tinderbox_link_import.py`, `cloud_link_import.py`, `sergio_import.py`). The importer shims use the identity-preserving pattern — e.g. `iiif_import.py:1`:
  `from fichero.importers.iiif_import import *; import sys; sys.modules[__name__] = sys.modules["fichero.importers.iiif_import"]`
  So ~67 real loose modules remain.
- **17 subpackages already exist**: `actions/ api/ bibliography/ books/ citations/ cli/ execution/ importers/ integrations/ kg/ knowledge/ loaders/ mcp/ resources/ retrieval/ search/ workflows/`.
- **`kg/` is an entire shim package**: `kg/graph.py:1` is `from fichero.knowledge.graph import *  # noqa` — every module in `kg/` mirrors a real module in `knowledge/`. Two names for one package, live today.
- **`api/routes/`**: 86 route modules flat (87 `.py` incl. `__init__.py`) + one subpackage (`workflow_execution/`). Routers are registered in one import block at `api/main.py:1301` and mounted via `_CORE_ROUTE_SPECS` at `api/main.py:1388`, each with an explicit prefix + OpenAPI tag — the tag list is effectively the domain map already (66 distinct tags).
- **The #2569 claim "routes are imported almost only by `include_router` in `api/main.py`" is FALSE as stated.** **157 files outside `routes/`** import `fichero.api.routes.*` (measured by grep over `src` + `tests`, `__pycache__` excluded). Heaviest: `workflow_execution` (77 refs), `activity` (42), `providers` (32), `chat` (26), `entities` (23), `documents` (19). Why: **Pydantic request/response schemas live inside route modules** and are imported by `cli/client.py:33-61`, `models.py:57-59`, `llm.py:3615`, `workflows/tools/merge_dedup_only.py:43-44`, `execution/runner.py:28`, and dozens of tests. Routes are still the right *first* move — but only because the shim pattern absorbs those 157 import sites, not because they don't exist. §4.2 and §8 account for this.
- **Inverted dependency worth fixing:** `execution/runner.py:28` imports `fichero.api.routes.workflow_execution.schemas` — core execution depends on the API layer (issue #2594's target).
- **Oversized files (god-nodes):** `cli/openapi_surface_generated.py` 14,021 ln (generated — exempt), `db.py` 4,574, `llm.py` 4,055, `__main__.py` 3,836, `api/routes/documents.py` 2,832, `workflows/tools/extractors.py` 2,802, `api/routes/search.py` 2,288, `models.py` 2,286, `app_db.py` 1,996.

### 1.2 Frontend (`fichero/fichero/`)

- **588 `.swift` files.** `Views/` has 402 across 27 subfolders + 13 loose at `Views/` root (the `ContentView` family — cohesive, fine). Largest: `Views/Library/` **102**, `Views/Workflow/` **64**, `Views/KnowledgeGraph/` **36**, `Views/Sidebar/` **33**. `Models/` has 91 direct files + `Platform/`; `Services/` 75 direct files.
- `scripts/check_folder_organization.py` already encodes the offender list (`KNOWN_VIOLATIONS`, :43-52: Models, Services, Views/KnowledgeGraph/OntologyBrowser, Views/Library, Views/Library/DocumentInspector, Views/Library/Inspector, Views/Sidebar, Views/Workflow) with `MAX_DIRECT_SWIFT_FILES = 18` (:31) and suggested subfolders for Views/Library (:38-40). **The reorg's Swift-side definition of done = this guardrail's `KNOWN_VIOLATIONS` shrinks to `{}`.**
- **Three distinct surfaces confirmed in code** (do not conflate): Preview/source-viewing (`Views/Library/ImageViewer/`, `QuickLookPreviewViews.swift`, `MediaStreamPreview.swift`), Reader (`Views/Library/Reading/` — `ImmersiveReaderView`, `DocumentTextReader`, `ReaderTabBar`, `PDFPageView`), Inspector/editing (`Views/Library/Inspector/` — presenter, tabs, panes — and `Views/Library/DocumentInspector/` — document-scoped tabs, 24+ files, two >1,100-line files per #3439).
- **The existing plan doc `docs/contributor/design/swiftui-app-reorg.md` is prior art AND is stale.** It proposes the same Library split (Reading/Representations/Inspector, :63-73) — partly executed since (Reading/ and Inspector/ exist). But it declares Mind-Palace-3D/RealityKit fully removed (:106-132, "No RealityKit import remains"), while today `Views/Space/SpaceSceneView.swift` imports RealityKit and renders "a Spatial room — the `.threeD` render mode". Its file counts are also outdated (Library 65 → now 102). It must be updated or superseded (§9).
- **Canvas naming chaos, frontend:** three sibling folders render the same domain — `Views/Canvas/` (Canvas2DProjection, CanvasOrtho2DRenderer), `Views/Space/` (Canvas3DProjection, CanvasScene3DRenderer, SpaceSceneView), `Views/Spatial/` (Spatial2DCanvasGestures/Items, SpatialView) — plus top-level `CanvasScene/` (7 files). Two naming generations (Spatial*, Canvas*) coexist.
- **`Services/*ServiceGenerated.swift` are hand-written** despite the suffix — AGENTS.md:375 says so explicitly. The suffix lies to strangers.

### 1.3 Repo-level

- Three Xcode native targets: `Fichero` (app, multiplatform), `FicheroTests`, `FicheroUITests`. Both test targets are already `PBXFileSystemSynchronizedRootGroup` with empty `exceptions` (project.pbxproj:1233-1248). The app target is a classic hand-listed group tree: 4,490-line pbxproj, 593 `PBXBuildFile` entries. **Zero** files use per-file `COMPILER_FLAGS`/`ATTRIBUTES` (grep count 0). A basename scan found **zero `.swift` files on disk missing from the pbxproj**.
- ~50 `scripts/check_*.py` guardrails; **30 have path-keyed `KNOWN_*` baselines** (grep for dict-literal `.py`/`.swift` keys). Verified stale-entry behavior in four: `check_native_controls.py:189-211`, `check_appkit_imports.py:28,136-158`, `check_dead_files.py:159`, `check_shell_chrome.py:29` — **a baseline entry whose path no longer matches makes the gate exit 1**, and a moved file reappears as a "new offender". So every move is a guaranteed double-red unless the baseline is rewritten in the same commit (§2).
- `scripts/check_docs_paths.py` (:1-16) fails the gate when a doc names a repo path that doesn't exist — so **docs must move in the same commit as the tree**, which is exactly the "docs and tree agree" bar, mechanically enforced.
- `scripts/add-swift-file.rb` / `remove-swift-file.rb` exist as the current pbxproj-surgery workaround; `check_xcode_registration.py` guards forgotten memberships.
- Issue-hygiene note: #2566, #2569, #2556 are engine/docs issues sitting on milestone **178 (Frontend and SwiftUI)** — mis-milestoned. A third milestone, **#237 "Backend Hygiene & Python Structure" (0 open)**, exists with unclear relation to #177. #2571's pointer to "#104's vocabulary table" is stale — #104 is a closed SwiftLint issue; no vocabulary table exists anywhere I could find. §6 fills that gap.

---

## 2. Hard constraint 1 — path-keyed guardrail baselines: the move protocol

The mechanics (verified, §1.3): a move flips a baselined guardrail red twice — stale old path + "new" offender at the new path. A churned baseline is indistinguishable from a regression *unless the diff proves the only change is the path*. Protocol, improving on "one subpackage per commit + full suite + baseline-diff":

1. **Move-only commits.** A commit that moves files contains: `git mv` + import/reference updates + the mechanical baseline path rewrite + doc path updates. **Zero content changes** to the moved code. Content changes (splitting a big file, renaming a type) are always separate commits. This makes `git diff -M --stat` show ~100% renames and the review trivial.
2. **Baseline-diff harness (build once, in H0).** A small script — `scripts/baseline_move_check.sh <old-prefix> <new-prefix>` — that (a) runs every `check_*.py --list`/`--json` in a **clean second worktree at the pre-move commit**, (b) runs them post-move, (c) normalizes paths (`sed s|new|old|`) and diffs. **Empty diff = the guardrail output changed only by path.** Attach the diff (or its emptiness) to the PR body. This converts "trust me" into evidence.
3. **One subpackage per commit**, one domain per PR. Never two lanes touching overlapping surface (lanes-disjoint rule) — and **nobody else touches `project.pbxproj` during a Swift move batch**.
4. **Full suite after each batch, not `-k` filters** — targeted gates skip the architecture guardrails (known failure mode). Backend runs with `PYTHONPATH=<worktree>/fichero-engine/src` and the relevant `FICHERO_RUN_*` flags; Swift gates run via the Xcode MCP build (never raw xcodebuild), serialized.
5. **Content-hash-keyed guardrails** (`check_shell_chrome.py` keys path+hash) confirm content-identity for free: after a pure move, only the path half of the key changes. If a hash changes in a move commit, the commit is not move-only — reject it.
6. **Order baselined-file moves late within each domain batch** where possible: moving un-baselined files first shrinks the baseline churn per commit and keeps each baseline rewrite small enough to eyeball.

---

## 3. Hard constraint 2 — pbxproj: convert the app target to a synchronized group (RECOMMENDED, as prerequisite H0)

**Recommendation: yes, convert — before any Swift file moves.** Evidence for feasibility:

- Both test targets already run as `PBXFileSystemSynchronizedRootGroup` with empty exception sets (pbxproj:1233-1248) — the mechanism is proven in this exact project/Xcode version.
- Single app target → no cross-target membership matrix to encode as exceptions. (iOS/macOS is one multiplatform target; `FicheroApp_iOS.swift` etc. are `#if os`-guarded in-target.)
- Zero per-file compiler flags/attributes to preserve (grep count 0).
- Zero on-disk `.swift` files outside the target — nothing silently *joins* the build on conversion. (Verified by basename scan; a stricter path-level scan is an H0 checklist item.)

**Payoff:** folder tree becomes the source of truth; every reorg move in H6-H7 becomes plain `git mv`; the recurring "worker adds .swift, forgets pbxproj, build fails" bug class dies permanently; `add-swift-file.rb`/`remove-swift-file.rb` retire; `check_xcode_registration.py` simplifies to "no stray non-source files in the app folder".

**Honest risks & mitigations:**

| Risk | Assessment | Mitigation |
|---|---|---|
| Non-source files under `fichero/fichero/` auto-included as resources: `Info.plist`, 4 × `.entitlements`, `Fichero.sdef`, `.DS_Store` litter (verified present) | Real. Sync groups include everything; `Info.plist`/entitlements are referenced via build settings, but the copy-resources phase may pick up strays | Add `membershipExceptions` for the plist/entitlements/sdef as needed; delete `.DS_Store` files and gitignore them; **verify the built .app's Resources/ contents pre/post conversion are identical** (checklist item) |
| Xcode rewrites pbxproj behind your back mid-conversion | Known behavior | Do the conversion in a quiet window: no other lane touches pbxproj; Daniel's Xcode closed or on another checkout; single commit |
| Giant one-time diff (~2,000+ deleted pbxproj lines) is unreviewable line-by-line | True | Review by *outcome*, not diff: MCP macOS build + iOS worktree build + `RunAllTests` + launch-stress smoke + compare `xcodebuild -list`/build-log file lists pre/post |
| Release/App Store configs (3 entitlements files, Sparkle-vs-MAS split) interact with target membership | Plausible; this is why the work waits until AFTER the MAS/TestFlight builds ship | Post-ship timing is already the plan's premise; re-run the release build script against a conversion branch before merging |
| Sync groups change how per-file localization/asset handling works | Unlikely to matter (assets are in `.xcassets`) | Covered by the built-product comparison |
| It simply doesn't work for some Fichero-specific reason | Cannot fully rule out from reading | **Spike it in a throwaway worktree first** (H0 step 1); if the spike fails, fall back: keep classic groups, do every H6/H7 move via `add-swift-file.rb` batches — slower but proven |

If the spike fails, the frontend reorg still proceeds — each move batch just includes scripted pbxproj re-registration and the moves get chunked smaller.

---

## 4. Target structure — backend (literal)

### 4.1 `src/fichero/` — loose modules → subpackages

New subpackages in **bold**; existing ones absorb where natural. Mapping table (every non-shim loose module accounted for):

| Target | Modules moving in |
|---|---|
| **`persistence/`** | `db.py`, `db_embeddings.py`, `db_manager.py`, `db_migrations.py`, `migrations.py`, `app_db.py`, `storage.py`, `storage_snapshots.py`, `paths.py`, `library_paths.py`, `library_bootstrap.py`, `library_discovery.py` |
| **`llm/`** | `llm.py`, `llm_models.py`, `llm_embeddings.py`, `llm_mock.py`, `local_inference.py`, `local_models.py`, `mlx_model_store.py`, `mlx_runtime.py`, `model_profiles.py`, `model_recommendations.py`, `providers.py`, `provider_validation.py`, `prompts.py`, `orchestration_policy.py`, `pykeen_inference.py`* |
| **`text/`** | `lang_detect.py`, `language_coverage.py`, `multilingual.py`, `utf16_offsets.py`, `ocr_geometry.py`, `image_ops.py`* |
| **`security/`** | `authz.py`, `accounts.py`, `multiuser.py`, `keychain.py`, `path_security.py`, `url_security.py`, `xml_security.py`, `remote_access_tls.py` |
| **`transport/`** | `bind_host.py`, `discovery.py`, `remote_backend.py` (the connection-transport invariants get one named home) |
| **`library/`** | `node_aliases.py`, `node_prototypes.py`, `bookmarks.py`, `canvas_models.py`, `spatial_arrange.py`, `geo.py`* (canvas/spatial are Library view modes — content folds in) |
| `knowledge/` (exists) | `graph_reasoning.py`, `verification_targets.py`; **delete the `kg/` shim package** after rewriting its remaining importers to `knowledge.` |
| `mcp/` (exists) | `mcp_server.py`, `mcp_simple.py`, `mcp_full.py`, `mcp_manager.py`, `mcp_kg_tools.py`, `mcp_document_tools.py`, `mcp_research_tools.py` |
| `importers/` (exists) | done — rewrite the consumers of the 10 existing shims, then delete the shims |
| `execution/` (exists) | `perf.py`? no — stays core. #2594: move runner's route-layer coupling here (schemas out of `api/routes/workflow_execution/`) |
| stays top-level (true core, ≤10 files) | `__init__.py`, `__main__.py` (entry; split its 3,836 ln under `cli/` per #2567 — separate content work), `errors.py`, `logging.py`, `perf.py`, `models.py`† , `research_models.py`† |

\* judgment calls — see Questions Q6. † `models.py` is the god-node (2,286 ln, imported everywhere): it moves **last**, alone, with a long-lived shim, or stays put — Q5. `research_models.py` is **held for #2571** (research/agent/search consolidation) — don't re-home a domain that's about to be redefined.

### 4.2 `api/routes/` — 86 flat modules → domain subpackages

Grouping follows the existing OpenAPI tags (`api/main.py` route specs), so folder = tag = generated-client domain:

```
api/routes/
├── auth/          authz, auth_accounts, pairing
├── system/        activity, changes, settings, migrations, integrations,
│                  storage, registries, tasks
├── library/       library, library_items, library_links, library_registry,
│                  library_entity_types, folders, views, locations, bookmarks,
│                  sources, canvas
├── documents/     documents, document_inspector, artifacts,
│                  content_representations, annotations, image_editing,
│                  ingest, iiif, export, batch, notes*
├── kg/            kg_claim_analysis, kg_claim_search, kg_curation_rules,
│                  kg_entity_curation, kg_graph, kg_inclusion, kg_mutations,
│                  kg_predictions, kg_pykeen, kg_rebuild, kg_render, kg_review,
│                  kg_search, kg_sparql, kg_triangulation,
│                  entities, entity_inspector, classifications, hermeneutics,
│                  claims, claim_curation, claim_links
├── citations/     citations, citation_rendering, citation_usages,
│                  bibliography, references
├── search/        search, search_explain
├── research/      research_crud, research_agents, research_notes,
│                  research_tools, projects, chat, agent_memory   ← grouping only;
│                  NO renames/merges until #2571 decides the surface
├── providers/     providers, provider_keys, provider_models, models,
│                  model_comparison, local_inference, local_models,
│                  multilingual, mcp_servers, mcp_tools
├── automation/    schedules, triggers, orchestration
└── workflows/     workflows, chains, actions, actions_registry,
                   workflow_execution/  (subpackage moves intact)
```

\* `notes` could equally be its own `routes/notes/` (it's a first-class UI surface) — Q6. Inside `kg/`, drop the now-redundant `kg_` filename prefix (`kg/search.py` not `kg/kg_search.py`) **only in the final shim-deletion pass**, not during the move.

**Shim strategy (what makes this safe despite 157 outside importers):** each move leaves a module at the old path using the proven `sys.modules` identity shim (`iiif_import.py:1` pattern), so `from fichero.api.routes.kg_search import KGSearchResponse` keeps working and even `isinstance`/monkeypatching in tests stay correct. Old paths are rewritten consumer-by-consumer in later mechanical commits; shims are deleted in H9. A follow-up (not this plan's scope) should extract Pydantic schemas from route modules into `schemas.py` per subpackage — that's what actually ends the coupling.

---

## 5. Target structure — frontend (literal)

Preview / Reader / Inspector are **three distinct product surfaces** (verified §1.2) and stay three distinct folders. Target tree (moves only; file splits like #3439 are separate content work):

```
fichero/fichero/
├── App/                        (unchanged; move IntegrationsPlaceholderSheet out or delete — it's a view)
├── Intents/                    (unchanged)
├── Models/
│   ├── Stores/                 all *Store.swift + *Store+*.swift + LibraryManager*  (~45 files)
│   ├── Domain/                 value types: Document, Artifact, Event, AnnotationHighlight, …
│   └── Platform/               (exists)
├── Services/
│   ├── API/                    per-domain endpoint wrappers (the *ServiceGenerated.swift files —
│   │                           rename to drop the lying "Generated" suffix, Q7)
│   ├── Engine/                 EngineSession, EngineConfig, EngineReadinessProbe,
│   │                           EmbeddedBackendService, ChangeStreamTransport, LibraryChangeStream,
│   │                           DeviceTokenRenewal, RemoteClientPairing, APIClient*
│   └── Platform/               AppleScriptCommands, AppleScriptSupport, UITestSupport, PDFDocumentCache
├── Views/
│   ├── (root)                  ContentView + its extensions stay — cohesive set
│   ├── Shell/                  (exists, 6 files) + AdaptiveAppleShellHost-type strays from root
│   ├── Library/
│   │   ├── Browser/            LibraryView* (9+), LibraryOutlineNode, LibraryViewComponents,
│   │   │                       DisplayAttributesStrip, NodeClassPicker, sorting/filter/column extensions
│   │   ├── Preview/            ImageViewer/* , QuickLookComponents, QuickLookPreviewViews,
│   │   │                       MediaStreamPreview            ← source-viewer surface
│   │   ├── Reader/             Reading/* (ImmersiveReaderView, DocumentTextReader, ReaderTabBar,
│   │   │                       PDFPageView†, PageImageGrid)  ← derived-knowledge surface
│   │   ├── Inspector/          (exists — pane chrome, tabs, presenter)   ← edit surface
│   │   ├── DocumentInspector/  (exists — document-scoped tabs; splits per #3439, stays separate)
│   │   ├── ImageEditor/        (exists)
│   │   └── Workspace/          (exists)
│   ├── Canvas/                 merge of Views/Canvas + Views/Spatial(2D) + CanvasScene/ — ONE canvas
│   │                           folder, one naming generation (Q4 decides 3D placement/name)
│   ├── Space/                  3D renderer (RealityKit) — pending Q4; do not touch until decided
│   ├── Workflow/
│   │   ├── Editor/  Nodes/  Canvas/  Execution/  Chains/  Inspector/
│   │   └── NodeConfigs/        (exists)
│   ├── Sidebar/
│   │   ├── Rows/  DragDrop/  Commands/
│   ├── KnowledgeGraph/
│   │   └── OntologyBrowser/ split per #1944 (31 direct files) into Entities/ Claims/ Toolbar/
│   └── … (Chat, Settings, Activity, Search, Automation, AIProviders, etc. — already ≤18 direct files, unchanged)
```

† `PDFPageView` sits in Reading/ today; whether PDF page rendering belongs to Preview (source) or Reader is a surface question — flag during the move, don't silently decide (Q4-adjacent).

Rules for the move worker: follow #3439's discipline — move reusable chrome only when it has >1 real consumer; never merge Inspector/ and DocumentInspector/; every batch shrinks `check_folder_organization.py` `KNOWN_VIOLATIONS` and never adds to it.

---

## 6. Shared vocabulary — concept → word, both sides

No vocabulary table exists (the "#104 table" referenced by #2571 and the reorg doc is a dangling pointer). This section is the seed table; it should land as `docs/contributor/architecture/vocabulary.md` and be referenced from AGENTS.md. **Canonical direction: frontend-first** (per closed #2565's settled approach), except where the UI itself is inconsistent.

### 6.1 Already aligned (keep, enforce)

`document`, `artifact`, `annotation`, `claim`, `entity`, `citation`, `note`, `activity`, `workflow`, `chain`, `batch`, `bookmark`, `provider`, `search` — same word both sides; folder names must use exactly these.

### 6.2 Verified disagreements (decision + recommendation each)

| # | Concept | Backend says | Frontend says | Recommendation |
|---|---|---|---|---|
| V1 | Grouping container in a library | `folders.py` route, tag `folders`, `docType == .folder` | `DocumentStore.collections` (SidebarItemRow.swift:148), UI mixes both | **`folder`** everywhere (Finder-like principle; the wire + docType already say folder). Rename the store property; UI copy follows |
| V2 | 2D spatial library view | URL paths `/api/mind-palace/...` (per reorg doc :95), `canvas.py`, `canvas_models.py`, `spatial_arrange.py` | `Views/Canvas` + `Views/Spatial` + `CanvasScene/` + `CanvasItemStore` | **`canvas`** (2D). Backend renames mind-palace paths + spatial_arrange in H8; frontend folds Spatial* files into Canvas naming |
| V3 | 3D view | (same mind-palace endpoints) | `Views/Space/` (`Canvas3DProjection`, `.threeD` mode) | Daniel decides Q4: `space` as the 3D mode name, or fold as `canvas` 3D mode. Reorg doc says 3D was retired; code says it's live — resolve the contradiction first |
| V4 | Knowledge graph | `knowledge/` package + `kg/` shim package + `kg_*` routes + tag `knowledge-graph` — **three spellings in one codebase** | `Views/KnowledgeGraph`, `KG*` type prefix | One rule: **`kg` is the sanctioned abbreviation in backend module/URL space; `KnowledgeGraph`/`KG` in Swift; `knowledge/` stays the real package** (it's the substantive one; `kg/` shim dies). Write the rule down so it stops drifting |
| V5 | Scheduled/triggered jobs | `schedules.py` + `triggers.py` + `orchestration.py` (no umbrella) | `Views/Automation`, `AutomationService` | **`automation`** as the umbrella (routes/automation/); keep schedule/trigger as the two member nouns |
| V6 | Research / agent / chat | `research_agents.py` ("no agent logic" — reorg doc :96), `chat.py`, `agent_memory.py` | `ResearchStore`, `Views/Research`, `Views/Chat` | **HOLD — #2571 owns this.** Hygiene only groups the files; no renames |
| V7 | Tree node vs document vs library item | `node_aliases.py`/`node_prototypes.py`, `documents.py`, `library_items.py` (library-items endpoints have **zero Swift references** — CLI-only per check_endpoint_usage KNOWN_GAPS) | `Document`, `LibraryOutlineNode`, `NodeClassPicker` | **`document`** = the source object today; **`node`** = tree entry (reserved for #2081 node-model work); **`library item` is retired vocabulary** — audit whether the CLI-only endpoints are dead (§7) |
| V8 | Hand-written API wrappers | — | `*ServiceGenerated.swift` suffix on hand-written files (AGENTS.md:375) | Drop the suffix (`ArtifactService.swift`); truly generated code lives only in `fichero-api-client/`. Q7 |

Backend route subpackage names in §4.2 and frontend folder names in §5 already apply these recommendations; if Daniel overrules any row, the trees rename accordingly before execution.

---

## 7. Dead code — the reliable method

Naive whole-repo "no references" scanning produced 26,000 false positives here (decorator-registered routes, pytest fixtures, SwiftUI previews, Codable synthesis). The reliable instruments are the repo's own conservative guardrails. Method:

1. **Swift files:** `check_dead_files.py` is the authority — it already skips entry points/previews and its `KNOWN_VIOLATIONS` (:41+) is a pre-triaged candidate backlog with issue notes (#1945/#2955). Work = **burn the list to zero**: each entry gets deleted (after `git log` sanity + full suite) or wired/annotated with a scanner-blind-spot note. "Removed, not allowlisted" = the allowlist ends empty except documented scanner blind spots (same-file helper types), which are the scanner's problem, not dead code.
2. **Endpoints:** `check_endpoint_usage.py` (--json) enumerates every OpenAPI operation vs app+CLI usage; its `KNOWN_GAPS` (:37) lists ~dozens of "cli-only" endpoints. Triage each: intentionally CLI-only (keep, re-annotate with rationale) vs vestigial (delete route + regen client). The `library-items` family (V7) is the first candidate.
3. **Python modules:** no engine equivalent of check_dead_files exists. Two-instrument proposal: (a) **runtime evidence** — run the FULL pytest suite plus a scripted CLI smoke under `coverage run`; modules with zero executed lines are candidates only; (b) **registration cross-check** — a candidate is deletable only if it is not imported anywhere (`check_references`), not registered in `api/main.py` route specs, not a workflow tool, not a CLI command, and not an alembic/migration hook. Wrap (b) as a new conservative `scripts/check_dead_python.py` twin so the state persists as a burndown list instead of a one-off analysis. Known KEEP regardless of scan results: `kg_sparql`/rdflib (wanted W3C query layer — verify live callers before touching any kg router, per standing instruction).
4. **Shims are scheduled dead code:** every shim this plan creates is logged in a single tracking issue at creation; H9 deletes them all; a one-line check (count of `sys.modules[__name__]` shims must be ≤ last recorded count) prevents new permanent shims.
5. **Deletion gate:** every deletion commit is deletion-only, cites its evidence (guardrail output + coverage + reference check), and passes the full suite. Sweep for siblings: when one dead file falls, audit its whole class (fix-then-sweep rule).

---

## 8. Ordering by risk (lowest first) — with reasoning

1. **Docs/READMEs/publicization** (#2556, #2559, #2555, #2564, #2702) — zero code risk; independently valuable; makes the repo readable to strangers even before any move.
2. **Dead-code burn-down** — deleting before moving shrinks every later batch and baseline; deletions are cheap to verify (build + suite) and cheap to revert.
3. **pbxproj synchronized-group conversion** — one scary-looking but behavior-neutral commit, gated by build-product comparison; it *reduces* the risk of everything after it. Done before any Swift move.
4. **Engine `api/routes/` grouping** (#2569) — lowest-risk *engine* move, but for the corrected reason: not "only main.py imports them" (false — 157 outside importers, §1.1) but because (a) route modules are leaves in the import graph (they import the world; almost nothing imports them except for schemas), (b) the `sys.modules` shim pattern is proven in-repo and absorbs all 157 sites unchanged, (c) registration is centralized in one import block (`main.py:1301`) + one spec list, and (d) the contract/endpoint guardrails will scream if any route drops off the OpenAPI surface.
5. **Engine loose modules** (#2566) — riskier than routes: these ARE the god-nodes (db 4.5k ln, llm 4k, models 2.3k) with hundreds of import sites. Same shim pattern, but ordered by blast radius: importers-finish → mcp → text → security/transport → library → llm → persistence (db last) → models.py (last of all, or never — Q5).
6. **Frontend folder moves** — after conversion these are plain `git mv` + baseline rewrites; risk is mostly baseline churn + the serialized-build bottleneck. Per-surface batches.
7. **Frontend Models/Services split + Generated-suffix rename** — mechanical but touches the most files per commit; needs the naming decision first.
8. **Wire vocabulary alignment** (mind-palace→canvas paths, tag/operation_id alignment with the new routes tree, client regen, Swift call-site update) — highest coordination cost, one coordinated pass, exactly the #2565 playbook. Last because everything before it reduces its surface.

---

## 9. Architecture docs to update (by path)

Must change in the same PRs as the moves (`check_docs_paths.py` enforces this):

- `AGENTS.md` — §Key Paths (:353), §Working in Xcode (:134 — retire add-swift-file.rb instructions post-conversion), §Docs Placement (:317), §Code Navigation (:273); add pointer to the new vocabulary doc.
- `docs/contributor/design/swiftui-app-reorg.md` — **stale on two counts** (RealityKit/3D "removed" vs live `Views/Space/SpaceSceneView.swift`; Library file counts). Update to match code or mark superseded-by this plan. Docs describe what is BUILT.
- `docs/contributor/architecture/fichero/key_files.md`, `overview.md`, `observable_data_layer.md` — path references to Views/Models/Services.
- `docs/contributor/architecture/fichero-engine/key_files.md`, `overview.md`, `KG_ENDPOINTS.md` — route paths and module names.
- `docs/contributor/architecture-overview.md`, `ui-map.md`, `swiftui-development-standards.md`, `backend-development-standards.md`, `setup-and-contributing.md`, `openapi-and-clients.md`.
- **New:** `docs/contributor/architecture/vocabulary.md` (§6 table) and a short "where does a new file go" section in `CONTRIBUTING.md` — the literal acceptance test, written down.
- `mkdocs.yml` nav + `scripts/check_docs_paths_allowlist.json` as paths move.
- Guardrails-as-docs: `scripts/check_folder_organization.py` (`MIXED_CONCERN_DIRS`/`SUGGESTED_SUBFOLDERS` updated to the §5 targets), `scripts/check_xcode_registration.py` (retire/rewrite post-conversion).
- `README.md`, `fichero/README.md`, `fichero-engine/README.md` (#2556).

---

## 10. Execution sequence — batches, each worker-sized, gateable, revertable

Each batch = one PR, full gate (backend: full pytest with correct PYTHONPATH + FICHERO_RUN_* flags; frontend: Xcode MCP build + tests + launch smoke; always: all check_*.py + baseline_move_check), revert = `git revert` of one PR. No two concurrent batches on overlapping surface.

| # | Batch | Contents | Owner sizing | Gate specifics |
|---|---|---|---|---|
| H0 | Prerequisites | Daniel answers §12; pbxproj conversion **spike in throwaway worktree**, then real conversion commit; write `scripts/baseline_move_check.sh`; fix stale swiftui-app-reorg.md; fix milestone assignments (#2566/#2569/#2556 → milestone 177) | manager, 1-2 sessions | build-product comparison, macOS + iOS builds, launch smoke |
| H1 | Docs & publicization | #2556 READMEs, #2559 CONTRIBUTING, #2555 memory/HISTORY triage, #2564 .claude/.codex table, #2702 de-personalize + secrets grep, vocabulary.md from §6 | docs worker, 2-3 sessions | check_docs_paths, check_docs_publication |
| H2 | Dead code | check_dead_files KNOWN → 0; #3433; endpoint KNOWN_GAPS triage incl. library-items; check_dead_python.py built + first burn | 1 worker, 2 sessions | full suites both sides |
| H3 | Routes grouping (#2569) | one domain subpackage per commit, order: kg → citations → search → automation → providers → workflows → documents → library → auth → system → research(group-only); shims at old paths; main.py import block updated per commit | codex worker, ~10 commits / 2-3 sessions | contract walker + endpoint-coverage + full backend suite + baseline_move_check per commit |
| H4 | Loose engine modules (#2566) | one subpackage per session: importers-finish (delete 10 shims) → mcp → text → security+transport → library → llm → persistence(db last) | codex worker, ~7 sessions | same as H3; db/llm stages get extra soak (run the heavy write-suites) |
| H5 | Execution consolidation (#2594) | audit-first: schemas out of api/routes/workflow_execution, runner decoupled from route layer (fixes execution/runner.py:28 inversion) | 1 worker, audit + 1-2 sessions | full workflows suite |
| H6 | Frontend Views moves | per-surface PRs: Library(Browser/Preview/Reader) → Workflow → Sidebar → OntologyBrowser → Components purge → Canvas/Spatial/Space consolidation (needs Q4) | swiftui worker, ~6 PRs | MCP build+tests, launch-stress (searchable-crash class), check_folder_organization shrinks monotonically, baseline_move_check |
| H7 | Models/Services split (+ rename if Q7 yes) | Models/Stores+Domain; Services/API+Engine+Platform; Generated-suffix drop as its own mechanical commit | swiftui worker, 2-3 PRs | same as H6 |
| H8 | Wire vocabulary | mind-palace→canvas path rename, tags/operation_ids aligned to routes tree, OpenAPI regen, Swift call-site update — one coordinated pass (#2565 playbook) | manager-led, 1 coordinated PR | openapi_client_parity, endpoint_usage, full suites both sides |
| H9 | Closeout | delete all shims (routes + engine + kg/ package), rewrite stragglers, kg/ filename-prefix drop, guardrail KNOWN_* down to documented blind spots only, docs sweep, close/verify all milestone issues | manager, 1-2 sessions | everything green, check_docs_paths, milestone review |

Rough shape: ~25-30 PRs over the two milestones. H1/H2 can run parallel to H0 (disjoint surface). H3-H5 (engine) can run parallel to H6-H7 (frontend) — different lanes, disjoint files — but never two engine batches or two frontend batches at once.

---

## 11. What I am NOT sure of (honest list)

- **Stale-baseline behavior verified in only 4 of ~30 path-keyed guardrails.** I read `check_native_controls/appkit_imports/dead_files/shell_chrome`; the rest are asserted to follow the same post-#3339 discipline but not individually verified. The H0 baseline-diff harness catches deviants regardless.
- **pbxproj conversion end-state**: I verified the preconditions (single target, no per-file flags, no orphan files, precedent in test targets) but have not performed a conversion of this project. Hence spike-first, and the honest fallback in §3.
- **The Views/Space contradiction**: whether 3D was deliberately re-added after the reorg doc declared it removed, or never fully removed. Needs `git log --follow` on `Views/Space/` before anyone consolidates canvas folders (Q4 depends on it).
- **`import` sed artifact**: my per-module import counts (§1.1) come from a one-line sed over grep output; the per-module numbers are approximate (the aggregate 157-files figure is exact). Directionally solid, not decimal-precise.
- **Route→subpackage assignments in §4.2** are 90% confident; ~6 modules (`notes`, `batch`, `tasks`, `multilingual`, `mcp_servers`/`mcp_tools`, `canvas`) are judgment calls flagged in Q6.
- **Milestone #237** ("Backend Hygiene & Python Structure", 0 open) — I don't know if it's a finished predecessor or an empty duplicate of #177.
- I did not measure how much of `Models/` is store vs value type; the Stores/Domain split sizes in §5 are estimates from filenames.

---

## 12. Questions for Daniel

Each is genuinely yours to decide; my recommendation first.

- **Q1 — #2577 top-level layout.** Promote `fichero-cli` / `fichero-mcp` / `web` to top-level now? **Recommendation: no — defer.** Neither `web/` nor `fichero-mcp/` exists as a top-level component today (verified). Keep the two-component monorepo (`fichero/`, `fichero-engine/`), document the *future* component map in README, and promote a component only when it gains an independent build/release. Promoting empty dirs before open-sourcing adds confusion, not clarity.
- **Q2 — pbxproj synchronized-group conversion.** Approve as prerequisite H0? **Recommendation: yes**, spike-first, with the §3 checklist and the add-swift-file.rb fallback if the spike fails.
- **Q3 — V1 folder vs collection.** **Recommendation: `folder`** everywhere (wire + docType already say it; Finder-like).
- **Q4 — Canvas/Spatial/Space.** Is the RealityKit 3D view (`Views/Space/`) a live product surface (contradicting swiftui-app-reorg.md's "removed")? If live: is the pair of words **canvas (2D) / space (3D)**? **Recommendation: canvas/space if 3D is staying**; either way, `Views/Spatial/` (old naming generation) folds into `Views/Canvas/`, and the backend `mind-palace` paths rename to `canvas` in H8. Also: does `PDFPageView` belong to Preview (source) or Reader?
- **Q5 — `models.py` god-node.** Move it into a `models/` (or split by domain) with a long-lived shim, or leave it top-level permanently as documented core? **Recommendation: leave top-level for this milestone**; splitting it is content work, not hygiene, and the shim risk isn't paid for by readability gains yet.
- **Q6 — judgment-call homes** (say yes/adjust per line): `notes` route → `documents/` (rec) or own `notes/`; `pykeen_inference.py` → `llm/` (rec) or `knowledge/`; `image_ops.py` → `text/`-renamed-`media/`? (rec: put `image_ops` + `ocr_geometry` in `media/`, keep `text/` for language); `geo.py` → `library/` (rec) or `knowledge/`; `tasks`+`batch` routes → `system/`/`documents/` as drawn (rec) or both → `workflows/`.
- **Q7 — drop the `*ServiceGenerated.swift` suffix** on the 20+ hand-written wrappers (rename to `*Service.swift`, resolving collisions like `ChatService`/`ChatServiceGenerated` by merging or `*APIService`)? **Recommendation: yes** — the suffix actively misleads strangers (AGENTS.md:375 has to warn about it), which fails the acceptance test.
- **Q8 — research/chat/agent hold.** Confirm H3 only *groups* `routes/research/` and all renaming waits for #2571's design decision. **Recommendation: confirm hold.**
- **Q9 — knowledge-graph spelling rule (V4).** Accept `kg` as the sanctioned backend abbreviation (packages/URLs) with `knowledge/` as the surviving package and `KnowledgeGraph` in Swift? **Recommendation: yes** — one written rule beats a churny rename either direction.
- **Q10 — board hygiene.** Move #2566/#2569/#2556 to milestone 177 (they're engine/docs issues on the frontend milestone) and clarify/retire milestone #237? **Recommendation: yes, both.**

---

## 13. Daniel's decisions (2026-07-13) — these OVERRIDE the recommendations above

| Q | Decision | Note |
|---|---|---|
| **Q1 / #2577** | **Top-level = CLIENTS + engine.** `cli/`, `mcp/`, `web/`, `fichero/` (SwiftUI) are clients; `fichero-engine/` is the backend. **`cli` and `mcp` work but are in the wrong place** and should be promoted. **Caveat Daniel raised:** there is also an *internal* MCP and an *internal* CLI — so the split is not clean, and `mcp` is "light" for that reason. **`web/` is far more work and is NOT happening any time soon** — do not create an empty `web/` dir. | OVERRIDES the planner's "defer everything". Promote `cli` + `mcp` only; resolve the internal-vs-external question first (see #2576, #2562). |
| **Q4** | **`canvas` (2D) and `space` (3D) — both are LIVE.** The `swiftui-app-reorg.md` claim that 3D was removed is WRONG and must be corrected. **Delete the old code, and incorporate Canvas + Space into ONE system** — today `Views/Canvas/`, `Views/Space/`, `Views/Spatial/` and top-level `CanvasScene/` are four folders for one domain, in two naming generations. Daniel: *"right now it's not working well."* **Check the Library view first — this was already partly done there; get it right, don't re-invent.** | Confirms 3D is live. Old `Spatial*` naming generation is the dead code to remove. |
| **Q7** | **Drop the `*ServiceGenerated.swift` suffix.** Rename to `*Service.swift`; truly generated code lives only in `fichero-api-client/`. | As recommended. The suffix misleads (AGENTS.md:375 warns about it). |
| **V1** | **`collection` everywhere — NOT `folder`.** | **OVERRIDES the planner's `folder` recommendation.** The backend renames toward `collection` (routes, docType, URLs), not the frontend toward `folder`. Larger churn than the recommended direction — sequence it as its own batch with the move protocol. |

### Consequences to fold into the execution sequence
- **V1 is now a backend-renaming batch**, not a one-line Swift rename. `folders.py`, the `folders` tag/prefix, and `docType == .folder` all move to `collection`. Wire + DB + OpenAPI + client regen. Treat as a content batch (NOT move-only) with full-suite gating.
- **Q4 becomes a real consolidation batch**, not just a folder move: fold `Views/Spatial/` + `CanvasScene/` into one Canvas/Space system, delete the superseded naming generation, and fix `swiftui-app-reorg.md`. Read the Library view's existing treatment first and match it.
- **Q1**: promote `cli` and `mcp` to top-level, but FIRST answer: what is internal vs external MCP/CLI? (#2576 = external MCP over HTTPS; #2562 = fichero-cli top-level split.) Do not create `web/`.
