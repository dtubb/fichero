# Fichero Harness console — one live source of work, one state per step, a page you can click into — Design Spec

> Milestone: Builder: agent profiles and generic workflows
> Manual: docs/contributor_manual/how-fichero-is-built.md — one section ("Watching the builder") saying that every piece
> of work has one state and an age on the console, that a lane page shows what was done and what it cost, and that the
> loop, not a person, moves work on, retries it, asks, or closes it out.

> **Status: DRAFT — written 2026-11-16 from the console review (kept untracked with the manager's briefs as
> `CONSOLE-REVIEW.md` and `build-order-proposed.md`) and the owner's direction of that day, paraphrased.** Tags: [OK] built
> and tested by name · [PARTIAL] exists, not wired · [GAP] not built · [BROKEN] built, wrong today. Issues: one per build-order
> step below, in the sibling's milestone. Scope with other specs: `harness/dev-workflows.md` keeps the loop's verbs (`run.loop-status` is replaced by
> § A–E here), the ladder, review, land and the jail; `harness/agent-profiles.md` keeps the run record
> (`agent-profiles.run.record`) and the columns of Runs, Compare and Bake-offs (`agent-profiles.console.runs`): this spec
> owns the pages they sit on, the one work tree the queue is fed from, the state and age of every step, what the loop does
> with stale work, and cleanup as a workflow step. The sibling's links to `harness/builder-website.md` mean this file.

## Decisions (owner 2026-11-16)

- **Fichero Harness is its own product**, and **for now its code stays inside the Fichero repository** (owner
  2026-11-16: the spec guards, specs and tests are already set up here); the repository split is Step 4.3, kept and
  **HELD** until the owner's word. When it moves, Fichero keeps only its project profile (`harness.toml` and
  `agents/projects/fichero/`). Public today in `fichero-builder/`: machine names, gate paths, the jail layout, prices and
  spend caps; a split means two repositories to version (the harness pins a Fichero profile version, Fichero pins a
  harness version) and one place to test generically. Direction: Fichero Harness may later be embedded in the Fichero app as **Fichero Researcher**, after the Harness is
  solid and not soon (owner 2026-11-16), so its core is a library with no app, no page and no GitHub assumption.
- **One engine API** (the one the MCP server exposes, § F) is what every front end renders: the HTML website and, later,
  a native Swift view inside Fichero. No page carries logic the API does not.
- **Everything is editable the same two ways** (website, MCP) through the same verbs, every edit audited (§ F).
- **The work store is host-agnostic** (§ A.3): a public GitHub repository, a private one, or a private store inside
  Fichero, behind one interface; "forgets nothing" never depends on GitHub.
- **Three project kinds to start** (`[project].kind`, consistent with `agent-profiles.project.profile`): `code` (a
  repository: Fichero or the owner's other code; profile = repo path, checks, tools, roles), `data` (research on a
  Fichero library's own records; this is Fichero Researcher when embedded in the app), `text` (a repository of writing,
  a book; its workers may call **Tinderbox** through its scripting interface or MCP as a declared tool of the profile).
  **Hosts** (terminal verbs, the website, inside Fichero) are independent of the kind: any host runs any kind.
- **The state store is Pydantic models over DuckDB** (owner 2026-11-16): the database system Fichero already uses,
  shared by builder, researcher, writer and the generic harness; `journal.jsonl` stays the append-only event log. A
  workflow may run on LangGraph or LangChain, or on Fichero's own workflows and recipes, as options behind one
  interface (`agent-profiles.workflow.declared`).
- **Costs and tokens are local only** (127.0.0.1): never in an issue, a comment or the repository; the page shows them,
  the work store never receives them.
- **Priority**: Fichero's release comes first; the Harness is a side project with one of the three worker slots (two
  on Fichero, one on the Harness).
- **Sequencing**: Stage 1 of `agent-profiles` (trailer, role prompts, jcodemunch + jdocmunch, Swift test rungs) and
  Stage 1 here (one state and age, stale work acted on, cleanup) are built in today's `fichero-builder/`. The repository
  split (`git subtree split` of `fichero-builder/` with its history into the Fichero Harness repository; Fichero keeps its
  profile) is Step 4.3 below, held until the owner says.

## Intent

The owner opens one page and sees what is being worked on, what worked, what failed and why, and what it cost, from one
live state; clicks a lane and sees everything it did; compares models, harnesses and roles over time. The builder is
**autonomous and forgets nothing**: the order of work is the queue's own, not a hand file that drifts; every step has one
state and an age; nothing half done is left silently; a finished step moves the lane to the next one; cleanup is a step
of the workflow. Project-neutral: a milestone, a step, a lane, a run and a commit mean the same for code, a book or a
research project; the page names no Fichero path, rung or branch, only what `harness.toml` declares.

## Terms

- **Work tree** — milestones › steps › lanes › runs, one record each, in `<state>/work.json` (§ A); the queue is a view of it.
- **Step** — one unit a lane takes (a build-order step or a cluster); it has exactly one **state** and an **age** (seconds in that state).
- **Lane** — one worktree working one milestone's steps in order; a **run** is one session of one worker on one step (`agent-profiles.run.record`).
- **Stale** — a step older in a non-final state than `[loop].stale_hours` for that state (defaults below); the loop acts on it.
- **Final states** — `landed`, `closed-out` (residue filed as an issue, tree swept), `retired` (a trial or a superseded lane, with its reason).

## Behaviours

### A. One live source of work (milestones › steps › lanes)

- `builder-console.ordered-work.one-source` [GAP] (#6645) (the order is `docs/contributor_manual/specs/build-order.md`, hand-edited
  last 2026-11-04, while tonight's lanes were queued by hand around it) — the ordered list of milestones the loop works is
  a record in `<state>/work.json`, written only by verbs: `builder order` (the console's drag, `builder milestone --enqueue`,
  `builder lane`, `queue add`) and `builder triage --order` (appends, never reorders). Every lane names its milestone and
  step; a lane started by hand on issues joins the tree under its issues' milestone (or `unfiled`, shown first, never
  hidden). The list's rows are GitHub milestone titles, so a spec name with no milestone (`dev-workflows` today) is refused
  with the milestone to make, never dropped. `build-order.md` becomes a generated copy written at each landing of the
  order, marked as such, never read. Acceptance: `queue add --lane x --issues 6600` puts lane x under `performance-sweep`;
  an order edit from the page is one `order` row and the next tick feeds from it; a name with no milestone is refused by
  name; the page and `builder status --json` show the same order. Test (to write): fichero-builder/tests/test_work_tree (new).
- `builder-console.work.counts-are-live` [GAP] (#6645) — each milestone row shows, from the work tree and the journal, not from
  issue counts: steps queued / running / waiting for check or review / blocked / done-not-landed / landed / closed-out,
  each with the oldest age in that state, the lane holding it, and the last failure (the newest red rung, NOT READY
  finding or question, one line). GitHub open/closed counts stay as a second, labelled pair ("GitHub: 31 open · 26
  closed"), never as a step state. "Lane running" means a lane with a non-final step; a finished lane is "last lane:
  <name>, landed <ago>". Acceptance (fixture tree): a milestone with one checking step and one blocked step shows both
  with ages and the blocked one's question; a milestone whose only lane is finished shows no running lane. Test (to write):
  fichero-builder/tests/test_work_tree (new), case test_counts_come_from_the_tree.
- `builder-console.store.one-database` [GAP] (#6644) (today: `queue.json`, `journal.jsonl`, `ladder-<lane>.json`, `review-<lane>.txt`,
  `question-*.txt`, `fix-*.txt`, read and joined by `console.py`) — the state of milestones › steps › lanes › runs › alerts
  › edits is one store, `<state>/harness.duckdb` (DuckDB, the database Fichero already uses, one file; owner 2026-11-16),
  with typed records (Pydantic models, one module, no engine import); `journal.jsonl` stays the append-only event log every change also writes, so a store rebuilt
  from the journal gives the same rows. The ladder and review results are rows (rung name, exit, seconds, tails; verdict,
  findings) keyed by lane, step and round; the text files are kept as attachments by path. `queue.json` is migrated on first
  open with a row and then never written. Every verb and every page reads the store through one module; nothing parses
  the journal to answer a page. Acceptance: a fixture journal replayed gives a store equal to one built live; the console's
  `/api/status` from the store equals today's for the fixed-rows test; a crash between a journal write and a store write
  is repaired on the next open. Test (to write): fichero-builder/tests/test_store (new).
- `builder-console.work-store.host-agnostic` [GAP] (#6644) (today `gh api`, `gh issue` in `console.py`, `milestone.py`, `landed.py`)
  — milestones, issues (steps' items), comments and labels are read and written through one interface, `WorkStore`:
  `milestones()`, `issues(milestone)`, `comment(issue, text)`, `label(issue, …)`, `close(issue, residue)`, `create(…)`, with
  three implementations chosen in `[project].work_store`: a public GitHub repository, a private GitHub repository (same
  code, a token), and a private store inside Fichero (the engine's records, for Fichero Researcher). The harness's own
  state (§ A.3, the step states, ages and runs) is never in the work store; only the items are. A store that is unreachable
  makes the loop keep working from its last copy and raises one alert, never stops a lane. Acceptance (fake stores): the
  loop runs a lane to landed on the GitHub store and on the in-Fichero store with the same rows; an unreachable store
  yields one alert and the lane goes on. Test (to write): fichero-builder/tests/test_work_store (new).

### B. One state and an age per step; stale work is surfaced and acted on

- `builder-console.step.one-state` [BROKEN] (#6643) (lane-qwen shows `done`, `paused`, and `blocked 4 h: retried once` at once;
  `done` means both "lane finished" and "worker said DONE, check pending") — a step is in exactly one of: `queued`, `sent`,
  `working`, `said-done` (DONE received, check not run), `checking`, `reviewing`, `fixing` (round n of 2), `blocked`
  (question, with the question), `red` (check failed, with the rung), `done-not-landed` (green and READY, not on the
  integration branch), `landed`, `closed-out`, `retired`. `paused` and `held` are **lane** flags shown beside the state
  ("said-done · lane paused since 11-08"), never a state; a lane is `finished` only when every step is final. `why` is the
  reason for the *current* state and is cleared on every transition (`queue.py` keeps the blocked reason on a `done` step
  today). Each state has an entered-at time; the page shows the age in words. Acceptance: a step through
  queued → sent → said-done → checking → red → fixing → said-done → checking → reviewing → done-not-landed → landed has at
  each point one state, a `why` about that state, and an age that resets; pausing the lane changes the flag and nothing
  else. Test (to write): fichero-builder/tests/test_step_state (new).
- `builder-console.stale.acted-on` [GAP] (#6646) (a week-old half-finished lane is a defect, owner 2026-11-16; 30 of 50 lanes today
  are finished-but-listed, two are 9-day-old paused trials, one is blocked on a question since 11-08) — every tick the loop
  lists each step older than `[loop].stale_hours.<state>` (defaults: said-done 1 h, checking 3 h, reviewing 3 h, fixing
  12 h, red 12 h, blocked 48 h, done-not-landed 24 h, queued 7 d, sent/working 2 × the step's usual run time) and acts,
  one action per step per tick, each a `stale` journal row naming the step, its age, the action and the result:
  `said-done` → run the check; `checking`/`reviewing` with no live activity → restart it; `red` → one re-brief with the
  rung's tail, then `blocked`; `fixing` past the rounds → `blocked`; `blocked` → ask again once (`builder ask`), then after
  `[loop].stale_hours.blocked` again file the residue as an issue and `closed-out`; `done-not-landed` → rebase and land, or
  `blocked` with the conflict; `queued` with its waits met → send; a paused or held lane past 7 d → an alert "retire or
  resume", and `retired` after 7 more unanswered. Nothing is ever silently left: a step the loop cannot move has an open
  alert, and the page's "Needs you" lists it with its age. Acceptance (fake clock, fake journal): each state past its
  hours gets its action and row; a lane paused 15 d is retired with a row; a step under its hours is untouched; the
  `stale` rows for one tick never act twice on one step. Test (to write): fichero-builder/tests/test_stale (new).
- `builder-console.step.moves-on` [PARTIAL] (#6646) (the queue feeds the next brief after a landing; a finished lane stops; a
  closed-out or retired step does not advance the cursor) — when a step reaches a final state the lane takes its next step
  itself, in the same session when one is open, else a fresh one; a lane with no step left takes the next step of its
  milestone from the work tree, and a milestone with none left frees the lane for the next milestone in order, within
  `[loop].lanes`. A `moves-on` row names the step left and the step taken. Acceptance: landing step 2 of 3 sends step 3
  within a tick; a closed-out step 2 sends step 3; the last step landed starts the next milestone's first step. Test (to
  write): fichero-builder/tests/test_moves_on (new).
- `builder-console.cleanup.is-a-step` [PARTIAL] (#6647) (`builder sweep` exists, offered by a button; `agent-profiles.cleanup.after-land`
  names the position) — cleanup is the last step of every lane and runs itself: once a step's head is on the integration
  branch its land snapshot goes; once a lane is `finished` its worker tree, feed, inbox and branch go after
  `[land].worktree_grace_hours`; a `retired` or `closed-out` lane's tree is patched to `<state>/patches/` then removed;
  stale parks older than 30 d become alerts; each removal is a `cleanup` row, and a tree whose head is not on origin is
  never removed (a row says why). The Worktrees tab lists only what cleanup could not do and why. Acceptance: a landed
  lane's tree is gone after the grace with a row; an unlanded tree stays with a row; the patch of a retired lane exists.
  Test (to write): fichero-builder/tests/test_cleanup_step (new).

### C. The page: what is worked on, what worked, what failed and why

- `builder-console.page.work-first` [GAP] (#6650) — the first tab is **Work**: the ordered milestones (§ A) with their live counts,
  the running steps at the top with lane, model, harness, age and the live line, then **Needs you** (blocked, stale,
  alerts, each with its age), then **Failed lately** (red rungs and NOT READY verdicts of the last 7 d, one line each with
  the lane page link), then **Landed lately**. Finished lanes and final steps are folded under "History (n)". No table
  with more than one meaning per column; every table has a header row that stays visible (the scroll container is the
  table's wrapper). Acceptance (fixture): the running step is the first row; a lane finished yesterday is under History; the
  blocked step shows its question and age. Test (to write): fichero-builder/tests/test_console_page (new).
- `builder-console.numbers.labelled` [BROKEN] (#6648) (lane-qwen's "1069" and "9.76" are the sum of 22 Pi sessions of 11-07 under
  a tooltip that says "today, API-equivalent"; the header row scrolls away; per-lane USD mixes all-time cost rows with
  today's transcripts) — every number on the page carries its unit, its period and its source in the cell, not a
  tooltip: `1 069 turns · 22 sessions · 11-07`, `$9.76 billed (OpenRouter)`, `$3.10 API-equivalent (Max, not billed)`,
  `91.4 M tokens (in 88.0 M · out 1.2 M · cache read 2.1 M · cache write 0.1 M)`, `4 h 42 min wall`. Billed and
  API-equivalent money are never one sum: the Spend card shows two figures. A number with no source reads `unknown`,
  never `0` or `-`. The totals on a lane row equal the sum of its runs' rows (§ D). Acceptance (fixture runs): the lane
  row's turns, tokens, money and wall are the sums of its run rows and name the period; a Pi run and a Claude Code run on
  one lane give two money lines; a run with no price reads unknown. Test (to write):
  fichero-builder/tests/test_console_numbers (new).
- `builder-console.lane.page` [GAP] (#6649) (the disclosure shows steps, a 3 000-char brief, the worktree and two buttons; on disk
  but unshown: `ladder-<lane>.json`, `review-<lane>.txt`, `fix-<lane>-<step>-<n>.txt`, `question-<lane>-<step>.txt`,
  the verdict rows, the `worker` and `cost` rows, the commits) — every lane name links to `/lane/<id>`, served from
  `GET /api/lane/<id>` (journal, work tree, state files and git of the lane's tree; no gh). It shows: the one state with
  its reason and age; the milestone and step i of n; model, harness, role and provider of the current run; wall time
  (first sent → now or final) and per step; **Steps**: each with its state in words, age, its commits (sha, subject,
  issues, files changed), its check rounds (each rung: ok / red / not run, seconds, the tail on red), its review rounds
  (verdict, the findings text, round n of 2), its questions and answers; **Runs**: each session with generation, started,
  ended, end reason, turns, tokens in / out / cache read / cache write, money with its kind; **Brief** (whole, and each fix
  and retry brief); **Journal**: the lane's rows newest first with a filter by kind. "Commits waiting" counts the lane's
  own commits (those after the step's base), not the tree's. Nothing on the page is a Fichero name: the rung names, the
  branch and the tree paths come from the rows and `harness.toml`. Acceptance (fixture lane with two steps, one red round,
  one review round, two sessions): the page shows every item above with the numbers of § C.2; the landing count is the
  lane's commits; a lane of a text project (no rungs but `spellcheck`) renders the same way. Test (to write):
  fichero-builder/tests/test_lane_page (new).

### D. Usage per run; comparison across models, harnesses and roles

- `builder-console.runs.page` [GAP] (#6651) (columns and data source: `agent-profiles.console.runs`; rows: `agent-profiles.run.record`)
  — **Runs** is a tab: one row per run from `GET /api/runs` (paged, filters project / milestone / role / model / harness /
  state / date), each row linking to its lane page and step; the page's totals are sums of the shown rows and say so. A
  cost row written before the run record exists (today's `cost` rows) is shown as a run with `source: cost row` and the
  fields it has, so history is kept. Acceptance: the fixture's 22 rows of one lane sum to the lane page's totals; a filter
  by harness `pi` keeps 22 and by `claude-code` keeps 0; an old cost row renders with unknown cache fields. Test (to write):
  fichero-builder/tests/test_console_runs (new) (shared with the sibling; the sibling's cases own the columns).
- `builder-console.compare.page` [GAP] (#6652) — **Compare** shows, per role, one row per model × harness over a window (7 d, 30 d,
  all) and by week: runs, steps landed, landing rate, median review rounds, median wall per landed step, median turns,
  tokens per landed step, money per landed step (billed and API-equivalent apart), refusals and stale actions; a pair
  with fewer than 3 runs is marked "too few to rank". **Bake-offs** shows the runs that share a brief id side by side with
  the same columns, the reference pair marked (`agent-profiles.bakeoff.measured`). Both read `/api/runs`; neither changes
  `[models]`. Acceptance (fixture): two pairs on `backend` rank by landing rate then money; a bake-off of two runs on one
  brief shows both; a window with no runs renders empty, not an error. Test (to write): fichero-builder/tests/test_console_compare (new).

### E. Generic and safe

- `builder-console.project.neutral` [PARTIAL] (#6653) (`console.py` names `integration`, `fichero-server/tests`, `Fichero-dev-*.dmg`,
  the `measure_x` scripts) — every project word on the page comes from `harness.toml` (`[project]` kind, name, tools,
  `[land].branch`, the rungs, `[machines]`) or from rows. The three kinds render the same pages with their own words: a
  `code` project its rungs and build; a `text` project (steps `draft`, `edit`, `source`, `review`; a declared tool such as
  Tinderbox listed under the role that may call it) with no DMG, no "Install", no app build; a `data` project (a Fichero
  library; steps `find`, `read`, `note`, `file`) with its library name and notes count in place of commits, and the same
  lane page. A host is not a kind: the same API serves the terminal, the website and the in-app view. Acceptance: with a
  `harness.toml` for a book project and one for a library the Work, Lane, Runs and Compare pages render and contain no
  word from the Fichero code profile; the text project's lane page names Tinderbox as a tool of its `writing` role. Test
  (to write): fichero-builder/tests/test_console_second_project (new).
- `builder-console.read-only-by-get` [OK] (#6649) (`console.py` `do_GET`/`do_POST`) — every `GET` is read-only; every action is a
  `POST /api/action` with the page's token and a loopback Host, onto the verb allow-list, one `console` row each. The new
  routes `/api/lane/<id>`, `/api/runs`, `/api/work` are GET only. Test: fichero-builder/tests/test_status_page.py (extend
  with the three routes).

### F. One API, two front ends, editable both ways

- `builder-console.api.one-engine` [PARTIAL] (#6654) (`/api/*` routes exist for the page only; the lane dict is built in the route)
  — every read and every verb is one API (`GET /api/work`, `/api/lane/<id>`, `/api/runs`, `/api/roles`, `/api/workflows`,
  `/api/alerts`; `POST /api/action {verb, args}`), served by the harness's engine module over HTTP on 127.0.0.1 and
  exposed one-to-one by the harness MCP server (one tool per verb, one resource per read). The HTML page and, later, a
  Swift view inside Fichero render the same JSON; a page shows nothing the API does not return, so the two never
  disagree. Acceptance: for each page, the test renders it from a recorded API response alone; an MCP `lane` resource and
  `GET /api/lane/<id>` return the same document. Test (to write): fichero-builder/tests/test_api_one_engine (new).
- `builder-console.repo.split-held` [GAP] (#6656; HELD, owner 2026-11-16) — the repository split (`git subtree split`
  of `fichero-builder/` with its history into a Fichero Harness repository; Fichero keeps `harness.toml` and
  `agents/projects/fichero/`; the harness pins a Fichero profile version and Fichero pins a harness version) is a step
  that exists and is not taken until the owner says; until then every harness change lands here under these guards. The
  `data` kind and the in-Fichero work store (the third `WorkStore`) go with it when Fichero Researcher starts.
  Acceptance (when taken): the harness repository's whole suite is green on the three fixture kinds with no Fichero code
  word; Fichero's gate still runs its profile. Test (to write): fichero-builder/tests/test_console_second_project (new).
- `builder-console.edit.both-ways` [GAP] (#6655) — workers, roles, prompts, workflows and controls are editable visually on the
  website and through the MCP server with the same verbs: `role add|edit` (name, prompt file, model, harness, provider),
  `prompt edit` (common, role, project layer), `workflow edit` (a project's ordered steps and their rungs), `models set`
  (model and harness per role; a move cites a bake-off or a person), `pause|resume|stop|retry <lane>`,
  `alert approve|dismiss|park <id>`, `order`. Every edit is one audited row (who: a person at the page, or the MCP client's
  name; what; before and after as a diff) and a commit of the edited file when it is a tracked prompt or `harness.toml`;
  a refused edit is a row too. The page's forms and the MCP tool schemas are generated from one verb table (today's
  `VERBS` in `console.py`, with argument types). Acceptance: editing a role's model from the page and from MCP produce the
  same file diff and the same audit row shape; an unknown verb is refused on both; the Edits tab lists the rows newest
  first. Test (to write): fichero-builder/tests/test_edit_both_ways (new).

## Open questions for the owner

A. Answered 2026-11-16: Pydantic models over DuckDB, the journal kept as the event log; § A.3 is written against it.
B. **Which work stores ship first.** GitHub public and private share one implementation and exist today; the in-Fichero
   store needs the engine's records and the Researcher front end. [PROPOSED: GitHub first; the in-Fichero store when
   Fichero Researcher starts, behind the interface from day one so no page or verb learns GitHub.]
1. The stale hours above: are the defaults right, and is `blocked → closed-out after 2 × 48 h unanswered` too eager? [PROPOSED: yes; a closed-out step is an issue with its residue, nothing is lost.]
2. Does a `retired` lane keep its runs on Compare? [PROPOSED: yes, flagged `retired`; a trial is data.]
3. Answered 2026-11-16: money and tokens are local only, 127.0.0.1, never in an issue or the repository.
4. Is the work tree one file (`work.json`) replacing `queue.json`, or `queue.json` plus a `milestones` record? [PROPOSED: one file; `queue.json` is read once and migrated with a row.]

## Build order

Smallest first; each step is one lane batch; `Depends on` defaults to the step before. Steps 1.x make the loop forget
nothing; 2.x make the page say it; 3.x compare; 4.3 is held.

### Stage 1 — one state, one source, the loop acts

#### Step 1.1 — one state per step with an age; `why` is about the current state; paused and held are flags
- Behaviours: `builder-console.step.one-state`
- Tests: fichero-builder/tests/test_step_state (new)
- Size: S

#### Step 1.2 — the store: DuckDB + Pydantic records with the journal as its log, and the WorkStore interface with its GitHub implementation
- Behaviours: `builder-console.store.one-database`, `builder-console.work-store.host-agnostic`
- Tests: fichero-builder/tests/test_store (new), fichero-builder/tests/test_work_store (new)
- Size: M

#### Step 1.3 — the work tree in the store: milestones › steps › lanes; the order is a record; `build-order.md` is generated
- Behaviours: `builder-console.ordered-work.one-source`, `builder-console.work.counts-are-live`
- Tests: fichero-builder/tests/test_work_tree (new)
- Size: M

#### Step 1.4 — stale work is listed and acted on every tick; a finished step moves the lane on
- Behaviours: `builder-console.stale.acted-on`, `builder-console.step.moves-on`
- Tests: fichero-builder/tests/test_stale (new), fichero-builder/tests/test_moves_on (new)
- Size: M

#### Step 1.5 — cleanup as the last step of every lane
- Behaviours: `builder-console.cleanup.is-a-step`
- Tests: fichero-builder/tests/test_cleanup_step (new)
- Depends on: 1.2
- Size: S

### Stage 2 — the page

#### Step 2.1 — labelled numbers everywhere; a header row that stays; billed and API-equivalent apart
- Behaviours: `builder-console.numbers.labelled`
- Tests: fichero-builder/tests/test_console_numbers (new)
- Depends on: 1.1
- Size: S

#### Step 2.2 — the lane page and `GET /api/lane/<id>`
- Behaviours: `builder-console.lane.page`, `builder-console.read-only-by-get`
- Tests: fichero-builder/tests/test_lane_page (new), fichero-builder/tests/test_status_page.py
- Depends on: 2.1
- Size: M

#### Step 2.3 — the Work tab first: running, needs you, failed lately, landed lately, history folded
- Behaviours: `builder-console.page.work-first`
- Tests: fichero-builder/tests/test_console_page (new)
- Depends on: 1.2, 2.2
- Size: M

### Stage 3 — runs and comparison (needs the sibling's run record, `agent-profiles` Step 2.2, #6628)

#### Step 3.1 — the Runs tab on `/api/runs`, old cost rows shown as runs, after the sibling's #6628
- Behaviours: `builder-console.runs.page`
- Tests: fichero-builder/tests/test_console_runs (new)
- Depends on: 2.3
- Size: S

#### Step 3.2 — Compare and Bake-offs
- Behaviours: `builder-console.compare.page`
- Tests: fichero-builder/tests/test_console_compare (new)
- Size: M

#### Step 3.3 — the pages on a second project of kind `text`, after the sibling's #6627
- Behaviours: `builder-console.project.neutral`
- Tests: fichero-builder/tests/test_console_second_project (new)
- Depends on: 3.2
- Size: S

### Stage 4 — one API, edits both ways, the separate repository

#### Step 4.1 — the verb table generates the page's forms and the MCP tools; reads are one API
- Behaviours: `builder-console.api.one-engine`
- Tests: fichero-builder/tests/test_api_one_engine (new)
- Depends on: 2.2
- Size: M

#### Step 4.2 — roles, prompts, workflows, models and controls editable from the page and MCP, audited
- Behaviours: `builder-console.edit.both-ways`
- Tests: fichero-builder/tests/test_edit_both_ways (new)
- Depends on: 4.1
- Size: M

#### Step 4.3 — HELD (owner 2026-11-16): the repository split into a Fichero Harness repository, the data kind and the in-Fichero work store
- Behaviours: `builder-console.repo.split-held`
- Tests: fichero-builder/tests/test_console_second_project (new)
- Depends on: 4.2
- Size: M

## Behaviour tests

| Behaviour | Step |
|---|---|
| `builder-console.step.one-state` | 1.1 |
| `builder-console.store.one-database` · `work-store.host-agnostic` | 1.2 |
| `builder-console.ordered-work.one-source` · `work.counts-are-live` | 1.3 |
| `builder-console.stale.acted-on` · `step.moves-on` | 1.4 |
| `builder-console.cleanup.is-a-step` | 1.5 |
| `builder-console.numbers.labelled` | 2.1 |
| `builder-console.lane.page` · `read-only-by-get` | 2.2 |
| `builder-console.page.work-first` | 2.3 |
| `builder-console.runs.page` | 3.1 |
| `builder-console.compare.page` | 3.2 |
| `builder-console.project.neutral` | 3.3 |
| `builder-console.api.one-engine` | 4.1 |
| `builder-console.edit.both-ways` | 4.2 |
| `builder-console.repo.split-held` | 4.3 (held) |

## Changes to other specs

- In `dev-workflows` `run.loop-status`: its page text is replaced by § C; its JSON (`/status.json`) gains `work`, every lane's
  one `state`, `state_since`, `flags` and the labelled numbers, and drops `done: true` on a lane dict.
- In `dev-workflows` `tool.queue`: the step states are § B's list; `paused` is a lane flag; a finished lane takes the next
  milestone from the work tree (§ B.3), and `build-order.md` is no longer read.
- In `agent-profiles` `console.runs`, `cleanup.after-land`, its § G and Step 2.3: the sibling now names this file; the loop behaviours of § B (stale, moves-on, cleanup) may move into that spec's
  workflow section if the owner prefers one home for the loop.
- In `harness/issues-and-labels.md`: "read by `builder milestone`, `builder queue` and the loop" now names the work tree.
- In `agent-profiles` `project.profile`: `[project].kind` is one of `code`, `data`, `text` (not `code` or `text`); a `text`
  profile may declare Tinderbox as a role's tool; `[project].work_store` names the store (§ A.4); the sequencing in
  Decisions above (everything in `fichero-builder/` inside the Fichero repository; the split held) applies to both specs.
