# Parallel Execution & Review Process

How to use single sessions, subagents, and agent teams on Fichero — and how to
keep the lead agent's context clean during the main-branch bug sweep.

## The core problem this solves

The 0.0.2 sweep slipped recurring bug patterns (see `MEMORY.md`) because there
was **no review gate on direct-to-0.0.2 commits**, and the lead agent burns
context running builds, lints, and test suites inline. Both are fixed by pushing
that work *off* the lead's context window.

**Rule of thumb:** the lead agent decides *what* to change and *why*. Building,
linting, testing, and bulk investigation are delegated. The lead reads a verdict,
not a log.

## Three execution modes

| Mode | What it is | Token cost | Use when |
|---|---|---|---|
| **Single session** | The lead does the work inline | Lowest | Sequential edits, same-file changes, work with many dependencies |
| **Subagent** | Helper spawned by the lead; reports a result back; no peer communication | Medium — result summarized into lead context | Focused task where only the *result* matters: build/lint/test, "trace why X happens", "find where Y is defined" |
| **Agent team** | Peer Claude sessions sharing a task list, messaging each other | Highest — every teammate is a full session | Work that needs *discussion*: parallel review with distinct lenses, competing-hypothesis debugging, cross-layer features with disjoint file ownership |

Agent teams are **enabled** in `~/.claude/settings.json`
(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: 1`, `teammateMode: tmux`).

## Decision guide — when to use a team vs. not

### Use an agent team

- **QA review gate** (the primary use — see below). Review-only teammates have
  no file conflicts and clear, non-overlapping lenses.
- **Competing-hypothesis debugging** — root cause genuinely unknown. Spawn 3–5
  teammates each defending a different theory, told to disprove each other.
  *Not* for bugs already diagnosed in `STATE.md` — those are sequential fixes.
- **Cross-layer features** (mostly 0.0.3+) — one teammate owns backend, one owns
  SwiftUI, one owns tests. Only works when file ownership is genuinely disjoint.

### Do NOT use an agent team

- **The backend fix cluster** — fixes overlap in the same files
  (`extract_all.py`, `extractors.py`, `runner.py`). Parallel teammates overwrite
  each other. Single session; use subagents only for the read-only investigation.
- **The SwiftUI bug cluster** — one Xcode, one DerivedData, one `⌘R`. Teammates
  serialize on the same build anyway. Single session.
- **Routine sequential work** — coordination overhead exceeds the benefit.

### Default tooling by task type

| Task | Tool | Why |
|---|---|---|
| Build / lint / test a change | **subagent** (`test-runner`) | report-back task; keeps lead context clean |
| Investigate a bug / trace a path | **subagent** (`Explore`, `feature-dev:code-explorer`) | result-only, no coordination cost |
| Review a finished sweep before commit | **agent team** (3 reviewers) | independent lenses, the QA gate |
| backend fix sweep | **single session** + investigation subagents | overlapping files kill team parallelism |
| SwiftUI fixes | **single session** | serialized on one Xcode |
| 0.0.3+ cross-layer feature | **agent team** (backend / swift / test) | disjoint file ownership = real parallelism |

## QA review gate (issue #1061)

Before committing a sweep of bug fixes to `main`, run a review team instead of
self-certifying. This is the safest place to use agent teams and the fix for the
"no review gate" gap.

1. Finish the fixes in a single session. Stage but **do not commit**.
2. Spawn a 3-teammate review team, review-only, each with a distinct lens
   (copy-paste spawn prompts in `docs/agent-workflow/templates/qa-reviewers.md`):
   - `backend-reviewer` — correctness, the recurring bug patterns in `MEMORY.md`
     (fixed-one-surface-missed-sibling, view-caches-stale-snapshot,
     invalid-config-saved-or-silent-failure), Pydantic field-declaration rule.
   - `silent-failure-hunter` — catch blocks, fallbacks, "success" returned on
     systemic failure (the #1060/#1029 class of bug).
   - `code-reviewer` — style, conventions, `docs/architecture/` standards.
3. Each teammate reviews the staged diff and reports findings with severity.
4. The lead synthesizes, applies fixes, then commits.

Give teammates the diff scope explicitly in the spawn prompt — they don't inherit
the lead's conversation history.

## Context hygiene — offload build/lint/test

The lead should **not** run the three-leg check inline. Delegate it:

- Spawn a `test-runner` subagent with the exact commands from
  `docs/CLAUDE.md` → Development Commands. It returns pass/fail + failure detail.
- For SwiftUI: a subagent runs `swiftlint` + Xcode build + `RunAllTests` and
  reports the verdict. (The 3-leg check itself is still mandatory — see
  `MEMORY.md`; only *who runs it* changes.)
- The lead acts on the verdict. A green run costs the lead ~one line of context
  instead of a full log.

## Autonomous loops

For unattended runs (`/session-start-auto`, `/loop`), the same rules apply, plus:

- **Always** run the QA review gate before an autonomous commit — there's no
  human gate, so the review team *is* the gate.
- Investigation and verification go to subagents so the loop's context doesn't
  fill mid-run.
- One milestone at a time; never start N+2 work in an N+1 loop (two-ahead rule).

## Best practices

- **3–5 teammates max.** Three focused teammates beat five scattered ones.
- **Disjoint files per teammate.** Two teammates editing one file = overwrites.
- **Spawn prompts carry full context.** Teammates load `CLAUDE.md` but not the
  lead's history — include file paths, the diff scope, severity expectations.
- **Start with review, not implementation.** Review teams have clear boundaries
  and no merge conflicts — the right way to learn the workflow.
- **The lead synthesizes.** Don't let teammates' raw findings land unfiltered;
  the lead reads, judges, and applies.
- **Clean up.** The lead runs team cleanup after shutting down teammates.

## Test-infrastructure pipeline

The lane contract is fixed:

- IMPLEMENT
- CODE REVIEW (different model, programmatic via `/code-review`)
- FIX
- TEST-EXPAND
- TEST-SANITY
- MANAGER GATE

Execution rules:

- Backend pytest runs on every integration:
  `PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived`
- Swift/UI/CLI tests are written by the test-writer lane in two passes (author
  pass and independent adversarial pass).
- Manager verifies Swift/UI by compile/build in deliberate batches.
- Never run `xcodebuild test` or `verify_all --full` on Daniel’s machine (GUI/window side effects).
