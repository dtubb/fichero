# People and lives — the person record, the biography page and the stitch bench — Design Spec (#5340, #5545)

> Milestone: people-and-lives
> Spec: kg/people-and-lives.md
> Manual: TBD — a "People in your archive" section, written for a historian: how to start from a name and read
> everything the sources say about that person; how Fichero proposes that two names are one person and what it shows
> as its reasons; that the person decides and can always undo; how to read the biography page (every line opens its
> page, sources that disagree stand side by side, empty years are shown); how to export a life with its citations;
> and what Fichero does about people who may still be alive.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-21** (from the owner's rulings of 2026-11-21 on people,
> biography and concepts; the owner approves). Nothing here is built unless tagged [OK]. This spec is one of a pair
> with `explore/concepts-and-terms.md`, and both sit inside Explore (`explore/explore.md`): they are ways to explore
> an archive, and they obey that file's rules. It rests on `kg/reconstruct-the-record.md`, which owns the check set,
> the measures, cross-archive candidates and the same-as link; on `kg/kg-entities-and-statements.md`, which owns the
> records; on `kg/kg-confidence-and-provenance.md`, which owns what a confidence means; on
> `kg/kg-paragraph-realisation.md`, which owns how a statement becomes a sentence by rule; and on
> `kg/ontological-layer.md`, which owns the kinds of thing and relation. This file owns what a historian sees and
> does with a PERSON: the record, the page, the bench and the views.
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists in part · **[GAP]** designed, not built · **[BROKEN]** built and
> contradicting the line. Every non-[OK] line cites an issue; "→ #NEW-Pn" is an issue the manager is asked to file on
> this milestone, one per build-order step.

## The problem, stated plainly

An archive recorded people in fragments: a name in a baptism here, the same person as a witness there, as a debtor
in a third book held in another archive, spelled differently each time. **Reconstructing the people the archive
recorded, from those fragments, across sources and archives** (which mentions are one person; who was whose parent,
spouse, child, witness or owner; what happened in a life) is one of history's oldest unsolved problems. By hand it
takes a scholar or a team years to decades for one community of a few thousand people. So it has been done for a
handful of well-kept places, and most of the people the record kept, above all those it kept least well, stay
invisible. This feature is how a historian solves that problem for their own archive.

## Exploring your archive: people (for a historian)

This is a way to explore your own archive, starting from a person.

You begin anywhere: a name you typed, a name you noticed on a page, a place, a term, or a document you are reading.
From a name you open that person's page. It is a biography put together from fragments: a baptism in one register,
a sale in a notary's book, a mention as a witness in a court case held somewhere else. Each line on the page is
something a source says, and one click on any line opens the page image with the words lit. Where two sources
disagree (a birth year, a spouse's name, a price) you see both, side by side, with their pages. Where the record
says nothing for twenty years, you see twenty empty years, not a smooth story.

From the person you walk outward. Their parents, spouse, children, the people who witnessed for them, the people
they owned or were owned by, the places they were written down in, the offices that wrote about them, the words
the sources used for them: each is a step, and each step opens the lines it rests on. You can go on to another
person's page, to a term's page (`explore/concepts-and-terms.md`), to a place, or back to a document.

Fichero's part is the fetching and the bookkeeping. It reads the handwriting, gathers the spellings of a name, and
proposes that two entries may be the same person, showing you why: the dates fit, they share a spouse, the same
three neighbours appear beside both. It also shows what speaks against it. You say same, different or cannot tell.
What you decide is kept, can be undone, and is the truth the app works from. Fichero never writes the biography's
argument, never decides who someone was, and never hides a doubt to make the page read better.

## Ruled 2026-11-21 (owner; paraphrased)

1. **It is both the grand problem and the feature.** Recovering the people an archive recorded, from fragments
   scattered across sources and archives, is the huge, old problem stated above, and Fichero takes it on as
   something a historian uses on their own archive, which is how it gets solved: one archive at a time, by the
   person who knows it. There is no public benchmark, no contest, no steward, no published score and no target
   figure that declares it solved.
2. **The first visible form is a very good biography page per person**, put together from fragments: every line a
   sourced statement one click from the page image; uncertainty, conflicting sources and gaps shown, never hidden.
3. **The design rule.** Historians distrust a machine that does the thinking. A view shows what is IN the sources
   and is built from counted, reproducible facts. A model does only mechanical jobs that can be checked (reading
   handwriting, grouping spelling variants, proposing a same-person link, ranking), each labelled as model output,
   with its confidence, one click from the evidence. The person accepts or rejects; their corrections are the truth.
4. **Measurement stays private.** Quality figures exist only as checks a person can see on their own project (for
   example, how many proposed links they accepted, later undid, or left unsure). They are never published and never
   compared.

What this supersedes: the review this spec draws on proposed a public benchmark with held-out communities, an outside
steward, a leaderboard and numbers for "solved". None of that is specified here or anywhere. The check set of
`kg/reconstruct-the-record.md` stays, as a private instrument.

## Intent (the design)

A person in Fichero is not a row that a model filled in. A person is **the set of places on pages where someone is
named or pointed at, that a historian has agreed are one human being**, plus what those places say. Three things
follow.

**The join is always visible.** Putting two mentions together is a link with reasons. It is proposed by a rule or a
model, labelled as such, decided by the person, and drawn on every view as a stitch that can be cut. Cutting it
separates exactly what it joined. A wrong join is the main way a reconstruction misleads, so no view may hide one.

**The page is made of what the sources say.** A line of the biography is a statement that rests on a stretch of a
page and that a person wrote or accepted, or it is a plain attestation ("named as witness in this act, on this
date"). Sentences are made by rule from the statement (`kg/kg-paragraph-realisation.md`); no model writes prose
about a life. What a model proposed and nobody has checked is listed apart, labelled, and counts for nothing.

**Doubt and absence are content.** A line says how sure the reading under it is. Two sources that disagree stand
side by side. An unreviewed join is marked. Years with no attestation are drawn empty, and the page says whether the
archive holds anything for those years at all.

## Prior art (what we adopt)

- **The factoid model of prosopography.** A statement is what one source says about a person, kept with its source;
  a person is the set of such statements; identity is asserted, with evidence, and can be withdrawn. Adopted whole.
- **Family reconstitution and nominal record linkage.** Decades of hand method: decide identity from the fit of two
  lives (dates, kin, neighbours, place), not from the likeness of two spellings. The stitch bench shows that fit.
  The blocking and scoring of candidates is `record.link.blocked-then-scored-on-context`.
- **Scholarly biographical dictionaries and regests.** An entry is short, ordered by life events, and every clause
  has a reference. Adopted as the page's shape. Deliberately different: conflicts are not resolved in the entry.
- **Life-course charts** for one person along time (`explore.time.life-course`), with spans for uncertain dates.
- **What we do not adopt:** generated biography. A fluent paragraph written by a model is the thing the design rule
  forbids, however well it is footnoted.

## What exists today (read 2026-11-21)

- Names and statements with page provenance; spelling keys and merge proposals inside one project; a decision is
  remembered and audited (`kg.resolve.decision-remembered` [OK]); corrections override (`kg.confidence.corrections-override`
  [OK]).
- An entity-readable route that returns sentences with the statements under each (`kg.read.biography` [PARTIAL]) and
  the rule that every sentence is sourced (`kg.read.every-sentence-sourced` [OK]). It does not yet respect a person's
  rejection (`kg.para.rejected-never-stated`), has no sections, shows no conflict and no gap.
- The Inspector for one name (`kg/kg-entity-inspector.md`), whose statement rows open the page.
- Not there: a mention as the one tie between a name and a page (`kg.one.mention-is-the-link` [GAP]); merge and split
  reachable with undo (`kg.resolve.merge-and-split-have-a-door` [GAP]); relations between people as typed links;
  anything across archives; any view of one life along time (`explore.time.life-course` [GAP]).
- Measured (2026-11-20, `kg/kg-confidence-and-provenance.md`): on the free tier two people in three are right as
  names, and 121 of 133 statements are a bare mention. So today an honest page is mostly attestations, and this
  design is built to be useful in that state.

## The design

### The person record

| Part | What it is | Who makes it |
|---|---|---|
| mention | a stretch of a page where a person is named or pointed at ("the said widow", "his son") | the reader and the tagger propose; a person corrects |
| person | the mentions a person agreed are one human being, with the forms of the name as written | links accepted by a person; identical forms joined by a stated rule |
| link | "these two mentions (or two persons) are the same", with its reasons, its maker and its state | proposed by a rule or a model, labelled; decided by a person |
| relation | a typed tie between two persons (parent, spouse, child, witness for, owner of, and the project's own types), resting on statements | a person, or a proposal a person accepts |
| statement | what one source says, on a stretch | as `kg/kg-entities-and-statements.md` |

A link has four states: proposed, accepted, rejected, cannot tell. "Cannot tell" is a kept answer. Accepting,
rejecting, splitting and merging are each one audited action with undo, and each is a row of the check set
(`record.check.is-read-from-decisions`). Across archives a link never merges two records
(`record.link.same-as-joins-and-never-merges`).

People who are written only through someone else ("wife of", "a servant of", a child with no name) are persons too.
They are kept with the words that point at them and are not discarded for lacking a name.

### The biography page

The Reader rendition of a selected person (`explore.panes.one-thing-is-a-rendition`). From top to bottom:

1. **Names as written.** Every form of the name, as crops of the written word, grouped; a proposed form is marked.
2. **The life band.** One line of time with every dated attestation as a span as wide as its date is uncertain, one
   row per archive or series, empty years left empty. It is the page's table of contents: choose a span and the
   sections below scroll to it.
3. **Sections by life event**, in the order the sources date them: birth or baptism, kin, marriage, work and office,
   property, dealings at law, movement, death and burial, and "other mentions". The section list is the ontological
   layer's event kinds; a project can add its own.
4. **Relations.** Parents, spouses, children, then witnesses, owners and the project's own types, each a row that
   names the other person, the sources' own word for the tie, and the lines it rests on.
5. **Undated and unplaced**, counted, never dropped.
6. **Proposed, not checked.** Statements and links a model or a rule proposed, hollow, labelled, apart.
7. **How this page was put together.** The joins it stands on, each with its state and maker, and what was left out
   (rights, unsure readings) with counts.

Every line carries a small mark for its reading (the four bands of `hands.calib.four-bands-in-the-reader`, or "reading
not yet measured"), its source reference, and opens its page on one click. Where two or more sources speak to the
same point and differ, the section shows each value on its own line, bracketed together, in the sources' words; the
page never picks one. A person may write their own reading of the conflict; it is stored as theirs in the
hermeneutic layer (`kg/hermeneutic-layer.md`) and drawn as theirs.

### The stitch bench

Where same-person proposals are decided, fast, with the evidence. Two lives (or three) are laid one above the other
on one time axis. Between them is the fit: a tie for each thing they share (a co-named person, a place, a role, a
date that overlaps, a hand or signature when that exists), and a bar for each impossibility (in two distant places
within a stated number of days, acting after a recorded burial, a child older than a parent). Beside them, the two
name forms as crops and how many other people in these sets carry the same spelling key. The matcher's score is
shown as a band, labelled as a model's ranking, or "not yet measured here". The person presses Same, Different or
Cannot tell. Each tie and each bar opens the two stretches it rests on in the compare panes.

### Across archives

An accepted link across two archives is drawn as a stitch between two rows of the life band. The page says, for
each line, which archive it comes from. Cutting a stitch splits the page where it stands, so the person sees what
that one join was holding together. A join nobody has reviewed is never drawn as settled.

### Living people

Joining scattered traces into one profile is the most privacy-sensitive thing this app does. A project carries a
date (default: a hundred years before today). A person with any attestation after it is treated as possibly living:
no cross-archive link is proposed for them unless the person asks, nothing about them leaves the machine, and their
page is not included in a publish or an export without a deliberate yes for that person. A restricted person is not
drawn and cannot be inferred from the hole (`explore.care.restricted-people-are-not-drawn-around`).

### Views that pass the design rule

Each is built from counted facts, opens to its lines, states its rule on its face, and has a table twin
(`explore.table.every-view-has-its-table`).

| View | What is counted | Where it lives |
|---|---|---|
| life band | attestations by written date, per archive | on the biography page |
| relations around a person | accepted relations, and co-naming in one act as a count | on the biography page |
| who names whom | which writers and offices name which people, and who is named beside whom, by act | a Library view mode on a set |
| the archive's shape and gaps | pages held, read, read unsurely, unread, by time and writer; numbered series with numbers absent | a Library view mode on a folder, and a strip beside any count |

**Three dimensions, judged honestly.** For a network or a cloud of points, 3D hurts: marks hide each other, distance
cannot be judged without motion, labels turn unreadable, a still image is useless in print and VoiceOver users are
shut out. It is not built for those. One case could earn depth: the archives as flat sheets stacked like tracing
paper, the same time axis on each, stitches as threads through the sheets, with one control that flattens it back to
the life band. It shows nothing the flat band cannot, only shows it faster for someone comparing three or more
archives. It is listed under Future and is not to be built before the flat band has been used on real work.

### Private quality checks

A project can show its owner how the linking is doing on that project only: of the links accepted, how many were
later undone; of the proposals offered, how many were accepted, rejected or left as cannot tell; how many held-out
decisions the matcher agrees with (`record.check.one-in-ten-held-out`, no figure under 50). These are read on the
person's own machine, are never sent anywhere, and are never set beside another project's.

## Behaviours

### A. The person record

- `people.record.mentions-add-up-to-a-person` — **[GAP]** (#5340 → #NEW-P1) a person is the set of mentions (stretches
  of pages, `kg.one.mention-is-the-link`) that accepted links join, and one route returns a person with every
  mention, its archive, its written form, its document's date with its basis, and the link that brought it in. No
  field of a person is a value without a mention under it, except what the historian typed, which is marked as
  theirs. *Test (to write):* test_person_is_its_mentions.py (three mentions and two accepted links give one person
  with three mentions; removing a link gives two persons).
- `people.record.unnamed-people-are-kept` — **[GAP]** (#5340 → #NEW-P1) a person pointed at without a name (by kinship,
  role or possession, found by a stated pattern the person can read and edit) is a person record with the pointing
  words as its form, linked to the person it is pointed through. It appears in lists and counts and is never dropped
  at a names gate for having no name. *Test (to write):* test_unnamed_person_is_a_record.py.
- `people.record.link-is-a-proposal-with-reasons` — **[GAP]** (#5340, #5545 → #NEW-P3) a same-person link is a record
  with its two ends, its maker (a named rule or a model with its version), its state, and its reasons as a list in
  which every reason is counted or read from the pages (dates that overlap, a shared co-named person, a shared
  place, the same role, the same spelling key) with the two stretches it rests on. A reason is never a sentence a
  model wrote. *Test (to write):* test_link_proposal_reasons.py (every reason row has two stretch ids; a payload with
  free prose in a reason is refused).
- `people.record.person-decides` — **[GAP]** (#5340, #5545 → #NEW-P3) the states of a link are proposed, accepted,
  rejected and cannot tell; only a person's action moves a link to accepted, and "cannot tell" is kept and counted.
  The one exception is the rule already specified for forms that are identical after normalisation inside one
  project (`kg.resolve.unmistakable-auto-merge`): such a join is made by the rule, labelled as the rule's, listed on
  the page among its joins, and undone like any other. *Test (to write):* test_only_a_person_accepts_a_link.py (a
  model's account calling accept is refused; cannot tell is a stored state).
- `people.record.model-work-is-labelled` — **[GAP]** (#4868, #4869 → #NEW-P3) wherever a reading, a grouping of
  spellings, a link proposal or a ranking is on screen, it says it is model output or rule output, by which method
  and version, with its confidence as a band (`kg.confidence.shown-as-a-band-with-its-reason`), and is one click
  from the stretches. *Test (to write):* PersonProposalLabelTests.swift (no proposal row renders without a maker
  label and an evidence target).
- `people.record.split-and-merge-are-undoable` — **[GAP]** (#5110 → #NEW-P4) accept, reject, split a person at a link,
  and merge two persons are each one audited action with undo, reachable from the page, the bench and the Inspector
  (`kg.resolve.merge-and-split-have-a-door`). Undoing an accept separates exactly the mentions that link joined and
  restores the two persons with their earlier ids. A decision is remembered: a rejected pair is not proposed again.
  *Test (to write):* test_split_merge_undo_roundtrip.py (accept, undo: ids and mention sets equal the start).
- `people.record.split-moves-what-rested-on-it` — **[GAP]** (#5110 → #NEW-P4) when a person is split, each relation,
  note and accepted statement goes with the mentions it rests on; one that rested on both halves is listed for the
  person to place and is attached to neither until they do. *Test (to write):* test_split_carries_dependents.py.

### B. Relations between people

- `people.relation.typed-link-rests-on-statements` — **[GAP]** (#5340 → #NEW-P5) a relation between two persons has a
  type from the ontological layer's list (`ontology.relations.one-list-the-person-extends`), a direction, an optional
  span of time, and the statements it rests on. A relation with no statement under it cannot be saved, except one
  the historian asserts, which is stored and drawn as their inference. *Test (to write):* test_relation_needs_a_statement.py.
- `people.relation.sources-word-is-shown` — **[GAP]** (#5340 → #NEW-P5) a relation row shows the sources' own word or
  formula for the tie, in the source language, beside the historian's type (`ontology.sources.categories-in-their-own-words`);
  where sources use different words for it, each is listed with its lines. *Test (to write):*
  test_relation_carries_source_words.py.
- `people.relation.proposed-is-never-drawn-as-fact` — **[GAP]** (#5340 → #NEW-P5) a relation proposed by a rule (a name
  in the father's slot of a baptism formula) or by a model is a proposal with its maker and the line it read; it is
  listed under "proposed, not checked", is not drawn in any view of relations and is not counted until a person
  accepts it. *Test (to write):* test_proposed_relation_not_in_views.py.

### C. The biography page

- `people.bio.every-line-is-sourced` — **[GAP]** (#4750, #5340 → #NEW-P6) one route returns the page as sections of
  lines, and every line carries the ids of the statements or mentions it rests on, the stretch of each, the
  archive, the source reference and the reading band. A line with no stretch is not returned; a line the historian
  wrote is returned as theirs. Extends `kg.read.biography`. *Test (to write):* test_biography_lines_are_sourced.py
  (every line of the payload resolves to a stretch on a page).
- `people.bio.only-accepted-or-attested` — **[GAP]** (#5340, #6835 → #NEW-P6) the sections hold only statements a
  person wrote or accepted and plain attestations (named in this act, in this position, on this written date). A
  statement a person rejected never appears (`kg.para.rejected-never-stated`). Statements and links nobody has
  checked are returned in their own block, "proposed, not checked", and take no part in any count, band or view.
  *Test (to write):* test_biography_proposed_is_apart.py.
- `people.bio.no-model-prose` — **[GAP]** (#4648, #5340 → #NEW-P6) every sentence on the page is made by rule from a
  statement (`kg.read.no-llm`, `kg/kg-paragraph-realisation.md`) or is the source's own words. No field of the
  payload holds text a model composed, and a guard walks the payload schema and every view payload of this spec to
  hold that. *Test (to write):* test_people_payloads_hold_no_model_prose.py.
- `people.bio.conflicts-side-by-side` — **[GAP]** (#5340 → #NEW-P6) where two or more sources speak to the same point
  of a life and their written values differ, or a person marked them as in conflict
  (`kg.confidence.contradiction-is-kept`), the page returns them as one group with every value, each with its source
  and date of writing. No value is chosen, ranked first for being likelier, or averaged. *Test (to write):*
  test_biography_keeps_conflicts.py (two birth years give one group of two lines).
- `people.bio.is-a-reader-rendition` — **[GAP]** (#5340 → #NEW-P7) the page is the Reader's rendition of a selected
  person on Mac, iPad and iPhone; one click or tap on a line selects its stretch and the linked Preview shows the
  page with the words lit (`explore.source.open-evidence-one-step`). On iPhone it follows the drill-then-swipe rule:
  the page, then swipe to the source. *Test (to write):* PersonBiographyRenditionTests.swift.
- `people.bio.sections-by-life-event-and-relation` — **[GAP]** (#5340 → #NEW-P7) lines are grouped under the event
  kinds of the ontological layer in the order the sources date them, then relations, then undated and unplaced with
  their counts; an empty section is not shown, and a line whose kind nobody set sits under "other mentions". The
  person can reorder sections for a project. *Test (to write):* PersonBiographySectionsTests.swift.
- `people.bio.names-as-written` — **[GAP]** (#5340 → #NEW-P7) the head of the page shows every written form of the
  name as a crop of the word with its count, grouped; a form joined by a proposal nobody accepted is marked and can
  be accepted or removed there. The page title is the form the historian chose, or the commonest written form, and
  never a form a model normalised. *Test (to write):* PersonNameFormsTests.swift.
- `people.bio.uncertainty-is-on-the-line` — **[GAP]** (#6763 → #NEW-P8) each line shows the reading band of the words
  it rests on (or "reading not yet measured"), a date as a span with its basis (`kg.qualifier.date-form`), and a mark
  when it reaches this person only through a join nobody has reviewed. A line is never shown more certain than the
  least certain thing under it (`record.confidence.capped-by-the-reading`), and no confidence is printed as a
  decimal. *Test (to write):* test_biography_line_doubt.py.
- `people.bio.gaps-are-shown` — **[GAP]** (#5340 → #NEW-P8) the page shows each stretch of years with no attestation
  as an empty span with its length, and says for that span whether the archives in the project hold pages of those
  years, and how many are unread or read unsurely. An implied record (`record.gap.implied-records-are-inferences`) is
  drawn as an inference in the gap, never as a line of the life. *Test (to write):* test_biography_gaps.py (a life
  attested in two decades thirty years apart returns one gap with the page counts of the years between).
- `people.bio.how-it-was-put-together` — **[GAP]** (#5340 → #NEW-P8) the foot of the page lists the joins the page
  stands on, each with its state, maker and reasons, and what was left out with counts (rights, unsure readings,
  rejected statements). Each join can be cut from there. *Test (to write):* PersonBiographyJoinsTests.swift.
- `people.bio.export-with-citations` — **[GAP]** (#5034 → #NEW-P9) the page exports as a readable document and as
  data: every line with its source reference in the project's citation style, the line as read, whether a person
  checked the reading, and the conflicts and gaps as shown. The joins and their states are part of the export; a
  person is never exported as silently merged. Rights rules and the living-people rule apply to the export as to
  the view. *Test (to write):* test_biography_export_carries_citations_and_joins.py.

### D. The stitch bench

- `people.bench.fit-between-two-lives` — **[GAP]** (#5545, #3323 → #NEW-P10) for a pair (or three) one route returns
  both lives' dated attestations on one axis and the fit between them: each shared co-named person, place, role and
  overlapping date as a tie with its two stretches. Every tie is a count or a match on what is written; the
  matcher's score is returned apart, labelled as a ranking, as a band or "not yet measured here"
  (`record.measure.one-report-and-a-gate`). *Test (to write):* test_bench_fit_lane.py (a shared-context pair has more
  ties than a namesake pair; every tie has two stretch ids).
- `people.bench.impossibilities-are-stated-rules` — **[GAP]** (#5545 → #NEW-P10) a small set of rules over written
  dates and places lists what speaks against a join: attested in two places further apart than a stated distance
  within a stated number of days, acting after a recorded death or burial, a child attested before a parent's
  birth. Each rule has a name, its settings are shown and can be changed for the project, and a bar always appears
  when its rule fires. A bar does not decide; the person does. *Test (to write):* test_bench_impossibility_rules.py.
- `people.bench.namesakes-are-counted` — **[GAP]** (#5545 → #NEW-P10) the bench shows how many other persons in the
  sets being compared share the spelling key of each side, and opens that list. *Test (to write):*
  test_bench_namesake_count.py.
- `people.bench.decide-by-key` — **[GAP]** (#5545 → #NEW-P11) the bench lives in the review surface
  (`ui/review-names-and-statements.md`); Same, Different and Cannot tell are the audited actions of section A, each
  on one key, and the next pair loads without a pause. On Same the two lives become one with a stitch. The seeded
  pairs of `record.check.seeded-with-hard-cases` are answered here. On iPhone it is one card per pair with the fit
  only. *Test (to write):* StitchBenchDecisionTests.swift.
- `people.bench.queue-is-ordered-and-says-how` — **[GAP]** (#5545 → #NEW-P11) proposals are offered in an order the
  bench states and the person can change: the default is the pairs whose answer would change the most pages
  first, then the least sure (`kg.confidence.review-least-sure-and-most-used-first`). A pair with a name read from
  unsure words is not offered (`record.confidence.unsure-readings-seed-nothing`), and the bench says how many were
  held back. *Test (to write):* test_bench_queue_order.py.

### E. Across archives

- `people.xarchive.stitch-is-drawn-and-can-be-cut` — **[GAP]** (#5341 → #NEW-P12) on the page and the life band an
  accepted link between two archives is a drawn object between their rows, and every line says which archive it is
  from. Cutting the stitch is undo of the same-as link (`record.link.same-as-joins-and-never-merges`) and the page
  becomes two pages. *Test (to write):* PersonStitchTests.swift (cut: two renditions, each with its own archive's
  lines).
- `people.xarchive.unreviewed-join-is-never-settled` — **[GAP]** (#5341 → #NEW-P12) a join that came from a rule or an
  import and that no person has reviewed is drawn doubled and labelled, on the page, the band and every set view,
  and every export carries its state. *Test (to write):* test_unreviewed_join_is_marked_everywhere.py.

### F. Views that pass the design rule

- `people.view.life-band` — **[GAP]** (#5032 → #NEW-P13) one person's attestations along time, a row per archive or
  series, each mark a span as wide as its date is uncertain, hollow if it rests on an unreviewed join, with empty
  years empty and undated marks parked and counted. A mark opens its line; a chosen span scrolls the page. Builds
  `explore.time.life-course` on attestations and accepted statements only. *Test (to write):* test_life_band_payload.py,
  LifeBandEncodingTests.swift.
- `people.view.relations-around-a-person` — **[GAP]** (#5032 → #NEW-P13) the people around one person in two groups
  that are never mixed: accepted relations by type, and people named in the same acts with the number of acts. The
  second group says its rule in words ("named in the same act") and is not called a relationship. Each row opens
  its lines. It is a list first; a small diagram of kin is offered only for accepted parent, spouse and child
  links. *Test (to write):* test_relations_around_payload.py.
- `people.view.who-names-whom` — **[GAP]** (#5032 → #NEW-P14) for a set, a counted table and its drawing: writers and
  offices on one side, the people they name on the other, grouped by the sources' own words for them, with the
  number of acts in each cell and, where the formula gives it, the position the person holds in the act (party,
  witness, the one spoken about). A control counts each writer once, so that a person is not central only because
  one office wrote about them often. Writer and office come from the catalogue or from a grouping of hands a person
  can edit; pages with no known writer are a visible row. *Test (to write):* test_who_names_whom_counts.py (counts
  equal a hand count on the fixture; the once-per-writer control changes the order as planted).
- `people.view.archive-shape-and-gaps` — **[GAP]** (#5032 → #NEW-P14) for a folder or a project, pages in shelf order
  as a strip tinted by one counted measure (read with confidence, read unsurely, unread, person-checked), with
  numbered series showing the numbers that are absent, and "not yet measured" as a state of its own and never a
  pale tint. A drag over the strip is an ordinary selection. The same strip, small, sits beside any count of people
  (`counts.strip.denominator-beside-every-count`). No measure counts what a model extracted. *Test (to write):*
  test_archive_shape_strip.py.

### G. Living people

- `people.privacy.living-date-holds-back-proposals` — **[GAP]** (#4953 → #NEW-P15) a project has a date, by default a
  hundred years before today, that the person can move. For a person with any attestation after it, no link across
  archives is proposed unless the person asks for that person by name, and the bench says how many proposals were
  held back for this. *Test (to write):* test_living_date_holds_back_candidates.py.
- `people.privacy.nothing-published-by-default` — **[GAP]** (#4953 → #NEW-P15) a biography page, a relations view or a
  set view that includes a possibly living person is left out of a publish and an export unless the person says
  yes for it, once, with the names listed (`explore.care.publishing-asks-about-people`); a restricted person is not
  drawn and the hole is not inferable (`explore.care.restricted-people-are-not-drawn-around`). *Test (to write):*
  test_living_people_not_exported_unasked.py.
- `people.privacy.a-person-record-never-leaves-unasked` — **[GAP]** (#4953 → #NEW-P15) no step of this spec sends a
  person's assembled record, a pair of lives or a list of names to a cloud model. A proposal method that would use
  one runs only where the library's cloud answer allows it and the person asked, and never for a possibly living
  person. *Test (to write):* test_people_routes_make_no_cloud_call.py.

### H. Private quality checks

- `people.quality.own-project-only` — **[GAP]** (#5545 → #NEW-P16) a panel in the project shows, for that project
  alone: links accepted, rejected and cannot tell; links accepted and later undone, as a count and a share; and the
  matcher's agreement with held-out decisions once there are 50 (`record.check.one-in-ten-held-out`). Each figure
  opens the decisions it counts. *Test (to write):* test_people_quality_panel.py (ten accepts and two undos give two
  of ten, and the two rows).
- `people.quality.nothing-is-published-or-compared` — **[GAP]** (#5545 → #NEW-P16) these figures are computed on the
  person's machine, are in no export, publish, shared file or telemetry, and no surface ranks a project, a method
  or a person against another by them. There is no public score. *Test (to write):*
  test_people_quality_is_in_no_export.py.

## Lines of other specs built here (cited, not copied)

`kg/ontological-layer.md` has no build order of its own. Its lines are built in Step 1.2 and Step 1.5 below, with
their text and tags left where they are: `ontology.kinds.small-closed-set`, `ontology.events.kinds-are-the-sections`,
`ontology.model-proposes-no-kind`, `ontology.relations.one-list-the-person-extends`,
`ontology.sources.categories-in-their-own-words`, `ontology.sources.mapping-is-a-persons-link`,
`ontology.role.is-a-position-in-a-statement`, `ontology.browse.is-a-table-of-what-is-used`. From
`explore/time.md`, `explore.time.life-course` is built in Step 4.1.

## Build order

Engine before app; each step ships alone and is 25 files or fewer. Stage 1 can start beside Stage 0 of
`kg/reconstruct-the-record.md`; Stage 3 waits for that spec's Step 2.2 for anything across archives.

### Stage 1 — The person record

#### Step 1.1 — A person is its mentions; unnamed people are kept
- Behaviours: `people.record.mentions-add-up-to-a-person`, `people.record.unnamed-people-are-kept`
- Tests: test_person_is_its_mentions.py, test_unnamed_person_is_a_record.py
- Size: M

Waits for `kg.one.mention-is-the-link` (`kg/kg-entities-and-statements.md` Step 1.3). → #NEW-P1

#### Step 1.2 — Kinds of thing and of event, as one small list
- Behaviours: `ontology.kinds.small-closed-set`, `ontology.events.kinds-are-the-sections`, `ontology.model-proposes-no-kind`
- Tests: test_ontology_kinds.py, test_no_model_writes_a_kind.py
- Depends on: 1.1
- Size: S

→ #NEW-P2

#### Step 1.3 — A link is a proposal with reasons; the person decides; model work is labelled
- Behaviours: `people.record.link-is-a-proposal-with-reasons`, `people.record.person-decides`, `people.record.model-work-is-labelled`
- Tests: test_link_proposal_reasons.py, test_only_a_person_accepts_a_link.py, PersonProposalLabelTests.swift
- Depends on: 1.1
- Size: M

→ #NEW-P3

#### Step 1.4 — Split and merge, with undo, carrying what rested on them
- Behaviours: `people.record.split-and-merge-are-undoable`, `people.record.split-moves-what-rested-on-it`
- Tests: test_split_merge_undo_roundtrip.py, test_split_carries_dependents.py
- Depends on: 1.3
- Size: M

→ #NEW-P4

#### Step 1.5 — Relations as typed links, with the sources' words beside the historian's type
- Behaviours: `people.relation.typed-link-rests-on-statements`, `people.relation.sources-word-is-shown`, `people.relation.proposed-is-never-drawn-as-fact`, `ontology.relations.one-list-the-person-extends`, `ontology.sources.categories-in-their-own-words`
- Tests: test_relation_needs_a_statement.py, test_relation_carries_source_words.py, test_proposed_relation_not_in_views.py, test_relation_types_list.py
- Depends on: 1.2, 1.3
- Size: M

→ #NEW-P5

#### Step 1.6 — Living people: the date, nothing published unasked, nothing sent
- Behaviours: `people.privacy.living-date-holds-back-proposals`, `people.privacy.nothing-published-by-default`, `people.privacy.a-person-record-never-leaves-unasked`
- Tests: test_living_date_holds_back_candidates.py, test_living_people_not_exported_unasked.py, test_people_routes_make_no_cloud_call.py
- Depends on: 1.3
- Size: M

Before anything across archives. → #NEW-P15

### Stage 2 — The biography page

#### Step 2.1 — The page as data: sourced lines, accepted or attested only, conflicts kept, no model prose
- Behaviours: `people.bio.every-line-is-sourced`, `people.bio.only-accepted-or-attested`, `people.bio.no-model-prose`, `people.bio.conflicts-side-by-side`
- Tests: test_biography_lines_are_sourced.py, test_biography_proposed_is_apart.py, test_people_payloads_hold_no_model_prose.py, test_biography_keeps_conflicts.py
- Depends on: 1.5
- Size: M

→ #NEW-P6

#### Step 2.2 — The page in the Reader: sections, relations, names as written
- Behaviours: `people.bio.is-a-reader-rendition`, `people.bio.sections-by-life-event-and-relation`, `people.bio.names-as-written`
- Tests: PersonBiographyRenditionTests.swift, PersonBiographySectionsTests.swift, PersonNameFormsTests.swift
- Depends on: 2.1
- Size: M

→ #NEW-P7

#### Step 2.3 — Doubt on the line, gaps on the page, and how it was put together
- Behaviours: `people.bio.uncertainty-is-on-the-line`, `people.bio.gaps-are-shown`, `people.bio.how-it-was-put-together`
- Tests: test_biography_line_doubt.py, test_biography_gaps.py, PersonBiographyJoinsTests.swift
- Depends on: 2.2
- Size: M

Ships "reading not yet measured" until `source/read-any-hand.md` Step 1.2 has a fit. → #NEW-P8

#### Step 2.4 — Export a life with its citations and its joins
- Behaviours: `people.bio.export-with-citations`
- Tests: test_biography_export_carries_citations_and_joins.py
- Depends on: 2.3, 1.6
- Size: S

→ #NEW-P9

### Stage 3 — The stitch bench

#### Step 3.1 — The fit between two lives, the impossibility rules, the namesake count
- Behaviours: `people.bench.fit-between-two-lives`, `people.bench.impossibilities-are-stated-rules`, `people.bench.namesakes-are-counted`
- Tests: test_bench_fit_lane.py, test_bench_impossibility_rules.py, test_bench_namesake_count.py
- Depends on: 1.3
- Size: M

→ #NEW-P10

#### Step 3.2 — The bench in the review surface: decide by key, an ordered queue
- Behaviours: `people.bench.decide-by-key`, `people.bench.queue-is-ordered-and-says-how`
- Tests: StitchBenchDecisionTests.swift, test_bench_queue_order.py
- Depends on: 3.1, 1.4
- Size: M

→ #NEW-P11

#### Step 3.3 — Across archives: the stitch drawn, cut, and never shown as settled unreviewed
- Behaviours: `people.xarchive.stitch-is-drawn-and-can-be-cut`, `people.xarchive.unreviewed-join-is-never-settled`
- Tests: PersonStitchTests.swift, test_unreviewed_join_is_marked_everywhere.py
- Depends on: 3.2, 2.2, 1.6
- Size: M

Waits for `kg/reconstruct-the-record.md` Step 2.2. → #NEW-P12

### Stage 4 — Views of people and of the record

#### Step 4.1 — The life band and the people around a person
- Behaviours: `people.view.life-band`, `people.view.relations-around-a-person`, `explore.time.life-course`
- Tests: test_life_band_payload.py, LifeBandEncodingTests.swift, test_relations_around_payload.py
- Depends on: 2.1
- Size: M

→ #NEW-P13

#### Step 4.2 — Who names whom, and the archive's shape and gaps
- Behaviours: `people.view.who-names-whom`, `people.view.archive-shape-and-gaps`, `ontology.role.is-a-position-in-a-statement`, `ontology.sources.mapping-is-a-persons-link`, `ontology.browse.is-a-table-of-what-is-used`
- Tests: test_who_names_whom_counts.py, test_archive_shape_strip.py, test_role_is_a_position.py, test_ontology_browse_table.py
- Depends on: 4.1
- Size: M

The writer or office of a document, and the position of a person in an act, are fields this step adds. → #NEW-P14

### Stage 5 — Private quality checks

#### Step 5.1 — How the linking is doing, on this project only
- Behaviours: `people.quality.own-project-only`, `people.quality.nothing-is-published-or-compared`
- Tests: test_people_quality_panel.py, test_people_quality_is_in_no_export.py
- Depends on: 1.4
- Size: S

→ #NEW-P16

## Future (not scheduled, not to be cut into issues)

- **The layered record.** The archives as stacked flat sheets with stitches as threads, tilting from and flattening
  back to the life band. Only after the flat band has been used on real work, always with the flat twin.
- **What rests on what.** For a family or a network, count what depends on each accepted join or each checked line,
  so the join that holds most can be checked first. Arithmetic over evidence; useful once joins are accepted.
- **An identity held open.** Two readings of an undecided join kept side by side, each a set of attestations. It
  changes the store and needs a ruling.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | the person from mentions, links and their states, split and merge with undo, relations, the page payload, the fit, the rules, the views' counts, the living-people rule, the private figures | the files named above |
| Pure rule (Swift) | y | labels on every proposal, sections, name forms, the stitch, the band's encoding | the Swift files named above |
| MCP | y | a person, a page and the proposals are read tools; accept, reject, split and merge are refused to a model's account | `fichero-mcp/tests/test_mcp_generated.py` |
| Click-around (XCUITest, Mac) | y | a line opens its page; Same on the bench joins two lives; cut splits them | to write |
| iPhone / iPad | y | the page and one-card bench by touch | to write |
| Load | y | a person with 2,000 mentions returns the page in bounded queries | to write |

Hard-gate once approved: no payload of this spec holds text a model composed; only a person's action accepts a
link; every line resolves to a stretch.

## Open questions for the owner

1. **Identical forms joined by rule.** Inside one project, `kg.resolve.unmistakable-auto-merge` joins forms that are
   identical after normalisation without asking. Under the ruling that the person accepts or rejects links, should
   that stand (labelled, listed, undoable; recommended, or the queue is thousands of trivial pairs), or should even
   those wait for a yes?
2. **The living-people date.** Is a hundred years before today the right default, and is it one date per project or
   per archive?
3. **Sections.** Is the list of life-event sections above right as the default for the owner's own material, and
   should a project be able to rename them as well as add and reorder?
4. **The historian's own sentences on the page.** May a person write a connecting sentence on a biography page
   (stored and drawn as theirs), or is the page only the sources, with the historian's writing kept in notes and
   the hermeneutic layer? Recommended: only the sources; their reading of a conflict sits beside it, marked.
5. **Co-naming.** "Named in the same act" is counted and shown apart from relations. Should it ever be offered as a
   reason to propose a relation, or only as a reason for a same-person link? Recommended: only the second.
6. **Its own milestone.** This spec declares the milestone `people-and-lives`, placed after `reconstruct-the-record`.
   Should the two be one milestone?
