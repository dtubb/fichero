# KG Readable Representation — narrative biographies from claims — Design Spec (#TBD)

> Milestone: kg-readable-representation
>
> Design-led (Testing Constitution). **Status: APPROVED — 2026-09-10.**
> Tags: [OK] built · [PARTIAL] exists, extend · [MISSING] not built.
>
> **Scope boundary:** this specs HOW the readable representation is BUILT — a deterministic,
> background, backend NLG pipeline over the existing KG. It is NOT the document inspector
> (`kg-entity-inspector.md`), which is the display *interface*; that surface consumes what this
> produces. Two hard constraints: (1) **NO LLM generation anywhere in the path** — rendering is
> 100% deterministic from stored claims (the current `narrative_v1` LLM prompt "makes it up" and
> is the thing being replaced); (2) **any language**, not just Spanish/English.

## Why this spec exists

The KG is truth-bearing but reads like a database: dot-separated triples, review tables, and
(the least useful view) a hairball graph. A reader — a historian, the person whose life the
records describe — wants **readable English**: a biography ordered the way a writer would order
it (chronologically, or grouped by source), with every statement still carrying its evidence.
The goal is *programmatic but writerly* prose that never fabricates and never hides uncertainty.

This is a **backend text-generation** concern (claims + sources → ordered prose), which makes it
deterministic and **fully unit-testable without a GUI** — the right first target while the app
build is blocked. It iterates on what already exists; it does not replace it.

## What already exists (iterate, don't replace)

- `fichero-server/src/fichero_server/knowledge/paragraph.py` — deterministic claim→prose with
  `ParagraphStyle` (`narrative` / `list` / `footnoted`), superscript citation markers,
  `_claim_sentence`, `_group_claims` (merges mergeable claims), and subject/verb/object ordering
  via `knowledge/_common.py` (`order_statement_parts`, `render_statement`).
- `resources/prompts/catalogue/narrative_v1.md` — an LLM narrative prompt. **Corrected
  2026-09-18:** this is NOT a "polish layer" this spec's no-LLM path builds on — it is the very
  thing `kg.read.no-llm` bans from the render path, live today at the `/bio` route (see
  `kg.read.no-llm`, [BROKEN]). Kept here as a historical pointer, not an endorsed layer.
- `api/routes/entity/inspector.py`, `entity/entities.py` — entity-scoped read surfaces.
- Swift `Models/ClaimLine.swift` — the app's clause rendering (recent fix: trim run-on person
  spans / entity display names read naturally — commits 444dfc6c0, 9eeef2114).

## Theoretical grounding (this is an old, respectable practice)

Historians have rendered archives as readable text for two centuries; the genres have unfashionable
names but each is a **deterministic text rendering of a graph**, and Fichero can generate them all:
- **regest / calendar** — one dated paragraph per document, in order.
- **prosopographical entry** — a person's assertions gathered; **a biography is this done well**.
- **gazetteer entry** — a place's assertions gathered.
- **index nominum / concordance** — name/term → attestations.

The rigorous model underneath is **Bradley & Short's factoid model**: you never store "facts about
a person," you store **assertions a source makes** — each with date, place, role, citation. That is
*already what the extraction pipeline produces* (a `KnowledgeClaim` is a factoid: subject/verb/
object + source anchor + confidence), which is why this is cheap for Fichero — the data is right.
Precedents: Gramps narrative reports (GEDCOM→sentences+citations, decades old); Lsjbot (millions of
template articles — shows both the scale AND the flatness you get if you stop at templates); Abstract
Wikipedia + Grammatical Framework (Wikidata→multilingual via functions/lexemes — the serious bar).

## Intent (the design)

Given an entity (or a set), render a **biography** (or any genre above): readable prose composed
from its claims/factoids, under a chosen **ordering** and **grouping**, with citation markers
linking every statement to its source anchor, and with **uncertainty shown, not hidden**
(low-confidence or contradicted claims are marked, hedged, or sectioned — never silently asserted).
Composition is **100% deterministic** — no LLM in the path, ever — computed in the **background**
(like embeddings) and stored, not generated on demand in a web request. The rendered prose is in
**the language of the SVO/claim itself** — i.e. the language of the source the factoid was
extracted from (a claim from a Spanish document renders Spanish, a French source French); the
representation is multilingual *because the sources are*, so realisation must be language-aware
per claim, not a fixed language pair.

## Rulings (creative director, 2026-09-18) — the claim as the unit, re-centred, in the Reader, source-language-only

Four rulings, following a Fabel review (`fabel-kg-readable`, revision 2) that traced every live
renderer against the code. **Central finding the spec was silent on: there are FIVE renderers
today, not one** — the engine's `readable.py` pipeline (2026-09-10, stages 1/2/3/5/6 built, 24
tests) has **zero callers outside its own tests**; the biography a maintainer actually sees comes
from a separate ten-line Swift loop (`EntityDigestContent.biographySentences`,
`EntityDigestView.swift:648-675`) that puts the page's entity in front of the first claim and the
English word **"they"** in front of every other claim, regardless of who the claim is really
about. That one fact explains most of the four standing complaints (not clear / hard to edit /
wrong subject / not multilingual) — see `kg.read.one-renderer` below.

1. **The unit of editing is the claim, never the prose.** Acting on a rendered sentence opens the
   claim behind it (subject/verb/object/date) for correction, AND brings up the SOURCE the claim
   came from — the page image or document — with the claim's passage highlighted, in one gesture.
   The sentence re-renders from the corrected claim. The correction is audited, survives
   re-extraction, and is training data. See `kg.read.edit-unit-is-the-claim`,
   `kg.read.sentence-opens-source-highlighted`.
2. **Sentences are re-centred on the page's entity.** On an entity's own page, that entity is the
   grammatical subject of every sentence, including claims where the source made it the object —
   this needs a per-verb INVERSE phrasing table, per language. A verb with no inverse entry keeps
   the claim's TRUE subject rather than a false one. See `kg.read.recentred-on-page-entity`.
3. **The paragraph lives in the Reader pane** when an entity (or claim) row is selected; a
   sentence click drives the Source pane to the page with the span highlighted; the Inspector
   keeps curation (statements list, merge, aliases, history). See `kg.read.lives-in-reader`.
4. **Source language only, for now.** The paragraph renders in the document's own language; an
   entity evidenced in two languages gets sentences in each source's language, never a gloss or
   cross-language realisation — record that as deliberately deferred, not a gap to fix now. See
   `kg.read.source-language-only`.

**Today's complaints, restated as the problem these rulings answer:** not clear; hard to edit;
often the wrong subject; not multilingual.

## Behaviors

### A. Rendering architecture — one renderer, not five

- `kg.read.one-renderer` — **[BROKEN]** (#4832) there are FIVE renderers touching KG
  claims today, and the spec previously named none of this: (A) `EntityDigestContent
  .biographySentences` (`EntityDigestView.swift:648-675`) — **LIVE**, the biography the
  maintainer sees, mounted at `DocumentInspector.swift:207` and
  `DocumentInspectorEntitiesTab+Rows.swift:58`; (B) `ClaimLine.text` (`ClaimLine.swift:41-61`) —
  LIVE, the "Source Annotations" rows under the biography, and the one renderer that gets the
  subject right on the same screen; (C) a JS `claimSummary` in `document_view.html:971-976` —
  LIVE, the document-level KG web pane; (D) `paragraph.py`'s `render_paragraph_claims` — route
  `POST /api/kg/render/paragraph` exists, but the Swift wrapper `renderKGParagraph` has ZERO
  callers; (E) the `readable.py` pipeline (stages 1/2/3/5/6, 2026-09-10, 24 tests) — ZERO callers
  anywhere outside the file and its own tests. Every `kg.read.*` behavior below that cites a
  `readable.py` test is describing a module NOBODY SEES — retagged honestly below as
  "[PARTIAL] — built and tested in the ENGINE, not wired to any view" rather than the tag its
  test count alone would suggest. Target state: ONE renderer, in the engine (`readable.py`'s
  successor, the entry composer below); the app draws what it is given; (B)/(C)/(D)'s bespoke
  loops retire once the Reader rendition (`kg.read.lives-in-reader`) replaces them.

### B. Ruling 1 — the claim is the unit of editing

- `kg.read.edit-unit-is-the-claim` — **[PARTIAL]** (#4833) the underlying edit mechanism is SOUND:
  `InlineClaimEditor`/`EditClaimSheet` → `claim.patch` (`EditClaimSheet.swift:226-236` →
  `claims.py:498`) is undoable and audited
  (`@action("claim.patch", undoable=True, invert=_invert_patch_claim)`, `claims.py:1229-1234`)
  and survives re-extraction (`stamp`/`record_superseded`, `claims.py:531-536`, matched on re-run
  by `_corrected_claim_for_incoming`, `_entity_writer.py:1413`) — real training data. Three gaps
  keep this from being the ruling: (a) **a rendered sentence has no edit affordance at all** — a
  click only navigates (`EntityDigestView.swift:357-365`); (b) **a subject edit does not
  round-trip** — `_apply_claim_patch` (`claims.py:341-371`) syncs `svo_*` fields only, never
  `subject_entity_id`/`entity_ids`/`claim.text`, and the subject field is free text, not an
  entity picker; (c) **the editor has no date field**
  (`EditClaimSheet.swift:158-163`), so a claim's date cannot be corrected from the surface this
  ruling makes the unit of editing. `ClaimSummaryCardView`/`EntityDetailView`, the other reachable
  editors, are themselves marked retired (→ #4828, → #4791).
- `kg.read.sentence-opens-source-highlighted` — **[GAP]** (#4834) editing and source-reveal are two
  SEPARATE gestures today (edit → `EditClaimSheet`; navigate → `ClaimSourceNavigationState`
  → `handleOpenClaimSource`, `ContentView+StateEvents.swift:397-446`). The ruling wants ONE
  gesture: open the claim editor AND reveal the highlighted source together.
  `focusKGSourcePreview` (`ContentView+SourceNavigation.swift:147`) already reveals a source
  WITHOUT changing the current selection — that is the existing seam to build this on, not a new
  mechanism. The span/region/page-only precision rules `ClaimSourceRequest` already computes
  (`ClaimSourceRequest.swift:53-68`) are correct and reusable as-is.

### C. Ruling 2 — re-centred on the page's entity, honestly

- `kg.read.recentred-on-page-entity` — **[BROKEN]** (#4837) today's app ALREADY re-centres — that is the
  defect, not an absence: `let subject = first ? entityName : "they"`
  (`EntityDigestView.swift:663`) makes the page's entity the subject of every claim where it
  appears in `entity_ids` (`claims.py:1058`, "any mention" — subject, object, or merely named
  nearby via the alias-substring scan, `extractors.py:1665-1683`), regardless of the claim's own
  `subjectCanonical`, which is never read. The safety rule the spec must state: a claim is
  re-centred ONLY when its verb has an INVERSE entry in that language's table; otherwise it keeps
  its TRUE subject — never a false sentence. No inverse-phrasing table exists anywhere yet (this
  is stage 4, `kg.read.lexicalisation` below) — until it does, re-centring MUST fall back to the
  true subject, which is a smaller, immediate fix distinct from building the table.
- `kg.read.render-uses-claim-subject` — **[BROKEN]** (#4835) (RENDER layer specifically, the largest and
  cheapest of three wrong-subject causes — fix first) `EntityDigestView.swift:663`'s ternary
  never reads the claim's own subject; `ClaimLine.swift:54` on the SAME screen gets it right
  (drops the subject only when it equals the group subject). Fixing this one line — read
  `subjectCanonical`, keep "they"/re-centring only behind a verb's inverse-table entry — resolves
  most of the "wrong subject" complaint without touching extraction or resolution at all.
- `kg.read.extraction-subject-accurate` — **[BROKEN]** (#4836) (EXTRACTION layer) verified by running
  `propose_triples`/`filter_proposals` on real sentences: (i) English dependency labels are
  mis-mapped — `spacy_svo.py:50-51` expects Universal-Dependencies labels (`nsubj:pass`) but
  `en_core_web_sm` emits `dobj`/`pobj`/`nsubjpass`, so EVERY English object comes back empty and
  English passives are lost entirely; (ii) a relative pronoun ("que") is kept as a subject —
  not in the pronoun gate (`svo_quality.py:233-244`); (iii) a relative clause's subtree leaks
  into the subject span (`spacy_svo.py:115-122` filters the `relcl` head token, not its
  subtree); (iv) Spanish null-subject ("pro-drop") sentences yield NO triple at all
  (`if not subjects: continue`, `:145-146`) — silently dropped, not flagged for review;
  (v) a pronoun subject is rebound to the last named subject in ITEM-LIST order, not by anything
  in the text (`extractors.py:2460, 2501-2521`).
- `kg.read.resolution-avoids-bad-merges` — **[PARTIAL]** (#4842, RESOLUTION layer, smallest of the
  three contributors) `upsert_entity`'s fuzzy fallback (`SequenceMatcher` ≥ 0.78 when vectors are
  absent, `_entity_writer.py:550-553`) can fold a father/son or namesake pair; the guards
  (`_terminal_surname_diverges`, a mid-band review queue) are careful and no bad merge was
  reproduced in this review — INFERRED as a contributor, not verified as a live bug. Do not
  retune the resolution thresholds globally to chase this; route more cases to the review queue
  instead (a global retune re-binds FUTURE imports differently from past ones).

### D. Ruling 3 — the paragraph lives in the Reader

- `kg.read.lives-in-reader` — **[GAP]** (#4838) today the paragraph lives in the INSPECTOR
  (`DocumentInspector.swift:207`, `DocumentInspectorEntitiesTab+Rows.swift:58`), not the Reader
  pane. The click handler that should drive the Source pane is mode-era: `handleOpenClaimSource`
  (`ContentView+StateEvents.swift:397-446`) sets `sidebarMode` and selects the source document
  directly, and never reads `ClaimSourceRequest.destination` (`.reader` is set at
  `ClaimSourceRequest.swift:89`, but nothing in `Views/Shell/ContentView` reads `destination` —
  confirmed by grep, zero matches). Consequence (not yet manually verified, flagged as a
  precise check rather than assumed): selecting the source document today likely REPLACES the
  entity inspector under the current pane system, so the biography a user clicked from
  disappears — the exact "reveal without losing your place" problem `focusKGSourcePreview`
  already solves for a different call site. **Cross-spec note:** the exact matrix-row text for
  `ui/modes-to-panes.md` (code lane's file, not edited here) is given verbatim in this spec's
  Migration section below, for the maintainer to relay.

### E. Ruling 4 — source language only

- `kg.read.source-language-only` — **[BROKEN, partially]** (→ #4839) the ruling itself (no gloss, no
  cross-language realisation, ever) has nothing to remove — grep of `paragraph.py`, `readable.py`,
  `document_view.html`, `EntityDigestView.swift`, and `ClaimLine.swift` shows none of them read
  the `_en` gloss fields on a claim. But the DEFAULT the ruling implies — each sentence in ITS
  OWN source language — is not honored either: `readable.py`'s `language` is a PARAMETER for the
  WHOLE paragraph, defaulting to `"es"`, that nothing derives from the claim (`:185`); an unknown
  language silently falls back to English glue (`:191`); and the app's live renderer hard-codes
  English words directly (`"they"` at `EntityDigestView.swift:663`; `" and "`/Oxford comma at
  `paragraph.py:91-92`; `"source:"`/`"excerpt:"`/`"Footnotes:"`/`"p."` at `paragraph.py:263-267,
  329-333`; fixed S-V-O word order in three places). A claim has no single language field today —
  only `source_languages: list[str]` (`models/knowledge.py:1648`) — so "language per claim" means
  reading `source_languages[0]`. **Deferred, recorded not built (ruling 4 itself, not a gap):**
  multilingual gloss / cross-language realisation — explicitly out of scope, not forgotten.
- `kg.read.aggregation-never-crosses-languages` — **[BROKEN]** (#4839) `readable.py`'s aggregation key is
  subject + verb ONLY (`:126`) — it would merge claims across languages into one sentence with one
  glue language, the opposite of "language per claim." No test catches this because the pipeline
  has never been run on a genuinely mixed-language entity page.

### F. The six-stage NLG pipeline — retagged against what a screen actually shows

`readable.py` shipped 2026-09-10 (stages 1, 2, 3, 5, 6; 24 tests) — but per `kg.read.one-renderer`
above, it has zero callers. Every tag below reflects that: "[PARTIAL] — engine-only" means built
and tested, reachable from no screen.

- `kg.read.content-determination` — **[PARTIAL] — engine-only** (#4647) `select_entry_claims`
  (`readable.py:46`) selects "any mention" (subject, object, or named) for an entity; splitting
  by ROLE (subject/object/mention, distinct sections) is new work tracked under the entry
  composer (`kg.read.biography` below), not this stage. Pinned: 4 tests in
  `test_readable_representation.py` (content-determination suite).
- `kg.read.order.chronological` — **[PARTIAL] — engine-only** (#4648) as before, plus: confirmed
  built as a pure function and unit-pinned (`readable.py:89`, d8afa61e6, 1e6661b45, 6 tests);
  "unwired" is the SAME gap `kg.read.one-renderer` names, carried forward to the entry composer.
- `kg.read.order.by-source` — **[PARTIAL] — engine-only** (#4648) same as chronological above.
- `kg.read.aggregation-keeps-objects` — **[BROKEN]** (#4649) `render_aggregation`
  (`readable.py:193-196`) prints a COUNT instead of the objects when count > 1 — "Juan Asprilla
  sold 2 veces" loses *what* was sold. Retagged from the earlier "[PARTIAL, unwired]" framing:
  this is not just unwired, it is WRONG even in isolation, verified by running it. Also loses
  citations: `Aggregation.claim_ids` (`readable.py:112`) keeps the ids, but `render_aggregation`
  returns a bare `str`, so the ids are gone by the time there is a sentence to click — this is
  why `kg.read.every-sentence-sourced` below is [BROKEN], not [PARTIAL].
- `kg.read.every-sentence-sourced` — **[BROKEN]** (#4840) every rendered sentence must carry >= 1 claim id
  through to the click target. Today it does not survive aggregation (see above); the app's live
  renderer (A) DOES carry a source per sentence (`fichero-claim://<id>` link,
  `EntityDigestView.swift:393-397`) since it never aggregates — so the property holds only in the
  UNAGGREGATED, wrong-subject path, and fails in the aggregated, engine path. The entry composer
  (`kg.read.biography` below) must fix both at once.
- `kg.read.referring-expressions` — **[PARTIAL] — engine-only, and orphaned** (#4651)
  `referring_expression` (`readable.py:144`) is BUILT (a surname heuristic: "Asprilla", "Cruz"
  for "María de la Cruz") but stage 6 (`render_aggregation`/realisation) NEVER CALLS it
  (`:185` on). The app's live renderer doesn't use referring expressions either — it uses
  literal "they".
- `kg.read.lexicalisation` — **[MISSING]** (#4650) stage 4 — an (event-type, role) pair → a verb
  phrase in the claim's language, via a per-language table including the INVERSE map
  (`kg.read.recentred-on-page-entity` depends on this) and notarial first→third-person formulas.
  Not started (`readable.py:20-21` says so in its own docstring). **The per-language `inverse`
  map is seeded from verbs that actually occur most frequently in the maintainer's own
  libraries — a read-only frequency count through the running app, not an invented verb list.**
- `kg.read.biography` — **[PARTIAL] — the keystone, not built** (#4750) nothing composes the six
  stages into an entry today — no route, no caller, confirmed by grep. This IS the fix for
  `kg.read.one-renderer`: `render_entry(entity_id, ordering)` returning
  `sentences: [{text, start, end, language, claim_ids: [...], role: subject|object|mention,
  revoiced: bool}]` plus citations, served at `GET /api/entities/{id}/readable`, fixing
  aggregation (keep objects, never cross languages, language per claim) and wiring stage 5
  (referring expressions) in along the way. This is the sentence-record CONTRACT the rest of
  this spec (and the Reader rendition, `kg.read.lives-in-reader`) is written against.
- `kg.read.genre.regest` [MISSING] (#4653) — one dated paragraph per document, in order (calendar of docs).
- `kg.read.genre.gazetteer` [MISSING] (#4653) — a place's assertions gathered as an entry.
- `kg.read.genre.index-concordance` [MISSING] (#4653) — name/term → its attestations, sorted.
- `kg.read.confidence-visible` [MISSING] (#4751) — certainty surfaces as **hedge words +
  corroboration** (ruling, 2026-09-12): hedge words tuned to confidence, PLUS a triangulation
  signal — how many independent sources assert the factoid and whether any contradict — and
  always the linked sources. **Today's app shows a bare "×N"**
  (`EntityDigestView.swift:407-412`) — the exact device the 2026-09-12 ruling says misleads (a
  bare number reads as an invented score); words ("three sources agree") are the fix, not a
  redesign.
- `kg.read.clean-triples-before-render` — **[GAP]** (#3808) as before, the raw SVO/KVO triples a
  representation reads from are noisy — repeated near-duplicate labels for the same
  entity/predicate, ungrouped multi-participant events. **Partly already mitigated**: dedup and
  pronoun-quality gates exist at extraction time (`svo_quality.py`, `spacy_svo.py:251`) — this
  behavior's remaining scope is label-once canonicalization and reified multi-participant events,
  not a from-scratch problem.
  representation reads from are noisy — repeated near-duplicate labels for the same
  entity/predicate, ungrouped multi-participant events — and today's readable-representation
  layer renders straight from them. Cleaning belongs upstream of rendering: label-once
  (canonicalize a repeated label to one form), dedup (collapse near-identical triples before
  they reach a representation), and reified events (a multi-participant happening becomes one
  event node with roles, not N separate flat triples). Every `kg.read.*` behavior below reads
  cleaner once this lands; not built yet on either side.
### G. Provenance, integrity, and honesty of a re-voiced sentence

- `kg.read.provenance-linked` [OK, extend] — every statement keeps its citation marker → source
  anchor. This is TRUE of the app's live path (`fichero-claim://<id>` link,
  `EntityDigestView.swift:393-397`; `ClaimSourceRequest.request(for:)`,
  `ClaimSourceRequest.swift:76-103`, refuses to draw a highlight it cannot vouch for) — kept
  [OK]. It is NOT true of the engine path once aggregation is involved — see
  `kg.read.every-sentence-sourced` above, tagged broken for that reason — this behavior covers
  the UNAGGREGATED, per-sentence case only; do not read this OK tag as covering the aggregated
  engine path too.
  Pinned: `test_paragraph_rendering_helpers.py::test_render_narrative_merges_and_offsets_align`
  (marker↔claim↔offset for the OLD `paragraph.py` path, itself unused per `kg.read.one-renderer`
  — kept as a reference test, not evidence of a live behavior).
- `kg.read.vocabulary-closure` — **[GAP]** (#4841) the testable form of "the app never invents": a
  re-voiced sentence (re-centred per ruling 2, or aggregated) is still HONEST when every rendered
  word traces to the claim's own text, an entity's canonical name, or an entry in the language
  table — never free generation. Three UI/data disciplines make this checkable rather than just
  asserted: (i) a click always shows the VERBATIM source passage, highlighted; (ii) the claim
  panel shows the stored subject/verb/object exactly as extracted, beside the rendered sentence,
  so a re-voicing can be inspected against its source; (iii) a vocabulary-closure test asserts
  every word in a rendered sentence comes from one of the three sources above. None of the three
  exist yet.
- `kg.read.cite-to-segment` — **[PARTIAL]** (#4652, → #974) a citation resolves not just to a
  document/page but to the **page SEGMENT** (the bbox/region the claim was extracted from).
  Retagged from [MISSING]: this is PARTLY BUILT in the app already —
  `ClaimSourceRequest.swift:61-64` already carries region data through to a highlight — the spec
  previously said MISSING and was wrong. What remains: the ENGINE side (`paragraph.py` emits one
  marker per claim after a merged sentence, `:318-325`, locating the superscript, not a sentence
  span — there is no sentence span in `ParagraphRenderResponse`, so "click the sentence" itself,
  as opposed to "click the marker," is unrepresentable there) and the entry composer's
  `sentences[].start/end` contract (`kg.read.biography`) closing that gap. → #974 frames the same
  chain more broadly as a first-class KG edge type: in-text marker → bibliography entry → claim,
  surfaced per-document AND library-wide — the library-wide aggregation is additional scope.
- `kg.read.expose-kg-on-hover` [MISSING] (#4652) — hover/click on a statement reveals **what the KG knows**
  behind it — location, dates, roles, confidence, the raw SVO — rendered readably (not raw JSON),
  as the bridge from prose back to structure back to source.
- `kg.read.audit-history` [MISSING] (#4660) — expose the factoid's HISTORY, not just its current state:
  the original extracted names before canonicalisation, how entities were merged (`merged_into_id`),
  the `curation_state` (blessed / rejected / merged) and who/when (`created_by`, `created_at`,
  `attribution_chain`). Much of this is already stored — the render surfaces it readably so a
  reader can see how a factoid came to read the way it does, not just trust it.
- `kg.read.generation-provenance` [MISSING] (#4652) — the render is no-LLM, but the underlying CLAIM was
  extracted by a model+prompt+run; that generation provenance (which model, which prompt version,
  which run) is exposed alongside the source, so a reader sees not just *where* the factoid came
  from but *how it was made*. Ties to run-scope provenance logging.
- `kg.read.no-llm` — **[BROKEN]** (#4652) NO generative model may be anywhere in the render
  path. `paragraph.py` and `readable.py` call no model — VERIFIED by reading both files whole,
  confirming the intent — but retagged [BROKEN] rather than [MISSING]: **an LLM biography
  endpoint IS live on the engine**, `POST /api/kg/entities/{id}/bio`
  (`api/routes/kg/render.py:117-191`) calls `chat(...)` (`:156`) and WRITES the result into
  `entity.description` (`:172-188`), which `EntityDigestContent` displays directly ABOVE the
  deterministic biography (`EntityDigestView.swift:324-329`). The Swift wrapper
  (`generateKGEntityBiography`) has no in-app caller, but CLI/MCP/agents can reach the route —
  this is a live violation of the AI-as-instrument north star, not a theoretical one. **Retiring
  it is the creative director's decision, explicitly not decided here** — see Open Questions.
  A future guard test must assert on CALLS (patch `llm.chat` to raise) and on PURITY (same input
  → same output), not on imports: `paragraph`/`readable` transitively import
  `fichero_server.llm` via the models package, so an import-based guard fails as written.
- `kg.read.language-of-svo` — **[BROKEN, overstated]** (#4651) retagged from [PARTIAL]: the spec
  previously read as if a claim's language is genuinely read and honored per-sentence. It is not
  — the existing tests (`test_realises_single_claim_in_spanish`,
  `test_realises_aggregated_count_and_places_in_english`,
  `test_unknown_language_falls_back_to_english_glue`,
  `fichero-server/tests/unit/knowledge/test_readable_representation.py`) prove a `language`
  PARAMETER can be passed and produces different glue words — they do not prove a claim's own
  stored language is ever READ and threaded through. See `kg.read.source-language-only` and
  `kg.read.aggregation-never-crosses-languages` above for the concrete gaps this behavior was
  overstating.
- `kg.read.background` [MISSING] (#4752) — the representation is computed in the background and stored
  (auto-throttled, like embeddings — the machine stays usable), not synthesized per web request.
  Last priority — string joining over at most 500 claims per entity; do this only if measured
  slow, not pre-emptively.

## Build: the Reiter & Dale NLG pipeline (six small, testable Python stages)

The classic NLG pipeline decomposes into six stages, and **each is a small pure function with its
own unit test** — which is exactly why this whole feature is headless-testable:
1. **Content determination** — which factoids belong in this entry (by entity, date range, genre).
2. **Document structuring** — order/section them: chronological, by life-stage, or by theme
   (family / property / litigation). (= `kg.read.order.*`)
3. **Aggregation** — collapse repetition: "seven witness appearances" → one sentence with a count
   and a place distribution. (extends `_group_claims`)
4. **Lexicalisation** — each (event-type, role) pair → a verb phrase, in **the claim's language**
   via a per-language lexicon table (add a language by adding a table, not code).
5. **Referring expressions** — full name on first mention, surname after, pronoun within a paragraph
   (pronoun/agreement rules are per-language).
6. **Realisation** — agreement + morphology, per language. Library landscape (researched 2026-09-10,
   for a Python backend):
   - **Default (ponytail): Jinja2 + per-language lexicon/rule tables** — deterministic, zero new
     deps, exactly how `paragraph.py` already works. **The active language(s) come from the
     project/collection setting (ruling 3), not a hardcoded list** — each language is a data table
     loaded on demand; the current corpus seeds Spanish, but nothing in code assumes it. Lsjbot
     proves this scales (and warns of flatness — mitigated by aggregation + referring-expression
     variation, stages 3 & 5).
   - **Any-language escalation: Grammatical Framework** via the `pgf` Python runtime — one abstract
     tree → concrete grammars per language; this is what **Abstract Wikipedia** uses. The principled
     answer when a language's morphology outgrows rule tables. Heavy (write grammars) — adopt only
     when it earns its keep.
   - **pyrealb** — native-Python (no bridge), realizes EN+FR deterministically; a light step if EN/FR
     realisation is needed before committing to GF.
   - **SimpleNLG-ES** (Java, via server/bridge) — mature Spanish realiser if the ES rule tables prove
     too weak before GF is worth it.
   NEVER translate a claim across languages — render each in its own (the `_en` fields are a
   pre-existing extraction-time translation, usable for an English rendering, not a license to
   translate other languages).

`paragraph.py` already implements a thin slice of stages 3–6 for a single paragraph; this spec
extends it stage by stage to entry/biography scale, each stage landed test-first.

**Prior art to build on (RDF/linked-data crowd — researched 2026-09-10):** the semantic-web
community verbalizes graphs to text with **LD2NL / SPARQL2NL / SemWeb2NL** (rule+template RDF→text),
whose pipeline (lexicalization → single-triple realization → clustering → ordering → grouping)
*mirrors Reiter-Dale* — independent confirmation the deterministic path is sound. **CIDOC-CRM** is
the ISO ontology the cultural-heritage crowd uses for exactly this factoid substrate (events,
actors, places, times); our factoids map to it, so they can be imported from / exported to an RDF
server as linked open data (cf. Enslaved.org). The readable render must work over a factoid whether
it came from the extraction pipeline OR an RDF import — same substrate, same rendering.
**CIDOC-CRM import/export itself is LATER — it belongs to the import/export engine, not this spec.**
This spec keeps the DH deterministic approach; CIDOC-CRM I/O is a separate future milestone.
**Corrected 2026-09-18:** the previous wording here ("stages 1-3 shipped, 12 tests green") was
true and misleading at once — shipped to a module with zero callers is not the same claim as
shipped to a reader. See `kg.read.one-renderer` for the honest framing and the migration plan
below for how it gets wired.

## Test matrix (BACKEND-heavy — this is why it's the right headless target)

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (py) | y | ordering (chronological/by-source), grouping, hedging by confidence | `fichero-server/tests/unit/knowledge/test_readable_representation.py` |
| Backend (pytest) | y | the render endpoint returns ordered prose + markers for a seeded entity | `fichero-server/tests/…` |
| No-LLM guard (py) | y | render module calls no LLM client; output is a pure function of its claims | same |
| Multilingual (py) | y | a claim renders in ITS language; adding a language = adding a lexicon table | same |
| Availability (Swift) | y | the reader surface wires the readable render | `fichero/Tests/Unit/**` |
| Snapshot (Swift) | y | a biography renders legibly (chronological + by-source states) | `fichero/Tests/Unit/**` |
| Click-around (XCUITest) | y | open an entity → read its biography → click a citation → its source | `fichero/Tests/UI/**` |

Hard-gate: `kg.read.no-llm` (integrity — the AI-as-instrument north star; no fabrication) and
`kg.read.provenance-linked` (every statement traceable to its source).

## Related vision — NOT this spec (future, separate specs)

The user's DH survey maps future **visualization** surfaces; each is its own spec when taken up.
Captured here so the research isn't lost, deliberately out of scope for the readable-text spec:
- **Finding-aid graphs** (ego networks, confidence-scored edges) — Six Degrees of Francis Bacon,
  Linked Jazz, CBDB. Grape (Swift d3-force port) or sigma.js in the new SwiftUI `WebView`.
- **Time axis** — storyline/arc/attestation timelines; Digital Panopticon life-courses; Swift
  Charts rule/bar marks; deck.gl TripsLayer for movement.
- **Map + graph** — Chocó terrain (Copernicus/SRTM DEM), HydroRIVERS, Codazzi/Comisión
  Corográfica sheets georeferenced via Allmaps (IIIF), HGIS de las Indias jurisdictions; MapLibre
  GL (web, shareable) embedded via `WebView`, native `Map(.mapStyle(.hybrid(elevation:)))` for
  the light in-app view.
- **Matrices** — reorderable co-occurrence heatmaps (Swift Charts `RectangleMark`); hierarchical
  edge bundling onto fondo→legajo→expediente.
- **Embedding space** — Chart3D (macOS 26) or Nomic-Atlas-style zoomable map of the sqlite-vec
  vectors.
- **RealityKit space-time cube** — Chocó map on the floor, time up, trajectories threading mines
  and towns (Hägerstrand); exports USDZ/glTF for sharing. Earns 3D only when the third axis means
  something.
- **Architecture principle** (from the survey): Python owns layout (networkx/igraph/Graphviz/UMAP
  → x,y,z,t in SQLite); the app draws coordinates (SwiftUI Canvas); the SAME coordinates feed a
  web front end (FastAPI) so the Mac view and the shareable link never drift.

## Cross-surface & authoring (the invariant to hold — audit tracked separately)

The factoid substrate is rich (audited 2026-09-10: who-asserts, date, place, role, citation,
Toulmin, confidence, language, generation-provenance all present). The open concern is whether
every dimension we can STORE is also: (a) visible in the UX (KG tables / inspector), (b)
**authorable by BOTH a person (manual) and the extraction pipeline (LLM)** — never LLM-only, and
(c) tested end-to-end (backend ↔ MCP ↔ CLI ↔ UX — the Constitution's hard-gate invariant). This
readable rendering is a READ view of that substrate; the authoring/visibility audit belongs to
`kg-tables.md` / `kg-entity-inspector.md`. Tracked, not assumed.

**Idea (Abstract Wikipedia / GF):** multilingual NLG organized into abstraction levels lets code
be shared across languages and splits labour between programmers (grammars) and authors (content);
a **Controlled Natural Language** puts a human in the loop to author/correct factoids in
constrained prose that round-trips to structure. A candidate future authoring path — deterministic,
no-LLM, and the same abstract representation the render reads.

## Rulings (creative director, 2026-09-12)

1. **Default ordering = chronological, changeable.** A reader lands on the chronological
   reading; a control switches to by-source. Either way **every statement always shows its
   source and date** — a click on any statement opens its provenance (source anchor →
   `kg.read.cite-to-segment`). Ordering is a lens over the same evidence, never a filter that
   hides it. (Resolves `kg.read.order.chronological` as the default; `by-source` is the toggle.)

2. **Confidence reads as hedge words AND triangulation — the point is "this is not magic."**
   Default to hedge words in the prose ("is said to have", "probably"), but the surface must make
   clear the render is evidence, not an oracle. A bare confidence *dot/number can mislead* (it
   reads as a made-up score), so express certainty primarily through **corroboration /
   triangulation** — how many independent sources assert the same factoid, and whether any
   contradict — not just the stored per-claim confidence. So `kg.read.confidence-visible`
   surfaces: (a) hedge words tuned to confidence, (b) the corroboration count ("three sources
   agree", "only one source, uncorroborated", "sources disagree"), and (c) always the linked
   sources themselves. A separate "less certain / disputed" section is allowed but is not the
   primary device. Never render a single low-confidence, single-source claim as flat fact.

3. **Realisation language is GENERIC and chosen at onboarding — no hardcoded language list.**
   This is a Python-backend concern and must not bake in Spanish/English. The active
   language(s) are a **user setting picked at onboarding, per project — and settable per
   collection**. The per-language lexicon/rule tables are data (a table per language), loaded for
   whatever language(s) the project/collection declares; adding a language is adding a data table,
   never code (see stage 4/6 below). Connective/structuring prose follows the entity's dominant
   *claim* language, but the set of languages the pipeline realises is driven by that
   project/collection setting, not by a fixed pair. (Claims themselves always render in their own
   language regardless — `kg.read.language-of-svo`.) The current corpus is Spanish-first, but that
   is a *setting value*, not a code assumption — the design ships generic and seeds Spanish.

## Migration — the ordered deliveries (Fabel review, `fabel-kg-readable`, 2026-09-18)

Principle: **one renderer, in the engine; the app draws what it is given.** Each delivery ships
alone, with its own tests. Wrong subject first, because it's the cheapest fix with the largest
visible payoff.

1. **Stop asserting the wrong subject (app, small).** `biographySentences` reads the claim's own
   `subjectCanonical`; the literal string "they" is removed. Tests: object-side and mention-only
   claims keep their TRUE subject. Interim fix — this whole loop is deleted in step 6. →
   `kg.read.render-uses-claim-subject`.
2. **Extraction subject fixes (engine; new extractions only, never a batch re-run — see Risks).**
   Fix the English dependency-label mismatch (`spacy_svo.py:50-51`); add the relative pronoun to
   the pronoun gate; exclude the relative-clause subtree from the subject span; bind pronoun
   antecedents only within the same sentence, else route to review. Tests: the exact sentences
   traced in this spec's `kg.read.extraction-subject-accurate`. → that behavior.
3. **Entry composer (engine, #4750, the keystone).** `render_entry(entity_id, ordering)` →
   `sentences: [{text, start, end, language, claim_ids: [...], role: subject|object|mention,
   revoiced: bool}]` + citations, served at `GET /api/entities/{id}/readable`. Fixes aggregation
   (keep objects, never merge across languages, language per claim) and wires stage 5 (referring
   expressions) in. Tests: every sentence has ≥ 1 claim id; offsets slice back to their own
   tokens; the function is pure; a mixed-language entity page gets each sentence in its own
   language. → `kg.read.biography`, `kg.read.aggregation-keeps-objects`,
   `kg.read.every-sentence-sourced`, `kg.read.aggregation-never-crosses-languages`.
4. **Stage 4 as data (engine, #4650).** One file per language: conjunction, "times", "at", page
   abbreviation, date pattern, role order, the verb → inverse-phrase map, and notarial
   first-person → third-person formulas. Seed `es` and `en` from the verbs that actually occur
   most frequently in the maintainer's own libraries (a read-only count through the running app —
   never an invented verb list). Test: adding a third language means dropping in a new file, no
   code change. → `kg.read.lexicalisation`.
5. **Re-centring (engine).** `role: object` + an inverse-table entry → the page entity becomes
   the subject, `revoiced: true`; no entry → the claim's TRUE subject, unchanged. Property test:
   the page entity is never the subject of a verb lacking an inverse entry, plus the
   vocabulary-closure test from Open Question 2. → `kg.read.recentred-on-page-entity`,
   `kg.read.vocabulary-closure`.
6. **Reader rendition (app).** The Reader pane gains the entity paragraph, drawing
   `sentences[]` from the entry composer's contract above; `biographySentences` is deleted.
   Sentence click → Source pane through the `focusKGSourcePreview` seam, selection untouched;
   an aggregated, multi-source sentence opens a short list of its sources instead of guessing
   one. The Inspector keeps the statements list, merge, aliases, and history. → `kg.read.lives-in-reader`.

   **Exact matrix-row text for `ui/modes-to-panes.md`** (that spec is the code lane's — relay
   this, don't edit it here): *"Entity or claim row selected → Reader = the readable paragraph
   (drawn from the entry composer's `sentences[]`); Source = the cited page, span highlighted,
   revealed via `focusKGSourcePreview` without changing the current selection; Inspector = KG
   curation (statements list, merge, aliases, history) unchanged."*
7. **Edit from the sentence (app + engine).** Acting on a sentence opens the claim editor AND
   reveals the highlighted source in one gesture. Add the date field to the editor; the subject
   field becomes an entity picker that patches `subject_entity_id` + `entity_ids` (never just
   `svo_*` text), and the patch regenerates `claim.text`. When a claim renders on more than one
   entity's page (e.g. a sale — direct on the seller's, inverse on the buyer's), the editor says
   so before saving ("also appears on Pedro Mosquera's page") — mechanically this already works,
   since `claimStore.changeToken` triggers a re-read on every page showing that claim
   (`EntityDigestView.swift:286`). → `kg.read.edit-unit-is-the-claim`,
   `kg.read.sentence-opens-source-highlighted`.
8. **Guard and honesty (engine).** A no-LLM test that patches `llm.chat` to raise and asserts
   purity (not an import check — `paragraph`/`readable` transitively import `fichero_server.llm`
   via the models package, so an import-based guard fails as written); retire `/bio` (pending the
   creative director's decision, Open Question 8); corroboration in words, replacing "×N"
   (#4751). Background precompute (#4752) is LAST, and only if measured slow — this is string
   joining over at most 500 claims. → `kg.read.no-llm`, `kg.read.confidence-visible`,
   `kg.read.background`.

## Risks to real libraries (Fabel review, section 9)

- **Nothing above requires a migration or rewrites a stored row.** Deliveries 1 and 3–6 are
  read-side only.
- **Delivery 2 (extraction fixes) changes FUTURE extractions only.** Do not batch re-extract to
  "fix" old claims: a re-run is protected for claims a human has EDITED
  (`record_superseded` matches them back), but an un-edited row whose subject span changes on
  re-extraction will not dedup against its old self — it will DUPLICATE. If a cleanup pass is
  ever wanted, it must be a reviewable proposal list through the running app's action layer,
  never a standalone-engine pass (standing rule: never standalone-engine surgery).
- **Delivery 7 (the subject picker) changes `entity_ids` on a curated claim** — it must go
  through `claim.patch` (undoable, audited) and must ADD the new entity without silently removing
  the claim from pages a person already placed it on.
- **Tightening the alias-scan (the render-time amplifier named in
  `kg.read.render-uses-claim-subject`) would change which pages OLD claims appear on if re-run.**
  Leave stored `entity_ids` alone; fix this at RENDER time by role instead (delivery 3's
  role-aware content determination), not by re-running the scan.
- **`/bio` retirement:** existing `entity.description` values may be model-written
  (`metadata.biography_provenance` marks them). Do not delete any of them — label them, and let
  the person keep or clear each individually.
- **Entity-resolution thresholds (the RESOLUTION layer, `kg.read.resolution-avoids-bad-merges`):**
  do not retune globally to chase the wrong-subject complaint — any global change re-binds
  FUTURE imports differently from past ones. Route more ambiguous cases to the review queue
  instead.

## Open questions

Copied from the Fabel review's design questions (section 7) with its recommendations. The
manager is proceeding on each recommendation unless the creative director says otherwise, with
ONE exception (#8) that stays an open question FOR him specifically.

1. **A verb with no natural inverse** ("doy fe", "compareció", intransitives, anything not yet in
   the table). *Recommendation (proceeding):* the sentence keeps the claim's true subject and
   sits after the re-centred run — never the entity's name in front of a verb it did not perform.
2. **Is a re-voiced sentence still sourced?** *Recommendation (proceeding):* yes — the source span
   is the evidence, the sentence is a rendering. Keep it honest three ways: (i) a click always
   shows the verbatim passage, highlighted; (ii) the claim panel shows the stored S/V/O beside the
   rendered sentence; (iii) a vocabulary-closure test asserts every rendered word comes from the
   claim, an entity name, or the language table — never free generation. → `kg.read.vocabulary-closure`.
3. **One aggregated sentence, several sources.** *Recommendation (proceeding):* the sentence is
   one click target that opens a short list of its sources (document, page, verbatim passage),
   each driving the Source pane; a single-source sentence goes straight there. Keep the objects in
   the sentence ("sold the mine and two slaves") — a count alone is not a reading.
4. **One claim on two entity pages** (a sale: direct on the seller's page, inverse on the
   buyer's). *Recommendation (proceeding):* both are renderings of ONE claim id — one edit
   re-renders both, and the editor says so before saving.
5. **First-person notarial voice under a named subject** ("Adolfo Hurtado doy fe").
   *Recommendation (proceeding):* quote it (*Adolfo Hurtado: "doy fe…"*); third-person rewrite
   only for the fixed formulas already listed in `FORMULAIC_PATTERNS`.
6. **Spanish sentences with no explicit subject**, dropped at extraction today.
   *Recommendation (proceeding):* surface as review proposals with an empty subject; never
   auto-bind to a guessed one.
7. **Merely-mentioned claims** (entity neither subject nor object, often placed there by the
   substring alias scan). *Recommendation (proceeding):* out of the paragraph, into an "also
   mentioned in" list below it.
8. **The LLM biography endpoint (`/bio`).** *Recommendation:* retire it; label existing
   model-written descriptions, never delete them. **This one stays open FOR THE CREATIVE
   DIRECTOR specifically — not proceeding on the recommendation without his ruling**, since it's
   a north-star/integrity call, not an implementation detail.
9. **The "×N" marker** vs. the 2026-09-12 ruling that a bare number misleads.
   *Recommendation (proceeding):* words ("three sources agree").
10. **A language with no table yet.** *Recommendation (proceeding):* render the claim verbatim,
    no glue words — never silent English.
