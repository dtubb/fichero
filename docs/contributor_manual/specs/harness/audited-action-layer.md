# Audited Action Layer — Design Spec (#1848)

> Milestone: audited-action-layer
> Manual: TBD — contributor-facing only; this is a backend architecture rule, not a
> user-visible surface (the user-visible consequence — undo, audit history — belongs to the
> specs that surface it, e.g. `kg/kg-readable-representation.md`'s `kg.read.audit-history`).

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** Written because a cross-cutting HARD
> rule (referenced in prose by `kg/kg-tables.md`, `ui/panes-workspaces.md`,
> `ui/modes-to-panes.md`, `ui/automation.md`, `ui/research.md`) had no spec of its own to pin a
> tag or a test against — this is that anchor.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the rule (needs an issue).

## Intent (the design)

Every mutating capability in Fichero — create, edit, delete, merge, split, link, curate,
anything that changes stored state — is **one named, typed action** in a single backend
registry, reached the same way regardless of WHO is asking: a person clicking a UI button, the
in-app agent calling a chat tool, an external MCP client, App Intents/Siri, or a test. The
registry is the ONE write choke point: it validates typed params, checks authorization,
executes the mutation, writes an audit row that is NOT best-effort (the action fails if the
audit can't be written), and broadcasts a change event that IS best-effort (broadcast failure
never fails the action). An action optionally declares itself undoable with an inverse, so the
SAME generic undo endpoint reverses (or redoes) any action without per-action undo code.

This converges four historically separate asks into one mechanism: a UI element that silently
does the wrong thing (no assertion), an agent that needs the app's own capabilities as tools (no
audited path to hand it), "who changed this and when" (no actor record), and duplicate
hand-rolled mutation paths for the same capability (two merge endpoints, two merge UIs). Fixing
the write path once fixes all four, and removes the duplication that caused the original
entity-merge bug this rule was converged from.

**The model is a user.** When the in-app agent (chat) invokes an action, it does so as a real
account with a role (viewer/editor/owner), through the same `ActionContext.actor` every human
click populates — there is no separate "AI audit," no privileged bypass. A model's authority is
scoped by that role today; a settings pane for finer per-tool grants does not exist yet
(`research.md`'s `research.per-model-tool-grants`, [GAP]).

**One object model, one write path.** Every knowledge object (entity, claim, interpretation,
note, annotation) shares this same choke point rather than a hand-rolled service per type — the
historical alternative (`AnnotationService`/`NoteService` hand-rolled `URLSession`, hardcoded
hosts, missing library-path headers) is the defect class this architecture retires, not a
parallel pattern to keep.

## What already exists (the mechanism itself — grounded, read 2026-09-18)

- `fichero_server.actions.registry.ActionRegistry` (`actions/registry.py`) — the process-global
  `<domain>.<verb>` → `ActionRegistration` map. `@action(name, params_model, domains=…,
  undoable=…, invert=…, read_only=…)` decorates an `execute(db, params, ctx) -> (result,
  ChangeSpec)` function and registers it.
- `ActionRegistry.invoke(db, name, raw_params, ctx)` is the single mutation path: resolve the
  action (unknown name → `ActionNotFoundError`) → validate `raw_params` into the action's
  Pydantic `params_model` → authorize (`authz.assert_can_write`, per-target-id when the params
  name specific ids) → `execute()` inside `db.transaction()` when the action is atomic → write
  an `ActionAudit` row (action name, actor, client, target ids, params, before/after snapshot,
  run id) — **not best-effort, the action fails if this write fails** — → broadcast a
  `ChangeEvent` to the observable layer — **best-effort, broadcast failure never fails the
  action** → return `ActionResult(ok, result, audit_id, changed_domains)`.
- `ActionContext` carries `actor`, `client` (attribution only, e.g. `fichero-mcp`, never an
  authorization input, #4469), `origin_window`, `run_id` (ties an action to an AI run, #1832),
  `library_path`, and `is_bootstrap`. **The actor cannot be forged**: `POST
  /api/actions/invoke`'s request body explicitly REJECTS an `actor`/`origin_window` field if a
  caller sets one (`InvokeActionRequest.reject_deprecated_fields`, #3285) — the real actor comes
  exclusively from `action_context()`'s `actor_from_request(request)`, populated by
  authentication middleware, never from anything a request body or header could claim.
- `POST /api/actions/invoke` — run any registered action by name; the same endpoint chat tools,
  App Intents, and UI-action tests all drive.
- `GET /api/actions/registry` — lists every registered action + its param JSON schema; this is
  what chat tools and App Intents read to build their tool/intent definitions FROM the registry,
  not a hand-maintained parallel list.
- `GET /api/actions/audit` + `POST /api/actions/audit/{audit_id}/undo` — the audit log and the
  ONE generic undo/redo endpoint. Undo: look up the action's `invert(before, after, ctx) ->
  (inverse_name, inverse_params)`, then `invoke()` that inverse tagged `inverse_of=this audit`.
  Redo: when the target audit IS an inverse (`inverse_of` set), replay the ORIGINAL forward
  action's recorded name+params — this works for ANY action regardless of how its inverse was
  implemented, no per-action redo code and no requirement that an inverse action itself be
  independently undoable.
- Not built: a fine-grained per-tool grant/deny UI for a model's role (beyond viewer/editor/
  owner) — `research.md`'s `research.per-model-tool-grants`.

## Behaviors

### A. The registry mechanism itself

- `audit.registry-is-the-one-write-choke-point` — **[OK]** every registered action's mutation
  runs inside `ActionRegistry.invoke`; `execute()` never writes state outside the transaction
  `invoke` opens for an atomic action. **Verified 2026-09-19** (test-audit follow-up: the
  citations below were plumbing-only, a throwaway `test.dummy` action, not a real production
  action driven end to end): `TestActionsRegistryRoute::test_invoke_via_route_writes_audit`
  drives the real `entity.merge` action through the real `POST /api/actions/invoke` route with
  real `KnowledgeEntity` rows, and `TestEntityMergeAction::test_merge_via_registry_effect_and_audit`
  drives the same action directly through `registry.invoke`, asserting both the merge effect
  (`merged_into_id`) and the written `ActionAudit` row — the choke point proven on real
  production behavior, not only the dummy. Pinned (plumbing + real-action, both needed):
  `test_action_registry.py::TestRegistryInvoke::test_invoke_returns_result_writes_audit_and_emits`,
  `::test_invoke_validates_params`, `::test_invoke_unknown_action_raises`,
  `::TestActionsRegistryRoute::test_invoke_via_route_writes_audit`,
  `::TestEntityMergeAction::test_merge_via_registry_effect_and_audit`.
- `audit.actor-cannot-be-forged` — **[PARTIAL]** (#4844, fixed for #4843's specific finding by
  8aa6c8e12) `POST /api/actions/invoke` rejects a request body that sets `actor`/
  `origin_window` directly (`InvokeActionRequest.reject_deprecated_fields`, → #3285); the real
  actor is derived exclusively from authenticated request state (`action_context()` →
  `actor_from_request(request)`). A `client` header (e.g. `X-Fichero-Client: fichero-mcp`) is
  attribution metadata only, never an authorization input. **The concrete forgeable path this
  behavior found is fixed**: `kg/inclusion.py::upsert_inclusion`'s `InclusionUpsertRequest
  .updated_by` field stays on the request model for compatibility, but its value is now
  IGNORED — the route stores `updated_by=actor` (`inclusion.py:63,71`), never
  `request.updated_by`; a test sends a forged name and reads the real actor back from the
  stored row. Verified at HEAD: no code path reads `request.updated_by` for the write. Still
  PARTIAL, not OK: the `POST /api/actions/invoke` guard itself remains untested — no test
  drives the route with a forged `actor` and asserts the rejection; that half is still filed
  as #4844. Pinned: `test_routes_kg_inclusion.py::test_forged_updated_by_is_ignored`.
- `audit.undo-redo-is-generic` — **[OK]** one endpoint (`POST
  /api/actions/audit/{audit_id}/undo`) reverses any undoable action via its own declared
  `invert()`, and redoes an inverse by replaying the ORIGINAL forward action's recorded
  name+params — no per-action redo code exists or is needed. **Verified 2026-09-19**
  (test-audit follow-up): both cited tests genuinely drive a real round trip — `entity.merge`
  through `registry.invoke`, `registry.get(...).invert(...)` for the real inverse, then
  `registry.invoke` again on the inverse — not a mock or a plumbing-only assertion; this
  citation was already correct, re-confirmed by opening the test bodies rather than trusted.
  Pinned:
  `test_action_registry.py::TestEntityMergeAction::test_undo_reverses_merge`,
  `::test_unmerge_undo_remerges_same_entities`.
- `audit.one-operation-has-one-undo` — **[BROKEN]** (#4864) one operation has ONE undo, and
  every undo of it gives the SAME result. Today an entity delete writes two trails.
  `delete_entity_impl` is reached through the registered, undoable `entity.delete` action,
  whose inverse `entity.restore` brings back the entity AND its claims' snapshot; the same
  function also writes a plain `MutationLog` row on every call, which feeds the older `POST
  /api/kg/mutations/{id}/undo` (`mutations.py::undo_mutation`, one of the nine routes still
  outside the registry, see `audit.every-mutating-route-uses-the-registry`). That older undo
  restores ONLY the entity row: the claims keep their cleared entity links and stripped
  `entity_ids`, which is exactly the drift the merge and delete link-integrity fixes removed from the
  forward path (kg-tables, `kg.merge.repoints-subject` and its delete sibling).
  Expected, in two steps. First, the narrowing, which needs no design decision: the older
  undo never performs a PARTIAL restore. For a mutation whose operation the action layer owns
  and can invert, it refuses with an error that names the action-layer undo, rather than
  restoring half the state; a refusal is loud and loses nothing, a partial restore is silent
  and corrupts curated links. Every other `MutationLog` writer is audited for the same
  duplication before the narrowing is called complete. Second, open (see Open questions):
  whether the older route then retires, or becomes a thin caller of the registry's undo, and
  when the second trail stops being written.
- `audit.action-record-not-best-effort` — **[PARTIAL]** (#4845) the `ActionAudit` write happens
  inside the same transaction as the mutation and is NOT best-effort — if the audit write
  fails, the whole action fails (`registry.py:220-233`). The change-stream broadcast that
  follows IS best-effort and never fails the action (`registry.py:259-290`) — an intentional
  asymmetry: silently losing an audit row is unacceptable, silently missing a live-UI nudge is
  recoverable on next reload. The happy path and the no-library-path case are pinned
  (`test_action_registry.py::TestRegistryInvoke
  ::test_invoke_returns_result_writes_audit_and_emits`, `::test_emit_skipped_without_library_path`)
  but nothing forces an audit-write failure or a broadcast failure to prove the asymmetry itself
  — filed as #4845.

### B. Every route reaches the registry (the rule this spec exists to test)

- `audit.every-mutating-route-uses-the-registry` — **[BROKEN]** (#4831) every mutating
  `@router.post/put/patch/delete` under `api/routes/kg/` and `api/routes/entity/` must call
  `registry.invoke(` in its own body (directly — no tracing through helper indirection; a
  route that calls a private helper which itself calls `registry.invoke` is still flagged,
  deliberately, per the guardrail's own docstring). The guardrail
  (`scripts/check_routes_use_action_layer.py`, an AST scan) ran for real (re-run 2026-09-18,
  after tonight's three landings) and now finds **9 violations + 5 by-design routes** across
  the same 42 decorated mutating routes — down from the 20 violations + 4 by-design this
  behavior originally found. **Three more landings since this spec's first pass**: 8aa6c8e12
  (`inclusion.upsert`, `review.accept`, `review.reject`, `review.queue`,
  `triangulation.recompute` — five routes; `review.accept` also stopped carrying its own copy
  of the entity-merge algorithm, calling `merge_entities_impl` instead so its undo is the
  already-tested `entity.unmerge`); 8e06dc31d (`claim.embed`, `entity.embed`, the
  external-authority setting, and creating/deciding a prediction review — five more routes,
  and `generate_heuristic_predictions` reclassified BY-DESIGN, not fixed — its body only reads
  and returns, POST only because its parameters travel in the body).

  **The 9 remaining violations, verified against the live allowlist
  (`scripts/routes_action_layer_allowlist.json`) rather than assumed from the old count:**
  `entity_curation.py`'s `refresh_external_authority` and `enrich_import`;
  `mutations.py::undo_mutation`; `predictions.py::apply_prediction_run`; `pykeen.py`'s `train`,
  `delete_trained_model`, `verify_prediction`; `rebuild.py`'s `reset_kg`/`rebuild_kg`
  (destructive).

  **The 5 by-design routes** (one more than the 4 this behavior first found):
  `render.py::render_paragraph`, `sparql.py`'s `sparql_query`/`sparql_query_legacy`,
  `entity_curation.py::enrich_preview` (all as before), plus
  `predictions.py::generate_heuristic_predictions` (new this pass, see above).

  This behavior is the guardrail's own home; it stays BROKEN until the guardrail reports zero
  unallowlisted violations — the count has now shrunk twice (20 → 15 → 9), which is the
  tracked-debt trend this line exists to hold the fixers to, not a point-in-time snapshot.
  Pinned: `test_check_routes_use_action_layer.py` (unchanged suite, all 13 tests), plus the
  new landings' own tests — `test_review_actions.py`, `test_routes_kg_inclusion.py`,
  `test_action_layer_batch3.py` (`TestClaimEmbedAction`, `TestEntityEmbedAction`,
  `TestSetExternalAuthorityEnabledAction`, `TestPykeenCreateReviewAction`,
  `TestPykeenDecideReviewAction`).
- `audit.wrapping-a-route-preserves-its-openapi-surface` — **[PARTIAL]** (#4846) wrapping a
  bare route to call `registry.invoke` internally must not change the OpenAPI document — three
  concrete traps found and avoided while doing this (2026-09-18): (1) adding
  `Depends(action_context)` as a NEW parameter adds header parameters
  (`X-Fichero-Origin-Window`, `X-Fichero-Client`) to the schema that weren't there before —
  building `ActionContext` directly from the route's EXISTING declared params (already-present
  `actor`/`x_fichero_library_path`/`x_fichero_origin_window` dependencies) avoids the diff; (2)
  a docstring added to a previously-undocumented function becomes its OpenAPI operation
  description — an unintended schema change; (3) the inverse mistake — REMOVING a route's
  original one-line docstring DELETES that operation's description, a diff in the other
  direction (a lesson named in that same landing's own commit message). Verified via
  `build_openapi_schema()` byte-identical checks in the fixing commits (e06b12551, 7523bcf95) —
  by hand, commit by commit. No standing regression test exists that would catch a FUTURE
  route-wrapping change breaking either direction — filed as #4846.

### C. Attribution — the actor recorded is the real one

- `audit.actor-attribution-is-real-not-hardcoded` — **[PARTIAL]** (implemented and tested,
  8e06dc31d; #4843 still open pending close) all
  three sibling spots this behavior found hardcoding `created_by="human"` regardless of who or
  what triggered the operation now record the real actor. Verified at HEAD: `EntityMergeAudit`
  rows for undo-of-merge, undo-of-split, and the authority-link audit
  (`entity_curation.py`, `created_by=actor` at every one of the sites this behavior previously
  named) — a `grep` for the literal `created_by="human"` in the file finds only the fix's own
  explanatory comment, no live hardcode. The authority-link argument that "a person confirmed
  this match, so the hardcode is a true domain statement" no longer holds — once
  `entity.link_authority` became reachable by agents through `POST /api/actions/invoke`, an
  agent-confirmed match was a real case the hardcode misrepresented, which is exactly why it
  was fixed rather than kept. Tests use different actors on each side of an operation, so a
  coincidence cannot hide a hardcoded value returning. Pinned:
  `test_routes_entity_curation.py::TestUndoEntityOperation`,
  `::TestLinkAuthorityAction`. `kg/inclusion.py::upsert_inclusion`'s related but distinct
  failure (a caller-CHOSEN actor, not a hardcoded one) is `audit.actor-cannot-be-forged`
  above's finding, not this one's — also fixed, per that behavior's own line.

### D. Undo/redo is honestly declared

- `audit.undoable-actions-declare-a-real-inverse` — **[OK]** `entity.split` is registered
  `undoable=True` and its inverse genuinely round-trips through the SAME generic undo endpoint
  as every other undoable action — verified against the code, not assumed from the
  `undoable=True` flag alone (undo-of-split restores the aliases the split moved away; it does
  NOT re-merge the split-off entities, which is existing, deliberate behavior, not a bug).
  Pinned:
  `test_routes_entity_curation.py::TestSplitEntityAction::test_split_is_undoable_via_the_existing_undo_endpoint`.
- `audit.non-undoable-actions-say-so` — **[OK]** `entity.link_authority` is registered
  `undoable=False` — the generic undo endpoint 409s on anything but merge/split, and the action
  registration honestly does not claim an undo capability the endpoint cannot deliver. Pinned:
  `test_routes_entity_curation.py::TestLinkAuthorityAction::test_not_undoable_no_regression_from_bare_route`.

### E. Only the action surface reaches a capability

- `audit.only-the-action-surface-reaches-capabilities` — **[PARTIAL]** (#4847, MCP half fixed
  93b2e97e5/54a13ffdf; #4866) agents, the CLI, and MCP should reach every mutating capability
  ONLY through the registered action surface — never a route or code path the action surface
  doesn't also expose. **The MCP tools half is now built and pinned**: all five MCP
  entity/claim write and delete tools (`mcp/tools.py`) are thin callers of `entity.create`/
  `entity.update`/`entity.delete`/`claim.create`/`claim.delete` via `registry.invoke` —
  verified at HEAD (`registry.invoke(db, "entity.create"/"claim.create"/"entity.delete"/
  "claim.delete", …, ctx)` at each of the five call sites) — where they previously built rows
  inline with no `ActionAudit`, no guarded undo, and none of the action side's validation. A
  source-scan test now enforces this as an INVARIANT for the whole file, not just these five:
  it fails if any function in `mcp/tools.py` writes to the database outside
  `registry.invoke` unless explicitly allowlisted, and the allowlist (the "bypass list") is
  now EMPTY — a synthetic case proves the scan still catches a real bypass, so an empty list
  reads as "nothing bypasses," not as a broken detector. Still PARTIAL, not OK: this is scoped
  to `mcp/tools.py` specifically, not a general "every capability the CLI/agent surface
  exposes has a matching registered action" guardrail across the whole app — the broader
  invariant this behavior's id names is still only a design intent, not a checked property
  everywhere. Pinned:
  `test_mcp_tools_write_through_registry.py::test_no_function_writes_to_the_db_outside_registry_invoke_unless_allowlisted`,
  `::test_the_five_reconciled_tools_are_not_in_the_bypass_list`,
  `::test_the_scan_itself_would_catch_a_real_bypass`,
  `test_mcp_kg_write_attribution.py::TestEntityCreateIsAccountable`,
  `::TestEntityDeleteIsAccountable`, `::TestClaimDeleteIsAccountable`.
- `audit.app-intents-use-typed-entities-not-raw-ids` — **[PARTIAL]** (#3304, legacy milestone
  "UX - Mac - Menus, Commands & Shortcuts" fold, 2026-09-19) every App Intent already routes
  through `invokeAuditedAction` → the registry (`FicheroActionIntents.swift`, verified at
  HEAD) — the one-audited-action-layer contract this behavior's siblings above establish holds
  for Shortcuts/Siri too, not only MCP. But a Siri/Shortcuts user can't discover a UUID: this
  issue's own two findings are **partly fixed, partly still open, verified at HEAD 2026-09-19**.
  `DeleteDocumentIntent` now takes a real `DocumentAppEntity` parameter (`@Parameter(title:
  "Document") var document: DocumentAppEntity`) — fixed, a picker with `EntityQuery` resolves it
  by name, not a pasted id — but still has **no confirmation step** before deleting
  (`perform()` invokes `document.delete` directly; no `requestConfirmation`), the destructive-
  action-without-confirmation half of this issue, unfixed. `MergeEntitiesIntent`,
  `RunWorkflowIntent`, and `CreateAnnotationIntent` still take raw `String`/`[String]` id
  parameters (`absorbingEntityId`, `workflowId`, `selectedDocumentIds`, `documentId`) despite
  `EntityAppEntity`/`WorkflowAppEntity`-shaped queries existing elsewhere in the codebase for at
  least some of these — the majority of this issue's own ask is not yet built. No dedicated
  pinning test found this pass for either the fixed or unfixed half.

### F. Undo scope beyond a single action — not this spec's mechanism, but its natural extension

> The mechanism above (registry, generic undo/redo, actor attribution) is built and largely
> proven for a SINGLE action. These three legacy-milestone issues (2026-09-19 fold, "UX - Mac -
> Menus, Commands & Shortcuts" #131) all ask for something structurally bigger — undoing a GROUP
> of actions, or exposing the audit trail as its own view — none of which exists yet. Grouped
> here as one family rather than three unrelated gaps, since all three read from the SAME
> `ActionAudit` table this spec's mechanism already writes.

- `audit.run-scoped-undo` — **[GAP]** (#2074, #1831 — the workflow-run half of this issue;
  its curation-undo half is already covered by the `entity.merge`/`entity.split` OK behaviors
  above, not a second gap) no capability exists to reverse every action of one agent/workflow
  run (`ActionContext.run_id`, already stamped on every `ActionAudit` row) as a single "Undo
  this run" — verified at HEAD: no `POST /api/actions/run/{run_id}/undo`-shaped route exists
  anywhere under `fichero-server/src/fichero_server/`. The data this would walk (per-run audit
  rows, newest-first) already exists; only the grouped-reversal endpoint and its UI affordance
  are missing. `ui/activity.md` is the natural home for the UI half of this once it's built
  (a run's own undo control) — cross-referenced, not restated, since that spec's own territory
  note already excludes execution mechanics.
- `audit.blame-and-rollback-view` — **[GAP]** (#1691) no "who changed what, when" view exists
  spanning documents/pages/entities/claims/notes with author+timestamp, wired to undo/rollback —
  verified at HEAD: no `blame`-named route, view, or model was found anywhere in
  `fichero-server/` or `fichero/fichero/`. The `ActionAudit` table this spec's mechanism already
  writes (actor, target ids, before/after snapshot, timestamp) is the exact data this behavior
  would read — the gap is a query/view surface over data that already exists, not a new audit
  mechanism. Explicitly `needs-design` per the issue's own label — scope the event model and
  retention before building, not decided here.

### G. Curation protection

- `audit.curation-actions-protect-nlp-drafts` — **[OK]** an entity or claim touched through the
  action layer (update, merge, link-authority, a claim link) is recognized as "touched" by the
  NLP draft purge action (`entity.purge_nlp_draft`, `importer.md`'s
  `importer.nlp-never-overwrites-curated-rows`) via the `ActionAudit` table itself, not only
  through domain-specific fallbacks (`EntityMergeAudit`, a hand-set metadata flag) — proof that
  routing a capability through the registry has a real downstream payoff beyond the audit log
  itself. Pinned: `test_nlp_draft_purge_action.py::TestF2IndependentTouchProtection` (the whole
  class), `test_routes_entity_curation.py::TestLinkAuthorityAction::test_a_linked_entity_survives_the_nlp_draft_purge`.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (py) | y | `invoke()`'s validate→execute→audit→emit contract | `actions/registry.py` (mechanism; see `audit.registry-is-the-one-write-choke-point`) |
| Guardrail (Swift-style Python AST scan) | y | every mutating KG/entity route calls `registry.invoke` | `scripts/check_routes_use_action_layer.py` + `fichero-server/tests/unit/scripts/test_check_routes_use_action_layer.py` |
| Backend (pytest) | y | undo/redo generic contract, actor cannot be forged, non-undoable says so | `test_routes_entity_curation.py` |
| Backend (pytest) | y | an action-layer touch protects an NLP draft row from purge | `test_nlp_draft_purge_action.py::TestF2IndependentTouchProtection` |
| MCP / CLI | y (MCP only) | MCP write/delete tools reach capabilities only via `registry.invoke`, source-scan enforced | `test_mcp_tools_write_through_registry.py`, `test_mcp_kg_write_attribution.py` (`audit.only-the-action-surface-reaches-capabilities`, [PARTIAL] — CLI/agent surface beyond MCP still unchecked) |
| OpenAPI diff | n | no dedicated regression test for the three wrapping traps | — (Open Questions) |

Hard-gate: `audit.every-mutating-route-uses-the-registry` (the guardrail exists and is wired
into `verify_all.sh`'s `check_*.py` sweep by filename, same as every other `check_*.py`
guardrail) once its violation count starts shrinking rather than only being tracked.

## Open questions

1. Should `audit.wrapping-a-route-preserves-its-openapi-surface`'s three traps get their own
   dedicated regression test (a `build_openapi_schema()` before/after diff assertion run as
   part of the guardrail or a sibling check), rather than relying on each fixing commit having
   manually verified byte-identity? Recommend: yes, as a follow-up once the route sweep
   (`audit.every-mutating-route-uses-the-registry`) is closer to done — not blocking this pass.
2. Should `audit.only-the-action-surface-reaches-capabilities` get its own guardrail (e.g.
   diffing the CLI's/MCP's exposed capability list against `GET /api/actions/registry`), or is
   this adequately enforced by convention plus the route guardrail above? Not decided here —
   flagged as a real gap, not assumed solved by the route sweep.
3. `EntityMergeAudit`'s two self-referencing `reversal_id = audit.id` writes (noted on #4831 as
   "meaning unknown; parity kept") — worth understanding before extending that table's pattern
   to more operations, or safe to leave as an established quirk? Not investigated in this pass.
- For the maintainer: once the older mutation undo refuses operations the action layer owns
  (`audit.one-operation-has-one-undo`, #4864), does that route RETIRE in favour of the
  registry's undo, or stay as a thin caller of it? And when does `MutationLog` stop being
  written for operations that already have an action audit?

## Sources folded in

Design content carried into this spec; files kept, not moved:

- `~/.claude/.../memory/one-audited-action-layer.md` — origin of the "one named typed action,
  five ways in" architecture (EPIC #1848), paraphrased throughout the Intent section.
- `~/.claude/.../memory/agent-chat-model-is-a-user.md` — origin of "the model is a user," a
  real account with a role, folded into this spec's "The model is a user" paragraph.
- `~/.claude/.../memory/knowledge-consistency-mandate.md` — origin of "one write path for every
  knowledge object," folded into this spec's "One object model, one write path" paragraph.
