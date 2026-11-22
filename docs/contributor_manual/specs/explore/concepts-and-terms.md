# Explore: concepts and terms — the sources' own words, the historian's concepts, and counts that can be cited — Design Spec (#5032, #4692)

> Milestone: concepts-and-terms
> Spec: explore/concepts-and-terms.md
> Manual: TBD — a "Words and ideas in your archive" section, written for a historian: how to see every word a set of
> sources uses and open any one of them (its spellings, every line it appears in, when and where, who writes it and
> about whom, the words beside it); how to define a concept of your own and have Fichero find passages that may be
> instances, passages that come close, and where it is absent; how to mark yes, no and unsure; what a count shown as
> a range means; and how to put a count in a footnote so a reader can check it.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-21** (from the owner's rulings of 2026-11-21 on people,
> biography and concepts; the owner approves). Nothing here is built unless tagged [OK]. This file belongs to the
> Explore set and obeys every rule of `explore/explore.md`. It differs from the other files of the set in one way:
> it declares its own milestone, `concepts-and-terms`, so that it can be ordered in `build-order.md` after
> `reconstruct-the-record`; the rest of the set stays on `explore`. Its pair is `kg/people-and-lives.md`. It rests on
> `source/read-any-hand.md` for reading confidence, on `explore/tables-and-counts.md` for the table and the corpus
> counts it extends, and on `kg/hermeneutic-layer.md`, which owns the record a concept is kept in.
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists in part · **[GAP]** designed, not built · **[BROKEN]** built and
> contradicting the line. Every non-[OK] line cites an issue; "→ #NEW-Cn" is an issue the manager is asked to file on
> this milestone, one per build-order step.

## Exploring your archive: words and ideas (for a historian)

This is a way to explore your own archive, starting from a word or from an idea of your own.

**Start from a word.** Open any folder and ask for its vocabulary: every term the sources use, how often, by how
many writers, from when to when. Pick one, perhaps a status word a register keeps using, and you get its page. You
see how it was actually written (every spelling and abbreviation, as snippets of the handwriting). You see every
line it appears in, with the word lined up down the middle so your eye can run along what comes before and after.
You see when and where it is used, who writes it and about whom, and which words keep it company in one decade and
which in the next. Every number opens to its lines, and every line opens to its page image.

**Start from an idea.** You have a concept: something you think is going on in these sources that no single
document says outright. You write it down in your own words, point at a few passages that show it, and say what
does not count. Fichero then does the legwork one person cannot do across thousands of pages. It brings you
passages that may be further instances, each with the reason it was fetched. It brings you the ones that come close
and differ, which are the ones that should worry you. It shows where your concept is common, where it is thin, and
where it is absent, and whether "absent" means the pages were read and it is not there, or the pages were never
read. You mark each passage yes, no or unsure, and the search gets better at finding what you mean.

**Walk outward.** From a term to the people it is applied to (`kg/people-and-lives.md`), to the office that wrote
it, to the documents, to a concept of yours that leans on it, and back to a page. A name is a word too: the same
page works for a person's name.

**What Fichero does not do.** It never proposes a concept, never names a pattern, never says what a word meant or
that its meaning changed, and never tells you an idea is new. It finds, counts and shows. The thinking is yours.

**Counts you can cite.** A count is shown as a range ("140 to 175 uses") because handwriting is misread sometimes,
and Fichero says how much of the count rests on readings a person checked. Beside it is a small strip showing which
pages were read, which were not, and which the archive does not hold. Any count exports with its passages and a
ready-made footnote, so a reader can check you.

## Ruled 2026-11-21 (owner; paraphrased)

1. **Concepts are the historian's.** In concept-led search the historian defines a concept and Fichero finds
   instances, near misses and counter-examples. The AI never proposes concepts or interpretations.
2. **The sources' own terms are surfaced.** The words the people in the documents used (their own, or more often
   their recorders'): who uses them, about whom, and how use shifts.
3. **The design rule.** Views show what is in the sources, built from counted, reproducible facts. A model does only
   mechanical, checkable jobs (reading handwriting, grouping spelling variants, proposing a link, ranking), each
   labelled as model output, with its confidence, one click from the evidence. The person's marks are the truth.
4. **No public scores.** Any quality figure is a private check on the person's own project.

## Intent (the design)

Two kinds of concept, and Fichero's part in each is different.

- **The sources' terms** are on the page. Listing them invents nothing, so Fichero does it unasked, as it lists
  names. It measures how each is used. It never says what one means.
- **The historian's concepts** are made by the historian to explain. Fichero serves one once it exists: it ranks
  candidate passages, shows near misses, counts, and remembers the historian's marks. It writes nothing in it.

One view serves a term and a name alike: **the attestation sheet**. And one rule covers every number on it and
everywhere else in this spec: **a count is a range that says what it is made of, has its denominator beside it, and
opens to its pages.** A concordance over clean text is decades old. What is new here is the same thing over
handwriting that was never searchable, with the reading's uncertainty carried into the count.

Nothing in this spec is a conversation. A model is a reader, a grouper of spellings and a ranker behind views. It
writes no sentence about the past.

## Prior art (what we adopt)

- **Keyword in context (the concordance), collocation and frequency over time** from corpus linguistics: old,
  published methods with stated settings (window, measure), which is part of why they convince. Adopted; every view
  states its settings on its face.
- **Collation** from textual scholarship: the same clause set side by side across witnesses, for formula and slot.
- **The history of concepts and historical semantics**: tracing a word's use across writers and periods by reading
  its attestations. The sheet gathers them; the tracing stays the scholar's.
- **Emic and etic** from anthropology, as the line between the two kinds of concept.
- **Qualitative coding** tools: a person's code applied to passages, with a codebook that changes. Adopted as the
  concept record with marks and versions. Deliberately different: counter-examples are put in front of the person.
- **Active learning with a simple ranker** fitted on a person's yes and no marks. Adopted, local, labelled.
- **Not adopted:** topic models and clusters as findings, generated summaries, a chat that answers about the corpus.
  A cluster is a model's claim that passages belong together, with no reason a person can check line by line.

## What exists today (read 2026-11-21)

- Full text, search, passage vectors, spelling keys for names; a keyword route (`GET /search/keywords`).
- No word frequency, collocation or word use over time (`explore/tables-and-counts.md`, "What exists"); its lines
  `explore.corpus.word-use-over-time`, `explore.corpus.keyword-in-context`, `explore.corpus.which-reading` and
  `explore.corpus.ocr-quality-is-shown` are [GAP] and are built by the steps here.
- The reader stores per-character confidences; none is calibrated (`hands.calib.fitted-per-hand-and-shown` [GAP]).
- Engine records for a framework, an interpretation and a pattern with supporting passages, with audited routes
  (`kg/hermeneutic-layer.md`); one Inspector tab reaches them; nothing anchors them to a stretch of a page.
- No word-level normalisation or lemmas for historical languages; no writer or office field on a document; no
  alignment of formulae. The steps below say which views wait for which.

## The design

### The attestation sheet

The Reader rendition of one selected term, or one name. Six parts, each opening to its passages:

| Part | Shows | Needs |
|---|---|---|
| **Forms** | the spellings, abbreviations and translations as crops of the written word, grouped; proposed groupings marked; each grouping can be cut | text; variant proposals |
| **Concordance** | every occurrence in its line, the term centred, sortable by what stands left or right, by date, by writer | text |
| **When and where** | use along time and by place and archive, as a rate against what was read, in four states: present; absent in pages read with confidence; unknown because unread or read unsurely; no such pages held | text; dates of documents |
| **Who writes it, about whom** | writers and offices down, the people or things it is applied to across, in the sources' words | the writer field; roles (`ontology.role.is-a-position-in-a-statement`) |
| **Company** | the words and names found within a stated window of it, against their rate elsewhere, by period, record type and writer, as lists with example lines | text |
| **The slot** | where it sits in a formula or a table column, and what else fills that place, over time | formula alignment |

### A count is a range

Wherever a count is shown, four things are shown together:

    140 to 175 uses                     the range, at a stated level (90%)
    126 on high-confidence readings, 31 checked by a person
    read: 2,140 of 2,600 pages in scope; 310 unread; 150 too unsure to count
    [strip: the pages in scope by time and writer: read, read unsurely, unread, not held]

The range has three measured sources and no invented one. **Finds that are wrong:** each matched word has a
calibrated chance of being read right. **Uses that were missed:** words whose second or third reading matches, and
the hand's measured miss rate for that kind of word. **Joined or not:** the low end counts only forms a person
accepted; the high end adds proposed forms; the two are stated apart. Until a hand has a calibration fit, the count
reads "at least N as read; reading not yet measured" and shows no range. An invented error bar is worse than none.

Beside a range is "check 20 lines to narrow this": the occurrences that contribute most to its width. Each yes or
no replaces a chance with a fact, and the range narrows as the person works.

### The concept, owned by the person

A concept is a sidebar node, kept in the hermeneutic layer's records, with: a name and a definition in the person's
words; seed passages; what counts and what does not; an optional scope (where, when, for whom it is claimed); the
person's marks (yes, no, unsure) with who and when; and a history of every version. Its Reader rendition is the
**concept sheet**, with two columns that are both open by default:

- **Candidates**, ranked, each as the crop of its lines with the reading beneath and the reason it is there: the seed
  it is nearest to, the words it shares, and after some marks, the score of the concept's own ranker.
- **Near the line**, in three labelled kinds: passages the ranker is least sure of; passages like the "does not
  count" seeds; and, only when a scope is given, documents of the kind where instances are usually found that have
  none. Fichero says "close, and differs here". Whether one is a counter-example is the person's judgement.

The **spread** of a concept (by time, place, record type, writer) is computed over passages the person marked yes,
as a rate against what was read, in the four states. Ranked candidates nobody marked are drawn hollow beside them
and are never summed with them.

A source's term can be **evidence for a concept, attached by the historian**. The sheet then shows a two-by-two:
passages with the term and marked yes; with the term and not; marked yes without the term; neither. The two
off-diagonal cells are where the historian's concept and the sources' word come apart.

### What Fichero may and may not put on screen

| May | May not |
|---|---|
| list terms ordered by something measured (count, writers, first and last use, unevenness in time) | title any list "key terms" or pick which words are categories |
| show that the company a term keeps differs between two periods, with the lines | say the term came to mean something |
| say a mark contradicts the person's own "does not count" rule, and show both | rewrite the definition or the rule |
| say two of the person's concepts match largely the same passages | say which is the better concept |
| show the share of pages in scope that no concept of the person's touches | name what is in it, cluster it, or suggest a concept |
| rank passages with a stated reason | summarise, explain, or compare with the literature |

### Views

All counted, each with its table twin and its settings on its face: the vocabulary of a set (a Library view mode);
the concordance; use over time as small bars with the denominator strip under them; company as small multiples of
lists by period; the who-writes-it-about-whom matrix (the one-term form of `people.view.who-names-whom`); the
slot's alternatives over time as counts; the concept's spread; the two-by-two. Not built: word clouds (size carries
no checkable quantity), a map of passages by vector likeness as a picture that carries an argument (likeness by
vectors is a model's judgement and stays a ranked list with reasons), and anything in three dimensions (there is no
third ordered quantity here that two cannot carry).

### Export for a footnote

Any counted view exports one bundle: the query (the set, the term with its accepted forms, filters, window and
measure, the reading threshold); what it was run on (the date, the version of each reader and of the variant
grouping, how many of the lines counted a person checked); the counts as a table, with ranges; the passages, each
with its line as read, its archive reference and its stretch on the page; and a footnote in plain words. A count
that rests on a model's readings says so in the footnote itself and cannot be exported without it.

## Behaviours

### A. The sources' own terms

- `terms.vocabulary.table-of-any-set` — **[GAP]** (#5032 → #NEW-C1) for any set, a Library view mode lists its terms
  as a table: count, rate per thousand words read, number of writers and of record types that use it, first and
  last attestation, and how unevenly it falls in time. Rows sort and filter on those columns only; no column and no
  title ranks a term as important. A row opens the term's sheet. Counts say which reading was counted
  (`explore.corpus.which-reading`). *Test (to write):* test_vocabulary_table.py (counts equal a hand count on a keyed
  fixture; the payload has no field of free prose).
- `terms.concordance.every-occurrence-in-its-line` — **[GAP]** (#5032 → #NEW-C1) every occurrence of a term or a name
  is listed in its line with the term centred, sortable by left context, right context, date and writer; each row
  shows the crop of the written line on demand and opens the page with the stretch lit. Builds
  `explore.corpus.keyword-in-context`. *Test (to write):* test_concordance_rows.py.
- `counts.open.every-count-opens-to-its-lines` — **[GAP]** (#5032 → #NEW-C1) every number on every view of this spec
  opens to the list of occurrences it counts, and each of those to its page, in one step each
  (`explore.source.aggregate-opens-to-a-list`). A guard walks every view payload: each count carries the ids of what
  it counts or a query that returns them, and no field holds text a model composed. *Test (to write):*
  test_term_payloads_open_and_hold_no_model_prose.py.
- `terms.forms.variants-are-proposals` — **[GAP]** (#5032 → #NEW-C2) spellings, abbreviations and translations of a
  term are grouped by a labelled method into proposals; a group becomes one term only when a person accepts it, and
  an accepted grouping can be cut, which separates its counts. The Forms part shows each form as a crop of the
  written word with its count and the state of its grouping. *Test (to write):* test_term_variants_are_proposals.py
  (a planted term in three spellings is three rows until accepted, then one; cut gives three again).
- `terms.forms.only-trusted-readings-make-a-term` — **[GAP]** (#6763 → #NEW-C2) a word read in the unsure or not-read
  band never creates a row of the vocabulary and never proposes a form; it is counted as "too unsure to count" in
  the strip. *Test (to write):* test_unsure_words_make_no_term.py.
- `terms.sheet.one-view-for-a-term-or-a-name` — **[GAP]** (#5032 → #NEW-C3) the attestation sheet is the Reader's
  rendition of a selected term and of a selected name, from one payload shape and one drawing: forms, concordance,
  when and where, who writes it about whom, company, slot. A part whose data the project does not have yet says
  what it waits for and shows nothing invented. On iPhone the parts are swiped. *Test (to write):*
  AttestationSheetTests.swift.
- `terms.sheet.when-and-where-in-four-states` — **[GAP]** (#5032 → #NEW-C3) use along time, by place and by archive is
  drawn as a rate against what was read, and each period or place is in one of four states that are drawn
  differently: present; absent in pages read with confidence; unknown because the pages are unread or read
  unsurely; no such pages held. A zero is never drawn for the third or fourth state. Builds
  `explore.corpus.word-use-over-time` and `explore.corpus.ocr-quality-is-shown`. *Test (to write):*
  test_when_and_where_four_states.py.
- `terms.reader.tracked-terms-layer` — **[GAP]** (#5032 → #NEW-C3) in the Reader a layer underlines the terms the
  person chose to track in any document; each opens its sheet. Off by default. *Test (to write):*
  TrackedTermsLayerTests.swift.
- `terms.sheet.company-is-collocation-with-settings` — **[GAP]** (#5032 → #NEW-C4) the words and names found within a
  stated window of a term, scored by a named measure against their rate elsewhere, shown as lists with example
  lines, as small multiples by period, record type and writer; the window and the measure are on the view and can
  be changed. Each neighbour opens its lines. *Test (to write):* test_collocation_settings_and_counts.py.
- `terms.sheet.shift-in-use-never-in-meaning` — **[GAP]** (#5032 → #NEW-C4) the sheet can show that a term's company,
  its writers or the people it is applied to differ between two periods the person chose, as two lists with their
  lines and counts. No payload or label states what a term means or that a meaning changed.
  *Test (to write):* test_shift_is_shown_as_counts.py (a planted term whose neighbours change after a date shows two
  different lists; the payload has no sentence).
- `terms.sheet.who-writes-it-about-whom` — **[GAP]** (#5032 → #NEW-C5) a matrix for one term: writers and offices
  down, the people or things it is applied to across, grouped in the sources' own words, each cell a count of acts
  that opens to them. A term in a writer's own voice is kept apart from one in reported speech where the source
  marks that. Waits for the writer field and roles of `kg/people-and-lives.md` Step 4.2. *Test (to write):*
  test_term_who_about_whom.py.
- `terms.sheet.the-slot-and-its-alternatives` — **[GAP]** (#5032 → #NEW-C5) where a term stands in a recurring formula
  or a table column, the sheet shows that slot and everything else that fills it across the set, as counts over
  time. Slots come from text alignment of acts of one kind (`xcorpus.link.shared-structure`) or from a column the
  person names; vectors may rank which acts to align and decide nothing else. *Test (to write):*
  test_slot_alternatives.py.

### B. Counts as ranges

- `counts.range.four-parts-together` — **[GAP]** (#6763 → #NEW-C6) one engine function returns every count this spec
  shows, and what it returns is always four parts: the range at a stated level; how many finds rest on
  high-confidence readings and how many on readings a person checked; the pages in scope read, unread and too
  unsure to count; and the data of the denominator strip. No view computes a count of its own.
  *Test (to write):* test_count_has_four_parts.py.
- `counts.range.built-from-measured-doubt-only` — **[GAP]** (#6763 → #NEW-C6) the range is computed from the
  calibrated chance that each matched word is read right, from words whose second or third reading matches with
  their chances, and from the hand's measured miss rate for that kind of word (names and rare words measured
  apart from common ones). The method is named and versioned and its inputs can be opened. Search and counting read
  the reader's alternative readings. *Test (to write):* test_range_from_calibrated_readings.py.
- `counts.range.no-fit-no-range` — **[GAP]** (#6763 → #NEW-C6) for pages whose hand has no calibration fit
  (`hands.calib.fitted-per-hand-and-shown`), the count reads "at least N as read; reading not yet measured" and no
  interval is shown or exported. *Test (to write):* test_no_fit_gives_no_range.py.
- `counts.range.accepted-and-proposed-apart` — **[GAP]** (#6763 → #NEW-C6) a count over forms or over joined people
  gives the figure under accepted groupings and joins, and separately how much proposed ones would add ("112 under
  accepted forms; up to 175 with 9 proposed forms"). Proposed groupings never enter the first figure.
  *Test (to write):* test_count_accepted_vs_proposed.py.
- `counts.strip.denominator-beside-every-count` — **[GAP]** (#5032 → #NEW-C7) every count and every rate has beside it
  a small strip of the pages in scope by time and by writer: read with confidence, read unsurely, unread, not held.
  It is one shared component and one field of the view data shape (`explore.panes.one-data-shape`); a rate cannot be
  rendered without it. *Test (to write):* DenominatorStripTests.swift, test_rate_payload_requires_strip.py.
- `counts.narrow.check-twenty-lines` — **[GAP]** (#6763 → #NEW-C7) beside a range the person can ask for the
  occurrences that contribute most to its width (the least sure finds, the likeliest misses), and mark each yes or
  no in the review surface; each mark replaces a chance with a fact, the term's own precision and recall replace
  the hand-wide estimate, and the range is recomputed. *Test (to write):* test_marks_narrow_the_range.py (after
  twenty marks on the fixture the range is narrower and still holds the true count).
- `counts.background.vocabulary-exists-when-pages-are-read` — **[GAP]** (#5032 → #NEW-C7) counts for every form above
  a stated frequency are computed as pages are read or corrected, as an Activity job that yields to the person's
  work and updates only what changed, so a set's vocabulary is there when the person opens it.
  *Test (to write):* test_vocabulary_updates_incrementally.py.

### C. The historian's concepts

- `concepts.record.owned-by-the-person` — **[GAP]** (#4692 → #NEW-C8) a concept has a name, a definition, what counts
  and what does not, an optional scope, and seed passages anchored to stretches of pages, all written by a person,
  and is a node in the sidebar. It is stored in the hermeneutic layer's framework and pattern records
  (`hermeneutic.concept.is-the-framework-record`), not in a new store. *Test (to write):* test_concept_record.py.
- `concepts.record.versions-are-kept` — **[GAP]** (#4692 → #NEW-C8) changing a definition, a rule or the scope makes a
  new version; earlier versions are never edited in place; each mark keeps the version it was made under, and after
  a change earlier marks are offered for re-marking, not silently reused. *Test (to write):*
  test_concept_versions.py.
- `concepts.never-proposed-by-a-model` — **[GAP]** (#4692 → #NEW-C8) no route, view or tool creates a concept, names
  one, drafts or rewrites a definition, labels a group of passages, or states that a concept is new or better than
  another. A model's account is refused on every write to a concept. *Test (to write):*
  test_model_cannot_write_a_concept.py.
- `concepts.find.candidates-ranked-with-why` — **[GAP]** (#5033 → #NEW-C9) one route takes a concept and returns
  ranked candidate passages across the set, each with the seed it is nearest to, the words it shares with it, its
  score once a ranker exists, its reading band and its stretch. The ranking is labelled as model output with the
  method and version; passages on unsure readings are held back and counted; vectors of two models are never mixed
  (`explore.meaning.same-space-only`). *Test (to write):* test_concept_candidates.py (planted instances outrank
  unrelated passages; every row names its reason).
- `concepts.marks.yes-no-unsure` — **[GAP]** (#4692 → #NEW-C9) on the concept sheet the person marks a passage yes, no
  or unsure by key or tap; each mark is one audited action by a person with undo; unsure is kept, counted, and
  teaches nothing. *Test (to write):* test_concept_marks.py, ConceptSheetMarksTests.swift.
- `concepts.sheet.is-a-reader-rendition` — **[GAP]** (#4692 → #NEW-C9) the concept sheet is the Reader's rendition of
  a selected concept: the two columns, each passage as the crop of its lines with the reading beneath, the linked
  Preview following the chosen stretch. On iPhone, one passage card at a time. *Test (to write):*
  ConceptSheetTests.swift.
- `concepts.find.near-the-line-is-always-open` — **[GAP]** (#4692 → #NEW-C10) the sheet's second column is open by
  default and holds, each under its own label: passages the ranker is least sure of, and passages like the "does
  not count" seeds that sit among the candidates. Each says in what measured respect it is close and differs.
  Where nothing was searched the column says so and never reads as "none found". *Test (to write):*
  test_concept_near_misses.py (at least half the planted near misses appear in the column).
- `concepts.find.expected-and-missing-needs-a-scope` — **[GAP]** (#4692 → #NEW-C10) when, and only when, the person
  gave a scope, the second column also lists documents inside it, of the record types where marked instances are
  found, that have none, split into read with confidence and unread or unsure. *Test (to write):*
  test_expected_and_missing.py (empty without a scope).
- `concepts.marks.sharpen-the-search-locally` — **[GAP]** (#4692 → #NEW-C11) after a stated number of marks a small
  ranker is fitted on the person's machine on their yes and no marks, in seconds, with no cloud call; one in ten
  marks is held out by the existing rule (`record.check.one-in-ten-held-out`) and never fitted on; once there are 50
  held-out marks the sheet says how many of the passages the person would accept the search finds in its first
  hundred, and before that says how many of the 50 there are. *Test (to write):* test_concept_ranker_local.py.
- `concepts.heldout.test-only-when-asked` — **[GAP]** (#4692 → #NEW-C11) when the person asks, the sheet draws a
  shuffled sample from pages set aside, the search's picks mixed with random passages, with scores absent from the
  payload until marking is done; the result is two counts, how often the picks and how often the random ones were
  accepted, and where they do not differ the sheet says it cannot tell whether the search or the concept is weak.
  It is never required and nothing ranks concepts by it. *Test (to write):* test_concept_blind_sample.py.
- `concepts.spread.rate-over-marked-against-read` — **[GAP]** (#4692 → #NEW-C12) the spread of a concept by time,
  place, record type and writer is computed over passages marked yes, as a rate against passages read, in the four
  states of `terms.sheet.when-and-where-in-four-states`, with the denominator strip. Unmarked candidates are drawn
  hollow beside them, labelled, and never summed with them. *Test (to write):* test_concept_spread.py.
- `concepts.reread.a-reader-layer` — **[GAP]** (#4692 → #NEW-C12) with a concept chosen, any document in the Reader
  shows where its ranker scores high and where it is near the line, labelled as a ranking, and marks made there are
  the same marks. A person's biography page can carry the concept as a row of the life band: the points in a life
  where passages marked yes occur. *Test (to write):* ConceptReaderLayerTests.swift.
- `concepts.term-as-evidence.two-by-two` — **[GAP]** (#4692 → #NEW-C13) the person can attach a term (optionally only
  in a slot, a period or a writer) to a concept as evidence; the link is theirs, typed and versioned. The sheet then
  shows the four cells (term and yes; term and not; yes without term; neither), which sum to the passages in scope
  and each open to them; a term's sheet lists the person's concepts that cite it. Fichero never proposes such a
  link. *Test (to write):* test_term_as_evidence_two_by_two.py.

### D. Export for citation, and the private check

- `cite.bundle.query-counts-passages` — **[GAP]** (#5034 → #NEW-C14) any counted view exports one bundle, as CSV and
  as a readable document: the query with its settings, what it was run on (date, reader and grouping versions,
  checked share), the counts with their ranges, and every passage with its line as read, its archive reference and
  its stretch. Rights rules apply as to the view. *Test (to write):* test_citation_bundle.py.
- `cite.footnote.carries-range-and-checked-share` — **[GAP]** (#5034 → #NEW-C14) the bundle includes a footnote in
  plain words with the range, its level, the number of acts or pages counted, how many lines a person checked, and
  the date; it cannot be exported with any of these removed, and a count on a model's readings says so in the
  footnote. *Test (to write):* test_footnote_form.py.
- `cite.rerun-gives-the-same-table` — **[GAP]** (#5063 → #NEW-C14) the bundle's query, kept as a saved view, re-run on
  the same library state gives the same table byte for byte. *Test (to write):* test_citation_rerun_is_identical.py.
- `counts.quality.ranges-checked-on-own-project` — **[GAP]** (#6763 → #NEW-C15) on the person's own project a panel
  shows, per hand, how often a stated range held the count a person later established by checking, with the median
  width of the ranges, and for each concept how many marks, how many in the near-the-line column and how many
  versions. It is computed on the person's machine, is in no export or publish, and is compared with nothing.
  *Test (to write):* test_range_coverage_panel.py.

## Lines of other specs built here (cited, not copied)

`kg/hermeneutic-layer.md` section D has no build order; its lines are built in the steps below, with their text and
tags left where they are: `hermeneutic.layer.only-a-person-writes`, `hermeneutic.concept.is-the-framework-record`,
`hermeneutic.reading.rests-on-a-stretch`, `hermeneutic.argument.links-evidence-and-is-the-persons`,
`hermeneutic.shown.as-the-persons-everywhere`. From `explore/tables-and-counts.md`: `explore.corpus.word-use-over-time`,
`explore.corpus.keyword-in-context`, `explore.corpus.which-reading`, `explore.corpus.ocr-quality-is-shown`.

## Build order

Engine before app; each step ships alone and is 25 files or fewer. Stage 1 needs only text and can start now.
Stage 2 ships "at least N, not yet measured" until `source/read-any-hand.md` Step 1.2 has a fit. Stage 3 needs
nothing from the knowledge graph.

### Stage 1 — The sources' terms, from text

#### Step 1.1 — The vocabulary, the concordance, and every count opening to its lines
- Behaviours: `terms.vocabulary.table-of-any-set`, `terms.concordance.every-occurrence-in-its-line`, `counts.open.every-count-opens-to-its-lines`, `explore.corpus.keyword-in-context`, `explore.corpus.which-reading`
- Tests: test_vocabulary_table.py, test_concordance_rows.py, test_term_payloads_open_and_hold_no_model_prose.py
- Size: M

→ #NEW-C1

#### Step 1.2 — Forms: variants as proposals a person accepts; unsure words make no term
- Behaviours: `terms.forms.variants-are-proposals`, `terms.forms.only-trusted-readings-make-a-term`
- Tests: test_term_variants_are_proposals.py, test_unsure_words_make_no_term.py
- Depends on: 1.1
- Size: M

→ #NEW-C2

#### Step 1.3 — The attestation sheet in the Reader, with when and where in four states
- Behaviours: `terms.sheet.one-view-for-a-term-or-a-name`, `terms.sheet.when-and-where-in-four-states`, `terms.reader.tracked-terms-layer`, `explore.corpus.word-use-over-time`, `explore.corpus.ocr-quality-is-shown`
- Tests: AttestationSheetTests.swift, test_when_and_where_four_states.py, TrackedTermsLayerTests.swift
- Depends on: 1.2
- Size: M

→ #NEW-C3

#### Step 1.4 — Company, and a shift in use shown as counts
- Behaviours: `terms.sheet.company-is-collocation-with-settings`, `terms.sheet.shift-in-use-never-in-meaning`
- Tests: test_collocation_settings_and_counts.py, test_shift_is_shown_as_counts.py
- Depends on: 1.3
- Size: M

→ #NEW-C4

#### Step 1.5 — Who writes it about whom, and the slot
- Behaviours: `terms.sheet.who-writes-it-about-whom`, `terms.sheet.the-slot-and-its-alternatives`
- Tests: test_term_who_about_whom.py, test_slot_alternatives.py
- Depends on: 1.4
- Size: M

Waits for the writer field and roles (`kg/people-and-lives.md` Step 4.2) and for formula alignment. → #NEW-C5

### Stage 2 — Counts as ranges

#### Step 2.1 — One count function: four parts, measured doubt only, no fit no range, accepted and proposed apart
- Behaviours: `counts.range.four-parts-together`, `counts.range.built-from-measured-doubt-only`, `counts.range.no-fit-no-range`, `counts.range.accepted-and-proposed-apart`
- Tests: test_count_has_four_parts.py, test_range_from_calibrated_readings.py, test_no_fit_gives_no_range.py, test_count_accepted_vs_proposed.py
- Depends on: 1.2
- Size: M

→ #NEW-C6

#### Step 2.2 — The denominator strip, "check 20 to narrow", and the vocabulary kept up in the background
- Behaviours: `counts.strip.denominator-beside-every-count`, `counts.narrow.check-twenty-lines`, `counts.background.vocabulary-exists-when-pages-are-read`
- Tests: DenominatorStripTests.swift, test_rate_payload_requires_strip.py, test_marks_narrow_the_range.py, test_vocabulary_updates_incrementally.py
- Depends on: 2.1
- Size: M

→ #NEW-C7

### Stage 3 — The historian's concepts

#### Step 3.1 — The concept record: owned, versioned, never written by a model
- Behaviours: `concepts.record.owned-by-the-person`, `concepts.record.versions-are-kept`, `concepts.never-proposed-by-a-model`, `hermeneutic.layer.only-a-person-writes`, `hermeneutic.concept.is-the-framework-record`
- Tests: test_concept_record.py, test_concept_versions.py, test_model_cannot_write_a_concept.py
- Size: M

Engine only. → #NEW-C8

#### Step 3.2 — Candidates with why, marks, and the concept sheet
- Behaviours: `concepts.find.candidates-ranked-with-why`, `concepts.marks.yes-no-unsure`, `concepts.sheet.is-a-reader-rendition`, `hermeneutic.reading.rests-on-a-stretch`
- Tests: test_concept_candidates.py, test_concept_marks.py, ConceptSheetMarksTests.swift, ConceptSheetTests.swift
- Depends on: 3.1
- Size: M

→ #NEW-C9

#### Step 3.3 — Near the line, and expected and missing
- Behaviours: `concepts.find.near-the-line-is-always-open`, `concepts.find.expected-and-missing-needs-a-scope`
- Tests: test_concept_near_misses.py, test_expected_and_missing.py
- Depends on: 3.2
- Size: M

→ #NEW-C10

#### Step 3.4 — Marks sharpen the search on this machine; the blind sample when asked
- Behaviours: `concepts.marks.sharpen-the-search-locally`, `concepts.heldout.test-only-when-asked`
- Tests: test_concept_ranker_local.py, test_concept_blind_sample.py
- Depends on: 3.2
- Size: M

→ #NEW-C11

#### Step 3.5 — The spread, and rereading with a concept
- Behaviours: `concepts.spread.rate-over-marked-against-read`, `concepts.reread.a-reader-layer`, `hermeneutic.shown.as-the-persons-everywhere`
- Tests: test_concept_spread.py, ConceptReaderLayerTests.swift
- Depends on: 3.4, 2.2
- Size: M

→ #NEW-C12

#### Step 3.6 — A term as evidence for a concept; the person's argument linked to its evidence
- Behaviours: `concepts.term-as-evidence.two-by-two`, `hermeneutic.argument.links-evidence-and-is-the-persons`
- Tests: test_term_as_evidence_two_by_two.py, test_argument_links_evidence.py
- Depends on: 3.2, 1.3
- Size: M

→ #NEW-C13

### Stage 4 — Citing, and the private check

#### Step 4.1 — The citation bundle, its footnote, and the identical re-run
- Behaviours: `cite.bundle.query-counts-passages`, `cite.footnote.carries-range-and-checked-share`, `cite.rerun-gives-the-same-table`
- Tests: test_citation_bundle.py, test_footnote_form.py, test_citation_rerun_is_identical.py
- Depends on: 2.1
- Size: M

Waits for the saved-view record (#5063). → #NEW-C14

#### Step 4.2 — How well the ranges held, on this project only
- Behaviours: `counts.quality.ranges-checked-on-own-project`
- Tests: test_range_coverage_panel.py
- Depends on: 2.2
- Size: S

→ #NEW-C15

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | counts equal hand counts on a keyed fixture; ranges; the four states; variants as proposals; the concept record and its refusals; candidates, near misses, the two-by-two; the bundle and its re-run | the files named above |
| Pure rule (Swift) | y | the sheet's parts, the strip, marks, labels on every ranking | the Swift files named above |
| MCP | y | vocabulary, concordance, counts and a concept's passages are read tools; every write to a concept is refused to a model's account | `fichero-mcp/tests/test_mcp_generated.py` |
| Click-around (XCUITest, Mac) | y | a count opens its lines, a line opens its page; a mark is made by key | to write |
| iPhone / iPad | y | the sheet's parts and the passage cards by touch | to write |
| Load | y | the vocabulary of 50,000 pages in bounded queries; background counts yield to the person | to write |

Hard-gate once approved: every count opens to its lines; no payload holds text a model composed; no write to a
concept by a model's account.

## Open questions for the owner

1. **Is a concept its own sidebar node** (recommended) or a kind of saved search?
2. **A cloud ranker.** May a cloud model rank candidates on a library that allows the cloud? Recommended: local by
   default; a cloud ranker only when asked for, labelled, since it adds little over local vectors plus marks.
3. **"What have I not covered?"** The review weighed listing groups of alike passages that no concept touches, and
   dropped it, since a cluster is a model's claim. This spec shows only the share of pages no concept touches.
   Is that the right place for the line?
4. **Order within the milestone.** Stage 1 (terms from text) needs nothing unbuilt and Stage 3 (concepts) needs
   nothing from Stage 2. Recommended: Stage 1, then Stage 3 beside Stage 2.
5. **Lemmas.** Rates split across inflected forms until historical languages have word-level normalisation. Should
   Stage 1 wait for that, or ship on written forms with groupings a person accepts (recommended)?
6. **The level of a range.** 90% is proposed. Is one level for the whole app right?
