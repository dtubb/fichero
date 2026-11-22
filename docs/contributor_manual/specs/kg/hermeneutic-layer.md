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
>
> **Updated 2026-11-21** from the owner's rulings on people, biography and concepts (section "Ruled 2026-11-21" and
> section D below). Lines the ruling overtakes are kept, each with a "Superseded 2026-11-21" pointer; nothing is
> deleted. Section D has no build order here: its lines are built in the steps of `explore/concepts-and-terms.md`,
> and "→ #NEW-Cn" is the step issue of that spec. Its neighbour is `kg/ontological-layer.md` (what kinds of thing
> exist); this layer holds what the historian thinks about them.

## For a historian

When you explore your archive (`explore/explore.md`) almost everything you see is what the sources say. This layer
is the one place that holds what YOU say: the concepts you define, your reading of a passage, your judgement on two
sources that disagree, and the arguments you build from them. Each is tied to the passages it rests on, so you and
your readers can go from your claim to the page. It is yours alone. Fichero stores it, finds passages for it and
counts for it. It never writes in it: no suggested interpretation, no proposed concept, no drafted argument.

## Ruled 2026-11-21 (owner; paraphrased)

1. **The hermeneutic layer is interpretation**: the historian's concepts, readings and arguments. It is owned by the
   person and linked to evidence.
2. **The model never writes here.** It proposes no concept and no interpretation. Its mechanical work (reading,
   grouping spellings, proposing a same-person link, ranking) lives outside this layer and is labelled.
3. **The historian's categories are kept distinct from the sources' own** (`kg/ontological-layer.md`). A tie between
   the two is something the historian makes, and it is stored here.

What this changes in the lines below: an interpretation is always a person's, so "attributed to whoever (or
whatever) made it" now means which person; the suggestion models have no future; letting an agent write an
interpretation is no longer an open question; a pattern becomes the historian's concept with its passages.

## A naming note, stated plainly

The codebase's own module is `fichero_server/models/hermeneutics.py`, and its own docstring
calls this "0.0.2 Layer 5." The three-layer READ→THINK→WRITE framing used elsewhere
(`ui/write-layer.md`, EPIC #2108) uses "Hermeneutic (READ)" for claim/entity/citation
extraction and "Interpretative (THINK)" for notes/annotations on a reading — a DIFFERENT use
of "hermeneutic" than the code's own naming. This spec is about the CODE's `Interpretation` /
`InterpretiveFramework` / `PatternInstance` objects (and the retired `HermeneuticCircleState`) — the reasoning
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

*Superseded 2026-11-21 in part:* only a person makes one (`hermeneutic.layer.only-a-person-writes`). A framework is
the record a historian's concept is kept in, and a pattern is that concept's passages
(`hermeneutic.concept.is-the-framework-record`, `explore/concepts-and-terms.md`).

## What already exists (grounded, read on disk 2026-09-18)

- `fichero_server.models.hermeneutics` — `InterpretiveFramework`, `Interpretation`,
  `PatternInstance`, `HermeneuticCircleState`, plus `HermesSuggestionRequest`/`HermesSuggestion`
  (models for an AI-suggestion feature whose route was deleted as a permanent-501 stub with no
  caller, 2026-07-27 — the models remain, nothing serves them). *Superseded 2026-11-21:* an AI suggestion of an
  interpretation is ruled out; the two models are to be deleted (`hermeneutic.layer.only-a-person-writes`).
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
  the way a claim's source anchor does. Not built. *Superseded 2026-11-21:* restated and scheduled as
  `hermeneutic.reading.rests-on-a-stretch` in section D.
- `hermeneutic.pattern-and-circle-state-have-no-app-surface` — **[GAP]** (#4692) `PatternInstance`
  and `HermeneuticCircleState` are fully modelled, routed, and (per the ordering tests below)
  tested engine-side, but have ZERO presence anywhere under `fichero/fichero/Views/` or
  `Models/` — no Swift model, no store, no view, confirmed by grep across the whole tree. A
  researcher cannot see or use pattern recognition or hermeneutic-circle navigation at all
  today, on any surface. *Superseded 2026-11-21 in part:* a pattern gets its surface as the historian's
  concept and its passages (the concept sheet, `explore/concepts-and-terms.md` section C); nothing "recognises" a
  pattern for the person. Circle-state stays without a surface; see the open question on retiring it. **Not built:** the owner's answer (2026-11-22), the circle-state model retires and the attestation sheet replaces it (open question 3); removing its code.
- `hermeneutic.reachable-by-agent-or-mcp` — **[GAP]** (#4692) `interpretation.create`/
  `.update` are registered, audited actions, but neither is in `chat_tools.py`'s
  `CHAT_WRITE_ALLOWLIST` (`:70-77`, four entries: `workflow.run`, `entity.create`,
  `entity.update`, `claim.create` — no `interpretation.*`), so the in-app agent cannot create or
  edit an interpretation via the audited chat-tools path. Framework/pattern/circle-state
  actions are absent from the allowlist too. The mechanism to add them is trivial (the registry
  already has the actions); the allowlist entry itself is what's missing. *Superseded 2026-11-21:* the entry is not to be added. An agent may READ this layer
  through generated tools; every write by a model's account is refused
  (`hermeneutic.layer.only-a-person-writes`). What remains of this gap is the read tools only.

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
- `hermeneutic.actor-not-forged` — **[OK]** (#4857 closed 2026-09-26)
  `create_interpretation_impl` stores `created_by=actor` from `ctx.actor`
  (`hermeneutics.py:402`) and the request field is ignored, so a caller can no longer claim
  authorship it does not have. Pinned by `test_hermeneutics_actions.py` (165 passing at close).
  Corrected 2026-09-26: this line described `created_by: str = "human"` as a live
  client-settable field long after the fix landed. The same class of gap is still tracked for
  `kg/inclusion.py::upsert_inclusion` in `harness/audited-action-layer.md`.

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
- `kg.claim.provenance-kind-is-server-stated` — **[PARTIAL]** (#4868, #4869) sits beside
  `hermeneutic.claim-provenance-badge-reads-the-right-field` above rather than in
  `kg-tables.md`, because both issues are filed on this milestone and both are the same class
  of defect the sibling behavior already names — which field means "who made this" — one
  layer deeper: that field's own STORED VALUE, not just which field the badge reads.
  (`kg-tables.md`'s own `kg.tables.provenance.author-mark` is the aspirational design line
  this behavior makes concrete; cross-referenced there, not duplicated.) Verified BROKEN at
  HEAD: `KnowledgeClaim.created_by` (`models/knowledge.py`) defaults to `"human"` — a default
  no caller has to override — and the workflow claim writer (`_entity_writer.py`'s
  `KnowledgeClaim(...)` construction) sets `provider`/`model` but never `created_by`; the
  NLP-draft importer likewise never sets it. So every machine-extracted claim is STORED as
  authored by a human, not merely mislabeled at render time. `ClaimSummaryCard
  +Provenance.swift`'s `createdByBadge(for:)` reads that same untrustworthy field: an exact
  match against `["human", "user", "manual", "researcher", "editor", "curator", "cli"]`
  badges "Human," and a substring `.contains("ai")`/`"agent"`/`"llm"`/`"extract"` badges
  "AI" — so a real human actor whose account name happens to contain "ai" (or any string not
  in the human list) gets badged "AI," and every machine claim gets badged "Human" by the
  same default. **Ruled direction**: one CLOSED field (`ProvenanceKind`: human/agent/
  workflow/external_import/unknown) set by the SERVER at the point of writing, never accepted
  from a client on any route or action; existing stored rows are NOT rewritten — a legacy
  row's kind is derived at READ time instead (provider/model present → `workflow`;
  `created_by == "wikidata"` → `external_import`; otherwise `unknown`, deliberately never
  `human`, since a legacy row's `created_by` being the string "human" is exactly the
  untrustworthy value this behavior exists to stop trusting). Whether stored rows also get an
  audited repair pass is explicitly the maintainer's decision, not decided here. **The engine half is built** (c30680467, contract
  regenerated in 6adec7180): `ProvenanceKind` and `KnowledgeClaim.provenance_kind`, set by the
  server on every write path and ignored when a client supplies it; `created_by` defaults to
  `unknown`; `resolve_claim_provenance_kind` is the one place a legacy row's kind is derived;
  an existing library takes the new column without any row being rewritten. Pinned:
  `fichero-server/tests/unit/knowledge/test_claim_provenance_kind.py`. PARTIAL, not OK, for
  three reasons that keep #4869 and #4868 open: the app's claim card still badges from words in
  `created_by` and has not yet been moved to this field; search results and export paths embed
  a claim and do not yet apply the derivation; and "agent" is identified by the surface an
  action came through, not by a verified property of the account.

### D. The layer after the ruling of 2026-11-21 (built in `explore/concepts-and-terms.md`)

- `hermeneutic.layer.only-a-person-writes` — **[GAP]** (#4692 → #7024) every create, update and delete of a
  framework, an interpretation, a pattern and a link in this layer is refused when the actor is a model, an agent or
  a workflow (`ProvenanceKind` other than human), on every route, action and tool; the chat write allowlist never
  gains an entry for this layer; and the unused suggestion models (`HermesSuggestionRequest`, `HermesSuggestion`) are
  deleted. Reading is open to tools. *Test (to write):* test_hermeneutic_refuses_non_human_actor.py (each mutating
  action with an agent actor is refused and writes no row).
- `hermeneutic.concept.is-the-framework-record` — **[GAP]** (#4692 → #7024) a historian's concept is stored in the
  framework record (name, definition, what counts, what does not, scope, versions) and its passages in the pattern
  record (seed passages and marked passages, each a stretch of a page with the person's mark), so the concept
  sheet adds no second store. The framework's `kind` list keeps its lenses and gains "concept". *Test (to write):*
  test_concept_is_a_framework.py.
- `hermeneutic.reading.rests-on-a-stretch` — **[GAP]** (#4692 → #7025) an interpretation (the historian's reading of
  a passage, or their judgement on sources that conflict) is anchored to one or more stretches of pages or to the
  statements it is about, with the same anchor a statement uses, so the Reader can light the passage and every
  explore view can open it. An interpretation with no anchor cannot be saved from the app. Restates and schedules
  `hermeneutic.interpretation-has-source-anchor` and `hermeneutic.interpretation-linked-to-claim-or-passage`.
  *Test (to write):* test_interpretation_anchor.py.
- `hermeneutic.argument.links-evidence-and-is-the-persons` — **[GAP]** (#4692 → #7029) the links a historian makes
  between things in this layer and the record are typed, owned and versioned: a term as evidence for a concept, a
  source's category treated as one of their types (`ontology.sources.mapping-is-a-persons-link`), a passage as a
  counter-example to a concept, one reading as support for or against another. Each link carries who made it, when,
  and the passages it rests on. Fichero never proposes one. *Test (to write):* test_argument_links_evidence.py.
- `hermeneutic.shown.as-the-persons-everywhere` — **[GAP]** (#4692 → #7028) wherever something from this layer is
  on screen beside what the sources say (a reading beside a conflict on a biography page, a concept as a row of a
  life band, a historian's type beside a source's word) it is drawn and labelled as the historian's, with their
  name and the date, and is never counted as an attestation or mixed into a count of what the sources say.
  *Test (to write):* HermeneuticMarksAreLabelledTests.swift.

- `hermeneutic.agency.reading-is-the-historians` — **[GAP]** (#4692 → #NEW-P9) when a source's statement gives an
  image, a river, a spirit, a document or any non-person an act ("the river took the mill"), the historian's reading
  of it (literal, figurative, belief, an account of responsibility) and any use of translation, mediation or an
  obligatory point of passage are interpretations of this layer: stored as theirs, linked to the statement and its
  stretch, drawn beside it with their name and the date. Fichero never labels an entity a mediator or an obligatory
  point and never ranks entities by centrality or importance. *Test (to write):* test_agency_reading_is_a_persons.py
  (a model's account cannot write one; the reading links to a statement).

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

**Confirmed live 2026-09-19 (maintainer test, → #4692):** the maintainer asked this exact
question directly, unprompted — how are hypotheses, citations, interpretations, and the rest
of this layer exposed at all? He wants FEWER rendering paths overall (echoing
`kg.read.statements-lens-becomes-the-paragraph` and `kg.read.one-renderer` in
`kg-readable-representation.md` — the same "too many renderers for one thing" pattern, a
different layer), and to be able to click around and see the source image from whichever kind
is currently showing, not just claims. This does not answer the five open questions below; it
confirms they are live, not hypothetical.

**Answered 2026-11-21 (owner's rulings, paraphrased):** this layer is reached while exploring. A concept is a node
in the sidebar whose Reader rendition is the concept sheet; a reading sits beside the passage or the conflict it is
about, on the biography page and in the Reader; and each opens the page image
(`explore/concepts-and-terms.md`, `kg/people-and-lives.md`). The Inspector tab stays as the list of one document's
readings.

## Open questions (for the maintainer — options the code makes cheap, not a recommendation)

1. **Answered in part** (owner 2026-11-21): the Reader and the sidebar are where this layer is met; the
   Inspector keeps the per-document list. **Does the Interpretations tab move, or does the Inspector stay its home?** The code makes
   cheap: (a) leave it in the Inspector, alongside Notes, as today; (b) give it a Reader
   rendition once it has a source anchor (mirrors the readable-representation ruling that the
   Reader shows content, the Inspector shows curation); (c) both — Inspector for the list/edit
   surface, Reader for a linked interpretation's highlighted passage once anchored.
2. **Answered** (design lead 2026-10-04, applying the spec's lean): Yes, wire the app's create form to send the claim or passage now, and build the anchors later. **Should an interpretation be linkable to a claim/passage before or after it gets a source
   anchor?** The engine already accepts `claim_id`/`passage_text` on create — wiring the APP's
   create form to send them is a small, standalone fix; a full char-span/rect anchor
   (`hermeneutic.interpretation-has-source-anchor`) is a bigger, separate piece of work. They
   can ship in either order.
3. **Answered** (owner 2026-11-21: patterns get their surface as the concept's passages; owner 2026-11-22): circle-state retires; the attestation sheet (`explore/concepts-and-terms.md`)
   replaces it, and no surface is built for it. Removing its code is not yet built.
4. **Answered** (owner 2026-11-21): no. The model never writes in this layer
   (`hermeneutic.layer.only-a-person-writes`). **Should interpretation actions join `CHAT_WRITE_ALLOWLIST`?** The mechanism is trivial (the
   actions are already registered and audited) — the only question is whether letting an agent
   record its OWN interpretation (as opposed to a human's) is a decision the creative director
   wants made now or deferred alongside the broader per-model tool-grant work
   (`research.md`'s `research.per-model-tool-grants`).
5. **Answered** (design lead 2026-10-04, applying the spec's lean): It belongs in the claim-editing spec. **Does `hermeneutic.claim-type-and-quotation-kind-are-modelled-not-editable` belong to this
   spec or to a claim-editing spec (`kg-tables.md`'s claim CRUD section)?** It's about the
   `KnowledgeClaim` model, not `Interpretation` — included here because #4692 framed it as part
   of the same "rich model, thin reach" finding, but it may belong split out.
