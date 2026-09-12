# AGENTS.md: Operational Manual

The single canonical agent/operational doc for Fichero. Every coding agent —
Codex, Claude Code, Claude-in-Xcode — reads this file (`CLAUDE.md` is a thin
pointer here). Product north-star: `CONSTITUTION.md`. Session-start / manager
skills under `agents/skills/` tell each lane its job.

Two roles, one layer (spec: `docs/contributor/specs/dev-orchestration-harness.md`):
the **manager** (the interactive session — coordinates, reviews, owns the verify
gate, AND integrates/merges) and the **worker** (implements + tests its own diff).
Start with `/session-start-manager` or `/session-start-worker`. Work happens on
the milestone branch this worktree is on — commit directly, no per-task branches.

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

**`Fichero (Dev Embedded)` is the RUN scheme** (design lead, 2026-08-04); **`Fichero
(Dev Local)` is the TEST scheme.** Dev Embedded's config is `Dev Embedded`, not
`Debug` — `DEBUG` is undefined, so `EngineConfig.engineProvisioningStrategy()`
resolves to `.releaseEmbedded` and **the app spawns and owns the bundled engine**
on the same UDS socket a hand-started `start_backend.sh` uses
(`EngineConfig.udsSocketPath`) — stop any hand-started engine first, or you get
two engines on one socket. The embedded engine is also UDS-only (no TCP, no TLS),
so **the CLI and MCP server cannot reach it**; to exercise CLI/MCP, run a
`start_backend.sh` engine (HTTPS `:8765`) instead — app quit, or against a
scratch library (two engines must never open the same DuckDB).

Dev Local's config IS `Debug`, resolving to `.debugExternal`: it never spawns
and *requires* a developer-run engine (not bundled in Debug, #3042) — the
opposite requirement of Dev Embedded. Swift optimization is `-Onone` in both;
they differ in who owns the engine, not in speed.

**Which tests the gates actually run — and what they deliberately skip.** Every
gate (`verify_python.sh`, `verify_all.sh --standard`, `build-and-validate.sh`)
covers `fichero-server/tests/unit/` plus, in `verify_all`, `tests/contracts/`.
**`fichero-server/tests/perf/` is run by NOTHING automatically** — run it on
purpose via `scripts/verify_perf.sh` (~50 min).

Do NOT reach for the whole-tree `pytest fichero-server/tests` form: it silently
pulls in the perf suite and takes ~70 minutes (two perf tests alone were 73% of
a measured 4219s full run, #4039) — they're SLOW, not hung, and print nothing
under `-q` for ~25 min each; `verify_perf.sh` streams progress instead.

A perf run and an Xcode build together can push this machine past the load
where the OS starts killing processes — check `pgrep -f xcodebuild` before
starting either the perf suite or a whole-tree pytest run.

**Working in a git worktree?** A worktree has no `.venv` of its own. Activate the one from
your main checkout, but keep `PYTHONPATH=fichero-server/src` **relative to the worktree**
— the venv is an editable install pointing at the main checkout, so without it you lint
and test the *other* tree and get a green run that means nothing. Never write an absolute
path like `~/code/fichero/.venv` into a doc or a script; it is only true on one machine.

- **Backend API changed?** `start_backend.sh` **auto-syncs the OpenAPI client on startup** (default;
  `--no-sync`/`--fast` skip it), so a normal server restart regenerates the committed client for you
  — then commit the regen. Run `./fichero-server/scripts/sync_openapi_schema.sh` directly only when
  you changed the API but aren't restarting the server. (Skipping the sync → the Swift build breaks
  against a stale client.)
- **Ship tests with the change.** Every SwiftUI fix or feature lands with new/updated unit tests in the same commit; write the failing test first for a bug. Test the logic (state, predicates, builders, ID parsing) rather than the rendered pixels, and eyeball pixels by running the built app.
- **Risky diff?** Anything touching auth, file I/O, network, secrets, or keychain → run `/security-review`.

**Testing manual: `docs/contributor/TESTING.md`.** Short version:
`fichero/Tests/Unit/general/` mirrors `fichero/fichero/` — a new test goes in
the matching folder (plus `Transport/`/`Contract/` buckets); shared specimen
files live in `test-fixtures/files/`, resolved ONLY via `tests/fixture_paths.py`
/ `TestFixtures.swift`; seeded libraries come only from `seed_test_library.py`;
the coverage ratchet (`scripts/check_coverage_ratchet.py` + `coverage-baseline.json`)
fails any run whose coverage drops — baselines move only by deliberate
`--update-baseline` commits.

**Design-led surfaces carry ONE name across three places** (guardrails enforce, all in the gate):
a spec `docs/contributor/specs/<name>.md`, a GitHub milestone named `<name>` (its description
points back at the spec), and a test tag of the same area name **front and back** — Swift `@Tag`
in `fichero/Tests/Unit/general/TestTags.swift`, pytest marker in `fichero-server/pyproject.toml`.
`scripts/check_specs_have_tests.py` binds spec↔test; `scripts/check_spec_milestones.py` binds
spec↔milestone. Approving a spec means: flip `Status: APPROVED`, declare `Milestone: <name>`,
create/rename that milestone, and cite the spec from ≥1 test. See `docs/contributor/TEST-TEMPLATE.md`.

---

## Worker Orchestration

Fichero is built by AI coding agents, **one layer deep** (spec:
`docs/contributor/specs/dev-orchestration-harness.md`). The shape:

- **Manager = the interactive session (Fabel).** Fast, cheap, always-on. It coordinates,
  does the design/root-cause/review, owns the verify gate, and dispatches workers. It does
  not grind implementation itself when a worker can.
- **Workers = sonnet by default, opus on escalation.** sonnet writes the specced feature +
  its tests, bulk/mechanical edits, doc sweeps; opus is only for hard root-cause debugging,
  tricky design, or deep review. One layer — a worker does NOT spawn its own managers.
  Route DOWN for writing, escalate UP only for reasoning.

Two dispatch modes — pick by lifetime, not habit:

- **Subagents (the `Agent` tool) — the DEFAULT** for a bounded task that reports back within
  the turn (context-isolated, no plumbing). Most delegation is this. `subagent_type:
  "general-purpose"` with `model: "sonnet"` (or `"opus"`), or `"fork"` to hand off your own
  context.
- **tmux worktree lanes — ONLY for long, cross-turn work** (a whole milestone that must
  survive across turns). Then, and only then:

  **`scripts/spawn-worker.sh` is the canonical launcher for a tmux lane — use it, never hand-roll.**

  ```bash
  scripts/spawn-worker.sh <opus|sonnet> "<Milestone Title>" [session-name]
  ```

  It fetches, creates the worktree off **`origin/main`** (never stale local `main` —
  hand-rolling `git worktree add … main` starts a worker on stale code), opens a
  detached tmux session, activates the venv, and feeds the worker prompt scoped to
  that milestone. Worktrees land under `$FICHERO_WORKTREES` (default: a
  `fichero-worktrees/` beside your checkout); it prints the `tmux attach` command.
- The manager **reviews** each worker's output (ponytail lens plus `/code-review`),
  **build-gates** it, runs `verify_all`, then **merges via PR**, closes the issues,
  and **re-dispatches** the next batch. It checks in on workers about every 15 minutes.
- **Then it CLEANS UP.** Lifecycle: issue → worktree → integrate + build-verify →
  **close the issue** → **remove the worktree AND delete its branch** (`git worktree
  remove`, never `rm -rf` a sibling worktree; then `git worktree prune`). Merged
  worktrees left lying around rot into stale-code and phantom-diff hazards. Keep only
  worktrees with an ACTIVE worker or genuinely unintegrated commits.

Workers never push to shared branches for the manager; the manager owns the merge.
This keeps one Xcode and one full-suite run as the gate while many workers grind in
parallel, isolated worktrees.

**Spec-lead development — the systematic loop, every surface, every time** (authority:
`docs/contributor/TESTING-CONSTITUTION.md` + `TEST-TEMPLATE.md`; run the design half in **plan
mode** with a **ponytail lens**). One `<name>` binds four artifacts — spec, GitHub milestone,
tests (tagged), docs. The eight steps:
1. **Prior art first** — survey how the field solves this (DH standards, NLP/NLG, Hugging Face,
   libraries) and cite what we reuse. Don't invent what the field has solved.
2. **Spec** — DRAFT a one-line-per-behavior spec (`specs/<name>.md`, format per `_TEMPLATE.md`).
3. **Approve** — the design lead approves the intent; flip APPROVED + declare the milestone.
4. **Test-first, per surface it touches** — **server (pytest) · MCP · CLI · Swift unit · UI-Mac
   (XCUITest) · iPhone · iPad**. Cross-surface invariant + capability-availability tests HARD-GATE.
5. **Reuse, don't duplicate** — search for an existing code path first (we too often grow a SECOND
   implementation); extend it, never add a parallel one.
6. **Implement** to green.
7. **Verify** — the gate (`verify_all`).
8. **Document both audiences** — contributor docs AND the user manual (reuse the snapshot as the
   screenshot). A regression isn't fixed until a test that would have caught it exists.

## Git Practices — Lanes, Integration, Commits

**Full layout + process: `docs/contributor/specs/git-worktree-workflow.md`** — one repo
(`~/code/fichero/.git`), worktrees as ephemeral branch-views, everything pushed via `main`;
branch-off-`origin/main`, the integration gate, keep-updated-via-GitHub, and cleanup. The essentials:

Short-lived **lane branches** (one worker, one worktree under
`~/code/fichero-worktrees/<name>`, branched off `origin/main`) merge into an
**integration branch** when 2+ lanes must land together; the manager gates the
combined diff there (full suite, 0 failed) before fast-forwarding to `main`.
Delete a lane branch once its commits reach `main` — nothing is lost, commits
stay reachable by SHA / `git log --grep` / the closed issue.

**Commit, never stash.** Park interrupted work as a WIP commit on the lane
branch — a stash doesn't survive a worktree teardown. Baseline-diffing happens
in a **separate worktree**, never stash-and-checkout in the same one (see
`agent-work/design/git-practices-fabel-review.md` "stash-pop hazard").

**Bring an agent up to speed with data, not a long-lived branch:**
`agents/ROADMAP.md` + GitHub milestones for "what's next", `*_STATUS.md` /
fabel-review docs for "what's the current state", commit-scope grep (`git log
--grep '(#1234)'`) for "what happened and why" — not a branch several agents
keep rebasing onto.

**Verification runs in the foreground.** Any agent whose job is "verify then
commit" blocks on its own check and commits in the SAME turn it sees the
result — never a background test + a `Monitor` + pause, or the turn ends
before the result lands and the agent loops without ever committing.

**Path-keyed guardrails move with the file.** A commit that moves, renames, or
splits a file must update every `scripts/check_*.py` `TARGET_FILES`-style
constant and guardrail allowlist in the SAME commit (see "A `pytest -k` subset
skips the architecture guardrails" below) — the guardrail's own test files are
part of the gate, not optional. Full rationale:
`agent-work/design/git-practices-fabel-review.md`.

### Manager loop — use the scripts, don't improvise

The manager drives work through these scripts. **Do not hand-pick issues, hand-edit ROADMAP order, or `gh issue create` by hand** — that is how duplicate/mis-placed milestones crept in.

1. **Pick next work** — `python3 scripts/choose_next.py [--json]`: walks the
   `## Tier` PRIORITY SPINE in `agents/ROADMAP.md` (foundations-first, ascending
   due-date) and returns the highest-priority *ready, unclaimed* batch.
2. **Size each issue** — `python3 scripts/dispatch_advisor.py <issue#>` → `mini |
   regular | frontier` worker class.
3. **Dispatch by lane label** — `backend` → codex · `client:swiftui` → claude ·
   `docs` → codex-docs. External worktree only, **commit-only, one build at a time**
   (serialize-builds rule). `needs-design` issues are NOT for free-model workers.
4. **File any new issue** — `scripts/file_issue.sh --title ... --type ... --lane ...
   [--milestone ...]` (`--dry-run` to preview). It validates the milestone is OPEN,
   enforces the 15 canonical labels, and auto-routes by keywords.
5. **On a red test** — `python3 scripts/tests_to_issues.py <junit.xml>` files one
   tracked issue per failing test so nothing is lost on a crash.
6. **Gate** from the **repo root** (contract tests read root-relative paths):
   `bash scripts/verify_all.sh --standard|--full`. Then merge via PR, close issues,
   re-run `choose_next.py`. Do NOT hand-edit ROADMAP order / milestone `due_on` —
   ask the board organizer to re-sort.

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

When an agent runs **inside Xcode**, prefer the MCP tools over command-line `ls`/`find` — every shell invocation may prompt the user for approval.

- **Build** with `BuildProject` (Xcode MCP) rather than raw `xcodebuild` — it shares Xcode.app's cache and avoids `build.db` lock contention.
- **New Apple APIs**: use `DocumentationSearch` (Xcode MCP) liberally — it's newer than training data. ALWAYS search for **Liquid Glass** (design system), **FoundationModels** (on-device ML), and evolving **SwiftUI** patterns (`NSViewRepresentable`-era) before assuming an implementation doesn't exist.
- **The three-leg Swift check** before declaring SwiftUI work done, in order: (1) `swiftlint lint fichero/fichero/` clean; (2) `BuildProject` succeeds; (3) `RunAllTests` passes. `XcodeRefreshCodeIssuesInFile` gives fast per-file diagnostics but does NOT substitute for a full build; use `RenderPreview` for rendered-UI changes.
- **Limit changes to the requested task** — don't make unrelated edits.

SwiftUI code-style guidelines live in `docs/contributor/swiftui-development-standards.md`; the deeper architecture reference in `docs/contributor/architecture-overview.md`.

---

## Verification (`verify_all`)

One gate, tiered. Run from the repo root:

- `bash scripts/verify_all.sh --fast` — swiftlint + ruff + `scripts/check_*.py` guardrails + version-date + OpenAPI model sync. Cheap; workers can run it.
- `--standard` — fast + backend pytest unit tests.
- `--full` — standard + platform legs (macOS Xcode build/test + the generic, device-less iOS Simulator compile gate; `--macos` / `--ios` to select). The manager owns `--full`.

Backend pytest needs `PYTHONPATH=fichero-server/src`; write-suites need their `FICHERO_RUN_*` flag. Parse the summary — merge only on **0 failed**. The macOS/UI leg needs a live window server (screen unlocked + `caffeinate -d`) or XCUITest times out. The iOS leg (`--ios`) is compile-only, using isolated DerivedData/output dirs so it never boots or names a simulator.

## Verify the part you touched (`gate part`) — do this AS YOU WORK

**Before you say an issue is done, run `scripts/gate part <area>`.** Not at the
end of the day, not before a release — while the work is in your hands and you
still remember what you changed.

```bash
scripts/gate areas              # what areas exist
scripts/gate part sidebar       # lint + build + Swift tests + engine tests + perf ratchet
```

It runs the SAME checks the release gate runs, scoped to one area, so green
here means what green means there. Minutes instead of ninety.

### It measures performance and memory too, automatically

Every test is timed and held to its **best-ever** result (#4439, milestone
#268). You do not opt in and there is nothing to remember:

- **Faster** → the bar tightens itself, permanently. Free.
- **Slower** → it FAILS, and tells you to re-run on a quiet machine or raise the
  entry in `fichero-server/tests/perf_baseline.json` **saying what bought the
  time**.

Comparison is against the best ever, never against last week — otherwise the
window absorbs each regression and the bar drifts up with the thing it was
meant to catch (fifty accepted 5% slips are a 12x slowdown).

**Why this is a working habit, not a release step:** a slowdown found before a
release is attributable to one person, one change, one afternoon; found at
release time it belongs to nobody, and the answer becomes "raise the budget."
**The issue you are working on is the unit of performance, not the release.**
If your area has no entry in `area_table()` in `scripts/gate`, add one — a
prefix and a test path, two minutes — rather than skipping the check.

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

4. **A closed set of values is an enum in the schema, never a bare `str`.** A `str`
   field generates a Swift `String`, so both sides write literals into it and nothing
   in the toolchain can object. `artifact_type` was declared `artifact_type: str`; the
   server wrote `"text_geometry"`, the client queried `"transcription"`, and two green
   commits produced one dead feature (#4418). Declared as an enum, the generated client
   turns that mismatch into a **compile error**. The same applies to any status, kind,
   mode, or event-type vocabulary — including `ChangeEvent.type` (#4427).
5. **A structured payload is a typed field, never `dict[str, Any]`.**
   `ExecuteWorkflowRequest` has no selection field: `selected_doc_ids` rides untyped
   inside `inputs`, which is why nothing could reject a client that sent a whole folder
   when the user picked one file (#4396). If it has a shape, declare the shape.

Prefer *impossible* over *checked* over *documented*. A generated type cannot drift; a
guardrail can fail open (#4382); a convention can be forgotten.

**Timestamps are aware UTC.** Write `fichero_server.core.timeutil.utc_now()`, never
`datetime.now()` / `datetime.utcnow()` — a naive local value serializes without an
offset and every ISO-8601 decoder reads it as UTC, which rendered a just-finished
run as "3 hours ago" (#4347). `scripts/check_naive_datetimes.py` fails the gate on
the naive forms. DuckDB `TIMESTAMP` columns are naive and DuckDB shifts an aware
value into the *session* timezone on bind, so open connections with
`fichero_server.core.duckdb_session.connect_utc` (pins `TimeZone='UTC'`) and pass
naive values read back out through `ensure_utc()` — a naive stored value **is** UTC.

---

## Two-Stack Rule

Before completing a backend route change: does OpenAPI need updating? Do the Swift generated files need regenerating? Do frontend callers need updating? Plan first for architectural, OpenAPI-schema, feature-flag-tier, or database-schema changes; proceed directly on clear-root-cause fixes, tests, and lint/build fixes.

**Engine bug or rendering bug?** The typed `fichero` CLI mirrors every endpoint reachable from SwiftUI. Reproduce against the CLI first; if it fails the same way, the engine owns it.

---

## Architecture at a Glance

```
SwiftUI app · fichero CLI · fichero-mcp
              |
   Unix domain socket (local) or
   HTTPS on 127.0.0.1:8765 (TLS, pinned fail-closed)
              |
        FastAPI engine  ──→ DuckDB (metadata) + LanceDB (vectors)
                        ──→ LangGraph (workflows)
                        ──→ LangChain (LLM providers)
```

The Swift app is a rendering layer: storage, ingest, search, workflows, the KG and
all validation live in the engine. `litellm` is metadata only — `get_model_info()`
and `cost_per_token()`. It never routes a call.

**Why the split is load-bearing, not stylistic.** Other clients exist (CLI, MCP, and
later web and other people's machines), and they must agree. Two clients with the
same logic drift; two clients rendering the same server state cannot — a workflow's
target set resolved client-side went wrong twice, once too wide (#4396), once
collapsed to one item (#4419). **Clients send what the user pointed at; the server
resolves what that means.**

The corollary is real-time propagation: a change in one client reaches the others
without a refresh via `api/change_stream.py`'s domain-typed vocabulary
(`entity.updated`, `claim.updated`, `document.updated`, `stream.gap`/
`stream.resync_required`) — but a mutation that does not emit is invisible to every
other client (how the KG inspector stopped updating, #4392). **Emit at the write,
not at each caller**, or the next caller forgets. See #4427.

**Where things live.** Pydantic models in `fichero-server/src/fichero_server/models/`;
the OpenAPI schema generated from them; the Swift client generated from that schema;
Swift **services** in `fichero/fichero/Services/` wrapping the generated client; Swift
**stores** (`@Observable`) as the only endpoint accessors, with views observing stores
rather than fetching. `fichero-cli` and `fichero-mcp` are thin — every command or tool
is one or two HTTP calls through `FicheroClient`, and **no backend logic lives in
either**. If a client needs logic, the logic belongs in the engine.

- **Route tiers.** `FICHERO_FEATURE_TIER` (`release` | `beta` | `alpha` | `dev`, default
  `release`) in `api/main.py`, table in `api/feature_tiers_generated.py`. **21 route
  groups are tier-gated** (`scripts/check_agents_route_tier_claim.py` checks it); a
  default (release) engine registers only `/api/ingest` and `/api/search` — `workflows`,
  `kg`, `claims`, `chat`, `mcp` and the rest need `beta`+. The app spawns its engine at
  its own build tier so it never notices, but a hand-started engine at the default tier
  404s the whole workflow/KG surface (#4470) — the 404 now NAMES the tier that would
  expose it. Route registration is a poor usability signal — the UI is flag-gated separately.
- **What ships to a user** is decided by `FeatureManager.resetToV001()` in
  `fichero/fichero/Models/FeatureManager.swift`, re-applied on every `releaseProfileVersion` bump.
- **Databases:** `~/Library/Application Support/Fichero/fichero.duckdb` and `.../lance/`.
  Never query them directly — everything goes through `db.py`.
- **Engine is macOS-only when embedded.** Briefcase declares one platform; iOS and
  iPadOS always talk to a remote engine. See `fichero-server/README.md`.
- **Restaging the embedded engine — use a script, never bare `briefcase`:**

  ```bash
  scripts/preflight-embedded-engine.sh --rebuild   # the restage; Xcode runs the no-arg form itself
  fichero-server/scripts/build_backend_bundle.sh   # full rebuild + Briefcase sign (release path)
  ```

  `briefcase update -r` by hand is **not** a restage — it never re-renders the generated
  app template, so `Info.plist` keeps a stale `CFBundleShortVersionString` (once left three
  drifted version stamps at once, 2026-09-01). Both scripts above recreate the template
  when the stamped version has drifted.
- **The version label is checked at launch, not just at build.** The embed phase stamps
  `FicheroEmbeddedEngineVersion` (bundle copied) and `FicheroExpectedEngineVersion`
  (checkout's `pyproject.toml` at build time) into `Info.plist`; `AppState` compares them
  against `/api/health`'s `backend_version` and shows a banner on mismatch.
  `scripts/check_engine_version_stamp.py` guards that the embed phase writes the stamps.

---

## MCP Tools

**The live tool list in your session is authoritative.** The repo pins nothing — no
`.mcp.json`. Every MCP server comes from the agent's own global/plugin config, varies
per harness, and changes over time; a roster here would rot. What the harness *needs*,
and what to do when it is missing:

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

- **New `.swift` files just work — never run `add-swift-file.rb` on the app target.** It's a synchronized folder; explicit registration DUPLICATES the build file. Never hand-edit `project.pbxproj`.
- **`PYTHONPATH=fichero-server/src` on every Python command.** The shared `.venv` is editable-installed against your MAIN checkout, not this worktree — without it, a worktree gates the *stale* tree.
- **Never bare `uvicorn`.** The app pins `https://127.0.0.1:8765` fail-closed. Use `fichero-server/scripts/start_backend.sh`.
- **Multi-library requests need the `X-Fichero-Library-Path` header** (app-wide endpoints — health, providers/catalog, settings — skip it).
- **A `pytest -k` subset skips the architecture guardrails.** Anything touching a persisted DB, a route, or a Swift service needs the full run.
- **Paths assembled from parts hide from a string sweep.** `ROOT / "docs" / "<page>.md"` has no `docs/<page>.md` substring to grep — moving a file breaks it silently.
- **Backtick text inside `git commit -m "..."` is command substitution** — the shell executes it and pastes the output into your message. Use `git commit -F <file>`.
- **Automated edits and function-local imports do not mix — AST-audit after any scripted import change.** A batch import-inserter once spliced a *function-local* `import sys` into a module-level import, then `ruff --fix` deleted it as "unused" while references remained (#4487). Run `python -c "import ast; ast.parse(open(f).read())"` over every touched file after any scripted import change.
- **Renames/moves break path-keyed guardrails.** `PERSISTENCE_PATH`, `WILDCARD_BIND`, `db_access`, `single_connection`, and every `check_*.py` `TARGET_FILES` list hardcode paths — a move that doesn't update them gives a false green (7 regressions from #3751/#3754). Grep for the old path across `scripts/check_*.py` before committing a rename.

---

## Code Navigation

jcodemunch is an AST index with large token savings over Read/Grep/Glob (fallback per
MCP Tools above). Typical routing:

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

## Commit Format & Attribution

Conventional commits — `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, `style:`
— always referencing a GitHub issue: `feat: add tasks router (#420)`. GitHub Issues +
Milestones is the source of truth for the backlog. **Before filing a bug or feature, search
existing issues** (`gh issue list --search "<terms>"` / `--state all`) and comment on the match
instead of opening a duplicate — the same reuse-don't-duplicate discipline we apply to code.

**Each agent is the AUTHOR of its own commits — NOT a `Co-Authored-By` trailer on a
human-authored commit.** The agent doing the work is the git *author* (Claude →
`Claude <noreply@anthropic.com>`; another model → that model's name); the human who directed it is
credited by a `Directed-By:` trailer, not by owning the authorship. This is what makes
`git log --author=Claude` and GitHub's contributor view cleanly separate agent work from the
maintainer's own edits — a `Co-Authored-By` line does not (it leaves the human as author):

```bash
git -c user.name="Claude" -c user.email="noreply@anthropic.com" \
  commit -m "docs: fix faq models (#1234)

Directed-By: the maintainer"
```

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
a live public page; `mkdocs.yml` `nav` controls only site navigation — a page left
out of `nav` is still public at its URL, just unlinked (`/ROADMAP/`, `/CLAUDE/` and
`/archive/` all shipped this way before anyone noticed). So:

- **`docs/`** — durable documentation you are content to publish; anything added here is public.
- **`agent-work/`** — AGENT scratch, never part of `docs/` or the build: session notes, handoffs, QA logs, reviews, audits, design explorations, proposals.
- **`agents/`** — the harness: skills, prompts, `agents/ROADMAP.md` (the priority spine). Operational planning, not documentation.
- **delete** — pure crud or superseded material: `git rm` it.

`scripts/check_docs_publication.py` enforces this: every built page must be reachable
from `nav` or listed in `scripts/check_docs_publication_allowlist.json` (a deliberate
decision to publish an unlinked page). When unsure between `docs/` and `agent-work/`:
point-in-time "what I found" material is agent-work, durable "how it works" reference
is `docs/`; anything that must never be public goes outside `docs/` entirely.

### Manuscript model — MARKDOWN IS THE MASTER

The guide chapters in the repo are the masters (`docs/user/guide/NN-<slug>.md`,
`docs/contributor/`). The design lead edits them in **Scrivener** via
Sync-with-External-Folder; agents edit the same files directly and may add images
(`docs/assets/users/…`, page-relative) — no round-tripping through a Drive `.docx`
(those are historical copies only). Contract: one chapter per file (`NN-<slug>.md`,
`# Title` H1, plain markdown); `> 🤖 *AI Drafted (Not reviewed)*` marks an unreviewed
page; gate every edit with `scripts/check_docs_publication.py` + `mkdocs build --strict`
(new chapter needs a `mkdocs.yml` nav line); the Word manual in Drive is built FROM
the markdown via `python3 scripts/build_manual_appendix.py` — the `.docx` is output-only.

---

## Where Things Live (file placement)

Nothing new lands at the repo root. Root holds only governance docs (`AGENTS.md`,
`CONSTITUTION.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `README.md`, `USER.md`,
`CHANGELOG.md`, `RELEASE_NOTES.md`), repo-wide config (`mkdocs.yml`,
`features.yaml`, `coverage-baseline.json`, `.swiftlint.yml`), and the
product/tooling directories below. A new note, report, or plan at the root is
misplaced — no exceptions.

**Agent scratch → `agent-work/`.** Never the repo root, never `docs/`.

| What you are writing | Where |
|---|---|
| Status / handoff / session notes | `agent-work/status/` (e.g. `agent-work/status/SIDEBAR_STATUS.md`) |
| Plans, sequencing, dispatch batches | `agent-work/plans/` |
| Specs and design explorations | `agent-work/specs/` |
| Reviews, audits, QA logs, validation reports | `agent-work/reviews/` |

The four `*_STATUS.md` files already live in `agent-work/status/` — follow that
convention; a new `FOO_STATUS.md` at the root is wrong by construction.

`agent-work/` is listed in `.gitignore`, so a note that is worth keeping must be
added deliberately: `git add -f agent-work/status/<file>.md`. Scratch you do not
add stays local, which is the point.

**Product code.** Four peer products, one docs tree, one fixtures tree — full paths in
Key Paths below. Pure crud or superseded material is `git rm`-ed, not parked at the root.

---

## Key Paths

| Path | What |
|---|---|
| `CONSTITUTION.md` | Product north star: what we're building, why, what it's not, hard constraints |
| `AGENTS.md` | This file — operational manual + hard rules |
| `docs/contributor/architecture/` | Architecture docs |
| `docs/contributor/architecture/vocabulary.md` | Shared backend/frontend terminology |
| `USER.md` | About the design lead — who they are, constraints |
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
| `test-fixtures/` | Shared specimen files, resolved only via `tests/fixture_paths.py` / `TestFixtures.swift` |
| `docs/` | Published documentation — `docs/user/` and `docs/contributor/` (see Docs Placement above) |
| `agents/` | Harness: skills, prompts, `agents/ROADMAP.md` (the priority spine) |
| `scripts/` | Repo-wide gates and tooling (`check_*.py`, `verify_*.sh`) |

---

## Rules I Don't Break

- **An issue is not done until `scripts/gate part <area>` is green.** It runs
  the release gate's checks on your area — lint, build, tests, and the perf
  ratchet — in minutes. Performance is the property of the change that caused
  it, not of the release that happens to ship it.

0. **Fail loudly; never fall back silently.** A rename or move is atomic: new path only, every caller repointed in the SAME commit, nothing left at the old location. No compatibility shims, no legacy-path aliases, no "try the new name, then the old name" resolution chains, no `except ImportError` bridges, no default that quietly substitutes a different id, value, model, or file. If something can't be resolved, raise/throw with what was expected and what was found.
   Why this is rule zero: a shim lets a stale caller keep working, so nobody finds it, and the failure surfaces weeks later, far from the change that caused it — #2566's "identity-preserving shims" turned into a **silently skipped** test suite that no gate could see (#4365). A hard cutover would have broken it immediately, at an obvious cause.
   Corollaries: a test that can't run must FAIL, not skip (a conditional skip is only legitimate for a genuinely optional capability, never a broken harness); a guardrail whose input is missing fails, never passes vacuously; grep does not see cross-language references embedded in strings.
   **A guardrail must know when it has gone blind** — not just when input is missing, but when it's present and only half-parsed: finding no violations in the part it managed to read and reporting success is a lie, not a gap. Every parsing/discovery check must assert a floor on what it found and FAIL with a distinct exit code when it comes up short, paired with a `--self-test` that synthesises (never borrows from a shrinking baseline) a known defect and asserts the check catches it. Distinguish BLIND (*my own committed inputs are missing* → exit 2) from NOT ARMED (*the thing I measure doesn't exist here yet* → exit 0). Worked examples: `scripts/check_environment_forwarding.py`, `scripts/check_release_size_ratchet.py`.
1. Never push directly to `main` — always go through a PR (create it and merge it yourself).
2. Never skip build, test, lint before marking work complete.
3. Never modify genuinely auto-generated files: `openapi.json`, or anything under `fichero/fichero-api-client/.build/` or `.../Sources/FicheroAPIClient/` produced by the OpenAPI generator. Regen via `fichero-server/scripts/sync_openapi_schema.sh` and commit the output — what's forbidden is hand-editing it.
4. When editing a service wrapper that builds a request body, **always use the OpenAPI-typed fields** on `Components.Schemas.*`, not `additionalProperties`, for any field declared in `openapi.json` — dumping declared fields into `additionalProperties` silently loses writes under Pydantic `extra="allow"` (commit 31fc4141; `docs/contributor/architecture/fichero/api_client.md`).
5. Never start coding before a plan exists for non-trivial work.
6. `PYTHONPATH` must be set to `fichero-server/src` for all Python commands.
7. Never create per-task branches — commit all work to the milestone branch directly.
8. Never start a milestone more than one ahead of what the design lead is currently testing.
9. **Schema changes are no-migration in 0.0.x for fresh DBs, but real data needs migrations.** A new column on a Pydantic model is picked up by `_ensure_table` on fresh databases — don't add an `ALTER TABLE ADD COLUMN` for a column already in the model. But once a persisted DB (`app.duckdb` or a real library) exists, a new column needs an idempotent `ALTER`+backfill, not `CREATE-IF-NOT-EXISTS`; structural changes (table renames, data backfills) belong in `db_migrations.py`.
10. **New .swift files just work — do NOT register them.** The `Fichero` main target is a SYNCHRONIZED folder; running `scripts/add-swift-file.rb` on a file it already picked up creates a duplicate build-file warning. Never edit `project.pbxproj` by hand; use `git mv` for moves.
11. **Worktrees live ONLY under `~/code/fichero-worktrees/<name>`; never `rm` a `~/code/` sibling.** Create with `git worktree add ~/code/fichero-worktrees/<name> -b <branch> main` — never as bare siblings `~/code/fichero-<name>` (those are SEPARATE projects with their own remotes and uncommitted work). Remove ONLY with `git worktree remove --force <path>`. **NEVER `rm -rf` a `~/code/` path or glob-delete `~/code/fichero-*`.** Before any destructive fs op, confirm the path is under `~/code/fichero-worktrees/` AND in `git worktree list`; otherwise stop and surface it. To build on un-pushed integration-branch state, create the worktree from that branch's HEAD sha explicitly (`git worktree add <path> <sha>`) — not the Agent tool's default `isolation: "worktree"`, which branches from `origin/main` and won't see integration-only commits.
12. **No personal names in new or revised code, comments, commits, issues, milestones, or docs.** Speak in ROLES ("the design lead", "the maintainer", "the reviewer") or drop the "who" and keep the date + intent: `(<name>, 2026-08-27)` → `(2026-08-27)`. A name is acceptable ONLY where it materially improves clarity. Genericize an existing mention when you're already editing that file — never a big-bang sweep of the codebase.

---

## Before editing backend or API-client code

Read `docs/contributor/architecture/` first — specifically:
- `docs/contributor/architecture/fichero/api_client.md` for the OpenAPI round-trip contract.
- `docs/contributor/backend-development-standards.md` for backend conventions.
- `docs/contributor/swiftui-development-standards.md` for Swift conventions.

`AGENTS.md` is the canonical detailed guidance and also references these.
