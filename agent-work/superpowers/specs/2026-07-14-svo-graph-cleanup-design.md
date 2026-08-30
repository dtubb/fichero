# SVO / Knowledge-Graph Cleanup — Design (issue #3808)

**Date:** 2026-07-14 · **Status:** COMPLETE — ready for review / worker dispatch
**Input:** issue #3808 (Daniel's 6-stage spec + `clean_svo.py` prototype, not in repo)
**Author:** design agent (research + design only; no source changes)

## 0. Constraints (fixed, not relitigated here)

1. **Non-destructive.** Raw SVO triples stay stored; cleanup is a derived display/export layer with full provenance back to raw triples.
2. **No parallel entity-merger.** Stage 2 normalization feeds the existing triangulation / entity-curation machinery.
3. **Reuse `events_extract`** for stage 5 reification; no second event mechanism.
4. **Dedup threshold (0.86) + abbreviation table are consequential.** Verified counts (Ana María 6→4, Antonio 6→4, Matheo 5→5) become regression tests.

## 1. Where the raw SVO lives and how it is read (verified trace)

All paths engine-side are under `fichero-server/src/fichero_server/` unless noted. Verified against `~/code/fichero` main on 2026-07-14.

### 1.1 Extraction (write side)

- **Section definitions** — `workflows/tools/extractors.py:141` (`_SECTIONS`). Each section (people, places, organizations, dates, rivers, **events** at `extractors.py:277-305`, mines, …) defines a `schema_key`, an `entity_type`, and an LLM prompt whose item shape is `{"name": …, "verb": …, "object": …}` — the SVO comes from the LLM already split into implicit-subject + verb + object. The people prompt explicitly says *"name is the implicit subject, do NOT repeat it inside verb or object"* (`extractors.py:160-163`) — **so the "subject restated on every clause" noise Daniel sees is partly a prompt-compliance failure and partly display composition (see §1.3), not a storage design.**
- **Per-entity SVO extraction (step 3)** — `workflows/tools/extract_svo_only.py:138` (`extract_svo_only`), registered as workflow tool (line 93), used by `resources/default_workflows/catalogue_stage_3_extract_svo.json:32` and `catalogue_full_pipeline.json:52`. It loops document × entity and calls `_extract_claims_for_entity` (imported from `extract_all.py`, see `extract_svo_only.py:27-32`), then persists via `_write_kg_rows` (`extract_svo_only.py:234-244`). **Extraction is per-entity: the same sale sentence is extracted once for Ana María, once for Antonio, once for the Convento — producing N separate claim rows for one event. This is the root of "same sale repeated on every participant node"; it is written that way, not just rendered that way.**
- **Persistence** — `workflows/tools/extractors.py:2016` (`_write_kg_rows`): upserts one `KnowledgeEntity` per item (by canonical name + alias index, `extractors.py:1681` `_build_alias_index`) and one `KnowledgeClaim` per predicate, via `_entity_writer.upsert_entity` / `save_claim` (`extractors.py:2063`). Also already contains an **event grounding guard** (`extractors.py:2078-2110`) that drops hallucinated events, and a first-person rewrite (#963, `extractors.py:2112+`).
- **Explicit writer node** — `workflows/tools/kg_writer.py:41` (`kg_writer`) persists the same bundles when `extract_all` runs with `persist_kg` off.

### 1.2 Storage (the raw truth)

- `KnowledgeClaim` — `knowledge/knowledge_models.py:1514`. First-class SVO fields: `subject_canonical` (:1612), `subject_entity_id` (:1621), `predicate_verb` (:1629), `object_phrase` (:1637), plus `svo_subject/svo_verb/svo_object` (:1647-1663). Provenance is already rich per claim: `source_document_id` (:1522), `source_page_label` (:1524), `source_excerpt` (:1525), `source_char_start/end` (:1532-1533, sub-page anchor #913), `source_bbox` (:1590). **The raw store already has everything the provenance model needs.**
- `KnowledgeEntity` — `knowledge/knowledge_models.py:723`: `canonical_name`, `aliases`, `merged_into_id` (:744, soft-delete merge pointer), `curation_state` (:742), `source_document_ids` (:738).
- Persistent curation-rule models **already exist**: `EntityResolutionRule` (`knowledge_models.py:771` — `rule_type`, `match_canonical_name`, `target_canonical_name`, `reason`, `created_by`) and `ClaimSuppressionRule` (`knowledge_models.py:786` — `match_predicate_verb`, `match_subject_name`, `match_object_phrase`, `suppress_is_a_copulas`). Merge operations are audited and reversible: `EntityMergeAudit` (:809), `ClaimMergeAudit` (:832).

### 1.3 Read path (what the Knowledge view actually calls)

- The Swift Knowledge pane is a **WebView onto engine-rendered HTML**: `fichero/fichero/Views/Reader/Knowledge/DocumentKGWebPane.swift:20-53` builds `\(baseURL)/view/document/{doc_id}` (or `/view/kg/global` for the global graph) and loads it in a `WKWebView` (`DocumentKGWebPane.swift:618-638`).
- Engine route: `api/routes/views.py:136` (`document_view`) — loads the document, collects claims for the document subtree (`views.py:150-151`), scopes entities (`views.py:122-133`), and renders the Jinja template `api/templates/document_view.html` with `entities_json` + `claims_json` (`views.py:204-214`). `views.py:217` (`global_kg_view`) is the unscoped variant (250-row cap, `views.py:23`).
- Template rendering — `api/templates/document_view.html`:
  - `claimSummary()` at `document_view.html:597-602` composes each row as `subject_canonical + predicate_verb + object_phrase` — **the subject is restated on every clause at render time even when stored cleanly split.** Stage 3 ("label once per node") is therefore mostly a one-line display change in this function when rendering inside an entity group.
  - `groupedClaims()` at `document_view.html:604-625`: every claim is pushed into **each** of its `entity_ids` groups (`:618-622`) — a claim shared by N entities appears N times.
  - Graph nodes are built per entity at `document_view.html:794+`; events (entity_type `event`) already appear as their own nodes because `events_extract` has `entity_type: EntityType.event` (`extractors.py:281`).

### 1.4 Daniel's raw "Part 1" output

The noisy per-entity clause list Daniel pasted matches the **claims panel of `document_view.html`** (entity heading + one composed `claimSummary()` line per claim, `document_view.html:715-735`). The same data is reachable via `GET /api/entities/{id}/digest`-style routes (`api/routes/entities.py`, `entity_inspector.py`) and the generated CLI (`cli/openapi_surface_generated.py:13372` wraps `/view/document/{doc_id}` itself). There is no separate formatter that dedups — every reader shows raw claims verbatim. (Could not determine which exact surface Daniel copied from; all of them show the same raw rows, so the design targets the shared read layer.)

## 2. Where the transform should live

**Recommendation: a pure, deterministic view module — `knowledge/svo_cleanup.py` — called at read time by the existing endpoints. Not a workflow stage, not a data migration.**

```
raw KnowledgeClaim/KnowledgeEntity rows  (untouched, canonical)
        │
        ▼  clean_svo_view(entities, claims) -> CleanedGraph   (pure fn, stdlib only, stages 1–4)
        │
        ├── views.py document_view / global_kg_view → template renders cleaned; raw reachable per-clause
        ├── kg_sparql.py export_rdf?view=cleaned    → Turtle with reified event
        └── (later) translation decorator over the CleanedGraph
```

Why this placement and not the alternatives:

- **Workflow stage (rejected as the primary home):** a workflow stage writes rows. Anything written becomes a second copy of the truth that can drift from the raw claims and would need migration discipline (memory: Marshall diaries are real data). Stages 1, 3, 4 are cheap enough (string ops over ≤ a few hundred claims per document; the global view is already capped at 250 rows, `api/routes/views.py:23`) to compute per request. **Exception:** stage 5 (reification) is an LLM pass and *must* persist — but it persists through the existing write path (`save_claim` / `upsert_entity`), producing ordinary audited rows, not a parallel store (§5).
- **Export mode only (rejected):** Daniel's pain is the *Knowledge view*, not just export. The same `CleanedGraph` feeds both.
- **Mutating cleanup script (`clean_svo.py` run over the DB — rejected):** destroys the raw layer; violates constraint 1 outright.

The `CleanedGraph` shape (engine-side dataclasses / Pydantic, serialized into the template payload):

```python
CleanedClause: {
    display_text: str,             # de-hyphenated, abbrev-normalized, subject stripped
    predicate_verb: str, object_phrase: str,
    source_claim_ids: list[str],   # ≥1 — EVERY raw claim this row absorbs (provenance)
    transforms: list[str],         # e.g. ["dehyphenate", "abbrev:dho→dicho", "dedup:0.91"]
    corroboration_count: int,      # from the absorbed claims
}
CleanedNode: {
    entity_id: str, label: str,    # label ONCE, normalized
    raw_labels: list[str],         # surface forms absorbed ("dho Combeto", "Comvento", …)
    clauses: list[CleanedClause],
    event_refs: list[EventRef],    # "→ Sale-1 (seller)" chips, stage 5
}
CleanedGraph: { nodes: [...], events: [...], suppressed: [...] }  # suppressed = dropped claims + reason
```

**Invariant (testable): every raw claim id appears in exactly one clause's `source_claim_ids`, or in `suppressed` with a reason. Nothing silently disappears.** This is the provenance spine (§6) and satisfies the "no silent fallback" memory.

## 3. Stage-by-stage mapping (Daniel's spec → real code)

| Stage | Daniel's spec | Existing code | What's new |
|---|---|---|---|
| 1 De-hyphenate | `(\w)-\s+(\w)` | `workflows/tools/ocr_cleanup.py:71` `_dehyphenate` — **exact same idea**, regex `(\w)-\n(\w)` (`ocr_cleanup.py:68`), newline-only | A `(\w)-\s+(\w)` variant in `svo_cleanup.py` (stored claim text has spaces, not newlines). ~5 lines. Long-term fix is upstream: run `ocr_cleanup` before extraction (related to the #3805 transcript de-hyphenation work) so future claims are born clean; the display fix covers the existing corpus. |
| 2 Abbreviations | dho→dicho, Combeto\|Comvento→Convento, adon→a don, Vezino→Vecino, … | **No scribal-abbreviation table exists anywhere in the engine** (searched `dicho`, `Vezino`, `abbreviat`, `scribal` — only test data). Entity resolution machinery DOES exist: §4 | The table itself (module constant, word-boundary, case-insensitive) + the curation-rule seeding (§4). Split into (a) *predicate-text normalization* (display-only, safe) and (b) *entity-label merge* (goes through curation, §4). |
| 3 Strip repeated subject | drop clause prefix = node name; label once per node | The store is already label-once: `subject_canonical`/`predicate_verb`/`object_phrase` are separate fields (`knowledge_models.py:1612-1643`), and the extraction prompt already demands implicit subject (`extractors.py:160-163`). The restatement is *re-introduced at render*: `claimSummary()` concatenates subject+verb+object (`document_view.html:597-602`) | (a) In the entity-grouped panel, render `verb + object` only (template change). (b) Deterministic guard in `svo_cleanup.py` for claims where the LLM disobeyed and re-embedded the name in `verb`/`object`: strip a leading subject-name (or alias) prefix, whole-word, case/accent-folded via `_normalized_match_key` (`_entity_writer.py:288`). |
| 4 Dedup | key-normalize (lowercase, strip `[]()…`, collapse ws, neutralize perspective verbs) → exact + `SequenceMatcher ≥ 0.86` | Three related mechanisms exist: (1) write-time same-doc guard `_same_claim_identity` ratio ≥ 0.9 (`_entity_writer.py:977-1001`); (2) cross-source corroboration merge `_same_structured_claim` ratio ≥ 0.92 (`_entity_writer.py:953-974`) via `_find_cross_source_canonical_claim` (`:1004`); (3) triangulation grouping by `TripleKey` with `slug_verb` + object normalization (`knowledge/triangulation.py:52-64,104-121`). **None neutralizes perspective verbs, so "otorgan…"/"es dado…" survive all three** — that is exactly the residue Daniel sees | View-time dedup in `svo_cleanup.py`: first group by the existing `_normalized_claim_svo_key` (`_entity_writer.py:302`) so counts agree with triangulation; then near-match within a node using Daniel's comparison key (incl. the perspective-verb neutralization list `otorgan\|dan\|es dado\|es\|era\|is\|given`) at **0.86, a named module constant**. Keep the cleanest surface form; absorb the rest into `source_claim_ids`. Never deletes rows. |
| 5 Reify sale | one event node with roles seller/buyer/object/terms/place | §5 — event *nodes* already exist; *roles* do not | An `events_reify` LLM pass writing ordinary role claims (§5). |
| 6 Translate | separate pass over cleaned Spanish | `workflows/tools/translate.py:58` (`translate`) and `text_translate.py:167` (`text_translate`) tools exist | A decorator pass over `CleanedGraph`. **Recommend deferring to a follow-up issue** — nothing in stages 1–5 depends on it, and interleaving risks exactly the diffability loss Daniel warns about. |

## 4. Stage 2 → entity-resolution seam

The engine already has a **complete, persistent, audited** entity-resolution pipeline. Stage 2 must feed it, and the plumbing is already in place:

- **Persistent rules:** `EntityResolutionRule` (`knowledge/knowledge_models.py:771`) with `rule_type ∈ {merge_into, alias, suppress, reclassify}` (`:339`). **Rules are applied at write time on every future import**: `upsert_entity` calls `_apply_entity_resolution_rules` (`_entity_writer.py:1219` → `:87-179`, with cycle guard). This IS the "curation persists and constrains imports" design (#1761/#1763) — nothing new to build.
- **Rule CRUD endpoints:** `POST /api/kg/curation-rules/entity-rules` (+ `/batch`, GET, DELETE) — `api/routes/kg_curation_rules.py:237-282`; claim-rule equivalents `:297-342`.
- **Retroactive merge (for entities that already exist as separate rows):** `POST /api/kg/entity-curation/merge` (`api/routes/kg_entity_curation.py:409`), audited via `EntityMergeAudit` (`knowledge_models.py:809`), undoable (`kg_entity_curation.py:610`), claims repointed by `_repoint_claim_entity_references` (`_entity_writer.py:1017`).
- Fuzzy/auto-merge already exists with tight precision gates (`_fuzzy_match_existing` `_entity_writer.py:436`, lexical floor 0.80 + shared-token gate `:341-378`) — evidence the codebase treats auto-merge as dangerous, which stage 2 should respect.

**Design for stage 2 — two distinct halves:**

1. **Predicate/clause text normalization (display-only, always-on).** Applying `dho→dicho`, `Vezino→Vecino` inside `object_phrase`/`predicate_verb` for the cleaned view changes no identity; it is reversible per-clause via `transforms` + `source_claim_ids`. Lives entirely in `svo_cleanup.py`.
2. **Entity-label merge (persistent, via curation).** `Combeto/Comvento/Combento → Convento` is identity resolution. The abbreviation table ships as a **seed of proposed `EntityResolutionRule` rows** (`rule_type=alias` or `merge_into`, `created_by="svo_cleanup_seed"`, `reason` citing the table entry), created through the existing batch endpoint — *not* a second merge engine. For rows that already exist separately, a one-time pass calls `/api/kg/entity-curation/merge` per confirmed group — audited and undoable. Because rules re-apply at import time (`_entity_writer.py:1219`), the next import of "dho Combeto" lands on the Convento entity automatically — exactly the persistence Daniel's curation design demands.

**Recommendation on display-only vs persistent (the open decision):** persistent, via the curation seam, but **human-gated**: the seed rules land as proposals Daniel confirms once in the curation UI (or a reviewed one-time script), not silently. Rationale: display-only merging would make the Knowledge view disagree with triangulation counts, entity search, and the inspector (three surfaces, one truth); and a wrong table entry under display-only is *still* wrong everywhere the cleaned view is used, without the audit/undo the curation path gives for free. The safe always-on subset is half 1 (text normalization), which never merges identities.

## 5. Stage 5 → events_extract seam (it is partly a rendering bug — but roles are genuinely missing)

**Checked, as instructed. Split verdict:**

- **Event nodes already exist.** `events_extract` (`extractors.py:277-305`) has `entity_type: EntityType.event` (`:281`), so each event becomes a real `KnowledgeEntity` row and renders as its own node (`document_view.html:794+`); RDF already types it `schema:Event` (`knowledge/triples.py:88`). A grounding guard against hallucinated events exists (`extractors.py:2078-2110`).
- **The repetition is written AND re-amplified at render.** Written: SVO extraction runs per entity (`extract_svo_only.py:214-244` loops document × entity), so the one sale sentence yields a separate claim row for Ana María, for Antonio, for the Convento. Re-amplified: each claim's `entity_ids` also includes every *other* entity mentioned in its text (reverse alias scan `_scan_for_mentioned_entities`, `extractors.py:1711`, applied at `:2526/:2591/:2683`), and the template pushes each claim into **every** group it references (`document_view.html:618-622`). So one sale can appear 6–9 times across nodes.
- **What does NOT exist: role structure.** The events item shape is `{event, date, verb, object}` (`extractors.py:285-288`) — no seller/buyer/object/terms/place. And no existing pass equates "Antonio es dado en Venta Real" with "Ana María dan … Antonio" (string similarity can't; `ClaimRelationType` has the vocabulary — `duplicate_of`, `corroborates` — `knowledge_models.py:352` — but nothing populates it for this case).

**Design — build on `events_extract`, persist through the normal write path:**

1. **Cheap wins first (no LLM):** stage-4 dedup already collapses near-identical restatements *within* a node; the template fix stops multi-`entity_ids` claims repeating per group (render the clause on its subject node only — `subject_entity_id` exists, `knowledge_models.py:1621` — with lozenge links from the other participants). This alone removes most of the visual repetition and costs a template + payload change.
2. **`events_reify` (new LLM workflow tool, sibling of `extract_svo_only`):** input = one document's entities + claims (post-stage-4 groups); output = for each event entity already extracted by `events_extract`, role assignments `{event_entity_id, roles: [{role: seller|buyer|object|terms|place, entity_id | text}], date}`. Constraints mirroring the existing grounding guard: every `entity_id` must be in the document's entity scope; unresolvable roles stay as text, never invented entities.
3. **Persistence = ordinary rows, no new mechanism:** each role becomes a `KnowledgeClaim` via `save_claim` (`_entity_writer.py:1691`) with `subject_entity_id = event`, `predicate_verb = "has seller"` (etc. — add these to `CANONICAL_VERBS`, `knowledge/_common.py:360`), `entity_ids = [event, participant]`, and the *original* per-participant sale claims linked to the event's role claims with `KnowledgeClaimLink(relation_type=duplicate_of)` (`knowledge_models.py:1937`, vocabulary at `:352`). The raw claims stay; the links are the provenance that lets the cleaned view show "→ Sale-1 (buyer)" on Antonio while the full clause lives once on the event node.
4. **Rendering:** cleaned view shows the event as one node with its role clauses; participant nodes get `event_refs` chips instead of repeated clauses. Raw claims remain reachable per-clause (§6).

## 6. Provenance model (non-negotiable)

Every cleaned artifact points back to raw rows; every raw row is anchored to source text. Three layers, two of which already exist:

1. **Raw claim → source document** (exists): `source_document_id`, `source_page_label`, `source_excerpt`, `source_char_start/end`, `source_bbox` on `KnowledgeClaim` (`knowledge_models.py:1522-1533,1590`). The template already highlights the excerpt in the transcript on click (`document_view.html:681-699`).
2. **Cleaned clause → raw claims** (new, in the view): `source_claim_ids` (≥1) + `transforms` audit list on every `CleanedClause`/`CleanedNode` (§2). Because stages 1–4 are pure functions computed from the raw rows on every read, the mapping can never drift — there is no stored cleaned copy to go stale. The **conservation invariant** (every raw claim id lands in exactly one clause or in `suppressed` with reason) is enforced by construction and by test.
3. **Reified event → raw claims** (new, persisted): `KnowledgeClaimLink(duplicate_of)` rows from each original per-participant sale claim to the event's role claims (§5.3); role claims carry their own `source_*` anchors copied from the strongest absorbed claim. Links are rows — auditable, queryable, undoable — and the RDF export already reifies claims as `rdf:Statement` with `fichero:sourceDocument` / `sourceExcerpt` (`knowledge/triples.py:186-222`), so the exported cleaned graph keeps provenance too.

UI contract: clicking a cleaned clause opens its raw claims (texts + excerpts + pages) — provenance is one click away, never a mode. Nothing in stages 1–4 writes; nothing anywhere deletes.

**Deviation from the issue's Turtle sketch, flagged:** Daniel spec'd the sale as a *blank node*. The engine already gives events real URIs (`https://fichero.app/entity/{id}`, `triples.py:66-68`) since events are entities. A named node is strictly better for provenance (addressable, linkable from `rdf:Statement` reifications); recommend keeping it. Export can additionally emit the role predicates (`fichero:hasSeller` …) exactly as sketched.

## 7. Swift side

**No Swift changes required for the core work.** The Knowledge pane is a WebView onto engine HTML (`DocumentKGWebPane.swift:20-53`, loads `/view/document/{id}`); node/event structure, cleaned clauses, chips, and the raw click-through all live in `api/templates/document_view.html` (engine-side). The existing native bridge (`entitySelected` notify, `document_view.html:758-772`) already handles entity navigation, and event entities are just entities — the bridge works unchanged.

Swift is touched only if Daniel wants (a) a raw/clean UI control in native chrome — **recommend not** (dead-simple-UX memory: the cleaned view is *the* view, provenance is click-through, no toggle), or (b) curation-rule review UI beyond what the existing curation surfaces (#3757) provide — out of scope here.

## 8. Build plan (worker-executable, in order)

Each step is independently landable and gate-able. No step modifies or deletes raw rows.

1. **`knowledge/svo_cleanup.py` + tests** (pure stdlib; stages 1, 2a, 3, 4).
   - Constants: `_HYPHEN_SPLIT = re.compile(r"(\w)-\s+(\w)")`; `SCRIBAL_ABBREVIATIONS` (word-boundary, case-insensitive; Daniel's table from #3808); `PERSPECTIVE_VERBS`; `DEDUP_RATIO = 0.86`.
   - `clean_svo_view(entities, claims) -> CleanedGraph` per §2, reusing `_normalized_match_key` / `_normalized_claim_svo_key` (`_entity_writer.py:288,302` — consider lifting them into `knowledge/_common.py` beside `slug_verb`, since `svo_cleanup` must not import from `workflows/`).
   - Tests: `fichero-server/tests/unit/knowledge/test_svo_cleanup.py` (§9). **This step alone is Daniel's stages 1–4 and can ship first.**
2. **Read-path wiring** — `api/routes/views.py`: compute `CleanedGraph` in `document_view`/`global_kg_view`, pass `cleaned_json` alongside the existing `claims_json`/`entities_json` (raw stays in the payload — it *is* the provenance click-through data). Template: entity groups render cleaned clauses (verb+object only, label once), clause click opens absorbed raw claims, multi-entity claims render on their subject node with lozenges elsewhere.
3. **Curation seeding (stage 2b)** — a small script or engine command that POSTs the abbreviation-derived `EntityResolutionRule` proposals to `/api/kg/curation-rules/entity-rules/batch` (`kg_curation_rules.py:267`) and, for already-split entities, prepares (prints, does not fire) the `/api/kg/entity-curation/merge` calls for Daniel's confirmation. Per the CLI-only memory, drive via the `fichero` CLI surface, not raw curl.
4. **`events_reify` tool (stage 5)** — new `workflows/tools/events_reify.py` registered like `extract_svo_only` (`extract_svo_only.py:93-137`); role claims via `save_claim`; `duplicate_of` links; role verbs added to `CANONICAL_VERBS` (`knowledge/_common.py`). Grounding constraints per §5.2. Wire the cleaned view to fold role-linked claims into `event_refs`.
5. **Export mode** — `export_rdf` (`api/routes/kg_sparql.py:242`) gains `view=cleaned` (default stays `raw`): build the graph from the cleaned view (events with role predicates + reified provenance statements).
6. **(Deferred / separate issue)** stage 6 translation decorator using the existing `translate`/`text_translate` tools.

Backend note for the gating manager: DB rows are only added by steps 3–4 (rule rows, role claims, links — all existing tables, no schema change anticipated; if any column IS added, migrations discipline applies). Full suite before push (targeted `-k` gates miss guardrail tests — standing memory).

## 9. Test plan

Grounded in Daniel's verified counts (these are the acceptance bar, encoded as fixtures from the #3808 sample document):

1. **Regression counts (stage 4):** Ana María 6→4, Antonio 6→4, **Matheo 5→5** (distinct facts must survive). Fixture = the raw clauses from Daniel's Part 1 sample; needs `clean_svo.py`'s input data from Daniel (see Q6). Assert at `DEDUP_RATIO = 0.86` *and* sweep 0.80–0.92 asserting Matheo never drops below 5 — the threshold's safety margin becomes visible in CI.
2. **Conservation invariant:** for arbitrary claim sets (hypothesis-style or hand fixtures), every input claim id appears exactly once across `source_claim_ids ∪ suppressed`. No silent loss.
3. **Stage 1:** `"Comben- to"→"Combento"`, `"Ne- gros"→"Negros"`, `"siem- pre"→"siempre"`; negative: legitimate hyphenated ranges/compounds (`"1830-31"`, digits excluded by `\w`… note `\w` matches digits — add an explicit negative test and, if needed, letter-only classes) are untouched.
4. **Stage 2 table:** each mapping fires only on whole words (`"dho"→"dicho"` but `"adhoc"` untouched; `"Combeto"→"Convento"` but `"Combate"` untouched); case-insensitivity; idempotence (running twice = once).
5. **Stage 3:** clause starting with node label (or alias, accent-folded) is stripped once; clause *mentioning* the label mid-text is untouched.
6. **Ordering:** dedup-before-dehyphenation misses dupes (Daniel's note) — a test that the pipeline order 1→2→3→4 catches a pair that reversed order misses.
7. **Stage 5:** role claims reference only in-scope entities (guard test mirroring `test_routes_entities_kg_integration.py` patterns); `duplicate_of` links created; cleaned view shows the sale once on the event node and chips on participants; undo of an entity merge leaves role claims consistent.
8. **Route/export tests:** `/view/document/{id}` payload contains both raw and cleaned; `export_rdf?view=cleaned` parses with rdflib, contains exactly one `schema:Event` for the sale with seller/buyer/object/terms/place predicates, and every cleaned statement traces to a `fichero:sourceDocument`.
9. **Consistency with triangulation:** dedup grouping never merges two claims that `TripleKey` (`triangulation.py:52`) considers distinct subjects — counts shown in the cleaned view reconcile with `compute_support_counts` (`triangulation.py:124`).

Per the test-bar memory: edge, undo, validation, and side-effect tests, not happy-path only; manager runs the full suite as gate.

## 10. Risks & mitigations

1. **Dedup merges genuinely distinct facts (data corruption of the *view*, and of reader trust).** Highest risk. Mitigations: display-layer only (raw rows never touched); `source_claim_ids` shows exactly what was absorbed, click-through to raw; Matheo 5→5 regression + threshold sweep in CI; perspective-verb list kept minimal and Spanish/English-explicit; dedup only *within* one node (never across subjects), and never across `_normalized_claim_svo_key`-distinct subjects (§9.9).
2. **Abbreviation table over-merges entities** (a person surnamed "Combeto" vs the Convento). Mitigations: entity merges go through `EntityResolutionRule` proposals + human confirmation, `match_entity_type`-scoped (`knowledge_models.py:777`), audited and undoable (`EntityMergeAudit`, `/audit/{id}/undo`); whole-word matching; the always-on half is text normalization only.
3. **LLM reification hallucinates roles or invents the event's shape.** Mitigations: reuse the grounding-guard pattern (`extractors.py:2078-2110`); roles restricted to in-scope entities; unresolvable roles stay literal text; role claims carry `confidence_origin="llm"` and the normal curation/suppression machinery applies to them like any claim.
4. **View disagrees with other surfaces** (inspector, triangulation, search) if it normalizes differently. Mitigation: reuse `slug_verb` / `_normalized_match_key` / `_normalized_claim_svo_key` rather than parallel normalizers (§8.1).
5. **Performance** — pairwise `SequenceMatcher` is O(n²) per node; fine at per-document scale (dozens of clauses/node) and the global view is capped at 250 rows (`views.py:23`). If a node ever has hundreds of clauses, bucket by exact key first (already the design).
6. **Template complexity** — `document_view.html` is 1393 lines of vanilla JS; the cleaned-view rendering adds more. Mitigation: keep ALL transform logic engine-side (template only renders the `cleaned_json` it is handed); every-frame-perfect gate on the pane after the change.
7. **`\w` in the de-hyphenation regex matches digits** — `"1830- 31"` would join to `"183031"`. Use letter classes (`[^\W\d]`) or add a digit guard; covered by test §9.3. (Daniel's prototype regex has this latent issue too — worth telling him.)
8. **Prompt-side fix temptation:** tightening extraction prompts (subject restatement) helps future imports but does nothing for the existing corpus, and re-extraction costs LLM passes over real data. The display layer fixes both; prompt hardening is a cheap optional follow-up, not a substitute.

## 11. Questions for Daniel (each with a recommendation)

1. **Stage 2 entity merges: display-only or persistent curation rules?** → **Recommend persistent** via `EntityResolutionRule` seeds + one-time audited merges, human-confirmed before firing (§4). Display-only would make the Knowledge view disagree with search/triangulation/inspector and forfeits audit/undo. The text-normalization half (dho→dicho in clause text) ships always-on and display-only.
2. **Cleaned view as *the* view (no raw/clean toggle), with per-clause click-through to raw?** → **Recommend yes** (dead-simple-UX + AI-as-instrument: provenance is an affordance, not a mode). Raw stays fully reachable per clause and via API/export defaults.
3. **Reified sale as a real entity node with a URI in the Turtle export, instead of the blank node in the spec?** → **Recommend named node** (§6) — events already have stable URIs and blank nodes can't be referenced by the provenance reifications. Role predicates emitted exactly as sketched.
4. **Defer stage 6 (translation) to a follow-up issue?** → **Recommend yes**; the `CleanedGraph` shape is translation-ready and `translate`/`text_translate` tools exist, but interleaving now risks the Spanish diffability Daniel himself flagged.
5. **Should stage-4 dedup also persist `KnowledgeClaimLink(duplicate_of)` rows** (making the grouping curatable/overridable) **or stay purely computed?** → **Recommend start purely computed** (zero write risk, always consistent with the raw), add persisted links only if Daniel wants to hand-correct groupings later; stage 5's event links ARE persisted from day one because an LLM produced them.
6. **Please attach `clean_svo.py` + the Part 1/Part 3 sample data to #3808** — the verified counts (Ana María 6→4, Antonio 6→4, Matheo 5→5) only become regression tests if the exact input clauses land in the repo as a fixture. Without them the worker can only approximate the fixture from the issue text.
7. **Is the sale document's raw extraction reproducible on Marshall data currently in the DB?** If the counts came from a one-off export, the fixture should be frozen from that export now (non-destructive read), before any re-extraction changes the rows.

## 12. What I could not determine (honest gaps)

- Which exact surface Daniel copied "Part 1" from (view panel vs an export vs CLI) — all render the same raw rows, so the design is unaffected (§1.4).
- The full contents of Daniel's `clean_svo.py` (not in the repo) — the pipeline is reconstructed from #3808's spec; Q6 covers importing it as reference + fixture.
- Whether `_scan_for_mentioned_entities` links the *event* entity into participant sale claims on Daniel's actual data (it should, when the event name appears verbatim; if it doesn't, stage 5's `duplicate_of` linking is doing that join for the first time). Verifiable only against the live library, which this design pass did not touch.
- jcodemunch index was 4 days stale (2026-07-10); every citation above was verified against the working tree directly with line-level reads, not the index.
