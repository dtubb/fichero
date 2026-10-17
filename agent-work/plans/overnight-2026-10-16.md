# Overnight plan, 2026-10-16 (orchestrator = the interactive session; workers = subagents on anthropic/claude-sonnet-5-5)

## Rules for the night
- One worker at a time, in this worktree (~/code/fichero-worktrees/integration), one issue each. No push, no tag, no DMG, no xcodebuild, no Swift edits, no pyproject.toml change, no real data (~/Fichero, ~/Fichero Projects, saved containers; read-only CLI on ~/Library/Application Support/Fichero/Projects/17402.fichero only when an issue says so).
- Every worker: spec ID first, failing test from the spec's words (red), then code (green); `PYTHONPATH=fichero-server/src`; ruff on its own diff must not add findings; pytest on the touched area only; commit as `Claude <noreply@anthropic.com>` with `Directed-By: the maintainer`, message via `git commit -F`, `Fixes #N` only when the issue is done.
- Orchestrator after each worker: read the diff, rerun its tests, run the spec guards (check_spec_behaviors_are_tagged, check_spec_broken_has_issue, check_specs_have_tests, check_capability_reference_current when a tool prompt changed), then comment on the issue with the commit.
- Checkpoint after every 3 issues: `bash scripts/verify_all.sh --fast`, plus pytest on the directories touched so far. The engine's whole unit run is killed by the memory watchdog (#4916); do not run it.
- Before each worker: `uptime` load below 20 (it was 60-245 on 2026-10-16), no pytest/xcodebuild running; else wait (background `sleep`), never stack runs.
- Between workers check for the file agent-work/STOP: if it exists, stop and write the log.
- Log every step to agent-work/status/night-2026-10-16.md (issue, worker, commit, tests, what failed). A failed or blocked issue is logged and skipped, not forced.
- Stop on: a worker hitting the Anthropic weekly limit (resets 2026-10-17 06:00 America/Moncton), a test that needs behaviour the spec does not state (record the question, skip), a gate/memory kill.
- Multilingual: it must hold for ANY language and script; nothing may assume spaces, left-to-right or an alphabet, and no language is named in code (#5728). Spanish colonial, German Kurrent, Aramaic (RTL), Chinese (vertical) are the test matrix, chosen to differ; a new script is a data file.

## Reporting
Stop and report to the maintainer after every 10 issues (or when the list ends or a stop rule fires): what is done, what to test, what failed, what you assumed. Then wait.

## Order
0. #5727 reproduce the A/B (Compare) failure on a scratch project (~/Fichero Dev Test), record the symptom on the issue, failing test, fix.
1. #5714 + #5715 reader rules: period-less readers offered not chosen; Apple Vision card (period 1900-2100, handwriting for Latin only); a stated period that misses the project's is refused and named.
2. #5720 hybrid re-ask per line; fail loudly (page's step fails, Kraken's reading stays).
3. #5721 every reader's output ties to lines (non-Kraken readers on a page with lines).
4. #5722 granularity (page, region, lines) measured by the bake-off; card field for lines per request; recipe keeps Kraken if nothing beats it.
5. #5724 segment-native review output (flag per line, never change a person's line), then #5723 profiles and lenses (data files, es-colonial, generic, de-kurrent stub, aramaic stub, zh stub), then #5725 names and places word list, then #5728 the four-script test matrix.
6. #5718 cloud models for reading and clean-up in the bake-off; #5717 remote models search (network only on request; tests stub it).
7. #5726 workflow gaps: page read by id workflow, classify_script as a step, export-pairs workflow.
8. #5729 spec guard accepts a citation of a nonexistent issue: add the check and a --self-test (small, do early).
9. #4916 shard the engine unit run so the gate fits the ceiling (infra; last, careful, `scripts/gate` self-tests).

## Lessons now part of the approach
- Test through the REAL path: the shipped preset's own prompts, not the default (the first #5719 fix missed the preset; the test now runs every shipped review node's prompt).
- Verify before you file or claim: read the data (CLI, read-only) before saying what a run did.
- A guard is tested by injecting the defect it claims to catch; one that passes on a nonexistent issue is blind (#5729).
- Harness: subagents (the `subagent` tool, background mode) are the default and need this session to stay alive; `scripts/spawn-worker.sh` makes a tmux lane that survives it, but it branches off origin/main and would miss unpushed local commits, so use it only with the worktree created from the branch HEAD sha by hand.

## Not tonight
#5716 (Swift fm-bridge image call; needs its own spec), #5711, #5713, #5645 (need the M4 or the app), the DMG (needs #4916), the decision issues (#5675, #5652, #5704, #5643, #5692, #5696), anything that pushes.

## Decisions by the maintainer (2026-10-16, no longer questions)
- Granularity limit is a card field `lines_per_request` (large cloud model: whole page; 2B local: few lines). A request never exceeds it; a longer region is split on line boundaries.
- The two best candidates and any the person named get the full set of granularities; the rest run once at their default. Cost shown first.
- Apple Vision's language correction is OFF for the bake-off's reading; confirm with one on/off measurement on a corrected page and note it on #5715.
- Tokens are available tonight (no stop at the 06:00 reset); workers are Sonnet (anthropic/claude-sonnet-5-5).

## Night 2 extension (2026-10-16 23:00): the next 30 issues, in order (engine-side, no Swift, none needs the maintainer)
A (rest of plan): 5724 rest, 5723, 5725, 5728, 5721, 5722, 5718, 5717, 5726, 5727 (only if reproducible)
B (data and recipe quality): 5447 (null answer stored as "null"), 5451 (recipe: Apple Vision text never a reader on handwriting), 5694 (names on gibberish warn), 5500 (Kraken second reading shifted), 5517 (imported segments keep direction/script; language code not name), 5516 (recipe rules period/material over averaged error), 5502 (Markdown per document), 5452 (split spread carries lines), 5521 (spaCy names step), 5637 (spaCy SVO tier), 5542 (feast days), 5572 (language detection), 5486 (corrections as readings), 5445 (kraken line crops)
C (hygiene/tests): 5630, 5674 (query ratchet), 5607 (DuckDB write conflict in fixtures), 5648 (correction prompt size), 5528 (tests depend on the machine), 4916
Gate: each worker commits; checkpoint every 3 issues; push after combined suite green (bydir-ee1d480d6 covers up to ee1d480d6 only; push that first, later commits get their own run before the DMG).
