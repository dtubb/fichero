# KG Cleanup Program — dedupe tooling, survey, and what a real run would change

*2026-09-02 overnight lane (Claude). Directed by Daniel. Proven end-to-end on a
scratch copy of the Marshall library; the real library is untouched.*

## What already existed (search-before-build inventory)

The merge machinery was essentially complete — what was missing was a **batch
planner** with a dry-run/apply contract and CLI verbs:

| Piece | Where | Status before tonight |
|---|---|---|
| Entity merge (audited, undoable) | `entity.merge` action → `merge_entities_impl`, `POST /api/kg/entity-curation/merge` | done — aliases fold, claims repoint, `EntityMergeAudit`, undo |
| Entity split / undo / audit list | same module | done |
| Claim merge (audited, undoable) | `claim.merge` action → `merge_claims_impl`, `POST /api/kg/claims/merge` | done — provenance fold, link repoint, **corroboration_count recomputed from union of sources**, snapshots for unmerge |
| Merge candidates (structural) | `GET /api/kg/entity-curation/candidates` — graph-context Jaccard (#988) | done, but pair-at-a-time review surface, no batch apply |
| Display-time SVO cleanup | `knowledge/svo_cleanup.py` (#3808) | done, non-destructive only |
| Trivial-claim pruning | `claim.prune_trivial` + suppression rules | done |
| Fields | `merged_into_id`, `aliases`, `curation_state`, `corroboration_count` on both models | done |

## What was built tonight (#4508)

One new pure module + two endpoints + two CLI verbs. Apply never re-derives a
merge — it drives the existing audited actions.

- **`fichero_server/knowledge/dedupe.py`** — pure planner.
  - `normalize_name`: NFKD accent-strip, casefold, punctuation→space, collapse
    whitespace. Collapses every noise form the survey actually found.
  - `plan_entity_dedupe(entities, include_reviewed=False, min_similarity=None)`
    — union-find over (a) identical normalized canonical names, (b) alias
    collisions (alias↔alias and alias↔canonical), (c) opt-in similarity tier
    (`SequenceMatcher` on normalized names). Survivor rank: curated state >
    corroboration_count > cleaner name (fewer punctuation/linebreak chars) >
    alias count > oldest.
  - `plan_claim_dedupe(claims, include_reviewed=False, near_duplicate_threshold=None)`
    — exact tier groups identical `(subject, normalized verb+object)` using the
    same `_comparison_key` the display path trusts; text fallback for non-SVO
    claims; subjectless claims are never touched. Near tier (opt-in) requires
    the identical token set *and* the ratio, mirroring `clean_svo_claims`.
- **`POST /api/kg/entity-curation/dedupe`** and **`POST /api/kg/claims/dedupe`**
  — request `{apply, include_reviewed, min_similarity|near_duplicate_threshold}`;
  response carries the full plan (survivor, absorbed, basis, similarity,
  audit_id-once-applied) plus counts. `apply: true` loops
  `registry.invoke("entity.merge"| "claim.merge", …)` — one ActionAudit + one
  merge audit per group, observable-layer emit, undo, real actor. Absorbed
  canonical spellings are passed as `merged_aliases` so no name form is lost to
  search (`Quibdó` stays findable on the `Quibdo` survivor).
- **CLI**: `fichero kg dedupe-entities [--apply] [--include-reviewed]
  [--min-similarity X]` and `fichero kg dedupe-claims [--apply]
  [--include-reviewed] [--near-duplicate-threshold X]`. Dry-run is the default;
  `--apply` is the only way to write.
- **OpenAPI** regenerated across all four committed copies + generated CLI
  surface (`sync_openapi_schema.sh`).
- **Tests**: 22 planner/route tests (`tests/unit/kg/test_kg_dedupe.py`) + 3 CLI
  wiring tests (`fichero-cli/tests/test_kg_dedupe_commands.py`). Dry-run/apply
  parity is asserted (same groups, then re-plan is empty); apply is asserted to
  write both audit kinds and repoint claims; claim apply is asserted to raise
  corroboration_count to the source-union size.

### Quality gates (structural where possible)

1. **Cross-type merges are impossible** — `entity_type` is part of every
   grouping key, similarity tier included. The survey validated the rule: the
   scratch library has `Davis` as both person and organization, and `Chi` as
   organization and location; neither is ever grouped.
2. **Unreviewed-only by default** — rejected and already-merged rows never
   participate; verified/curated rows are absorbed only under
   `include_reviewed`, and a curated row always wins survivorship.
3. **Similarity is opt-in, and dry-run-first is the intended workflow** — the
   exact tier on real data was 100% true duplicates, while the 0.90-similarity
   tier contained landmines (`Dredge No. 3` vs `Dredge No. 1`, `H.C. Foster`
   vs `N.C. Foster`). Similar names are a review queue, not a merge.
4. **Every merge is provenanced** — actor-attributed ActionAudit +
   EntityMergeAudit/ClaimMergeAudit rows, each individually undoable (the
   scratch run below exercised undo across all six merges and got the original
   576 back).

## Survey: scratch Marshall copy (before)

576 entities (228 location, 228 person, 96 organization, 23 concept, 1 event),
all `unreviewed`, none merged. **0 claims** — SVO extraction has not been run
on this library, so the claim-side numbers below come from the seeded test
suite, not Marshall data.

- **Exact duplicates (same type, normalized name): 6 groups / 12 entities
  (2.1%)** — `Quibdó`/`Quibdo`, `Jorge\nCardenas`/`Jorge Cardenas`,
  `Laura C. Hall`/`Laura C Hall`, `B'na`/`B/na`, `SS "Turrialba"`/`SS
  Turrialba`, `"La Piedra"`/`La Piedra`.
- **Near-duplicates at ≥0.90 similarity: 15 pairs**, mixed quality — real
  (`Albert/Alberto Holguin`, `Rodolfo/Rudolfo Arriaga`, `Laura Hall`/`Laura C.
  Hall`) alongside must-not-merge (`Dredge No. 1/3`, `H.C./N.C. Foster`,
  `Marin`/`Marvin`). At 0.93 the tier still proposes 7 (mostly real, but
  `Muriello`/`Murillo` and `Crawton`/`Crawston` would need a human eye).
- **Cross-type name collisions: 2** (`Davis`, `Chi`) — correctly excluded.
- **NER junk (short tokens, weekday/heading fragments): ~17 rows** —
  `Legal Holiday - Office`, `Bank - Ordered`, `Tambo - Arr.`, `za`, `NY`,
  `Mo`, `Sa`, `THE STANDARD DIARY COMPANY\n\`\``… These are not duplicates;
  they need *rejection*, which already exists (`batch-curation` →
  `curation_state=rejected`, or entity-resolution suppress rules). A junk
  classifier is follow-up work, sketched below.

## Run on the scratch copy (after)

Full cycle executed against the scratch copy through the real app routes:

| Step | Result |
|---|---|
| Dry-run (defaults) | 576 scanned → 6 groups / 6 absorbed proposed; **nothing written** (0 audits, 0 tombstones) |
| Apply | 6 merges via `entity.merge`; 576 → **570 live entities**, 6 tombstones, 6 EntityMergeAudit + 6 ActionAudit rows |
| Re-plan | **0 groups** (idempotent) |
| Undo ×6 (audited undo route) | back to 576 live — reversibility proven on real data |
| Re-apply (with alias preservation) | 570 live again; each survivor now carries the absorbed spelling as an alias (`Quibdo` ← alias `Quibdó`, `Jorge Cardenas` ← alias `Jorge\nCardenas`, …) and the clean spelling won survivorship |
| Claims dedupe dry-run | 0 claims scanned, 0 groups (no SVO extraction on this library) |

Claim-side behaviour (merge, corroboration_count 1→2 across two source
documents, audit, re-plan empty) is proven by the route tests on seeded data.

## What a run on the REAL library would change (Daniel decides)

`fichero kg dedupe-entities` (dry-run) against the real Marshall library, then
reviewing the printed plan before `--apply`, would:

- absorb ~6 entities (the same six groups, assuming the library matches the
  Sep-2 copy) — each undoable individually, absorbed spellings kept as aliases;
- change **no** claims (there are none), **no** documents, **no** curated work.

Explicitly *not* recommended for auto-apply on the real library:
- `--min-similarity` merges — run `--min-similarity 0.93` as a dry-run and
  review; `Muriello/Murillo` and friends need a human verdict;
- the ~17 junk entities — they want `rejected`, not merging. Cleanest path: a
  short curation session in the app, or a follow-up `kg reject-junk` planner
  (heuristics: ≤2 chars, weekday/month abbreviations, `X - Y` ledger headings,
  digit-heavy strings) with the same dry-run/apply contract.
- claims cleanup — moot until SVO extraction runs on this library; when it
  does, `kg dedupe-claims` is ready and corroboration-raising.

## Follow-ups worth filing

1. Junk-entity planner (`reject`, not merge) with the same dry-run/apply shape.
2. Surface the dedupe plan in the app's curation UI (the endpoint already
   returns everything a review list needs; Swift regen already carries types).
3. `entitymatchcandidates` table exists but is empty/unused — either wire the
   candidates endpoint to persist into it or retire it.
4. Engine port is hard-coded to 8765 (`__main__.py` uvicorn kwargs);
   `FICHERO_TCP_PORT` only affects the TCP-also sharing listener. A spare-port
   engine for side-by-side verification is currently impossible — tonight's
   live proof ran in-process (TestClient against the real routes + the scratch
   DuckDB) instead.
