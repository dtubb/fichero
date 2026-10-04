# Source — Checking a layer's proposals — Design Spec (#5404, #4642)

> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven · **[GAP]** intended, not built.
> Tests: `fichero-server/tests/unit/check/test_check_to_spec.py`, one per behaviour, through the API.
> Sharpens `source.job.check` (`models-chains-and-projects.md`): the one job that checks a layer's
> proposals, and its first three cards.

## Intent

Machines propose: a line's reading, a statement (subject, relation, object), an entity. Before a
project relies on them (the Mosquera notebooks' site, a training set, an edition), someone checks
them: a person, or a checker model such as a palaeographer (Fable reading a hard hand) or a careful
reader of statements. One job does this for every layer, so a recipe names *check* after the step
it checks, and a checker's verdicts are found, counted and trusted the same way whatever the layer.

A check never edits what it checks. It records a **verdict** beside the proposal: **confirm**,
**correct** or **reject**, with the checker's **reasons** and its **trust level**. A model's verdict is a
model's, never a person's, and it never takes a decision that belongs to a person (a statement's
curation, an entity's verification). A correction is a new proposal naming the one it replaces.

## The design

**A verdict** is one record: the layer, the proposal checked, the verdict, the reasons, the checker
(a person's name, or a model's id), the trust level (`person` or `model`, set by the server from who is
writing, never accepted from a caller), the check run and the episode of the call that produced it, and,
for a correction, what replaces the proposal. Written through one audited action, `check.verdict`.

**The cards**, one per layer, each saying what the checker is shown and what a correction is:

| layer | the checker sees | a correction is |
|---|---|---|
| `readings` (the palaeographer reviewer) | the line's picture (the line reader's own cut) and the reading that counts for it | a new reading of the line naming the one it corrects (`corrects_representation_id`), written as the checker's |
| `claims` (statements) | the statement's text, its subject, relation and object, and the excerpt it came from | the corrected text, subject, relation and object, held on the verdict for a person to take |
| `entities` | the entity's name, type and other names, and the excerpts that mention it | the corrected name and type, held on the verdict for a person to take |

A statement or an entity is never rewritten by a model: the knowledge graph changes only when a person
takes a correction. A reading is different: readings already coexist, and a correction is a reading.

**The run.** `check` runs over a scope (folders, pages, or the statements and entities from them) as one
job, with the card's prompt (the recipe's file, or Fichero's own), one proposal per call. Each call is
an episode in the ledger (`observability/episodes.py`): the prompt, the raw answer, the model's
thinking when it gives one. The palaeographer reviewer's episodes are what the vision card's `review`
arm trains on (`distillation.md`, `distill.set.keeps-reasons`).

## Behaviors

- `source.check.verdict-recorded` — **[OK]** (#5404) each verdict on a proposal is one record of the
  layer, the proposal, the verdict (confirm, correct or reject), the checker's reasons, the checker,
  its trust level, the run and the episode, written through the audited action `check.verdict`; the
  proposal itself is not edited. *Test:* a check run over a page's lines gives one verdict per line,
  each found again by its proposal.
- `source.check.model-never-a-person` — **[OK]** (#5404) a verdict made by a model, or written through
  a run or by an agent, is recorded at the trust level `model`; only a person's own verdict is `person`;
  a caller cannot set it. A reading a model's correction writes is a machine's reading, never a
  person's. *Test:* the same correction recorded by a check run and by a person carry `model` and
  `person`; the run's corrected reading is not `human`.
- `source.check.correction-names-the-first` — **[OK]** (#5404) a correction names the proposal it
  replaces: for a reading, a new reading of the same line with `corrects_representation_id` set to the
  reading checked, the first left as it was; for a statement or an entity, the corrected values held
  on the verdict, naming the statement or entity they would replace. *Test:* after a corrected line,
  the line has both readings, the new one naming the first; a corrected statement's text is unchanged.
- `source.check.curation-is-a-persons` — **[OK]** (#5404) a model's verdict never moves a statement to
  `curated` or `rejected`, nor an entity to `verified` or `rejected`; a model's *reject* moves an
  `unreviewed` statement to `shortlisted`, for a person to look at, and nothing further. *Test:* a
  model rejects one statement and confirms another: the first is `shortlisted`, the second unchanged,
  neither curated or rejected; a model's reject of an entity leaves it `unreviewed`.
- `source.check.traces-in-the-ledger` — **[OK]** (#5404, #4642) each call of a checker model is one
  episode in the ledger with its prompt, raw answer and thinking, and each verdict names its episode.
  *Test:* every verdict of a run names an episode that holds that call.
- `source.check.readings-card` — **[OK]** (#4642) the palaeographer reviewer is shown each line's
  picture and the reading that counts for it, and its review of the line is kept as the `review` arm's
  lesson. *Test:* the checker is shown the counting reading; the vision card's `review` arm finds the
  run's verdicts.
- `source.check.claims-card` — **[OK]** (#5404) a statements checker is shown each statement's text,
  subject, relation and object, and the excerpt it came from. *Test:* the prompt names all four and the
  excerpt.
- `source.check.entities-card` — **[OK]** (#5404) an entities checker is shown each entity's name, type
  and other names, and the excerpts that mention it. *Test:* the prompt names them.
- `source.check.run-is-a-job` — **[PARTIAL]** (#5404) a check run is one job in Activity over a scope, from
  the API, the CLI and MCP, with its counts in words (confirmed, corrected, rejected, unanswered), and
  can be stopped; what was checked stays. *Built: API and MCP (`checking/job.py`, `api/routes/check.py`);
  not built: a CLI command (the CLI client has the calls) and an Activity row of its own in the app.* *Test:* a run reports its counts; a stopped run checks no
  further proposals.
- `source.check.person-checks-the-same-way` — **[OK]** (#5404) a person's verdict goes through the same
  action and is recorded at `person`; a person's *reject* of a statement is still taken through the
  statement's own curation, never by the verdict. *Test:* a person's verdict is `person` and moves no
  curation state.
- `source.check.on-the-site` — **[OK]** (#5404, #5390; built: `export_service` site pages, claim index and entity pages; tested in `fichero-server/tests/unit/check/test_check_on_the_site.py`) where a check has run, the published site shows it
  beside the statement or entity it checked, on the page the statement was found on, in the claim index and
  on the entity's page: the verdict, the reasons, the checker and its trust level (a person, or a model,
  named as a model), and for a correction the values offered; a statement or entity no check has seen is
  shown without one, never as confirmed. *Test:* a model rejects one statement and a person confirms an
  entity; the site's page, claim index and entity page say so, by whom; the unchecked statement says nothing
  about a check.

## Open questions

1. Should a person's *confirm* of a reading also choose it (`reading.choose`)? *Proposal: no; choosing
   is its own act, offered beside the verdict.*
2. **Answered** (design lead 2026-10-04, applying the spec's lean): Yes, through the existing claim and entity edits, in a later slice once a review surface exists. A statement or entity correction a person takes: through the existing claim and entity edits, naming
   the verdict. *Proposal: a later slice, once a person's review surface exists.*
