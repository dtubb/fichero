# KG Paragraph Realisation — how a name's statements become a paragraph a person can read — Design Spec (#4750, #4832)

> Milestone: kg-readable-representation
> Manual: TBD — the knowledge-graph part of the user manual needs one section, "Reading a name's
> paragraph": what the paragraph says and does not say, how a date, a place and a doubt read,
> why a sentence is never edited as prose, and how a click reaches the statement and its page.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-11-21), written from a review of the
> graph-to-text literature, a reading of the engine's renderer, and a measured run of that
> renderer and of a scratch prototype on a synthetic evaluation set (figures in "Measured").
> This spec owns ONE thing: the engine's pipeline from a name's statements to a paragraph, stage
> by stage, with its output shape, its rules for dates, places and doubt, its evaluation set and
> its build order. It is the buildable companion of `kg-readable-representation.md`, which keeps
> the four rulings of 2026-09-18, the three of 2026-09-12, the claim editor, the source reveal
> and the Reader pane, and it never restates them. Confidence, basis and bands are
> `kg-confidence-and-provenance.md`; how a date and a place look on other surfaces is
> `kg-rendering.md`; the statements themselves are `kg-entities-and-statements.md`.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built · **[BROKEN]** code contradicts the line.
> `→ #N` names the issue filed for the line from this review (listed at the end); the plain
> number beside it is the older open issue that also tracks it.

## Intent (the design)

A name's paragraph is a rendering of the statements held about it, and of nothing else. A
researcher reading it should be able to tell, for every clause: which statement it states,
when and where at the precision the source gave, how many sources say so, whether a person has
checked it, and whether two sources disagree. Every clause opens its statement and its page.

The paragraph is written by rules and tables, never by a language model. The reason is
measured in the literature and is not a matter of taste: a rule realiser cannot say what is
not in its input, so every word can be traced; a model writes more fluently and cannot give
that guarantee (see "Prior art"). Fluency is earned the way the older systems earned it: by
ordering, by joining what belongs together, by not repeating the name, and by saying dates and
places as a person would.

The rulings kept, from `kg-readable-representation.md`: the unit of editing is the statement,
never the prose; sentences are re-centred on the page's name through a per-verb inverse
phrasing, and a verb with no inverse keeps its true subject; the paragraph lives in the Reader;
each sentence is in its source's language; ordering is by time unless the reader chooses by
source; doubt reads as words and as how many sources agree, never as a bare number.

## Measured (2026-11-21, a synthetic evaluation set, no archive data)

One invented person with 21 statements, shaped like the engine's rows: day, month, year, span,
"about" and "on or after" dates; places on the statement and inside the object; the person as
object of four statements; one statement from two sources; two sources that disagree; one
statement a person rejected; one only mentioning the person; one tentative; one with no
language; Spanish and English. The engine's `render_entry` and a scratch prototype of this
spec were run on it. The app's own loop (`EntityDigestContent.biographySentences`) prints
subject, verb and object per statement and adds nothing `render_entry` lacks.

| Measure | `render_entry` today | Prototype, no gender known | Prototype, gender known |
|---|---|---|---|
| Sentences / words | 18 / 140 | 15 / 178 | 15 / 174 |
| Statements a person rejected, stated as fact (of 1) | 1 | 0 | 0 |
| Mention-only statements inside the paragraph (of 1) | 1 | 0 | 0 |
| Dated statements whose date is stated (of 18) | 0 | 18 | 18 |
| Places not already in the object, stated (of 6) | 0 | 5 (the sixth shares its sentence's place) | 5 |
| Statements needing a doubt, dispute or inferred mark that carry one (of 5) | 0 | 5 | 5 |
| Person as object, made the subject (of 4) | 0 | 1 | 3 |
| False subjects | 0 | 0 | 0 |
| Statements whose own words sit in a clause naming only that statement (of 19) | 16 | 19 | 19 |
| Letters and digits traced to a statement field, a name or a table entry | not recorded | 820 of 820 | 795 of 795 |
| Full canonical name printed | 17 times | 2 | 2 |
| The same sentence printed twice | 1 | 0 | 0 |
| Doubled or uncontracted prepositions ("at at", "de el") | 2 | 0 | 0 |

What the renderer does today, checked in the code:

- It never reads a date except to sort (`_entry_sort_key`,
  `fichero-server/src/fichero_server/knowledge/readable.py`), never reads `time_precision`,
  `date_values[].circa`, `open_start`, `open_end` or `basis`, and never prints a place:
  `_render_group_sentence` joins subject, verb and objects only. The place glue lives in
  `render_aggregation`, which the entry path does not call.
- It reads neither `curation_state` nor `epistemic_status` nor `merged_into_id`, so a rejected
  statement is printed as fact; it reads no confidence, basis, support count or `contradicts`
  link, so two sources that disagree print the same sentence twice.
- It prints the statement's stored subject in full in every sentence; `referring_expression`
  exists and nothing calls it.
- The doubled-preposition fix (#5008) is in `render_aggregation` only, so the entry path still
  prints "arrived at at"; no Spanish contraction is made ("fue testigo de el testamento").
- A merged sentence lists objects and drops each one's date and place, and its claim ids are
  per sentence, so a click cannot tell which object belongs to which statement.

## Prior art (what we adopt)

- **The pipeline.** Reiter and Dale, [Building applied natural language generation
  systems](https://doi.org/10.1017/S1351324997001502) (Natural Language Engineering, 1997):
  content determination, document structuring, aggregation, lexicalisation, referring
  expressions, realisation. Castro Ferreira and others,
  [a comparison between pipeline and end-to-end architectures](https://aclanthology.org/D19-1052/)
  (EMNLP-IJCNLP 2019), found the explicit stages gave better text than end-to-end models and
  generalised better to unseen inputs. Moryossef, Goldberg and Dagan,
  [Step-by-Step](https://aclanthology.org/N19-1236/) (NAACL 2019), and Puduppully and Lapata,
  [macro planning](https://aclanthology.org/2021.tacl-1.31/) (TACL 2021), make the same case
  for a symbolic plan in front of any realiser. Adopted: a plan (ordered units, each naming its
  statements) is a separate, testable value before any words exist.
- **Why not a model.** Wiseman, Shieber and Rush,
  [Challenges in data-to-document generation](https://aclanthology.org/D17-1239/) (EMNLP 2017),
  showed neural generators fluent and unfaithful. On WebNLG-style triples, Kasner and Dušek,
  [Beyond traditional benchmarks](https://aclanthology.org/2024.acl-long.651/) (ACL 2024),
  report that more than 80 per cent of the outputs of open models (Llama 2, Mistral, Zephyr)
  held at least one semantic error. The checks built to catch this (PARENT,
  [Dhingra and others 2019](https://aclanthology.org/P19-1483/); entailment,
  [Dušek and Kasner 2020](https://aclanthology.org/2020.inlg-1.19/); question answering,
  [Rebuffel and others 2021](https://aclanthology.org/2021.emnlp-main.633/)) are themselves
  models and themselves err. A realiser that fills slots from the data needs none of them:
  its faithfulness is a property a unit test can assert. Adopted: rules and tables; the
  faithfulness check is an exact one (`kg.para.every-character-has-an-origin`).
- **Templates per predicate.** The WebNLG tasks
  ([Gardent and others 2017](https://aclanthology.org/P17-1017/)) have a closed set of
  predicates, and Kasner and Dušek,
  [Neural pipeline for zero-shot data-to-text generation](https://aclanthology.org/2022.acl-long.271/)
  (ACL 2022), write one template per predicate and leave only ordering, joining and smoothing
  to a model. Fichero's verbs are the source's own words and are open; so the claim's verb is
  kept as written, and a table entry exists only where a verb is inverted.
- **Referring to the same person.** Dale and Reiter,
  [the Gricean maxims in referring expressions](https://arxiv.org/abs/cmp-lg/9504020)
  (Cognitive Science, 1995), and Grosz, Joshi and Weinstein,
  [Centering](https://aclanthology.org/J95-2003/) (Computational Linguistics, 1995): name in
  full once, shorter while the person stays the centre, in full again after another person has
  been the subject. Adopted, with the rule that a short form must be one the sources attest.
- **How historians write an assertion.** Bradley and Short, "Texts into databases: the evolving
  field of new-style prosopography" (Literary and Linguistic Computing 20, 2005), and Pasin and
  Bradley, [Factoid-based prosopography and computer ontologies](https://doi.org/10.1093/llc/fqt037)
  (Digital Scholarship in the Humanities, 2015): the record is what a source says, not what is
  so. [CIDOC CRM](https://cidoc-crm.org) (ISO 21127) holds the same as events with actors, a
  time-span and a place. Adopted: doubt is said as attribution ("one source only", "according
  to one source … according to another"), not as a probability word laid over a fact.
- **Dates.** The [Extended Date/Time Format](https://www.loc.gov/standards/datetime/)
  (ISO 8601-2:2019) names the levels a date is known at: day, month, year, approximate,
  uncertain, open interval. Adopted as the levels a date is read at (table below).
- **Many languages, later.** Grammatical Framework (Ranta,
  [2004](https://doi.org/10.1017/S0956796803004738)) and Abstract Wikipedia (Vrandečić,
  [Building a multilingual Wikipedia](https://doi.org/10.1145/3425778), CACM 2021) realise one
  language-neutral structure in many languages with agreement done by grammar. Dannélls and
  others, [Multilingual access to cultural heritage content](https://aclanthology.org/W13-2715/)
  (LaTeCH 2013), did it for museum records. Adopted now: the plan is language-neutral, so a
  grammar can replace a table later without touching the stages before it. Not adopted now: a
  grammar; the rulings ask for the source language only.

## Words

- **Statement**: a `KnowledgeClaim` row. **Page name**: the entity the paragraph is about.
- **Role**: what the page name is in a statement: `subject` (its `subject_entity_id`),
  `object` (one of its names is a whole word of the object), else `mention`.
- **Unit**: one thing to say: one statement, or several that say the same thing.
- **Clause**: the stretch of a sentence that states one unit. **Segment**: a run of characters
  in a clause with one origin: a statement's field, a name, or a table entry.
- **Table**: a language's data: joining words, date patterns, doubt words, prepositions,
  contractions, inverse frames. Adding a language is adding a table.
- **Frame**: a table entry that states a verb from its object's side, with a slot for the
  agent and, where the verb takes one, a slot for what is left of the object.

## The pipeline

Seven stages, each a pure function with its own tests. The first five produce the **plan** and
no words; only the last two read a language's table.

| Stage | Takes | Gives | Today |
|---|---|---|---|
| 1 Select | the name, its statements | statements to say, each with its role; the mention list | role built; no filter |
| 2 Unite | selected statements, `contradicts` links | units: same statement from several sources; one passage's two halves; a dispute | objects merged; nothing else |
| 3 Order | units | units by time (or by source), undated last | built by time only |
| 4 Group | ordered units | sentences: a run of one verb joins; everything else stands alone | merges across the whole list |
| 5 Qualify | each unit | its date, place, state, doubt as values, with their basis | not built |
| 6 Word | the plan, the table | clauses: the name or its short form, the verb or its frame, the object, the qualifiers | subject + verb + object |
| 7 Trace | clauses | the paragraph, sentences, clauses and segments with offsets and origins | per sentence only |

### The output

`GET /api/kg/entities/{id}/readable` keeps its fields and gains the ones in bold.

- `paragraph`, `sentences[]`: `text`, `start`, `end`, `language`, `claim_ids`, `role`, `revoiced`.
- **`sentences[].clauses[]`**: `start`, `end` (into the paragraph), `claim_ids`, `role`,
  `revoiced`, `state` (`proposed`, `reviewed`), `doubt` (`none`, `one_source_unsure`,
  `disputed`), `sources` (a count of distinct documents), `date` (`text`, `level`, `basis`,
  `as_written`) and `place` (`text`, `entity_id`, `basis`), each null when absent.
- **`sentences[].segments[]`**: `start`, `end`, `origin`, `claim_ids`. An origin is one of
  `claim:<id>:<field>`, `entity:<id>`, `table:<language>:<key>`, `punctuation`.
- **`also_mentioned_in[]`**: `claim_id`, `text`, `document_id`, for the mention list.
- **`ordering`** (a query value, `time` or `source`), echoed in the answer.

## Behaviors

Each line's test is named and is to be written red, from the line's words, before the change.
They go in `test_paragraph_*.py` files beside
`fichero-server/tests/unit/knowledge/test_readable_representation.py`.

### A. What is said

- `kg.para.rejected-never-stated` — **[OK]** (#4647, → #6835) a statement a person rejected
  (`curation_state` or `epistemic_status` is `rejected`) or that was merged into another
  (`merged_into_id`) is in no sentence and no list. Before this, `render_entry` read none of the
  three and printed the rejected statement of the evaluation set as fact. Tests:
  `test_a_rejected_or_merged_statement_is_never_stated` (through the route) and
  `test_a_statement_is_withdrawn_when_rejected_or_merged` in
  `fichero-server/tests/unit/knowledge/test_paragraph_selection.py`.
- `kg.para.mentions-are-a-list` — **[OK]** (#4647, → #6835) a statement in which the page
  name is neither subject nor object is not in the paragraph; it is in `also_mentioned_in`
  (`claim_id`, `text`, `document_id`), in the paragraph's order. Test:
  `test_a_mention_is_listed_not_narrated` in
  `fichero-server/tests/unit/knowledge/test_paragraph_selection.py`.
- `kg.para.proposed-is-marked` — **[OK]** (#4750, → #6836) each clause says whether a person
  has reviewed its statement: `state` is `reviewed` when every statement of the clause is
  curated or confirmed, else `proposed`. The app draws the one mark `kg-rendering.md` names;
  the paragraph's words do not change. Test: `test_a_clause_says_proposed_or_reviewed` in
  `fichero-server/tests/unit/knowledge/test_paragraph_trace.py`.
- `kg.para.every-statement-is-said-once` — **[OK]** (#4750, → #6836) every selected
  statement's id is in exactly one clause, and no clause is without one. Built: every sentence
  carries its ids
  (`fichero-server/tests/unit/knowledge/test_readable_representation.py::test_render_entry_every_sentence_carries_its_claim_id`).
  Built: clauses. Test: `test_every_selected_statement_is_in_exactly_one_clause` in
  `fichero-server/tests/unit/knowledge/test_paragraph_trace.py`.

### B. Every clause keeps its statement

- `kg.para.clause-carries-claim-ids` — **[OK]** (#4841, → #6836) a sentence that states more
  than one unit has one clause per unit, each with its own offsets and its own statement ids, so
  a click on "the sale of a farm" in a joined sentence opens that statement and no other. A
  word that joins clauses (a conjunction, a shared date) belongs to the sentence and names
  every statement it joins. Tests: `test_a_joined_sentence_has_one_clause_per_unit` in
  `fichero-server/tests/unit/knowledge/test_paragraph_trace.py` and
  `test_the_route_returns_clauses_and_segments_that_slice_the_paragraph` in `fichero-server/tests/unit/api/test_routes_kg_paragraph_clauses.py`.
- `kg.para.every-character-has-an-origin` — **[PARTIAL]** (#4841, → #6836) every letter and digit
  of the paragraph lies in a segment whose origin is a field of one of the clause's own
  statements, a name of an entity one of them links, or an entry of the sentence language's
  table; `paragraph[start:end]` of a `claim:` segment is a substring of that field as stored,
  but for the first letter's case and a contraction the table lists. This is the exact form of
  `kg.read.vocabulary-closure`. Built: segments name a claim field, a table word or punctuation. Not built: an entity name as an
  origin, the first-letter case and contraction exceptions. Test: `test_every_character_traces_to_its_origin` in
  `fichero-server/tests/unit/knowledge/test_paragraph_trace.py`.
- `kg.para.deterministic` — **[OK]** (#4652, → #6836) the same statements give the same
  bytes whatever order the store returns them in, and no model is called. Built: a full sort
  key and a pure function
  (`fichero-server/tests/unit/knowledge/test_readable_representation.py::test_render_entry_ordering_is_stable_across_repeated_calls`).
  Built: a test that shuffles the input and one that fails if the network is opened. Tests:
  `test_shuffled_input_gives_the_same_paragraph`, `test_no_model_is_called` in `fichero-server/tests/unit/knowledge/test_paragraph_trace.py`.
- `kg.para.edit-re-renders-the-clause` — **[GAP]** (#4833, → #6836) correcting a statement
  changes the text of its clause and of no clause that does not share a sentence with it; the
  editor is given the statement, never the sentence's text, and nothing accepts edited prose.
  Test (to write): `test_patching_one_statement_changes_only_its_sentence`.

### C. When

A date is read from the statement's point in time (`time_start`, `time_end`,
`time_precision`), else from its first date value (`date_values`), and is said at the level
held, never finer. A statement with no stored level is said to the year.

| Level held | Spanish | English |
|---|---|---|
| day | el 14 de marzo de 1702 | on 14 March 1702 |
| month | en junio de 1731 | in June 1731 |
| year | en 1733 | in 1733 |
| a span of years | de 1746 a 1749 | from 1746 to 1749 |
| about (`circa`) | hacia 1738 | about 1738 |
| on or after (`open_end`) | en 1751 o después | in or after 1751 |
| on or before (`open_start`) | en 1751 o antes | in or before 1751 |
| worked out, not read (`basis` inferred) | the date, then "(fecha inferida)" | the date, then "(date inferred)" |
| none | under "Sin fecha conocida:" at the end | under "Undated:" at the end |

- `kg.para.date-at-stored-level` — **[PARTIAL]** (#6773, → #6837) every dated statement's clause
  states its date in the sentence's language at the level held: a year-level statement stored
  as 1 January never reads as a day; a month never gains a day. The sentence says the date
  normalised at that level; the form written on the page is kept in `date.as_written` and the
  app shows it on hover (owner ruling 2026-11-21, G3). Today no sentence has a date
  (0 of 18). Test (to write): `test_each_level_reads_as_its_row_of_the_table`.
  Built: on the entry path for a language with a table that holds `dates`, the clause says the date at its level. Test:
  `fichero-server/tests/unit/knowledge/test_paragraph_dates.py::test_each_level_reads_as_its_row_of_the_table`.
  Not built: the app's hover showing `date.as_written`.
- `kg.para.date-bound-and-about` — **[OK]** (#6773, → #6837) a bound and an approximate date
  read as the table's rows, and a date whose basis is `inferred` is followed by the table's
  "inferred" words; a bound is never said as a date. Test (to write):
  `test_a_bound_and_an_about_date_never_read_as_exact`.
  Built: the bound and about rows and the inferred words. Test:
  `fichero-server/tests/unit/knowledge/test_paragraph_dates.py::test_a_bound_and_an_about_date_never_read_as_exact`.
- `kg.para.date-leads-the-sentence` — **[OK]** (#4648, → #6837) a sentence of one unit opens
  with its date, so the paragraph reads as a chronology and consecutive sentences do not open
  with the name; in a joined sentence each object's date follows it in brackets.
  Test (to write): `test_a_single_unit_sentence_opens_with_its_date`.
  Built: a one-unit sentence opens with its date; a joined sentence follows each object with its date. Tests:
  `fichero-server/tests/unit/knowledge/test_paragraph_dates.py::test_a_single_unit_sentence_opens_with_its_date`,
  `test_a_joined_sentence_follows_each_object_with_its_own_date`.
- `kg.para.order-by-time` — **[PARTIAL]** (#4648, → #6837) units are ordered by the earliest
  bound of their date, then source document, then position in it, then id; undated units come
  last under the table's "undated" words; `ordering=source` orders by document, page and
  offset. Sentences in Spanish and in English share this one chronology; there is no block per
  language (owner ruling 2026-11-21, G5). Built: order by date
  (`fichero-server/tests/unit/knowledge/test_readable_representation.py::test_render_entry_orders_by_date_then_created_at_then_id`).
  Not built: the undated lead-in, the query value, the by-source order on the route.
  Test (to write): `test_undated_units_come_last_under_their_own_words`.
  Built: the undated lead-in, said once before the first undated sentence that follows a dated one
  (`fichero-server/tests/unit/knowledge/test_paragraph_dates.py::test_undated_units_come_last_under_their_own_words`).
  Not built: the query value, the by-source order on the route, the tie-break by source document and position.

### D. Where

- `kg.para.place-stated-once` — **[OK]** (#6773, → #6838) a statement's place
  (`claim_location`, else its first place value's label) is said in its clause unless the
  object already says it; a place that qualifies several clauses of one sentence is said once
  and its segment names every statement it qualifies. Today no place is said unless the object
  holds it (0 of 6). The prototype named only some of the statements on a shared place, which
  is why this line says "every". Test (to write): `test_a_place_is_said_once_and_names_all_it_qualifies`.
  Built: on the entry path for a language with a table that holds `places`, a clause says its place after its object unless the object holds it; a merged sentence says a place every statement has once at the end, its segment naming every statement; when the statements' places differ, each object is followed by its own. Tests:
  `fichero-server/tests/unit/knowledge/test_paragraph_places.py::test_a_place_is_said_once_and_names_all_it_qualifies`, `test_a_place_not_every_statement_shares_follows_its_own_object`, `test_two_places_each_follow_their_own_object`.
- `kg.para.place-says-its-basis` — **[OK]** (#6773, → #6838) a place read in the statement's
  own sentence is said plainly; a place that is only where the document was drawn up
  (`basis` source-anchored) is said as the document's place, in the table's words, never as
  where the event happened; an inferred place carries the table's "inferred" words; a place
  given relative to another is said as written. Test (to write):
  `test_a_documents_place_is_not_said_as_the_events_place`.
  Built: the document's place, the inferred words and the relative place as written. Tests:
  `fichero-server/tests/unit/knowledge/test_paragraph_places.py::test_a_documents_place_is_not_said_as_the_events_place`, `test_a_place_given_relative_to_another_is_said_as_written`.
- `kg.para.place-links-its-name` — **[OK]** (#6773, → #6838) when the place is a known name,
  `place.entity_id` holds it so the app can open that name. Test (to write):
  `test_a_known_place_carries_its_entity_id`.
  Built: `place.entity_id` is the one entity whose canonical name is the place's label, else null; an entry's places are looked up in one query. Tests:
  `fichero-server/tests/unit/knowledge/test_paragraph_places.py::test_a_known_place_carries_its_entity_id`, `test_every_place_of_an_entry_is_looked_up_in_one_call`, `test_a_real_entry_links_one_known_place_and_not_a_shared_name`.
  Not built: the app's link; the app does not open a place from `place.entity_id`.

### E. How sure

Doubt is decided in this order, and the first rule that fits is the only one used.

| # | When | The clause | `doubt` |
|---|---|---|---|
| 1 | a person rejected it | not said | |
| 2 | a person curated or confirmed it | said plainly | `none` |
| 3 | a `contradicts` link joins it to another selected statement | both said in one sentence, each attributed | `disputed` |
| 4 | two or more documents say it | said plainly, then "(dos fuentes)" / "(two sources)" | `none` |
| 5 | one document, and it is tentative or its measured band is low | ", al parecer," / ", apparently," and "(una sola fuente)" / "(one source only)" | `one_source_unsure` |
| 6 | anything else | said plainly | `none` |

- `kg.para.doubt-is-attribution` — **[GAP]** (#4751, → #6839) rule 5: a single-source statement
  that is tentative, or whose confidence has the source `measured` and falls in the engine's
  low band, is never said as plain fact; it takes the table's hedge and its one-source words.
  Test (to write): `test_a_single_unsure_statement_is_hedged_and_attributed`.
- `kg.para.no-figure-no-hedge` — **[GAP]** (#4751, → #6839) a confidence that was not measured
  (no source, or `default`) changes no word: the stored 0.5 a statement is born with is not a
  doubt (`kg.confidence.no-made-up-figure`). No number is ever printed. Test (to write):
  `test_an_unmeasured_figure_changes_no_word`.
- `kg.para.sources-are-counted-in-words` — **[GAP]** (#4751, → #6839) rule 4: the count is of
  distinct source documents, in words from the table up to twelve, and `sources` holds the
  number. Test (to write): `test_two_documents_read_as_two_sources`.
- `kg.para.dispute-states-both` — **[GAP]** (#4751, → #6839) rule 3: two statements joined by
  a `contradicts` link are one sentence that says what they share once and what differs twice,
  each with the table's attribution, in source order ("… el 14 de marzo de 1702 según una
  fuente y en 1704 según otra"); neither is dropped or preferred. Only a stored link makes a
  dispute; the renderer never infers one. Test (to write):
  `test_a_dispute_is_one_sentence_with_both_readings`.
- `kg.para.person-decision-is-plain` — **[GAP]** (#4751, → #6839) rule 2 outranks 3 to 5: a
  statement a person confirmed carries no hedge whatever its figure. Test (to write):
  `test_a_confirmed_statement_is_never_hedged`.

### F. Fewer, better sentences

- `kg.para.same-statement-one-clause` — **[PARTIAL]** (#3808, → #6840) statements with the same
  subject entity, verb, object, date and language are one unit and one clause naming all of
  them. Built: identical objects are listed once and every id kept
  (`fichero-server/tests/unit/knowledge/test_readable_representation.py::test_render_entry_merge_keeps_every_source_claim_id_in_order`).
  Not built: the date in the key (today two sources with different dates collapse into one
  sentence that says neither). Test (to write):
  `test_same_statement_different_date_is_two_units`.
- `kg.para.one-passage-one-sentence` — **[GAP]** (#3808, → #6840) two statements with the same
  subject entity and verb that rest on the SAME stretch of one page (the same character
  range), one with a plain object and one whose object opens with a preposition, are said as
  one clause pair, the plain object first, with no conjunction between them ("vendió una casa
  a …"). Anything less than the same stretch stays two sentences, as ruled for #4836. This
  narrows that ruling: the two halves of one act from the same passage may share one sentence
  (owner ruling 2026-11-21, G2). Test (to write):
  `test_two_halves_of_one_passage_are_one_sentence_and_never_coordinated`.
- `kg.para.run-is-neighbours` — **[BROKEN]** (#4648, → #6841) only units next to each other in
  the paragraph's order, with the same subject entity, verb, language and doubt, join into one
  sentence, four at most. Today `aggregate_claims` joins every same-verb statement of the
  whole list into the place of the first, so a sentence dated 1741 holds an act of 1745 ahead
  of acts of 1744. Test (to write): `test_only_neighbours_in_order_join`.
- `kg.para.run-keeps-each-date` — **[BROKEN]** (#4648, → #6841) in a joined sentence each
  object is followed by its own date and place in brackets ("… del testamento de … (1741,
  …) y de la venta de … (9 de mayo de 1743, …)"), each object its own clause. Today the
  dates and places of joined statements are dropped. Test (to write):
  `test_each_joined_object_keeps_its_date_and_place`.

### G. Words

- `kg.para.table-is-data` — **[PARTIAL]** (#4650, → #6842) a language's joining words, date
  patterns, month names, doubt words, number words, prepositions, contractions and frames are
  one data file per language in the engine's resources, validated on load; the code holds no
  language's words. Today two small dictionaries in
  `fichero-server/src/fichero_server/knowledge/readable.py` hold three words each. Test (to
  write): `test_a_language_is_added_by_a_file_alone`.
  Built: `fichero-server/src/fichero_server/resources/language_tables/<language>.json`
  holds the joining, place and count words, the leading prepositions and the contractions, and
  `load_language_tables` refuses a file with a missing key or a name other than its language.
  Not built: date patterns, month names, doubt words, number words and frames are not in the
  files. Test: `test_a_language_is_added_by_a_file_alone` in `fichero-server/tests/unit/knowledge/test_paragraph_tables.py`.
- `kg.para.no-table-is-verbatim` — **[OK]** (#4650, → #6842) a sentence in a language
  with no table is the statement's stored subject, verb and object and nothing else, with its
  year in digits in brackets; it joins nothing and takes no word from another language. Built:
  such a statement is never merged (`_is_solo_claim`). Not built: the year. Test (to write):
  `test_a_language_without_a_table_takes_no_borrowed_word`.
  Built: the year of its start date is kept. Test:
  `test_a_language_without_a_table_takes_no_borrowed_word` in `fichero-server/tests/unit/knowledge/test_paragraph_tables.py`.
- `kg.para.seams` — **[PARTIAL]** (#5008, → #6842) at the seam of verb and object a
  preposition is said once, and the table's contractions are made (Spanish de + el, a + el);
  in a joined Spanish sentence the verb's preposition is repeated before each object. Today
  the said-once rule is in `render_aggregation`, which the entry path does not call, so the
  route still prints the doubled word. Tests (to write):
  `test_the_entry_path_says_a_preposition_once`, `test_spanish_contractions_at_the_seam`.
  Built: on the entry path the object's copy of the verb's last preposition is dropped, and
  "de el" / "a el" become "del" / "al" as a segment of origin `table:es:de el`; in a joined
  sentence the contraction is made against the first object only. Not built: a joined sentence
  whose objects begin with a preposition is never merged (`_is_prepositional_object`), so the
  repeated preposition before each object does not arise there. Tests: in `fichero-server/tests/unit/knowledge/test_paragraph_tables.py`.
- `kg.para.name-once` — **[GAP]** (#4651, → #6843) the page name is given in full in the first
  sentence. After it, while the page name stays the subject: a language whose table says the
  subject may be left out (Spanish) leaves it out; any other uses the short name. After a
  sentence whose subject is someone else, the next uses the short name. Today the full name
  is printed in every sentence (17 times in 18). Test (to write):
  `test_the_full_name_is_given_once`.
- `kg.para.short-name-is-attested` — **[BROKEN]** (#4651, → #6843) the short name is the
  shortest of the entity's own recorded names that is made of words of the canonical name, has
  two words or more, and is no other entity's name in the project; with none, the full name.
  It is never computed from a token: `referring_expression` takes the last word, which for a
  Spanish name with two surnames is the mother's. No pronoun is used while no gender is held.
  Test (to write): `test_a_short_name_is_always_a_recorded_name`.
- `kg.para.recentre-by-frame` — **[GAP]** (#4837, → #6844) a statement whose object is the
  page name is said with the page name as subject only when: the verb, folded, has a frame in
  the language's table; what stands before the name in the object is nothing or one of the
  table's prepositions; and what stands after it is nothing or the frame has a slot for it
  ("nombró a … albacea" becomes "fue nombrada albacea por …"). Otherwise the statement keeps
  its true subject, in its place in the order, with the page name in its short form. The
  clause is `revoiced` and its frame's words have a `table:` origin. The first Spanish and
  English frames are drafted by a worker from the project's 50 most frequent verbs and reviewed
  by the owner before they ship (owner ruling 2026-11-21, G6). Test (to write):
  `test_an_object_statement_is_recentred_only_through_a_frame`.
- `kg.para.frame-needs-agreement` — **[GAP]** (#4837, → #6844) a frame lists the forms it has
  (one for all, or one per gender and number); a frame with only gendered forms is used only
  when the page name's grammatical gender is held, else the true subject is kept. Measured:
  of four object statements, one is re-centred with no gender held and three with it.
  Test (to write): `test_a_gendered_frame_waits_for_a_held_gender`.
- `kg.para.gender-is-evidence` — **[GAP]** (#4837, → #6845) a person's grammatical gender,
  for agreement only, is a value on the name with its basis and source like any other: set by a
  person, or read from an agreeing word the page itself uses of them (a title, an adjective),
  marked as read and naming that page as its source; never guessed from a given name (owner
  ruling 2026-11-21, G4). Test (to write): `test_gender_is_never_guessed_from_a_name`.

### H. The app, and what stays out

- `kg.para.app-draws-the-engines-paragraph` — **[GAP]** (#4832, #4838) the Reader draws
  `paragraph` and uses `clauses` for hit-testing; a click on a clause opens its statement and
  reveals its page (`kg.read.sentence-opens-source-highlighted`); a clause of several
  statements offers each. The app composes no sentence. Today nothing in the app calls the
  route. Test (to write): `EntityParagraphClauseTests` in the app's unit tests.
- `kg.para.no-model-in-the-path` — **[PARTIAL]** (#4652) no stage calls a language model, on
  the device or off it, and no setting turns one on. Built: `render_entry` calls none. Not
  built: the guard test (`kg.para.deterministic`); the model-written biography route still
  exists (`kg.read.no-llm`). No model smooths the prose (owner ruling 2026-11-21, G1), and the
  model-written biography route is retired (G7): the route is removed, and the descriptions it
  already wrote are labelled as model-written and kept for a person to keep or clear (the
  migration risk in `kg-readable-representation.md`). Test (to write):
  `test_no_route_writes_a_model_biography`.

## The evaluation set and its pass bar

- `kg.para.eval-set` — **[OK]** (#4841, → #6846) a synthetic set, no archive data, lives
  with the engine's test fixtures as rows shaped like the engine's: three invented names (a
  person, a place, an organisation), 26 statements each, covering every case in "Measured"
  above, in Spanish, English and Portuguese (a language with no table) and with no language. A
  case seen wrong on a real paragraph is added as an invented row before it is fixed. Test:
  `test_the_evaluation_set_covers_every_case` in
  `fichero-server/tests/unit/knowledge/test_paragraph_eval_set.py`.
- `kg.para.pass-bar` — **[PARTIAL]** (#4841, → #6846) a scorer reads the route's answer for each
  name of the set and the test fails unless, exactly:

| Measure | Bar |
|---|---|
| rejected or merged statements said | 0 |
| mention-only statements in the paragraph | 0 |
| selected statements in exactly one clause | all |
| letters and digits inside a segment with an origin | all |
| `claim:` segments that are substrings of their field | all |
| dated statements whose date is said at its level | all |
| dates said finer than held | 0 |
| places said, or already in the object | all |
| statements needing a mark (rules 3 and 5, inferred, bound) that carry it | all |
| statements a person confirmed that carry a hedge | 0 |
| false subjects (a clause's subject is neither the statement's own nor a frame's) | 0 |
| identical sentences | 0 |
| full canonical name | once per paragraph, plus once per sentence with no table |
| words in the longest sentence | 40 at most |
| the same bytes from shuffled input, five shuffles | yes |

  Built: the scorer, checked on hand-written answers; `test_the_route_answer_meets_the_pass_bar`
  runs it on the route's answer for each name and is a strict xfail until #6835 to #6844 land.
  Not built: the re-centred share report and the expected paragraphs as text.
  The share of object statements re-centred is reported and has no bar: it grows with the
  table. Reading quality beyond these counts is judged by a person on the set's paragraphs,
  kept beside the fixtures as expected text, so a change in wording shows as a diff.

## A worked example (the evaluation set's person, gender held)

The target for the evaluation set's person. It is the prototype's output but for one seam the
prototype got wrong and `kg.para.seams` rules on (the repeated "de" before "la venta").

> Inés Valcárcel Montaño nació en Villa Arenal el 14 de marzo de 1702 según una fuente y en
> 1704 según otra. El 30 de septiembre de 1722 casó con Clemente Ibarra en Villa Arenal. En
> junio de 1731 vendió una casa de teja a Baltasar Oquendo en Villa Arenal (dos fuentes). En
> 1733, al parecer, fue demandada por Baltasar Oquendo (una sola fuente). En 1734 Baltasar
> Oquendo compareció ante Inés Valcárcel. Inés Valcárcel Montaño compró dos mulas (1736).
> Hacia 1738 enviudó (fecha inferida). El 2 de noviembre de 1740 fue nombrada albacea por
> Clemente Ibarra. Fue testigo del testamento de Clemente Ibarra (1741, Villa Arenal) y de la
> venta de una estancia (9 de mayo de 1743, San Telmo del Río). In August 1744 Inés Valcárcel
> arrived at San Telmo del Río. En 1745 fue testigo de un poder. From 1746 to 1749 Inés
> Valcárcel served as administrator of the Arenal estate. In 1746 Inés Valcárcel was appointed
> by Clemente Ibarra. En 1751 o después otorgó testamento. Sin fecha conocida: era vecina de
> Villa Arenal.

Every name here is invented. The sixth sentence is a statement with no language: its own words
and its year, nothing borrowed. "Compareció ante" has no frame, so that sentence keeps its true
subject. The same statements read today: "Inés Valcárcel Montaño nació en Villa Arenal. Inés
Valcárcel Montaño nació en Villa Arenal. Inés Valcárcel Montaño casó con Clemente Ibarra. …"
for eighteen sentences, with the rejected death and the mention among them.

## Build order

Each step is one builder step (25 files at most), engine first, with the test written red from
the behaviour's words before the change. Stages 1 to 3 change the engine only.

### Stage 1 — Say only what is held, and keep every clause's statement

#### Step 1.1 — The evaluation set and its scorer, red (#6846)
- Behaviours: `kg.para.eval-set`, `kg.para.pass-bar`
- Tests: to write: `test_paragraph_eval_set.py` in fichero-server/tests/unit/knowledge/
- Size: M

#### Step 1.2 — Rejected and merged statements are never said; mentions are a list (#6835)
- Behaviours: `kg.para.rejected-never-stated`, `kg.para.mentions-are-a-list`
- Tests: to write: `test_paragraph_selection.py` in fichero-server/tests/unit/knowledge/
- Depends on: 1.1
- Size: S

#### Step 1.3 — Clauses and segments on the route; the exact faithfulness test (#6836)
- Behaviours: `kg.para.clause-carries-claim-ids`, `kg.para.every-character-has-an-origin`, `kg.para.every-statement-is-said-once`, `kg.para.deterministic`, `kg.para.proposed-is-marked`
- Tests: `test_paragraph_trace.py` in fichero-server/tests/unit/knowledge/, `test_routes_kg_paragraph_clauses.py` in fichero-server/tests/unit/api/
- Depends on: 1.2
- Size: M

#### Step 1.4 — The model-written biography route is retired; no model in the path (#4652)
- Behaviours: `kg.para.no-model-in-the-path`
- Tests: to write: `test_paragraph_no_model.py` in fichero-server/tests/unit/knowledge/
- Depends on: 1.3
- Size: S

### Stage 2 — When, where, how sure

#### Step 2.1 — A language's table is a data file; seams (#6842)
- Behaviours: `kg.para.table-is-data`, `kg.para.no-table-is-verbatim`, `kg.para.seams`
- Tests: to write: `test_paragraph_tables.py` in fichero-server/tests/unit/knowledge/
- Depends on: 1.3
- Size: M

#### Step 2.2 — Dates at the level held, and the order they give (#6837)
- Behaviours: `kg.para.date-at-stored-level`, `kg.para.date-bound-and-about`, `kg.para.date-leads-the-sentence`, `kg.para.order-by-time`
- Tests: to write: `test_paragraph_dates.py` in fichero-server/tests/unit/knowledge/
- Depends on: 2.1
- Size: M

#### Step 2.3 — Places, said once, with their basis (#6838)
- Behaviours: `kg.para.place-stated-once`, `kg.para.place-says-its-basis`, `kg.para.place-links-its-name`
- Tests: to write: `test_paragraph_places.py` in fichero-server/tests/unit/knowledge/
- Depends on: 2.1
- Size: S

#### Step 2.4 — Doubt as attribution, sources in words, disputes in one sentence (#6839)
- Behaviours: `kg.para.doubt-is-attribution`, `kg.para.no-figure-no-hedge`, `kg.para.sources-are-counted-in-words`, `kg.para.dispute-states-both`, `kg.para.person-decision-is-plain`
- Tests: to write: `test_paragraph_doubt.py` in fichero-server/tests/unit/knowledge/
- Depends on: 2.1
- Size: M

### Stage 3 — Reads like prose

#### Step 3.1 — Units: one statement from many sources; one passage, one sentence (#6840)
- Behaviours: `kg.para.same-statement-one-clause`, `kg.para.one-passage-one-sentence`
- Tests: to write: `test_paragraph_units.py` in fichero-server/tests/unit/knowledge/
- Depends on: 2.2
- Size: S

#### Step 3.2 — Only neighbours join, and each keeps its date and place (#6841)
- Behaviours: `kg.para.run-is-neighbours`, `kg.para.run-keeps-each-date`
- Tests: to write: `test_paragraph_runs.py` in fichero-server/tests/unit/knowledge/
- Depends on: 3.1
- Size: M

#### Step 3.3 — The name once, then an attested short form or nothing (#6843)
- Behaviours: `kg.para.name-once`, `kg.para.short-name-is-attested`
- Tests: to write: `test_paragraph_names.py` in fichero-server/tests/unit/knowledge/
- Depends on: 2.1
- Size: S

#### Step 3.4 — Re-centring through frames, with agreement (#6844, #6845)
- Behaviours: `kg.para.recentre-by-frame`, `kg.para.frame-needs-agreement`, `kg.para.gender-is-evidence`
- Tests: to write: `test_paragraph_frames.py` in fichero-server/tests/unit/knowledge/
- Depends on: 3.3
- Size: M

### Stage 4 — The app draws it

#### Step 4.1 — The Reader draws the engine's paragraph; a clause opens its statement (#4838, #4832)
- Behaviours: `kg.para.app-draws-the-engines-paragraph`, `kg.para.edit-re-renders-the-clause`
- Tests: to write: `EntityParagraphClauseTests` in the app's unit tests, `test_paragraph_edit.py` in fichero-server/tests/unit/knowledge/
- Depends on: 1.3
- Size: M

## Test matrix (legs this surface touches)

| Leg | Pins |
|---|---|
| Pure rule (pytest) | every stage: selection, units, order, runs, dates, places, doubt, names, frames, seams |
| Route (pytest) | the answer's clauses, segments, mention list, ordering value |
| Evaluation set (pytest) | the pass bar, on every name of the set; expected paragraphs as text |
| No model (pytest) | any model client raising fails nothing; the same bytes from shuffled input |
| App unit (Swift Testing) | a clause's offsets hit-test to its statement ids; the app composes no sentence |
| Click-around (XCUITest, a person's session) | select a name, read, click a clause, see the statement and the page |

## Open questions for the owner

Answered by the owner on 2026-11-21 (rulings G1 to G7) except question 3; the behaviours above
carry each answer.

1. **A model for smoothness, ever?** Ruled (G1): no model smooths the prose for now. The
   literature's hybrid (rules state the facts; a small model only reorders, joins and smooths; a
   checker refuses any output whose clauses do not map back) stays an experiment on the
   evaluation set behind the same pass bar, never the default (NEW-13 (owner question 1), not
   filed).
2. **One passage, one sentence.** Ruled (G2): the two halves of one act from the same passage
   may share one sentence (`kg.para.one-passage-one-sentence`). It narrows the ruling made for
   #4836 that a prepositional object never joins anything.
3. **A statement that keeps its true subject: in its place in time, or after the rest?** An
   earlier answer put it after the re-centred run; this spec keeps it in date order, since
   order by time is the ruled default. Which holds? (Open.)
4. **The date in the sentence: normalised, or as written?** Ruled (G3): normalised at the level
   held, with the written form on hover (`kg.para.date-at-stored-level`).
5. **Gender for agreement.** Ruled (G4): a person's grammatical gender may be read from an
   agreeing word on the page, marked and sourced, never guessed from a name
   (`kg.para.gender-is-evidence`).
6. **Two languages in one paragraph.** Ruled (G5): Spanish and English statements share one
   chronology (`kg.para.order-by-time`).
7. **The inverse frames.** Ruled (G6): a worker drafts the first inverse verb frames from the 50
   most frequent verbs, and the owner reviews them (`kg.para.recentre-by-frame`).
8. **The model-written biography route** (question 8 of `kg-readable-representation.md`).
   Ruled (G7): retire it (`kg.para.no-model-in-the-path`, Step 1.4).

## Future (ideas, not scheduled)

- A Grammatical Framework grammar, or a Wikifunctions renderer once Abstract Wikipedia's are
  usable outside it, in place of a language's table: the plan (stages 1 to 5) is the
  language-neutral input either needs. Agreement, case and word order then come from the
  grammar. Worth its cost at the third language with rich inflection, not before.
- The other genres (`kg.read.genre.*`): a document's regest and a place's entry are the same
  pipeline with another selection and another order.

## Issues to file (milestone kg-readable-representation)

- #6835 (NEW-1): the paragraph states rejected and merged-away statements as fact, and narrates mention-only ones; filter them and return the mention list.
- #6836 (NEW-2): the readable route returns clauses and segments (claim ids, origin, state) with the exact every-character-has-an-origin test and a shuffled-input test.
- #6837 (NEW-3): the paragraph states each statement's date at the level held (day, month, year, span, about, bound, inferred), leads with it, and puts undated last.
- #6838 (NEW-4): the paragraph states each statement's place once, with its basis, and links a known place.
- #6839 (NEW-5): doubt in the paragraph: the six ordered rules (person's decision, dispute, sources in words, single unsure source), and no hedge from an unmeasured figure.
- #6840 (NEW-6): units: the same statement from several sources is one clause (date in the key); two halves of one passage are one sentence.
- #6841 (NEW-7): only neighbouring units join, four at most, and each joined object keeps its own date and place.
- #6842 (NEW-8): a language's table is one data file (joining words, dates, doubt words, prepositions, contractions, frames); seams fixed on the entry path ("at at", "de el").
- #6843 (NEW-9): the name in full once, then an attested short name or a left-out subject; the last-word surname rule is removed.
- #6844 (NEW-10): re-centring through per-verb frames with a slot for the rest of the object and forms per gender; no frame, no re-centring.
- #6845 (NEW-11): a person's grammatical gender as a value with basis and source, for agreement only, never guessed from a name.
- #6846 (NEW-12): the synthetic evaluation set and the scorer with its pass bar, as an engine test.
- NEW-13 (owner question 1), not filed: measure a small local model as a smoothing pass on the evaluation set behind the pass bar.
