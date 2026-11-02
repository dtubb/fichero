# Fichero Builder — the harness map

Plain Python 3.12 on the standard library; imports nothing from the engine (`tests/test_no_engine_import.py`). Spec:
`docs/contributor_manual/specs/harness/dev-workflows.md` (the verbs) and `harness/issues-and-labels.md` (what they read
and write on GitHub). Run it as `python -m fichero_builder <verb>` from `fichero-builder` with `PYTHONPATH=.`; the rules
file is `harness.toml` in the repo root (or the pinned copy).

## Two users, one boundary

The owner runs the verbs; workers and the ladder run as a second macOS user (`[jail]`) over a scratch tree they own.
The owner cannot read the worker's session files, the worker cannot write the owner's journal: `builder work` is the one
place the chain crosses (`as_worker`), and land trusts the owner's check row because a worker could forge its own. A
pinned copy of the rules (`pinned-<sha7>`, made by `builder landed`) judges every check, never the worker's tree.

## Modules

| Module | Owns | Public | Tests |
|---|---|---|---|
| `check_tool.py` | the ladder: pinned checks, ready, diff bound, red-on-base, pytest rungs, guards, contract | `load`, `run_ladder`, `pytest_rung`, `red_on_base`, `ladder` | `fichero-server/tests/unit/workflows/test_check_tool.py` |
| `land_tool.py` | the land gate: a READY verdict keyed to the exact range, the public/private boundary | `gate`, `unreviewed`, `write_verdict`, `risky_paths` | `test_land_tool.py` (server) |
| `jail.py`, `start_tool.py`, `policy_hook.py` | the second user, the start path, the refused-actions hook | `load`, `prepare`, `trust_folder` | `test_start_tool.py` (server), `test_pi_policy_extension.py` |
| `session.py`, `watcher.py`, `budget.py` | what a session file says; caps, prices, decisions; machine memory | `read`, `assess`, `cost_of`, `refusals` | `test_session.py`, `test_watcher.py`, `test_budget.py` |
| `run.py` | one worker: start, watch, nudge, handoff + successor, the DONE end; `--feed` keeps the session across steps | `run`, `Procs`, `with_done_line` | `test_dry_run.py`, `test_main.py` |
| `pi_rpc.py` | the Pi worker kind over RPC | `Pi` | `test_pi_rpc.py`, `test_pi_live_helpers.py` |
| `brief_tool.py` | an issue + trusted comments + where the code is, as a brief; cluster briefs with the rules | `fetch_issue`, `build`, `cluster`, `localise` | `test_brief_tool.py` (server) |
| `spec_tool.py`, `steps.py` | the spec-writer brief; build-order steps as issues under the spec's milestone | `run`, `ensure_labels` | `test_spec_verb.py`, `test_steps_verb.py`, `test_steps_name.py` |
| `milestone.py` | a milestone's issues placed under steps, one brief per step, waits and the step's map | `build_order`, `plan`, `write_briefs`, `where_map` | `test_milestone_verb.py` |
| `work.py` | run → rebase → patches → fetch → check → review → land gate as one process; the `ladder` lock | `main`, `after_run`, `run_cmd`, `do_*`, `ensure_pinned` | `test_work_verb.py` |
| `landed.py` | after a verdict: push (`--push` only), refresh, pin, jail root, scratch, issues, spec [OK] | `main`, `update_issues`, `mark_specs_ok` | `test_landed_verb.py` |
| `queue.py` | one long-running worker per lane, fed step by step: check, review, land, next brief into the same session | `add`, `run`, `tick_lane`, `Procs` | `test_queue_verb.py` |
| `triage.py` | GitHub metadata by the rulings: labels, needs-spec, milestones, assignees, the build-order file | `Triage`, `first_open`, `build_order` | `test_triage_verb.py` |
| `watch.py` | the live page: runs, checks, lands, the queue | `render`, `server` | `test_watch.py` |
| `codemap.py` | jcodemunch where the jail worker can run it; the search behind a step's Where list | `provide`, `mcp_config`, `index_prefix`, `search` | `test_codemap.py` |
| `journal.py`, `models.py` | the append-only JSONL journal and its locks; one model per role | `append`, `read`, `Lock`, `for_role` | `test_journal.py`, `test_model_config.py` |

## The chain as verbs

`steps` (issues from a spec) → `milestone [--enqueue]` (briefs per step, one lane) → `queue run` (one session per lane:
`run --feed` as the worker; per step `work.after_run` then `landed`) → `watch`. `work` and `run` stay the one-brief path. `triage` keeps GitHub current; `landed` is the only closer of
issues. `scripts/harness_land.py` stays the hand-run ladder path.

## Journal rows (event → meaning)

`worker` a generation started · `cost` a generation ended (end: done, done-unsaid, lane-done, handoff, parked, gone) · `step` a lane's step ended (seq, sha, moved) · `watch` a
decision (nudge, park, alert, handoff, false done) · `work` one chain step · `check` a ladder result · `landed` one
landing step (verdict … issues, specs, done) · `queue` a transition · `triage` one metadata change (dry rows marked) ·
`steps` / `spec` a filed issue or brief.

## What reviewers hold the harness to

- A refusal is a `QUESTION:` line or a `REFUSED` row, never a traceback.
- No worker-chosen name reaches git as the owner (branches are `work-<name>`, `pinned-<sha7>`, `step-N.M`).
- Every `gh` call in a test goes to a fake; a real run of triage's write path is the owner's call, never a test's.
- A reverted or weakened test goes red on base; a pinned file (`conftest.py`, `ruff.toml`, `check_*.py`) needs a maintainer batch.
- Nothing pushes except `builder landed --push`, typed by a person.

## Running the tests

From `fichero-builder`, one pytest at a time, each with its own `--basetemp` and a scratch `GIT_CONFIG_GLOBAL`:

```
PYTHONPATH=. GIT_CONFIG_GLOBAL=/path/scratch/gitconfig-none python -m pytest tests -q -p no:cacheprovider --basetemp=/path/scratch/bt-1
```

The server-side harness tests run from `fichero-server` with `PYTHONPATH=src:../fichero-builder`.
