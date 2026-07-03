# AGENTS.md: Operational Manual

The single canonical agent/operational doc for Fichero. Every coding agent —
Codex, Claude Code, and Claude-in-Xcode — reads this file. (`CLAUDE.md` is a thin
pointer here.) The product north-star is `CONSTITUTION.md`; the detailed
architecture/development guide is `docs/CLAUDE.md`; the session-start / manager
skills under `agents/skills/` tell each lane its job.

Every agent starts with `/session-start` (or a lane variant: `-manager`, `-worker`, `-integrator`, `-auto`); it loads context and reports state. Work happens on the milestone branch this worktree is on. Commit directly, no per-task branches.

---

## Who Verifies What

- **Worker**: lints and tests **only its own diff**, then commits. Backend: `ruff check` + `pytest` on the area you touched. Swift: `swiftlint`. A worker does not compile the whole app or run the full suite.
- **Manager / integrator**: owns the Xcode build, the full `FicheroTests` run, and the cross-stack gate before anything merges (one Xcode, the backend on :8765).

```bash
# Backend — PYTHONPATH=fichero-engine/src on every Python command
PYTHONPATH=fichero-engine/src .venv/bin/ruff check fichero-engine/src/
PYTHONPATH=fichero-engine/src .venv/bin/pytest fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived
bash fichero-engine/scripts/start_backend.sh   # server (serves HTTPS; app pins it fail-closed — never bare uvicorn/HTTP, #2538)

# Swift — lint your diff; the manager runs the build + test (prefer the Xcode MCP)
swiftlint lint fichero/fichero/
```

- **Backend API changed?** Regenerate the committed client or the Swift build breaks: `./fichero-engine/scripts/sync_openapi_schema.sh` (change API → sync → commit regen).
- **Ship tests with the change.** Every SwiftUI fix or feature lands with new/updated unit tests in the same commit; write the failing test first for a bug. Test the logic (state, predicates, builders, ID parsing) rather than the rendered pixels, and eyeball pixels by running the built app.
- **Risky diff?** Anything touching auth, file I/O, network, secrets, or keychain → run `/security-review`.

---

## Worker Orchestration

Fichero is built by AI coding agents that Daniel directs. The work runs through a
manager-with-workers loop:

- The **manager** (`session-start-manager`) holds the control lane. It does not
  write source code. It triages issues, picks the next batch, and dispatches it.
- Each **worker** runs in its OWN git worktree under
  `~/code/fichero-worktrees/<name>`, in a separate tmux window, as an interactive
  agent (`claude --dangerously-skip-permissions` or `codex`). A worker grinds one
  milestone's GitHub issues and commits as itself (see Commit Attribution below).
- The manager **reviews** each worker's output (ponytail lens plus `/code-review`),
  **build-gates** it, runs `verify_all`, then **merges via PR**, closes the issues,
  and **re-dispatches** the next batch. It checks in on the workers about every 15
  minutes.

Workers never push to shared branches for the manager; the manager owns the merge.
This keeps one Xcode and one full-suite run as the gate while many workers grind in
parallel, isolated worktrees.

### Manager loop — use the scripts, don't improvise (2026-07-03)

The board organizer owns issue/milestone structure; the manager drives work
through three scripts. **Do not hand-pick issues, hand-edit ROADMAP order, or
`gh issue create` by hand** — that is how duplicate/mis-placed milestones crept in.

1. **Pick next work** — `python3 scripts/choose_next.py [--json]`. It walks the
   `## Tier` PRIORITY SPINE in `docs/ROADMAP.md` (foundations-first, milestone
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

MCP/build notes live in `docs/CLAUDE.md` (`## MCP Tools`, `## Development Commands`); the SwiftUI code-style guidelines live in `docs/contributor/swiftui-development-standards.md`.

---

## Pydantic + OpenAPI Discipline

Three failure modes that bite *silently*, with no exception and no test failure, just data that vanishes or rows that hide. Load-bearing, not style:

1. **Declare every field on the Pydantic model.** `extra="allow"` lets unknown fields write at runtime, but `model_dump()` only serializes declared fields, so the next read drops them. Add the DB column + the model field + the OpenAPI-typed schema field in the same commit. (`feedback_pydantic_field_must_be_declared.md`)
2. **Swift wrappers set OpenAPI-typed fields, not `additionalProperties`.** Declared fields dumped into `additionalProperties` round-trip on the wire, but the backend Pydantic model ignores them, so the write is lost. (`docs/architecture/swiftui/api_client.md`)
3. **Endpoint defaults matched by strict equality against seed data are foot-guns.** A `folder_path: str = "/"` default silently stops returning rows the moment seed JSON shape changes. Default `Optional[T] = None`, filter only when the caller passes a value, add a regression test. (#722 → #723)

When seed-data shape changes, the shape change and every filter that reads it ship together.

---

## Two-Stack Rule

Before completing a backend route change: does OpenAPI need updating? Do the Swift generated files need regenerating? Do frontend callers need updating? Plan first for architectural, OpenAPI-schema, feature-flag-tier, or database-schema changes; proceed directly on clear-root-cause fixes, tests, and lint/build fixes.

**Engine bug or rendering bug?** The typed `fichero` CLI (`python -m fichero`) mirrors every endpoint reachable from SwiftUI. Reproduce against the CLI first; if it fails the same way, the engine owns it.

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
committer stays the human; credit Daniel with a `Co-Authored-By` trailer.

- Claude writing → author `Claude <noreply@anthropic.com>`
- Codex writing → author `Codex <noreply@anthropic.com>`
- Other model → that model's name with `<noreply@anthropic.com>`

```bash
git -c user.name="Claude" -c user.email="noreply@anthropic.com" \
  commit -m "docs: fix faq models (#1234)

Co-Authored-By: Daniel Tubb <dtubb@me.com>"
```

This keeps authorship honest: the git log shows which agent produced which work,
and Daniel is credited as the human who directed and reviewed it.

---

## Docs Placement

ONE docs folder, `docs/` (the MkDocs `docs_dir`). It is BOTH the published site AND
the reference contributors read on GitHub. Only the pages listed in `mkdocs.yml`
`nav` are surfaced as site navigation; the deeper architecture and runbook material
lives alongside them and stays buildable reference. So:

- **`docs/`** — all durable documentation: the curated user manual (`docs/user/`),
  contributor docs (`docs/contributor/`), API reference, How It's Built, and the
  architecture/runbook reference (`docs/architecture/`, `docs/release/`, etc.). Put
  public-worthy pages in `nav`; leave internal reference out of `nav` but in `docs/`.
- **`agent-work/`** — AGENT scratch, never part of `docs/` or the build: session
  notes, handoffs, QA logs, reviews, validation reports, audits, triage, design
  explorations, proposals.
- **delete** — pure crud or superseded material: `git rm` it.

When unsure between `docs/` and `agent-work/`: point-in-time, dated, "what I found"
material is agent-work; durable "how the system works" reference is `docs/`. Keep raw
internal design docs out of `nav` rather than out of `docs/`.

---

## Key Paths

| Path | What |
|---|---|
| `CONSTITUTION.md` | Product north star: what we're building, why, what it's not, hard constraints |
| `AGENTS.md` | This file — operational manual + hard rules |
| `docs/CLAUDE.md` | Full architecture & development guide (canonical, detailed) |
| `docs/architecture/` | Architecture docs |
| `USER.md` | About Daniel — who he is, constraints |
| `STATE.md` | Current branch, focus, next session |
| `MEMORY.md` | Persistent lessons and decisions |
| `agents/skills/` | Session-start / manager / worker skills + shared principles |
| `fichero/fichero/` | Swift/SwiftUI frontend (Xcode project: `fichero/fichero.xcodeproj`) |
| `fichero/fichero-api-client/` | Generated Swift OpenAPI client package |
| `fichero-engine/src/fichero/` | Python FastAPI backend |
| `fichero-engine/tests/` | Python tests (`unit/`, `integration/`, `contracts/`) |

---

## Rules I Don't Break

1. Never push directly to `main` — always go through a PR (create it and merge it yourself).
2. Never skip build, test, lint before marking work complete.
3. Never modify genuinely auto-generated files: `openapi.json`, anything under `fichero/fichero-api-client/.build/`, anything under `fichero/fichero-api-client/Sources/FicheroAPIClient/` that's produced by the OpenAPI generator. **Note:** `fichero/fichero/Services/*Generated.swift` files are *hand-written service wrappers* (despite the confusing suffix) and CAN be edited. The `openapi.json` files ARE regenerated from the backend (via `fichero-engine/scripts/sync_openapi_schema.sh`) and that regen output should be committed — what's forbidden is hand-editing them.
4. When editing a service wrapper that builds a request body, **always use the OpenAPI-typed fields** on `Components.Schemas.*`, not `additionalProperties`, for any field that's declared in `openapi.json`. Dumping declared fields into `additionalProperties` silently loses writes under Pydantic `extra="allow"` — see commit 31fc4141 for the pattern and `docs/architecture/swiftui/api_client.md` for context.
5. Never start coding before a plan exists for non-trivial work.
6. `PYTHONPATH` must be set to `fichero-engine/src` for all Python commands.
7. Never create per-task branches — commit all work to the milestone branch directly.
8. Never start a milestone more than one ahead of what Daniel is currently testing.
9. **Schema changes are no-migration in 0.0.x for fresh DBs, but real data needs migrations.** A new column on a Pydantic model is picked up by `_ensure_table` on fresh databases — don't add an `ALTER TABLE ADD COLUMN` for a column already in the model. BUT once a persisted DB (`app.duckdb` or a real library) exists, a new column needs an idempotent `ALTER`+backfill, not `CREATE-IF-NOT-EXISTS`. Structural changes (table renames, data backfills) belong in `db_migrations.py`.
10. **New .swift files must be registered with `scripts/add-swift-file.rb`**: The `Fichero` main target uses traditional PBX file references — a file written to disk is invisible to the compiler until registered. Always run `ruby scripts/add-swift-file.rb <path>` after creating any new `.swift` file. Test-target files are the exception (sync'd groups). Never edit `project.pbxproj` by hand. The build gate will catch unregistered files as "Cannot find type" errors.
11. **Worktrees live ONLY under `~/code/fichero-worktrees/<name>`; never `rm` a `~/code/` sibling.** Create worktrees with `git worktree add ~/code/fichero-worktrees/<name> -b <branch> main` — never as bare siblings `~/code/fichero-<name>`. Remove them ONLY with `git worktree remove --force <path>` (operates only on registered worktrees). **NEVER `rm -rf` a `~/code/` path and NEVER glob-delete `~/code/fichero-*`** — bare siblings are SEPARATE projects with their own remotes and uncommitted work. Before any destructive fs op, confirm the path is under `~/code/fichero-worktrees/` AND in `git worktree list`; otherwise stop and surface it.

---

## Before editing backend or API-client code

Read `docs/architecture/` first — specifically:
- `docs/architecture/swiftui/api_client.md` for the OpenAPI round-trip contract.
- `docs/contributor/backend-development-standards.md` for backend conventions.
- `docs/contributor/swiftui-development-standards.md` for Swift conventions.

`docs/CLAUDE.md` is the canonical detailed guidance and also references these.
