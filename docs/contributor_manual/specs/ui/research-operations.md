# Research operations — a research project as runs of lead-steps, checked by scripts, driven from inside or outside — Design Spec (#2069, #2072)

> Milestone: research-operations
> Spec: ui/research-operations.md
> Manual: TBD — a "Letting Fichero look for sources" section: how one sentence becomes a brief the person approves,
> what the agent then does alone (search, import to Staged, read, extract, compare, a dossier of claims) and what it
> never does (approve its own brief, accept its own imports, log in anywhere, raise a cap, write the prose), what
> "requested" means, and how to let Claude Code, Claude Desktop or Pi do the work through Fichero.
>
> Design-led (Testing Constitution). **Status: DRAFT 2026-11-21** (from the owner's rulings of 2026-11-21 on the
> research-automation design and the review of research on the builder; the owner approves). Facts read from
> `origin/integration` 2b271cfbc5, file and function; nothing run. A COMPANION of `ui/research.md`, whose 2026-11-21
> revision (branch `review-research-ux-1121`, not landed when this was written) owns WHERE Research lives and what the
> Plan shows: the research folder, the Plan pane and window, and the rows a person sees (`research.plan.*`,
> `research.runs-are-activity-jobs`, `research.folder.one-record`). This file owns WHAT RUNS: the project model, the
> six step kinds, the brief, the checks, the stops and caps, the catalogue adapters, what a project learns, and how an
> agent harness is hooked up in either direction. It names that spec's ids and does not restate them; section
> "What this amends in `ui/research.md`" says where the two differ.
> Tags: **[OK]** built and pinned · **[PARTIAL]** exists in part · **[GAP]** designed, not built · **[BROKEN]** built and
> contradicting the line. Every non-[OK] line cites an issue; "→ #N" is an issue filed on
> this milestone.

## Ruled 2026-11-21 (owner; paraphrased)

1. **The pilot is the owner's maps project,** in a new library made for it, and **the builder drives it now through
   the Fichero MCP**; the in-app runner comes after.
2. **Read and extract run on Staged imports** before the person's Accept. What they produce is held as proposed, and
   a Reject removes it.
3. **Only the catalogues listed in the approved brief are scripted.** One the agent finds by itself becomes a question.
4. **Caps for the pilot: 5 USD a run and 20 USD a day.**
5. **Cloud reading is set per library** (cloud allowed, or local only), and the agent obeys.
6. **The held-out set is one in ten of the person's decisions, chosen silently.**
7. **The agent has an editor account on the one pilot library only**, and every staged import waits for the
   person's Accept. A catalogue that needs a login or blocks scripts makes its lead "requested".
8. **Two ways to drive, one record.** When research runs inside Fichero, the in-app runner can use Pi or Claude Code
   as its agent harness as well as Fichero's own loop. And an agent outside Fichero (Claude Code, Claude Desktop, Pi)
   can drive a research project through the Fichero MCP, which is how the pilot runs today. Both share the same
   leads, search log, source register, Staged and Changes, the same caps and journal, and the same stops that are the
   person's alone.

## Intent (the design)

**A research pass is a recipe step whose unit is a lead, not a page.** Recipes already have a registry of steps, a
model per step, resume, a cloud cap and a way to distil each step into a smaller model. The builder has already shown
what makes unattended work reliable: a brief, scripted checks, a critic that is a different model, a journal, caps and
escalation by rule. Research gets both, on the engine's one job model, with no second runner, model picker or record.

A person types one sentence. Fichero drafts a brief; a script refuses a brief that cannot be run; the person edits and
approves it. From then on the agent searches the catalogues the brief names, imports what it finds into Staged, reads
and extracts, compares sources and lays out a dossier of claims, each with its page and quote. Scripts judge every
step before any model's word is believed. The person is stopped for five things only: to approve the brief, to accept
or reject what was staged, to answer a question (a login, a cap reached), to merge two people, and to write.

## Prior art (what we adopt)

- **The builder** (`harness/building-fichero-locally.md`): a spec with a milestone and a build order becomes one brief
  per step; guards run before a reviewer; the reviewer is a different, stronger model; caps stop a run; one journal
  row per event; MODEL × HARNESS behind an adapter that answers six questions (`agent-profiles.adapter.interface`). We
  adopt the loop and the adapter's shape, and none of its machinery: the builder's work store is commit ranges in a
  jailed checkout, Research's is rows in a library behind the audited action layer.
- **Systematic review practice** (PRISMA; the search log of a scoping review): every search is logged with its terms,
  source, date and hits, so a "not found" can be believed and a search repeated.
- **Archival finding aids and harvest protocols:** IIIF collections and Content Search, OAI-PMH, SRU. A catalogue is
  reached by its published interface under its terms of use, at its rate, or not at all.
- **The Model Context Protocol** as the one door: an agent, whoever runs it, reaches Fichero through the Fichero MCP
  and the audited actions behind it (`architecture/agent_chat_as_user.md`: a model is a real account with a role and
  an audit trail).

## What exists today (read 2026-11-21)

- **Records:** research projects, plans, tasks, steps of four kinds, sources and notes (`models/research.py`
  `ResearchProject`, `ResearchPlan`, `ResearchTask`, `ResearchStep`); a plan drafted with web search
  (`api/routes/research/crud.py`); the chat's write allowlist (`actions/chat_tools.py` `is_write_allowed`).
- **Every write is audited:** `actions/registry.py` `ActionRegistry.invoke`, `ActionAudit`, and sets undone as one
  (`actions/undo.py` `undo_set`). The MCP carries `fichero_actions_invoke` and the undo tools, with the actor taken
  from the session (`fichero-mcp/src/fichero_mcp/openapi_tools_generated.py`).
- **Import:** `iiif.import` (`api/routes/ingest/iiif.py`), declared not undoable; a polite fetcher
  (`media/iiif_fetch.py` `PoliteFetcher`); files compared by checksum on ingest.
- **Reading and extracting:** recipe runs with a model per step, resume and a monthly cloud cap per project
  (`recipes/runner.py`, `recipes/cloud_cap.py`); check runs by a checker model with verdicts (`api/routes/check.py`).
- **The cloud answer per library:** one egress gate (`llm/egress.py` `require_project_yes`), obeyed by every stored
  job because a job names its library. Whether the chat tool loop passes the same gate was not verified.
- **Roles:** owner, editor and viewer per library (`api/routes/auth/pairing.py`).
- **Missing:** a detached research run; leads, milestones and outcomes; the search log; register fields; Staged and an
  account confined to it; an undo for a IIIF import; catalogue adapters; the brief's lint and approval; research
  checks; term yield; a research tool set in the MCP; a lease on a lead; any external harness started by the engine.

## The design

### The project model

| Thing | What it is | Stored as |
|---|---|---|
| Question | one sentence, a period, a region, languages, what counts as a source | the **brief**, a note in the research folder |
| Milestone | a phase (one archive or catalogue family) or a sub-question, with a short spec: aim, catalogues, terms, done-when | a section of the brief, with a build order of leads |
| Lead | one thing to find, or one search task; ends with exactly one outcome: found, not found, requested | a Plan row (`research.plan.leads-and-milestones`) |
| Step | one of six kinds, run in order for a lead or for a milestone | an Activity job (`research.runs-are-activity-jobs`) |

### Six step kinds

Per lead, in order:

1. **search**: these terms, this catalogue. Writes search-log rows and register rows.
2. **import**: these register rows. Writes documents into Staged, each with its source URL and shelfmark.
3. **read**: the project's recipe on those documents (lines, reading, dates). Writes readings.
4. **extract**: names, places, statements. Writes claims held as proposed, each with its maker and the stretch it
   rests on.

Per milestone, once its leads have ended:

5. **compare**: agreement, contradiction and gaps across sources. Writes a table of claim ids.
6. **dossier**: the claims grouped under the sub-question, each with source, page and quote, in a proposed order.
   Never prose. The person writes from it.

### What runs where

| Step | Existing system it runs on | Kind of work in Models and Compute |
|---|---|---|
| search | catalogue adapters over the polite fetcher; web search; the project's own search, first | small and local: turn a lead into queries, sift hits |
| import | `iiif.import`, `import.file`; mechanical | none |
| read | a recipe run, with its stages and resume | the recipe's own per-step models |
| extract | the recipe's find-names and find-statements steps | small and local first; a larger tier on low confidence |
| compare | `knowledge/triangulation.py`, `knowledge/dedupe.py`, graph reads | larger: judgment |
| dossier | paragraph realisation as clauses that carry claim ids (`knowledge/paragraph.py`) | larger: judgment |
| the brief, the critic | a check run by a checker model | larger; the critic is never the worker's model |

Research has no model picker (`research.models-come-from-the-models-system`): each step kind is a kind of work in the
Models and Compute window, and so is the harness that runs it (section "Driving a project").

### Reliability

**Scripts first.** After each step, deterministic checks run before any model reads the result, and a check that
could not run is shown as not run, never as green. **Then a critic:** a different, larger model reads what passed,
with a checklist scripts cannot run (does the quote carry the claim, is the reading anachronistic, was
counter-evidence looked for, is a "not found" believable given the terms tried). A critic's yes is weaker than a
green script, and the row says which it was. **Autofix:** a red check goes back to the step with the failing rows
named, at most twice; mechanical repairs (drop a duplicate, re-anchor a quote, retry a fetch) use no model.
**Escalation** is by mechanical trigger only (the same check red twice, two failed fix rounds, a turn cap reached with
no output), one journal row each; past the top tier the step parks as a question.

**The journal is not a new record.** It is three things read together: the audit rows of every write by the agent's
account, the search log, and each job's row (driver, model, place, cost, checks, verdict).

### Driving a project: inside or outside, one record

A **driver** is whatever runs the agent's turns for a step: it reads the step's brief, calls tools, and stops. There
are two directions, and a project can use both, on different leads.

**(a) Inside.** Fichero's in-app runner starts the step as an Activity job and gives its turns to a harness behind an
adapter: Fichero's own loop (the chat tool loop, detached), Claude Code, or Pi. The adapter has the builder's shape,
MODEL × HARNESS, and answers the same six questions: where the system prompt goes; how the MCP servers are written
(exactly one, the Fichero MCP, in the harness's strict mode); which model and provider; the non-interactive
permission mode; the tool-use policy hook; and where tokens, cost and the done state are read from. An external
harness is a child process of the job, given a scratch directory, the step's brief and a token, and nothing else: no
file tools, no shell, no web tools of its own. It reaches Fichero only through the MCP.

**(b) Outside.** An agent the person runs themselves (Claude Code, Claude Desktop, Pi, or the builder) connects to the
Fichero MCP with an agent account's token. It reads the Plan, takes a lead, runs steps with the research tools, and
writes to Staged through the audited actions. Its work shows in Activity as a job row marked as driven from outside,
and in the Plan's Changes view with Undo. This is how the pilot runs today, with the builder as the driver.

**What both share.** One record (leads, search log, source register, Staged, Changes); the same checks, run by the
engine when a step is finished, whoever drove it; the same caps and journal; and the same stops, which are refused to
a model's account in the action layer whatever the driver: Approve Brief, Accept, a login, raising a cap, merging two
people, and writing outside the dossier note.

**What Fichero ships, and what the person installs.**

| | Fichero ships | The person installs or does |
|---|---|---|
| Fichero's own loop | everything | nothing; picks a model in Models and Compute |
| Claude Code, inside | the adapter; the research role prompt and step briefs; a generated strict MCP file naming only the Fichero MCP; a generated settings file whose tool-use hook allows only the research tools; the session reader | installs Claude Code and signs in to it themselves; Fichero never holds that sign-in |
| Pi, inside | the adapter; an agent directory with the prompt, the MCP entry, the policy extension and a priced model list | installs Pi; points it at a provider (a local runtime Fichero already manages, or an endpoint and key of their own) |
| Any agent, outside | the Fichero MCP with the research tool set; a research skill (the role prompt and the step briefs as the tools return them); the agent account and its token | adds the Fichero MCP to their agent with the token; runs the agent |

An outside driver needs three things from Fichero, and nothing else: **a tool list** for research operations, small
enough to be a policy; **an agent account and a token** scoped to one library and one research folder; and **a lock**,
so an inside run and an outside driver never work the same lead at once.

### Finding sources

**A catalogue adapter is a plugin with one shape:** `describe()` (name, languages, terms of use, rate, whether it
needs a login), `search(query, page)` returning hits (title, shelfmark, institution, URL, date, a manifest or PDF
URL), and `record(id)`. Each fetches through the polite fetcher and writes its own log rows. The project's own search
is the first adapter and always runs first, so nothing already held is sought again.

**Requested.** An adapter that needs a login, or meets a block, stops at once. The lead becomes requested, with its
terms ready to paste; no other route is tried. Files or a manifest URL dropped on the lead resume it.

### Learning

Each search-log row gains what came of it (hits kept, staged, accepted); yield per term, origin and catalogue ranks
the next batch, and a term with three empty runs is retired and listed. After each extract step a script proposes
new terms from the graph: names with their spelling variants, alternate labels from authority links, gazetteer names
in each catalogue's language, date ranges from dated claims; each term keeps the name it came from, and only names
above the project's confidence bar seed a term. Accepted corrections are training data; one in ten of the person's
decisions is held out and never trained on (`record.check.one-in-ten-held-out`, `kg/reconstruct-the-record.md`).

## Behaviours

### A. Steps

- `research.ops.step.six-kinds-in-order` — **[GAP]** (#2072 → #6987) a step has one of six kinds. Search, import,
  read and extract belong to a lead and run in that order; compare and dossier belong to a milestone and run once
  every lead of it has an outcome. A step's row says its kind, its lead or milestone, its driver, and what it wrote
  (the ids of its search-log rows, register rows, documents, claims or note). A step of a kind out of order refuses,
  naming the step that must come first. *Test (to write):* test_research_step_kinds.py (extract before read refuses;
  compare with an open lead refuses; the six kinds round-trip through the contract).
- `research.ops.step.nothing-runs-without-an-approved-brief` — **[GAP]** (#2072 → #6988) no lead exists and no step
  starts in a research folder whose brief is not approved; a step started against a milestone whose section changed
  after approval refuses until it is approved again. The refusal is in the engine, for every driver. *Test (to
  write):* test_research_brief_gates_steps.py.

### B. The brief

- `research.ops.brief.drafted-from-one-sentence` — **[GAP]** (#2070 → #6988) from one sentence typed in a new research
  folder's chat, one job on the judgment model drafts the brief as a note: the question with its period, region and
  languages; three to eight milestones; for each, the catalogues to try (from the adapter list, each marked
  scriptable or needs-login), the first terms per language with variant spellings, and a done-when; the caps; and
  what it could not decide, as questions. It guesses nothing it could ask. *Built:* a plan drafted with web search
  (`api/routes/research/crud.py`); not built: the brief's shape, the job, the questions. *Test (to write):*
  test_research_brief_draft.py (a fake model's draft becomes a note with every section; an undecided item is a
  question, not a value).
- `research.ops.brief.lint-refuses-what-cannot-run` — **[GAP]** (#2070 → #6988) a script reads the brief and refuses a
  milestone with no catalogue, no terms or no done-when, a catalogue that is not in the adapter list, a missing cap,
  and a period that does not parse; it names each line. The lint runs on every save and before Approve Brief.
  *Test (to write):* test_research_brief_lint.py.
- `research.ops.brief.approve-is-the-persons` — **[GAP]** (#2070 → #6988) **Approve Brief** is a verb in the Plan's
  menu and the brief note's, enabled when the lint is green, and an audited action that refuses a model's account.
  Approving makes the leads from the brief's build order, and records the brief's text as approved; a later edit to
  a milestone's section shows "changed since approved" on its leads. *Test (to write):* test_research_brief_approve.py
  (a model's account is refused; leads appear; an edit marks them).
- `research.ops.brief.only-listed-catalogues-are-scripted` — **[GAP]** (#2072 → #6989) a search or import step may
  reach only a catalogue the approved brief lists for its milestone. One the agent comes across (in a hit, on the
  web) is written as a question with its name, URL and terms of use, and waits for the person to add it to the brief
  and approve. *Test (to write):* test_research_only_briefed_catalogues.py (an unlisted adapter name refuses and
  leaves one question).

### C. Checks, the critic, autofix, escalation

- `research.ops.check.scripts-judge-first` — **[GAP]** (#2069 → #6990) when a step is finished the engine runs that
  kind's checks before any model reads the result, and the step is done only if they are green:
  **search**: every query has a log row (date, catalogue, terms as typed, hits), a step with none is not done, and
  every kept hit has a register row with shelfmark, institution and a URL that answered;
  **import**: the manifest parses as IIIF Presentation 2 or 3 over https, no shelfmark, URL or checksum repeats one in
  the register or the project, every item is in Staged and nowhere else, the page count matches the manifest, and
  the rights statement is stored;
  **read**: the recipe's own (every page has a state; none silently unread);
  **extract**: every claim has a maker, a document, a segment and a span, its quote is on that page after whitespace
  and diacritic normalisation, its dates parse and fall in the brief's period, and its places are in the gazetteer or
  listed as unresolved;
  **compare**: every cell cites claim ids that exist, and a contradiction is kept, not resolved;
  **dossier**: every clause carries claim ids and a quote, every citation resolves to the register or the
  bibliography export, an inference names the claims it rests on, and nothing was written outside the dossier note.
  *Test (to write):* test_research_step_checks.py (one failing fixture per rule; each names its rows).
- `research.ops.check.not-run-is-never-green` — **[GAP]** (#2069 → #6990) a check that could not run (a catalogue that
  rate-limited the URL probe, a page with no text yet) is stored and shown as not run with its reason, and a step
  with a not-run check is not done. *Test (to write):* test_research_check_not_run.py.
- `research.ops.critic.a-different-larger-model` — **[GAP]** (#2069 → #6991) what passes the scripts is read by a
  critic on the engine's check runs (`api/routes/check.py`), with a checklist per step kind, on a model that is not
  the one that did the step and is of a larger tier. Its verdict and findings are on the step's row beside the
  scripts' results, labelled as a model's reading. A step whose driver and critic would be the same model refuses to
  be judged, and says so. *Test (to write):* test_research_critic_differs.py.
- `research.ops.autofix.twice-then-up-then-parked` — **[GAP]** (#2069 → #6990) a red check sends the step back with
  the failing rows named, at most twice. Dropping a duplicate, re-anchoring a quote and retrying a fetch are done by
  script with no model. After two rounds the step moves up a tier by rule (the same check red twice, two failed fix
  rounds, a turn cap with no output), each move one journal row; past the top tier it parks as a question on the
  Plan. A step kind that failed over half the time on the small tier is started one tier up
  (`research.ops.learn.routing-by-failure-rate`). *Test (to write):* test_research_autofix_and_escalation.py.

### D. Stops, caps, cloud, the journal

- `research.ops.stops.five-are-the-persons` — **[GAP]** (#1848 → #6992) these actions refuse a model's account, in the
  action layer, for every driver and every role it holds: approving a brief; accepting staged imports; any action
  that stores or uses a catalogue's login; raising or removing a cap; merging two people; and writing or changing a
  note other than the folder's dossier, search log and questions. No setting grants them. Each refusal leaves an
  audit row. *Built:* a write allowlist for the chat (`actions/chat_tools.py` `is_write_allowed`); not built: the
  refusal by account kind in the registry. *Test (to write):* test_research_owner_stops.py (each of the six refuses
  an editor-role model account and succeeds for a person).
- `research.ops.caps.per-run-per-day-per-project` — **[GAP]** (#2073 → #6993) a research folder has three caps, set
  in its brief: per run, per day, and the project's monthly cloud cap that exists (`recipes/cloud_cap.py`). The engine
  counts every cost it can see against them, across both directions of driving: its own model calls, the cost an
  inside harness's session reports, and the cost an outside driver reports when it finishes a step. The call that
  would pass a cap is not made; the run stops, its Activity row says "stopped at the cap", and what remains is a
  question, not a failure. A run whose driver reports no cost is also held to a step count per run and per day, so a
  cap always stops it. *Test (to write):* test_research_caps.py (the step that would pass the run cap does not start;
  the day cap holds across an inside and an outside run; a driver with no cost stops at the step count).
- `research.ops.caps.the-pilot-is-five-and-twenty` — **[GAP]** (#2073 → #6994) the pilot's brief sets 5 USD a run and
  20 USD a day, and the builder's project configuration for the pilot carries the same two figures, so the cap holds
  on whichever side counts first. *Test (to write):* test_pilot_brief_caps.py (the pilot brief's lint refuses other
  figures until the person changes the ruling in the brief).
- `research.ops.cloud.the-library-decides` — **[PARTIAL]** (#5368 → #6993) every model call a research step makes
  passes the one egress gate under its library, so a library that is local only reads and extracts with local models
  or parks the step with the reason. *Built:* the gate, obeyed by stored jobs (`llm/egress.py`,
  `fichero-server/tests/unit/llm/test_one_egress_gate_5368.py`). Not built: research steps as stored jobs; a proof
  that the chat tool loop passes the gate; the same answer told to an outside driver, whose own model Fichero cannot
  gate (`research.ops.driver.outside-reads-only-what-may-leave`). *Test (to write):* test_research_step_obeys_egress.py.
- `research.ops.journal.is-three-records-read-together` — **[GAP]** (#1848 → #6993) what a research run did is read
  from the audit rows of the agent account's writes, the search log, and each step job's row (driver, harness, model,
  place, cost, checks, critic's verdict), joined by the step's id. No fourth record is written, and a claim's
  provenance stays on its row. *Test (to write):* test_research_journal_join.py.

### E. Reading and extracting before Accept

- `research.ops.staged.read-and-extract-before-accept` — **[GAP]** (#2072 → #6995) read and extract steps run on
  documents in Staged. Their readings belong to the staged document; their names and statements are held as
  proposed, attributed to the agent's account and the step, and are left out of the project's graph views, counts,
  search and exports until the document is accepted. The Staged view shows, per waiting import, what was read and
  how many names and statements are proposed, so the person accepts knowing what a source says. *Test (to write):*
  test_research_proposed_claims_on_staged.py (a proposed claim is in no graph count; Accept makes it an ordinary
  unconfirmed claim).
- `research.ops.staged.reject-removes-what-was-proposed` — **[GAP]** (#2072 → #6995) Reject on a staged import puts
  the documents in the Trash (`research.plan.staged-imports-wait-for-yes`) and removes every reading, name and
  statement the read and extract steps proposed from them, as one undoable step; a name that other, accepted sources
  also carry is kept and loses only the rejected mentions. A IIIF import, which is not undoable as an action
  (`api/routes/ingest/iiif.py`), is taken back this way. *Test (to write):* test_research_reject_removes_proposed.py.

### F. Catalogues

- `research.ops.catalogue.adapter-has-one-shape` — **[GAP]** (#2072 → #6989) a catalogue adapter is one small module
  with `describe()`, `search(query, page)` and `record(id)`; it fetches only through the polite fetcher
  (`media/iiif_fetch.py` `PoliteFetcher`) at the rate it states, writes a search-log row for every query, and returns
  hits in one shape. A register row is made only from a hit an adapter returned and a URL that answered, never from a
  model's memory. *Test (to write):* test_catalogue_adapter_shape.py (a fake adapter; a row with no adapter hit
  behind it is refused).
- `research.ops.catalogue.the-project-first-then-iiif-and-web` — **[GAP]** (#2072 → #6989) the first adapters are the
  project's own search, which every search step runs first and whose hits end the lead as found with no import; a
  IIIF collection walk (nested, Presentation 2 and 3); and web search with the log row and the hit shape. *Built:*
  the collection import (`importers/iiif_import.py`), web search as a chat tool (`api/routes/research/tools.py`), the
  project's search. Not built: any of them as an adapter. *Test (to write):* test_catalogue_first_adapters.py.
- `research.ops.catalogue.login-or-block-means-requested` — **[GAP]** (#2072 → #6989) an adapter whose `describe()`
  says it needs a login, or that meets a refusal, a challenge page or a rate limit it cannot wait out, stops at
  once: the lead's outcome becomes requested, with the catalogue, the terms as they would be typed and the reason. No
  login is scripted and no other route to that catalogue is tried. Files or a manifest URL dropped on the lead start
  its import step. *Test (to write):* test_catalogue_requested.py.
- `research.ops.catalogue.harvest-protocols` — **[GAP]** (#2072 → #6996) adapters for OAI-PMH, SRU and IIIF Content
  Search and Change Discovery, one module each, each with its terms and rate in `describe()`. *Test (to write):*
  test_catalogue_protocol_adapters.py (recorded responses; no network in the test).
- `research.ops.register.exports-a-bibliography` — **[GAP]** (#2072 → #6990) the source register exports as BibTeX by
  script, and the dossier's citation check reads that export beside the one the person's reference manager writes; a
  key in neither is red. *Test (to write):* test_register_bibtex_export.py.

### G. Compare and the dossier

- `research.ops.compare.a-table-of-claim-ids` — **[GAP]** (#2069 → #6997) a compare step writes, for a milestone, a
  table whose rows are things claimed and whose columns are sources; each cell holds claim ids, and a row is marked
  as agreement, contradiction or a gap. It uses the graph's own triangulation (`knowledge/triangulation.py`) and
  resolves nothing. *Test (to write):* test_research_compare_table.py.
- `research.ops.dossier.claims-in-order-never-prose` — **[GAP]** (#2069 → #6997) a dossier step writes one note per
  milestone: the claims grouped under the sub-question in a proposed order, each a clause carrying its claim ids, its
  source, page and quote, with inferences marked and naming what they rest on. It contains no connected prose, and
  the step can write to no other note. *Test (to write):* test_research_dossier_note.py (a paragraph with no claim id
  is red; a write to another note is refused).

### H. Learning

- `research.ops.learn.term-yield-ranks-the-next-batch` — **[GAP]** (#2072 → #6998) each search-log row carries what
  came of it (hits kept, staged, accepted). The next batch of terms for a milestone is ordered by yield per term,
  origin and catalogue; a term with three empty runs is retired and listed with its runs. *Test (to write):*
  test_research_term_yield.py.
- `research.ops.learn.kg-proposes-terms` — **[GAP]** (#2072 → #6998) after each extract step a script proposes search
  terms from the graph: names with their spelling variants (`knowledge/dedupe.py` `spelling_key`), alternate labels
  from authority links (`knowledge/authorities.py`), gazetteer names in each catalogue's language, and date ranges
  from dated claims. Each term keeps the name it came from. Only an accepted document's names above the project's
  confidence bar seed a term (`record.confidence.unsure-readings-seed-nothing`); a model may translate and order
  them; a script caps how many run. An implied gap a person made a lead (`record.gap.implied-records-are-inferences`)
  arrives the same way. *Test (to write):* test_research_kg_term_expansion.py (a name under the bar seeds nothing;
  each term names its origin).
- `research.ops.learn.extractor-is-taught-and-measured` — **[GAP]** (#5536 → #6999) the person's accepted and
  corrected names and statements train the extractor (`kg.teach.*`, `kg/kg-confidence-and-provenance.md`), with one
  decision in ten held out by `record.check.one-in-ten-held-out`; an extractor's figure is its precision on the
  report half, per kind and band, and under 50 held-out decisions none is shown. *Test (to write):*
  test_research_extractor_figures.py. **Not built:** the owner's answer (2026-11-22) replaces the threshold above: an extractor's figure is shown only after 100 held-out decisions; below that the line says "not enough checked yet" and shows no number.
- `research.ops.learn.routing-by-failure-rate` — **[GAP]** (#2069 → #6999) per step kind and tier the engine keeps
  the share of steps that needed a fix round or an escalation; a kind over one half on a tier starts one tier up, and
  the Models and Compute row for that kind of work says so with the count. *Test (to write):*
  test_research_routing_by_failure.py.

### I. Driving a project

- `research.ops.driver.one-record-whoever-drives` — **[GAP]** (#2069 → #6992) a step driven from inside and a step
  driven from outside write the same rows through the same audited actions, are finished by the same engine call
  that runs the same checks, appear in Activity as rows of the same job model (an outside step's row says "driven
  from outside" and names the client), and appear in the Plan's Changes with the same Undo and Undo Pass
  (`research.plan.changes-with-undo`). Nothing in the record depends on which driver it was except the driver's name
  on the row. *Test (to write):* test_research_one_record_two_drivers.py (the same lead worked by a fake inside
  harness and a fake MCP client leaves rows that differ only in the driver).
- `research.ops.driver.research-tool-set-in-the-mcp` — **[GAP]** (#2069, #1848 → #6992) the Fichero MCP has a named
  tool set for research operations, and an agent account granted it is served no other tool: the read tools (the
  Plan, its leads, the brief, the search log, the register, Staged, documents, text, the graph, search); the step
  verbs (take a lead, begin a step, finish a step with its reported cost, release, ask a question); the adapter
  verbs (list the briefed catalogues, search one, fetch a record); and `fichero_actions_invoke` narrowed to a list of
  action names (search-log and register rows, an import into Staged, a recipe run on staged documents, proposed
  names and statements, the dossier note) with the undo tools. The narrowing is in the engine, by the account's
  grant (`research.per-model-tool-grants`), not in the client's configuration; a tool outside the set answers as if
  it did not exist. *Built:* `fichero_actions_invoke` and the undo tools among about 970 generated tools, with no
  narrowing. *Test (to write):* test_mcp_research_tool_set.py (an agent token lists only the set; a direct route
  outside it is refused).
- `research.ops.driver.agent-account-and-scoped-token` — **[GAP]** (#2069 → #6992) an agent account is a model's
  account with the editor role on one library, confined to one research folder: it imports only into that folder's
  Staged (`research.plan.staged-imports-wait-for-yes`) and writes nothing outside the folder. Its token is made by
  the person in the Mac app, never by a network caller; it names the library, the folder, the tool set and an
  expiry, is shown once, can be revoked from the same place, and is stored hashed. An inside harness is handed it in
  a file in its scratch directory, never in its arguments or the journal; for an outside driver the person pastes it
  into their agent's MCP configuration. *Built:* accounts, sessions and the three roles
  (`api/routes/auth/pairing.py`). *Test (to write):* test_research_agent_token.py (a write outside the folder
  refuses; a revoked or expired token refuses; the token is in no log line or job row).
- `research.ops.driver.one-driver-per-lead` — **[GAP]** (#2069 → #6992) a lead has at most one driver at a time. Taking
  a lead writes a lease (the lead, the driver, the account, since when, last heard from); a second take, from inside
  or outside, refuses and names the holder. Every tool call under the lease renews it; ten minutes of silence, a
  Stop in Activity, a finish or a release ends it, and a step it interrupted is left resumable. A milestone's compare
  and dossier steps take a lease on the milestone, which refuses while any of its leads is held. *Test (to write):*
  test_research_lead_lease.py (inside holds, outside is refused with the holder's name; silence frees it; Stop frees
  it).
- `research.ops.driver.adapter-answers-six-questions` — **[GAP]** (#2069 → #7000) inside, a step's turns go to a
  harness through an adapter with the builder's shape (`agent-profiles.adapter.interface`), each answer a value or
  unsupported with a reason: (1) the system prompt (the research role and the step kind's rules); (2) MCP servers
  (exactly the Fichero MCP, with the scoped token, in the harness's strict mode); (3) model and provider, from the
  Models and Compute row for the step's kind of work; (4) the non-interactive permission mode, with the harness's own
  file, shell and web tools off; (5) the tool-use policy hook, allowing only the research tool set; (6) the session
  read: tokens, cost and the done state, written to the job's row. A harness that cannot answer (2), (5) or (6)
  cannot take a step, and the refusal says which. Which harness runs a kind of work is chosen where its model is, in
  Models and Compute, and nowhere in Research. *Test (to write):* test_research_harness_adapter.py (a fake adapter
  unsupported for the policy hook refuses; the dry run's generated files name one MCP server and no other tool).
- `research.ops.driver.fichero-loop-and-claude-code-inside` — **[GAP]** (#2069 → #7000) two adapters ship first.
  **Fichero's own loop** is the chat tool loop run detached as the job (`research.runs-are-activity-jobs`), with the
  research tool set in place of the chat's allowlist. **Claude Code** is started by the engine as a child of the job
  with an appended system prompt, a settings source naming only the generated settings, a strict MCP file naming only
  the Fichero MCP, and a tool-use hook that refuses every tool outside the research set
  (`agent-profiles.adapter.claude-code`'s shape); its session file gives tokens and cost. Fichero finds an installed
  Claude Code by a version probe and shows it in Models and Compute as available or not installed; it never installs
  it, signs in to it or stores its credentials. Where the app cannot start a child process (a sandboxed build), the
  harness is shown as "outside only" with the reason. *Test (to write):* test_research_claude_code_adapter.py (the
  argv and the two generated files; not installed is said, never an error at run time).
- `research.ops.driver.pi-inside` — **[GAP]** (#2069 → #7000) the **Pi** adapter writes an agent directory for the
  step (the prompt by Pi's own mechanism, the Fichero MCP entry, a policy extension on its tool-call event that
  allows only the research set, and a model list in which every model has a price), starts Pi in its RPC mode and
  reads its events as the session (`agent-profiles.adapter.pi`'s shape). Its provider is a local runtime Fichero
  manages or an endpoint the person configured; an unpriced model refuses, so a cap can always be counted. *Test (to
  write):* test_research_pi_adapter.py (an unpriced model refuses; the agent directory holds one MCP entry).
- `research.ops.driver.outside-through-the-mcp` — **[PARTIAL]** (#2069 → #6992) an agent the person runs (Claude Code,
  Claude Desktop, Pi) drives a research folder by connecting to the Fichero MCP with an agent token: it reads the
  Plan and the approved brief, takes a lead, begins a step (which returns that step kind's brief and rules), calls
  the tools, and finishes the step, which runs the checks and answers with their result. Fichero ships a research
  skill for such agents that says only this order of calls; the rules themselves come back from the tools, so an
  agent with no skill is held to them all the same. *Built:* the MCP, `fichero_actions_invoke` and the undo tools
  with the actor from the session. Not built: the tool set, the step verbs, the lease, the Activity row. *Test (to
  write):* test_research_outside_driver.py (a scripted MCP client works one lead from take to finish; skipping
  "begin" refuses the writes).
- `research.ops.driver.outside-reads-only-what-may-leave` — **[GAP]** (#5368 → #6992) an outside driver's own model is
  not behind Fichero's egress gate, so the gate is applied to what it is served: an agent token for a library that is
  local only is refused page text and page pictures by the research tools unless the person, making the token,
  states that this agent runs on a local model; the token says which, and the Activity row shows it. *Test (to
  write):* test_research_outside_local_only.py.
- `research.ops.driver.the-pilot-is-driven-by-the-builder` — **[PARTIAL]** (#2069 → #6994) until the steps above land,
  the pilot is direction (b) with the builder as the driver: its policy hook allows `fichero_actions_invoke`, the
  undo tools and read tools and blocks every other tool; it works a new library made for the pilot and never a
  person's own; its imports go to one folder that stands in for Staged, and nothing leaves that folder without the
  person. *Built:* the builder's policy hook, caps and journal; the MCP tools. Not built: the agent account and
  token for the builder's worker, the pilot's project configuration and approved brief. *Test (to write):*
  test_pilot_policy_allowlist.py, in the builder's tests (a tool outside the three groups is refused).

## What this amends in `ui/research.md`

That spec's 2026-11-21 revision is not landed; it is not edited here. When it lands, these are the differences to
reconcile, in its file, under this ruling:

| Its line | Says | Becomes |
|---|---|---|
| `research.plan.leads-and-milestones` | a lead has passes of three kinds: search, import, read and tag | a lead has steps of four kinds (search, import, read, extract: "read and tag" is split), and a milestone has two (compare, dossier): six step kinds, `research.ops.step.six-kinds-in-order`. "Pass" and "step" are one thing; the word is step |
| `research.runs-are-activity-jobs` | names a search pass, an import pass and a read-and-tag pass | names the six kinds, and a row driven from outside (`research.ops.driver.one-record-whoever-drives`) |
| `research.plan.staged-imports-wait-for-yes` | Reject trashes the items and undoes that pass's other writes | also removes what read and extract proposed (`research.ops.staged.reject-removes-what-was-proposed`) |
| `research.plan.changes-with-undo` | Undo Pass reverses a pass | unchanged in behaviour; reads "Undo Step" if the word changes |
| `research.per-model-tool-grants` | the first grant: imports only into Staged | the research tool set is the second (`research.ops.driver.research-tool-set-in-the-mcp`) |
| its Build order, Stage 3 (Steps 3.1 to 3.5) | the operations views | is A5, A1, A1, A2 and A5 of this spec's order; the issues are that spec's, and this spec's steps add only their own lines |

## Build order

Twelve steps from the design (A1 to A6, B1 to B4, C1, C2), kept by those names in the titles, plus the pilot's
Stage 0 and the three hook-up steps. Each is 25 files or fewer. Where a step rides one of `ui/research.md`'s Stage 3
steps it says so and waits for it; it does not file that work twice.

### Stage 0 — The pilot today, driven from outside by the builder (no product code)

#### Step 0.1 — The pilot's brief, the builder's allowlist and the two caps
- Behaviours: `research.ops.driver.the-pilot-is-driven-by-the-builder`, `research.ops.caps.the-pilot-is-five-and-twenty`
- Tests: test_pilot_policy_allowlist.py, test_pilot_brief_caps.py
- Size: S

The builder's project configuration for the pilot (policy allowlist, 5 USD a run and 20 a day, the scriptable
catalogues as the brief lists them), the brief written by hand in this spec's shape and approved by the owner, a new
pilot library. Configuration and a brief, in the builder's own tree; nothing in the app or the engine.

### Stage 1 — A: found, staged, stoppable

#### Step 1.1 — A1: six step kinds on the lead's rows
- Behaviours: `research.ops.step.six-kinds-in-order`
- Tests: test_research_step_kinds.py, fichero/Tests/Unit/general/Models/ResearchModelsTests.swift
- Size: S

Rides `ui/research.md` Steps 3.2 and 3.3 (leads, milestones, outcomes; the search log; the register and its duplicate
refusal), which are the rest of A1.

#### Step 1.2 — A2: the agent account, its token, and the stops that are the person's
- Behaviours: `research.ops.driver.agent-account-and-scoped-token`, `research.ops.stops.five-are-the-persons`
- Tests: test_research_agent_token.py, test_research_owner_stops.py, fichero-server/tests/unit/actions/test_action_registry.py
- Depends on: 1.1
- Size: M

Rides `ui/research.md` Step 3.4 (Staged, Accept, Reject, the first grant), which is the rest of A2.

#### Step 1.3 — The outside driver: the research tool set, the lease, one record
- Behaviours: `research.ops.driver.research-tool-set-in-the-mcp`, `research.ops.driver.one-driver-per-lead`, `research.ops.driver.outside-through-the-mcp`, `research.ops.driver.one-record-whoever-drives`, `research.ops.driver.outside-reads-only-what-may-leave`
- Tests: test_mcp_research_tool_set.py, test_research_lead_lease.py, test_research_outside_driver.py, test_research_one_record_two_drivers.py, test_research_outside_local_only.py, fichero-mcp/tests/test_mcp_generated.py
- Depends on: 1.2
- Size: M

Built this early because the pilot is already driven this way: it replaces the builder's client-side allowlist with
the engine's. The step verbs, the lease row, the Activity row for an outside step. About 20 files.

#### Step 1.4 — A3: the brief from one sentence, its lint, Approve Brief
- Behaviours: `research.ops.brief.drafted-from-one-sentence`, `research.ops.brief.lint-refuses-what-cannot-run`, `research.ops.brief.approve-is-the-persons`, `research.ops.step.nothing-runs-without-an-approved-brief`
- Tests: test_research_brief_draft.py, test_research_brief_lint.py, test_research_brief_approve.py, test_research_brief_gates_steps.py
- Depends on: 1.1
- Size: M

#### Step 1.5 — A4: the adapter shape, the first adapters, requested
- Behaviours: `research.ops.catalogue.adapter-has-one-shape`, `research.ops.catalogue.the-project-first-then-iiif-and-web`, `research.ops.catalogue.login-or-block-means-requested`, `research.ops.brief.only-listed-catalogues-are-scripted`
- Tests: test_catalogue_adapter_shape.py, test_catalogue_first_adapters.py, test_catalogue_requested.py, test_research_only_briefed_catalogues.py
- Depends on: 1.4
- Size: M

#### Step 1.6 — A5: caps, the cloud answer and the journal on research steps
- Behaviours: `research.ops.caps.per-run-per-day-per-project`, `research.ops.cloud.the-library-decides`, `research.ops.journal.is-three-records-read-together`
- Tests: test_research_caps.py, test_research_step_obeys_egress.py, test_research_journal_join.py, fichero-server/tests/unit/llm/test_one_egress_gate_5368.py
- Depends on: 1.3, 1.5
- Size: M

Rides `ui/research.md` Steps 3.1 and 3.5 (runs are Activity jobs; Changes with undo), which are the rest of A5.

#### Step 1.7 — A6: search and import checks, autofix, the bibliography export
- Behaviours: `research.ops.check.scripts-judge-first`, `research.ops.check.not-run-is-never-green`, `research.ops.autofix.twice-then-up-then-parked`, `research.ops.register.exports-a-bibliography`
- Tests: test_research_step_checks.py, test_research_check_not_run.py, test_research_autofix_and_escalation.py, test_register_bibtex_export.py
- Depends on: 1.6
- Size: M

The check runner and the search and import rules land here; each later step adds its own kind's rules to the same
behaviour and the same test file.

#### Step 1.8 — Inside: the adapter seam, Fichero's own loop, Claude Code
- Behaviours: `research.ops.driver.adapter-answers-six-questions`, `research.ops.driver.fichero-loop-and-claude-code-inside`
- Tests: test_research_harness_adapter.py, test_research_claude_code_adapter.py, fichero-server/tests/unit/actions/test_chat_tools_loop.py
- Depends on: 1.6
- Size: M

#### Step 1.9 — Inside: Pi
- Behaviours: `research.ops.driver.pi-inside`
- Tests: test_research_pi_adapter.py
- Depends on: 1.8
- Size: S

### Stage 2 — B: sources worked, not only found

#### Step 2.1 — B1: read and extract on Staged, held as proposed; Reject removes them
- Behaviours: `research.ops.staged.read-and-extract-before-accept`, `research.ops.staged.reject-removes-what-was-proposed`
- Tests: test_research_proposed_claims_on_staged.py, test_research_reject_removes_proposed.py
- Depends on: 1.7
- Size: M

#### Step 2.2 — B2: the critic on check runs
- Behaviours: `research.ops.critic.a-different-larger-model`
- Tests: test_research_critic_differs.py
- Depends on: 2.1
- Size: S

#### Step 2.3 — B3: terms from the graph; term yield
- Behaviours: `research.ops.learn.kg-proposes-terms`, `research.ops.learn.term-yield-ranks-the-next-batch`
- Tests: test_research_kg_term_expansion.py, test_research_term_yield.py
- Depends on: 2.1
- Size: M

#### Step 2.4 — B4: OAI-PMH, SRU, Content Search
- Behaviours: `research.ops.catalogue.harvest-protocols`
- Tests: test_catalogue_protocol_adapters.py
- Depends on: 1.5
- Size: M

### Stage 3 — C: the writing starts here, and the figures get honest

#### Step 3.1 — C1: compare, then the dossier
- Behaviours: `research.ops.compare.a-table-of-claim-ids`, `research.ops.dossier.claims-in-order-never-prose`
- Tests: test_research_compare_table.py, test_research_dossier_note.py, fichero-server/tests/unit/kg/test_triangulation.py
- Depends on: 2.2
- Size: M

#### Step 3.2 — C2: the extractor taught and measured; routing by failure rate
- Behaviours: `research.ops.learn.extractor-is-taught-and-measured`, `research.ops.learn.routing-by-failure-rate`
- Tests: test_research_extractor_figures.py, test_research_routing_by_failure.py
- Depends on: 2.3
- Size: M

Waits for `kg/reconstruct-the-record.md` Step 0.2 (the one-in-ten hold-out).

## Risks, and what contains each

| Risk | Contained by |
|---|---|
| A source that does not exist | a register row needs an adapter's hit and a URL that answered; a claim needs a span found on the page; a citation must resolve; the critic is not the worker |
| Terms of use and rate limits | each adapter states its terms and rate; one polite fetcher; a block makes the lead requested; no login is scripted; rights travel with the import |
| Private material in the cloud | the library's answer at the egress gate; an outside driver is served page content only as the token allows; the pilot library holds public catalogue material only |
| Cost | three caps counted in the engine across both directions; a step count where no cost is reported; small models for mechanical steps; a result for the same input and model reused; IIIF by reference |
| A false "not found" | the outcome needs its search-log rows; the critic reads the terms tried |
| Two drivers on one lead | the lease, in the engine, refused by name |
| A harness with tools of its own | inside, the adapter turns them off and the policy hook refuses them; outside, the token's tool set and folder are the fence, and nothing an agent does elsewhere on the person's machine is Fichero's to promise |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | step kinds, the brief's lint and approval, checks, caps, the stops, proposed claims and Reject, adapters with recorded responses, the lease, the journal join | the files named above |
| MCP | y | the research tool set is all an agent token is served; a scripted client drives one lead; a direct route is refused | test_mcp_research_tool_set.py, test_research_outside_driver.py (to write), `fichero-mcp/tests/test_mcp_generated.py` |
| Harness adapters (pytest, fakes) | y | the six answers; argv and generated files for Claude Code; Pi's agent directory; not installed is said | test_research_harness_adapter.py and its two siblings (to write) |
| Pure rule (Swift) | y | Approve Brief enables on a green lint; the Staged row's proposed counts; a row driven from outside says so | with `ui/research.md`'s Plan tests |
| Builder | y | the pilot's policy allowlist and caps | test_pilot_policy_allowlist.py (to write) |

## Open questions for the owner

1. **A sandboxed build cannot start a child process.** There the inside direction is Fichero's own loop only, and
   Claude Code and Pi are "outside only". Recommended: accept that; the direct-download build offers all three.
2. **Cost an outside driver does not report.** The spec holds such a run to a step count per run and per day.
   Recommended figures: 15 steps a run, 60 a day, set in the brief beside the money caps.
3. **Local-only libraries and an outside agent.** The spec refuses page content to an agent token unless the person
   states, when making it, that the agent runs a local model. Recommended: keep that; it is a statement, not a proof,
   and the token says so.
4. **One word.** `ui/research.md` says "pass"; this spec says "step", as recipes and the builder do. Recommended:
   step everywhere, changed in that file when it lands.
5. **Which of Fichero's own loop and Claude Code is the default inside?** Recommended: Fichero's own loop, since it
   needs nothing installed; the harness is a choice in Models and Compute.
