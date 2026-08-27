# Contributing

## License and the CLA

Fichero is released under the
[GNU Affero General Public License, version 3.0 (AGPL-3.0)](https://www.gnu.org/licenses/agpl-3.0.html).
Contributors agree to a [Contributor License Agreement](CLA.md) (CLA), which lets the
project also release Fichero under other terms (e.g. commercially) or when a channel requires it
(for example, distribution on the Mac App Store, whose rules the AGPL does not
fit). Your contribution always remains available under the AGPL. The Fichero
name may not be used to sell the app as-is.

Fichero is written by AI coding agents, which receive creative direction from Daniel Tubb.

The backlog lives in GitHub Issues and the project's working ledgers. Work
lands on lane branches (one worktree per lane); there are no per-task
branches.

## The worktree and worker workflow

The repository uses a manager-with-workers workflow.

- The **manager** agent coordinates. It picks the next batch of work,
  dispatches workers, reviews their output, runs the build and test
  gates, fixes what the merge surfaces, merges lanes into `integration`,
  and merges `integration` to `main` at release time.
- Each **worker** agent runs in its own git worktree under
  `~/code/fichero-worktrees/<name>`, works one focused lane (a feature, a
  fix batch, a research task), and commits as itself to its lane branch.
  Workers do not push and do not run the full merge gate (merged lane
  code is build-gated and fixed by the manager before it lands).
- **People** direct the work and review the result by using the app,
  then filing bug reports and feature requests.

Use `scripts/spawn-worker.sh` to create a worker. It fetches `origin`, creates a
worktree under `$FICHERO_WORKTREES` (by default a sibling `fichero-worktrees/`),
opens a detached tmux session, activates the shared virtual environment, and
starts the selected agent. The script branches from `origin/main` by default;
in practice, lane worktrees are usually branched off `integration`. Run
`scripts/spawn-worker.sh --help` for the supported agent commands (which
agents and models do the work is an implementation detail that changes over
time).

Workers report progress and blockers to the manager with
`scripts/notify_manager.sh`. Workers commit directly to their lane branch
and never push it. The manager runs the merge gate (build, test suites,
and every `scripts/check_*.py` guardrail) and merges the lane into
`integration`; `integration` merges to `main` at release time.

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

If you would like to contribute, open a pull request against
`integration` (the [CLA](CLA.md) applies, and the same merge gates run
on your change that run on every lane). Until an automated CLA check is
in place, state your agreement to the CLA in the pull-request
description. Bug reports and feature requests
are welcome as
[GitHub issues](https://github.com/dtubb/fichero/issues). The short
[Code of Conduct](CODE_OF_CONDUCT.md) applies everywhere in the project.

## Building from source (for developers)

Most people should just download the app (see [Installing and using
Fichero](README.md#installing-and-using-fichero)). This section is for working on
Fichero itself.

This is the canonical from-source setup. The subtree READMEs point here rather than
repeating it.

**0. Requirements.** Building the app needs a Mac on **macOS 26** with
**Xcode 26** (the deployment target is macOS 26.0 / iOS 26.5; there is no
back-deployment to older systems). For linting, `brew install swiftlint`.

**1. Install Python 3.12.** Briefcase pins 3.12 for the shipped app (many of the
engine's ML dependencies have no wheels for newer versions), so develop against 3.12.

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
dependency manifest: the runtime dependencies plus the optional extras `[dev]`,
`[kg]` and `[image]`. The only `requirements-*.txt` in the repo is
`requirements-docs.txt`, which builds this documentation site and nothing else.
**Briefcase is a build tool, not a runtime dependency**
(`fichero-server/scripts/build_backend_bundle.sh` uses it to package the engine into
the shipped app).

**4. Run the app.** Open `fichero/fichero.xcodeproj` in Xcode, pick a scheme,
and run. Schemes come in tiers (Dev, Alpha, Beta, Release) and two flavors:

- **Embedded** (e.g. "Fichero (Dev Embedded)"): the app spawns the engine
  itself; there is nothing to start by hand. This is the default development
  path.
- **Local** (e.g. "Fichero (Dev Local)", plus "Local iOS" variants): for
  engine development; the app connects to an engine you run yourself with
  `bash fichero-server/scripts/start_backend.sh`. When served over the
  network the engine speaks HTTPS on `127.0.0.1:8765` and the app pins the
  certificate fail-closed, so a plain-HTTP engine cannot connect. Never run
  a bare `uvicorn`.

**5. Engine-only work.** Every Python command needs
`PYTHONPATH=fichero-server/src` (with the venv from step 2 activated, so
`python` is the right one):

```bash
PYTHONPATH=fichero-server/src python -c "import fichero_server"
```

iPhone and iPad cannot embed the engine; they connect to one running on a Mac.

## Architecture

Fichero has two components. A front end and a back end. The front end is written in SwiftUI (the Fichero app), and the back end (the Engine) is a FastAPI server that holds the data and logic. The Fichero Mac, iPhone, and iPad apps share one SwiftUI codebase (and the CLI and MCP server are separate front ends) that connect to the Fichero Server and display what it returns. The Fichero Server is packaged using Briefcase and embedded in the Fichero app for release, but it can also run locally as a separate process or be shared on the network (a remote host), so the same clients work whether the engine is embedded, local, or remote. Clients connect over a Unix domain socket or pinned HTTPS (an in-process transport may come later); the same API rides both.

One engine, many clients:

```
SwiftUI app    fichero CLI    MCP server
       \           |            /
        \          |           /
      Unix domain socket (local)
    or HTTPS on 127.0.0.1:8765
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

## Lint and test

Back end (with the venv activated):

```bash
PYTHONPATH=fichero-server/src ruff check fichero-server/src/
PYTHONPATH=fichero-server/src pytest fichero-server/tests/unit/ --ignore=fichero-server/tests/unit/_archived
```

Front end:

```bash
swiftlint lint fichero/fichero/
```

Swift tests run from Xcode (the FicheroTests scheme) or via
`scripts/verify_all.sh`, which wraps lint, the backend suite, and the
platform build/test legs.

## Conventions

The canonical conventions live in [AGENTS.md](AGENTS.md) (repo-wide),
[fichero/AGENTS.md](fichero/AGENTS.md) (SwiftUI), and
[fichero-server/AGENTS.md](fichero-server/AGENTS.md) (engine). The rules the
codebase most relies on:

- **OpenAPI is the contract.** The generated Swift client (`fichero/fichero-api-client/`) is never hand-edited. After backend route/schema changes, regenerate with `./fichero-server/scripts/sync_openapi_schema.sh`.
- **Observable data layer.** SwiftUI views observe `@Observable` domain stores; the store is the only thing that touches endpoints. Views render and collect input (they never call the API directly).
- **`verify_all` is the merge gate.** Lint + backend pytest + platform build/test legs. The manager runs `--full`; merge only on 0 failed.
- **Native, not web.** SwiftUI first, AppKit/UIKit bridges only where needed. Semantic system fonts and standard controls (no hardcoded `.system(size:)`).
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
- `fichero/`: SwiftUI app and Xcode project
- `fichero-cli/`: the `fichero` command-line client ([README](fichero-cli/README.md))
- `fichero-mcp/`: the MCP server product ([README](fichero-mcp/README.md))
- `docs/`: published documentation site and contributor reference
- `scripts/`: build, release, worker, and guardrail (`check_*.py`) scripts
- `test-fixtures/`: shared test data
