# Recipe ranking and auto-compare at each step — Design Spec

> Milestone: ranking-and-auto-compare
> Manual: TBD — the user manual must explain how a recipe step picks its model (measured, else the default), what Compare shows and when it runs, and how to read the ranking facts on each candidate row.
> Status: DRAFT — awaiting the owner's approval before tests or code. No milestone is created yet (create it on approval).
> Source: agent-work/status/briefs/ranking-and-auto-compare-design.md (design brief, 2026-10-24).

## Intent

A recipe step should pick its model by one rule the person can read: a measurement on their own pages when one exists,
then a vendored measured default for their language and script, then the facts of each candidate (fit, tier, cost, speed).
Compare runs by itself when a step first has candidates to compare, and says in words what it measured and what it could
not measure. The rule is the same for every step; only the measure and the ground truth differ by step.

Files: `fichero-server/src/fichero_server/recipes/assemble.py` (`_rank_key`, `_choose`), `recipes/bakeoff.py` (measurement),
`recipes/samples.py` (the Try), `recipes/stages.py` (`TRIED_BY_THE_BAKEOFF`), `recipes/discovery.py` (`frontier_rank`,
`reader_tier`), and the Set Up pages in `fichero/fichero/Views/Onboarding/`.

## Prior art / best practices

- Measurement on the person's own pages before any default: the house rule (a measured number beats a hand order).
- Character and word error rate on corrected pages, with a noise band before a difference counts (as in published HTR
  benchmarks; the bake-off already scores CER, WER and line recall).
- Benchmark provenance: each vendored default names its corpus and licence (the Test Corpus README), as the datasets it
  reads from do (HTR-United, Zenodo entries cited in the corpus).
- A model is not used to rank candidates (it cannot know the person's pages better than a measurement on them, and a
  sentence it writes carries no provenance). A model may be a reviewer that produces a measurable artefact (section e of
  the brief, not this spec's first slice).

## Behaviors

- `recipe.rank.one-rule-every-step` [PARTIAL] — every step ranks candidates by the same order: measured on the person's
  pages, else the vendored default for the language and script, then coverage, card fit, tier, cost, speed.
- `recipe.rank.measure-per-step` [MISSING] — each step names its measure (read: CER; find lines: line recall; find
  names: F1; correct: agreement) and its ground truth in one short table.
- `recipe.rank.reasons-in-words` [PARTIAL] — each candidate row says why it is ranked where it is, in words; the best,
  the cheapest and the fastest are labelled on every row.
- `recipe.default.measured-per-language` [MISSING] — a vendored default per language and script, from the Test Corpus
  sets, with its corpus, licence and measured value written beside it; no default without a measurement.
- `recipe.compare.auto-on-open` [MISSING] — when a step first has two or more candidates on the person's pages, Compare
  runs by itself and says what it measured; it does not wait for a press.
- `recipe.compare.cost-before-run` [PARTIAL] — the estimated cost and time are shown before an automatic Compare starts;
  time is predicted per set, not only cost.
- `recipe.compare.side-by-side-text` [MISSING] — results show the candidates' text beside the page image, not only counts.
- `recipe.compare.says-what-it-could-not-measure` [PARTIAL] — a Compare that cannot measure (no corrected lines, no ground
  truth on the pages) says so in plain words and names what would let it measure.
- `recipe.review.own-stage` [MISSING] — review is its own stage with a kind (palaeographer lenses, by kind), its level
  and a measured gain; proposals are a separate pass from the review.
- `recipe.coverage.before-cer` [PARTIAL] — a candidate that cannot write the script or language is filtered before any
  CER is compared (Loove coverage as a filter, not a score).
- `recipe.regions.one-stage` [PARTIAL] — Find Regions and Find Lines are one stage, "Find the layout"; Kraken's
  segmentation runs once when both steps are Kraken.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | the candidate row's order and labels | `fichero/Tests/Unit/general/Models/ModelFinderTiersTests.swift` (to write) |
| Availability (Swift) | y | Compare reachable from the step | `fichero/Tests/Unit/general/Views/Onboarding/` (to write) |
| Backend (pytest) | y | ranking, measurement, coverage filter, Compare triggers | `fichero-server/tests/unit/recipes/` (to write) |
| MCP | n | — | — |
| CLI | n | — | — |
