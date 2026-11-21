# Knowledge Graph — confidence, provenance, dates and places as qualifiers, authorities, search — Design Spec (#5032, #4751, #5008, #5123)

> Milestone: kg-confidence-and-provenance
> Manual: TBD — a section, "How sure is this?", telling a researcher what the band beside a name,
> a statement, a proposed merge and an authority link means, where the figure comes from (the
> project's own check set), what a person's decision does to it, how the threshold control hides
> and shows the uncertain, where a statement's date and place come from, and how to search names
> and statements.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-11-20), written from the review of
> the code and a measured run of the free tier on ten read pages (figures in "Measured" below).
> This spec owns ONE question the other knowledge specs touch and none answers: how sure the
> graph is of each thing in it, who or what said so, and what follows from that. It cites and
> never restates `kg-entities-and-statements.md` (names, statements, resolution, the check set),
> `kg-tables.md` (CRUD, rules that survive re-import), `kg-enrichment.md` and
> `project-gazetteer-and-names.md` (authorities), `kg-readable-representation.md` (hedge words),
> `../explore/networks.md`, `../explore/time.md`, `../explore/place.md` (the controls).
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built · **[BROKEN]** code contradicts the line.
> `→ #n` marks an issue filed for this spec (milestone kg-confidence-and-provenance, listed at the end).

## Intent (the design)

Everything in the graph is somebody's assertion: a tagger's, a model's, a rule's, an authority
file's, or a person's. A researcher has to be able to see, for any name, mention, merge,
statement, date, place and authority link: **who or what made it** (which model and prompt
version, which rule, which person), **from where** (which page, which line, which stretch),
**how sure** (a figure that means something, because it was measured on this project's own
corrected pages), and **what a person has decided** (which outranks every figure). The figure is
never decoration: it orders the review queue, it is the control on every graph, timeline and map,
and it is the one thing that may let a machine act without asking, inside limits a person set.

Three questions are kept apart and never folded into one number:

1. **Is this what the page says?** (extraction confidence: the name is a name of that type, the
   statement's subject, verb and object are the page's).
2. **Is the page read right?** (reading confidence: the line's reading, from the reader steps).
3. **Is what the page says so?** (evidential weight: how many independent sources say it, of
   what authority, and whether another contradicts it).

A person's decision is a fourth thing and is not a number at all.

Lives in: `models/knowledge.py` (`KnowledgeClaim.confidence`, `confidence_source`,
`evidential_confidence`, `EvidentialDateRange`, `EvidentialPlace`, `AttributionStep`,
`SourceSupport`, `EntityMatchCandidate.score`), `workflows/tools/_entity_writer.py`
(`save_claim`, `derive_evidential_dimensions`, `_merge_corroborating_claim`, `upsert_entity`),
`workflows/tools/extractors.py` (`_write_kg_rows`), `importers/nlp_draft.py`,
`knowledge/triangulation.py`, `knowledge/probabilistic_scorer.py`, `knowledge/authorities.py`,
`api/routes/kg/entity_curation.py`, `api/routes/kg/graph.py`, `api/routes/kg/search.py`; the
app's `ConfidenceBand`, the Claims and Entities panes, and the graph, timeline and map views.

## Prior art (what we adopt)

- **Apple, Photos People** (Apple Machine Learning Research, "Recognizing People in Photos
  Through Private On-Device Machine Learning", 2021): the first clustering pass is deliberately
  conservative because a join is permanent, giving high precision and many small clusters; a
  second, looser pass raises recall; an observation may be left "unknown" instead of forced into
  a match; uncertain ones are offered one at a time as a yes or no ("Review More Photos").
  Adopted: joins are conservative and reversible, "no match" is an answer, the uncertain are a
  yes-or-no queue. Apple publishes no threshold values and does not describe how a "no" is used.
- **Apple, Saga** (the knowledge platform paper, SIGMOD 2022): every fact carries provenance (an
  array of its sources) and a trust score per source; the matcher emits a calibrated
  probability, kept as metadata beside the fact; suspect facts are quarantined for human
  curation and curations come back in as a source. Adopted: source list and per-source figure on
  every statement; the probability is metadata, never the fact; a person's curation is itself a
  source that wins.
- **Apple's semantic index and Core Spotlight semantic search**: nothing public says what is
  stored per item or exposes a confidence to a developer (checked 2026-11-20; the developer
  pages name ranked results only). Nothing to adopt beyond "ranked, on the device".
- **Record linkage** (Fellegi and Sunter 1969; Splink): a match weight and TWO thresholds: above
  the upper, a match; below the lower, not; between, clerical review. Adopted as the shape of
  every threshold here.
- **Calibration** (Platt scaling, isotonic regression, temperature scaling; expected calibration
  error; Guo et al. 2017): a score becomes a probability only by being fitted to labelled
  outcomes. A language model's own stated confidence is poorly calibrated (Xiong et al. 2023)
  and is never stored as a confidence.
- **Fusing extractors** (Knowledge Vault, 2014; noisy-OR; Dawid and Skene 1979): agreement of
  independent extractors raises the probability a fact was extracted right; two runs of one
  model are not independent.
- **Wikidata's statement model**: a statement has a value, **qualifiers** (point in time,
  location, start, end), **references** and a **rank** (preferred, normal, deprecated). Adopted:
  a statement's date and place are its qualifiers; a person's decision is its rank. Wikidata's
  time value (value, precision, calendar model; earliest and latest date as qualifiers) and
  **EDTF** (ISO 8601-2: `?` uncertain, `~` approximate, `/` interval, `..` open end, `X`
  unspecified digit) are the date forms.
- **W3C PROV-O** (Entity, Activity, Agent; `wasGeneratedBy`, `wasAttributedTo`,
  `wasDerivedFrom`) for the export of who made what from what; **RDF 1.2 triple terms**
  (`rdf:reifies`) or named graphs for saying "this source asserts this" without asserting it;
  **W3C Web Annotation** selectors for the stretch of text and the region of the image; the
  **factoid model** (already adopted in `kg-entities-and-statements.md`).
- **Reconciliation** (the W3C Reconciliation Service API that OpenRefine speaks): a candidate
  list, each with a score and a `match` flag, and a person confirming. Adopted as the shape of
  an authority proposal.
- Deliberately not adopted: a single blended "quality" number; a default of one half meaning
  "nobody measured"; a machine promoting its own output to confirmed.

## Measured (2026-11-20, the free tier, ten read pages, a scratch library)

Ten pages of a Spanish notarial notebook already read (23,055 characters of cleaned reading),
`importers.nlp_draft.run_nlp_draft` (spaCy `es_core_news_sm` names and parser statements) on a
light Mac (M1, 16 GB), nothing else measured (no local model is installed on that Mac, and no
paid model was used).

| What | Figure |
|---|---|
| Time | 13.4 s for the first page (the pipeline loads), then 0.72 s a page |
| Names written | 123 (78 person, 35 location, 10 organisation): 12.3 a page |
| Names right, by eye on a 30-name sample per type | about 2 in 3 people, about 1 in 2 places, about 1 in 4 organisations (verbs, role words, cut surnames and month names among the wrong) |
| Statements written | 133, of which 121 are a bare mention with no verb and no object, 10 are an English "is a person" filler on a Spanish page, 2 are real parser statements |
| Confidence on the 133 | 121 at 0.5 marked `llm`, 10 at 0.5 marked `heuristic`, 2 at 0.7 marked `llm`: no language model ran |
| Names carrying any confidence | 0 of 123 (the record has no such field) |
| Statements with a date | 0 of 133; with a place value, 38 (each a place name's own mention) |
| Merge proposals queued at write | 9 for 123 names, all `similar_name`, scores 0.80 to 0.89 |
| Names that are dates | 2 month names stored as a person and an organisation |
| Neighbourhood graph | 9 of 39 edges end in a literal leaf drawn as a node |

## Words

- **Maker**: what made a row: a run (provider, model, prompt version, run id), a rule (its
  name), an import (the authority and the record), or a person (the account).
- **Score**: what a maker returned (a tagger's span score, a cosine, a string ratio). Not a
  probability, and never shown as one.
- **Confidence**: the probability the row is right about question 1, with its **source**: one of
  `measured` (fitted on the check set), `rule` (a rule whose precision was measured), `prior`
  (the maker's measured precision, no score of its own) or absent. Absent means not measured.
- **Basis**: how a date, a place or an attribution was established: `asserted` (the statement's
  own words), `source_anchored` (bounded from the document's or folder's description) or
  `inferred` (worked out by a model, a geocoder or a rule). Already `EvidenceBasis`.
- **Support**: the distinct sources that say the same thing, each with its own anchor.
- **Decision**: a person's word on a row (verified, curated, rejected, merged, linked, "not the
  same as"), with who and when. It outranks every confidence.
- **Qualifier**: a statement's date or place: a value ON the statement, never a node or an edge.

## Behaviors

### A. Everything says who made it, from where

- `kg.prov.every-row-has-a-maker` — **[PARTIAL]** (#4869, #4868) every name, mention, statement,
  date value, place value, merge proposal and authority link names its maker in its attribution:
  provider, model, prompt version and run for a run; the rule's name for a rule; the account for
  a person; the authority and record for an import. Built: `KnowledgeEntity.add_attribution`
  (one `extractor` step per run, the pages it found the name on), the claim's `provider`,
  `model`, `provenance_kind`, `EntityMatchCandidate.method` and `reason`, the typed link's
  `provenance_kind` and `created_by`. Not built: the prompt version (#6278); the tagger's
  draft marked as a draft on the name's entry (`kg.names.says-who-made-it`).
- `kg.prov.every-row-rests-on-a-stretch` — **[PARTIAL]** (#5488) a mention and a statement rest
  on a stretch of a line of a page (and so on a region of the image), as a Web Annotation style
  selector. Built: character offsets on all 133 measured statements
  (`source_char_start`, `source_char_end`). Not built: the segment anchor (`source_anchor` was
  empty on all 133; `kg.one.mention-is-the-link` in `kg-entities-and-statements.md`).
- `kg.prov.exported-as-prov` — **[GAP]** (#4755, #4641) the RDF and JSON-LD exports say who made
  each statement and from what in PROV-O terms (the run an Activity, the model or person an
  Agent, the page the Entity it was derived from), and a statement the project has not confirmed
  is exported as reified (an RDF 1.2 triple term or a named graph per source), never as a bare
  asserted triple.

### B. What carries a confidence, and what the figure means

- `kg.confidence.statement` — **[PARTIAL]** (#4751) a statement carries a confidence for
  question 1 and its source. Built: `KnowledgeClaim.confidence` and `confidence_source`. Not
  built: a figure that was measured: today it is a constant chosen in code (0.7 when a model
  returned both verb and object, 0.5 otherwise, 0.3 when the model called it rejected:
  `extractors._write_kg_rows`).
- `kg.confidence.source-is-true` — **[BROKEN]** (#4869, → #6761) `confidence_source` says what
  actually produced the figure. Today the writer stamps `llm` on rows no language model made:
  `_write_kg_rows` passes `confidence_origin="heuristic" if svo_synthesised else "llm"` whatever
  the provider, so 123 of the tagger's 133 measured rows read as a language model's. The closed
  vocabulary is `measured`, `rule`, `prior` and absent; a person's decision is a state, not a
  source.
- `kg.confidence.no-made-up-figure` — **[BROKEN]** (#4751, → #6761) nothing is stored as a confidence
  that nobody measured. Today 0.5 is the default on `KnowledgeClaim.confidence`,
  `EvidentialDateRange.confidence`, `EvidentialPlace.confidence`,
  `AttributionStep.confidence` and `SourceSupport.support_confidence`, and 0.55 and 0.5 are
  written for a date or place bounded from the document's description
  (`derive_evidential_dimensions`); a reader cannot tell "half sure" from "never measured". An
  unmeasured row has NO confidence and shows no band (the app's `ConfidenceBand.recorded`
  already draws nothing for none). Stored rows are not rewritten: a row whose source is not one
  of the closed vocabulary reads as unmeasured.
- `kg.confidence.name-and-mention` — **[GAP]** (→ #6762, #6385) a name's mention carries the
  tagger's or model's score and the confidence fitted from it; the name carries none of its own
  (a name is as sure as its best mention and its decision). Today `KnowledgeEntity` has no
  confidence field, `upsert_entity` takes none, and the score the taggers return
  (`workflows/ner/providers.py`: a constant 0.99 for spaCy, the model's score for a
  token-classification model) is dropped at the door.
- `kg.confidence.merge-proposal` — **[PARTIAL]** (#1675, #6280) a proposed merge carries its
  method, its evidence in words, its score, and the confidence that the two are one. Built:
  `EntityMatchCandidate.method`, `reason`, `score`. Not built: one meaning for `score` (it holds
  a cosine for one method and a string ratio for another, and its description offers "calibrated
  probability or cosine"); the confidence; the same fields on the merge's audit row (#1675).
  `knowledge/probabilistic_scorer.py` (a 0.4, 0.4, 0.2 blend with 0.95 and 0.7 thresholds) is
  called by nothing and is not a calibrated probability: it is retired or replaced by the fitted
  matcher below, never wired as it stands.
- `kg.confidence.authority-link` — **[PARTIAL]** (#5123) a proposed link to an authority record
  carries how it was found and a confidence; a chosen link keeps the confidence it had when
  chosen. Built: `found_by` and a figure on each candidate
  (`entity_curation._external_authority_candidates`), `TypedLink.certainty`. Not built: the
  figure is a rank (1.0 for the same name, 0.5 for an alias: `MATCH_CONFIDENCE`), and
  `link_authority_impl` stores no certainty on the link it writes.
- `kg.confidence.date-and-place` — **[PARTIAL]** (#5032) each date value and place value of a
  statement carries its basis and a confidence. Built: `EvidentialDateRange.basis`,
  `EvidentialPlace.basis`, both with `confidence` and the stretch it came from. Not built: a
  measured figure (section B's rule applies).

### C. Where the figure comes from: the project's check set

- `kg.confidence.calibrated-on-the-check-set` — **[GAP]** (#5545, #6385, #6386, → #6763) the
  check set of `kg.names.measured` (about ten corrected pages) plus every decision a person has
  made since (section E) is the labelled set. For each maker and kind (a tagger or a model and
  prompt version, per name type; statements; each merge method; each authority) the engine
  keeps: the measured precision (the `prior`), and, where the maker returns a score and there
  are at least 50 labelled rows, a monotone fit from score to probability (isotonic, else Platt)
  with its expected calibration error and a ten-bin reliability table. A row's confidence is the
  fit's value for its score, else the prior, else absent. The table is kept with the run and
  shown on the step card and in Settings; it is refitted when the labelled set grows by a tenth.
- `kg.confidence.model-says-so-is-not-a-figure` — **[PARTIAL]** (#6386, → #6761) a language model's own stated
  certainty is never stored as a confidence: the prompts ask for none and the writer takes none
  from a model (`_write_kg_rows` reads `epistemic_status`, which is about the SOURCE's stance,
  and no confidence field). Built; not pinned by a test (Step 1.1 writes it).
- `kg.confidence.token-probabilities` — **[GAP]** (#6386) where a local model exposes token
  log-probabilities, the mean over a statement's or name's tokens is a score like any other and
  goes through the fit; it is never used raw.

### D. Several makers, several sources: how figures combine

- `kg.confidence.three-questions-apart` — **[BROKEN]** (#4751, → #6764) extraction confidence,
  reading confidence and evidential weight are three fields and three displays. Today
  `_merge_corroborating_claim` adds 0.05 for each further source (to at most 0.2) onto
  `confidence`, relabels it `corroboration`, and copies the same number into
  `evidential_confidence`: a second page repeating a statement makes the first page's extraction
  look surer, and the two fields always agree. Extraction confidence is not changed by another
  source; evidential weight is `corroboration_count`, `weighted_corroboration_count` and the
  triangulation band (`knowledge/triangulation.py`: two sources corroborated, three
  triangulated), shown as "three sources agree, one differs" (`kg.read.confidence-visible`).
- `kg.confidence.makers-agree` — **[GAP]** (#6386, → #6764) when two INDEPENDENT makers (the tagger
  and a model; two different models) produce the same mention (same stretch, same type) or the
  same statement (same subject, verb, object and line), the row keeps one attribution step per
  maker, each with its own confidence, and its confidence is the noisy-OR of them, capped at the
  best calibrated bin the check set has actually seen. Two runs of one model and prompt are one
  maker. Today a second maker is only noted (`add_attribution`); nothing combines.
- `kg.confidence.makers-disagree` — **[GAP]** (→ #6764, #1677) when makers disagree on one
  stretch (a different type; a different object or date for the same subject and verb on the
  same line; one maker finds it and a stronger one, run on the same page, does not) nothing is
  averaged and nothing is silently dropped: the row is marked `disputed`, keeps each maker's
  version, and goes to the review lens ahead of undisputed rows of the same confidence.
- `kg.confidence.reading-is-shown-beside` — **[PARTIAL]** (#5694) a statement on a line whose
  reading is uncertain says so beside its own band, and a tier that reads off the text is not
  run on a page too uncertain to read. Built: `recipes.runner.reading_too_uncertain` gates the
  parser tier and the import draft. Not built: the line's reading confidence on the statement's
  card and as a filter.
- `kg.confidence.contradiction-is-kept` — **[PARTIAL]** (#4751) two sources that say different
  things are two statements linked `contradicts`, both kept, neither lowered. Built: the link
  type and `claim_analysis`; not built: the count on the card and the paragraph.

### E. A person's decision outranks every figure, and is the ground truth

- `kg.confidence.decision-is-a-state` — **[PARTIAL]** (#5416, → #6765) verified, curated,
  rejected, merged, linked and "not the same as" are states with who and when; the card shows
  "confirmed by a person" or "rejected", never 100% or 0%; a decided row is exempt from every
  threshold (a confirmed row is always shown, a rejected one never drawn). Built: the states,
  the audited routes, rules that survive re-import (`kg.resolve.decision-remembered`). Broken
  today: demoting a statement rewrites its number (`min(confidence, 0.2)` in
  `claim/curation.py` and `save_claim`), so a decision is stored as a fake measurement; and
  `claim.transition` accepts a machine actor (#5416).
- `kg.confidence.corrections-override` — **[OK]** a person's correction of a statement's
  subject, verb, object, date or place replaces the machine's value, is audited, and a later run
  that finds the old value again writes a proposal beside it, never over it
  (`_corrected_claim_for_incoming`, `kg.tables` rules). *Test:*
  `fichero-server/tests/unit/workflows/test_merge_dedup_curation_survival.py`.
- `kg.confidence.decisions-are-labels` — **[PARTIAL]** (#5536, #6385, → #6763) every decision
  is a labelled example for section C and for `tune-names`: a verified or rejected name is a
  span label of its type; an accepted or rejected pair is a matcher label; a curated or rejected
  statement and each corrected field is a statement label; a chosen or refused authority
  candidate is a linker label. A row the SYSTEM withdrew is never a label. Built: the pair
  labels route (`GET /api/kg/review/labels`), `withdrawn` kept apart from `rejected`. Not built:
  the name, statement and link labels as one export; their use by a fit.
- `kg.confidence.reviewer-model-has-its-own-figure` — **[GAP]** (#5416, #5072) a model allowed
  to review (`kg.resolve.person-wins`) writes a verdict with ITS measured precision as the
  confidence of the verdict; the verdict is a maker's opinion in section D, never a decision.

### F. Showing the uncertain, and reviewing it

- `kg.confidence.shown-as-a-band-with-its-reason` — **[PARTIAL]** (#4751, #1768) a band (high,
  medium, low) with, on hover or in the card, the maker, the source of the figure and the check
  set it was measured on ("names by the tagger: right 2 times in 3 on this project's check
  set"); never a bare percentage, and nothing at all when unmeasured. Built: `ConfidenceBand` on
  the Inspector's statement block and the citations list; the map and timeline draw an inferred
  value as an open pin or a dashed bar from `confidence_source`. Not built: the band on a name,
  a mention, a proposal and a link; the reason; hedge words in the paragraph (#4751).
- `kg.confidence.review-least-sure-and-most-used-first` — **[GAP]** (#1677, #6280) the to-review
  lens orders by what a decision buys: disputed rows first, then by confidence nearest the
  review threshold, weighted by how many pages and statements the row touches; each row shows
  its evidence (the stretch, each maker's version) and takes yes, no or edit in one keystroke,
  as Photos asks one face at a time.
- `kg.confidence.threshold-is-a-view-control` — **[GAP]** (#5032) every graph, timeline, map and
  both tables have one minimum-confidence control and one "who says so" control
  (`explore.network.confidence-is-a-control`); what the control hides is counted beside it
  ("41 hidden below the line"), unmeasured rows are a separate switch, and decided rows are
  exempt (section E).

### G. The threshold drives what a machine may do alone

- `kg.confidence.two-thresholds-per-kind` — **[GAP]** (→ #6766, #6280) each project keeps, per
  kind (names by type, statements, merges, authority links), a **keep** line and a **trust**
  line, set FROM the check set and never typed as a bare number: the trust line is the lowest
  score at which measured precision is at least the project's target (default 95 in 100), the
  keep line the score below which precision is under 1 in 5. Below keep: not written, counted in
  the run summary with three examples. Between: written as a proposal and queued for review.
  Above trust: written as a proposal that views and search use by default without review, still
  marked unreviewed. With fewer than 50 labelled rows for a kind there is no trust line and
  everything above keep is queued.
- `kg.confidence.what-is-never-automatic` — **[PARTIAL]** (#6280, #5416; owner rulings
  2026-10-29) no threshold ever lets a machine: set a decision state; merge two names (only the
  unmistakable rule of `kg.resolve.unmistakable-auto-merge` merges, and it is a rule, not a
  score); choose an authority link; put a name into the catalogue's access points; delete a row
  a person made or decided. Built: the writer proposes and never merges on similarity
  (`upsert_entity` stage 1.6 and after, #5409). Not built: the refusal of a machine actor on
  claim review (#5416).
- `kg.confidence.thresholds-replace-the-constants` — **[BROKEN]** (#6280, #4842, → #6766) the
  cut-offs in code (0.78 for a string ratio in `_fuzzy_match_existing`, 0.92 and 0.75 for a
  cosine in `knowledge/entity_vectors.py`, 0.7 for a predicted link in
  `api/routes/kg/predictions.py`, 2 and 3 sources in triangulation) are not project settings and
  were measured on nothing. The write-time similarity pairs go
  (`kg.resolve.no-write-time-embedding-pairs`: still queued, 9 for 123 names in the measured
  run); what remains reads its line from the project's fitted table.

### H. A statement's date and place are its qualifiers

- `kg.qualifier.where-a-date-comes-from` — **[PARTIAL]** (#5008, #4659, → #6767) a statement's
  date is looked for in this order, and the level it came from is recorded on the value
  (`basis` and `source_field`): (1) the statement's own sentence (`asserted`, with its stretch);
  (2) the page's or entry's own dateline, the date the reading steps found for the page
  (`source_anchored`, field `page.date`); (3) the document's date, then the folder's or series'
  date range (`source_anchored`, an open-ended range, field naming which description); (4) a
  date a model or rule worked out (`inferred`, with its reason). Only level 1 fills the
  statement's point in time (`time_start`, `time_end`); levels 2 to 4 are bounds, shown as "on
  or after", "within" or "about", drawn dashed on the timeline, and never sorted as if exact.
  Built: level 1 kept only when the date is on the page (`_date_is_on_the_page`); level 3 from
  the document's description as an open-start range (`_first_source_date_anchor`). Not built:
  level 2 (the page's date is given to the prompt as a note, `page_date_note`, and not stored on
  the statement); the folder or series range; the level named on the value. In the measured
  free-tier run 0 of 133 statements had any date: the parser tier finds none and asks no dates
  pass.
- `kg.qualifier.date-form` — **[GAP]** (#4364, #3314) a date value is stored as: the words as
  written; an EDTF string (uncertain `?`, approximate `~`, interval, open end, unspecified
  digits); its precision; the calendar it was written in (Gregorian, Julian, a regnal or church
  reckoning named as text) with the converted proleptic Gregorian bounds for sorting; earliest
  and latest bounds. Built: `start`, `end`, `open_start`, `open_end`, `circa`, `precision`,
  `label`, `numbering` on `EvidentialDateRange`. Not built: EDTF, the calendar, any uncertainty
  but a "circa" found by a pattern, a date written out in words (the usual form in notarial
  text). `_range_from_date_text` reads only four digits with optional month and day.
- `kg.qualifier.month-ends-are-real-dates` — **[BROKEN]** (#4364, → #6767)
  `_entity_writer._range_from_date_text` ends every month on day 31 (a February or a 30-day
  month gets a date that does not exist), which a strict date parser downstream refuses.
- `kg.qualifier.where-a-place-comes-from` — **[PARTIAL]** (#4600, #5597) a statement's place is
  looked for in the same order (its own sentence; the page's dateline place; the document's or
  folder's place of creation; inferred) with the same basis, and is a POINTER to the project's
  place name (`kg.one.places-one-home`), whose coordinates come from the gazetteer link, never
  a second copy of a label and a point on each statement. Built: level 1 grounded
  (`ungrounded_span`), level 3 from the document's description (`_first_source_place_anchor`),
  a geocoded point marked `inferred` with its source. Not built: the pointer (today
  `claim_location`, `claim_geo` and `place_values` are copies on the claim), level 2.
- `kg.qualifier.qualifiers-are-not-edges` — **[PARTIAL]** (#5008, → #6768) a date or a place of
  a statement is never a second statement, an entity or an edge: it is exported as a qualifier
  of the reified statement (Wikidata's model), drawn as a label on the edge and a position on
  the timeline or the map. Built: the fields on the claim. Broken today: see the next line.
- `kg.graph.dates-are-never-nodes` — **[BROKEN]** (#5008, #4605, → #6768) no graph view draws a
  date as a node, and no list of names holds one. Three ways a date becomes a node or a name
  today, each to close:
  1. **The literal leaf.** `api/routes/kg/graph.neighborhood_impl` emits an edge to
     `literal:<object>` for any statement whose object matched no name, and the app's
     `GraphSimulation.buildNodes` draws every such target as a node. An object that is a date
     ("on the third of May") is drawn beside the people. Fix: the engine classifies a literal
     with the dates parser; a date literal is returned as the edge's `date` qualifier and no
     node; other literals stay leaves but are returned as `kind: literal` so the view can hide
     them with one switch.
  2. **The name gate.** `svo_quality.usable_entity_name` refuses a numeric date but lets
     through a bare month name, a weekday, a century, a relative day and a date written out in
     words (probed 2026-11-20; two month names were stored as a person and an organisation in
     the measured run). Fix: the gate asks the same dates parser the dates step uses
     (`workflows/tools/date_extract.py`), in the page's language; what parses as a date is a
     date value with its stretch, never a name; a feast or a named event that carries a year
     stays an event and gets the year as its date value.
  3. **The date as subject.** A dates-pass row is written as a statement whose subject slot
     holds the date (`_write_kg_rows`, the `entity_type is None` branch;
     `kg.statements.dates-are-values`), so claims lists and any view grouping by subject show
     dates where people should be.
  Existing rows are found by a scan-first, audited repair (names that parse as dates; statements
  whose subject is a date), listed for the person, never rewritten in a batch.
- `kg.graph.timeline-is-where-dates-live` — **[PARTIAL]** (#5037) the timeline lays statements
  on their date values, exact ones solid, bounded and inferred ones dashed with their basis, and
  page dates with no actor as a row of their own; the graph's "as of" control filters edges by
  the same values. Built: `KGTimelineView` with solid and dashed from `confidence_source`. Not
  built: the basis as the reason, page dates, the "as of" control.

### I. Authorities: Wikidata, VIAF, Library of Congress, the gazetteers

- `kg.authority.known-set` — **[OK]** seven authorities have one canonical URI form each and an
  identifier that fits no pattern is refused: Wikidata, VIAF, Library of Congress, Pleiades,
  Getty TGN, GeoNames, World Historical Gazetteer (`knowledge/authorities.py`). *Test:*
  `fichero-server/tests/unit/api/test_gazetteer_authorities.py`.
- `kg.authority.nothing-leaves-unasked` — **[OK]** no authority is asked anything unless the
  library's opt-in is on AND the person pressed refresh for that name; what is sent is the name
  being looked up and nothing else; candidates are matched against the local snapshots only and
  that match never fetches (`_external_authority_enabled`, `check_egress`,
  `_external_authority_candidates`); the geocoder asks the outside service only behind the same
  egress check (`media/geo.py`). *Test:*
  `fichero-server/tests/unit/security/test_external_authority_reconciliation.py`.
- `kg.authority.per-type-and-per-source-consent` — **[GAP]** (#4757, #4758) the opt-in is per
  authority and per name type (a project may look places up and never people: a name in a
  private archive is itself sensitive), a candidate is only offered from an authority that
  holds that type (a person is never matched to a place record), and the run summary says what
  was sent where. Today one switch covers all, and `_external_authority_candidates` compares
  names with no regard to type.
- `kg.authority.fetchers` — **[PARTIAL]** (#5123) built: search of Wikidata, VIAF and the
  Library of Congress into `AuthoritySnapshot` rows; Wikidata statements by SPARQL or JSON-LD
  (`knowledge/wikidata_enrich.py`). Not built: any fetcher for GeoNames, Getty TGN, Pleiades or
  the World Historical Gazetteer, though links to them can be stored.
- `kg.authority.offline-copies` — **[GAP]** (#5123, #5380, → #6769) a project can hold an
  authority offline: a GeoNames country extract, a Pleiades or World Historical Gazetteer
  download, a Linked Places file, a spreadsheet of the archive's own authority list, imported
  once into the snapshot table with its licence and date, after which place lookup needs no
  network. The 40-name table compiled into `media/geo.py` becomes such a file, with a source
  and a licence, instead of coordinates in code. A snapshot shows when it was fetched and can
  be refreshed; a refresh never changes a chosen link.
- `kg.authority.candidate-confidence` — **[GAP]** (#5123, → #6769) a candidate's figure is
  built from evidence a person can read: the name form that matched (exact, folded, an alias,
  the old-spelling key), type agreement, date overlap (the record's life or existence dates
  against the statements' dates), place agreement (the record's country or parent against the
  project's region), and how many other records share the name; it is fitted on the project's
  chosen and refused candidates (section C) once there are enough, and a "no match here" answer
  is always offered and remembered. Today the figure is 1.0 or 0.5 by name alone.
- `kg.authority.confirm-and-refuse` — **[OK]** a person chooses a candidate (a `same_as` link,
  audited, with who and when), choosing one refuses its namesakes at that authority, a refused
  candidate (`different_from`) is not offered again, and choosing a refused one withdraws the
  refusal (`link_authority_impl`). *Test:*
  `fichero-server/tests/unit/api/test_gazetteer_candidates.py`. Not built here and tracked above: the confidence kept on the
  link (`kg.confidence.authority-link`).
- `kg.authority.data-comes-in-as-claims-with-their-source` — **[PARTIAL]** (#5380, #4759)
  what an authority says (coordinates, birth and death, other names) comes in only for a
  CONFIRMED link, each as a value that names the authority record as its source, marked
  `external_import`, kept apart from what the pages say, and never overwriting a page's or a
  person's value. Built: Wikidata statements previewed and imported as claims with
  `provenance_kind=external_import` and no page. Not built: coordinates into the place name's
  `place_values` (basis `inferred`, source the record); other names into `names` (each with
  its source, so search finds them, `kg.search.one-field`); dates into `date_values`; the
  imported claim is given the default 0.5 as if measured (`kg.confidence.no-made-up-figure`).

### J. Searching the graph

- `kg.search.one-field` — **[PARTIAL]** (#4604, #5725, → #6770) one search field finds names
  and statements: a name by any of its forms with case, accents, punctuation and old spellings
  set aside (`dedupe.normalize_name`, `dedupe.spelling_key`), by an authority's other names once
  linked, and by meaning (the entity vectors); a statement by its words, its subject, its
  object and its source's words. Built: `GET /api/kg/search` (names, statements, notes and
  annotations by lower-cased substring), `GET /api/kg/entity-curation/semantic` (names by
  vector), `GET /api/kg/claim-search` (statements by vector), SPARQL with examples. Not built: accents
  and old spellings set aside (a name typed without its accent finds nothing); one route that
  merges the three; the app calls none of the mixed search (`EntityService.searchKnowledgeGraph`
  has no caller), only the MCP and CLI tools do.
- `kg.search.filters-are-the-lens` — **[GAP]** (#4604, #5032) a search narrows by type, decision
  state, minimum confidence, maker, date range (reading the qualifier values, bounded ones
  included when the range overlaps), place (a place name or a region) and folder, and its
  result IS a lens: it can be reviewed, exported and saved.
- `kg.search.what-connects-two-names` — **[PARTIAL]** (#5551) "what connects A and B" returns
  the shortest paths with the statement and page behind each step, honouring the confidence and
  "as of" controls. Built: `GET /api/kg/graph/path`. Not built: the controls; a door in
  the app.

### K. Teaching the names, statements and linking models: the set, the labels, the scorers, the trainers (#5536, #5545, #6385, #6386)

Moved here from `kg-entities-and-statements.md` section J on 2026-11-21, with its Stage 8, so the guard and the milestone tool read
its behaviours and steps in one spec; every id is kept. The ids named here outside `kg.teach.*` (`kg.names.measured`,
`kg.statements.measured`, `kg.resolve.folder-pass`) and the Stages 6 and 7 are that spec's.

The loop is `compute/distillation.md`'s (teach, correct, train, evaluate, run anywhere, publish), and it is not restated
here. This section says what that loop needs for the three knowledge-graph steps and does not have: which corrections
are ground truth, the one file a training set is, how each step is scored, and which small models are trained where.
Read against the code on 2026-11-20. What exists: a name is a mention with a span in the page's text
(`workflows/tools/extractors.write_mentions`, read back by `export_service.record_mentions`); a person's rulings on a
mention are kept per span (placed or fixed: `MENTION_CORRECTED_BY`; taken away: `MENTIONS_REFUSED`, the routes
`/mentions/repoint` and `/mentions/respan` in `api/routes/entity/entities.py`); an entity and a claim each carry a
review state (`EntityCurationState`, `ClaimCurationState`); every merge, split and authority link is an audit row
(`EntityMergeAudit`); the step's offer says in words that no trainer exists (`recipes/train_offers.WAYS`,
`recipes/jobs.DISTIL`: names "not built yet", statements "not built yet", vectors "nothing to distil"). What does not
exist: any code that turns those rulings into a training set, any scorer for names, statements or links (the evaluation
job scores readers by CER and nothing else, `training/evaluation.py`), any trainer for a tagger or a language model
(the only LoRA trainer is the vision one, `training/hf_vision_lora_train.py`), and any mark that says a page's names
were checked through.

**A first measurement (2026-11-20, by hand, on an M4 Mac with 24 GB; no Fichero code, because none exists).** It proves
the pipeline runs and what it costs; it does not show how good any model is, because the labels were a model's and no
person checked them. 72 transcribed English diary pages (about 700 characters each), split by volume: 48 to train on
(three volumes), 8 to stop on (a fourth), 16 held out (a fifth). The teacher was an open 7-billion-parameter language
model at 4 bits under MLX; the kinds were person, place, organization and date; the scorer was the strict one of
`kg.teach.names-scorer`.

| | Result | Time | Memory | Size |
| --- | --- | --- | --- | --- |
| Teacher labels 72 pages | 916 names returned, 60 (6.6%) not written on the page as returned and so not usable; 1,008 mentions kept | 10.7 s a page (20 tokens a second); 13 minutes in all | 4.8 GB | 4.3 GB download |
| spaCy's stock small English pipeline, as shipped, on the 16 held-out pages | F1 0.18 against the teacher (precision 0.17, recall 0.20) | 0.016 s a page | 0.6 GB | 15 MB |
| spaCy trained from that pipeline on the 48 pages (679 mentions), 30 passes, best pass kept by the 8 validation pages | F1 0.48 (precision 0.51, recall 0.46); person 0.45, place 0.56, organization 0.24 on 21, date 0.50 on 15 | 41 s to train on the CPU | 0.6 GB | 15 MB |
| spaCy trained from nothing on the same pages | F1 0.47; organization 0.00 on 21 | 30 s | 0.6 GB | 4 MB |
| A 1.5-billion-parameter open language model at 4 bits, asked with no training | F1 0.27 (precision 0.59, recall 0.18); 7 of 16 answers could not be read as a list | 4.0 s a page | 1.4 GB | 0.9 GB download |
| The same model with a LoRA adapter (8 layers, 0.17% of its weights, 150 steps of 2 pages) under MLX's trainer | F1 0.55 (precision 0.61, recall 0.50); person 0.62, place 0.62; 2 of 16 answers unreadable; 29 of 165 names (18%) not written on the page | 5.4 minutes to train; 3.3 s a page to run | 5.0 GB while training, 1.6 GB to run | a 22 MB adapter |

What it shows for the design: (1) both trainers run on a Mac in minutes inside 5 GB, so `kg.teach.spacy-trained-on-this-mac`
and `kg.teach.extractor-lora-on-this-mac` need no machine elsewhere to start; (2) on 48 pages the adapter beats the tagger by
seven points and costs two hundred times the seconds a page, which is the trade `kg.teach.cheapest-as-good-is-offered` must
put in front of a person, and 48 pages is too few to settle it; (3) three of 679 spans did not fall on spaCy's token
edges and were dropped, so the count must be on the manifest (`kg.teach.one-set-three-writers`); (4) a small model taught by
an adapter still returns names that are not on the page (18%) and answers that are not a list (2 of 16), so grounding
and a counted refusal come before scoring (`kg.teach.teacher-names-must-stand-on-the-page`); (5) organization and date
had 21 and 15 held-out mentions and their figures differ by up to 24 points between the two tagger runs, which is why a kind under 20
mentions is not judged (`kg.teach.names-scorer`); (6) the error table was the useful output: after training the tagger's
errors were 68 missed, 48 invented, 33 wrong boundary, 8 wrong kind. Not measured: anything against a person's
corrections, HTR text with its errors, Spanish, statements, linking, a Hugging Face Job, a cluster.

- `kg.teach.precision-from-review-decisions` — **[GAP]** (#5545) engine. Before any check set exists, the engine
  answers, per maker (provider, model, prompt version, run) and per kind of name, how many of its names a person
  verified, rejected or merged away, and how many of its statements a person curated or rejected: the precision of each
  maker on what was reviewed, with the count reviewed beside it and the words "of the reviewed, not of all" on every
  figure. It reads the review states and the attribution chain that exist; it needs no new data. It is not recall and
  never stands in for the check set. *Test (to write):* test_precision_from_review_decisions.py (two makers, one with
  8 verified and 2 rejected names, one unreviewed: 0.80 on 10 for the first, "not reviewed" for the second).
- `kg.teach.page-is-checked-for-names` — **[GAP]** (#5545) engine and app. A page counts as ground truth for names
  only when a person has marked its names checked: every name on it is confirmed or placed and what is left is not a
  name. A tagger learns "not a name" from every word that carries no label, so a page with three confirmed names of
  twenty teaches it to miss seventeen; pages with some names confirmed and no mark are never in a training or
  held-out set, and the set says how many were left out for it. The mark is per page and per kind of work (names;
  statements, separately), names who made it and when, and is cleared in words when the page's text changes under it
  (a correction of the reading after the mark). The check set of `kg.names.measured` is the pages that carry the mark.
  No such mark exists today. *Test (to write):* test_page_checked_for_names.py (an unmarked page with confirmed names
  is left out and counted; a marked page is in; correcting its reading clears the mark and says so).
- `kg.teach.names-set-from-corrections` — **[GAP]** (#5536) engine. One builder writes the names set from the
  checked pages: for each page its standing text (`actions/page_text_cache.standing_text`) and its mentions as spans
  (start, end, kind, entity) from the one mention reader (`export_service.record_mentions`), leaving out names a
  person rejected and spans a person took away, and never including a name with no place on the page (an unanchored
  mention is counted and left out). Overlapping spans keep the longer. The set is split by document (a folder or a
  volume), never by page within one, into train, validation and held-out, and the held-out pages are the ones no
  candidate saw (`training.set.held-out-picked-across-folder`). The set is one file of lines, each
  `{"id", "document", "split", "text_class", "text", "spans": [[start, end, kind, entity_id]]}`, with a manifest
  beside it: the pass each page's text came from, counts per kind and per split, and what was left out and why. The
  same pages and rulings give the same file. *Test (to write):* test_names_set_from_corrections.py (a fixture project
  with two folders: spans read back at their offsets; a rejected name and a refused span absent; an unanchored name
  counted; no document on both sides of the split; a second build is byte-identical).
- `kg.teach.one-set-three-writers` — **[GAP]** (#5536, #6385) engine. Every trainer reads that one file through a
  writer, and no trainer has a set of its own: spaCy's binary documents (a span that does not fall on token edges is
  dropped and counted on the manifest, never silently); chat lines for a language model (the page as the question, the
  names as a list of exact text and kind as the answer, the prompt the registry's versioned one,
  `kg.names.prompt-is-versioned`); tokens with begin and inside tags for a token classifier on Hugging Face. Both text
  classes are written when the page has both (the corrected reading and the raw reading it was corrected from, the
  spans carried across by `actions/highlight_reanchor`'s re-anchoring), because the model will run on raw readings.
  *Test (to write):* test_names_set_writers.py (the three forms of one fixture set agree on every span that survives;
  the dropped count is on the manifest).
- `kg.teach.teacher-names-must-stand-on-the-page` — **[PARTIAL]** (#5488, #5337) engine. A teacher's name becomes a
  lesson only where its text is found on the page as written; one that is not is kept unanchored with its reason and
  never enters a set, and the share a teacher lost this way is on its run and its card, because a teacher that
  rewrites spellings teaches nothing. Built: the anchoring and the reason (`write_mentions`, `NAME_NOT_WRITTEN`). Not
  built: the share per run, and a teacher run for names as a step with a sample (`distill.loop.teacher-any-step`).
  *Test (to write):* test_teacher_names_grounded_share.py (a fake teacher returns ten names, two respelled: eight
  mentions, two unanchored, "2 of 10 not on the page" on the run).
- `kg.teach.names-scorer` — **[GAP]** (#5545) engine. One function scores names for every candidate, in the bake-off
  and after training (`training.eval.names-precision-recall` is this line's figure): a predicted mention is right when
  its start, its end and its kind all match a checked one; precision, recall and F1 per kind and over all, each with
  the number of checked mentions it rests on, and a kind with fewer than 20 checked mentions reads "too few to judge"
  and is never ranked on. Beside the strict figures, the same three counting any overlap with the right kind, so a
  boundary habit is told from a miss. The spread of F1 over three held-out splits is the names noise band, as the
  readers' is (`training.regression.noise-band-one-number`). *Test (to write):* test_names_scorer.py (a perfect, a
  boundary-off-by-one, a wrong-kind and an empty prediction each give their known figures; a kind with five
  mentions reads too few).
- `kg.teach.names-error-table` — **[GAP]** (#5545) engine. With every names score comes a table of what went wrong,
  each row with its count and three examples a person can open on the page: the wrong kind (the right stretch, named a
  place when it is a person); the wrong boundary (a title or an office taken into the name, a surname cut); invented
  (a stretch that overlaps no checked name: a role, a common noun, a date); missed entirely; and, for a language
  model, a name it returned that is not written on the page. The table is per kind and per text class, kept with the
  run, and is what the step card shows under the figures (`training.errors.*` in
  `compute/training-and-evaluation.md` is the readers' form of the same idea). *Test (to write):*
  test_names_error_table.py (one fixture page with one error of each kind: five rows of one, each with its example).
- `kg.teach.spacy-trained-on-this-mac` — **[GAP]** (#5536) engine. The names trainer for a tagger is spaCy, trained
  whole on this Mac as a job in the local machine-learning lane (`compute.tune.on-this-mac`), from the language's
  stock pipeline when one is installed and from an empty one otherwise, with the project's kinds as its labels; it
  stops on the validation pages, not on a fixed count of passes; the pipeline it writes lands in the model store as a
  folder the step can be pinned to (`knowledge/spacy_ner._stored_path`, `runtime.spacy.pin-is-honoured`) with a card
  that names its set, its base, its seed and its scores; it is offered only above the threshold the offer names
  (`recipes/train_offers.WAYS` loses its "no spaCy trainer" sentence) and is never the step's model until the gate
  passes it and a person takes it (`distill.gate.one-rule`). The same script runs as a Hugging Face Job and on a
  cluster with no change (`compute.tune.one-trainer-three-places`); it needs no accelerator. *Test (to write):*
  test_spacy_names_trainer.py (a twelve-page fixture set trains on CPU in the test, the pipeline loads from the store
  by its pin, its card holds set, base and scores; a set under the threshold is refused in words).
- `kg.teach.extractor-lora-on-this-mac` — **[GAP]** (#5240, #6385; → #6795 "A small language model taught to find
  names and statements: LoRA with mlx-lm on this Mac, the same set as a PEFT job elsewhere") engine. A small open
  language model is taught to answer the names prompt (and, from the statements set, the statements prompt) by an
  adapter: on an Apple-silicon Mac with MLX's trainer as a job in the local lane, on Hugging Face Jobs or a cluster
  with the transformers trainer the vision LoRA uses (`training/hf_vision_lora_train.py`), from the same chat lines.
  Its answers go through the same grounding as any model's (a name not on the page is dropped and counted;
  `kg.statements.grounded`) before they are scored. The adapter lands as a model the step can choose, merged and
  converted as the vision student is (`training/mlx_landing.py`, `compute.tune.convert-for-mlx`). It is offered when
  the tagger's score on the held-out pages is below the teacher's by more than the bar, never by default: it is the
  costlier student. *Test (to write):* test_extractor_lora_set_and_landing.py (a recording stand-in for the trainer:
  the chat lines it is given match the set; the adapter it returns lands with a card; an answer naming a string not
  on the page is dropped before scoring).
- `kg.teach.statements-set-and-scorer` — **[GAP]** (#5545, #5637, #6386) engine. The statements set is the claims a
  person curated on pages marked checked for statements, each as subject, verb and object with their spans and the
  entities they resolve to; rejected claims are kept as counted wrong answers. A predicted statement is right when its
  subject and object fall on the checked statement's spans (or resolve to the same entities) and its verb is the same
  after the normaliser the claims table uses; precision is always reported; recall only on pages marked checked for
  statements, and where there are none the figure reads "precision only". The error table names: a wrong subject, a
  wrong object, a wrong verb, an invented statement, a statement about a date or a role as if it were a person
  (`kg.statements.grounded` already refuses the ungrounded ones before scoring). `kg.statements.measured` and
  `kg.compare.relations-candidates-on-the-check-set` use this scorer and no other. *Test (to write):*
  test_statements_set_and_scorer.py (five curated and two rejected claims on a fixture page: a candidate repeating a
  rejected claim loses precision; a page not marked gives precision only).
- `kg.teach.linking-set-and-scorer` — **[GAP]** (#6386, #6280) engine. The linking set is read from decisions that
  already exist: every merge a person made is a pair that is one thing; every split, undone merge and rejected
  proposal is a pair that is two; every authority link a person confirmed is a name with its record
  (`EntityMergeAudit`, the resolution rules). A resolver (the folder pass's rules, an embedder with a threshold, a
  language model asked) is scored on held-out pairs by precision and recall of the pairs it would propose, and a
  linker by the share of names whose first candidate is the confirmed record and the share it rightly leaves
  unlinked. The two similarity thresholds the writer uses (`knowledge/entity_vectors.py`, 0.92 and 0.75) are
  constants that were never measured; where an embedder is used to propose at all (`kg.resolve.folder-pass` rules it
  out as a source of merges), its threshold is the one this scorer finds for the project and is shown with the
  figure. Teaching an embedder on these pairs is the vectors row of `compute/distillation.md` and is not scheduled before the scorer
  shows the stock embedder losing to the rules. *Test (to write):* test_linking_set_and_scorer.py (three merges, one
  split and one rejected proposal: five pairs with their truth; a resolver proposing the split pair loses precision).
- `kg.teach.cheapest-as-good-is-offered` — **[GAP]** (#5941, #6385) engine. For each of the three steps the
  candidates measured on the same held-out pages are listed with score, the seconds a page takes here, the memory
  they hold and the cost of the whole project, and the one offered is the cheapest whose score is within the noise
  band of the best (the readers' rule, `recipes/bakeoff.recommend`, with the names scorer in place of CER); the
  sentence says so ("as good as the hosted model on 40 pages, free, 0.02 s a page"). A person may choose any other.
  *Test (to write):* test_names_cheapest_as_good.py (a tagger within the band of a hosted model is offered; one
  outside it is listed, not offered).
- `kg.teach.runs-anywhere-and-is-published` — **[GAP]** (#5971, #5240) engine. A trained tagger is a folder that runs
  wherever the engine runs, the remote runner included; an adapter runs under MLX on a Mac and under transformers
  elsewhere, and its card names both builds (`compute.engine.same-card-resolves-by-platform`). Publishing either to
  the person's Hugging Face account is the one publishing path (`compute/jobs-and-fine-tuning.md` Stage 2): private
  unless the person says otherwise each time, with the card's set counts, scores per kind and error table, and never
  the pages or the names themselves unless the project's rights allow it. *Test (to write):*
  test_names_model_card_for_publishing.py (the card of a trained tagger holds counts and scores and no page text).

## Build order

Each step is one builder step (25 files at most), engine first, with the test written red from
the behaviour's words before the change.

### Stage 1 — Honest figures (engine)

#### Step 1.1 — The source of a figure is true; unmeasured is absent (→ #6761)
- Behaviours: `kg.confidence.source-is-true`, `kg.confidence.no-made-up-figure`, `kg.confidence.model-says-so-is-not-a-figure`
- Tests: to write: `test_confidence_source_is_true.py` in fichero-server/tests/unit/kg/, `test_no_model_stated_confidence.py` in fichero-server/tests/unit/kg/
- Size: M

#### Step 1.2 — Three questions, three fields: corroboration never raises extraction confidence; a decision is not a number (→ #6764, → #6765)
- Behaviours: `kg.confidence.three-questions-apart`, `kg.confidence.decision-is-a-state`, `kg.confidence.contradiction-is-kept`, `kg.confidence.corrections-override`
- Tests: to write: `test_corroboration_is_not_extraction_confidence.py` in fichero-server/tests/unit/kg/, `test_demote_keeps_the_figure.py` in fichero-server/tests/unit/kg/
- Depends on: 1.1
- Size: M

#### Step 1.3 — A mention keeps its score; a proposal and a link keep theirs (→ #6762, #1675)
- Behaviours: `kg.confidence.name-and-mention`, `kg.confidence.merge-proposal`, `kg.confidence.authority-link`, `kg.prov.every-row-has-a-maker`
- Tests: to write: `test_mention_keeps_its_score.py` in fichero-server/tests/unit/kg/, `test_link_keeps_candidate_confidence.py` in fichero-server/tests/unit/kg/
- Depends on: 1.1
- Size: M

### Stage 2 — Dates and places are qualifiers, never nodes

#### Step 2.1 — No date is a node or a name: the literal classified, the gate asks the dates parser, the repair lists (→ #6768)
- Behaviours: `kg.graph.dates-are-never-nodes`, `kg.qualifier.qualifiers-are-not-edges`
- Tests: to write: `test_dates_are_never_nodes.py` in fichero-server/tests/unit/kg/, `test_name_gate_refuses_written_dates.py` in fichero-server/tests/unit/knowledge/, `GraphModelDateLiteralTests.swift` in fichero/Tests/Unit/general/Views/Library/
- Size: M

#### Step 2.2 — Where a date and a place come from, with the level named; real month ends (→ #6767)
- Behaviours: `kg.qualifier.where-a-date-comes-from`, `kg.qualifier.where-a-place-comes-from`, `kg.qualifier.month-ends-are-real-dates`
- Tests: to write: `test_statement_date_ladder.py` in fichero-server/tests/unit/kg/, `test_month_range_ends_on_a_real_day.py` in fichero-server/tests/unit/kg/
- Depends on: 2.1
- Size: M

#### Step 2.3 — The date form: as written, EDTF, bounds (#4364)
- Behaviours: `kg.qualifier.date-form`
- Tests: to write: `test_date_value_edtf.py` in fichero-server/tests/unit/kg/
- Depends on: 2.2
- Size: M

#### Step 2.4 — The calendar a date was written in; the timeline draws the basis and page dates (#3314, #5037)
- Behaviours: `kg.graph.timeline-is-where-dates-live`
- Tests: to write: `test_date_value_calendar.py` in fichero-server/tests/unit/kg/, `KGTimelineBasisTests.swift` in fichero/Tests/Unit/general/Views/Library/
- Depends on: 2.3
- Size: M

### Stage 3 — Measured figures and what they drive

#### Step 3.1 — Decisions exported as labels; the measured precision of each maker and kind (→ #6763)
- Behaviours: `kg.confidence.decisions-are-labels`, `kg.confidence.statement`, `kg.confidence.date-and-place`
- Tests: to write: `test_decisions_export_as_labels.py` in fichero-server/tests/unit/kg/, `test_maker_priors_from_check_set.py` in fichero-server/tests/unit/kg/
- Depends on: 1.1, 1.3
- Size: M

#### Step 3.2 — The fit from score to probability, its reliability table, token probabilities as a score (→ #6763)
- Behaviours: `kg.confidence.calibrated-on-the-check-set`, `kg.confidence.token-probabilities`
- Tests: to write: `test_confidence_fit_from_check_set.py` in fichero-server/tests/unit/kg/
- Depends on: 3.1
- Size: M

#### Step 3.3 — Makers agree and disagree (→ #6764)
- Behaviours: `kg.confidence.makers-agree`, `kg.confidence.makers-disagree`, `kg.confidence.reviewer-model-has-its-own-figure`
- Tests: to write: `test_makers_agree_and_disagree.py` in fichero-server/tests/unit/kg/
- Depends on: 3.2
- Size: M

#### Step 3.4 — Two thresholds per kind, set from the fit; the constants go (→ #6766)
- Behaviours: `kg.confidence.two-thresholds-per-kind`, `kg.confidence.what-is-never-automatic`, `kg.confidence.thresholds-replace-the-constants`
- Tests: to write: `test_thresholds_from_the_fit.py` in fichero-server/tests/unit/kg/, `test_no_threshold_makes_a_decision.py` in fichero-server/tests/unit/kg/
- Depends on: 3.2
- Size: M

#### Step 3.5 — The review order and the reading beside the statement, in the engine (#1677, #5694)
- Behaviours: `kg.confidence.review-least-sure-and-most-used-first`, `kg.confidence.reading-is-shown-beside`
- Tests: to write: `test_review_lens_order.py` in fichero-server/tests/unit/api/
- Depends on: 3.4
- Size: M

#### Step 3.6 — The band with its reason and the threshold control, in the app (#4751, #5032)
- Behaviours: `kg.confidence.shown-as-a-band-with-its-reason`, `kg.confidence.threshold-is-a-view-control`
- Tests: to write: `ConfidenceBandReasonTests.swift` in fichero/Tests/Unit/general/Views/Inspector/, `ConfidenceThresholdControlTests.swift` in fichero/Tests/Unit/general/Views/Library/
- Depends on: 3.5
- Size: M

### Stage 4 — Authorities and search

#### Step 4.1 — Consent per authority and type; candidates scored by evidence (→ #6769, #4757, #4758)
- Behaviours: `kg.authority.per-type-and-per-source-consent`, `kg.authority.candidate-confidence`, `kg.authority.known-set`, `kg.authority.nothing-leaves-unasked`, `kg.authority.confirm-and-refuse`
- Tests: to write: `test_authority_candidates_by_evidence.py` in fichero-server/tests/unit/kg/, `test_authority_consent_per_type.py` in fichero-server/tests/unit/kg/
- Depends on: 1.3
- Size: M

#### Step 4.2 — Offline copies and the gazetteer fetchers (→ #6769, #5123)
- Behaviours: `kg.authority.offline-copies`, `kg.authority.fetchers`
- Tests: to write: `test_authority_offline_snapshot_import.py` in fichero-server/tests/unit/kg/
- Depends on: 4.1
- Size: M

#### Step 4.3 — What a confirmed link brings in: coordinates, names, dates, each with its source (#5380, #4759)
- Behaviours: `kg.authority.data-comes-in-as-claims-with-their-source`
- Tests: to write: `test_confirmed_link_feeds_place_names_dates.py` in fichero-server/tests/unit/kg/
- Depends on: 4.2
- Size: M

#### Step 4.4 — One search in the engine: folded names, authority names, meaning, filters (→ #6770, #4604)
- Behaviours: `kg.search.one-field`, `kg.search.filters-are-the-lens`
- Tests: to write: `test_kg_search_folds_and_filters.py` in fichero-server/tests/unit/api/
- Depends on: 4.3
- Size: M

#### Step 4.5 — The search field and "what connects" in the app (→ #6770, #5551)
- Behaviours: `kg.search.what-connects-two-names`
- Tests: to write: `KGSearchFieldTests.swift` in fichero/Tests/Unit/general/Views/Library/
- Depends on: 4.4
- Size: M

#### Step 4.6 — Provenance in the exports (#4755)
- Behaviours: `kg.prov.exported-as-prov`, `kg.prov.every-row-rests-on-a-stretch`
- Tests: to write: `test_rdf_export_prov_and_reified.py` in fichero-server/tests/unit/kg/
- Depends on: 3.1
- Size: M

### Stage 8 — Teaching the names, statements and linking models (#5536, #5545, #6386)

Section K's behaviours (moved from `kg-entities-and-statements.md` Stage 8, numbers kept), engine first. Steps 8.1 to 8.3 need nothing from Stages 6 and 7 and make their bake-offs
possible: the names scorer of Step 8.3 is the scorer Steps 1.4 and 6.1 of `kg-entities-and-statements.md` call, and Step 8.4 is
the trainer its Step 6.2 starts. Each step is one builder step of at most 25 files.

#### Step 8.1 — precision from the review decisions that exist (#5545)
- Behaviours: `kg.teach.precision-from-review-decisions`
- Tests: test_precision_from_review_decisions.py (not yet written)
- Size: S

- test (to write): `test_precision_from_review_decisions.py` in fichero-server/tests/unit/kg/ (per maker and kind: verified, rejected, merged and the precision on the reviewed, with its count; an unreviewed maker reads "not reviewed"; the same for curated and rejected statements)

#### Step 8.2 — a page marked checked for names; the names set, one file with a manifest (#5545, #5536)
- Behaviours: `kg.teach.page-is-checked-for-names`, `kg.teach.names-set-from-corrections`, `kg.teach.teacher-names-must-stand-on-the-page`
- Tests: fichero-server/tests/unit/workflows/test_entity_reject_survives_reimport.py, test_page_checked_for_names.py (not yet written), test_names_set_from_corrections.py (not yet written), test_teacher_names_grounded_share.py (not yet written)
- Depends on: 8.1
- Size: M

Order: the mark as a route with its audit row and its clearing when the page's text changes; the builder over `record_mentions`; the split by document; the manifest; the share of a run's names that do not stand on the page.

#### Step 8.3 — the names scorer and its error table, through the one comparison path (#5545)
- Behaviours: `kg.teach.names-scorer`, `kg.teach.names-error-table`, `kg.teach.cheapest-as-good-is-offered`
- Tests: test_names_scorer.py (not yet written), test_names_error_table.py (not yet written), test_names_cheapest_as_good.py (not yet written)
- Depends on: 8.2
- Size: M

#### Step 8.4 — the set's three writers and the spaCy trainer as a job on this Mac (#5536)
- Behaviours: `kg.teach.one-set-three-writers`, `kg.teach.spacy-trained-on-this-mac`
- Tests: fichero-server/tests/unit/knowledge/test_one_spacy_pipeline_per_model_5370.py, test_names_set_writers.py (not yet written), test_spacy_names_trainer.py (not yet written)
- Depends on: 8.3
- Size: M

Order: the writers; the job kind beside `train-on-this-mac` with the gentle callbacks (`training/local.Gentle`); landing in the model store with a card; the offer's sentence and threshold (`recipes/train_offers.WAYS`, `recipes/jobs.DISTIL`).

#### Step 8.5 — statements: the set from curated and rejected claims, the scorer (#5545, #5637)
- Behaviours: `kg.teach.statements-set-and-scorer`
- Tests: fichero-server/tests/unit/knowledge/test_svo_quality.py, test_statements_set_and_scorer.py (not yet written)
- Depends on: 8.3
- Size: M

#### Step 8.6 — linking: the pairs from merges, splits and confirmed links, the scorer, the measured threshold (#6386, #6280)
- Behaviours: `kg.teach.linking-set-and-scorer`
- Tests: fichero-server/tests/unit/kg/test_models_propose_merges_to_spec.py, test_linking_set_and_scorer.py (not yet written)
- Depends on: 8.3
- Size: M

#### Step 8.7 — a small language model taught by an adapter, here and elsewhere; the card for publishing (#6795, #5240, #5971)
- Behaviours: `kg.teach.extractor-lora-on-this-mac`, `kg.teach.runs-anywhere-and-is-published`
- Tests: fichero-server/tests/unit/training/test_vision_lora_trainer.py, test_extractor_lora_set_and_landing.py (not yet written), test_names_model_card_for_publishing.py (not yet written)
- Depends on: 8.4, 8.5
- Size: M

Order: the MLX trainer as a job in the local lane with its memory read before it starts (`training.fit.by-memory-before-start`); the same chat lines as a Hugging Face Job; grounding before scoring; landing; the card.

## Test matrix (legs this surface touches)

| Leg | Covers | Where |
|---|---|---|
| Engine unit | every `kg.confidence.*`, `kg.qualifier.*`, `kg.authority.*`, `kg.search.*` line | `fichero-server/tests/unit/kg/`, `tests/unit/knowledge/`, `tests/unit/api/` |
| Engine real run | the ten-page measure above, repeated per tier on the project's check set | `scripts/realrun_check.py` on a scratch project |
| Swift unit | the band and its reason; a date literal is no node; the control's hidden count | `fichero/Tests/Unit/general/Views/` |
| Contract | the confidence source vocabulary, the edge's `date` qualifier and `kind` | `fichero-server/tests/contracts/` |

## Open questions for the owner

1. The precision target for the trust line: 95 in 100 is proposed as the default. Is a project
   allowed to lower it, and to what floor?
2. Above the trust line a proposal is used by views and search without review but never enters
   the catalogue or changes a state. Is that the wanted meaning of "a threshold drives
   automation", or should a trusted NAME (not a merge) also count as accepted for the folder's
   access points until a person says otherwise?
3. Stored rows carrying the old constants (0.5, 0.7, `llm` on a tagger's row): read as
   unmeasured without rewriting (proposed), or an audited, scan-first repair that clears them?
4. People's names and outside authorities: off by default per project, places on when the
   library's opt-in is on (proposed)?
5. No specification named "NGP" (graph processing in the way NLP is language processing) was
   found in the repository, its branches or the notes; the nearest are Stages 6 and 7 of
   `kg-entities-and-statements.md` and `../explore/networks.md`. If it is meant to be its own
   spec, this one is written to sit under it.

## Issues filed (milestone kg-confidence-and-provenance)

- **#6761** Confidence source is false and defaults are made up: `llm` stamped on tagger rows;
  0.5, 0.55, 0.7, 0.3 constants; unmeasured must be absent.
- **#6762** Names and mentions carry no confidence; the taggers' scores are dropped at
  `upsert_entity`.
- **#6763** Calibration: priors and score-to-probability fits per maker and kind from the check
  set and from decisions; decisions exported as labels.
- **#6764** Corroboration raises extraction confidence and overwrites the evidential field;
  makers that agree or disagree are not combined or flagged.
- **#6765** Demote rewrites a statement's confidence to at most 0.2: a decision stored as a
  measurement.
- **#6766** Two thresholds per kind set from the fit; retire the constants in
  `_fuzzy_match_existing`, `entity_vectors`, `predictions`, and the unused
  `probabilistic_scorer`.
- **#6767** Statement date and place ladder with the level named; page date stored on the
  statement; `_range_from_date_text` ends every month on day 31.
- **#6768** Dates drawn as graph nodes and stored as names: literal leaves, the name gate
  (month names, weekdays, centuries, dates in words), date-as-subject rows; a scan-first repair.
- **#6769** Authority candidates scored by evidence and type; consent per authority and type;
  offline gazetteer copies; the compiled-in coordinate table becomes a sourced file.
- **#6770** Graph search: fold accents and old spellings, search authority names, one merged
  route, filters, and a door in the app (the mixed search has no caller there).
- Also (in `kg-entities-and-statements.md`): **#6771** an English "is a person" statement is
  written on a page whose language the detector could not name.
