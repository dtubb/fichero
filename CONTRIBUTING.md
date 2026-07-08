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

## More detail

See [AGENTS.md](AGENTS.md) for the operational manual (hard rules, commit
attribution, docs placement, worker orchestration). For SwiftUI-specific
guidance see [fichero/AGENTS.md](fichero/AGENTS.md) and for the Python engine see
[fichero-engine/AGENTS.md](fichero-engine/AGENTS.md). 

For the fuller repo
conventions, see
[docs/contributor/setup-and-contributing.md](docs/contributor/setup-and-contributing.md).
The [Developer Guide](docs/contributor/README.md) is the entry point for the whole
contributor manual: architecture, the OpenAPI contract, the action registry, the
security model, and the release lane.

If you would like to contribute to Fichero, please make a pull request. Outstanding Milestones and Issues that the Fichero Manager is working on are on GitHub. Milestones and Issues are coded by AI. The Forum is for people.

## Building from source (for developers)

Most people should just download the app (see [Installing and using
Fichero](#installing-and-using-fichero). This section is for working on
Fichero itself.

First, you’ll need to clone Fichero. Then create a virtual environment. Then install the fichero engine requirements.

Then start the Fichero engine on a local host. 

**Start fichero-engine** (serves HTTPS on `127.0.0.1:8765`; the app pins it fail-closed, so a plain-HTTP engine cannot connect):
```bash
bash fichero-engine/scripts/start_backend.sh
```

Then open `fichero/fichero.xcodeproj` in Xcode and run.

## Architecture

Fichero has two components. A front end and a back end. The front end is written in SwiftUI (the Fichero app), and the back end (the Engine) is a FastAPI server that holds the data and logic. The Fichero Mac, iPhone, and iPad apps share one SwiftUI codebase (and the CLI and MCP server are separate front ends) that connect to the Fichero Engine and display what it returns. The Fichero Engine is packaged using Briefcase and embedded in the Fichero app for release, but it can also run locally as a separate process or be shared on the network (a remote host), so the same clients work whether the engine is embedded, local, or remote.

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
        (fichero-engine/src/fichero)
           | DuckDB + LanceDB
           | workflows
           | knowledge graph
           | provider integrations
```

All surfaces sit on top of fichero-engine. They render and accept input; they do not contain logic.

| Surface | Path | Status |
|---|---|---|
| SwiftUI app (macOS, iOS, iPad) | `fichero/` (Xcode project: `fichero/fichero.xcodeproj`) | Live |
| `fichero` CLI | `fichero-engine/src/fichero/cli/` | Live (typed, end-to-end verified) |
| MCP server | `fichero-engine/src/fichero/mcp_server.py` (`fichero-mcp`) | Live |


**Use the CLI (against a running fichero-engine):**
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

- `fichero-engine/`: the server (FastAPI), workflow runner, KG, ingest ([README](fichero-engine/README.md))
- `fichero/`: SwiftUI app, Xcode project, and `fichero` CLI under `fichero-engine/src/fichero/cli/`
- `docs/`: published documentation site and contributor reference