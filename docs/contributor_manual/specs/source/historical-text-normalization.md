# Historical Text Normalization — Design Spec (#TBD)

> **2026-09-19 — read this first.** The shared ideas in this file (what a segment is, its
> slots, the delivery rule) now have one home: `source-model.md` and its slices.
> Where this file and that set differ, that set wins. This file stays as the TEXT LAYER. How language, script and direction are recorded, and the cascade, now live in `languages-scripts-glyphs.md`; what is done with text stays here, and works on a reading of a segment.
>
> Milestone: historical-text-normalization
> Manual: TBD — the contributor manual has no historical-text-normalization section yet.
>
> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** Legacy milestone "Historical Text"
> (#265) accumulated 19 open issues from a 2026-07-06 strategy brief, a Fabel deep review, a
> six-part sequenced implementation plan (issues literally numbered 1/6 to 6/6), and four later
> 2026-09-08 archival-data-model design briefs. This is Pass 1: the spec these issues never got,
> written against the code as it stands today, not the plan as written.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the intent (needs an issue).

## Intent (the design)

Fichero transcribes historical documents — colonial notarial records, multiple scripts, multiple
calendars, spellings that predate any standard orthography. A normalization is what makes that
material searchable and comparable; it is never a rewrite of what the source says.

**Non-negotiable constraints (project rulings, stated once here for the whole program):**

1. **The source text is never rewritten.** Whatever the diplomatic transcription (`page_content`)
   says stays exactly what it says — abbreviations, spelling, scribal marks intact. A
   normalization, a translation, a transliteration, or a fuzzy-search fold is a **separate,
   derived, reversible layer over it**, never an in-place edit to the stored transcription.
2. **Every derived layer carries its own provenance.** Which process produced it, when, from
   what version of the source — the same provenance discipline as any other artifact
   (`Artifact.provider`/`model`/`run_id`, chained via `source_artifact_id`). A derived layer is
   never silently indistinguishable from the source it was derived from.
3. **Real libraries are real research data.** Nothing in this program batch-rewrites stored rows.
   A new derived column or table is populated for NEW writes going forward and offered as an
   opt-in backfill, never an automatic mass mutation of an existing library — the precedent
   (unicode(1–6), #3071–#3076) needed an explicit sign-off before touching existing rows, and
   this program follows the same discipline.
4. **Deterministic first; a model is an instrument, never the author.** Where a rule table, a
   library conversion (`convertdate`/`jdcal`), or a fold function can do the job, it does the
   job — an LLM is reached for only when nothing deterministic can express what is asked for, and
   even then its output is marked and reviewable, never asserted as fact (AI-as-instrument north
   star, `ai-integrity-instrument-not-interlocutor`).

## Grounding: what the six-phase program actually built (verified against HEAD, 2026-09-19)

The 2026-07-06 Fabel review (#3319) sequenced the work into six issues, 1/6 through 6/6. Reading
the code — not the issue text, which was written before most of it landed — the sequence is
**much further along than the ledger's own working guess** ("mostly GAPs" was the expectation;
it is not what HEAD shows). Each phase below is graded on what exists today, phase by phase:

1. **Textnorm foundation (#3320, 1/6) — GAP.** No `textnorm.py` module and no NFC/ftfy
   canonicalization choke point at the storage boundary exists. `ftfy` IS a declared dependency
   (`fichero-server/pyproject.toml`) and IS imported and used — but only locally, inside the date
   extractor (`workflows/tools/date_extract.py`), to clean text before it parses a date
   expression, not as a general `page_content` canonicalization step. `page_content` is still
   written verbatim by every producer (LLM/VLM/OCR tools, transcription review, catalogue) with
   no NFC pass. The dual-field model the 2026-07-06 brief proposed (`diplomatic_text` +
   `normalized_text`) was never built as separate columns; `page_content` remains the single text
   field, and it IS the diplomatic text by default (consistent with constraint 1, but only
   because nothing has touched it — not because a deliberate dual-field design exists yet).
2. **Normalized-content column + fuzzy search (#3321, 2/6) — PARTIAL, split result.** The
   **fuzzy-match half is genuinely built**: `use_fuzzy_match` (`db/__init__.py:5143` →
   `_fuzzy_contains_any_term` at `:5385`) is no longer the no-op the 2026-07 review found — it
   expands the zero-FTS-hit fallback scan with fuzzy token matching, distinct from the exact
   `_contains_any_term` path. The **schema half is not built**: no `normalized_content` column,
   no migration, no stored-folded index text — search still folds every candidate row's raw text
   at query time (`_fold_for_search`, called per-row in the pandas fallback scan and per-query
   for the term), and search is still LanceDB FTS + a pandas full-scan fallback, not a DuckDB FTS
   index. Accent-insensitive search itself already works independently of this phase (see below).
3. **Histdate core (#3322, 3/6) — OK, the strongest result in the program.**
   `fichero-server/src/fichero_server/histdate.py` (384 lines, 34 tests in
   `tests/unit/workflows/test_histdate.py`) is a complete, tested module: Gregorian↔JDN,
   Julian↔JDN (the 1752 Britain cutover), French Republican, Hebrew, Islamic conversions via
   `convertdate`/`jdcal` (both declared dependencies, never hand-rolled math per the plan's own
   instruction); a regnal-year accession table and a Chinese era-name table (`REGNAL_ACCESSIONS`,
   `ERA_NAMES`); explicit-undated detection (`is_explicitly_undated`, the "n.d./s.f." case, a
   fact distinct from "nothing found"); `parse_historical_date`/`extract_date_from_text`.
   `Document` carries `date_original`/`date_jdn`/`date_jdn_end`/`date_meta` (a JSON block:
   calendar system, precision, converted ISO string, source, confidence) — a RANGE, not a single
   collapsed point, honoring "never throw away uncertainty." It is wired in two places: (a)
   `apply_import_date` (`importers/ingest.py`) applies an import-carried date
   (`.iffy.json` sidecar, manifest) automatically on arrival, never overwriting an existing date;
   (b) the `date_extract` workflow tool parses a date out of the document's own text/metadata —
   built and tested, but **not wired into any default workflow** (confirmed: no
   `resources/default_workflows/*.json` references it), so on-document-text date extraction is
   opt-in per workflow, not automatic at every import the way segmentation/embeddings are.
   Search/sort read the columns (`db/__init__.py`'s `date_jdn_from`/`date_jdn_to` filters,
   `dataset_query.py`'s `date_original`/converted-ISO projection). This phase is real,
   substantially delivered, and undertested only in the sense that its extraction step is manual.
4. **Cross-script entity variants (#3323, 4/6) — GAP.** `anyascii` is a declared dependency but
   unused: `llm/multilingual.py`'s `TRANSLITERATION_PATTERNS` is still the same 6-entry hardcoded
   toy table (tokyo/osaka/kyoto/iphone/samsung) the 2026-07-06 review found, never replaced. No
   cross-script candidate-review feed exists. What DOES already work, and is NOT this phase's
   gap: same-script accent/spelling variant collapse is mature —
   `workflows/tools/_entity_writer.py`'s `_fold_accents` (NFKD, drop combining marks) and
   `_normalized_match_key` (fold + case + strip administrative qualifiers) fold "Peña"/"Pena"
   and "Chocó"/"Chocó department" to the same key, with a fuzzy `SequenceMatcher` fallback and an
   audited `entity.merge`/`entity.unmerge` write path. Cross-script pairs (Tokyo/東京,
   Moscow/Москва) have zero token overlap by construction and so never reach that machinery —
   which is the correct precision stance, but nothing surfaces them as review candidates either.
5. **Paleography fonts + diplomatic render (#3324, 5/6) — GAP.** No bundled fonts exist anywhere
   in the app (no `.ttf`/`.otf` under `fichero/fichero`, no pbxproj font membership found); rare
   paleographic ranges (Latin Extended-A/B/D, Combining Diacritical Marks Extended) and CJK
   Extension B–I glyphs depend entirely on the system font cascade. **A related but DIFFERENT
   mojibake bug is already fixed and is not evidence toward this phase**: #4666 (RTF hex escapes
   like `\'f1` leaking into stored KG rows as literal text — "ca\\'f1istin" instead of "cañistin")
   has a real decoder (`loaders/rtf_text.py`'s `decode_rtf_hex_escapes`/`to_plain_text`), tested
   against an actual corpus fixture. That fixes ONE mojibake vector (RTF-escape leakage into
   extraction); it does nothing for font coverage, the cascade, or the charset-pinning audit
   #3324 itself asks for, which remain unbuilt.
6. **Translation (#3325, 6/6) — mostly OK, one clear gap remains.** Contrary to the issue text
   (written when this was theoretical), most of it is built and tested:
   `workflows/tools/translate.py`/`text_translate.py` persist `artifact_type="translation"` with
   `trigger_embedding=True, embedding_scope="translation"` (no longer the invisible-to-search gap
   the review found) — `test_translation_embedding.py` proves embed/delete-vectors round-trips.
   An audited registry action, `artifact.translate` (params: `document_id`, `target_lang`,
   `source_lang`, `provider`; undoable), is registered and reachable from the app (Inspector
   mini-toolbar, `ArtifactsInspectorPane.swift`, with its own UI test
   `testArtifactsTranslateActionLivesInInspectorMiniToolbar`). **Not built:** entity-label
   translation (`entity.translate_label` or equivalent — no match anywhere in source) and the
   full "representations picker" the plan asked for (source image / diplomatic / each
   translation version, in one menu with provenance badges) — today's UI is a translate action
   plus a target-language picker, not a representation switcher across original and derived
   forms.

**Overall correction to the ledger's working guess:** this is not "mostly GAPs with a clear
sequence." Phases 3 and 6 are substantially delivered and tested; phases 1, 4, and 5 are
genuine gaps; phase 2 is split (fuzzy search real, schema/index half not). State this plainly
rather than defaulting to the pessimistic prior.

## Grounding: language detection, per-language tables, and the readable-representation tie-in

- `llm/multilingual.py`'s `detect_language` prefers `cld3` if importable, else a character-range
  heuristic fallback — `cld3` is **still not a declared dependency** (confirmed absent from
  `fichero-server/pyproject.toml`), so production always runs the heuristic. This is unchanged
  from the 2026-07-06 review's own finding; no work has landed on it since.
  `normalize_text()` there is NFKC + lowercase + Turkish-I/ß rules — a DIFFERENT, coarser fold
  than `_fold_for_search`'s NFD-strip-Mn and `_entity_writer.py`'s NFKD `_fold_accents` — three
  folding implementations already coexist for different purposes (search, entity keys, this
  multilingual module); this spec's phase-1/2 work must not add a fourth without first deciding
  which of the three, if any, it replaces.
- The extraction pipeline already carries genuine per-language tables, separate from anything in
  this milestone's own issues: `knowledge/spacy_svo.py`'s `_LANG_DEPS` (`en`, `es`) maps each
  language's own dependency-label scheme (English `dobj`/`nsubjpass`, not universal-dependencies
  `obj`/`nsubj:pass`) so subject/object extraction is correct per language, not English-shaped.
- `knowledge/readable.py` (the readable-representation spec's engine, `kg/kg-readable-
  representation.md`) added two more per-language tables **last night (2026-09-18)**:
  `_LEADING_PREPOSITIONS` (which words mark an object as a place/instrument rather than a plain
  patient, per language) and `_REALISATION` (per-language conjunction/glue words — `"y"`/`"and"`
  for list-joining). Issue #4650 (stage 4 of that spec's own six-stage pipeline: an
  (event-type, role) → verb-phrase lexicon, plus the verb inverse-map for re-centring) will grow
  this same family of tables. **This is the same architecture pattern this spec's own gaps
  should follow — add a language by adding a data table, never new code** — but #4650 and this
  spec's phases are DIFFERENT tables for different jobs (verb lexicalisation vs. text
  normalization/date/entity-variant handling) and should not be merged into one table family.

## Behaviors

### A. Normalization foundation

- `histnorm.no-content-canonicalization` — **[GAP]** (#3320, #3319 — the review that sequenced
  this whole program) `page_content` is stored verbatim
  from every writer (LLM/VLM tools, transcription review, catalogue, import); no NFC/ftfy
  canonicalization choke point exists. `ftfy` is declared and used locally in the date extractor
  only. Building this must apply to NEW writes at the storage boundary, per constraint 3 above —
  never a batch rewrite of existing rows without an explicit, separate sign-off.
- `histnorm.dual-field-model-not-built` — **[GAP]** (#3312, #3321) no `normalized_content`/
  search-index column exists; `page_content` is the only text field, serving as both the
  diplomatic source and (folded at query time, not stored) the search target. Constraint 1 is
  honored today only incidentally (nothing has touched the field), not by a deliberate diplomatic/
  normalized separation.
- `histnorm.fuzzy-search` — **[OK]** (b1c3a8e-equivalent — verified by reading
  `db/__init__.py:5143-5397` directly) `use_fuzzy_match` is implemented: when the exact folded
  full-text scan is requested, the fuzzy path runs `_fuzzy_contains_any_term` over folded text
  instead of the no-op the 2026-07-06 review documented. Pinned:
  `test_fuzzy_match_wiring.py::test_a_typo_misses_without_the_flag_and_hits_with_it` (module-level
  pytest function; the same file's `test_accent_folding_still_works_independently_of_the_flag`
  covers the non-regression case).
- `histnorm.accent-insensitive-search` — **[OK]** (pre-existing, unrelated to this milestone's
  own issues) `_fold_for_search` (NFD, strip combining marks, casefold) already makes
  "Quibdó"/"Quibdo"/"QUIBDÓ" match one another; this predates and is independent of phases 1–2.
  Pinned: `test_search_scoring.py::TestFoldForSearch::test_strips_acute_accent`.

### B. Historical dates

- `histnorm.dates.jdn-core` — **[PARTIAL]** (implemented and tested, 34 tests in
  `test_histdate.py`; #3322, #3314 still open pending close) Gregorian, Julian (with the 1752 Britain
  cutover), French Republican, Hebrew, and Islamic calendar conversion to a Julian Day Number
  range (`jdn`/`jdn_end`), via `convertdate`/`jdcal`, never hand-rolled; regnal-year and
  Chinese-era-name tables; explicit-undated detection distinct from nothing-found.
  `Document.date_original`/`date_jdn`/`date_jdn_end`/`date_meta` store the range and its
  metadata, never collapsing to one guessed point.
- `histnorm.dates.wired-at-import` — **[PARTIAL]** (#3322) import-carried dates (sidecar,
  manifest) are applied automatically and non-destructively (`apply_import_date`, never
  overwrites an existing date); parsing a date out of the document's OWN transcribed text
  (`date_extract` workflow tool) is built and tested but not wired into any default workflow, so
  it runs only when a workflow author adds it — not automatically at every import the way
  segmentation and embeddings are.
- `histnorm.dates.search-and-sort` — **[PARTIAL]** (implemented and tested,
  `test_dataset_query.py`; → #3309, #3322 still open pending close) `date_jdn_from`/
  `date_jdn_to` filters and JDN-based sort exist in `db/__init__.py` and `dataset_query.py`;
  undated documents fall back to `created_at`, matching the documented fallback rule.
- `histnorm.dates.adopt-standards-format` — **[GAP]** (#4364, moved onto this milestone
  2026-09-19) the built date model above is real and tested, but it is entirely hand-rolled
  (custom `HistoricalDate`/`date_meta` JSON), not the `undate`/EDTF standard #4364 asks the
  project to adopt instead of inventing its own. Its own scope note says to evaluate `undate`
  against what #3322 built and prefer the library if it covers the same ground — that
  evaluation has not happened. This is the one concrete, actionable ask left in the
  date-handling thread; everything else it worried about ("uncertainty thrown away") is already
  handled by the JDN-range + `date_meta` model, just not in EDTF's standard form. #4364 was
  correctly waiting on this spec — it named this exact thread and now lives here, not on a
  code-lane's own milestone.

### C. Entity variants across scripts

- `histnorm.entities.same-script-variants` — **[OK]** (pre-existing, `_entity_writer.py`)
  accent-folding, spelling-variant collapse, and administrative-qualifier stripping are mature,
  audited (`entity.merge`/`entity.unmerge` with undo), and persist as rules
  (`EntityResolutionRule`) so a re-import doesn't need re-review. This is NOT this milestone's
  gap — the same-script half of the entity-variant ask is already solved. Pinned:
  `test_entity_writer.py::test_claim_svo_dedup_collapses_normalized_near_duplicate`.
- `histnorm.entities.cross-script-candidates` — **[GAP]** (#3323, #3313) no mechanism surfaces
  cross-script variant PAIRS (Tokyo/東京) as review candidates; `anyascii` is declared but
  unused; `TRANSLITERATION_PATTERNS` is still a 6-entry hardcoded toy table backing
  `/api/multilingual/transliterate`, and `/api/multilingual/entities/search` is still an O(n)
  full-table scan rather than using the existing `kg_entity_embeddings` vectors. The correct
  precision stance — never auto-merge a cross-script pair, only surface it for review — is
  already implicit in how same-script merging works (a lexical-agreement gate); this phase adds
  discovery, not new merge plumbing.

### D. Paleography rendering

- `histnorm.render.no-bundled-fonts` — **[GAP]** (#3324, #3315) no paleographic or CJK-extension fonts
  are bundled; rare glyphs depend on the system cascade and may render as `.notdef` boxes. The
  semantic-fonts rule (`.title`/`.body`, never a raw point size) does not forbid this — a
  diplomatic-view face is a deliberate, scoped exception, the same way a serif/mono case already
  is elsewhere in the app; it is simply not built.
- `histnorm.render.rtf-hex-escape-leak` — **[PARTIAL]** (fixed and tested, distinct bug; → #4666
  still open pending close) RTF hex escapes (`\'f1`) leaking into stored KG statements as literal
  text (reading as "ca\\'f1istin" for "cañistin") are decoded before they reach a row
  (`loaders/rtf_text.py`, `decode_rtf_hex_escapes`/`to_plain_text`), tested against a real
  17th-century-corpus fixture (`test_rtf_escapes_never_reach_rows.py`). Stated precisely so it is
  not mistaken for progress on `histnorm.render.no-bundled-fonts` above — the two are different
  bugs in the same general "unicode/RTF mojibake" class, and only one of them is fixed.
- `histnorm.render.charset-pinning-audit` — **[GAP]** (#3324) no regression test pins that served
  HTML/text carries `charset=utf-8` for paleographic/CJK-extension fixtures end to end; the
  2026-07-06 review's own read of the code judged this LIKELY fine (Starlette's `FileResponse`
  appends charset for `text/*`) but explicitly said it needs a pinning test, which does not
  exist.

### E. Language detection and per-language resources

- `histnorm.language.detection-heuristic-only` — **[GAP, unchanged since 2026-07]** (#3311)
  `cld3` remains an optional import with no declared dependency; production language detection
  is always the character-range heuristic fallback, never the real detector.
  `normalize_text()`'s NFKC fold is a fourth, narrower folding scheme alongside
  `_fold_for_search` (NFD/search), `_fold_accents` (NFKD/entity keys), and whatever this spec's
  phase-1 canonicalization eventually adds — any new normalization work must state which of
  these it replaces or coexists with, not silently add a fifth.
- `histnorm.language.no-silent-english-entity-model` — **[BROKEN]** (#4914) VERIFIED on disk
  2026-09-19 (`fichero_server/knowledge/spacy_ner.py`, in the pipeline loader): when there is
  no spaCy pipeline for a document's language, the code sets the language to English, loads
  the English models, and only logs a warning. So a text in an unsupported language gets
  English entity recognition, and its results feed the automatic draft layer at import with no
  sign to the researcher. This breaks the standing rule to decline, not substitute. Expected:
  entity recognition declines for that language, says plainly "no entity model for this
  language", and the import carries on without it; no English fallback. Not yet checked: what
  language detection returns for a language it cannot identify, and whether that value reaches
  this loader (see `source/models-chains-and-projects.md`, "Language tools are honest").
- `histnorm.language.per-language-tables-exist-elsewhere` — **[OK]** (pre-existing, cited for
  context, not this milestone's own delivery) `spacy_svo.py`'s `_LANG_DEPS` (extraction-time
  dependency-label tables) and `readable.py`'s `_LEADING_PREPOSITIONS`/`_REALISATION` (added
  2026-09-18, growing via the readable-representation spec's own lexicalisation stage) are the
  project's live precedent for "add a language by adding a table" — this spec's own gaps
  (phases 1/2/4) should follow the same pattern when built, using their own tables, not these
  ones. Pinned: `TestEnglishRecipientKeepsItsPreposition` (`test_spacy_svo_validator.py`).

### F. Translation

- `histnorm.translate.searchable` — **[PARTIAL]** (implemented and tested,
  `test_translation_embedding.py`; #3325 still open pending close) translation artifacts embed
  with `embedding_scope="translation"` and are found by search; deleting the artifact removes its
  vectors (no stale entries).
- `histnorm.translate.audited-action` — **[PARTIAL]** (implemented and tested,
  `test_translation_embedding.py`'s `TestArtifactTranslateAction`,
  `DocumentInspectorTests.testArtifactsTranslateActionLivesInInspectorMiniToolbar`; #3325 still
  open pending close) `artifact.translate` is a registered, undoable, UI-reachable action — not
  workflow-only, closing the "can't translate without authoring a workflow" gap the review named.
- `histnorm.translate.entity-labels` — **[GAP]** (#3325, #3316) no entity-label translation/alias
  mechanism exists; `KnowledgeEntity.aliases` could carry a language-tagged translated name (no
  schema change needed) but nothing writes one.
- `histnorm.translate.representations-picker` — **[GAP]** (#3325) no single menu switches
  between a document's source image, its diplomatic transcription, and its translation
  versions with provenance shown per representation; today's UI is a translate action plus a
  target-language picker, not a representation switcher. The plan's own note that a prior
  attempt at this (`RepresentationStore`) was built and then removed as dead code (0 call sites,
  since closed) is the standing lesson: wire it into an existing surface (the Inspector's
  Artifacts pane, already the translate action's home) rather than resurrecting that store.

### G. Transliteration/romanization (a standalone ask, not sequenced into the six)

- `histnorm.transliteration.romanization` — **[GAP]** (#3326) no derived romanized/
  transliterated form exists alongside the diplomatic text; `anyascii` (declared, unused) is the
  natural candidate once phase 4's cross-script work above (#3323) picks it up — the two issues
  should very likely become one delivery, not two, since both need the same library for related
  ends (cross-script matching vs. display), but that decision belongs to Pass 2 triage, not
  asserted here.

### H. Future direction, explicitly deferred (not this milestone's gap to close)

- `histnorm.future.cascading-attribute-resolution` — **NOT NOW, ratified future direction.**
  Language and other per-text attributes are intended to eventually CASCADE
  (app → library → folder → page → region → line → word → character), with an override at any
  level and the finest grain able to differ from its ancestors — e.g. a page set to Spanish with
  one interlined Latin line. This is a deliberately deferred design (creative-director ruling:
  get the "loove" character-coverage/tiering fit right first — see `histnorm.language.*` above
  and #4637's coverage-tier design) — recorded here as the destination this milestone's
  per-language-table work is walking toward, not a behavior to build now.

## Design-first epics (2026-09-08 briefs) — sequenced after this spec, not folded into it

Four issues (#4636, #4637, #4638, #4639) plus #4642 are **design-first** creative-director briefs
for a much larger "archival data model" (segments/anchors, provenance+versioning, language/
script/coverage, transcription editions+export formats) — each names its own spec deliverable
under `docs/contributor/specs/...` (a path that predates this manual's `docs/contributor_manual/`
reorganization) and explicitly says not to start before its own Status flips to APPROVED. They
are **the correct future home for several of this spec's own GAPs** — `histnorm.language.*`
belongs under #4637's coverage-tier model once that spec exists; provenance-for-derived-layers
(constraint 2 above) belongs under #4636's model once that spec exists — but writing those specs
is its own body of work, not part of folding milestone #265's issues. They stay open, uncited by
a specific behavior above beyond this cross-reference, pending their own design passes.

## Waiting-issue notes for other folds

- **#4364** (adopt undate/EDTF) — **belonged here, now moved** (2026-09-19, onto #317), see
  `histnorm.dates.adopt-standards-format` above. Was correctly waiting on this spec; no longer
  waiting.
- **#1755** (georeference a map image onto a real/3D basemap) — **does NOT belong here.**
  Checked its full body: it is about treating a scanned map IMAGE as a georeferenced overlay on a
  basemap/globe (2D warp + 3D RealityKit), filed under milestone "UX - Representations" (#183).
  It shares no ground with historical-TEXT normalization beyond both being "historical." Flagging
  this precisely rather than forcing a fit: whoever asked for it to wait on this spec should be
  told it does not belong, so it can go back to its own milestone's queue.

## Open questions (for the creative director / maintainer, not decided here)

1. Which of the four existing folding schemes (`_fold_for_search` NFD, `_entity_writer._fold_
   accents` NFKD, `multilingual.normalize_text` NFKC, and this spec's still-unbuilt phase-1
   canonicalization) should phase 1 actually add, replace, or delegate to? Building a fifth
   without deciding this multiplies the class #3320 itself warned against.
2. Should #3323 (cross-script entity variants) and #3326 (transliteration/romanization) merge
   into one delivery, since both need `anyascii` for related ends? (Raised as `histnorm.
   transliteration.romanization` above.)
3. Backfilling `date_original`/`date_jdn` onto EXISTING documents via the (unwired) `date_extract`
   tool — an explicit, opt-in run the maintainer chooses, never automatic — needs the same kind
   of sign-off #3077 (unicode path backfill) required before touching real library data
   (constraint 3).
4. `undate`/EDTF evaluation (#4364): if it covers what `histdate.py` already does, does the
   hand-rolled module get replaced outright (iterate-never-replace tension: this would be a
   genuine case for replacing internals while keeping the tested contract), or does EDTF become
   an export/display format layered on the existing JDN-range storage?

## Fold record for the 19 issues (Pass 2 — executed 2026-09-19)

All by NUMBER. 14 issues moved onto #317 (`gh api -X PATCH .../milestone=317`); 5 stayed
untouched (the design-first epics). No issue was closed by this pass — every "already built"
finding was posted as GitHub-comment evidence with "Left OPEN; not closing myself," per the
standing rule that a lane states evidence and never recommends closure or calls an open issue
superseded; that judgement is the maintainer's.

**Moved onto #317 (historical-text-normalization), each now backing a named behavior above:**
- #3311 (strategy brief) — background/intent source, cited throughout; folds as context, not a
  behavior of its own.
- #3312 → `histnorm.dual-field-model-not-built`
- #3313 → `histnorm.entities.same-script-variants` (OK half) + `histnorm.entities.cross-script-
  candidates` (GAP half) — one issue, two behaviors, since the review found it already
  half-solved. **Verify-close comment posted**, evidence for the same-script half; stays OPEN.
- #3314 → cites `histnorm.dates.jdn-core` and `histnorm.dates.adopt-standards-format`.
  **Verify-close comment posted** — its own ask (JDN plus calendar metadata) is the part already
  built; stays OPEN, the maintainer decides whether it closes now or waits on #4364.
- #3315 → `histnorm.render.no-bundled-fonts` + `histnorm.render.charset-pinning-audit`
- #3316 → `histnorm.translate.entity-labels` + `histnorm.translate.representations-picker`.
  **Verify-close comment posted** — its own feasibility question is answered: yes, and mostly
  built; stays OPEN, the two named gaps are what remains.
- #3319 (the deep review that sequenced this program) — the record of the grounding, stays
  OPEN with no comment; its six children carry the actual work above.
- #3320 → `histnorm.no-content-canonicalization`
- #3321 → `histnorm.dual-field-model-not-built` (schema half) + `histnorm.fuzzy-search` (OK
  half). **Scope-narrowing comment posted** (not a verify-close): the fuzzy half is done and
  named by test; the remaining scope is the schema/index half only.
- #3322 → `histnorm.dates.jdn-core`, `histnorm.dates.wired-at-import`,
  `histnorm.dates.search-and-sort`. **Verify-close comment posted**, naming each test suite
  (`TestGoldenConversions`, `TestRangeSemantics`, `TestHonestAbsence`,
  `TestExtractionFromRunningText`, `TestColumnsPersist`, `TestUserDatesSurviveReExtraction`) by
  name rather than citing the 34-test count; stays OPEN.
- #3323 → `histnorm.entities.cross-script-candidates`
- #3324 → `histnorm.render.no-bundled-fonts`, `histnorm.render.charset-pinning-audit` (with
  `histnorm.render.rtf-hex-escape-leak` cited as a related-but-different already-fixed bug, not
  progress toward this issue)
- #3325 → `histnorm.translate.searchable` + `histnorm.translate.audited-action`.
  **Verify-close comment posted**, evidence for both, plus `histnorm.translate.entity-labels` +
  `histnorm.translate.representations-picker` (named as the two gaps that remain); stays OPEN.
- #3326 → `histnorm.transliteration.romanization`

**Left untouched, on their own milestones:**
- #1755 was never on milestone #265 in the first place (see Waiting-issue notes above) — no
  action needed; it stays on "UX - Representations" (#183).
- #4636, #4637, #4638, #4639, #4642 — each has its own Status-gated design-first path; folding
  them into #317 would blur "approved, testable spec" with "not-yet-approved design brief."
  Cross-referenced from this spec (above); milestone left as-is.

**Net effect:** #265 dropped from 19 open to 5 (verified via `gh api .../milestones/265`'s
`open_issues`) — exactly the five design-first epics; #317 (historical-text-normalization) now
holds 14 open issues, all cited by a behavior above. No milestone reached zero this pass.
