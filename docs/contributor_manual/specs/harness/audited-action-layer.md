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
  `invoke` opens for an atomic action. Pinned:
  `test_action_registry.py::TestRegistryInvoke::test_invoke_returns_result_writes_audit_and_emits`,
  `::test_invoke_validates_params`, `::test_invoke_unknown_action_raises`,
  `TestActionsRegistryRoute::test_invoke_via_route_writes_audit`.
- `audit.actor-cannot-be-forged` — **[PARTIAL]** (#4844) `POST /api/actions/invoke` rejects a
  request body that sets `actor`/`origin_window` directly
  (`InvokeActionRequest.reject_deprecated_fields`, → #3285); the real actor is derived
  exclusively from authenticated request state (`action_context()` →
  `actor_from_request(request)`). A `client` header (e.g. `X-Fichero-Client: fichero-mcp`) is
  attribution metadata only, never an authorization input (a fix landed under a separate closed issue). Verified by reading the
  code, not by a test — no test drives the route with a forged `actor` and asserts the
  rejection; filed as #4844.
- `audit.undo-redo-is-generic` — **[OK]** one endpoint (`POST
  /api/actions/audit/{audit_id}/undo`) reverses any undoable action via its own declared
  `invert()`, and redoes an inverse by replaying the ORIGINAL forward action's recorded
  name+params — no per-action redo code exists or is needed. Pinned:
  `test_action_registry.py::TestEntityMergeAction::test_undo_reverses_merge`,
  `::test_unmerge_undo_remerges_same_entities`.
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
  (`scripts/check_routes_use_action_layer.py`, an AST scan) ran for real (2026-09-18) and found
  **20 violations + 4 by-design routes** across 42 decorated mutating routes total. **First
  batch landed while this spec was written** (e06b12551): `entity.split`, `add_entity_aliases`
  (a thin caller of `entity.update` — no second action for the same underlying write),
  `entity.batch_curation` — confirmed COMPLIANT by the real scan. **Second landing**
  (7523bcf95, its own now-closed filing issue): `entity.link_authority` — also confirmed
  compliant. `render.py::generate_entity_bio` (the LLM `/bio` route,
  `kg.read.no-llm`'s BROKEN finding in `kg-readable-representation.md`) is itself already
  compliant — it calls `registry.invoke("entity.update", …)` to persist the LLM output, which
  is a *separate* finding from whether that write should exist at all.

  **The 20 real violations, by file:** `claim_search.py::embed_claims`; `entity_curation.py`'s
  `embed_entities`, `put_external_authority_settings`, `refresh_external_authority`,
  `enrich_import`; `inclusion.py::upsert_inclusion` (also client-supplies `updated_by`, a
  second, distinct actor-forgery risk — see `audit.actor-attribution-is-real-not-hardcoded`);
  `mutations.py::undo_mutation`; `predictions.py`'s `generate_heuristic_predictions` and
  `apply_prediction_run`; `pykeen.py`'s `train`, `create_prediction_review`,
  `decide_prediction_review`, `delete_trained_model`, `verify_prediction`; `rebuild.py`'s
  `reset_kg`/`rebuild_kg` (destructive); `review.py`'s `accept_pair`/`reject_pair`/`queue_pair`;
  `triangulation.py::recompute_triangulation`.

  **The 4 by-design routes** (each read on its own merits, never an automatic "looks read-only"
  guess — see the guardrail's own allowlist rule): `render.py::render_paragraph` (composes
  existing claims into prose via `db.get()` only, POST for the request body's `claim_ids` list,
  not for mutation); `sparql.py`'s `sparql_query`/`sparql_query_legacy` (both reject any
  mutating SPARQL verb before running, by their own docstring); `entity_curation.py
  ::enrich_preview` (fetches candidate Wikidata statements for review, no `db.save`/`delete` —
  its mutating sibling `enrich_import` above IS a real violation).

  **Diff against the engine lane's own #4831 sweep (comparing both directions, as requested):**
  the sweep listed ~14 mutating violations and separately named `sparql.py`'s two query
  endpoints and `render_paragraph` as "probably fine, not verified exhaustively" — the guardrail
  CONFIRMS all three are by-design after reading their bodies, closing that open question. The
  guardrail found ONE violation the sweep's list did not name: `inclusion.py::upsert_inclusion`
  — a real, previously-unlisted bare mutating route. The guardrail also surfaced
  `enrich_preview` as a finding the sweep never mentioned at all (it isn't mutating, so it was
  out of the sweep's own scope) — resolved by-design, not a miss. No violation the sweep named
  went unfound by the guardrail. This behavior is the guardrail's own home; it stays BROKEN
  until the guardrail reports zero unallowlisted violations AND its violation count (currently
  20) starts shrinking, tracking real debt rather than a point-in-time count. Pinned:
  `test_check_routes_use_action_layer.py` (all 13 tests, incl.
  `test_multi_router_file_scans_every_router_variable`,
  `test_fires_on_a_decorator_on_a_nested_async_function`,
  `test_does_not_trace_through_helper_indirection`).
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

- `audit.actor-attribution-is-real-not-hardcoded` — **[BROKEN]** (#4843) an
  action's audit row must record the ACTUAL actor (`ctx.actor`), never a hardcoded string —
  `merge_entities_impl` was fixed to thread the real actor under a separate, already-closed issue, but three sibling spots
  in the same file still hardcode `created_by="human"` regardless of who or what triggered the
  operation: `EntityMergeAudit` rows for undo-of-merge (`entity_curation.py:647`),
  undo-of-split (`entity_curation.py:667`), and the authority-link audit
  (`entity_curation.py:1211`). A workflow- or agent-driven undo or authority-link is logged as
  if a person did it. Distinct from `audit.every-mutating-route-uses-the-registry` above —
  these three ARE reachable through the action layer's own audit-adjacent bookkeeping
  (`EntityMergeAudit`, a domain-specific curation-history table, not `ActionAudit` itself); the
  registry's own `ActionAudit.actor` for these operations is correct (it threads `ctx.actor`)
  — this is a SECOND, domain-local audit trail with its own actor field that wasn't updated to
  match.

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

- `audit.only-the-action-surface-reaches-capabilities` — **[GAP]** (#4847) agents, the CLI, and MCP
  should reach every mutating capability ONLY through the registered action surface (`POST
  /api/actions/invoke` or an equivalent typed wrapper) — never a route or code path the action
  surface doesn't also expose. No test or check was found that PINS this as an invariant (e.g.
  "every capability the CLI/MCP exposes has a matching registered action" or its converse); it
  is currently a design intent stated in `registry.py`'s own module docstring and this spec's
  Intent section, not a checked property. A candidate future guardrail, not built this pass.
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
| MCP / CLI | n | no test found pinning "only the action surface reaches a capability" | — (`audit.only-the-action-surface-reaches-capabilities`, [GAP]) |
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

## Sources folded in

Design content carried into this spec; files kept, not moved:

- `~/.claude/.../memory/one-audited-action-layer.md` — origin of the "one named typed action,
  five ways in" architecture (EPIC #1848), paraphrased throughout the Intent section.
- `~/.claude/.../memory/agent-chat-model-is-a-user.md` — origin of "the model is a user," a
  real account with a role, folded into this spec's "The model is a user" paragraph.
- `~/.claude/.../memory/knowledge-consistency-mandate.md` — origin of "one write path for every
  knowledge object," folded into this spec's "One object model, one write path" paragraph.
