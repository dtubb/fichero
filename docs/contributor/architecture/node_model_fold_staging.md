<!-- Staging/planning doc. Current-state rows re-verified 2026-07-18 (F4/F5 drift flagged inline); the plan itself is unchanged. -->

# Node-Model Subsystem Fold — Staging Doc (#2591 / EPIC #2081)

> **Status: STAGED, not implemented.** Implementation deferred to after the TestFlight release per Daniel, 2026-06-26: the node-model fold is top-tier thinking but must not block TestFlight. This doc is the path — it ties each fold target to the EPIC #2081 foundation it blocks on, sequences the slices, and links issues/milestones so we know how to continue. Do not start the fold before TestFlight.
>
> Companion audit: #2592 (view modes are client-only) — closed 2026-06-26, confirmed no server coupling to a view mode. The legacy Mind Palace `/rooms/*` backend retirement identified there lives here, under #2591.
>
> **Update 2026-07-18 (current-state re-verify):** two fold rows below have
> already moved since the 2026-06-26 grounding, via other work (not this fold):
> - **F5** — `api/routes/mind_palace.py` and the `/rooms/*` endpoints are **gone**;
>   `/api/mind-palace` was retired and replaced by `/api/canvas` (`api/routes/canvas.py`,
>   with `/canvas-layout` + `/canvas-items`), per the #2565/#3750 rename. So the
>   backend endpoint-retirement half of Fold-E is effectively done; the remaining
>   Fold-E work is the node-model *reshape*, not the router removal.
> - **F4** — a bookmarks route now exists (`api/routes/bookmarks.py`), so the
>   "not built / 0 symbol matches" note is stale; whether it satisfies the
>   bookmark-as-node vision is for the fold author to assess.
>
> The plan below (P1–P6 foundation, slice sequence) otherwise stands. Rows are
> left as-authored except where flagged inline.

## Design north-star (EPIC #2081, Daniel + manager 2026-06-11; CONTENT-vs-INFRA split Daniel 2026-06-23)

A library is **one tree of nodes**. Every node has a structural kind (`DocType`) **and** a prototype (class). Folder ≈ workspace ≈ room are all *container prototypes* — they differ by class, not by structure. Entities are first-class filable nodes. Aliases are reference nodes (point at another node). Tasks/milestones/notes are prototype *attributes* any container can carry. Views (list/table/icons/map/graph/3D) render any container's contents — they are renderers, not subsystems (confirmed client-only by #2592).

**CONTENT folds into the library** (node types + attributes + relations + view modes): workspaces/tasks/issues/aliases/bookmarks/saved-searches, plus the legacy Mind Palace spatial subsystem.

**PROCESS / INFRA stays separate** (workflows / actions / providers / auth): background reindex/metrics/repair tasks are infra, not content — they do NOT fold.

This is the information-architecture foundation the Mac UI reform (#2030) sits on.

## Fold table (grounded in code, verified 2026-06-26 via jCodemunch index `local/fichero-29aa4eed`)

| # | Current subsystem | Location (file:symbols) | Target construct | Foundation it blocks on | CONTENT / INFRA | Fold slice |
|---|---|---|---|---|---|---|
| F1 | Saved searches | `api/routes/search.py` — `SavedSearch` CRUD + 5 `_action_*` registry actions (save/list/update/duplicate/delete/reorder), `search.py:994-1209` + actions `1556-1737` | A node **type/attribute** (a saved-search node, or a `saved_query` attribute on a container) | Prototype/class system (P1) — needs node-type definitions to fold *into* | CONTENT | Fold-A |
| F2 | Research workspace | `api/routes/research_crud.py` — `ResearchProject` CRUD (`create_project`…`delete_project`, 62-172) + `library_destination_folder_id` | A **container prototype** ("workspace" = a folder prototype that is chat-able + carries tasks) | Prototype/class system (P1) + Workspace/room=folder prototype (P5) | CONTENT | Fold-B |
| F3 | Research plans/tasks/steps | `api/routes/research_crud.py` — `ResearchPlan`/`ResearchTask`/`ResearchStep` CRUD (`create_plan`…`update_step`, 180-639) | **Prototype attributes** (tasks/milestones/notes) on any container; `ResearchStep` → a task sub-attribute or child node | Generalize tasks/milestones/notes to any container (P3) + Prototype (P1) | CONTENT | Fold-C |
| F4 | Bookmarks | **Not built** — 0 symbol matches for `bookmark` in `api/routes/*.py` | A new **node type** (bookmark-as-node) or a reference relation (alias) | Alias node kind (P2) — bookmarks are closest to aliases (reference to a target) | CONTENT | Fold-D (net-new, not a collapse) |
| F5 | Legacy Mind Palace spatial subsystem | `api/routes/mind_palace.py` — `/rooms`, `/nodes`, `/connections`, `/stacks`, `/notes`, `/viewport` (178-820); still mounted in `_CORE_ROUTE_SPECS` at `/api/mind-palace` (promoted dev→release for 0.0.2); called by CLI `cli/client.py` (`mp_list_rooms` + scene/viewport/focus/suggest-arrangement, 1523-1866) + MCP (`mcp_full.py`, `mcp_server.py`) | **Positions → item attributes** (#2293/#369 already persists positions via `/canvas-layout`); **connections → `LibraryItemLink`** (#2636 shipped the general links endpoint at `api/routes/library_links.py`); **stacks/notes → node types/attributes** | Alias node kind (P2) for reference links; Prototype (P1) for room-as-container; Entities-as-filable (P4) for the spatial node set | CONTENT | Fold-E (largest; needs CLI/MCP migration) |
| — | Background tasks | `api/routes/tasks.py` — `BackgroundTask` (reindex/metrics/vector-repair/kg-metrics), `create_reindex_task`…`get_task_system_health` | **Stays separate** — these are INFRA (reindex/metrics/repair), not content nodes | — | INFRA | **No fold.** Do not collapse. |

Verified-live: the SwiftUI spatial view no longer drives from the `/rooms/*` endpoints — it uses a pure projection over library data (`Services/SpatialLibraryProjector.swift`; the file was named `MindPalaceLibraryProjector` when this row was authored). As of the 2026-07-18 update above, the `/rooms/*` endpoints are gone entirely, so there is no longer a live `/rooms/*` caller surface to migrate.

## Foundation dependencies (EPIC #2081 sub-issues — currently `[ ]` gaps, not yet filed)

EPIC #2081's "Current state" (verified in code) shows the foundation is **STUBBED/MISSING**. These six sub-issues must land before the folds. They are listed in #2081 as gaps to build; **file each as a separate issue** in the **Node Model & Endpoint Unification** milestone before starting.

- **P1 — Prototype/class system.** Prototype *definitions* with inheritable attributes/behaviors (Tinderbox-style); `Document.prototype_key` (models.py:180, currently a string tag) resolves to a real definition. *Keystone — F1, F2, F3, F5 all block on this.*
- **P2 — Alias node kind.** A reference node that points at another node; resolves to its target; appears in any container; never duplicates content. *Keystone — F4 (bookmarks) + F5 (connection→reference) block on this. Highest leverage: it is the relation #2591 explicitly calls out ("Aliases = reference relation").*
- **P3 — Generalize tasks/milestones/notes to any container.** As prototype attributes; add a `Milestone` model; any folder/room can carry them. *F3 blocks on this.*
- **P4 — Entities as filable library nodes.** Drop a `KnowledgeEntity` (currently a separate KG layer) into a folder; focusing it surfaces its documents (entity-as-collection). *F5's spatial node set benefits; also the EPIC's own gap.*
- **P5 — Workspace/room = a folder prototype.** Unify `ResearchProject` + Mind-Palace room onto the container-prototype model; chat-able. *F2 blocks on this.*
- **P6 — Chat/agent scopes to any node/container.** Ties to #2067 agent-as-principal (the agent edits nodes like a user). *Orthogonal enabler; not a hard fold blocker.*

Recommended filing order: **P2 (alias) and P1 (prototype) first** — they are the two keystones and they unblock the most folds. P3, P5, P4 follow. P6 in parallel.

## Slice sequence (dependency-ordered, tied to issues + milestones)

All work targets the **Node Model & Endpoint Unification** milestone.

**Phase 0 — File the foundation (no code).** File P1–P6 as issues under the milestone (bodies lifted from #2081's gap list). Assignee: dtubb. This is the gating step — nothing below starts until P1 + P2 land.

**Phase 1 — Foundation keystones (post-TestFlight).**
1. P2 Alias node kind — new `DocType.alias` (or reference node); resolver; appears-in-container; no-copy semantics. Unit test: alias resolves to target, deleting target surfaces a dangling reference (raise, not silent fallback — per the prefer-raise rule).
2. P1 Prototype/class system — prototype definitions table + `prototype_key` resolution + attribute inheritance. Unit test: a container prototype inherits attributes from its parent.

**Phase 2 — Folds (each gated on the foundation it blocks on).**
3. **Fold-A — Saved searches → node type/attribute** (smallest fold; gated on P1). Migrate `SavedSearch` storage to a node-type/attribute; keep the 5 `_action_*` registry actions working via the action layer (#1848) so audit/undo stays intact. Regression test: saved-search CRUD round-trip + reorder.
4. **Fold-D — Bookmarks as a node type / alias relation** (net-new; gated on P2). Define bookmark-as-node (or bookmark-as-alias). This is "create as a node type," not "collapse an endpoint."
5. **Fold-C — Research plans/tasks/steps → prototype attributes** (gated on P1 + P3). `ResearchTask`/`ResearchStep`/`Milestone` become attributes on any container; `ResearchPlan` becomes a container prototype attribute. Regression test: research workspace CRUD + task/step lifecycle.
6. **Fold-B — Research workspace → folder prototype** (gated on P1 + P5). `ResearchProject` → a "workspace" container prototype (chat-able, carries tasks, holds aliases). Regression test: project CRUD + `library_destination_folder_id`.
7. **Fold-E — Legacy Mind Palace `/rooms/*` retirement** (largest; gated on P1 + P2 + P4; last). Migrate CLI (`cli/client.py` mp_* methods) + MCP (`mcp_full.py`, `mcp_server.py`) off `/rooms/* /nodes/* /connections/*` onto the library/node + `LibraryItemLink` (#2636) + item-attribute positions (#2293/#369). Then unmount the legacy router from `_CORE_ROUTE_SPECS` and delete `mind_palace.py` room/node/connection/stack/note/viewport routes (keep `/canvas-layout` + `/canvas-items` — they are position persistence, wanted). Caller verification before deletion (go-slow, prefer-raise).

**Phase 3 — No-fold confirmation.** `tasks.py` `BackgroundTask` (reindex/metrics/vector-repair/kg-metrics) stays as INFRA. Document this in the milestone close-out so no one later tries to fold it.

## What NOT to do (explicit)

- Do not start any Phase 1/2 slice before TestFlight (Daniel, 2026-06-26).
- Do not fold `tasks.py` BackgroundTask — it is INFRA, not CONTENT.
- Do not unmount the legacy `/rooms/*` router until Fold-E's CLI/MCP migration is verified (silent breakage risk).
- Do not add migrations for the library DB — per rule #9 (retired for app.duckdb, NOT for library DB): library schema is reimportable; structural fold changes go in the Pydantic model + `_ensure_table` directly, no `ALTER TABLE` migration. (App-DB device-token expiry #2173 was the exception that proved app-DB needs migrations; library DB does not.)
- Do not drop `private`→`internal` to paper over cross-file Swift access (per the #2082/#2002 bounce pattern) — fold work will touch Swift; keep access surfaces narrow.

## Verification (when implementation starts, post-TestFlight)

- Per fold: ruff + targeted pytest on the migrated subsystem's tests (e.g. `test_routes_savedsearch_actions.py` for Fold-A) + the full suite if a god-node (`Database`, `Document`, `KnowledgeEntity`) is touched (per the targeted-gate-misses-guardrails rule).
- Contracts: if `openapi.json` changes (it will for endpoint renames/removals), regen via `fichero-server/scripts/sync_openapi_schema.sh` + run `contracts/` walker + Swift compile-only build (NEVER `xcodebuild test` on Daniel's desktop).
- Audit/undo invariant: every migrated `_action_*` must still flow through `registry.invoke` (action layer #1848) so ActionAudit + emit stay intact.
- Docs: update this doc's fold table rows to "done" as each slice ships; keep claims grounded in code (per the docs-grounded-in-code rule).

## Cross-references

- EPIC #2081 — the foundation gaps (P1–P6 above).
- #2592 — view-mode audit (closed 2026-06-26; confirmed client-only; flagged the `/rooms/*` retirement that lives here).
- #2636 — general `LibraryItemLink` endpoint (the relations target for Fold-E connections).
- #2293 / task #369 — canvas position persistence (the item-attribute positions Fold-E keeps).
- #1848 — the audited action layer (every migrated `_action_*` must keep flowing through `registry.invoke`).
- #2067 — agent-as-principal (P6 chat scopes; the agent edits nodes like a user).
- `docs/contributor/architecture/fichero/mac_shell_design_proposal.md` + `agents/ROADMAP.md` line 37 — the Mac UI reform this foundation enables.