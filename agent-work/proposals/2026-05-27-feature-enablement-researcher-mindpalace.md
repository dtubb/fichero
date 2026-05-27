# Feature Enablement Decomposition — Researcher & Mind Palace (3D/2D Space)

**Date:** 2026-05-27
**Lane:** planner (PLAN only — no implementation)
**Inputs:** `agent-work/proposals/2026-05-27-endpoint-frontend-coverage.md` (#1288 audit), memory `feedback_kg_logic_in_backend`
**Verified via:** jcodemunch (`plan_turn` model=claude-sonnet-4-6, high confidence both), direct reads.

---

## TL;DR — the premise needs correcting

Both features were framed as "BUILT but feature-gated OFF — flip a flag." That is **only half right**:

- ✅ **Backend is fully built** for both (routers, models, CRUD, real tools).
- ✅ **The OpenAPI contract already includes them** — both committed `openapi.json` copies under `fichero/fichero-api-client/Sources/` contain all 40 `/api/research` + `/api/mind-palace` paths, so the **generated Swift typed-client already exposes these operations at build time**. No OpenAPI regen needed.
- ✅ **They are reachable in-app today** — `EmbeddedBackendService` launches the engine with `FICHERO_FEATURE_TIER=dev` (per the #1288 audit), and both routers live in `_DEV_ROUTE_SPECS` (`api/main.py:854-871`), so the running app process can already call them.
- ❌ **There is NO frontend** — `FeatureManager.swift` has **no `research` and no `mind-palace`/`spatial` flag** (only workflows/search/chat/agents/automation/mcp/integrations/activity/batches); there is **no `ResearchService`, no `MindPalaceService`, no view, and no navigation entry**. The only spatial-named Swift (`KGTemporalSpatial.swift`, `KGMapView.swift`) is the #1266/#1267 KG timeline/map — unrelated.

**So neither is "pure enablement."** The blocker is a missing SwiftUI surface, not a flag. The work is **frontend-heavy, backend-complete**. Per `feedback_kg_logic_in_backend`, that is the correct shape: the backend already owns positions, viewport, arrangement, dedup, and research data; **the Swift views only render and persist back**.

One genuine release-tier decision (shared, below): whether to **promote both routers from `_DEV` to `_CORE`** so shipped *release-tier* engines (not just the dev-tier embedded one) serve them.

---

## Verified backend inventory

### Researcher — `/api/research` (dev tier)
- `api/routes/research_agents.py` — aggregator router; mounts three sub-routers:
  - `research_crud.py` — Project / Plan / Task / Step CRUD (`create_*`, `get_*`, `list_*`, `update_*`).
  - `research_notes.py` — Search Sources / Notes / Checklists CRUD.
  - `research_tools.py` — **real implementations** (not stubs): `web-search`, `browser-navigate`, `document-fetch`, all `httpx.AsyncClient` with SSRF redirect guard (`_safe_http_get`), timeouts, connection limits.
- Endpoints (from contract): `/api/research/{projects,plans,tasks,steps,notes,checklists,sources}` + `/api/research/tools/{web-search,browser-navigate,document-fetch}`.
- **No autonomous agent runner** — there is no LLM loop that plans→searches→writes. `/api/research` is structured data + sandboxed tools. An auto-driving agent is *new backend work* and overlaps the intentionally-gated `orchestration`/`agents/write` policy (#1151) — **out of scope for enablement**.

### Mind Palace — `/api/mind-palace` (dev tier)
- `api/routes/mind_palace.py` — full CRUD: rooms, nodes (`place_node`/`move_node`/`remove_node`), connections, stacks (`create_stack`/`add_to_stack`/`remove_from_stack`), notes, **viewport** (`get_viewport`/`save_viewport`), plus Tinderbox **import/export** (`/import/tinderbox`, `/export/tinderbox`).
- `spatial_models.py` — the data model is explicitly 3D-and-server-owned:
  - `SpatialNode`: `position_x/y/z`, `rotation_x/y/z`, `scale`, `node_type` (source/claim/note/entity/transcription), `source_id`.
  - `SpatialConnection`: typed links (evidentiary/semantic/ontological/hermeneutic/user_drawn) + `link_subtype`.
  - `SpatialStack`, `NativeNote` (linked_claim/source/entity ids), `SpatialViewport` (camera_x/y/z, zoom, focus_node, bookmark), `RoomSceneSummary`, `ArrangementType` (semantic/chronological/thematic).
- **Layout/arrangement is backend state**, not client math — exactly what `feedback_kg_logic_in_backend` prescribes.

---

## Shared decisions / tasks (apply to both)

- **S0 — Tier decision (backend, XS, needs Daniel/#1151 sign-off):** keep both in `_DEV_ROUTE_SPECS` and rely on the dev-tier embedded engine, **or** promote `mind_palace.router` and `research_agents.router` into `_CORE_ROUTE_SPECS` (`api/main.py`) like KG (#967) and chains (#1151) were. Promotion is the clean path for shipped release builds; re-run `fichero-engine/scripts/sync_openapi_schema.sh` + `BuildProject` afterward (per `feedback_backend_merge_needs_swift_build`). **No new endpoints required either way** — the contract already covers them.
- **S1 — New FeatureManager flags (frontend, XS):** add `research` and `mindPalace` (or `spatial`) `@AppStorage` flags + `isResearchEnabled`/`isMindPalaceEnabled` accessors, defaulted **off** in `resetToV001()` and bump `releaseProfileVersion`. These are **new flags, not flips** — none exist today.
- **S2 — File registration discipline:** every new `.swift` file must be registered with `ruby scripts/add-swift-file.rb <path>` (main target is PBX-referenced, not sync'd — Rule 10). Three-leg gate on completion: `swiftlint` + Xcode `BuildProject` + `RunAllTests` (`feedback_three_leg_check`).
- **S3 — Rendering-only contract:** Swift consumes the generated typed client and renders/persists; it must **not** compute layout, dedup, or arrangement client-side (`feedback_kg_logic_in_backend`). Node positions, viewport, and arrangement come from / go back to the backend.

---

## (A) RESEARCHER — task list

**Nature:** ~95% frontend. Backend complete for a manual/tool-driven research workspace. Autonomous agent = separate future work (gated).

| # | Task | Layer | Size | Notes |
|---|------|-------|------|-------|
| A1 | Add `research` flag to `FeatureManager.swift` (+ `resetToV001` default off, version bump) | FE | XS | New flag; gate the nav entry + view |
| A2 | `ResearchService.swift` wrapper over the generated client — projects/plans/tasks/steps, notes/checklists/sources, and the 3 tool calls | FE | M | Typed client already exposes ops; follow the OpenAPI-typed-field rule (Rule 4) when building request bodies |
| A3 | Swift view-models / display models for Project→Plan→Task→Step + Note/Checklist | FE | S | Mirror Pydantic shapes from the generated `Components.Schemas.*` |
| A4 | `ResearchView` — projects list → plan detail → tasks/steps; notes & checklists panel; a "run tool" affordance (web-search/fetch) writing results into notes/sources | FE | L | Net-new multi-pane UI. Use `HStack` + `ResizableDivider`, not nested `NavigationSplitView`/`.inspector()` (`feedback_swiftui_splits`) |
| A5 | Navigation entry (sidebar section or top-level mode) gated by `isResearchEnabled`; register all new files via `add-swift-file.rb` | FE | S | |
| A6 | Three-leg verify (swiftlint + build + RunAllTests) + a Swift round-trip test against the embedded engine | FE | S | Don't run `RunAllTests` against Daniel's live backend (`feedback_runalltests_pollutes_dev_backend`) |
| A7 *(optional, future)* | Autonomous research-agent runner (plan→tool→note loop) | **BE** | L+ | **New backend work**, collides with `orchestration`/`agents/write` (#1151). Explicitly out of enablement scope — file separately if Daniel wants it. |

**Backend work needed for MVP:** none (besides shared **S0** tier decision). **Pure enablement?** No — frontend must be built.

---

## (B) MIND PALACE + 3D/2D SPACE — task list

**Nature:** 100% frontend for the data plumbing; the spatial *view* is the real lift. Backend owns positions/connections/stacks/viewport/arrangement already.

| # | Task | Layer | Size | Notes |
|---|------|-------|------|-------|
| B1 | Add `mindPalace` (or `spatial`) flag to `FeatureManager.swift` (+ default off, version bump) | FE | XS | New flag |
| B2 | `MindPalaceService.swift` wrapper — rooms, nodes (place/move/remove), connections, stacks, notes, viewport (get/save), Tinderbox import/export | FE | M | Generated client covers all; `MindPalaceListResponse`/`MindPalaceDeletedResponse` already in the schema |
| B3 | Spatial view-models (Room, Node, Connection, Stack, Viewport) | FE | S | Map `Components.Schemas.SpatialNode` etc. |
| B4 | **2D canvas view (MVP)** — render `SpatialNode` by `position_x/y`, draw `SpatialConnection` edges, drag-to-reposition → `move_node`, persist camera/zoom → `save_viewport`; room switcher | FE | L | Pragmatic first surface. Lessons: `feedback_state_binding_through_value_copy`, `feedback_dropdestination_stacking`. Layout is read from backend, written back — no client-side autolayout |
| B5 | **3D view (phase 2)** — SceneKit/RealityKit scene driven by `position_x/y/z` + `rotation_*` + `scale`, camera from `SpatialViewport` | FE | XL | The heavy lift; gate behind same flag or a sub-flag. Defer until 2D proves the data round-trip |
| B6 | Connection-type styling + node-type rendering (source/claim/note/entity/transcription), stack grouping UI | FE | M | Pure render of backend enums |
| B7 | Navigation entry gated by flag; register files via `add-swift-file.rb`; three-leg verify | FE | S | |
| B8 *(optional)* | Surface Tinderbox import/export in a menu (backend already implements both) | FE | S | High value, low cost once B2 exists |

**Backend work needed:** none (besides shared **S0** tier decision). **Pure enablement?** No — the 2D/3D space view is net-new SwiftUI; 3D specifically is the largest single item across both features.

---

## Suggested sequencing

1. **S0 tier decision** (Daniel/#1151) — gates whether release builds serve these or only the dev-tier embedded engine.
2. **S1 flags** (both, trivial) — unblocks gating the new surfaces.
3. **Researcher A2–A6** first (lower risk: list/detail UI over existing CRUD; no 3D).
4. **Mind Palace B2–B4** (service + 2D canvas) — ships the spatial concept without the SceneKit cost.
5. **Mind Palace B5** (3D) last, only after the 2D round-trip is proven.

---

## Proposal path + one-line summaries

**Path:** `agent-work/proposals/2026-05-27-feature-enablement-researcher-mindpalace.md`

- **(A) Researcher:** Backend + OpenAPI client fully built and reachable; NOT pure enablement — needs a new `research` FeatureManager flag, a `ResearchService` wrapper, a project/plan/task/notes SwiftUI surface, and nav wiring (~M–L, frontend-only; autonomous agent is separate, gated backend work).
- **(B) Mind Palace / 3D-2D space:** Backend owns all spatial state (positions, connections, viewport, arrangement, Tinderbox I/O) and the client schema is generated; NOT pure enablement — needs a new `mindPalace` flag, a `MindPalaceService`, a 2D canvas MVP (render+persist positions), nav wiring, and a deferred 3D SceneKit view (~L now, XL for 3D; frontend-only).
