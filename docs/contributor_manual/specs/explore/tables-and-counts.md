# Explore: tables and counts — facets, distributions, flows, the corpus — Design Spec (#5032)

> Milestone: explore
> Manual: TBD — a section of "Exploring a project": the table as the everyday way to look at a
> set; narrowing by facets; counts and simple charts made from what is showing; looking at a
> project's words across time; looking at hands, readings and certainty.
>
> **Status: DRAFT — first pass, 2026-09-20.** Foundation, words and common rules: `explore.md`.

## Intent (the design)

SlaveVoyages shows what the everyday form of this layer is: **a table**, with facets down the
side and summary numbers on top, from which the charts and maps are made, and from which the
data can be downloaded. Most questions a historian asks of a project are counting questions
("how many baptisms per year, by parish?"), and a count is only trustworthy if each number opens
to its rows and each row to its ink.

This family also holds the two "distant" kinds of looking the brief names: the project's text as
a corpus (Underwood), and the hermeneutic layers (readings, hands, campaigns, certainty) as
things that can be counted and compared.

Lives in: the Library's existing Table and Sheet view modes and the claims and entities tables
(`Views/Library/ViewModes/Table/`, `Dataset/Grid/`). Their own behaviours (filtering, columns,
sorting) belong to `ui/library-view-modes.md` and `kg/kg-tables.md` and are not restated here.
This file adds only what those do not have: facets with counts, summaries, charts made from
what is showing, and export of what is showing.

## Prior art

SlaveVoyages (table, facets, summary statistics, downloads), the Digital Panopticon (life
archives; Sankey flows for cohorts and outcomes), Underwood's *Distant Horizons* (models over a
corpus across time, with perspective and the evidence kept close), Voyant Tools (the standard
small set of corpus views: frequencies, trends, keyword in context). Tidy, long-format tables
(one row per observation) are the form that R, Python and Observable expect.

## What exists

- Documents, claims and entities as native tables with a text filter, a type picker, column
  configuration, and search that combines with the filter. Owned by `kg/kg-tables.md` and
  `ui/library-view-modes.md`.
- Dataset rows with roles and engine-side aggregates; a date facet and a prototype facet.
- `GET /search/keywords` (a keyword cloud). A bar chart of entity kinds
  (`EntityKindChartView.swift`) that nothing mounts (`kg.entity.kind-chart`, GAP, #4828).
- Exports: Parquet, JSONL, Excel from the engine; the app's menu wires only Word and Markdown
  (#4873). **No CSV. No "export what is showing".**
- Tables extracted from sources as real tables: not built (#5026, and the source model).
- Hands, campaigns, readings and their certainty: specified in the source-model set (milestone
  322), not built. Interpretations and frameworks: built, with gaps (#4692).
- No word-frequency, collocation or word-use-over-time computation.

## Behaviors

The table is the base
- `explore.table.every-view-has-its-table` — **[GAP]** (#5032) every view in this set can be
  switched to the table of the same marks, with the same selection. The table is the view's
  accessible form and its export.
- `explore.table.facets-with-counts` — **[PARTIAL]** (#5032) beside a table, facets list the
  values of chosen fields (kind, person, place, year, hand, language, asserter, group by
  meaning) each with its count in the current set; choosing values narrows the set for every
  view in the pane. Built today only as a date facet and a prototype facet for dataset rows and
  a type picker for claims and entities, without counts.
- `explore.table.facets-are-the-query` — **[GAP]** (#5032) the chosen facets are part of the
  set's description, so they are kept in a saved view and the same set can be made again by the
  command line or an agent. For large sets the narrowing is done by the engine, not in the app.
- `explore.table.summary-row` — **[GAP]** (#5032) above a table: how many rows; how many dated,
  placed, inferred; the span of dates; and, for number columns, sum, mean, median, smallest and
  largest. Each number opens to its rows.
- `explore.table.rows-from-source-tables` — **[GAP]** (#5026, #5032) a table transcribed from a
  source (an account book, a register, a census) is a set like any other: it can be faceted,
  counted and charted, and every row and cell opens to its place on the page.

Counts, distributions, flows
- `explore.count.chart-from-what-is-showing` — **[GAP]** (#5032) from any table a researcher can
  make a simple chart by choosing what to count and what to split it by: bars, a histogram of a
  number column, counts over time (which is `time.md`'s binned timeline), a grid of two fields
  against each other. Every bar and cell opens to its rows.
- `explore.count.kind-chart-is-the-first-tenant` — **[GAP]** (#4828, #5032) the unmounted
  entity-kind bar chart is mounted through this behaviour or deleted; it does not stay as
  unreachable code.
- `explore.count.missing-is-a-value` — **[GAP]** (#5032) "unknown", "illegible" and "not
  recorded" are counted and drawn as their own values, never dropped from a percentage
  silently.
- `explore.count.small-numbers-are-said` — **[GAP]** (#5032) a percentage always shows the count
  it is a percentage of; a chart of seven items does not look like a chart of seven thousand.
- `explore.count.flows` — **[GAP]** (#5032) for a set of people with an ordered sequence of
  states (arrested, tried, sentenced, transported; or born here, married there, died
  elsewhere), a flow chart (Sankey) shows how many pass from each state to the next. Each band
  opens to its people. The sequence of states is chosen by the researcher and shown.
- `explore.count.linked-records-say-how` — **[GAP]** (#5032) where one life is assembled from
  several sources, each link between records carries its method, confidence and asserter, and
  flows and life courses can be limited by them
  (`explore.inferred.filter-by-confidence-and-asserter`). A wrongly joined pair of records is the commonest way such charts mislead.

The project's words as a corpus
- `explore.corpus.word-use-over-time` — **[GAP]** (#5032) for a set with dates: how often chosen
  words or names appear, per period, as a rate (per thousand words) beside the raw count, with
  the amount of text in each period shown so that a thin year is not read as silence.
- `explore.corpus.which-reading` — **[GAP]** (#5032, waits on milestone 322) counting words
  always says WHICH text was counted (the diplomatic reading, the normalised reading, the
  translation); historical spelling makes this the difference between a finding and an artefact.
- `explore.corpus.keyword-in-context` — **[GAP]** (#5032) any word count opens to its
  occurrences, each shown in its line of text, each opening to the page.
- `explore.corpus.compare-two-sets` — **[GAP]** (#5032) two sets (two hands, two decades, two
  correspondents) can be compared by the words that distinguish them, with the measure named.
- `explore.corpus.ocr-quality-is-shown` — **[GAP]** (#5032) any corpus view shows how much of the
  text counted was machine-read and unchecked, because transcription error is not evenly
  spread and can look like historical change.

The hermeneutic layers
- `explore.layers.countable-like-anything-else` — **[GAP]** (#5032, waits on milestone 322)
  hands, campaigns, languages, scripts, kinds of reading and levels of certainty are fields
  like any other: facets, colours, rows of a timeline, groups of a comparison.
- `explore.layers.certainty-map-of-a-source` — **[GAP]** (#5032, waits on milestone 322) for one
  source or volume, a page-by-page strip shows where readings are certain, doubtful, disputed
  or machine-only, as a Reader or Inspector rendition; it is a map of where work remains.
- `explore.layers.disagreement-is-findable` — **[GAP]** (#5032) segments where two readings, or
  two people, or a person and a model disagree can be listed as a set, and then looked at by
  any view here.
- `explore.layers.interpretations-are-a-set` — **[GAP]** (#4692, #5032) interpretations and the
  frameworks they were made under can be listed, faceted and counted like claims, once they
  carry a source anchor.

Out
- `explore.table.csv-and-parquet-of-what-is-showing` — **[PARTIAL]** (#5032) one command exports
  the current set, as narrowed, with the columns showing, as CSV or Parquet, in tidy long form,
  with a citable reference to the source in every row. Parquet export of a whole project is
  built (`export.one-stream-feeds-every-record-emitter`); CSV, "what is showing", and an app
  command are not.

## How it is drawn

Native: the existing tables, Swift Charts for bars, histograms and grids; a native Sankey. The
NLG side of the engine (`knowledge/readable.py`) may later SAY a summary in a sentence ("312
entries, 1924 to 1931, most from Quibdó"); that is noted, not specified, here.

## Test matrix (legs this family touches)

Backend (facet counts agree with the rows they open to; summaries; flows; word rates with the
denominator; every number resolvable to row ids); pure Swift (missing is a value; small numbers
are said); CLI and MCP (export what is showing; facet a set); click-around (choose a bar, the
rows show, choose a row, the Source view follows); load (facets on a project's claims are
computed by the engine, bounded).

## Open questions for the creative director

Question 14 (how far into distant reading the first version goes). Full text in
`agent-work/dh-layer/questions-for-the-maintainer.md`.
