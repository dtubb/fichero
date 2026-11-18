# Phase 0 report — `building-fichero-locally.md` (2026-11-18)

> **Decision:** written by the supervising manager after reading this report (a journal row and one line here). This report was
> prepared by the Phase 0 worker; nothing was built; every GitHub write waits for the manager's yes.

## What Phase 0 did

Branch `harness-phase0-2026-11-18` on top of `origin/integration` `b56999b271`:

1. The spec is in the repo (`docs/contributor_manual/specs/harness/building-fichero-locally.md`), first verbatim, then made to pass the
   spec guards (the `> Milestone:` line carries one word; every `local.*` [GAP] cites the parent #6116; the page is in the docs nav).
2. Ten specs absorbed, one commit each, verbatim under their ids and tags: `dev-workflows` (165), `agent-profiles` (26), `builder-console`
   (18), `performance-sweep` (20), `issues-and-labels` (6), `git-worktree-workflow` (9 of 10), `performance-sweep-REVIEW` (as notes),
   `deterministic-conductor` (the 12 this spec still wants; the rest stays as history), `spec-pipeline` (18: the check rules and two triaged
   issues; the rest history), `dev-orchestration-harness` and `builder-mac-app` (pointers; their behaviours stay as history under their ids).
   Nothing deleted, no id renamed, no id defined in two files. Citations that named tests which do not exist became owed tests (debt
   251/28 to 224/26). Repointed in the same commits: `build-order.md` entry 1, the Builder README, the docs nav, `test_dev_workflows_spec.py`,
   the `spec_pipeline` baseline. The history files carry `> Milestone: Builder` so `builder triage` never recreates a closed milestone.
3. Sixteen `local.*` behaviours that repeated an existing id were cut (review § 5); the survivors carry the new sentences. The Build order is
   nine stages and 28 `#### Step N.M` headings `builder steps` can file. The dev-workflows Behaviour tests table gained its 35 missing rows.
4. The GitHub batch is planned, not run (below). `builder triage --milestones --dry` was run with its journal redirected to a scratch folder.
5. The review is beside the spec: `building-fichero-locally-REVIEW.md`.

## Before and after

| | Before (`b56999b271`) | After (this branch; GitHub after the batch) |
|---|---|---|
| Harness spec files | 19 (10 about the Builder, 9 about Fichero) | 20: 1 live Builder spec, 10 superseded pointers/history files, 9 Fichero specs (proposed to move out of `specs/harness/`) |
| Behaviours about the Builder | 335 across ten files (165+46+26+18+20+12+10+6+23+... counted by the bullet regex) | 307 in the one spec (33 `local.*`), 12 + 23 + 1 + 8 + 34 left as history in five files |
| Harness milestones | 7 open (#282 dev-orchestration-harness, #357, #356, #347, #297, #283; no `dev-workflows` exists) | 1: `Builder` (#282 renamed); five closed |
| Open issues in them | 66, plus 10 harness issues with no milestone | 75 in `Builder`; #6609 (a product bug) to `Next release` |
| Checkers | citations, tagged, broken-has-issue, no-duplicates, acceptance, milestones, specs-have-tests, docs-publication green; docs-paths red (29) | the same; `test_dev_workflows_spec.py` goes from 1 red to green |

## The answers to the twelve questions

### 5. The control numbers on Sonnet today (answered first)

Source: the Builder journal (`journal.jsonl`, read-only), `queue` rows 2026-11-02 to 2026-11-18 (17 calendar days; 6,868 rows; 414 lane+step
pairs). Sonnet = every lane except `lane-qwen`/`lane-qwen2` (4 steps); the builder role has been `claude-code`/`sonnet` throughout. The nightly
build's pseudo-steps (`build*`, `verify*`) and the `-` lane are excluded: 407 worker steps.

| Number | Value | How it was computed |
|---|---|---|
| Steps landed | 297 of 407 (73 %) | a `queue` row `state: landed` for the lane+step |
| READY within two fix rounds | 297 of 297 landed; **263 (89 %) needed no fix brief, 11 one, 23 two** | `fix brief, round N` rows (`state: sent`); the loop blocks after round 2 (`run.loop-fix-rounds`), so "landed" already means ≤ 2: the honest control is the 89 % zero-round share |
| Steps with a NOT READY review | 129 of 297 landed had at least one row naming NOT READY; 38 had three or more | rows of the step containing `NOT READY` (reviews re-run inside a fix round) |
| Share blocked | 200 of 407 (49 %) were `blocked` at some point; 6 (1.5 %) ended the window blocked or parked; 11 were parked at least once | last `queue` state; `blocked` is the loop's normal state while a red check or review goes back to the worker |
| Not landed in the window | 110: 19 queued, 9 told, 47 superseded, 7 done-refused, 5 dropped, 6 blocked/parked, 17 in flight or build pseudo-states | last state |
| Handoffs per lane | 7 rows name a handoff in 17 days, in 4 lanes (lane-ie 3, perf-review 2, lane-onboard 1, lane-sharing 1); no `generation` row exists | `queue`/`work` details; sessions mostly end by DONE and take the next brief, so handoffs are rare, not absent |
| Cost per landed step | **not in the journal**: no row carries `usd`, `tokens` or a price; the only ledger is `qwen-ledger.jsonl` (10 hand rows for #6380) | every key of every row scanned. **First gap: `dev-workflows.ledger.one-row-per-unit` (#6379).** The real number for the Max plan is tokens, which only the worker's session files hold |
| Steps landed per day | 297 / 17 = 17.5; median 11; peak 64 (2026-11-08); 137 (46 %) landed between 22:00 and 08:00 | `landed` timestamps by day |
| Fichero lanes vs harness lanes | Fichero: 177 landed of 239 steps in 43 lanes = **10.4 a day**; harness: 120 of 168 in 44 lanes = **7.1 a day** (40 % of landings were harness work) | lane name prefix (`builder-`, `harness-`, `spec-`, `perf-`, `security*`, `release-*`, `remote-*`, `loop-lanes`, `rung-alerts`, ... = harness) |

Caveats: a step is a queue step (a cluster brief, often several issues), not an issue; nights with the loop off are in the window; the Qwen trial
(4 steps, 0 landed) is too small to compare.

### 1. What is on GitHub

| Merge list | Live (2026-11-18) | Open / closed | What the batch does |
|---|---|---|---|
| `dev-workflows` (rename to Builder) | **does not exist** | — | the dev-workflows step issues (#6116 parent, #6166, #6202, #6318, #6323, #6324, #6336, #6340, #6342, #6344) live in `dev-orchestration-harness` #282: **#282 is renamed `Builder`** (history kept) |
| `Builder: agent profiles and generic workflows` | #357 | 35 / 0 | move 35, close |
| `dev-orchestration-harness` | #282 | 17 / 37 | becomes `Builder`; #6356, #6357 (machine pool) stay open as deferred; #6609 (engine allowed-roots bug) to `Next release` #333 |
| `performance-sweep` | #356 | 9 / 0 | move 9, close |
| `builder-mac-app` | does not exist; it is `Builder app` #347 | 1 / 0 | move #6345 with a deferred comment, close |
| `spec-pipeline` | #297 | 2 / 0 | move #5112, #5461, close |
| `git-worktree-workflow` | #283 | 2 / 0 | move #4813, #4814, close |
| `ui-test-harness` | #278 | 16 / 8 | **product** (XCUITest and UI-smoke infrastructure of the app, a perf harness on an archive copy, accessibility of drawn boxes): left alone |

Left alone: `cloud-permission-and-spend` #348 (product), `github-hygiene` #331 and `checking` #343 (empty; `builder triage` closes empties),
every `Bugs - *`, `Performance - *`, `Lint - *` bucket. Cited issues: 155 distinct numbers in the ten specs; all resolve. Open with no
milestone: harness #6381, #6382, #6387, #6388, #6390, #6391, #6466, #6467, #6658, #6659 (to Builder); product rules #4259, #4367 (left).
32 open in product or ops milestones (left). 56 closed. Every conductor step issue (#6148–#6161, #6179, #6140, #6100, #6101, #6112) is already
closed; there is nothing to close as superseded. The spec's counts hold (64 distinct from dev-workflows, 22 agent-profiles, 16 builder-console,
28 dev-orchestration-harness of which 2 open and both product).

`builder triage --milestones --dry` on the merged tree would relabel 322 issues, move 663, create 21 milestones and close 6 — a whole-repo
triage. It is **not** the mechanism for this merge; the batch below does 1 rename, 60 moves and 5 closes with an undo list.

### 2. Which spec governs each topic

| Topic | Governs | Disagreement, resolution |
|---|---|---|
| Loop, lanes, sessions, handoff, ladder, land gate, tools | `dev-workflows.*` | the "only `builder landed --push`" rule is overturned: the loop pushes after READY and a green gate |
| Adapters, prompts, trailer, small worker, Swift rungs, manager, isolation | `agent-profiles.*` | `worker.small` vs the long-running worker (Q3); `role.manager` supervised by the supervising manager |
| Console, one database, one state per step | `builder-console.*` | DuckDB → SQLite (owner 2026-11-17) |
| Perf measurement, ratchets, warnings | `perf-sweep.*` | `rung.not-run-is-visible` [BROKEN] fixed before any enforcement |
| Issues, labels, milestones, build order | `issues.*`, `dev-workflows.tool.triage` | `pipeline.closes-issues`, `pipeline.issues-and-milestones-kept-current` kept as the older words; `issues.*` governs |
| Spec ↔ issues ↔ tests check | `pipeline.check.*`, `pipeline.status` | `builder triage --specs/--milestones` covers needs-spec and milestone mapping, not the a–h rules on tags, [OK] tests and closed issues; `scripts/spec_pipeline.py` exists, is tested and is not in the gate: kept as the seed of `local.spec-lint` |
| CI, nightly, release | `pipeline.github-actions`, `pipeline.nightly-gate`, `pipeline.weekly-release`, `dev-workflows.run.nightly-build` | the maintainer's yes kept for alpha/beta/release; dev automatic |
| Worktrees | `git.*` | `git.shared-venv` [OK] stays in its old file: its test exists nowhere |
| Roles and routing | `orch.*` | all superseded by `dev-workflows.models.by-config`; history |

### 3. Does `agent-profiles.worker.small` conflict with the long-running worker?

`agent-profiles.worker.small` [GAP] (#6625): a worker gets one step, a brief under 120 lines naming its files and tests, and a diff bound
per role; the brief tool refuses a cluster with more than one step. `dev-workflows.tool.queue` [PARTIAL] (#6166): one long-running worker per
lane, fed step by step, so it keeps what it has read; a good `DONE <sha>` ends the step, not the session.

They conflict only if "a worker" means "a session". Read as the owner ruled: `worker.small` bounds the **brief**, `tool.queue` bounds the
**session**; a session receives many one-step briefs in turn. One tension is real: the diff bound must be counted per step (commits since the
step's base, as `tool.check` already does), not per session. Resolution: the long-running worker wins (owner 2026-11-01), `worker.small` is
read as "one step per brief", the bound is per step. The owner is told here.

### 4. Which `local.*` behaviours repeat an existing one

Sixteen, cut in commit `10c1cad046`; the table is in the review § 5. Thirty-three `local.*` remain, each saying something no existing id says.

### 6. Can a Pi worker start today? What is missing, by file

No. Exists: `fichero-builder/fichero_builder/pi_rpc.py` (the `pi --mode rpc` process, `start`, `priced`, `pi_procs`, the policy argv),
`fichero-builder/pi/policy.ts` (the fail-closed tool-call extension), `session.py` reads a Pi session (fixtures `tests/fixtures/pi-session-*.jsonl`),
`watcher.py` knows the Pi handoff is delivered by the watcher, `harness.toml [models].providers` lists `anthropic` and `omlx` as Pi providers.
Missing:

- On `fichero_builder/adapters.py`: only `ClaudeCode` answers the six adapter questions; a `Pi` adapter is owed (`agent-profiles.adapter.pi`, #6631).
- On `fichero_builder/run.py` and `queue.py`: lanes are `worker`/`external`; nothing routes a lane to `pi_rpc.start` or feeds `msg-<seq>.txt` into an RPC session.
- On `harness.toml`: no `openrouter` provider, no price row for an OpenRouter model (`pi_rpc.priced` refuses an unpriced model; `watcher.refusals` parks it); `[spend].window` is Sonnet's.
- On `fichero_builder/profiles.py`: the common prompt folder exists; a Pi role prompt and the `diff_bound:` role files do not.
- On `policy_hook.py` / `pi/policy.ts`: wired through `pi_rpc.policy_argv`, never run live. Tests exist for the pieces; a live start against a priced provider is owed.

Four files of work before the first Pi lane (Step 1.1); the key comes from the environment and is written nowhere.

### 7. Pi and Xcode

Not tried in Phase 0. Known: Xcode 27's MCP server is reached through `xcrun mcpbridge` when "Allow external agents to use Xcode tools" is on,
and it talks to the Xcode open in **the calling user's GUI session**; Pi loads MCP servers, so an Xcode worker is a Pi worker with that server in
its MCP config. It cannot sit in the jail as the jail is today (a second user with no GUI session). The design that fits the three accounts:
the Xcode worker runs **as the GUI test user**, who owns Xcode and the Swift test run (`dev-workflows.run.swift-tests`), one Xcode per lane
worktree, with the policy extension and the sandbox profile as its walls; never as the owner. The other direction (Xcode hosting Pi through the
Agent Client Protocol) is a Stage 8 trial, recorded, not decided now. The repo already carries commits "using Xcode using Fichero Builder".

### 8. The model slate

Not measurable in Phase 0 and not asserted from memory: exact OpenRouter ids, serving providers and quantizations change weekly and are read from
OpenRouter at Stage 1 and recorded per run (`local.bridge-openrouter`). The only named model, Qwen3-Coder-Next, is outside this reviewer's
knowledge; the Qwen3-Coder family has a 30B-A3B member (about 17–19 GB at 4-bit; fits the 85 GB budget several times) and a 480B-A35B member
(about 270 GB at 4-bit: never fits the Studio, OpenRouter only). The slate is chosen by `local.memory-budget` arithmetic once the ids are known:
builder + a different reviewer + helper ≤ 85 GB beside a build and the gate. Usable context on the Studio is a measurement (prompt re-read time
at 100k tokens), not a datasheet number.

### 9. What does not fit on the 16 GB M1 Pro

From `harness.toml`: the full nightly check (`[nightly].check_footprint_mb = 14336`; the Kraken two-model test peaks at 9.4 GB) runs on the 24 GB
`check_runner`; the smoke test on the overnight-only `smoke_machine`; daily builds and the perf rung on `[check].build_remote`; the engine gate
on `[check].remote` (three helpers in order; a runner under 6 GiB free is skipped); the dev DMG on `build_machine = "local"` (about 65 minutes,
the one heavy local job). Two lanes at once fit because no model is loaded locally. Stage 1 changes none of this (`local.interim-16gb`); Step 1.3
adds GitHub's hosted runners as a second place for engine tests, guards and scans.

### 10. Why tags have no release notes, and why ten trailer spellings

Tags `v2026.11.13` (11-13), `v2026.11.14` (11-14), `v2026.11.17` and `v2026.11.18` (both 11-17) exist; `RELEASE_NOTES.md` ends at `## 2026.11.12`,
`CHANGELOG.md` at `2026-11-12`, `docs/_latest.md` points at 2026.10.30. Why: `RELEASE_NOTES.md` is written by hand (`scripts/release-notes-gen.sh`
only backfills `CHANGELOG.md` backwards with a local model); `scripts/check_release_docs_ready.py` requires the section but runs on the public
release path, not on the dev tag; since 11-13 every tag has been a dev pre-release. `local.notes-with-every-tag` (Step 3.5) closes this.

Trailers since 2026-11-01 on `origin/integration`: `Directed-By: the maintainer` 583, `Co-Authored-By: Claude Sonnet 5.5` 513, `Written-By:
claude-sonnet-5-5` 321, `Co-Authored-By: Claude Opus 5.5` 247, `Written-By: Claude Sonnet 5.5` 185, `Written-By: claude-opus-5-5` 175,
`Written-By: Claude Fable 5.1` 145, `Written-By: Claude Opus 5.5` 125, `Co-Authored-By: Claude Fable 5.1` 103, `Written-By: sonnet using Claude
Code using Fichero Builder` 101, and ten more forms. Why: three rulings in sixteen days (11-05 one `Written-By`; 11-16 the three-part form); the live
`harness.toml` still accepts `Directed-By: the maintainer`; the brief names the model by its `/model` id in one place and its display name in another;
nothing normalises. `agent-profiles.trailer.one-line` (Step 1.4) is the fix and must land before the bake-off.

### 11. The plan for moving onto LangGraph

The engine pins `langgraph 1.2.22`; the Builder pins its own copy (`local.pinned-dependency`) and still imports nothing from the engine. First lane:
a **harness lane** (fichero-builder changes): the cheapest ladder (pytest only), and a fault hurts only the harness. Acceptance: `test_queue_verb.py`,
`test_loop.py`, `test_loop_survives.py`, `test_builder_restart.py`, `test_approve_resume.py` pass unchanged against the graph-backed lane, plus one new
test: a session fed three briefs hands off at its mark and the successor lands. A worker that runs for hours is **not** a node's call; it is an
external process the graph `interrupt`s on: the node writes the brief, the graph checkpoints to SQLite and stops; the loop's tick resumes the graph
with the session's event (DONE, handoff, parked). State per step is the graph's thread; the JSONL row is written by the node that moves state. The old
loop is deleted only when every lane has moved (Steps 5.1, 5.2).

### 12. The steps to file, sizes, what is not built, spend

**Steps** (the spec's Build order; `builder steps` files them): Stage 1 (4 steps: M, S, M, S), Stage 2 (5: M, M, S, L, M), Stage 3 (6: L, M, M, S, S, M),
Stage 4 (2: L, M), Stage 5 (2: L, L), Stage 6 (4: M, M, L, L), Stage 7 (2: M, M), Stage 8 (6: M, L, L, L, S, S), Stage 9 (1: S). 28 steps: 7 S, 11 M,
10 L. The shape guard flags every L; `agent-profiles.worker.small` says `builder steps` splits a step whose named files exceed the bound before any brief.

**Not built**: the Builder as a Mac app (12 behaviours, history); five adapters (opencode, Qwen Code, Codex CLI, Gemini CLI, goose); the
Researcher and text projects; machine pooling (retired at Stage 8); perf automation beyond budgets (app profiling, MetricKit, automatic issues);
console editing both ways; the repository split. A new harness feature after Stage 9 needs the owner.

**Spend**: OpenRouter ≤ 50 USD a week from Stage 1 (the bake-off at Stage 4 is the heavy week); Sonnet builds and Opus reviews on the Max plan
for Stages 1–3 (the control: 17.5 landings a day today, 7 of them harness); the supervising manager's own use in tokens per stage — Phase 0 cost
about 370k tokens of one session's context, most of it reading. The stop rule "the manager's tokens exceed what Sonnet used" cannot be checked
until the ledger (Step 3.1) exists: another reason it is first in Stage 3.

## Disagreements resolved and the overturned rulings

The table "Rulings this overturns" in the spec has the owner's yes of 2026-11-18. Phase 0 applied each as an amendment on the surviving id
(`dev-workflows.models.by-config`, `pipeline.weekly-release`, `dev-workflows.tool.landed`'s push rule, `agent-profiles.role.manager`,
`builder-console.store.one-database`) and left the Builder README's "stdlib only" and "nothing pushes" sentences as residues for Step 1.4.
Further disagreements found and resolved are in the review § 6. One the owner should hear: **the handoff is built and almost unused** (7 rows in 17
days); Stage 4 is the first time it is measured.

## `harness.toml` drift (report only; neither file changed)

The checkout (`b56999b271`) has `[nightly]`, `required_trailers = ["Written-By: "]`, `lanes = 2`, `workers = 2`, `check_no_home_paths_in_project`.
The live copy in the builder's worktree has `lanes = 3`, `workers = 3`, a 70-entry `[loop].only`, no `[nightly]`, and `trailer_one_of` still
accepting `Directed-By: the maintainer`. Step 1.4 reconciles them; proposed rule: the live file equals the landed one or the loop says why.

## GitHub batch (approved in shape; runs after the manager's yes)

`github_batch.py plan|execute|undo` in the Phase 0 scratch folder (the manager has the path). `plan` is read-only and writes
`github_batch_undo.json` with before/after for every object; `execute` aborts if any object drifted since `plan`; `undo` restores milestones and
issue milestones (comments stay). The plan: rename #282 → `Builder` with the spec path as description; move 59 open issues to it (35 from #357,
9 from #356, 2 from #297, 2 from #283, #6345 from #347 with a deferred comment, 10 loose harness issues); move #6609 to `Next release` #333;
close #357, #356, #347, #297, #283 with a note naming the survivor. The `ui-test-harness` milestone is product and untouched.

## Worktrees and branches (inventory; a proposal, nothing removed)

Read-only, 2026-11-18: `git worktree list`, `git cherry origin/integration`, file reads of the worker clone (git refuses it: dubious ownership),
`queue.json` (read-only).

**Keep (a queued lane still has an open step, or live state):** `builder-live` (the loop's tree; lane `builder-harness`), `harness-fable`
(lane `dev-workflows`, paused), `appkit-allow` (paused, 1 open), the worker clone's `wt-agent-profiles-1.3`, `wt-segments-rest`, `wt-credit-stop`,
`wt-engine-reds`, `wt-seg-rendition`, `wt-release-notes`, `wt-runtime-matrix`, `wt-spec-cleanup`, `wt-security`, `wt-fable-role`, `wt-engine-version`,
`wt-swiftlint-zero`, `wt-sharing-pairing-dead-simple-ux`; the four `fichero-pinned/pinned-*` trees (the pinned rules copies); `dev-default` and
`release-1114` (the release trees, 11-17); the two sibling agent worktrees of this session.

**Merge (unmerged commits worth reading):** `origin/imac/activity-stage5-rest` (+6, 11-18) and `activity-stage5-rest` (+4, 11-16): the Activity
Step 1.8 work; `ux-everything` / `rescue/pro-ux-everything` (+89, 11-14): the owner's UX branch, his call; `activity-pane` / `rescue/pro-activity-pane`
(+30, 11-14); `rescue/pro-night-1114` (+12); `keep/ux2-incoming` (+10, 11-12); `backup-lane-sharing-pre-batches` (+19, 11-02); `harness-gen3-before-opus`
(+26), `-before-split` (+24), `-before-rename` (+15) and the other `harness-gen3-*` snapshots of 11-01/02 (+2 to +19 each: pre-rebase states of landed
work; read one diff to confirm they are superseded, then delete); `builder-harness-1108` / `harness-fix-1113` (+5, 11-13); `lane-qwen` (+6),
`lane-qwen2` (+3), `rescue/worker-lane-qwen*` (+2..+6): the Qwen trial's unlanded fixes; `old-lane-onboard` (+7, "wip: all fixes (to be split)");
the 16 `rescue/*` branches of 11-16 (+1..+4 each, rescued uncommitted work from three Macs): triage each, then delete.

**Delete (every commit is on `origin/integration`, cherry +0):** on origin 16 branches (`builder-autofix`, `code-org`, `fix/6661-activity-crash`,
`loop-lanes`, `perf-review`, `release-defaults`, `release-hardening`, `release/2026.10.28`, `release/2026.10.30`, `release/2026.11.17`,
`rescue/pro-review-b25`, `review-images`, `spec-agent-profiles`, `spec-perf-sweep`, `spec-ux-1113`, `spec/segment-pdf-geometry`); locally 153
branches (the `b-*`, `cand*`, `lead-*`, `m-bugs-*`, `lane/*`, `harness-batch-*`, `land-*` families of October and early November); the prunable
worktree under a scratch `bisect` folder; the nine locked `check-tree-*` temp worktrees once no gate runs.

**Scratch:** the worker account's shared folder holds **981 `check-base-*` trees, 12 GB** (625 dated 11-16, 289 11-17, 71 11-18). No running process
references any of them (the only running builder processes are the loop since 11-16 and two jcodemunch index runs stuck since 12:41 and 14:12
today). `dev-workflows.run.scratch-sweep` [PARTIAL] should have removed them: a residue on that id, and the first line of the cleanup batch.
Also 22 `wt-*` worktrees in the worker clone (6 with open steps above; the other 16 are landed lanes), and under the worktrees folder
five non-worktree folders (`archive`, `code-org`, `local-small-pi`, `prompt-review`, `qwen-cleanup-sessions`; 42 MB the largest).

**Proposed cleanup batch (for the manager's yes; a script will do it in this order, each step reversible by branch name):** (1) remove the 981
`check-base-*` trees and the two stuck index processes; (2) delete the 16 fully-merged origin branches; (3) delete the 153 fully-merged local
branches; (4) `git worktree prune` and remove the landed `wt-*` and `land-*` worktrees whose lanes have no open step; (5) the unmerged list above,
one by one, after a read. Never `builder-live`, never a worktree a queued lane uses.

## Pre-existing reds (unchanged)

`check_docs_paths` (29 unaccounted paths, the same set as on `origin/integration`); `check_spec_manual_refs` warns that
`how-fichero-is-built.md` does not exist; `check_spec_build_order_shape` warns on the DRAFT (L steps; demoted history ids).
