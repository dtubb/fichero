# Contributing

Fichero is written by AI coding agents, which receive creative direction from Daniel Tubb.

There is a Manager (Claude Opus), that manages Workers who write code. The Manager keeps track of open issues and milestones, which it writes and keeps track of. The Manager takes commits, reviews them, merges them, runs a battery of tests against them and builds the app.

- The **Manager** agent uses a (`session-start-manager`) skill to control the app. It triages GitHub issues, picks the next batch, and dispatches it to a worker agent. The manager does not write source code.
- Each **worker** agent runs in its own git worktree under
  `~/code/fichero-worktrees/<name>`, in a separate tmux window (an interactive
  `claude` or `codex` or `ollama launch codex` session). A worker grinds one milestone's GitHub issues and commits as itself. Generally, Codex writes backend code, and Claude writes the SwiftUI code. Some code has been written or edited by various open source models.
- The manager **reviews** each worker's output, **build-gates** it, runs
  `verify_all`, then **merges via PR**, closes the issues, and dispatches the next
  batch.
  - Users reviews the result by using the app and filing bugs (‘/bug’ skill) and making feature request (‘/feature’ skill)

GitHub Issues plus Milestones is the source of truth for the backlog. Work lands on
the milestone branch; there are no per-task branches.

## The worktree and worker workflow

The repository uses a manager-with-workers workflow. The manager chooses ready
issues from the roadmap, dispatches a worker for a milestone, reviews the
result, and owns the merge and full gate. Workers make the focused code or
documentation change in their own worktree, commit it, and notify the manager;
they do not push or run the manager's full build gate.

Use `scripts/spawn-worker.sh` to create a worker. It fetches `origin`, creates a
worktree under `$FICHERO_WORKTREES` (by default a sibling `fichero-worktrees/`)
from `origin/main`, opens a detached tmux session, activates the shared virtual
environment, and starts the selected agent. Supported worker commands are
`claude`, `opus`, `sonnet`, `haiku`, and `codex`.

Before editing, a worker claims the issue with `gh issue edit N --add-assignee
@me --add-label status:in-progress`. It skips issues already assigned or marked
in progress, and reports design or ownership blockers with:

```bash
bash scripts/notify_manager.sh --blocked "why this issue is blocked"
```

After a commit, notify the manager with its issue number and SHA:

```bash
bash scripts/notify_manager.sh "done #123 (<sha>); next #456"
```

The notifier appends to the manager inbox and sends a best-effort tmux status
message. Workers commit directly to their milestone branch and never push it.
The manager runs the merge gate (`scripts/verify_all.sh`) and merges through a
pull request after review.

## More detail

See [AGENTS.md](AGENTS.md) for the operational manual (hard rules, commit
attribution, docs placement, worker orchestration). For SwiftUI-specific
guidance see [fichero/AGENTS.md](fichero/AGENTS.md) and for the Python engine see
[fichero-server/AGENTS.md](fichero-server/AGENTS.md). 

For the fuller repo
conventions, see
[docs/contributor/setup-and-contributing.md](docs/contributor/setup-and-contributing.md).
The [Contributor Guide](docs/contributor/README.md) is the entry point for the whole
contributor manual: architecture, the OpenAPI contract, the action registry, the
security model, and the release lane.

If you would like to contribute to Fichero, please make a pull request. Outstanding Milestones and Issues that the Fichero Manager is working on are on GitHub. Milestones and Issues are coded by AI. The Forum is for people.

## Building from source (for developers)

Most people should just download the app — see [Installing and using
Fichero](README.md#installing-and-using-fichero). This section is for working on
Fichero itself.

This is the canonical from-source setup. The subtree READMEs point here rather than
repeating it.

**1. Install Python 3.12.** The engine pins 3.12 — many of its ML dependencies have no
wheels for newer versions, and Briefcase bundles 3.12 into the shipped app.

```bash
brew install python@3.12
```

**2. Clone, then build the virtual environment.**

```bash
git clone https://github.com/dtubb/fichero.git
cd fichero
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e 'fichero-server[dev]'
pip install pytest ruff
```

The last line is not optional. `pytest` and `ruff` are neither runtime dependencies nor
part of the `[dev]` extra, but the lint and test commands in `AGENTS.md` assume both are
on your `PATH`.

**3. There is no `requirements.txt`.** `fichero-server/pyproject.toml` is the
dependency manifest: 37 runtime dependencies, plus the optional extras `[dev]` (15),
`[kg]` (3) and `[image]` (1). The only `requirements-*.txt` in the repo is
`requirements-docs.txt`, which builds this documentation site and nothing else.
**Briefcase is a build tool, not a runtime dependency** —
`fichero-server/scripts/build_backend_bundle.sh` uses it to package the engine into
the shipped app.

**4. Start the engine.** It serves HTTPS on `127.0.0.1:8765`; the app pins that
fail-closed, so a plain-HTTP engine cannot connect. Never run a bare `uvicorn`.

```bash
bash fichero-server/scripts/start_backend.sh
```

Every Python command needs `PYTHONPATH=fichero-server/src` (with the venv from step 2
activated, so `python` is the right one):

```bash
PYTHONPATH=fichero-server/src python -c "import fichero_server"
```

**5. Run the app.** Open `fichero/fichero.xcodeproj` in Xcode and run.

- **Debug (⌘R)** talks to the engine you started in step 4, externally on `:8765`.
- **Release** embeds the engine (Briefcase) and spawns it on launch — no manual start.

iPhone and iPad cannot embed the engine; they connect to one running on a Mac.

## Architecture

Fichero has two components. A front end and a back end. The front end is written in SwiftUI (the Fichero app), and the back end (the Engine) is a FastAPI server that holds the data and logic. The Fichero Mac, iPhone, and iPad apps share one SwiftUI codebase (and the CLI and MCP server are separate front ends) that connect to the Fichero Server and display what it returns. The Fichero Server is packaged using Briefcase and embedded in the Fichero app for release, but it can also run locally as a separate process or be shared on the network (a remote host), so the same clients work whether the engine is embedded, local, or remote.

One engine, many clients:

```
SwiftUI app    fichero CLI    MCP server
       \           |            /
        \          |           /
         HTTPS on 127.0.0.1:8765
                 (TLS, pinned)
                   |
                   v
            FastAPI engine
        (fichero-server/src/fichero_server)
           | DuckDB + LanceDB
           | workflows
           | knowledge graph
           | provider integrations
```

All surfaces sit on top of fichero-server. They render and accept input; they do not contain logic.

| Surface | Path | Status |
|---|---|---|
| SwiftUI app (macOS, iOS, iPad) | `fichero/` (Xcode project: `fichero/fichero.xcodeproj`) | Live |
| `fichero` CLI | `fichero-cli/src/fichero_cli/` | Live (typed, end-to-end verified) |
| MCP server | `fichero-mcp/src/fichero_mcp/server.py` (`fichero-mcp`) | Live |


**Use the CLI (against a running fichero-server):**
```bash
fichero --help
fichero workflow list
```

**Lint the SwiftUI app:**
```bash
swiftlint lint fichero/fichero/
```

## Conventions

A few rules the codebase relies on:

- **OpenAPI is the contract.** The generated Swift client (`fichero/fichero-api-client/`) is never hand-edited — regenerate it from the engine schema after backend route/schema changes.
- **Observable data layer.** SwiftUI views observe `@Observable` domain stores; the store is the only thing that touches endpoints. Views render and collect input — they never call the API directly.
- **`verify_all` is the merge gate.** Lint + backend pytest + platform build/test legs. The manager runs `--full`; merge only on 0 failed.
- **Native, not web.** SwiftUI first, AppKit/UIKit bridges only where needed. Semantic system fonts and standard controls — no hardcoded `.system(size:)`.
- **Iterate, never replace.** Build on the existing code; no wholesale rewrites.
- **Per-agent commit attribution.** The author is the agent that wrote the code; the human directs and reviews.

## Releases

The release lane is documented in [docs/contributor/release/release-lane.md](docs/contributor/release/release-lane.md).
It covers the notarized DMG/Sparkle/GitHub path and the separate Mac TestFlight
archive/upload path. The wrapper script is:

```bash
scripts/release-all.sh --help
```

## Project Structure

- `fichero-server/`: the server (FastAPI), workflow runner, KG, ingest ([README](fichero-server/README.md))
- `fichero/`: SwiftUI app, Xcode project, and `fichero` CLI under `fichero-cli/src/fichero_cli/`
- `docs/`: published documentation site and contributor reference
