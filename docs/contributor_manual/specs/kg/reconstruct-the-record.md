# Reconstruct the record — one graph of people, places and events across archives, measured on its own check set — Design Spec (#5340, #5545)

> Milestone: reconstruct-the-record
> Spec: kg/reconstruct-the-record.md
> Manual: TBD — a "The same person in two archives" section: how Fichero proposes that a name in one archive and a name
> in another are one person, place or event, what evidence it shows, that the person decides and nothing is merged
> for them, what the figures beside a proposal mean and where they come from, and how a gap in the record becomes
> something to look for.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-21** (from the owner's ruling of 2026-11-21 on the flagship
> review; the owner approves). One of two flagship goals that run in parallel; the other is
> `source/read-any-hand.md`. Facts read from `origin/integration` 2b271cfbc5 and from the "Measured" sections of the
> knowledge-graph specs; nothing run. This spec is deliberately thin. `explore/connections-across-corpora.md` owns the
> METHODS that propose a connection (`xcorpus.*`); `kg/kg-confidence-and-provenance.md` owns what a confidence means,
> a person's decision as a state, and the sets and scorers for names, statements and linking inside one project
> (`kg.teach.*`, `kg.confidence.*`); `kg/kg-entities-and-statements.md` owns the records. This file owns THREE things:
> the check set that says whether a cross-archive graph is right, which comes first; the measures and the gate read
> from it; and the three things only a cross-archive graph has (identity across archives, events, and the gaps the
> surviving record implies). It is also where `xcorpus.*` lines get their build steps: that spec has none.
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists in part · **[GAP]** designed, not built · **[BROKEN]** built and
> contradicting the line. Every non-[OK] line cites an issue; "→ #N" is an issue filed on
> this milestone.

## Ruled 2026-11-21 (owner; paraphrased)

1. **In parallel with Read any hand.** The review recommended this as a second act that waits for reading to work.
   The owner ruled both at once. What makes that safe is section D: the graph reads each line's calibrated confidence
   as soon as there is one, and until then says its figures rest on unmeasured readings.
2. **Its own check set.** The graph cannot be evaluated today; a set of decisions it is measured against comes before
   any method is built or tuned.
3. **Truth is what people decide as they work**, with a frontier model where no person has decided, labelled. One in
   ten of a person's decisions is held out, silently, and never trained or tuned on.

## Intent (the design)

A historian's sources are scattered: the same merchant appears in a notary's register in one archive, a ship's
manifest in a second and a court case in a third, spelled three ways in two languages. The record of an event is the
sum of what survives about it, and much does not survive. Fichero should hold **one graph across the archives a
person works with** in which a person, a place and an event are each one thing with everything said about them, from
every source, each statement resting on a stretch of a page a person can open. Every join between two archives is a
proposal with its evidence that a person accepted. Nothing is merged for them. And the graph should say what it
implies is missing: the register number that is skipped, the party named in an act that is not held.

Whether such a graph is right is a harder question than whether a page is read right: truth is scarce and
contestable. So the first thing built is not a method but a check set, and every later step is judged against it.
Measured today (2026-11-20, `kg/kg-confidence-and-provenance.md`): on the free tier two people in three are right, one
organisation in four, and 121 of 133 statements are a bare mention; the confidences are constants.

## Prior art (what we adopt)

- **The factoid model and prosopography databases.** A statement is what a source says, kept with its source; a
  person is the set of factoids about them. Identity across sources is an assertion with evidence, never a merged
  record. Fichero's claims already work this way.
- **Record linkage** (Fellegi and Sunter 1969; Christen 2012): block candidates cheaply, score pairs, decide with
  thresholds measured on labelled pairs, and report pairwise precision and recall with a cluster measure (B-cubed,
  Bagga and Baldwin 1998), because pairwise figures alone reward one giant cluster.
- **Dating and placing from parallels.** Models that restore, date and place inscriptions by retrieving similar texts
  show their parallels as evidence. Dated acts label themselves, so truth for dating is nearly free.
- **Events** in CIDOC-CRM and the Simple Event Model: an event has participants, a time-span and a place, and is
  distinct from the documents that witness it.

## What exists today (read 2026-11-21)

- **Inside one project:** names and statements with page provenance (`kg.store.two-tables-are-the-record` [OK]);
  spelling variants (`knowledge/dedupe.py` `spelling_key`); authority links (`knowledge/authorities.py`); agreement
  and contradiction across sources (`knowledge/triangulation.py`, tested in
  `fichero-server/tests/unit/kg/test_triangulation.py`); merges proposed and audited.
- **Sets and scorers designed, not built:** `kg.names.measured`, `kg.teach.names-scorer`,
  `kg.teach.statements-set-and-scorer`, `kg.teach.linking-set-and-scorer`, `kg.confidence.calibrated-on-the-check-set`
  (all [GAP]). The names and statements prompts carry no version (`kg.names.prompt-is-versioned` [GAP] #6278), so a
  figure could not yet be tied to what produced it.
- **Across archives: nothing.** `explore/connections-across-corpora.md` is fifteen behaviours, all [GAP], with no
  build order and a test matrix "to be filled".
- **No event record.** A date and a place are qualifiers of a statement (`kg/kg-confidence-and-provenance.md`
  section H); nothing groups statements into an event.

## The design

### The check set comes first

The check set is a set of **decisions a person made**, each about something small enough to be right or wrong:

| Kind | The decision | Where it comes from |
|---|---|---|
| name | this stretch is a person, a place, an organisation or an event, or is not a name | `kg.teach.page-is-checked-for-names` |
| statement | this statement is what the stretch says, or is not | `kg.teach.statements-set-and-scorer` |
| pair, inside an archive | these two names are one thing, are two, or cannot be told | `kg.teach.linking-set-and-scorer` |
| pair, across archives | the same, for names in two archives | this spec |
| event | these statements, from one source or several, are about one event | this spec |
| date and place of a document | written on it, so read, not judged | this spec |

It is not a second store: each row is read from the state and the audit a person's action already leaves
(`kg.confidence.decision-is-a-state`). What this spec adds is how the set is seeded, what is held out, and the three
kinds no other spec has.

**Seeding on purpose.** Decisions made in passing are the easy ones. Version 0 is seeded: about ten corrected pages
per archive (`kg.names.measured`), and 200 cross-archive pairs drawn by a script so that the set has hard cases: a
third from candidates near where a method would draw its line, a third that share a spelling key and differ in
context, a third at random. The person answers same, different or cannot tell; "cannot tell" is kept and counted,
never forced.

**Held out.** One in ten of a person's decisions of each kind is held out, silently, by a hash of the decision's id
and a per-project salt. A held-out decision never trains a tagger, an extractor or a matcher, never sets a threshold,
and is never an example in a prompt. As in `source/read-any-hand.md`, held-out decisions are cut into a fit half
(calibration, thresholds) and a report half (every figure shown). Under 50 held-out decisions of a kind, no figure of
that kind is shown: the app says how many there are of the 50.

**Open and private.** A small open part (pairs from open-licensed parallel sets, which is the fixture
`explore/connections-across-corpora.md` names in its test matrix) is committed and runs in the tests. A project's own
decisions stay in its library.

### The measures and the gate

Per method and version (a tagger, a model and prompt version, a matcher's rule set), on the report half: names by
type, precision and recall (owned by `kg.teach.names-scorer`); statements supported by their stretch, and the share
that are bare mentions; pairs, inside an archive and across archives separately, by pairwise precision and recall and
by B-cubed; events, by the share of a checked event's statements that were grouped and the share of grouped
statements that belong; dates by the error in years against the written date with the date hidden, and places by the
share right at the level the gazetteer resolves. One report per run. A method's proposals are offered by default only
once it passes the project's bar on the report half; **no method ever accepts its own proposal**, at any figure.

### Identity across archives

An archive here is any named set (`xcorpus.compare.named-sets`). A cross-archive identity is a proposed link
(`xcorpus.link.proposed-with-evidence`) between two names that stay two records, each in its own library or folder.
Candidates are blocked (spelling key, authority record, transliteration) and scored on shared context: dates that
overlap, places in common, roles, and the other people both appear with. Accepted, it is a typed same-as link that
every graph view and query follows; rejected, it is remembered and never proposed again
(`kg.resolve.decision-remembered`). It can be undone, and undoing it separates everything that was joined through it.

### Events

An event is a node that groups statements, from one source or several, that a person or a method says are about the
same happening, with a time-span and a place carried up from the statements' qualifiers and the evidence under each.
Statements that contradict each other stay in the event, side by side, with their sources: the contradiction is the
finding. An event proposed by a method is a proposal like any other.

### What the record implies is missing

From what survives, some of what does not can be named: a numbered series with a number absent; an act that cites
another by date and notary that is not held; a party who appears once in a role that normally leaves a second trace.
Each is an **inference**, kept as one with the claims it rests on, shown in a list a person reads, and never a
statement about the world. A person can turn one into a lead for research (`ui/research-operations.md`), which is how
this graph feeds the finding of sources.

### Resting on the reading

Every name and statement rests on words, and every word will have a calibrated confidence
(`hands.calib.fitted-per-hand-and-shown`). A name's or statement's own confidence is capped by the confidence of the
words it rests on; a name read from words in the unsure bands is not offered as a candidate for a cross-archive link
and never seeds a search. Until a hand has a fit, figures say "reading not yet measured" beside them.

## Behaviours

### A. The check set

- `record.check.is-read-from-decisions` — **[GAP]** (#5545 → #6979) the check set is the decisions of the six kinds in
  the design's table, each with who decided, when, the stretch or the pair it is about and the archive of each side,
  read from the states and audit rows a person's actions already leave and from no second store. A model's write is
  never a decision. One function returns the set for a project and a kind, and every scorer and every fit calls it.
  *Test (to write):* test_check_set_from_decisions.py (three merges, one split, one rejected proposal and one
  cross-archive accept give six pair rows with their truth; a machine actor's accept is not in the set).
- `record.check.seeded-with-hard-cases` — **[GAP]** (#5545 → #6979) a script draws the pairs a person is asked to
  decide for version 0: 200 cross-archive pairs, a third near the matcher's line, a third sharing a spelling key and
  differing in context, a third at random, with the draw's seed kept. The person answers same, different or cannot
  tell in the review surface (`ui/review-names-and-statements.md`), and "cannot tell" is a kept answer that is counted
  and scored as neither. *Test (to write):* test_check_set_seed_draw.py (the three thirds; the seed repeats the draw).
- `record.check.one-in-ten-held-out` — **[GAP]** (#5545 → #6980) one in ten of a person's decisions of each kind is
  held out by a hash of the decision id and a per-project salt, silently: no response, row or view says which. A
  held-out decision is never in a training set, a threshold fit's report half, or a prompt; held-out decisions are
  cut into a fit half and a report half as `hands.heldout.fit-half-and-report-half` cuts pages. Under 50 held-out
  decisions of a kind no figure of that kind is shown, and the app says "N of 50 checked". *Test (to write):*
  test_check_set_held_out.py (1,000 decisions give 100 within the binomial band; a trainer's set has none of them;
  49 decisions show no figure).
- `record.check.open-part-is-a-fixture` — **[GAP]** (#5341 → #6979) the open part of the check set (pairs and
  parallel passages from open-licensed sets, with their licences) is a committed fixture the tests run on, and is the
  fixture `explore/connections-across-corpora.md`'s test matrix asks for. No decision from a person's library is ever
  written to the repository. *Test (to write):* test_check_set_open_fixture.py.
- `record.check.model-answers-are-labelled` — **[GAP]** (#5545 → #6980) where a frontier model, not a person, answered
  a pair or a statement, the row is labelled model-checked, its figures are called agreement and are never summed
  with person-checked ones, and the call obeys the library's cloud answer (`llm/egress.py` `require_project_yes`).
  *Test (to write):* test_check_set_model_checked_is_apart.py.

### B. The measures and the gate

- `record.measure.pairs-and-clusters` — **[GAP]** (#5545 → #6981) a matcher is scored on the report half by pairwise
  precision and recall and by B-cubed precision and recall, for pairs inside an archive and across archives
  separately, per method and version. The inside-archive pair set and its scorer are `kg.teach.linking-set-and-scorer`;
  this line adds the cross-archive cut and the cluster measure. *Test (to write):* test_pairs_and_clusters_scorer.py
  (one giant cluster scores high pairwise recall and low B-cubed precision).
- `record.measure.statements-stand-on-their-stretch` — **[GAP]** (#5545 → #6981) the report gives, per extractor and
  version, the share of statements whose quoted stretch is on the page it names (after whitespace and diacritic
  normalisation), the share a person judged right, and the share that are a bare mention. *Test (to write):*
  test_statements_report.py.
- `record.measure.events-grouped` — **[GAP]** (#5545 → #6982) for each checked event the report gives the share of
  its statements a method grouped together and the share of the method's group that belongs to it. *Test (to
  write):* test_events_scorer.py.
- `record.measure.date-and-place-against-the-written` — **[GAP]** (#5545 → #6983) a method that proposes a document's
  date or place is scored on documents whose written date and place a person confirmed, with those hidden from the
  method: the median error in years and the share within five and within twenty-five; the share of places right at
  the gazetteer's level. *Test (to write):* test_date_and_place_scorer.py.
- `record.measure.one-report-and-a-gate` — **[GAP]** (#5545, #6278 → #6981) each run of a method writes one report
  row with the method, its version (the prompt version of `kg.names.prompt-is-versioned` where a model was asked), the
  counts and the figures. A method's proposals are offered by default in a project only once its report-half figure
  passes the project's bar; before that they are offered only when asked for and say "not yet measured here". No
  figure lets a method accept its own proposal. *Test (to write):* test_method_gate.py (a method under the bar is not
  offered by default; a machine actor cannot accept).

### C. Across archives

- `record.link.blocked-then-scored-on-context` — **[GAP]** (#3323 → #6984) cross-archive candidates are blocked by
  spelling key, authority record and transliteration (`histnorm.entities.cross-script-candidates`), then scored on
  shared context: overlapping dates, places in common, roles and co-occurring people, each named in the proposal's
  evidence with the stretch it came from. The work is one bounded query per block, never every pair
  (`kg/kg-store-and-query.md` section C). *Test (to write):* test_cross_archive_candidates.py (two archives of
  made-up names: the shared-context pair outranks the same-name stranger).
- `record.link.same-as-joins-and-never-merges` — **[GAP]** (#5341 → #6984) an accepted cross-archive identity is a
  typed same-as link between two names that stay two records in their own archives. The neighbourhood, the tables
  and a path follow it and say they did; undoing it separates what it joined; a rejected pair is remembered. No
  action merges two records across archives. *Test (to write):* test_same_as_across_archives.py (accept, read through,
  undo; the two records' ids never change).
- `record.event.groups-statements-and-keeps-contradiction` — **[GAP]** (#5032 → #6982) an event is a node grouping
  statements from one source or several, with a time-span and a place taken from their qualifiers and the evidence
  under each; statements that contradict stay in it side by side (`knowledge/triangulation.py`). A method's event is a
  proposal a person accepts; a person can make one by hand from a selection of statements. *Test (to write):*
  test_event_groups_statements.py.
- `record.gap.implied-records-are-inferences` — **[GAP]** (#5032 → #6985) the graph lists what the surviving record
  implies is missing (a number absent from a series, an act cited and not held, a role with no second trace), each as
  an inference naming the claims it rests on and the rule that found it, never as a statement. A person can dismiss
  one, or make it a lead in a research folder (`research.ops.learn.kg-proposes-terms`, `ui/research-operations.md`).
  *Test (to write):* test_implied_gaps.py (a series 1 to 10 without 7 lists 7 once, with the nine claims it rests on).
- `record.date.proposed-from-parallels` — **[GAP]** (#5341 → #6983) an undated document gets a proposed date range and
  place from its nearest dated parallels (shared formulae, names and hand), shown with the parallels as evidence and
  stored as a qualifier with the basis `inferred` (`kg/kg-confidence-and-provenance.md` section H), never as a written
  date. *Test (to write):* test_date_from_parallels.py.

### D. Resting on the reading

- `record.confidence.capped-by-the-reading` — **[GAP]** (#6763 → #6986) a name's or a statement's confidence is never
  above the calibrated confidence of the words it rests on (`hands.calib.fitted-per-hand-and-shown`); where the hand
  has no fit yet, the figure carries "reading not yet measured" and is exempt from no threshold. *Test (to write):*
  test_confidence_capped_by_reading.py.
- `record.confidence.unsure-readings-seed-nothing` — **[GAP]** (#6763 → #6986) a name read from words in the unsure
  or not-read band is not a candidate for a cross-archive link, an event or an implied gap, and never seeds a search
  term; the proposal list says how many names were left out for this. *Test (to write):*
  test_unsure_names_are_not_candidates.py.

## Lines of other specs built here (cited, not copied)

`explore/connections-across-corpora.md` has no build order. These of its lines are built in this spec's steps, with
their text and tags left where they are: `xcorpus.compare.named-sets`, `xcorpus.link.proposed-with-evidence`,
`xcorpus.link.person-decides`, `xcorpus.link.entities-across-languages`, `xcorpus.link.same-hand`,
`xcorpus.method.says-its-limits`. Its other lines (parallel passages, words over time, shared structure, the
known-and-unknown aids, training on several corpora) stay in the `explore` milestone.

## Build order

Stage 0 starts now, in parallel with `source/read-any-hand.md` Stage 0, and changes no model: it makes the check set
and measures the graph as it is. Each step is 25 files or fewer.

### Stage 0 — The check set, and the graph measured as it is

#### Step 0.1 — The set read from decisions; the seed draw; the open fixture
- Behaviours: `record.check.is-read-from-decisions`, `record.check.seeded-with-hard-cases`, `record.check.open-part-is-a-fixture`
- Tests: test_check_set_from_decisions.py, test_check_set_seed_draw.py, test_check_set_open_fixture.py
- Size: M

Engine only: one function over the states and audit rows that exist, the draw script, the fixture. No new table. About
12 files.

#### Step 0.2 — One in ten held out; a model's answers kept apart
- Behaviours: `record.check.one-in-ten-held-out`, `record.check.model-answers-are-labelled`
- Tests: test_check_set_held_out.py, test_check_set_model_checked_is_apart.py
- Depends on: 0.1
- Size: S

The same hash and the same two halves as `source/read-any-hand.md` Step 1.1; whichever lands first owns the function.

#### Step 0.3 — The baseline report: pairs, clusters, statements, and the gate
- Behaviours: `record.measure.pairs-and-clusters`, `record.measure.statements-stand-on-their-stretch`, `record.measure.one-report-and-a-gate`
- Tests: test_pairs_and_clusters_scorer.py, test_statements_report.py, test_method_gate.py, fichero-server/tests/unit/kg/test_kg_dedupe.py
- Depends on: 0.2
- Size: M

Today's matcher and extractor scored as they are. This is the figure every later step must beat.

### Stage 1 — First tasks: dating, placing and the same hand

#### Step 1.1 — A date and a place proposed from parallels, scored against the written ones
- Behaviours: `record.date.proposed-from-parallels`, `record.measure.date-and-place-against-the-written`
- Tests: test_date_from_parallels.py, test_date_and_place_scorer.py
- Depends on: 0.3
- Size: M

#### Step 1.2 — The same hand across collections
- Behaviours: `xcorpus.link.same-hand`, `xcorpus.method.says-its-limits`
- Tests: test_same_hand_across_collections.py
- Depends on: 0.3
- Size: M

Uses the line-picture vectors of `hands.index.nearest-hand-starts-the-new-one` (`source/read-any-hand.md` Step 2.2)
and waits for it.

### Stage 2 — Identity across archives

#### Step 2.1 — Named sets compared; candidates blocked, then scored on context
- Behaviours: `xcorpus.compare.named-sets`, `xcorpus.link.entities-across-languages`, `record.link.blocked-then-scored-on-context`
- Tests: test_cross_archive_candidates.py, fichero-server/tests/unit/kg/test_variant_spellings_to_spec.py
- Depends on: 0.3
- Size: M

#### Step 2.2 — The proposal, the person's decision, and same-as that never merges
- Behaviours: `xcorpus.link.proposed-with-evidence`, `xcorpus.link.person-decides`, `record.link.same-as-joins-and-never-merges`
- Tests: test_same_as_across_archives.py, CrossArchiveProposalTests.swift
- Depends on: 2.1
- Size: M

#### Step 2.3 — Confidence rests on the reading
- Behaviours: `record.confidence.capped-by-the-reading`, `record.confidence.unsure-readings-seed-nothing`
- Tests: test_confidence_capped_by_reading.py, test_unsure_names_are_not_candidates.py
- Depends on: 2.1
- Size: S

Waits for `source/read-any-hand.md` Step 1.2 (the fit). Until then the "reading not yet measured" label is what ships.

### Stage 3 — Events, and what is missing

#### Step 3.1 — Events group statements and keep their contradictions
- Behaviours: `record.event.groups-statements-and-keeps-contradiction`, `record.measure.events-grouped`
- Tests: test_event_groups_statements.py, test_events_scorer.py, fichero-server/tests/unit/kg/test_triangulation.py
- Depends on: 2.2
- Size: M

#### Step 3.2 — What the record implies is missing, as inferences that can become leads
- Behaviours: `record.gap.implied-records-are-inferences`
- Tests: test_implied_gaps.py
- Depends on: 3.1
- Size: M

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | the set from decisions, the draw, the hold-out, the scorers, the gate, same-as and its undo, events, gaps | the files named above |
| Pure rule (Swift) | y | a proposal shows both stretches and its evidence; Accept and Reject by the Mail rule; no verb merges across archives | CrossArchiveProposalTests.swift (to write) |
| MCP | y | the check-set report and the proposals are read tools; accept is refused to a model's account | `fichero-mcp/tests/test_mcp_generated.py` |
| CLI | n | — | — |

## Open questions for the owner

1. **Who answers the 200 seeded pairs?** Recommended: whoever is working those archives, a few a day in the review
   surface; a frontier model first where the library allows the cloud, labelled, so the hard third is found sooner.
2. **Where does the cross-archive graph live** when two archives are two libraries? Recommended: the same-as links
   live in a comparison node of the library the person is working in (as `explore/connections-across-corpora.md`'s
   open question 1 recommends), and each archive's records never leave their library.
3. **The bar.** What figure on the report half lets a method's proposals be offered by default? Recommended: pairwise
   precision 0.9 across archives; until a project has 50 held-out pairs, nothing is offered by default.
4. **Events as a type of name or a record of their own?** Recommended: a name of type event (the type exists) plus a
   grouping link to its statements, so no third record is added.
