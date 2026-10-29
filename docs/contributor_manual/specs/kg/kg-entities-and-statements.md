# Knowledge Graph — names, statements, review and the graph — Design Spec (#6283, #6280, #5380)

> Milestone: kg-entities-and-statements
> Manual: TBD — a section, "Names and statements", telling a researcher how the people, places
> and institutions of a folder are found, how to confirm, reject or merge them, how the folder's
> catalogue entry and the authority sheets come from them, and how the statements and the
> graph views read.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-10-29), written from the review in
> `agent-work/status/briefs/kg-review-2026-10-29.md` and the B12 data. This is the OVERVIEW of the
> knowledge graph: what it is for, how names and statements are made, reviewed, joined to the
> catalogue and shown. The detail specs stand and are cited, never restated: `kg-tables.md` (the
> Entities and Claims tables, CRUD, rules that survive re-import), `kg-entity-inspector.md` (one
> entity in the Inspector), `kg-readable-representation.md` (the paragraph), `kg-enrichment.md`
> (authorities, RDF), `project-gazetteer-and-names.md` (the authority lists, whose behaviours this
> spec schedules), `kg-interactions.md`, `hermeneutic-layer.md`, `../explore/networks.md`,
> `../explore/time.md`, `../explore/place.md`, `../source/cataloguing.md` and the names and
> statements steps in `../source/models-chains-and-projects.md`.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built · **[BROKEN]** code contradicts the line.

## Intent (the design)

A box of court files names a few hundred people, a few dozen places and a handful of offices
and institutions. The knowledge graph is where those names live once, with every form the pages
use, what each page says about them, and a person's word on each. It exists to feed four things,
in this order: the **catalogue** (each folder's people, places and institutions, and one
authority sheet per name), **writing** (a paragraph or a note that cites its statements),
**timelines and maps** (dated and placed statements), and the **research view** (what connects
two names, and on what evidence).

So the unit of work is the **folder**, not the library: a names step runs on a folder's pages
with a model whose cost is shown first and never runs twice on the same page and model; the
folder's names come back as a short reviewable list, with proposals to join the ones that are
one person written three ways; a person confirms, rejects or merges, and that decision is
remembered through every later import; the confirmed names become the folder's attributes and
the catalogue reads them; a statement is a claim one of those names makes or is the object of,
resting on its line, with its date and place as values, never as subjects. Graph views stand on
reviewed names and on edges whose rule is stated.

**One source of truth.** A name, a place, an institution, a statement and the link between a name
and a page each live in ONE record, and every view reads it: the Inspector, the Entities and
Claims panes, the knowledge lenses and graph views, the folder's catalogue lists, the authority
sheets, the Excel and RDF exports, the prompts' known-names list. Section G names the record for
each fact, the copies that hold it twice today, and the migration that retires each copy. No new
store is added: the `KnowledgeEntity` and `KnowledgeClaim` tables and the segment-anchored mention
are the records; everything else is derived from them or goes.

Lives in: the engine's `workflows/tools/extract_entities_only.py`, `extract_svo_only.py`,
`_entity_writer.py`, `knowledge/svo_quality.py`, `knowledge/dedupe.py`, `api/routes/kg/*`,
`api/routes/entity/*`, `api/routes/claim/*`, `recipes/catalogue_step.py`; the app's Entities and
Claims panes, the Inspector's Entities tab and entity arm, the Reader's knowledge lenses, and the
native graph, timeline and map views.

## Prior art (what we adopt)

- **The factoid model** (Prosopography of the Byzantine World, PASE): a factoid is one source's
  assertion about a person, kept apart from the person; every statement here is a factoid with
  its page and span. Adopted as is.
- **Record linkage practice** (Fellegi–Sunter, Splink, the Dutch and Norwegian census linking
  projects): candidate pairs from blocking keys, scored, decided by a person, decisions kept as
  labels. Adopted: proposals, never automatic merges; the rejected label trains the matcher.
- **Authority control** (VIAF, Wikidata, GeoNames, World Historical Gazetteer, Linked Places):
  a project's own list first, links proposed and confirmed (`project-gazetteer-and-names.md`).
- **Archival description** (ISAD(G) access points; EAD `controlaccess`): a folder's people,
  places and corporate bodies are its access points. Adopted: the folder's confirmed names ARE
  its access points; there is no second list.
- **Named-entity evaluation** (CoNLL exact-span F1; relation extraction precision and recall):
  the measure the bake-off uses before a model or prompt is adopted.
- **Network analysis for historians** (Six Degrees of Francis Bacon; nodegoat; Gephi): an edge
  made by a named rule, with its evidence, as of a date, confidence as a control. Adopted from
  `../explore/networks.md`.
- Deliberately not adopted: automatic merging on embedding similarity (what produced 1,493
  pending pairs in B12); an LLM writing prose from the graph (`kg.read.no-llm`); a second
  model-written list of names beside the graph (the catalogue's access points today).

## Words

- **Name** (entity): a person, place, organisation or event the pages name, with one preferred
  form and every form as written (`names`, `aliases`). Types: `person`, `location`,
  `organization`, `event`; `concept` only for a thing a project declares; a **date** is a value
  on a statement or a page, never an entity.
- **Mention**: one form on one stretch of one page's reading (anchored to the line, #5488).
- **Statement** (claim): subject, verb, object, each copied from the page, resting on its line,
  with a date and a place as values where the page gives them, and who made it.
- **Proposal**: a name, statement, merge or link a model or rule made; it stays a proposal until
  a person decides. **Decision**: verified, rejected, or merged, by a person, remembered.
- **Lens**: a scoped review list (a folder's people; a folder's places; one name's statements).

## Behaviors

### A. Extraction: which model, versioned, costed, never twice

- `kg.names.one-canonical-set` — **[PARTIAL]** (#6283, #6285; owner ruling 2026-10-29) a name
  may come from the tagger (spaCy, where it is good enough), from the model a person chose (such
  as Sonnet), or from a person; whatever made it, it is a PROPOSAL until it is resolved into the
  project's one canonical set of names by accept, merge or reject. There is one set: a superseded
  proposal (a draft name the model step or a person has since resolved on the same page) is
  resolved into its canonical entity or removed, never kept as parallel data; a tagger's draft
  never counts as done for a chosen model step; and a person's decision on any row stays
  whatever runs later. Built: the step, the import draft, `entity.take_back_run`, the merge and
  reject paths. Not built: the draft told apart from a canonical name by the done-check and the
  tables; its resolution when the model step writes the same page; the "no drafts left lying
  around" check (a names step ends with every proposal on its pages resolved or listed as to
  review).
- `kg.names.prompt-is-versioned` — **[GAP]** (#6278) the names prompt and the statements prompt
  are entries in the prompt registry (`llm/prompts.py`), with a version; a shipped version is
  never edited in place; every entity and claim a run writes records the prompt id and version
  beside provider, model and run in its attribution.
- `kg.names.never-twice` — **[GAP]** (#6127, #6278) a names or statements step never runs again
  on the same page with the same model and prompt version; the start plan counts such a page as
  done and says so, and a person who wants a rerun chooses a different model or version, or
  takes the earlier run back first.
- `kg.names.cost-shown-first` — **[PARTIAL]** (#6168) the step shows, before Start, the model,
  the pages it will read, and the estimated cost, as the reading step does; the Statements and
  Names paths pages offer the same local-or-cloud chooser as every model stage. Built: the
  plan's cost line; not built: the chooser on the two pages.
- `kg.names.types` — **[PARTIAL]** (#5546) the step asks for people, places, organisations and
  institutions (offices, courts, notaries, companies and parishes are organisations), and
  events; a date is returned as a value with the stretch it came from, never as a name; money
  and offices as typed values are the later work #5546 names. Built: the five sections, the
  date gate; not built: institution as a stated subtype, money.
- `kg.names.tagger-is-a-seed` — **[GAP]** (#5536, #5545; owner ruling 2026-10-29) the bundled
  Spanish tagger is assessed on the project's check set before it is offered as a names source;
  on B12 it is not good enough (the review, section 4.1: offices as people, given names as
  places, cut surnames, a hundred names a page), so by default it runs only as a free seed whose
  names are proposals into the canonical set and never the catalogue's names by themselves; a
  project where it measures well on the check set may choose it as the step's source; a tagger
  fine-tuned on the project's confirmed names (#5536) is measured the same way.
- `kg.names.gate` — **[OK]** a name saved is somebody or somewhere: a whole-name date or a bare
  role word is refused, a name is never trimmed, a role word never refuses a longer name
  (`svo_quality.usable_entity_name`; `source.job.find-names.not-a-date-or-a-role`). *Test:*
  `fichero-server/tests/unit/knowledge/test_name_quality.py`.
- `kg.names.says-who-made-it` — **[PARTIAL]** (#4869, #4868) every entity and claim names its
  maker in its attribution chain: a run (provider, model, prompt version, run id, time), the
  import draft (the tagger and pipeline, marked as draft), or a person (account and time); a
  machine row never defaults to `human` in `created_by`. Built for entities a run writes
  (`kg.entity.says-who-made-it` in `kg-tables.md`); not built: the draft's provider and model
  on the entity's entry, the claim's `created_by`.
- `kg.names.measured` — **[GAP]** (#5545, #5536) a project keeps a check set (about ten
  corrected pages with their names and statements confirmed) and the bake-off reports precision
  and recall for names, by type, and for statements, for each candidate model and prompt
  version, before one is adopted; the figures are shown on the step card and kept with the run.
  A project's confirmed names are the training set #5536 names.
- `kg.names.known-names-given` — **[GAP]** (#5725) the names and statements prompts for a
  folder are given the project's confirmed names and places (the authority list, section D),
  so a spelling already decided is written in that form and a new form is proposed as a form
  of the known name, not a new entity.

### B. Resolution and merge: proposals, per folder, never automatic

- `kg.resolve.exact-and-alias-only-at-write` — **[OK]** (#5409) a run adds a name to an
  existing entity only when it is the same name once case, accents, punctuation and spacing
  are set aside, or already one of that entity's forms; every merely similar name is a new
  entity (`kg.entity.models-propose-merges` in `kg-tables.md`). *Test:*
  `fichero-server/tests/unit/kg/test_models_propose_merges_to_spec.py`.
- `kg.resolve.no-write-time-embedding-pairs` — **[BROKEN]** (#6280, #4842) the writer no
  longer queues an embedding-cosine or `SequenceMatcher` pair for every new name: B12 holds
  1,493 pending pairs for 2,885 names, most of them two people of one surname or two events
  of one kind, and nobody can review that. The writer keeps the exact and alias matches; the
  similar-name pairs it queued are withdrawn by the system (never marked rejected); proposals
  come from the folder pass below.
- `kg.resolve.folder-pass` — **[GAP]** (#6280, #5107) after a names step on a folder (and on
  demand for any folder or box) a resolution pass over that scope proposes GROUPS of names that
  are likely one person, place or organisation, by evidence in this order: the same name
  written differently (`dedupe.spelling_key`: old spellings, marked abbreviations, titles), a
  shared surname with a given-name form of the same name (a short form, a double name with one
  part), and co-presence in the same folder as a tie-breaker; a group names its evidence and
  what accepting it joins (pages and statements). A pass proposes few: at most about one
  group for every ten names in the scope, ranked by how much they join, the rest listed as
  "similar, not proposed". A given-name gender variant or a father-and-son pair with the same
  surname is never proposed as one and is shown as "same family" instead
  (`_terminal_surname_diverges`).
- `kg.resolve.decision-remembered` — **[OK]** a person's accept is the audited merge, a
  reject is remembered and the pair is never proposed again, an absorbed name re-imported lands
  on the survivor, a split survives re-import, a delete or retype writes its rule
  (`kg-tables.md`: `kg.tables.entity-resolution-registry`, `kg.entity.variant-spellings-proposed`).
  *Tests:* `fichero-server/tests/unit/kg/test_variant_spellings_to_spec.py`,
  `fichero-server/tests/unit/workflows/test_entity_reject_survives_reimport.py`.
- `kg.resolve.person-wins` — **[GAP]** (#5416, #5072) where a model's proposal and a person's
  decision disagree, the person's stands: a model never changes `curation_state`, a reviewer
  model's verdict is recorded at its own trust level and never as a person's, a verified name's
  preferred form and type are never rewritten by a run, and a re-import that would contradict a
  decision writes a proposal beside it, never over it.
- `kg.resolve.merge-and-split-have-a-door` — **[GAP]** (#5110, #4828) merge, split and the
  review of proposals are reachable from the lens (section E) and the Inspector, with undo;
  the unmounted sheets are re-mounted there or retired, one path per verb.

### C. Statements: one of the names says or is said something, on its line

- `kg.statements.subject-is-a-page-name` — **[OK]** a statement's subject is one of the page's
  names, the agent of the verb, never a pronoun or a date; a dated statement with no subject
  goes to the one person or organisation named in its words; the page is read as running text
  and each statement rests on its line through the offset map
  (`source.job.find-statements.not-a-date-or-swapped`). *Tests:*
  `fichero-server/tests/unit/workflows/test_statements_dates_not_subjects.py`,
  `fichero-server/tests/unit/knowledge/test_name_quality.py`.
- `kg.statements.grounded` — **[OK]** the verb and object are spans on the page, the object
  at most 25 words, a place or date is kept only when the page states it
  (`svo_quality.claim_rejection`, `ungrounded_span`, `_date_is_on_the_page`). *Test:*
  `fichero-server/tests/unit/workflows/test_svo_write_quality.py`.
- `kg.statements.dates-are-values` — **[GAP]** (#5008, #4659, #5597) a date the dates pass
  finds is stored as a date on the page or on a statement (`date_values`, `time_start`), never as
  a claim whose subject slot holds the date; the timeline reads dates, the tables and the
  paragraph never show a date where a person should be; existing dated rows are converted by
  an audited, scan-first repair, never a batch rewrite. In B12's Sonnet folder 36 of 75 claims
  are such rows.
- `kg.statements.object-role` — **[GAP]** (#3808, #5541) a statement's object carries a role
  where the extraction knows it (patient, recipient, place, instrument), seeded from the
  language's dependency labels and the prompt's fields, so a renderer and a query can ask who
  received without re-parsing; coreference ("the said", honorifics, pronouns) is the
  `resolve-references` job #5541 names, between names and statements.
- `kg.statements.measured` — **[GAP]** (#5545, #5637) the bake-off compares the parser tier, a
  local model and a cloud model on the check set, precision and recall per statement, cost
  first; a prompt version is adopted only when it does not lose on the check set.
- `kg.statements.no-invented-english` — **[OK]** a name with no statement gets no English "is"
  on a page that is not English (`source.extract.no-english-verb-on-another-language`). *Test:*
  `fichero-server/tests/unit/workflows/test_svo_fallback.py`.
- `kg.statements.review` — **[PARTIAL]** (#4691, #4768, #5416) a statement is `unreviewed`,
  `shortlisted`, `curated` or `rejected`; a person curates from the Claims table and the lens,
  single or multi-select, the table filters by state, and a machine actor is refused by
  `claim.transition`. Built: the routes and batch routes; not built: the table's verbs and
  filter, the refusal.

### D. The attribute link: folder names become the catalogue

Builds on `../source/cataloguing.md` (`catalogue.folder-description-fields`,
`catalogue.fields-on-prototypes`) and on the attributes-and-prototypes spec being written in
parallel at `../source/attributes-and-prototypes.md` (on branch `spec/export-catalogue`; not
present at origin/integration when this was written, so its field names are to be aligned at
approval).

- `kg.attr.folder-names-are-attributes` — **[GAP]** (#6283, #5365, #6087; owner ruling
  2026-10-29) a folder carries three list attributes, `catalogue_people`, `catalogue_places` and
  `catalogue_institutions`, each entry the canonical name of an entity in the folder's scope; at
  `folder.promote_catalogue` the description's access points are TYPED BY THE GRAPH into the three,
  with no model call: each access point is matched to a canonical entity in the folder's scope
  (exact or same-name-written-alike, else a proposal into the canonical set, section A), takes
  that entity's type and canonical name, and an access point that matches nothing is kept in its
  list as a proposed name; the attributes are rewritten by the engine when a name's state, type
  or form changes in that scope; a person can add or remove an entry, which is a decision on the
  name. The free-text `catalogue_access_points` attribute is superseded by the three and retired
  by the promote migration.
- `kg.attr.entry-shows-state` — **[GAP]** (#6283) each entry in the folder's lists shows
  whether it is confirmed or proposed, how many pages name it in this folder, and opens the
  name's lens; the Excel and catalogue exports print confirmed entries, and proposed ones only
  when asked, marked.
- `kg.attr.authority-sheet` — **[GAP]** (#5380; owner ruling 2026-10-29) the authority sheets
  come from the catalogue rows: one sheet per distinct entry across the folders'
  `catalogue_people`, `catalogue_places` and `catalogue_institutions`, headed by the graph's
  canonical name, read from the entity: the canonical form and the rule that chose it, every form as written with
  its folders and pages, type, roles and dates as attested (from its statements), the folders
  where it is named, links to authorities (proposed, confirmed), and a quality line (forms
  unresolved, likely duplicates, no link). It is `project-gazetteer-and-names.md`'s entry; no
  new table, the entity with its mentions and statements is the record.
- `kg.attr.authority-sheet-export` — **[GAP]** (#5380, #5603) the sheets export as one row per
  name (CSV and Excel, the catalogue's authority sheets), as Linked Places for places, and in
  the RDF export with authority URIs; the export reads the same record the views do.
- `kg.attr.links-proposed-per-type` — **[GAP]** (#4758, #3528) Wikidata and GeoNames candidates
  are proposed for places, Wikidata and the project's own list for people and organisations,
  from the authority sheet, confirmed by a person, kept apart from what the pages say
  (`kg-enrichment.md`, `gazetteer.links-proposed-confirmed`).

### E. Review lenses

- `kg.lens.folder-names` — **[GAP]** (#4978, #2020, #4885) selecting a folder (or box, or
  project) and the Entities kind shows that scope's names in three lists, people, places and
  institutions, each row with its preferred form, forms as written, pages in this scope, state,
  maker, and a merge-proposal mark; sorted by pages then name; filtered by state and by
  "one-page, one-word" (the draft's noise); with confirm, reject, merge, retype and rename as
  the row verbs; one definition of "this folder's names" (`entities.document_entity_ids`,
  recursive by default).
- `kg.lens.proposals` — **[GAP]** (#6280, #5107) the scope's merge proposals appear as a
  worklist above the lists: each group with its evidence, what accepting joins, accept, reject,
  "same family"; an empty worklist says so; a proposal a person decided leaves the list and the
  count in the sidebar goes down.
- `kg.lens.one-name` — **[PARTIAL]** (#4838, #4802) selecting a name shows its authority sheet
  in the Reader and its curation in the Inspector (statements where it is subject or object with
  source click-through, forms, merge history, notes); built: the Inspector's entity arm and
  statements list; not built: the sheet in the Reader, the forms and history there.
- `kg.lens.statements-of-a-scope` — **[PARTIAL]** (#4886, #5010) the Claims pane below an
  Entities pane shows the selected name's statements, and with none selected every statement in
  the scope, with state, date, place, page, and the subject's name; built: master/detail; not
  built: curation verbs and the state filter in the table.
- `kg.lens.counts-in-the-sidebar` — **[GAP]** (#5413, #5508) the Entities row under a project
  shows confirmed / proposed / to review counts, and an empty knowledge row offers the names
  step that fills it.

### F. The graph views

- `kg.graph.edge-rule-is-named` — **[GAP]** (#5032, #5551) every edge a view or an analysis
  draws is made by a named rule with its evidence ids, from three rules shipped in this order:
  same case file (two names on pages of one folder; weight = distinct pages), same statement
  (subject and object of one claim; label = the verb), same date and place (co-presence in a
  dated or placed claim). The alias-scan `entity_ids` of a claim is never an edge.
- `kg.graph.measures-are-columns` — **[GAP]** (#5551, #5032) degree and betweenness within a
  scope (a folder, a box) are sortable columns of the folder lens, named by their rule
  ("named in the most case files"), computed on reviewed names by default with a control to
  include proposed ones; communities and paths are offered from one name ("how are these two
  connected"), each hop opening its evidence.
- `kg.graph.neighbourhood` — **[PARTIAL]** (#5551, #4605) the native force-directed view shows
  one name's or one folder's neighbourhood with an edge legend naming the rule, node colour by
  type, selection driving the Inspector, and the "as of" control shared with time and place
  views; built: the view on claim co-occurrence, 30 neighbours; not built: the rule, the legend,
  the time control.
- `kg.graph.export-first` — **[GAP]** (#5034) the network of any scope exports as GEXF and
  GraphML with the edge rule, weights, dates and evidence counts, before any further in-app
  drawing; the RDF export carries authorship (`kg-enrichment.md`, #4636).
- `kg.graph.timeline-and-map-read-values` — **[PARTIAL]** (#5008, #4600, #5037) the timeline
  and map read dates and places as values on statements and pages (section C), with a place's
  coordinates from the gazetteer link where one is confirmed; built: the views on the
  document's claims; not built: the value rule, coordinates, the library scope
  (`../explore/time.md`, `../explore/place.md`).
- `kg.graph.paragraph-from-reviewed` — **[PARTIAL]** (#4832, #4750) the readable paragraph
  renders from the engine's one renderer over a name's statements, marking proposed ones, with
  the date never as subject; built: the engine renderer; not built: the app calling it
  (`kg-readable-representation.md`).

### G. One source of truth: the record for each fact, and the copy it retires

The rule: a fact is written once, in its record; a copy is either derived from the record by the
engine on read (or on change, rebuildable) or retired. A migration is an audited, scan-first,
idempotent action that reads the copy, writes what the record lacks, and leaves the record's own
values alone; never a batch rewrite of a person's work.

| Fact | The record | Copies today | Migration |
|---|---|---|---|
| A name (person, place, organisation, event): preferred form, forms as written, type, state, maker | `KnowledgeEntity` (`names`, `curation_state`, `attribution_chain`) | the per-document `entities` artifact (`workflows/tools/entities.py`, `importers/manifest_import.py`) read by the app's `ArtifactEntityStore` for list rows and table cells; the folder's `catalogue_access_points` attribute (superseded by `catalogue_people`, `catalogue_places`, `catalogue_institutions`, typed by the graph at promote); the catalogue tool's people and places tables (`_build_data_from_claims`); `aliases` beside `names` | artifact names become page-scoped entities through `upsert_entity`, then the artifact and the app store go; access points become proposals (section D); the catalogue tables read `document_entity_ids`; `aliases` derived from `names` |
| A name's tie to a page: which stretch of which line | the mention: `source_supports` entry with its `source_anchor` on the segment (#5488) | `source_document_ids` on the entity; the alias scan's `entity_ids` on every claim; `pages_with_names` reading `source_document_ids` for the done-check | `source_document_ids` derived from the mentions (kept as a column only as a cache the engine fills); `entity_ids` recomputed as the names whose mention lies in the claim's span; the done-check reads mentions by run |
| A statement: subject, verb, object, line, maker | `KnowledgeClaim` (`subject_entity_id`, the role ids, `source_segment_id`, span) | the dated rows with the date as subject; the `claim_text_en` glosses; the parser's English "is" rows | dates become values (section C); glosses stay display-only; English rows pruned by the standing rule |
| A date | on the page (`document_date`) or on the statement (`date_values`, `time_start`) | the `dates` artifact (`workflows/tools/date_extract.py`); `catalogue_dates`, `catalogue_date_start`, `catalogue_date_end`, `catalogue_date_normalised` on the folder | the artifact derived or retired (#5597); the folder's date attributes derived from its pages' and statements' dates by `folder.promote_catalogue`, a person's value kept |
| A place's coordinates and gazetteer identity | the location entity's `place_values` (`EvidentialPlace`) and its authority link | `claim_location`, `claim_geo`, `place_values` on claims; the geocode cache in `media/geo.py` | claims point at the place entity; their place fields derived; the cache stays a cache |
| Who made a row | `attribution_chain` on entity and claim | `created_by`, `provider`, `model` columns; the draft marked only by the claim's provider | the columns derived from the chain; the draft's entry carries provider and model (#4869) |
| The project's known names | verified entities | `recipes/known_names.py` (reads them, correct); the catalogue's description prose | nothing to retire; the prose reads the record |
| Derived stores: entity vectors (LanceDB), the triple file for SPARQL, the networkx graph cache, triangulation counts, PyKEEN predictions | the two tables | the stores themselves | rebuildable from the tables (`/api/kg/rebuild`); re-derived when a page's text or a name's state changes (#5361) |
| In the app | `EntityStore`, `ClaimStore` | `ArtifactEntityStore`, `LibraryClaimsModel`, the Inspector's own fetches (#3186) | the two stores are the only holders; the rest retire |

- `kg.one.entity-is-the-record` — **[GAP]** (#5597, #5603) the `KnowledgeEntity` row is the one
  record for a name; every surface named in the intent reads it through the entity routes, and
  no other table, artifact, attribute or app store holds a list of names of its own.
- `kg.one.entities-artifact-retired` — **[GAP]** (#5597, #3861) the per-document `entities`
  artifact and the app's `ArtifactEntityStore` previews are replaced by page-scoped entities
  (`document_entity_ids`): the Entity Extraction tool and the manifest importer write through
  `upsert_entity` with a page scope, the list rows and table cells read the entity routes, and a
  migration turns each existing artifact's names into scoped entities once, then retires it.
- `kg.one.mention-is-the-link` — **[GAP]** (#5488, #4932, #1562) a name's tie to a page is one
  record, the mention on a segment stretch; `source_document_ids` is derived from the mentions;
  a claim's `entity_ids` is the names whose mention lies within the claim's span, computed by
  the engine, never the alias scan; the done-check counts pages by the mentions a run wrote.
- `kg.one.names-not-aliases` — **[GAP]** (#1688) `names` (each form with language and script)
  is the record of a name's forms; `aliases` is derived from it until it is dropped; adding or
  removing a form is one audited action on `names`.
- `kg.one.dates-one-home` — **[GAP]** (#5597, #5008) a date lives on the page or on the
  statement; the `dates` artifact and the folder's `catalogue_date_*` attributes are derived
  from those (promote reads the record, a person's value is kept), never a third copy.
- `kg.one.places-one-home` — **[GAP]** (#5597, #4600) a place's coordinates and gazetteer
  identity live on the location entity; a claim's place fields point at that entity and derive
  from it.
- `kg.one.catalogue-reads-the-record` — **[GAP]** (#5365, #6283) the catalogue tool's people,
  places, organisations and dates tables, the folder's three list attributes and the authority
  sheets are read from the entity and claim records through one scope function, never from a
  model's answer kept beside them.
- `kg.one.derived-stores-follow-the-record` — **[PARTIAL]** (#5361) the vector store, the
  triple file, the graph cache and the triangulation counts are derived and rebuildable from the
  two tables; built: the rebuild route; not built: re-derivation when a page's corrected text,
  a merge or a decision changes what they were built from.
- `kg.one.app-has-two-stores` — **[PARTIAL]** (#4984, #3186) `EntityStore` and `ClaimStore`
  are the app's only holders of names and statements; built: the stores; not built: the
  Claims table and the Inspector's knowledge section reading them, the artifact store retired.

## Build order

### Stage 1 — Names a person can review (engine first)

#### Step 1.1 — Versioned prompts and the no-rerun rule (#6278, #6127)
- Behaviours: `kg.names.prompt-is-versioned`, `kg.names.never-twice`
- Tests: fichero-server/tests/unit/llm/test_names_statements_prompts_versioned.py, fichero-server/tests/unit/recipes/test_names_never_twice_same_model_and_prompt.py
- Size: S

#### Step 1.2 — One canonical set: a draft is a proposal, resolved, never left beside (#6285, #4869)
- Behaviours: `kg.names.one-canonical-set`, `kg.names.says-who-made-it`
- Tests: fichero-server/tests/unit/recipes/test_draft_never_counts_as_done.py, fichero-server/tests/unit/kg/test_draft_taken_back_when_model_writes_page.py, fichero-server/tests/unit/kg/test_entity_says_who_made_it_to_spec.py
- Depends on: 1.1
- Size: M

#### Step 1.3 — The folder lens route (#4978, #2020)
- Behaviours: `kg.lens.folder-names`, `kg.lens.statements-of-a-scope`
- Tests: fichero-server/tests/unit/api/test_folder_names_lens_route.py, fichero-server/tests/unit/api/test_entity_scope_leaks_and_page_links.py
- Depends on: 1.2
- Size: M

#### Step 1.4 — The check set and the measured step (#5545)
- Behaviours: `kg.names.measured`, `kg.names.cost-shown-first`, `kg.names.tagger-is-a-seed`
- Tests: fichero-server/tests/unit/recipes/test_names_check_set_precision_recall.py, fichero-server/tests/unit/recipes/test_names_paths_offer_the_chooser.py
- Depends on: 1.1
- Size: M

#### Step 1.5 — The mention is the link; entity_ids and source pages derived (#5488, #1562)
- Behaviours: `kg.one.mention-is-the-link`, `kg.one.names-not-aliases`
- Tests: fichero-server/tests/unit/kg/test_mention_is_the_one_link.py, fichero-server/tests/unit/kg/test_entity_ids_from_mentions_not_alias_scan.py, fichero-server/tests/unit/kg/test_names_field_is_the_record.py
- Depends on: 1.2
- Size: M

### Stage 2 — Resolution as proposals, per folder

#### Step 2.1 — Stop write-time similarity pairs; withdraw the old queue (#6280, #4842)
- Behaviours: `kg.resolve.no-write-time-embedding-pairs`
- Tests: fichero-server/tests/unit/kg/test_writer_queues_no_similarity_pairs.py, fichero-server/tests/unit/kg/test_old_similarity_pairs_withdrawn_not_rejected.py
- Size: S

#### Step 2.2 — The folder resolution pass (#6280, #5107)
- Behaviours: `kg.resolve.folder-pass`, `kg.resolve.person-wins`
- Tests: fichero-server/tests/unit/kg/test_folder_resolution_pass_proposes_groups.py, fichero-server/tests/unit/kg/test_person_decision_wins_over_a_run.py
- Depends on: 2.1
- Size: M

#### Step 2.3 — Proposals, merge and split in the lens (#5110, #4828)
- Behaviours: `kg.lens.proposals`, `kg.resolve.merge-and-split-have-a-door`, `kg.lens.counts-in-the-sidebar`
- Tests: fichero/Tests/Unit/general/Views/Library/FolderNamesLensTests.swift, fichero/Tests/Unit/general/Views/Library/MergeProposalWorklistTests.swift
- Depends on: 2.2, 1.3
- Size: M

#### Step 2.4 — Known names given to the prompts (#5725)
- Behaviours: `kg.names.known-names-given`
- Tests: fichero-server/tests/unit/workflows/test_names_prompt_carries_known_names.py
- Depends on: 2.2
- Size: S

### Stage 3 — The attribute link to the catalogue

#### Step 3.1 — Folder people, places and institutions as attributes (#6283, #5365)
- Behaviours: `kg.attr.folder-names-are-attributes`, `kg.attr.entry-shows-state`
- Tests: fichero-server/tests/unit/kg/test_folder_names_become_attributes.py, fichero-server/tests/unit/recipes/test_access_points_read_as_proposed_names.py, fichero-server/tests/unit/api/test_routes_export.py
- Depends on: 2.2
- Size: M

#### Step 3.2 — The authority sheet and its export (#5380, #5603)
- Behaviours: `kg.attr.authority-sheet`, `kg.attr.authority-sheet-export`, `kg.lens.one-name`
- Tests: fichero-server/tests/unit/api/test_authority_sheet_route.py, fichero-server/tests/unit/api/test_authority_sheet_export_rows.py, fichero/Tests/Unit/general/Views/Reader/AuthoritySheetInReaderTests.swift
- Depends on: 3.1
- Size: M

#### Step 3.3 — Links proposed per type (#4758, #3528)
- Behaviours: `kg.attr.links-proposed-per-type`
- Tests: fichero-server/tests/unit/kg/test_authority_links_proposed_per_type.py
- Depends on: 3.2
- Size: S

#### Step 3.4 — Every name list reads the record: catalogue tables, entities artifact, app stores (#5597, #3861, #5365)
- Behaviours: `kg.one.entity-is-the-record`, `kg.one.entities-artifact-retired`, `kg.one.catalogue-reads-the-record`, `kg.one.app-has-two-stores`
- Tests: fichero-server/tests/unit/kg/test_entities_artifact_migrates_to_scoped_entities.py, fichero-server/tests/unit/workflows/test_catalogue_tables_read_the_entity_record.py, fichero/Tests/Unit/general/Models/EntityStoreIsTheOnlyNameHolderTests.swift
- Depends on: 3.1, 1.5
- Size: M

### Stage 4 — Statements worth reading

#### Step 4.1 — Dates are values, never subjects (#5008, #4659)
- Behaviours: `kg.statements.dates-are-values`
- Tests: fichero-server/tests/unit/workflows/test_dates_stored_as_values_not_claims.py, fichero-server/tests/unit/kg/test_dated_rows_repair_is_scan_first.py
- Size: M

#### Step 4.2 — Curation from the Claims table and the lens (#4691, #4768, #5416)
- Behaviours: `kg.statements.review`
- Tests: fichero-server/tests/unit/api/test_claim_transition_refuses_a_machine_actor.py, fichero/Tests/Unit/general/Views/Library/ClaimsTableCurationTests.swift
- Depends on: 4.1
- Size: S

#### Step 4.3 — Measured statements; object roles (#5545, #5637, #3808)
- Behaviours: `kg.statements.measured`, `kg.statements.object-role`, `kg.names.types`
- Tests: fichero-server/tests/unit/recipes/test_statements_bakeoff_precision_recall.py, fichero-server/tests/unit/knowledge/test_object_role_from_parse.py
- Depends on: 1.4
- Size: M

#### Step 4.4 — Dates and places have one home; derived stores follow (#5597, #4600, #5361)
- Behaviours: `kg.one.dates-one-home`, `kg.one.places-one-home`, `kg.one.derived-stores-follow-the-record`
- Tests: fichero-server/tests/unit/kg/test_dates_artifact_and_catalogue_dates_derive_from_the_record.py, fichero-server/tests/unit/kg/test_claim_place_points_at_the_place_entity.py, fichero-server/tests/unit/kg/test_derived_stores_rederive_on_change.py
- Depends on: 4.1
- Size: M

### Stage 5 — Graph views on reviewed names

#### Step 5.1 — Named edge rules with evidence; GEXF and GraphML out (#5032, #5034)
- Behaviours: `kg.graph.edge-rule-is-named`, `kg.graph.export-first`
- Tests: fichero-server/tests/unit/kg/test_edge_rules_carry_evidence.py, fichero-server/tests/unit/kg/test_gexf_graphml_export_opens_in_a_parser.py
- Size: M

#### Step 5.2 — Measures as lens columns; the neighbourhood with a legend (#5551, #4605)
- Behaviours: `kg.graph.measures-are-columns`, `kg.graph.neighbourhood`
- Tests: fichero-server/tests/unit/kg/test_scope_measures_named_by_rule.py, fichero/Tests/Unit/general/Views/Library/GraphEdgeLegendTests.swift
- Depends on: 5.1, 2.3
- Size: M

#### Step 5.3 — Timeline, map and paragraph read the reviewed values (#5037, #4600, #4832)
- Behaviours: `kg.graph.timeline-and-map-read-values`, `kg.graph.paragraph-from-reviewed`
- Tests: fichero-server/tests/unit/kg/test_timeline_map_rows_from_values.py, fichero/Tests/Unit/general/Views/Inspector/ParagraphUsesEngineRendererTests.swift
- Depends on: 4.1, 3.3
- Size: M

## Test matrix (legs this surface touches)

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | yes | lens sorting and filters; proposal worklist order; edge legend mapping | `fichero/Tests/Unit/general/Views/Library/` |
| Availability (Swift) | yes | confirm/reject/merge/split reachable from the lens and the Inspector | same |
| Visual / A11y | yes | the lens and the sheet pass `performAccessibilityAudit()` | `fichero/Tests/UI/` |
| Backend (pytest) | yes | every behaviour above: the gates, the pass, the attributes, the sheet, the edges, the exports | `fichero-server/tests/unit/kg/`, `fichero-server/tests/unit/api/`, `fichero-server/tests/unit/recipes/` |
| MCP | yes | lens, proposals, accept/reject, authority sheet, export reachable by an agent | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | yes | the same, scriptable (a box's names as CSV) | `fichero-cli/tests/` |
| Click-around (Mac) | yes | select a folder, see its names; choose a name, see its sheet and its page | `fichero/Tests/UI/` |
| iPhone / iPad | later | read-only lens and sheet | — |
| Load | yes | a box of 100 folders and 20,000 names: the lens pages, the pass is bounded, no peg (#5261) | `fichero-server/tests/perf/` |

Fixtures: ten corrected B12 pages (names and statements confirmed by the owner) as the check
set; the B12 one-folder Sonnet run as the before picture; a synthetic box for load.

## Open questions for the owner (at most eight, each with a recommendation)

1. **Answered** (owner 2026-10-29): the access points are typed by the graph into the three
   attributes at promote; the free-text list is superseded. Still open for the per-document
   `entities` artifact: retire it after a one-time migration into page-scoped proposals?
   Recommendation: yes.
2. **Which names count for the catalogue by default: confirmed only, or confirmed plus
   unrejected proposals marked as proposed?** Recommendation: confirmed plus proposed, marked,
   for the working catalogue; confirmed only in anything exported or published.
3. **Answered** (owner 2026-10-29): a draft never counts as done; the chosen model step runs
   on its pages and the draft's names are resolved into the canonical set, not left beside it.
4. **The per-folder proposal budget.** Recommendation: about one group per ten names, ranked
   by what it joins, the rest visible under "similar, not proposed"; a person can ask for more.
5. **Given-name gender variants and father-and-son pairs (#6280):** never proposed as one?
   Recommendation: never automatically; shown as "same family" with a one-click merge a person
   can still make.
6. **Where a dated row with no actor lives:** a date on the page, or a statement with an empty
   subject? Recommendation: a date value on the page (and on the one claim it belongs to when
   there is one); the timeline reads page dates; no subject-less claims.
7. **A reviewer model for names and statements (a cheap second model confirming a first)?**
   Recommendation: allowed as a proposal at its own trust level, shown as such, never counted as
   a person's decision; measured on the check set before it is offered.
8. **Authorities on by default:** Recommendation: Wikidata and GeoNames for places, Wikidata and
   the project's list for people and organisations; others per project, as
   `project-gazetteer-and-names.md` already recommends.

## Rulings

**Owner, 2026-10-29** (relayed; decided):
- Names may come from the tagger where it is good enough, from the chosen model, or from a person.
- A person edits them into ONE canonical set. Every draft, from any source, is a proposal resolved
  into the canonical entities by accept, merge or reject; a superseded draft does not persist as
  parallel data (`kg.names.one-canonical-set`).
- The bundled Spanish tagger is assessed for this archive; on B12 it is very noisy and belongs, by
  default, as a free seed or proposal only (`kg.names.tagger-is-a-seed`).
- At promote, the catalogue's access points are typed by the graph into `catalogue_people`,
  `catalogue_places` and `catalogue_institutions`, with no model call
  (`kg.attr.folder-names-are-attributes`).
- The authority sheets come from the catalogue rows, with the graph's canonical name
  (`kg.attr.authority-sheet`). The export spec being written on `spec/export-catalogue` points here
  for the canonical-names design.

## Future (ideas, not scheduled)

- Relation extraction trained on corrected statements (#5637's last clause).
- A whole-project network in an HTML view mode once the GEXF route has been used in practice
  (`../explore/networks.md`).
- CIDOC-CRM and Linked Art profiles for the export (#1678, #4826).
- Fine-tuning the Spanish tagger on confirmed names (#5536).
