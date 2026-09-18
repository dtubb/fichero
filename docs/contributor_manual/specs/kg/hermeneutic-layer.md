# Hermeneutic Layer — Design Spec (#4692)

> Milestone: hermeneutic-layer
> Manual: TBD — contributor-facing only until the access question below is answered; there
> is no user-facing story to document beyond "there is an Interpretations tab in the Document
> Inspector" today.
>
> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** Written because the maintainer asked
> how a researcher reaches this layer and no spec anchored it — it is referenced in six other
> specs (`ui/write-layer.md`, `ui/research.md`, `ui/reading-markup-annotations.md`,
> `harness/audited-action-layer.md`, `harness/observable-data-layer.md`,
> `kg/kg-entity-inspector.md`) but owned by none of them.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the rule (needs an issue).

## A naming note, stated plainly

The codebase's own module is `fichero_server/models/hermeneutics.py`, and its own docstring
calls this "0.0.2 Layer 5." The three-layer READ→THINK→WRITE framing used elsewhere
(`ui/write-layer.md`, EPIC #2108) uses "Hermeneutic (READ)" for claim/entity/citation
extraction and "Interpretative (THINK)" for notes/annotations on a reading — a DIFFERENT use
of "hermeneutic" than the code's own naming. This spec is about the CODE's `Interpretation` /
`InterpretiveFramework` / `PatternInstance` / `HermeneuticCircleState` objects — the reasoning
a researcher (or, per one doc comment, "what *I* think" as against "what the source says") adds
between a source's claims and a piece of writing — which functionally sits at the THINK
position in that other framing, not a fourth layer. Not resolving the naming collision here;
noting it so nobody reads "hermeneutic" the same way twice by accident.

## Intent (the design)

A researcher applies an interpretive framework (a named lens — historical, thematic,
theoretical, and so on) to a claim or a passage, and records what it means under that lens: an
`Interpretation`. Interpretations can recognize recurring `PatternInstance`s across many claims,
and a `HermeneuticCircleState` tracks moving between a part and the whole it belongs to. All of
it is distinct from the KG's own claims (asserted facts with provenance) and from Notes
(free-floating Zettelkasten atoms) — an interpretation is always ABOUT a specific claim or
passage, FROM a specific framework's perspective, and is attributed to whoever (or whatever)
made it.

## What already exists (grounded, read on disk 2026-09-18)

- `fichero_server.models.hermeneutics` — `InterpretiveFramework`, `Interpretation`,
  `PatternInstance`, `HermeneuticCircleState`, plus `HermesSuggestionRequest`/`HermesSuggestion`
  (models for an AI-suggestion feature whose route was deleted as a permanent-501 stub with no
  caller, 2026-07-27 — the models remain, nothing serves them).
- `api/routes/interpretation/hermeneutics.py` — full CRUD for frameworks (create/list/get/
  update/DELETE), create/list/get/PATCH for interpretations (no delete), create/list/get/PATCH
  for patterns plus an add-claim-to-pattern action, and create/list/get/navigate/backtrack for
  circle-state. **Every mutating route in this file calls `registry.invoke(` in its own body** —
  verified by reading the whole file; this directory is outside
  `scripts/check_routes_use_action_layer.py`'s current scope (`api/routes/kg/` and
  `.../entity/` only) but is independently compliant with the same rule
  (`harness/audited-action-layer.md`).
- Swift `InterpretationStore` — a document-scoped `ObservableDomainStore`; `create` appends the
  new row in place, `update` splices by index with a reload fallback when the id is genuinely
  absent (both fixed 2026-09-18, #4824). `apply(_ event:)` still `scheduleReload()`s on any
  `interpretation.*` event for the current scope — already tracked as a violation in
  `harness/observable-data-layer.md`'s allowlist, not re-litigated here.
- `DocumentInterpretationsTab` / `DocumentInterpretationsSection` — the ONE app surface.
  Confirmed MOUNTED: `.interpretations` is in `DocumentInspector+TabBar.swift`'s
  `availableTabs` list (always present, not gated), and
  `DocumentInspector+Sections.swift:16-17` mounts `DocumentInterpretationsTab` for that tab
  case. It offers a framework picker, an act picker, a text editor, a confidence slider, and
  per-row inline editing — genuinely a read AND write surface, not read-only.
- **Nothing else reaches this layer.** Grepped the whole `Views/` tree: no other file
  references `InterpretationStore` or constructs an `Interpretation`. `PatternInstance` and
  `HermeneuticCircleState` have **zero** Swift presence — no model, no store, no view, at all
  — despite full, tested engine routes.

## Behaviors

### A. Reachability — frameworks, interpretations, patterns, circle-state

- `hermeneutic.framework-crud` — **[OK]** create/list/get/update/delete all work and are
  audited. Pinned: `test_routes_hermeneutics.py::TestCreateFramework::test_create_framework`,
  `TestListFrameworks` (both tests), `TestGetFramework` (both), `TestUpdateFramework` (both),
  `TestDeleteFramework` (both).
- `hermeneutic.interpretation-create-and-list` — **[OK]** creating an interpretation validates
  the framework exists and is active, requires and resolves a `claim_id`, and appears in the
  list. Pinned: `test_routes_hermeneutics.py::TestCreateInterpretation` (all 3),
  `test_routes_hermeneutics.py::TestListInterpretations::test_empty_list`,
  `::test_returns_interpretations`.
- `hermeneutic.interpretation-update` — **[OK]** patching an interpretation's text/confidence/
  predicate persists and re-normalizes `predicate_canonical`. Pinned:
  `test_routes_hermeneutics.py::TestListInterpretations::test_update_interpretation_updates_predicate_canonical`.
- `hermeneutic.interpretation-delete` — **[GAP]** (#4692) there is no DELETE route for an
  interpretation — frameworks have one (`hermeneutics.py:334`), interpretations end at PATCH
  (`:476`). Once created, wrong or abandoned, an interpretation cannot be removed at all. Not
  built.
- `hermeneutic.interpretation-linked-to-claim-or-passage` — **[GAP]** (#4692) the model
  supports `claim_id`/`document_id`/`passage_text` on an interpretation, but the ONE app
  surface's create form (`DocumentInterpretationsSection.swift:130-136`) sends only
  `frameworkId`/`documentId`/`act`/`text`/`confidence` — never `claim_id` or `passage_text`.
  An interpretation the app creates is never actually linked to the specific claim or passage
  it's about, only to the whole document. Not built on the app side; the engine already accepts
  the fields.
- `hermeneutic.interpretation-has-source-anchor` — **[GAP]** (#4692) an interpretation has no
  char-span/rect anchor (`rendition_id`, offsets) the way a claim or annotation does, so even
  once linked to a passage (behavior above), nothing can highlight that passage in the reader
  the way a claim's source anchor does. Not built.
- `hermeneutic.pattern-and-circle-state-have-no-app-surface` — **[GAP]** (#4692) `PatternInstance`
  and `HermeneuticCircleState` are fully modelled, routed, and (per the ordering tests below)
  tested engine-side, but have ZERO presence anywhere under `fichero/fichero/Views/` or
  `Models/` — no Swift model, no store, no view, confirmed by grep across the whole tree. A
  researcher cannot see or use pattern recognition or hermeneutic-circle navigation at all
  today, on any surface.
- `hermeneutic.reachable-by-agent-or-mcp` — **[GAP]** (#4692) `interpretation.create`/
  `.update` are registered, audited actions, but neither is in `chat_tools.py`'s
  `CHAT_WRITE_ALLOWLIST` (`:70-77`, four entries: `workflow.run`, `entity.create`,
  `entity.update`, `claim.create` — no `interpretation.*`), so the in-app agent cannot create or
  edit an interpretation via the audited chat-tools path. Framework/pattern/circle-state
  actions are absent from the allowlist too. The mechanism to add them is trivial (the registry
  already has the actions); the allowlist entry itself is what's missing.

### B. Ordering, in-place updates, and honesty

- `hermeneutic.ordering-deterministic` — **[OK]** interpretations, frameworks, patterns, and
  circle-states all come back oldest-first with a stable id tiebreak — previously no order at
  all (2593a6776). Pinned:
  `test_routes_hermeneutics.py::TestListOrderingIsDeterministic::test_interpretations_come_back_oldest_first_regardless_of_insert_order`,
  `::test_interpretations_with_equal_timestamps_break_ties_by_id_stably`,
  `::test_frameworks_come_back_oldest_first`, `::test_patterns_come_back_oldest_first`,
  `::test_circle_states_come_back_oldest_first`.
- `hermeneutic.store-updates-in-place` — **[OK]** (169ca6299) `InterpretationStore.create`
  appends the created row in place (matching the now-deterministic oldest-first order above,
  so `append` produces what a real reload would); `.update` splices by index, falling back to a
  reload only when the id is genuinely absent. Pinned:
  `InterpretationStoreTests.testCreateAppendsInPlaceWithoutReload`,
  `InterpretationStoreTests.testCreatePreservesOrderAcrossMultipleAppends`,
  `InterpretationStoreTests.testCreateSkipsAppendWhenTheInterpretationIsOutOfTheCurrentScope`,
  `InterpretationStoreTests.testUpdateSplicesInPlaceByIndex`,
  `InterpretationStoreTests.testUpdateFallsBackToReloadWhenTheIdIsAbsent`.
- `hermeneutic.mutations-are-audited` — **[PARTIAL]** (#4858) every mutating route in
  `interpretation/hermeneutics.py` calls `registry.invoke(` in its own body, verified by
  reading the file whole — the mechanism is real. No test specific to THIS domain was found
  asserting an `ActionAudit` row is actually written for a framework/interpretation/pattern/
  circle-state action (the generic mechanism is pinned elsewhere,
  `harness/audited-action-layer.md`'s `audit.registry-is-the-one-write-choke-point`, but not
  re-asserted per-domain here).
- `hermeneutic.actor-not-forged` — **[BROKEN]** (#4857) `InterpretationCreateRequest
  .created_by: str = "human"` (`hermeneutics.py:115`) is a plain client-settable field, stored
  verbatim by `create_interpretation_impl` (`:388`) — any caller can claim to be anyone. The
  route already threads `ctx.actor` correctly into `ActionAudit` via `registry.invoke`; this is
  specifically the domain model's OWN `created_by` field not deriving from it, the same class
  of gap `harness/audited-action-layer.md` tracks for `kg/inclusion.py::upsert_inclusion`.

### C. Where the reasoning connects to a claim

- `hermeneutic.claim-type-and-quotation-kind-are-modelled-not-editable` — **[GAP]** (#4692)
  "what the source says" vs. "what the reader concludes" IS modelled richly on `KnowledgeClaim`
  (`ClaimType` including `interpretation`/`argument`/`historiography`/`theory`;
  `QuotationKind` including `paraphrase`/`inference`/`free_indirect`; Toulmin
  `grounds`/`warrant`/`backing`/`qualifier`/`rebuttal`) — but the UI exposes only Kind/Status/
  EpistemicStatus (`EditClaimSheet.swift` pickers); `quotation_kind` and the Toulmin fields are
  edit-invisible, and the claims table has no Type column. Not built.
- `hermeneutic.promote-to-claim-keeps-the-distinction` — **[BROKEN]** (#4692) promoting an
  annotation to a claim (`annotations.py:569`) yields a claim with no `claim_type`/
  `quotation_kind` set — the "says vs. concludes" distinction drops at exactly the moment a
  highlight becomes knowledge. It is also the one KG create action that is NOT undoable
  (confirmed: `test_routes_annotations_actions.py::test_promote_is_not_undoable`).
- `hermeneutic.claim-provenance-badge-reads-the-right-field` — **[BROKEN]** (#4692) a
  manually-created claim stamps `createdBy: "human"` client-side
  (`EntityService+ClaimEntityCRUD.swift:125` → `claims.py:461`, trusted from the client rather
  than derived from the actor — the SAME actor-forgery class as
  `hermeneutic.actor-not-forged` above, a different model), but `ClaimProvenanceBadge` derives
  its label from `confidence_source` (`ClaimTableRow.swift:26-35`) — a different field
  entirely. An uncurated, hand-authored claim shows "—" instead of "Human," because the badge
  and the write path disagree about which field means "who made this."

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | framework/interpretation/pattern/circle-state CRUD + ordering | `fichero-server/tests/unit/api/test_routes_hermeneutics.py` (ran for real, 22/22 pass) |
| Availability (Swift) | y | store create/update in-place, scope-gating | `fichero/Tests/Unit/general/Models/InterpretationStoreTests.swift` |
| Availability (Swift) | n | no test exists for pattern/circle-state — no Swift code to test | — (`hermeneutic.pattern-and-circle-state-have-no-app-surface`) |
| MCP / chat tools | n | no test pins interpretation actions being allowlisted (they aren't) | — (`hermeneutic.reachable-by-agent-or-mcp`) |
| Click-around (XCUITest) | n | no dedicated flow test found for the Interpretations tab | — |

Hard-gate: none yet — DRAFT spec; a hard-gate set is chosen once the access question below is
answered and the surface has an owner.

## The access question (stated plainly, not decided here)

The maintainer asked where in the pane system a researcher opens, reads, and writes
interpretations. Today the honest answer is: **only from one document's Inspector tab.** There
is no Reader rendition, no Source-pane reveal (interpretations have no source anchor to reveal
in the first place — see `hermeneutic.interpretation-has-source-anchor`), no library-wide or
cross-document view, and no agent/chat-tool access (see `hermeneutic.reachable-by-agent-or-mcp`).
An interpretation is scoped to exactly one document, editable only while that document's
Inspector is open, and invisible everywhere else in the app.

## Open questions (for the maintainer — options the code makes cheap, not a recommendation)

1. **Does the Interpretations tab move, or does the Inspector stay its home?** The code makes
   cheap: (a) leave it in the Inspector, alongside Notes, as today; (b) give it a Reader
   rendition once it has a source anchor (mirrors the readable-representation ruling that the
   Reader shows content, the Inspector shows curation); (c) both — Inspector for the list/edit
   surface, Reader for a linked interpretation's highlighted passage once anchored.
2. **Should an interpretation be linkable to a claim/passage before or after it gets a source
   anchor?** The engine already accepts `claim_id`/`passage_text` on create — wiring the APP's
   create form to send them is a small, standalone fix; a full char-span/rect anchor
   (`hermeneutic.interpretation-has-source-anchor`) is a bigger, separate piece of work. They
   can ship in either order.
3. **Do patterns and circle-state get a Swift surface at all, or do they retire?** Both are
   fully built and tested engine-side with zero app presence. The code makes cheap: (a) build a
   real Swift surface for both (a pattern list, a circle-navigation UI); (b) retire the
   circle-state model specifically if hermeneutic-circle navigation isn't a feature anyone
   wants surfaced (patterns still feed potential future cross-document analysis, so retiring
   patterns too is a bigger claim); (c) leave both as engine-only substrate for now, undecided,
   revisited when a concrete UI need names them.
4. **Should interpretation actions join `CHAT_WRITE_ALLOWLIST`?** The mechanism is trivial (the
   actions are already registered and audited) — the only question is whether letting an agent
   record its OWN interpretation (as opposed to a human's) is a decision the creative director
   wants made now or deferred alongside the broader per-model tool-grant work
   (`research.md`'s `research.per-model-tool-grants`).
5. **Does `hermeneutic.claim-type-and-quotation-kind-are-modelled-not-editable` belong to this
   spec or to a claim-editing spec (`kg-tables.md`'s claim CRUD section)?** It's about the
   `KnowledgeClaim` model, not `Interpretation` — included here because #4692 framed it as part
   of the same "rich model, thin reach" finding, but it may belong split out.
