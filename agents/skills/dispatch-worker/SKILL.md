---
name: dispatch-worker
description: Manager spawns a coding worker the RIGHT way — external worktree (never .claude/worktrees), correct CLI (codex for backend, claude -p for frontend), cheap-model-by-default, then verify-on-integration. Use after /choose-next has picked a batch.
---

# /dispatch-worker

Spawn one worker for a chosen batch, then integrate it. The rules here are
load-bearing — getting them wrong caused real incidents (uvicorn reload-storm
from in-repo worktrees; false-green incremental builds; stale-tree pytest).

## HARD rules
- **Worktrees live ONLY under `~/code/fichero-worktrees/<name>`** — a single isolated
  parent dir, NEVER bare siblings `~/code/fichero-<name>`. NEVER the Agent tool's
  `isolation: worktree` (lands in `.claude/worktrees/` inside the repo, which
  `uvicorn --reload` watches). Create: `git worktree add ~/code/fichero-worktrees/<name> -b <branch> main`.
- **DELETION SAFETY (2026-06-09 — I rm-deleted the separate `fichero-search` project):**
  remove worktrees with `git worktree remove --force <path>` ONLY (touches only registered
  worktrees). **NEVER `rm -rf` a `~/code/` path, and NEVER glob-delete `~/code/fichero-*`** —
  bare siblings like `fichero-search`, `fichero-search-issue-*` are SEPARATE projects with
  their own remotes + uncommitted work. Before any destructive fs op: confirm the path is under
  `~/code/fichero-worktrees/` AND in `git worktree list`; else stop and surface it. To clear a
  stale bare-sibling, `mv` it aside for Daniel — don't recursive-delete.
- **Cheap model by default:** Sonnet (frontend) / codex 5.4-mini (backend).
  Opus / codex 5.5 only for keystones.
- **Workers NEVER run pytest. The MANAGER runs the backend test suite — serially, one at a time.**
  Backend pytest loads the embedding model + heavy deps (~2–9 GB RAM each); 3 workers
  running pytest in parallel background terminals once pegged the machine at ~15 GB
  (2026-06-10). Workers WRITE tests and may run **swiftlint** (cheap) and
  `python3 scripts/check_*` guards (cheap, stdlib) — but must NOT invoke `pytest`,
  `uvicorn`, the CLI, or any heavy/background subprocess. The dispatch brief MUST say:
  *"Do NOT run pytest or any background test process — the manager runs tests. Write the
  tests, commit, and report."* See [[workers-write-tests-manager-runs-them]].
- jcodemunch index is stale → tell the worker to verify-by-reading-disk.
- **PARTITION BY FILE-SET before fanning out (2026-06-09 lesson).** Parallel is only
  free when lanes touch DISJOINT files. Two backend lanes that both rewrote
  `documents.py`/`storage.py` (#1917 profiling + #1957 doc-notfound) cherry-pick-
  conflicted and cost manager Opus tokens to hand-merge; a tooling-only lane merged
  clean. So: **before launching ≥2 lanes, predict each batch's likely file-set** (use
  jcodemunch `get_blast_radius`/`find_importers` on the god-nodes the issues touch). If
  two batches clearly share a file, MERGE them into ONE worker's 2-issue batch (it keeps
  them coherent in its own context) rather than two lanes you must reconcile. Fan out
  ACROSS naturally-disjoint layers (SwiftUI / backend-routes / backend-storage / tooling /
  scripts); serialize same-file lanes so the second rebases on the first.

## 1. Create the external worktree
```bash
git worktree add ~/code/fichero-worktrees/<name> -b <branch> main
```

## 2. Launch via tmux + send-keys (NOT `codex exec` — it hangs headless)

`codex exec --full-auto` is flaky non-interactively (stdin hang: "Reading additional
input from stdin…"; or drops to interactive if the prompt arg is empty). The reliable,
persistent, watchable pattern is an interactive codex in a named tmux window:
```bash
tmux new-window -t fichero-workers -n <name> -c ~/code/fichero-worktrees/<name> "codex -m gpt-5.4-mini"
sleep 2
tmux send-keys -t fichero-workers:<name> "$(cat /tmp/<name>.txt)" Enter   # the Enter IS what runs it
```
Next batch → `tmux send-keys` to the SAME window (keeps context). Detect done by polling
the worktree for a new commit and/or `tmux capture-pane`. Frontend = `claude` interactive
the same way. **NEVER `pkill -f codex`** — kills Daniel's own windows; stop a lane with
`tmux kill-window -t fichero-workers:<name>`.

**TRAP — codex "Update available!" prompt eats the task (2026-06-09, stalled a keystone lane).**
A fresh `codex` window sometimes opens on `✨ Update available! … 1. Update now 2. Skip 3. Skip
until next version / Press enter to continue` INSTEAD of the prompt box. If you `send-keys` the
task into that, codex runs the menu, not your task — the lane produces nothing. ALWAYS
`tmux capture-pane` right after launch (before sending the brief); if you see the update prompt,
`tmux send-keys -t fichero-workers:<name> "3" Enter` (skip-until-next-version) first, wait for the
prompt box, THEN send the brief. Belt-and-suspenders: launch with the update check disabled if the
codex version supports it (e.g. an env flag / `--no-update-check`), else always do the capture-pane check.
The brief MUST tell the worker to: mirror the right templates, register new
.swift files with `ruby scripts/add-swift-file.rb`, swiftlint each file, COMMIT on
its branch, and report risks. Give it 1 big or 3–10 same-milestone issues.

**Ponytail in every brief (Daniel, standing rule):** the worker applies ponytail —
the simplest solution that actually works, fewest lines, *deletion over addition*.
Reach for stdlib → native platform feature → **standard SwiftUI controls** before
any custom UI (no hand-rolled control when a `List`/`Table`/`.fileImporter`/`Menu`
does it). No abstraction with one caller, no config nobody sets, no scaffolding
"for later". Mark every deliberate shortcut with a `// ponytail:` comment naming
the ceiling + upgrade path (harvestable later via `/ponytail-debt`). "Less is more."

## 3. Standard test pipeline (pipeline integration)

1. IMPLEMENT: worker writes code + AUTHOR-PASS tests (happy-path + known edges) in one run.
   - Backend: worker WRITES pytest tests but does NOT run them (RAM — manager runs the suite).
   - Swift/UI/CLI: write compile-verifiable tests; mark backend vs frontend ownership clearly.
   - Implementation and FIX loops run on `spark`.
2. CODE REVIEW: manager runs `/code-review` using **codex 5.4** (different model from the worker, programmatic reviewer), AND `/ponytail-review` (over-engineering pass — what to delete/simplify; aim for a shorter diff). Cut the dead/speculative before merge.
3. FIX: if review points out issues, return to the same worker for warm-context fixes.
4. TEST-EXPAND: manager dispatches `/test-writer` for the ADVERSARIAL PASS (error/boundary/failure modes, same files already changed).
5. TEST-SANITY: run `python3 scripts/check_test_assertions.py` from the **fichero** repo root.
6. MANAGER GATE: merge only after the manager can confirm backend pytest and Swift compile-verify expectations are met.

Swift and CLI tests are compile-verify-only; full test execution is intentionally batched/deliberate and should never be in default per-feature loop.

## 4. Integrate on completion (manager)
```bash
# codex can't write the shared .git lock — commit from the manager shell if needed:
git -C ~/code/fichero-worktrees/<name> add -A
git -C ~/code/fichero-worktrees/<name> commit -m "<msg>"   # only if worker left it uncommitted
CX=$(git -C ~/code/fichero-worktrees/<name> rev-parse HEAD)
git cherry-pick "$CX"      # resolve conflicts keeping BOTH intents
```
- **Build-verify** Swift via Xcode MCP `BuildProject` (a full build — incremental
  greens can mask cross-file errors). Run targeted `pytest` for Python **serially (one
  pytest process at a time)** — never several at once (each loads the embedding model,
  ~2–9 GB).
- If green: `git push`, `git worktree remove --force ~/code/fichero-worktrees/<name>`,
  `git branch -D <branch>`, close the issues with the verifying sha.
- If red: fix the small stuff yourself or send the worker back; never push red.

## 4. Never run `xcodebuild test` / `verify_all.sh --full` on Daniel's machine in
parallel — it spawns GUI windows + the engine. Manager-only, serial.
