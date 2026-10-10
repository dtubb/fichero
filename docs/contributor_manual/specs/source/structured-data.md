# Structured data — a question set over a collection, each answer tied to its source — Design Spec (#5636)

> Milestone: source-model
> Manual: TBD — a section, "Pulling a table out of a collection": choosing or writing the questions
> for a kind of document, running them over a folder, reading the table, checking a cell against the
> words it came from, correcting it, and exporting the table with its sources.
>
> Design-led (Testing Constitution). **Status: DRAFT — 2026-10-10.** Asked by the maintainer on
> 2026-10-09 (#5636). #5636 carries no milestone yet; this spec proposes `source-model`, where the
> table job (`source.job.extract-to-table`, #5365) and the fields on prototypes (`cataloguing.md`)
> already live. Every claim about the code was read on disk in this worktree on 2026-10-10; paths are
> relative to `fichero-server/src/fichero_server/` unless they start `fichero/`, `fichero-mcp/` or
> `scripts/`. Tags: **[OK]** built and tested · **[PARTIAL]** built in part, named · **[GAP]** not
> built. Every non-OK line cites an issue.
>
> Builds on, and does not restate: `source/models-chains-and-projects.md` (recipes, jobs, the Start
> plan, the egress gate), `source/finding-documents.md` (kinds as prototypes, proposals accepted by a
> person), `source/cataloguing.md` (fields on prototypes, proposed then confirmed),
> `source/source-model.md` (segments, readings, the anchor; attribute values that cite),
> `compute/distillation.md`, `compute/remote-compute.md`, `compute/hpc-runner-acenet.md`,
> `ai/where-models-run.md`, `export/exporter.md`, `kg/project-gazetteer-and-names.md`.

## Intent

A researcher has a box of military service records: attestation papers, muster rolls, casualty
cards, pension files. Thousands of pages, and twenty questions about each soldier: name, service
number, rank, unit, date and place of enlistment, place of birth, age at enlistment, height, trade,
next of kin, date and cause of discharge. The answer wanted is a table, one row per record (or per
soldier on a muster roll), one column per question, where **every cell can be opened to the page
and the words it was read from**, checked, corrected, and exported with that source still attached.

The same need appears for notarial deeds (parties, object, price, date, notary), parish registers
(baptism: child, parents, godparents, date), and ship logs (date, position, wind, events). The
questions differ; the method does not.

Fichero answers it with pieces it already has, joined up: a **prototype** declares the questions as
typed fields; a **recipe step** asks them of a chosen model, one unit at a time; each answer lands
as an **attribute value that cites its words** (a segment, a reading, a span); a person reviews a
column at keyboard speed; values are normalised (dates, places, names) without losing the words;
rows are linked to **entities** across records (one soldier in five documents); the table exports
as CSV, Parquet and W3C annotations; a run of 41,000 files runs on this Mac for a sample and on
Hugging Face Jobs or a Slurm cluster for the whole, with cost and time shown before Start; and the
reviewed rows teach a small local model that does the next box.

## Prior art

- **The factoid model** (Bradley and Short, Prosopography of the Byzantine World): a factoid is an
  assertion a source makes about a person, at a place in that source. A cell here is a factoid: a
  value, about a record, at a span. We adopt it directly; a row is the bundle of a record's factoids.
- **Record linkage in historical demography** (IPUMS, the Minnesota Population Center's linking
  rules; LINKS for Dutch civil records; Ruggles et al. on probabilistic linking by name, birthplace
  and birth year): candidates are scored, a threshold proposes, a person confirms; false links are
  worse than missed ones. We adopt the propose-then-confirm shape the knowledge graph already uses
  (`kg.entity.models-propose-merges`, `names.merge-is-a-proposal`) and the blocking keys (name,
  birthplace, birth year) as the default candidate rule for people.
- **CIDOC-CRM** for export: a record is an `E31 Document`, a soldier an `E21 Person`, an
  enlistment an `E7 Activity` at an `E53 Place` in an `E52 Time-Span`, and every value is attributed
  through `P70 documents`. We map on export; we do not model in CRM internally.
- **W3C Web Annotation and IIIF**: a cell's citation is an annotation whose body is the field and
  value and whose target is the line with `TextQuoteSelector` and `TextPositionSelector`, exactly as
  mentions and claims already export (`source.extract.exported`, `GET /api/documents/{id}/annotations.jsonld`).
- **Hugging Face `datasets`**: the export bundle loads with `load_dataset()` with no loader script
  (`export.huggingface-dataset-ready-bundle`); structured extraction with a schema and constrained
  decoding is standard practice (JSON schema → a Pydantic model → validated output), which is what
  the extraction step does.
- **Tinderbox prototypes**: a note's attributes come from its prototype; the prototype editor is the
  schema editor. Fichero's prototypes already follow this (`models/node_prototypes.py`).
- **Key-value extraction from forms in the HTR field** (Transkribus's form and table models; the
  census and civil-register projects that train field extractors from reviewed rows): field
  extraction is trained from reviewed examples, and reviewed rows are the training set. That is the
  distillation loop (`compute/distillation.md`), not a new mechanism.

## What exists today (verified 2026-10-10)

- **Typed fields on prototypes.** `models/prototype_schema.py`: `ATTRIBUTE_TYPES` = text, long_text,
  number, date, select, multi_select, checkbox, rating, url, geo, media, document_ref, entity_ref,
  claim_ref; `ATTRIBUTE_ROLES` = title, date, geo, media, subtitle; `AttributeDecl` {type, role,
  default, options, required}; unknown types raise. Inheritance root→leaf in
  `node_prototypes.resolve_prototype_attributes`. Tested by `tests/unit/models/test_prototype_schema.py`.
  There is no field for a question's wording, units, a vocabulary's mapping, or a repeating group.
- **Prototype editor.** `fichero/fichero/Views/Prototypes/PrototypeEditorSheet.swift` (+ `+Detail`):
  create, edit, delete a prototype; a parent; attribute rows with type and role pickers and
  comma-separated options. Routes: `api/routes/document/classifications.py` (create, patch, delete,
  restore as audited actions; `resolved_prototype`). No rename-with-migration, no reorder, no
  conversion when a type changes.
- **Per-value provenance.** `workflows/attribute_sources.py` (#5600): `Document.metadata.attribute_sources[key]`
  = `{"by": "person"}` or `{"by": "machine", tool, step, run_id, artifact_id, provider, model, said,
  cites}`; a person's value is never overwritten by a run; `cites` is a segment, mention or span, but
  **no writer fills it yet** (`source.extract.attributes-cite`, [PARTIAL]). The node's kind is a
  proposal a person accepts (`document.assign_prototype`, `document.reject_proposed_kind`). Tested by
  `tests/unit/workflows/test_attributes_cite.py`.
- **Query and view.** `POST /api/documents/dataset/query` (`api/routes/document/dataset.py`,
  SQL in `db/dataset_query.py`): paging, server sort, typed filters, date bins, facet counts over
  `Document.attributes` by `json_extract`; the module's docstring records a 2026-08-13 measurement
  at 100k and 1M rows and the ruling "no column promotion". Tested by `tests/unit/api/test_dataset_query.py`.
  The app's Dataset modes (`fichero/fichero/Views/Library/ViewModes/Dataset/`: Grid (Sheet), Cards,
  Timeline, Calendar, Map) read it; `DatasetGridView.swift` has an editable cell that commits on
  focus-out through the document update, which records a person source. Effective attributes:
  `GET /api/documents/{id}/effective-attributes` (`tests/unit/api/test_effective_attributes.py`).
- **Export.** The record stream (`export_service.py`, `POST /api/export/parquet`) carries each
  document's `prototype` and `attribute_values` with who set each (#5603), and mentions and claims
  with anchor columns; `GET /api/documents/{id}/annotations.jsonld` writes mentions and claims as
  W3C annotations. Tested by `tests/unit/core/test_export_reads_the_record.py`. Attribute values
  are not yet annotations, and CSV has no per-cell source column.
- **Field extraction.** The `extract` tool (`workflows/tools/extract.py`): `fields` = [{name, prompt,
  type ∈ string, array, boolean, number}], one vision call, JSON back, saved as an `extraction`
  artifact; nothing lands on attributes, nothing is cited. The **"Extract Table" workflow**
  (`workflows/tools/table_extract.py`, `resources/default_workflows/extract_table.json`) is a
  different thing: it transcribes a table drawn on the page into a `table` artifact. It is not this
  spec's job, and the name collision is noted under Requests.
- **Entries as units.** The diary tool makes child documents with `node_kind="entry"`, their own
  attributes and a region in the parent (`workflows/tools/diary_entries.py`; `source.extract.entries-are-units`
  [PARTIAL]).
- **Jobs and places.** Reading at scale on Hugging Face Jobs is built per shard with resend of failed
  shards (`compute.job.array-by-shard`, `compute.job.sparse-resubmit`); the Slurm array and dry run
  exist, live submit does not (`compute.job.live-submit` [GAP]); the Start plan carries pages and
  cost (`source.onboard.estimate-before-start` [PARTIAL]); the egress gate is one rule in intent and
  three in code (`ai.where.one-egress-gate` [BROKEN]).
- **The job id.** `source.job.extract-to-table` is declared [GAP] (#4949, #5365) in
  `models-chains-and-projects.md`; this spec is its design.

## The design

### 1. The question set is the prototype's fields

A **question set** is a prototype's declared fields, each one a question in plain words the model
is asked and the person reads. `AttributeDecl` gains:

| Addition | Meaning | Example (attestation paper) |
|---|---|---|
| `ask` | the question, as a sentence | "What is the soldier's regimental number?" |
| `label` | the column heading | Service no. |
| `unit` | for `number`: the unit, fixed or read | height in inches; "read" when the page says ft/in |
| `precision` | for `date`: allowed precision (day, month, year, range) | enlistment date: day |
| `vocabulary` | for `select`: the options, each with an optional authority mapping | rank: Private, Corporal, Sergeant… |
| `entity_type` | for `entity_ref`: person, place, organisation | place of birth → place |
| `not_found` | whether "not on this page" is an acceptable answer | next of kin: yes |
| `examples` | a few worded answers, used in the prompt and the training set | "No. 123456" → 123456 |
| `check` | a column rule: range, pattern, cross-field | discharge after enlistment |

Types are the existing fourteen. `date` keeps the words and an ISO value with precision
(`date_jdn` where the node's date role applies); `number` keeps the words, the value and the unit;
`select` keeps the words and the option; `entity_ref` keeps the words and the entity.

**Repeating groups.** A muster roll lists many soldiers on one page. A prototype may declare
`entries: <child prototype key>` (muster roll → muster entry {name, number, rank, remarks}). The
extraction step then makes one **entry node** per soldier under the page (the diary tool's pattern,
`node_kind="entry"`, with a region or the lines it covers), each with the child prototype. A row is
a node: a document, or an entry node. Nothing new is stored; the table is the dataset query over
nodes with that prototype.

**Document attribute or entity?** A field answers about *this record*: the attestation's rank,
date, height. A thing that recurs across records (the soldier, the regiment, the parish) is an
**entity** in the knowledge graph, and the row refers to it through an `entity_ref` field. Extraction
never creates the "Soldier" entity by itself; linking does (section 6), with a person's confirmation.

**Prototypes can be proposed.** A step on a sample of units (20 to 50) proposes a prototype: its
fields, types, vocabularies and example answers, as a proposal in the editor, accepted or edited by a
person. Same shape as a proposed kind (`source.extract.kinds-proposed-as-prototypes`).

**Shipped sets.** A recipe can carry its prototypes (`catalogue.recipes-ship-prototypes`); the
flagship ships `service-record`, `muster-roll` + `muster-entry`, `notarial-deed`, `baptism-entry`,
`log-entry`.

### 2. Extraction, one unit at a time, by a chosen model

The recipe step **Extract to a table** (`extract-to-table`) takes a folder or selection and a
prototype (the folder's, or chosen). For each unit (a document, or each entry the splitter found):

1. The input is the unit's **tied reading** (its lines with segment ids and that reading's id),
   when the page has a reading at or under the project's CER bar; otherwise the page image, for a
   vision model. Text is the default because it gives line anchors for free.
2. One call asks all the prototype's questions. The output schema is a Pydantic model generated
   from the prototype: per field `{value, words, status, confidence}` where `status` ∈ found,
   not_found, illegible, ambiguous, and `words` is the exact run of characters the value was read
   from. Constrained output where the runtime supports it; otherwise validated and re-asked once.
3. The engine finds `words` in the reading (exact first, then the closest real span, labelled
   `fuzzy`, as `extractors.name_spans` and `_anchor_quotation` do) and resolves it to a segment,
   the reading and a character span: a `SourceAnchor`.
4. The value lands through `attribute_sources.write_from_run` with `cites` = `{segment_id,
   representation_id, char_start, char_end, words, anchor: exact|fuzzy|none}`, `said` = the model's
   raw answer, and the status. A person's value is never overwritten.
5. **"Not found" is a value.** It is stored as status `not_found` with no value, distinct from a
   field nobody has filled (no source) and from an empty string. Counts and exports keep the three apart
   (`explore.count.missing-is-a-value`).

Every value is a claim tied to an anchor. A value whose words cannot be found on the page is kept
with `anchor: none` and a reason, and the review queue surfaces it first; it is never silently
accepted.

### 3. Confidence, and review at keyboard speed

Two confidences are kept: the model's **self-report** (stored, shown dimly, never used for
thresholds) and a **calibrated** one, which is agreement: between two readings (two models, or the
student and the teacher), between a value and its column check, and, once a column has person-checked
rows, the measured accuracy of values at that self-report level. A column shows its calibration state.

**Review.** In the table, a cell's state is visible (machine / accepted / person's / not found /
problem). Selecting a cell shows its page in the Preview with the cited words lit, and the Inspector
shows the words, the line, the model, its answer and confidence. Keys: Down moves down the column;
Return accepts; typing replaces (a person's value); X rejects (value cleared, source kept as
rejected); N marks not-found; Shift-Return accepts to the end of the column above a confidence. Each
is one audited, undoable action (`attribute.accept`, `attribute.set`, `attribute.reject`,
`attribute.not_found`; a batch accept is one action with one undo, `audit.one-operation-has-one-undo`).
Filters: low confidence, not found, unanchored, out of vocabulary, failed check, disagreeing readings.
No threshold accepts by itself until a person sets one per column after seeing a sample's accuracy.

### 4. Column checks

Each column runs its checks on write and on demand: the type parses (a date, a number); the date
is inside the prototype's or the project's range; a select value is in the vocabulary; a number is
in range and in the unit; a pattern matches (a service number); cross-field rules (discharge after
enlistment; age consistent with birth year). A failed check is a problem on the cell, counted in the
column header, filterable; it never changes the value.

### 5. Normalisation without losing the words

A value keeps three things: the **words** (as written: "Sgt.", "12th Febry 1915", "Halifax N.S."),
the **value** as read, and the **normalised** form: a date as ISO with precision; a place as a
gazetteer entry (`gazetteer.one-per-project`, with authority links proposed and confirmed); a name as
an entity in the project's name list (`names.one-per-project`, `names.preferred-form-rule`); a rank as
its vocabulary option. Normalisation is a step a person can run again with a better rule; the words
and the anchor never change. Date parsing uses the one date parser the project already has
(`histdate.py`); name and place normalisation use the knowledge graph's own proposals, never a
second mechanism (`kg.scale.normalize-names`).

### 6. Linking rows to an entity across documents

One soldier appears on an attestation paper, three muster rolls, a casualty card and a pension file.
**Link** proposes that these rows are one person: candidates blocked on normalised surname and
first initial, scored on name similarity, birthplace, birth year or age at date, service number,
unit and dates; the score and the evidence for and against are shown; a person confirms, rejects,
or splits later (`kg.entity.models-propose-merges`, `names.merge-is-a-proposal`, `entity.split`).
A confirmed link makes the row's `entity_ref` field point at the entity, and the entity's page lists
its records in date order ("a life assembled from five documents, and how",
`explore.count.linked-records-say-how`). A link is a claim with the rows as its evidence, undoable.
Service numbers and other identifiers can be declared `identifier` fields: an exact match on one is a
strong candidate, never an automatic merge.

### 7. Export

- **CSV**: one row per unit; for each field, `<field>` and `<field>_source` = `document id · page ·
  segment id · "words" · by · confidence · status`; a project switch for "confirmed values only".
- **Parquet**: the existing stream (`export.duckdb-parquet-not-pyarrow`) gains
  `attribute_values.parquet`: one row per value with the anchor columns mentions already have
  (`anchor_columns`), status, both confidences, normalised form, and the run. The Hugging Face bundle
  (`export.huggingface-dataset-ready-bundle`) is this plus a dataset card.
- **W3C annotations / IIIF**: each value is an annotation with motivation `describing`, body
  `{field, value, normalised}`, target the line with `TextQuoteSelector` + `TextPositionSelector`
  and the reading, creator the run or the person, through the one annotation writer
  (`source.extract.exported`).
- **RDF**: the CIDOC-CRM mapping above, through `GET /kg/export/rdf` (`export.rdf-multi-format-with-named-jsonld-context`).
- **EAD / Dublin Core** where a field maps (`catalogue.export-standards`).

### 8. At scale: this Mac, Hugging Face Jobs, a cluster

One run is one job in the one job model (`compute.job.one-state-machine`), its units sharded
(`compute.job.array-by-shard`), failed shards resent alone (`compute.job.sparse-resubmit`), results
landed exactly once (`compute.hpc.results-exactly-once`, `compute.land.never-overwrites`), resumable
after the app quits (`compute.job.survives-the-app-quitting`).

**Pilot first.** Before the whole, the step runs on a sample (the person chooses; 100 units by
default) on this Mac or the chosen place, and reports pages per hour, cost per unit, and the
column accuracy once the person has checked the sample. The Start sheet then states, for the whole:
units, model and place (`ai.where.estimate-names-the-place`), time, cost, and that pages or text
leave the Mac (asked once per project, `ai.where.batch-sends-ask-the-project`). Figures are marked
measured (from the pilot) or estimate.

- **This Mac**: the student or a small model through MLX, throttled, under the one lane model.
- **Hugging Face Jobs**: the worker image, vLLM offline batch per shard, text or images as the
  package (`compute.package.*`), results as Parquet shards.
- **A Slurm cluster (ACENET)**: the same shards as a throttled array under Apptainer, Globus for the
  package, `compute.hpc.*`; nothing here is cluster-specific.

**The table at 41,000 rows**: the dataset query is paged and sorted on the server; the grid fetches
pages by cursor (`library.listing.slim-rows-paged-by-cursor`); review filters are server filters.
What will be measured: query time at 41k and 100k rows with twenty attributes and sources, grid
scroll at those sizes, and the memory of the open table. No figure is claimed until measured.

### 9. Distilling the extraction

Reviewed rows are the training set: for each unit, (reading or image, the questions) → (values,
words, statuses). Only person-checked rows are ground truth; a model-checked row is labelled so
(`distill.scale.check-trust-levels`). The student is a small language model with a LoRA for
question answering with spans, or a span tagger per field where fields are short (both measured in
the first bake-off). It is measured per column on held-out person-checked rows: value accuracy, span
exactness, not-found precision; adopted per column where it clears the bar (`distill.adopt.within-bar`);
then runs first, with the teacher asked only where it is unsure (`distill.cascade.small-first`). Every
accept, correction and rejection in review is an example (`distill.scale.everyday-corrections-are-data`).
The student lives in the project and can be made global (`compute.model.lives-in-project`).

### 10. In the app, MCP and CLI

- **Library**: a folder with a prototype (or a selection) shows its table in Sheet mode: one column
  per field, state per cell, problems per column, the review filters, a column menu (accept all above
  a confidence, run checks, normalise, link). Organise ▸ Extract to a Table starts the step with the
  pilot-first sheet.
- **Inspector** of a row: a Fields section listing each value, its words, the line, who set it, the
  model and confidence, with Accept, Correct, Reject, Not found; the Preview lights the cited words
  (the claim highlighting path, `kg.entity.source.highlights-span`).
- **Prototype editor**: add, rename (rows migrate), retype (values convert or are flagged), reorder,
  options with mappings, the question wording and examples, `entries`, checks; a proposed prototype
  shown for acceptance.
- **MCP and CLI**: generated from the routes (`openapi.mcp.one-tool-per-operation`,
  `openapi.cli.one-command-per-operation`): start a run, its status, the table (the existing dataset
  query), a value's source, accept / set / reject / not-found, link proposals and answers, export.
  No hand-written tool.

## Answers to the issue's questions

1. A step creates nodes of a kind: entry nodes for repeating groups, each with the child prototype;
   a document's kind is proposed, not assigned. A fact about the record is an attribute; a thing that
   recurs across records is an entity, referred to by an `entity_ref`; the Soldier entity comes from
   linking, confirmed by a person.
2. The editor creates, edits and deletes prototypes with typed fields; missing: rename with
   migration, reorder, retype with conversion, option mappings, the question wording, examples,
   repeating groups, checks, and accepting a proposed prototype.
3. Yes, as a proposal from a sample, accepted in the editor.
4. Yes: each answer lands in the prototype's typed column with `cites` filled (segment, reading, span,
   words), status and both confidences; not-found is a status, distinct from empty and from unfilled.
5. The Sheet mode with cell states, the Preview lighting the words, keyboard review, audited
   per-cell and per-column actions, and server-side filters for low confidence and not found.
6. Column checks as above; names and places normalise through the knowledge graph's own lists and
   proposals.
7. One job, sharded, resumable, pilot first, estimate before Start, this Mac / Hugging Face / Slurm;
   query and grid paged on the server, measured before any figure is claimed.
8. CSV with a source column per field, Parquet with a values table, W3C annotations, RDF.

## Behaviors

### Schema (`structured.schema.*`)

- `structured.schema.typed-fields` — **[PARTIAL]** (#5636) a prototype declares typed fields with a
  type from one closed list, options, required and a role. *Built:* `models/prototype_schema.py`
  (`AttributeDecl`, `ATTRIBUTE_TYPES`), inheritance in `models/node_prototypes.py`; pinned by
  `fichero-server/tests/unit/models/test_prototype_schema.py`. *Not built:* `ask`, `label`, `unit`,
  `precision`, vocabulary mappings, `entity_type`, `not_found`, `examples`, `check`.
- `structured.schema.question-wording` — **[GAP]** (#5636) each field carries the question a model is
  asked and a person reads, its label, and a few worded examples; the extraction prompt is built from
  them and nothing else.
- `structured.schema.units-and-precision` — **[GAP]** (#5636) a number field declares its unit (fixed,
  or read from the page); a date field its allowed precision; both are kept on the value.
- `structured.schema.vocabulary-with-mapping` — **[GAP]** (#5636) a select field's options may each map
  to an authority term (Getty AAT or a project list); a value outside the vocabulary is a problem,
  not a new option.
- `structured.schema.repeating-groups` — **[GAP]** (#5636) a prototype may declare `entries` (a child
  prototype); extraction makes one entry node per entry under the page, each a row of the child
  prototype, with the lines or region it covers.
- `structured.schema.editor-complete` — **[PARTIAL]** (#5636) the prototype editor adds, renames
  (rows migrate through one audited action), retypes (values convert or are flagged), reorders and
  deletes fields, edits options with mappings, wording, examples, `entries` and checks. *Built:*
  `fichero/fichero/Views/Prototypes/PrototypeEditorSheet.swift` (+ `+Detail`) creates, edits and
  deletes prototypes with typed rows and options; the routes in
  `api/routes/document/classifications.py` are audited, pinned by
  `fichero-server/tests/unit/api/test_routes_classification_ontology_actions.py`. *Not built:* rename
  with migration, reorder, retype with conversion, mappings, wording, examples, entries, checks; the
  sheet itself has no Swift test.
- `structured.schema.proposed-from-a-sample` — **[GAP]** (#5636) a step on a sample of units proposes a
  prototype (fields, types, vocabularies, examples) as a proposal a person accepts or edits; nothing
  is created until accepted.
- `structured.schema.recipes-ship-sets` — **[GAP]** (#5636, #5365) a recipe carries its prototypes;
  the flagship ships service-record, muster-roll with muster-entry, notarial-deed, baptism-entry and
  log-entry.

### Extraction (`structured.extract.*`)

- `structured.extract.step-in-a-recipe` — **[GAP]** (#5636, #4949) "Extract to a table" is a recipe
  step and an Organise verb on a folder or selection, taking a prototype; it is the design of
  `source.job.extract-to-table`.
- `structured.extract.text-first-then-image` — **[GAP]** (#5636) the input is the unit's tied reading
  with line ids when its CER is at or under the project's bar; otherwise the image for a vision
  model; the choice is recorded on each value's source.
- `structured.extract.schema-constrained` — **[GAP]** (#5636) one call per unit asks every field; the
  answer is validated against a Pydantic model generated from the prototype (value, words, status,
  confidence per field), constrained where the runtime can, re-asked once otherwise, refused loudly
  after that.
- `structured.extract.lands-on-attributes` — **[GAP]** (#5636) answers land as the node's typed
  attribute values through `attribute_sources.write_from_run`, never as an artifact alone; a person's
  value is never overwritten.
- `structured.extract.not-found-is-a-status` — **[GAP]** (#5636) not found, illegible and ambiguous
  are statuses on the value, distinct from an empty value and from a field nobody filled; counts,
  filters and exports keep them apart.

### Citation (`structured.cite.*`)

- `structured.cite.value-names-its-words` — **[GAP]** (#5636, #5600) every machine value's source
  carries `cites` = segment, reading, character span and the words, found exactly or by the closest
  real span (labelled fuzzy); a value whose words are not on the page is kept with `anchor: none`
  and a reason and is reviewed first.
- `structured.cite.value-records-its-maker` — **[PARTIAL]** (#5636, #5600) each value says who set it:
  a person, or a run with its step, model and answer. *Built:* `workflows/attribute_sources.py`;
  pinned by `fichero-server/tests/unit/workflows/test_attributes_cite.py`. *Not built:* the status,
  both confidences and the anchor on the source, and the source on the effective-attributes response.
- `structured.cite.words-lit-in-preview` — **[GAP]** (#5636) selecting a cell opens its page in the
  Preview with the cited words lit and the Inspector showing the words, line, model and confidence,
  through the one anchor path the claim inspector uses.

### Review (`structured.review.*`)

- `structured.review.two-confidences` — **[GAP]** (#5636) a value keeps the model's self-report and a
  calibrated confidence from agreement and from the column's checked rows; thresholds use only the
  calibrated one; a column says whether it is calibrated.
- `structured.review.keyboard-column` — **[GAP]** (#5636) a column is reviewed from the keyboard:
  Down, Return accepts, typing corrects, X rejects, N not-found, Shift-Return accepts above a
  confidence to the column's end.
- `structured.review.one-action-per-answer` — **[GAP]** (#5636) accept, set, reject and not-found are
  audited actions, each undone as one; a batch accept is one action with one undo; a person's value
  outranks a run's and no later run proposes over it.
- `structured.review.filters` — **[GAP]** (#5636) low confidence, not found, unanchored, out of
  vocabulary, failed check and disagreeing readings are server filters on the dataset query.
- `structured.review.no-silent-threshold` — **[GAP]** (#5636) no value is accepted by itself until a
  person sets a threshold for that column after seeing a checked sample's accuracy at that level.
- `structured.review.column-checks` — **[GAP]** (#5636) type, range, vocabulary, pattern and
  cross-field checks run on write and on demand; a failure is a counted, filterable problem on the
  cell and never changes the value.

### Normalisation and linking (`structured.normalise.*`, `structured.link.*`)

- `structured.normalise.keeps-the-words` — **[GAP]** (#5636) a value holds the words, the value and
  its normalised form; normalising again changes only the third.
- `structured.normalise.dates-places-names` — **[GAP]** (#5636, #5380) dates normalise through the one
  date parser with precision; places to the project gazetteer; names to the project name list;
  never a second mechanism.
- `structured.link.rows-to-an-entity` — **[GAP]** (#5636) Link proposes that rows across documents
  are one entity, blocked on name and scored on birthplace, birth year or age, identifiers, unit
  and dates, with evidence for and against; a person confirms, rejects or splits; a confirmed link
  fills the row's `entity_ref` and is a claim with the rows as evidence, undoable.
- `structured.link.identifiers-propose-never-merge` — **[GAP]** (#5636) an exact match on an
  identifier field is a strong candidate, never an automatic merge.
- `structured.link.entity-lists-its-records` — **[GAP]** (#5636, #5032) an entity's page lists the
  rows linked to it in date order with how each was linked.

### Export (`structured.export.*`)

- `structured.export.csv-source-per-field` — **[GAP]** (#5636) CSV has, beside each field, a source
  column with document, page, segment, words, by, confidence and status; a switch exports confirmed
  values only.
- `structured.export.parquet-values-table` — **[PARTIAL]** (#5636, #5603) Parquet carries every value
  with its anchor, status, confidences, normalised form and run. *Built:* the document rows carry
  `prototype` and `attribute_values` with who set each (`export_service.py`, `POST /api/export/parquet`);
  pinned by `fichero-server/tests/unit/core/test_export_reads_the_record.py`. *Not built:*
  `attribute_values.parquet` with anchor columns, status and confidences; the Hugging Face bundle.
- `structured.export.w3c-annotations` — **[GAP]** (#5636) each value exports as a `describing`
  annotation on its line with text selectors, through the one annotation writer; the IIIF manifest
  lists them.
- `structured.export.rdf-cidoc` — **[GAP]** (#5636) the table exports to RDF with the CIDOC-CRM
  mapping (document, person, activity, place, time-span, `P70 documents`).

### Scale (`structured.scale.*`)

- `structured.scale.pilot-first` — **[GAP]** (#5636) a run starts with a sample the person chooses;
  its measured pages per hour, cost per unit and, once checked, column accuracy feed the estimate
  for the whole.
- `structured.scale.estimate-before-start` — **[GAP]** (#5636, #4951) Start states units, model and
  place, time, cost and whether text or pages leave the Mac, each marked measured or estimate; the
  egress gate is asked once per project.
- `structured.scale.one-job-sharded` — **[GAP]** (#5636, #5240) a run is one job in the one job model,
  sharded, failed shards resent alone, landed exactly once, resumed after the app quits.
- `structured.scale.three-places` — **[GAP]** (#5636, #5642) the same step runs on this Mac (MLX,
  throttled), on Hugging Face Jobs (vLLM batch per shard) and on a Slurm cluster (array under
  Apptainer, Globus transfer); nothing is cluster-specific.
- `structured.scale.table-paged` — **[PARTIAL]** (#5636, #5260) the table and its filters are served
  paged and sorted by the engine at any size. *Built:* `api/routes/document/dataset.py`,
  `db/dataset_query.py`; pinned by `fichero-server/tests/unit/api/test_dataset_query.py`. *Not
  built:* source and status columns in the query, the review filters, cursor paging in the grid, and
  a measurement at 41k and 100k rows with twenty attributes.

### Distillation (`structured.distil.*`)

- `structured.distil.reviewed-rows-are-the-set` — **[GAP]** (#5636, #5404) person-checked rows form
  the training and held-out sets, split by document, trust level recorded; a model-checked row is
  labelled so.
- `structured.distil.student-per-column-bar` — **[GAP]** (#5636, #5337) the student is measured per
  column (value accuracy, span exactness, not-found precision) on held-out rows and adopted only for
  the columns where it clears the bar.
- `structured.distil.student-first-teacher-when-unsure` — **[GAP]** (#5636, #5338) an adopted
  student runs first; the teacher is asked only for values under the calibrated confidence.

### Surfaces (`structured.app.*`, `structured.mcp-cli.*`)

- `structured.app.sheet-over-a-folder` — **[PARTIAL]** (#5636) a folder with a prototype shows its
  table in Sheet mode, one column per field. *Built:* `fichero/fichero/Views/Library/ViewModes/Dataset/Grid/DatasetGridView.swift`
  over the dataset query; pinned by `fichero/Tests/Unit/general/Services/DatasetModeStoreFilterTests.swift`
  and `DatasetPageDecodeTests.swift`. *Not built:* cell states, problems per column, the review
  filters, the column menu, Organise ▸ Extract to a Table.
- `structured.app.inspector-fields` — **[GAP]** (#5636) a row's Inspector lists each value with its
  words, line, maker, model and confidence, and Accept, Correct, Reject, Not found.
- `structured.mcp-cli.generated` — **[GAP]** (#5636, #5453) every route of this spec (run, status,
  value source, accept / set / reject / not-found, link proposals and answers, export) is an MCP tool
  and a CLI command generated from OpenAPI; none is hand-written.

## Test matrix

| Leg | This surface? | Pins | File |
|---|---|---|---|
| Backend (pytest) | y | schema additions; entries as nodes; one unit through the real runner with a stub model landing cited values; not-found; checks; review actions and undo; filters; CSV and Parquet with sources; annotations | `fichero-server/tests/unit/structured/test_structured_data_to_spec.py` |
| Backend, known answer | y | a synthetic box of attestation papers and one muster roll with a known table; column accuracy and span exactness reported | `fichero-server/tests/unit/structured/test_structured_known_answer.py` |
| Load (#4634) | y | dataset query with sources at 41k and 100k rows, twenty fields, timed | `fichero-server/tests/perf/test_structured_table_scale.py` |
| MCP / CLI | y | the generated tools and commands for run, review and export | `fichero-mcp/tests/test_mcp_full.py`, `fichero-cli/tests/` |
| Swift unit | y | cell state, keyboard review model, column problems | `fichero/Tests/Unit/general/Models/StructuredReviewTests.swift` |
| Click-around (Mac) | y | select a cell → words lit → Return accepts → undo | `fichero/Tests/UI/` |

Fixtures: a synthetic set with a known answer first; then a real box the maintainer names, broken down
by a person.

## Open questions (with recommendations)

1. **Rows as nodes, or a table store of their own?** Recommendation: nodes (documents and entry nodes)
   with typed attributes. One home, the existing query, the existing export; a separate table store
   would be a second place for the same fact (`source.extract.one-fact-one-home`).
2. **Where a muster roll's soldiers live.** Recommendation: one entry node per soldier under the page,
   with the child prototype and the lines it covers; the same unit the diary splitter makes.
3. **When does extraction make an entity?** Recommendation: never by itself. A row refers to an entity
   through an `entity_ref` field; the entity exists through linking, confirmed by a person. Extraction
   that created a Soldier per row would make 41,000 entities to merge later.
4. **May a model propose a prototype?** Recommendation: yes, from a sample of 20 to 50 units, as a
   proposal; nothing exists until accepted.
5. **Auto-accept thresholds.** Recommendation: none by default; a person sets one per column after
   seeing a checked sample's accuracy at that level. Find the Documents' 95% rule is for a calibrated
   score; a self-report is not one.
6. **What is confidence?** Recommendation: agreement (two readings, checks, measured accuracy) is the
   confidence used for thresholds; the self-report is shown but never acted on.
7. **Text or image by default?** Recommendation: the tied reading when its CER is under the project's
   bar; it gives line anchors. A vision model only where there is no reading good enough, with the
   anchor then found on the best reading after the fact, or `none`.
8. **Per project or shared question sets?** Recommendation: per project, promotable to a collection
   like models and prototypes (#5539; `finding-documents.md` question 1).
9. **Export unreviewed values?** Recommendation: yes, with their status and maker in every format, and
   one switch for confirmed only. Hiding machine values would hide most of a 41,000-row table.
10. **The student's shape.** Recommendation: decide by the first bake-off between a small LM with a
    LoRA answering with spans and a per-field span tagger, on the synthetic box, then a real one.
11. **Milestone for #5636.** Recommendation: `source-model`, beside #5365, so the job, the fields and
    the citation rule are one milestone.
12. **The name "Extract Table".** Recommendation: rename the existing workflow (a table drawn on the
    page) "Transcribe a Table", and keep "Extract to a Table" for this spec's step.

## Requests to other specs (for the manager to route; nothing edited here)

- `source/models-chains-and-projects.md`: `source.job.extract-to-table` points here for its design;
  the job registry names it once (`extract-to-a-table` appears in `cataloguing.md`'s header and
  `extract-to-table` in the behaviour; one spelling).
- `source/cataloguing.md`: its field types (text, date or date range, number, person, place,
  controlled term, extent, condition) are not the code's fourteen (`ATTRIBUTE_TYPES`); person and
  place are `entity_ref` with an `entity_type`; extent and condition are text or number with a unit.
  One list, in `prototype_schema.py`.
- `source/source-model.md`: `source.extract.attributes-cite` gains `words`, `anchor` (exact / fuzzy /
  none), status and the two confidences on the source; `source.extract.entries-are-units` covers
  entry nodes made by this step.
- `export/exporter.md`: `attribute_values.parquet`, the CSV source column, and values as annotations.
- `explore/tables-and-counts.md`: not-found as a value and linked records on an entity's page are
  this spec's rows.
- `kg/project-gazetteer-and-names.md`: normalisation of place and name fields goes through its lists.
- `ui/library-view-modes.md`: Sheet mode gains cell states, problems and review filters; the
  "Extract Table" workflow name collides with this step (open question 12).
- `compute/remote-compute.md`, `compute/hpc-runner-acenet.md`: this step is a second job kind beside
  reading, with text or images as its package.

## Sources

- Bradley, J. and Short, H., "Texts into databases: the evolving field of new-style prosopography",
  Literary and Linguistic Computing 20 (2005) — the factoid model.
- Ruggles, S., Fitch, C. and Roberts, E., "Historical Census Record Linkage", Annual Review of
  Sociology 44 (2018).
- CIDOC Conceptual Reference Model, version 7.1 — https://cidoc-crm.org/
- W3C Web Annotation Data Model — https://www.w3.org/TR/annotation-model/
- IIIF Presentation API 3.0 — https://iiif.io/api/presentation/3.0/
- Hugging Face `datasets` documentation — https://huggingface.co/docs/datasets/
