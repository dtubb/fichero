# AGENTS.md — Operational Manual

How to work on Fichero as an AI agent. Read this at the start of every session alongside SOUL.md → MEMORY.md → STATE.md.

---

## Current Phase: Execution

**GitHub is the source of truth.** Implement and close milestone issues in priority order. Commit to `0.0.2` directly after each task — no per-task branches, no PRs.

---

## Session Startup

Run `/session-start` first. It reads SOUL.md → MEMORY.md → STATE.md and reports current state.

### What to Check

1. **Branch** — `git branch`. Should be on `0.0.2`.
2. **Uncommitted changes** — `git status`. Nothing should be left hanging.
3. **STATE.md** — Current focus, in-progress, blocked.
4. **GitHub Milestones/Issues** — Active scope, status, and priority (source of truth).

---

## Additional Guidance

- `agents/AGENTS.md` — Xcode-specific guidance (DocumentationSearch for new APIs like Liquid Glass / FoundationModels, Swift code style, validation tools like `XcodeRefreshCodeIssuesInFile`). Read this when doing any SwiftUI work.

---

## Skills Available

Run skills with `/skill-name`.

### Project Skills

| Skill | What It Does |
|---|---|
| `/session-start` | Load memory, check git, report state |
| `/session-end` | Write session log, update STATE.md, commit |
| `/build-and-test` | Full quality cycle: build + test + lint (Swift AND Python) |
| `/feature-audit` | Audit features — what works, broken, tested, untested |
| `/feature-flags` | List and manage feature flags |
| `/assign-task` | Pick up an issue from GitHub |
| `/milestone-check` | Check progress against current milestone |

### Global Skills

| Skill | What It Does |
|---|---|
| `/blocked` | List everything blocked and what's needed |
| `/scope-check` | Check if current work is in scope |
| `/handoff` | Write handoff notes for next session |
| `/retrospective` | Post-milestone retrospective |
| `/changelog` | Generate changelog from git log |

---

## Agent Team — Delegate to Preserve Context

The main session context fills up fast when reading large files, running test suites, or trawling git history. Delegate these kinds of work to specialized subagents via the `Agent` tool (subagent_type=…). The subagent reads what it needs in its own context, returns a concise summary, and the main session stays lean.

### When to delegate vs. do-it-yourself

**Do it yourself (main session):**
- Small targeted edits where you already know the file/line.
- Decisions that require the whole conversation's context (user intent, trade-offs, previous corrections).
- Short commands (`git status`, `gh issue view 588`).

**Delegate to a subagent:**
- Any task that produces large intermediate output (test logs, search results, build logs) you only need a summary of.
- Any task where the *goal* is clear but the *path* requires exploring the codebase (subagents burn their own context on the search).
- Independent parallel work — spawn multiple subagents in one message so they run concurrently.

### Role → Agent mapping

| Role | Agent(s) | When |
|---|---|---|
| **Planning / architecture** | `Plan`, `feature-dev:code-architect` | Non-trivial features, multi-file changes, anything needing a blueprint before code |
| **Exploring the codebase** | `Explore`, `feature-dev:code-explorer` | "How does X work?", tracing execution paths, mapping architecture — cheaper than grepping from main session |
| **Writing feature code** | `general-purpose` or main session | Well-scoped features with a clear plan; main session when the work is small or highly interactive |
| **Testing** | `test-runner` | Running the Xcode unit tests or Python pytest; returns pass/fail summary without flooding main-session context |
| **Linting** | `test-runner` (or inline `Bash`) | `swiftlint lint …` and `ruff check …` — delegate when output is likely to be long |
| **Building** | `test-runner` (or `mcp__xcode__BuildProject` directly) | `xcodebuild` or `BuildProject`; delegate when the build log is likely to have many warnings |
| **Code review / QA** | `code-reviewer`, `feature-dev:code-reviewer`, `pr-review-toolkit:code-reviewer`, `superpowers:code-reviewer` | Before marking work complete — independent second read; flags correctness, style, security, silent failures |
| **Second opinion on a plan** | `critic` | After writing a plan but before coding — looks for gaps, unstated assumptions, missing edge cases |
| **Library / API research** | `researcher`, `context7` MCP | Third-party library docs, Apple API details; returns summarized findings, not raw docs |
| **Guarded alignment check** | `guardian` | Before pushing a branch — compares diff against SOUL/CONSTITUTION/MEMORY |

### Typical feature loop (delegation pattern)

1. `Plan` or `feature-dev:code-architect` → produces implementation blueprint.
2. `critic` (optional) → reviews the plan, flags issues.
3. Main session (or `general-purpose`) → writes the code.
4. `test-runner` → build + Xcode unit tests + SwiftLint (or pytest + ruff on the Python side).
5. Peekaboo (main session) → visual check of the running app for UI changes.
6. `code-reviewer` → independent QA pass before commit.
7. Main session → commit + push.

### Parallelization

If tasks are independent, spawn subagents **in a single message with multiple Agent tool uses** so they run concurrently. Example: kick off `test-runner` for the Swift test suite and a separate `test-runner` for Python tests at the same time, rather than serially.

### Anti-patterns

- **Don't delegate understanding.** Never write "based on your findings, fix the bug" — that pushes synthesis onto the subagent. The subagent should return facts/summaries; the main session decides.
- **Don't duplicate work.** If you've delegated research, don't also grep from the main session — trust the summary.
- **Don't over-delegate trivial tasks.** A one-line bash command or a targeted file read is cheaper done inline than through a subagent.

---

## Build Commands — Both Stacks

**Python backend:**
```bash
# Start backend
PYTHONPATH=fichero-engine/src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Run tests
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ \
  --ignore=fichero-engine/tests/unit/_archived

# Lint
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/
PYTHONPATH=fichero-engine/src .venv/bin/ruff format fichero-engine/src/
```

**Swift frontend — the three-leg check is MANDATORY. Run ALL three, every time, in this order. Skipping any leg is a hard-rule violation (see Hard Rule #4). "Build passed" is not evidence of "done" without a test run; "tests passed" is not evidence of "done" without SwiftLint clean.**

```bash
# 1. SwiftLint (must pass — zero warnings/errors before anything else)
swiftlint lint fichero/fichero/

# 2. Xcode build
xcodebuild -project fichero/fichero.xcodeproj \
  -scheme fichero -configuration Debug -sdk macosx build

# 3. Xcode unit tests (FicheroTests, 220 tests as of 0.0.2) — REQUIRED, not optional
xcodebuild -project fichero/fichero.xcodeproj \
  -scheme fichero -configuration Debug -sdk macosx test
```

When the Xcode MCP is available, prefer these (faster, no Xcode.app build-db lock) — same mandatory order:
1. `mcp__xcode__BuildProject` — build the project
2. `mcp__xcode__RunAllTests` — run the full FicheroTests suite (never skip; if the suite is slow use `RunSomeTests` for iteration, but `RunAllTests` must pass before commit)
3. `mcp__xcode__GetBuildLog` / `XcodeListNavigatorIssues` — only on failure, to diagnose errors/warnings

SwiftLint still runs from the shell (`swiftlint lint fichero/fichero/`) — the Xcode MCP does not substitute for it.

**Xcode.app build-db lock workaround** — if the CLI fails with "database is locked" while Xcode.app is open (see MEMORY.md):
```bash
xcodebuild ... -IDEBuildOperationQueueDisableLogging=YES \
  -derivedDataPath /tmp/fichero-test-dd clean build test
```

### Test-as-You-Go — Stop UI Regressions at the Source

Every feature or bug fix that touches SwiftUI **must land with unit test coverage added or updated in the same commit**. This is the single most effective defense against the UI-regression cycle we've been in (same bug class reappearing across releases). "Tests in a follow-up issue" is how regressions happen.

**What to test, by change type:**

| Change type | Required tests |
|---|---|
| Bug fix (UI) | Add a failing test that reproduces the bug *first*, confirm it fails, then fix. Test must live alongside the fix. |
| New SwiftUI view | Model/view-model tests for all state transitions and decision logic. If the view owns logic (not just layout), it needs tests. |
| New gesture / drop handler | Test the decision function directly (what accept/reject/highlight state does this input produce?). Don't test SwiftUI's rendering — test the logic that drives it. |
| Sidebar / filter / selection logic | Unit test the predicate/builder. `SidebarItemBuilder` and `buildLibraryHierarchy` must have test coverage for every new case. |
| Refactor | All existing tests continue to pass. If behavior changes intentionally, update tests in the same commit. |

**What goes in a unit test vs. a visual check:**

- **Unit test (XCTest/Testing framework, fast, committed)** — state logic, filters, builders, decoders, URL handling, drop-decision logic, predicate evaluation, ID parsing. Anything expressible as "input → expected output" or "before state + action → after state."
- **Visual check (peekaboo, manual, not committed as a test)** — rendered pixels, highlight colors, drag-preview images, layout overflow, font rendering. These fail the "input → output" shape, so don't force them into XCTest.

**Rule of thumb:** if a bug recurs because it wasn't caught by a test, the test was missing. Add it now. See MEMORY.md for the bug classes we keep hitting (NSItemProvider vs. Transferable, SidebarItem ID parsing, `.onInsert(of:)` crash, etc.) — each of these should have regression tests pinned to it.

**Writing the test:**
1. Find the existing test target (`FicheroTests` — 220 tests as of 0.0.2).
2. Put the test next to its peers: `ActivityItemTests.swift` style, colocated by domain.
3. Use Swift Testing framework (`@Test`, `#expect`) for new tests — it's what the rest of the suite uses.
4. Reference the issue in the test name: `@Test("#571 sidebar drop highlight stays during folder drop")`.
5. Run `RunAllTests` and confirm the new test appears in the pass list.
6. **Commit the test in the same commit as the fix/feature** — not separately.

### Visual Verification with Peekaboo

Unit tests catch logic regressions but not UI regressions. After a SwiftUI change, run the built Fichero and screenshot it to verify the actual rendered UI. Peekaboo MCP (`mcp__peekaboo__*`) is the third verification leg *for app behavior*, not for Xcode itself.

| Tool | Use |
|---|---|
| `mcp__peekaboo__list` with `app: "Fichero"` | Find Fichero's windows once running |
| `mcp__peekaboo__image` | Screenshot to `/tmp/*.png` with `capture_focus: "background"` so focus stays in iTerm2 |
| `mcp__peekaboo__see` | Screenshot + element map (`B1`, `T1`…) for follow-up clicks/typing |
| `mcp__peekaboo__click` / `type` / `hotkey` / `drag` | Drive Fichero to a specific state before capture |

**Ground-truth rule:** after peekaboo writes a PNG, use `Read` on the file path — Claude Code displays images directly into context, which is more reliable than peekaboo's inline vision-model description (the AI caption can hallucinate). Use the inline `question:` parameter only for bulk/headless triage.

**Gotchas:**
- `path` is a *prefix* — one PNG per window, suffixed with title/index. Target a specific window (`PID:…`) or use `frontmost` to get one file.
- Use the built product (Xcode → Product → Build, then launch the binary), not Xcode's Run — otherwise peekaboo captures the Xcode debug chrome.

**Use for these 0.0.2 bugs specifically** (issues that are visual-only and hard to test with XCTest):
- `#571` sidebar drop highlight — drag a folder onto the sidebar, screenshot the blue outline.
- `#588` PDF pinch-zoom audit — open a doc, screenshot PDFView at varying zooms.
- `#556` settings `.formStyle(.grouped)` — open Settings, screenshot each tab.
- PDF ↔ grid selection sync (commit `413b6614`) — select a page, screenshot, confirm thumbnail highlights match.

**CRITICAL:** `PYTHONPATH=fichero-engine/src` must be set for ALL Python commands.

**Generated files (NEVER edit manually):**
- `*Generated.swift`
- `openapi.json`
- Swift api-client package
- Regenerate via `scripts/sync_openapi_schema.sh`

---

## Per-Commit Gates

Every commit must pass these gates before push. They are MANDATORY, not advisory.

| Gate | When | Tool |
|---|---|---|
| **pytest** | Always (any backend touch) | `pytest fichero-engine/tests/unit/` |
| **ruff** | Always (any backend touch) | `ruff check fichero-engine/src/` |
| **SwiftLint + xcodebuild build + xcodebuild test** | Any SwiftUI touch | three-leg check above |
| **`code-reviewer` subagent** | Always | independent QA pass on the staged diff |
| **`silent-failure-hunter` subagent** | When the diff touches error handling, fallback chains, optional inputs, or anywhere a failure could be swallowed | dedicated hunt for caught-and-ignored exceptions, unchecked Optionals, defaults that hide drift |
| **Security review** | When the diff touches auth, file I/O, network calls, secrets, keychain | `/security-review` |

If any gate fails, fix and re-stage — do NOT amend a previous commit; create a new one.

## Manager Pattern

The lead session is a **manager**, not an editor. The manager's job is to preserve orchestration context (user intent, prior corrections, the plan) and delegate targeted edits to subagents.

- Lead reads the plan, dispatches edits to subagents, reviews returned diffs, decides what to commit.
- Subagents read what they need into their own context, return a concise diff or summary.
- The lead never burns context on test logs, build output, or large file reads — those go to subagents.
- Spawn parallel subagents in a single message when work is independent (e.g. backend reviewer + silent-failure hunter + code reviewer for the QA review gate).

See `docs/agent-workflow/parallel-execution.md` for the full pattern.

## Autonomous Loop

The pattern Daniel uses to run Claude unattended:

1. **tmux** session on the dev machine (a bare SSH shell hits "Not logged in" — see MEMORY.md).
2. **`agent-autonomous-loop.py`** drives a `claude` CLI loop.
3. **ScheduleWakeup** reschedules the loop on a cadence.
4. **BLOCK.md** is the human-in-the-loop gate — the loop checks it each cycle and halts if there is anything for Daniel to decide.

Workflow execution runs on a worker thread (post-#1000); per-thread `db_manager` and `DBWriter` are required.

## CLI as Verification Surface

The typed `fichero` CLI (`fichero-engine/src/fichero/cli/`; ships inside the engine package, invoked via `python -m fichero`) mirrors the engine's HTTP surface. Use it as the engine-quality comparison loop:

- Every endpoint reachable from the SwiftUI app should be reachable from the CLI.
- Endpoint parity (CLI ↔ SwiftUI) is a per-session check item.
- When investigating "is this an engine bug or a SwiftUI rendering bug?", reproduce against the CLI first. If the CLI fails the same way, the engine owns the bug.

## Commit and Branch Discipline

All work happens on `0.0.2`. Do NOT create per-task worktrees or feature branches.

After each task:
1. Run build + test + lint (evidence before claiming complete)
2. Commit with conventional format referencing the GitHub issue
3. Push to `origin/0.0.2`

```
feat: add semantic search to document inspector (#42)
fix: correct PYTHONPATH in uvicorn startup (#38)
chore: regenerate OpenAPI client after endpoint changes
refactor: extract DocumentStore from LibraryView (#55)
test: add pytest coverage for ingestion pipeline
docs: update architecture-summary.md with LanceDB schema
```

One concern per commit. Don't mix feat + fix.

---

## Decision-Making

### When to Proceed vs. Plan

**Proceed without planning:**
- Bug fixes with clear root cause and test coverage
- Adding tests for existing behavior
- Lint/build fixes
- Documentation updates

**Enter plan mode first:**
- Architectural changes to either stack
- Changes to the OpenAPI schema (frontend + backend must stay in sync)
- Feature flag tier changes
- Anything touching the database schema

### Two-Stack Rule

Every significant change touches both stacks or touches neither. Before completing any backend route change:
1. Does the OpenAPI schema need updating?
2. Do the Swift generated files need regenerating?
3. Do frontend callers need updating?

If you change the backend API without regenerating the Swift client, the build breaks.

### Pydantic + OpenAPI Discipline

Two failure modes have bitten us repeatedly. Both fail *silently* — no exception, no test failure, just data that vanishes or filters that hide rows. Treat these as load-bearing rules, not style nits.

**1. Declare every field on the Pydantic model.** `extra="allow"` lets unknown fields *write* to the DB at runtime, but `model_dump()` only serializes declared fields, so the next read drops them. Symptom: write succeeds, value silently disappears on next load. Fix: when adding a column, add (a) the DB migration, (b) the Pydantic model field, (c) the OpenAPI-typed field on the request/response schemas — in the same commit. See `commit 31fc4141` and `feedback_pydantic_field_must_be_declared.md`.

**2. Use OpenAPI-typed fields, not `additionalProperties`, in Swift service wrappers.** When building a request body in `fichero/fichero/Services/*Generated.swift`, every field declared in `openapi.json` must be set via the typed `Components.Schemas.*` field. Dumping declared fields into `additionalProperties` works at compile time and round-trips through `extra="allow"` on the wire, but the backend Pydantic model ignores them and the write is lost. See `docs/architecture/swiftui/api_client.md` for the contract.

**3. Endpoint defaults that match against seed data are foot-guns.** When you set a query-param default that is then matched by strict equality against rows (e.g. `folder_path: str = "/"`), the route quietly stops returning data the moment the seed JSONs change shape. Same failure shape as #1: schema and data drift apart, no error fires. Default to `Optional[T] = None` and only filter when the caller passes a value. Add a regression test that seeds a row outside the old default and asserts the unfiltered list returns it. See #722 → #723 (`commit 968602e7`).

**Whenever you change seed data shape (default JSON resources, migration defaults, fixture data), audit every endpoint that filters that field.** The shape change and the filter change must ship together.

---

## Memory Management

- **STATE.md** — Current focus, in-progress, blocked, next session entry point
- **MEMORY.md** — Durable lessons/decisions (not project status)
- **memory/YYYY-MM-DD.md** — Session log (detailed notes)

GitHub Issues + Milestones are authoritative for scope and status.

---

## Hard Rules

1. Never push to `main` — all work goes to `0.0.2`
2. Never deploy or publish without permission
3. Never edit generated files (`*Generated.swift`, `openapi.json`, api-client)
4. **Three-leg Swift check is mandatory** — for any SwiftUI change, run ALL three before marking work complete, in this exact order: (1) `swiftlint lint fichero-swiftui/fichero-swiftui/`, (2) Xcode build (`xcodebuild … build` or `mcp__xcode__BuildProject`), (3) Xcode unit tests (`xcodebuild … test` or `mcp__xcode__RunAllTests`). None of these are optional. "Build passed" alone is not evidence of done. Python work requires the equivalent two-leg check (ruff + pytest). Add peekaboo visual verification for any SwiftUI change that has a rendered UI surface.
5. **Every SwiftUI bug fix or feature must land with new/updated unit tests in the same commit** — no "tests in a follow-up." This is how we stop UI regressions from recurring.
6. Never start coding on unapproved scope (GitHub milestone/issues are the approval boundary)
7. `PYTHONPATH=fichero-engine/src` on all Python commands
8. One concern per commit, conventional commit format
9. `trash` over `rm`
