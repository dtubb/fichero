# AGENTS.md: Operational Manual

The single canonical agent/operational doc for Fichero. Every coding agent —
Codex, Claude Code, and Claude-in-Xcode — reads this file. (`CLAUDE.md` is a thin
pointer here.) The product north-star is `CONSTITUTION.md`; the detailed
architecture/development guide is `AGENTS.md`; the session-start / manager
skills under `agents/skills/` tell each lane its job.

Every agent starts with `/session-start` (or a lane variant: `-manager`, `-worker`, `-integrator`, `-auto`); it loads context and reports state. Work happens on the milestone branch this worktree is on. Commit directly, no per-task branches.

---

## Who Verifies What

- **Worker**: lints and tests **only its own diff**, then commits. Backend: `ruff check` + `pytest` on the area you touched. Swift: `swiftlint`. A worker does not compile the whole app or run the full suite.
- **Manager / integrator**: owns the Xcode build, the full `FicheroTests` run, and the cross-stack gate before anything merges (one Xcode, the backend on :8765).

Activate the virtualenv first (`source .venv/bin/activate`, see `CONTRIBUTING.md`), then
call the tools on `PATH`. Run everything from the repo root of the tree you are editing.

```bash
# Backend — PYTHONPATH=fichero-server/src on every Python command. The CLI and
# MCP products live in sibling trees (#4227); tests reach them via the conftest
# sys.path seam, but lint them explicitly:
PYTHONPATH=fichero-server/src:fichero-cli/src:fichero-mcp/src ruff check fichero-server/src/ fichero-cli/src/ fichero-mcp/src/
PYTHONPATH=fichero-server/src pytest fichero-server/tests/unit/
bash fichero-server/scripts/start_backend.sh   # server (serves HTTPS; app pins it fail-closed — never bare uvicorn/HTTP, #2538)

# Swift — lint your diff; the manager runs the build + test (prefer the Xcode MCP)
swiftlint lint fichero/fichero/
```

**Which tests the gates actually run — and what they deliberately skip.** Every
gate (`verify_python.sh`, `verify_all.sh --standard`, `build-and-validate.sh`)
covers `fichero-server/tests/unit/` plus, in `verify_all`, `tests/contracts/`.
**`fichero-server/tests/perf/` is run by NOTHING automatically** — that is
deliberate, not an oversight:

```bash
scripts/verify_perf.sh          # the perf suite, on purpose (~50 min)
```

Do NOT reach for the whole-tree `pytest fichero-server/tests` form. It silently
pulls in the perf suite and takes ~70 minutes: measured 2026-07-28, a full-tree
run was 4219s of which **two perf tests were 3089s — 73% of the entire suite**
(`test_list_entities_full_scale` 1612s, `test_list_entities_doc_scoped_scale`
1477s). Everything outside `tests/perf/` finishes in under 12s per test. Those
two are SLOW, not hung — under `-q` they print nothing for ~25 minutes each and
have been mistaken for a hang (#4039); `verify_perf.sh` streams their output so
you can see progress.

Because a perf run and an Xcode build together have pushed this machine past
the load where the OS starts killing processes, check `pgrep -f xcodebuild`
before starting either the perf suite or a whole-tree pytest run.

**Working in a git worktree?** A worktree has no `.venv` of its own. Activate the one from
your main checkout, but keep `PYTHONPATH=fichero-server/src` **relative to the worktree**
— the venv is an editable install pointing at the main checkout, so without it you lint
and test the *other* tree and get a green run that means nothing. Never write an absolute
path like `~/code/fichero/.venv` into a doc or a script; it is only true on one machine.

- **Backend API changed?** Regenerate the committed client or the Swift build breaks: `./fichero-server/scripts/sync_openapi_schema.sh` (change API → sync → commit regen).
- **Ship tests with the change.** Every SwiftUI fix or feature lands with new/updated unit tests in the same commit; write the failing test first for a bug. Test the logic (state, predicates, builders, ID parsing) rather than the rendered pixels, and eyeball pixels by running the built app.
- **Risky diff?** Anything touching auth, file I/O, network, secrets, or keychain → run `/security-review`.

**Testing manual: `docs/contributor/TESTING.md`.** The short version:
`fichero/fichero-tests/` mirrors `fichero/fichero/` — a new test goes in the
folder matching the code under test (plus `Transport/` and `Contract/`
buckets); shared specimen files live in `test-fixtures/files/`, resolved ONLY
via `tests/fixture_paths.py` (Python) or `TestFixtures.swift` (Swift); seeded
libraries come only from `seed_test_library.py`; and the coverage ratchet
(`scripts/check_coverage_ratchet.py` + `coverage-baseline.json`) fails any
run whose coverage drops — baselines move only by deliberate
`--update-baseline` commits.

---

## Worker Orchestration

Fichero is built by AI coding agents. The work runs through a
manager-with-workers loop:

- The **manager** (`session-start-manager`) holds the control lane. It does not
  write source code. It triages issues, picks the next batch, and dispatches it.
- Each **worker** runs in its OWN git worktree, in its own detached tmux session, as an
  interactive agent. A worker grinds one milestone's GitHub issues and commits as itself
  (see Commit Attribution below).

  **`scripts/spawn-worker.sh` is the canonical launcher. Use it; do not hand-roll.**

  ```bash
  scripts/spawn-worker.sh <claude|opus|sonnet|haiku|codex> "<Milestone Title>" [session-name]
  ```

  It fetches, creates the worktree off **`origin/main`** (never stale local `main`),
  opens a detached tmux session in it, activates the venv, launches the agent, and feeds
  the worker prompt scoped to that milestone. Worktrees land under
  `$FICHERO_WORKTREES` (default: a `fichero-worktrees/` beside your checkout). It prints
  the `tmux attach -t <session>` command to watch it.

  Hand-rolling `git worktree add … main` branches off whatever your local `main` happens
  to be, which is how a worker starts on stale code.
- The manager **reviews** each worker's output (ponytail lens plus `/code-review`),
  **build-gates** it, runs `verify_all`, then **merges via PR**, closes the issues,
  and **re-dispatches** the next batch. It checks in on the workers about every 15
  minutes.

Workers never push to shared branches for the manager; the manager owns the merge.
This keeps one Xcode and one full-suite run as the gate while many workers grind in
parallel, isolated worktrees.

## Git Practices — Lanes, Integration, Commits

Short-lived **lane branches** (one worker, one worktree under
`~/code/fichero-worktrees/<name>`, branched off `origin/main`) merge into an
**integration branch** when 2+ lanes must land together; the manager gates
the combined diff there (full suite, 0 failed) before fast-forwarding to
`main`. Delete a lane branch once its commits reach `main` — nothing is
lost, the commits stay reachable by SHA / `git log --grep` / the closed
issue.

**Commit, never stash.** Park interrupted work as a WIP commit on the lane
branch, not `git stash` — a stash doesn't survive a worktree teardown and is
invisible outside the shell that made it. Baseline-diffing (comparing two
tree states) happens in a **separate worktree**, never via
stash-and-checkout in the same one (see `docs/design/git-practices-fabel-review.md`
Rule "stash-pop hazard").

**Bring an agent up to speed with data, not a long-lived branch:**
`agents/ROADMAP.md` + GitHub milestones for "what's next", per-area
`*_STATUS.md` / fabel-review docs for "what's the current state",
conventional-commit scopes (`git log --grep '(#1234)'`) for "what happened
and why". A branch several agents keep rebasing onto is the failure mode
this replaces.

**Verification runs in the foreground.** Any agent whose job is "verify then
commit" (worker or otherwise) blocks on its own check and commits in the
SAME turn it sees the result. Never launch a background test + a `Monitor`
and pause — the turn ends before the result lands, and the agent loops
without ever committing.

**Path-keyed guardrails move with the file.** Any commit that moves, renames,
or splits a file must update every `scripts/check_*.py` `TARGET_FILES`-style
constant and guardrail allowlist in the SAME commit — see "A `pytest -k`
subset skips the architecture guardrails" in Common Pitfalls below; the
guardrail's own test files are part of the gate, not optional.

Full rationale and the incidents behind each rule:
`docs/design/git-practices-fabel-review.md`.

### Manager loop — use the scripts, don't improvise

The manager drives work through three scripts. **Do not hand-pick issues, hand-edit ROADMAP order, or `gh issue create` by hand** — that is how duplicate/mis-placed milestones crept in.

1. **Pick next work** — `python3 scripts/choose_next.py [--json]`. It walks the
   `## Tier` PRIORITY SPINE in `agents/ROADMAP.md` (foundations-first, milestone
   order = ascending due-date) and returns the highest-priority *ready, unclaimed*
   batch (it already skips `status:in-progress`/`blocked`, `needs:human`, assigned).
2. **Size each issue** — `python3 scripts/dispatch_advisor.py <issue#>` → `mini |
   regular | frontier` worker class.
3. **Dispatch by lane label** — `backend` → codex · `client:swiftui` → claude ·
   `docs` → codex-docs. External worktree only, **commit-only, one build at a time**
   (serialize-builds rule). `needs-design` issues are NOT for free-model workers.
4. **File any new issue** — `scripts/file_issue.sh --title ... --type ... --lane ...
   [--milestone ... | let it route]`. It validates the milestone is OPEN, rejects
   closed ones with their successor, enforces the 15 canonical labels, auto-routes
   by keywords. `--dry-run` to preview, `--self-test` to check the router.
5. **On a red test** — `python3 scripts/tests_to_issues.py <junit.xml>` files one
   tracked issue per failing test (labeled to its lane) so nothing is lost on a crash.
6. **Gate** from the **repo root** (some contract tests read source via root-relative
   paths): `bash scripts/verify_all.sh --standard|--full` — or the PYTHONPATH-forced
   backend gate on the integrate worktree. Then merge via PR, close issues, re-run
   `choose_next.py`. Do NOT hand-edit ROADMAP order / milestone `due_on` — ask the
   board organizer to re-sort.

**Lane discipline:** two workers must never own the same file — overlap = an
unmergeable collision (see the disjoint-ownership rule). Before dispatching, check
the target paths don't overlap another live lane. When a collision slips through, the
worker that *wrote* the code reconciles it; the manager does not blind-`--theirs` a
test whose semantics it can't verify.

### Workers run a self-continuing LOOP, and signal the manager

A worker is dispatched a **whole milestone**, not one issue. It **drains the
milestone in a loop**: pick next ready issue → smallest correct slice + a test →
commit-only (`Closes #n`, authored as itself) → **`bash scripts/notify_manager.sh
"done #n (<sha>); next #m"`** → repeat. It never stops-and-waits between issues;
the manager gates asynchronously. Blocked on a design wall →
`notify_manager.sh --blocked "why"` and move on.

`notify_manager.sh` appends to `~/.fichero-manager-inbox`; the manager arms a
**Monitor** on that file so a completion wakes it immediately (no timer polling).

**Every worker uses jcodemunch + ponytail.** Navigate code via the jcodemunch MCP
(`search_symbols`/`get_file_outline`/`get_symbol_source`/`find_references`/
`get_blast_radius`), reading only the file about to be edited — never grep-dumps.
Write ponytail code: shortest working diff, stdlib/native/existing-dep before new
code, no speculative abstractions, delete over add, one runnable test per
non-trivial change, `ponytail:` comments for deliberate simplifications.

**Reusable prompts:** `agents/prompts/worker-loop.md` (the standing worker
contract, with `{{LANE}}`/`{{MILESTONE}}` placeholders) and
`agents/prompts/manager-loop.md` (the manager cadence). Dispatch by pasting the
filled worker-loop template.

---

## Working in Xcode

When an agent runs **inside Xcode** (Claude-in-Xcode / the `xcode-tools` MCP server), prefer the MCP tools over command-line `ls`/`find` — every shell invocation may prompt the user for approval, so use them sparingly.

- **Build** with `BuildProject` (Xcode MCP) rather than raw `xcodebuild` — it shares Xcode.app's cache and avoids `build.db` lock contention.
- **New Apple APIs**: use `DocumentationSearch` (Xcode MCP) liberally. It runs locally, returns compact results fast, and is newer than training data. ALWAYS search for these if referenced — they post-date most training data:
  - **Liquid Glass** — the current design system.
  - **FoundationModels** — on-device ML framework with macros for structured generation.
  - **SwiftUI** keeps evolving (especially around `NSViewRepresentable`-era patterns) — don't assume the latest way of doing anything. If you can't find an implementation of something in the project, assume it's new API and search for it.
- **The three-leg Swift check** before declaring SwiftUI work done, in order: (1) `swiftlint lint fichero/fichero/` clean; (2) `BuildProject` succeeds; (3) `RunAllTests` passes. A build log alone is not done; a green test run alone is not done. `XcodeRefreshCodeIssuesInFile` gives fast per-file diagnostics for the inner loop but does NOT substitute for a full build. Use `RenderPreview` / visual capture for rendered-UI changes.
- **Limit changes to the requested task** — don't make unrelated edits.

SwiftUI code-style guidelines live in `docs/contributor/swiftui-development-standards.md`; the deeper architecture reference in `docs/contributor/architecture-overview.md`.

---

## Verification (`verify_all`)

One gate, tiered. Run from the repo root:

- `bash scripts/verify_all.sh --fast` — swiftlint + ruff + `scripts/check_*.py` guardrails + version-date + OpenAPI model sync. Cheap; workers can run it.
- `--standard` — fast + backend pytest unit tests.
- `--full` — standard + platform legs (macOS Xcode build/test + the generic iOS Simulator compile gate; `--macos` / `--ios` to select). The manager owns `--full`.

Backend pytest needs `PYTHONPATH=fichero-server/src`; write-suites need their `FICHERO_RUN_*` flag. Parse the summary — merge only on **0 failed**. The macOS/UI leg needs a live window server (screen unlocked + `caffeinate -d`); a locked screen makes XCUITest time out. The iOS leg is compile-only and device-less: `bash scripts/verify_all.sh --standard --ios` uses `-destination 'generic/platform=iOS Simulator'` and isolated generated DerivedData/output directories (named `verify-all-derived` and `ios-simulator`) under the build output area, so CI/manager gates iOS compilation without booting or naming a simulator.

## Releasing

The app ships as a notarized DMG (Sparkle/GitHub) and, separately, to TestFlight. Wrapper: `scripts/release-all.sh --help`; lane doc: `docs/contributor/release/release-lane.md`.

1. **Gate:** `verify_all.sh --full` green.
2. **Build + package the Mac DMG:** `scripts/build-release-dmg.sh` — stamps today's dated version (`YYYY.MM.DD-beta`; opt out with `FICHERO_RELEASE_VERSION`), builds the Release app with the **embedded** engine (Briefcase), re-signs inside-out with Developer ID, and styles the DMG. (Reuse an already-built app with `--skip-app-build`, but note that **skips the date re-stamp**.)
3. **Notarize + staple:** `scripts/notarize.sh build/releases/Fichero.dmg` (needs the `notarytool` keychain profile or an App Store Connect API key). Verify with `spctl -a -t exec` / `stapler validate`.
4. **iOS/iPhone/iPad → TestFlight:** archive + upload separately (build in a worktree per the iOS-build-gate rule).

The version date is stamped **at build time** — it does not auto-update when you open the DMG later.

---

## Pydantic + OpenAPI Discipline

Three failure modes that bite *silently*, with no exception and no test failure, just data that vanishes or rows that hide. Load-bearing, not style:

1. **Declare every field on the Pydantic model.** `extra="allow"` lets unknown fields write at runtime, but `model_dump()` only serializes declared fields, so the next read drops them. Add the DB column + the model field + the OpenAPI-typed schema field in the same commit. (`feedback_pydantic_field_must_be_declared.md`)
2. **Swift wrappers set OpenAPI-typed fields, not `additionalProperties`.** Declared fields dumped into `additionalProperties` round-trip on the wire, but the backend Pydantic model ignores them, so the write is lost. (`docs/contributor/architecture/fichero/api_client.md`)
3. **Endpoint defaults matched by strict equality against seed data are foot-guns.** A `folder_path: str = "/"` default silently stops returning rows the moment seed JSON shape changes. Default `Optional[T] = None`, filter only when the caller passes a value, add a regression test. (#722 → #723)

When seed-data shape changes, the shape change and every filter that reads it ship together.

---

## Two-Stack Rule

Before completing a backend route change: does OpenAPI need updating? Do the Swift generated files need regenerating? Do frontend callers need updating? Plan first for architectural, OpenAPI-schema, feature-flag-tier, or database-schema changes; proceed directly on clear-root-cause fixes, tests, and lint/build fixes.

**Engine bug or rendering bug?** The typed `fichero` CLI (`python -m fichero_cli`) mirrors every endpoint reachable from SwiftUI. Reproduce against the CLI first; if it fails the same way, the engine owns it.

---

## Architecture at a Glance

```
SwiftUI app · fichero CLI · fichero-mcp
              |
   HTTPS on 127.0.0.1:8765 (TLS, pinned fail-closed)
              |
        FastAPI engine  ──→ DuckDB (metadata) + LanceDB (vectors)
                        ──→ LangGraph (workflows)
                        ──→ LangChain (LLM providers)
```

The Swift app is a rendering layer: storage, ingest, search, workflows, the KG and
all validation live in the engine. `litellm` is metadata only — `get_model_info()`
and `cost_per_token()`. It never routes a call.

- **Route tiers.** `FICHERO_FEATURE_TIER` (`release` | `dev`, default `release`) in
  `api/main.py`. On current `main` the dev tier gates exactly one route group:
  `iiif`. Everything else is core. Route registration is therefore a poor signal of
  whether a feature is *usable* — the UI is flag-gated separately.
- **What ships to a user** is decided by `FeatureManager.resetToV001()` in
  `fichero/fichero/Models/FeatureManager.swift`, re-applied on every
  `releaseProfileVersion` bump. `docs/user/features.md` is derived from it.
- **Databases:** `~/Library/Application Support/Fichero/fichero.duckdb` and
  `.../lance/`. Never query them directly — everything goes through `db.py`.
- **Engine is macOS-only when embedded.** Briefcase declares one platform; iOS and
  iPadOS always talk to a remote engine. See `fichero-server/README.md`.

---

## MCP Tools

**The live tool list in your session is authoritative.** The repo pins nothing —
there is no `.mcp.json`. Every MCP server comes from the agent's own global or
plugin config, varies per harness (Claude Code, Codex, Claude-in-Xcode), and changes
over time. A roster here would rot; this is deliberate.

What the harness *needs*, and what to do when it is missing:

| Capability | Server | If absent |
|---|---|---|
| Code navigation | **jcodemunch** — required, see Code Navigation below | fall back to Read/Grep **and say so** |
| Xcode build / test | **xcode** MCP (`BuildProject`, `RunAllTests`) | raw `xcodebuild` + `-skipPackagePluginValidation` |
| Apple API docs | **xcode** MCP `DocumentationSearch`, or sosumi | say you could not check; do not guess new API |

`XcodeBuildMCP`'s tools mostly target iOS simulators — Fichero is macOS, so use the
macOS / device-less variants. Prefer the `xcode` MCP over raw `xcodebuild`: it shares
Xcode.app's cache and avoids `build.db` lock contention.

**Two tools are not optional.** Every worker navigates with **jcodemunch** and writes
**ponytail** code (shortest working diff; stdlib → native → existing dep → one line;
delete over add; no speculative abstraction; a `ponytail:` comment on any deliberate
simplification). Both are enforced by review, not by a script.

---

## Common Pitfalls

The ones that cost hours, and that no test catches for you:

- **A new `.swift` file is invisible until registered.** The `Fichero` target uses
  traditional PBX file references, not synchronized groups. Write the file, then
  `ruby scripts/add-swift-file.rb <path>`. Never hand-edit `project.pbxproj`.
  (Test-target files use sync'd groups and just work.)
- **`PYTHONPATH=fichero-server/src` on every Python command.** The shared `.venv` is
  editable-installed against your MAIN checkout, not this worktree; without it, a
  worktree gates the *stale* tree — a green run that means nothing.
- **Never bare `uvicorn`.** The app pins `https://127.0.0.1:8765` fail-closed. Use
  `fichero-server/scripts/start_backend.sh`.
- **Multi-library requests need the `X-Fichero-Library-Path` header** (app-wide
  endpoints — health, providers/catalog, settings — skip it).
- **A `pytest -k` subset skips the architecture guardrails.** Anything touching a
  persisted DB, a route, or a Swift service needs the full run.
- **Paths assembled from parts hide from a string sweep.** `ROOT / "docs" / "<page>.md"`
  has no `docs/<page>.md` substring to grep. Moving a file breaks it silently.
- **Backtick text inside `git commit -m "..."` is command substitution.** The shell
  executes it and pastes the output into your message. Use `git commit -F <file>`.
- **Renames/moves break path-keyed guardrails.** `PERSISTENCE_PATH`,
  `WILDCARD_BIND`, the XML chokepoint check, `db_access`,
  `single_connection`, and every `check_*.py` `TARGET_FILES` list hardcode
  paths. A move that doesn't update them in the same commit gives a false
  green (7 regressions from #3751/#3754). Grep for the old path across
  `scripts/check_*.py` before committing a rename.

---

## Code Navigation

When a code-intelligence MCP server (jcodemunch) is connected, prefer it over Read/Grep/Glob for code questions — it is an AST index with large token savings. If it is **not** connected, fall back to Read/Grep and say so. Typical routing:

| Question | tool |
|---|---|
| Where is a symbol defined? | `search_symbols` |
| What's in a file before I edit? | `get_file_outline` |
| One symbol's source | `get_symbol_source` |
| What breaks if I change X? | `get_blast_radius` |
| Who imports / references this? | `find_importers` / `find_references` |
| Repo overview / file tree | `get_repo_outline` / `get_file_tree` |
| String/comment/config search | `search_text` |

Start a session with `plan_turn { repo: ".", query: "<task>" }` for confidence + recommended files. **Top god nodes** (run `get_blast_radius` before touching): `Database`, `KnowledgeClaim`, `KnowledgeEntity`, `Document`, `LLMConfig`, `EntityType`, `DocType`, `Artifact`, `WorkflowDef`.

---

## Commit Format

Conventional commits — `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, `style:` — always referencing a GitHub issue: `feat: add tasks router (#420)`. GitHub Issues + Milestones is the source of truth for the backlog.

---

## Commit Attribution

Each agent commits as ITSELF. The author is the agent doing the work; the
committer stays the human.

- Claude writing → author `Claude <noreply@anthropic.com>`
- Codex writing → author `Codex <noreply@anthropic.com>`
- Other model → that model's name with `<noreply@anthropic.com>`

```bash
git -c user.name="Claude" -c user.email="noreply@anthropic.com" \
  commit -m "docs: fix faq models (#1234)

Directed-By: Daniel Tubb <dtubb@me.com>"
```

The git log shows which agent produced which work, and Daniel is credited as the human who directed it.

---

## Docs Placement

ONE docs folder, `docs/` (the MkDocs `docs_dir`). It is BOTH the published site AND
the reference contributors read on GitHub. It holds two guides:

- **`docs/user/`** — the User Guide: using Fichero. Entry point `docs/user/README.md`.
- **`docs/contributor/`** — the Contributor Guide: building it. Architecture, API
  reference, release runbooks, QA, design notes. Entry point
  `docs/contributor/README.md`. (Agents read this file, `AGENTS.md`, not a copy
  inside `docs/`.)

**`nav` does not gate publication.** MkDocs builds EVERY `.md` under `docs_dir` into
a live public page. `mkdocs.yml` `nav` controls only what appears in the site
navigation — a page left out of `nav` is still public at its URL, just unlinked.
`/ROADMAP/`, `/CLAUDE/` and `/archive/` all shipped publicly this way before anyone
noticed. So:

- **`docs/`** — durable documentation you are content to publish. Anything you add
  here is public.
- **`agent-work/`** — AGENT scratch, never part of `docs/` or the build: session
  notes, handoffs, QA logs, reviews, validation reports, audits, triage, design
  explorations, proposals.
- **`agents/`** — the harness: skills, prompts, and `agents/ROADMAP.md` (the priority
  spine). Operational planning, not documentation.
- **delete** — pure crud or superseded material: `git rm` it.

`scripts/check_docs_publication.py` enforces this: every built page must be reachable
from `nav` or listed in `scripts/check_docs_publication_allowlist.json`. Adding an
allowlist entry is a decision to publish an unlinked page — make it deliberately.

When unsure between `docs/` and `agent-work/`: point-in-time, dated, "what I found"
material is agent-work; durable "how the system works" reference is `docs/`. Material
that must never be public goes outside `docs/` entirely — not merely out of `nav`.

---

## Where Things Live (file placement)

Nothing new lands at the repo root. Root holds the governance docs
(`AGENTS.md`, `CONSTITUTION.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`,
`USER.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`), repo-wide config
(`mkdocs.yml`, `features.yaml`, `coverage-baseline.json`, `.swiftlint.yml`), and
the product/tooling directories below. A new note, report, or plan at the root
is misplaced — no exceptions.

**Agent scratch → `agent-work/`.** Never the repo root, never `docs/`.

| What you are writing | Where |
|---|---|
| Status / handoff / session notes | `agent-work/status/` (e.g. `agent-work/status/SIDEBAR_STATUS.md`) |
| Plans, sequencing, dispatch batches | `agent-work/plans/` |
| Specs and design explorations | `agent-work/specs/` |
| Reviews, audits, QA logs, validation reports | `agent-work/reviews/` |

The four `*_STATUS.md` files already live in `agent-work/status/` — follow that
convention; a new `FOO_STATUS.md` at the root is wrong by construction.

**Product code.** Four peer products, one docs tree, one fixtures tree:

| Path | What |
|---|---|
| `fichero/` | Swift/SwiftUI app + Xcode project |
| `fichero-server/` | Python FastAPI server (`src/fichero_server/`) and the Python test suite |
| `fichero-cli/` | `fichero` CLI (`src/fichero_cli/`, tests in `fichero-cli/tests/`) |
| `fichero-mcp/` | MCP server product (`src/fichero_mcp/`, tests in `fichero-mcp/tests/`) |
| `test-fixtures/` | Shared specimen files, resolved only via `tests/fixture_paths.py` / `TestFixtures.swift` |
| `docs/` | Published documentation — `docs/user/` and `docs/contributor/` (see Docs Placement above) |
| `agents/` | Harness: skills, prompts, `agents/ROADMAP.md` |
| `scripts/` | Repo-wide gates and tooling (`check_*.py`, `verify_*.sh`) |

Pure crud or superseded material is `git rm`-ed, not parked at the root.

---

## Key Paths

| Path | What |
|---|---|
| `CONSTITUTION.md` | Product north star: what we're building, why, what it's not, hard constraints |
| `AGENTS.md` | This file — operational manual + hard rules |
| `docs/contributor/architecture/` | Architecture docs |
| `docs/contributor/architecture/vocabulary.md` | Shared backend/frontend terminology |
| `USER.md` | About Daniel — who he is, constraints |
| `STATE.md` | Local working notes (gitignored, not in the repo) — current branch, focus, next session |
| `MEMORY.md` | Local working notes (gitignored, not in the repo) — persistent lessons and decisions |
| `agents/skills/` | Session-start / manager / worker skills + shared principles |
| `fichero/fichero/` | Swift/SwiftUI frontend (Xcode project: `fichero/fichero.xcodeproj`) |
| `fichero/fichero-api-client/` | Generated Swift OpenAPI client package |
| `fichero-server/src/fichero_server/` | Python FastAPI backend (the server; was `fichero-engine/src/fichero/`, #4227) |
| `fichero-cli/src/fichero_cli/` | `fichero` command-line client (thin HTTP client of a running server) |
| `fichero-mcp/src/fichero_mcp/` | MCP server product (also shipped inside the app bundle) |
| `fichero-server/tests/` | The gated Python suite for all three products (`unit/`, `integration/`, `contracts/`, and `perf/` — gated separately via `scripts/verify_perf.sh`) |
| `fichero-cli/tests/`, `fichero-mcp/tests/` | Each product's own unit tests. Run directly (`pytest fichero-cli/tests`) — their conftest supplies the sibling `src/` paths. **Not yet in `verify_all`/`verify_python`, which name `fichero-server/tests/` explicitly** |

---

## Rules I Don't Break

1. Never push directly to `main` — always go through a PR (create it and merge it yourself).
2. Never skip build, test, lint before marking work complete.
3. Never modify genuinely auto-generated files: `openapi.json`, anything under `fichero/fichero-api-client/.build/`, anything under `fichero/fichero-api-client/Sources/FicheroAPIClient/` that's produced by the OpenAPI generator. The `openapi.json` files ARE regenerated from the backend (via `fichero-server/scripts/sync_openapi_schema.sh`) and that regen output should be committed — what's forbidden is hand-editing them.
4. When editing a service wrapper that builds a request body, **always use the OpenAPI-typed fields** on `Components.Schemas.*`, not `additionalProperties`, for any field that's declared in `openapi.json`. Dumping declared fields into `additionalProperties` silently loses writes under Pydantic `extra="allow"` — see commit 31fc4141 for the pattern and `docs/contributor/architecture/fichero/api_client.md` for context.
5. Never start coding before a plan exists for non-trivial work.
6. `PYTHONPATH` must be set to `fichero-server/src` for all Python commands.
7. Never create per-task branches — commit all work to the milestone branch directly.
8. Never start a milestone more than one ahead of what Daniel is currently testing.
9. **Schema changes are no-migration in 0.0.x for fresh DBs, but real data needs migrations.** A new column on a Pydantic model is picked up by `_ensure_table` on fresh databases — don't add an `ALTER TABLE ADD COLUMN` for a column already in the model. BUT once a persisted DB (`app.duckdb` or a real library) exists, a new column needs an idempotent `ALTER`+backfill, not `CREATE-IF-NOT-EXISTS`. Structural changes (table renames, data backfills) belong in `db_migrations.py`.
10. **New .swift files must be registered with `scripts/add-swift-file.rb`**: The `Fichero` main target uses traditional PBX file references — a file written to disk is invisible to the compiler until registered. Always run `ruby scripts/add-swift-file.rb <path>` after creating any new `.swift` file. Test-target files are the exception (sync'd groups). Never edit `project.pbxproj` by hand. The build gate will catch unregistered files as "Cannot find type" errors.
11. **Worktrees live ONLY under `~/code/fichero-worktrees/<name>`; never `rm` a `~/code/` sibling.** Create worktrees with `git worktree add ~/code/fichero-worktrees/<name> -b <branch> main` — never as bare siblings `~/code/fichero-<name>`. Remove them ONLY with `git worktree remove --force <path>` (operates only on registered worktrees). **NEVER `rm -rf` a `~/code/` path and NEVER glob-delete `~/code/fichero-*`** — bare siblings are SEPARATE projects with their own remotes and uncommitted work. Before any destructive fs op, confirm the path is under `~/code/fichero-worktrees/` AND in `git worktree list`; otherwise stop and surface it. A worktree that must build on un-pushed integration-branch state (not yet on `origin/main`) is created from that branch's HEAD sha explicitly — `git worktree add <path> <integration-branch-or-sha>` — not the Agent tool's default `isolation: "worktree"`, which branches from `origin/main` and won't see integration-only commits.

---

## Before editing backend or API-client code

Read `docs/contributor/architecture/` first — specifically:
- `docs/contributor/architecture/fichero/api_client.md` for the OpenAPI round-trip contract.
- `docs/contributor/backend-development-standards.md` for backend conventions.
- `docs/contributor/swiftui-development-standards.md` for Swift conventions.

`AGENTS.md` is the canonical detailed guidance and also references these.
