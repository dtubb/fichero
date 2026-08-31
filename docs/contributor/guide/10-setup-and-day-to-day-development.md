# 10. Setup and Day-to-Day Development


### Requirements and setup

Building the app needs a Mac on **macOS 26** with **Xcode 26** (deployment target macOS 26.0 / iOS 26.5; no back-deployment). For linting, `brew install swiftlint`. Briefcase pins **Python 3.12** for the shipped app (many engine ML dependencies have no wheels for newer versions), so develop against 3.12:

    brew install python@3.12
    git clone https://github.com/dtubb/fichero.git
    cd fichero
    python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -e 'fichero-server[dev]'
    pip install pytest ruff

The last line is not optional: `pytest` and `ruff` are neither runtime dependencies nor part of the `[dev]` extra, but the lint and test commands assume both are on your `PATH`. There is **no** `requirements.txt` — `fichero-server/pyproject.toml` is the dependency manifest (runtime deps plus the `[dev]`, `[kg]`, `[image]` extras). Briefcase is a build tool, not a runtime dependency.

### Running the app

Open `fichero/fichero.xcodeproj`, pick a scheme, and run. Schemes come in tiers (Dev, Alpha, Beta, Release) and two flavors:

- **Embedded** (e.g. “Fichero (Dev Embedded)”) — the app spawns the engine itself; nothing to start by hand. This is the default development path and the standing run target. Stop any hand-started engine first: the spawn binds the same Unix socket path a `start_backend.sh` engine uses — two engines, one socket.
- **Local** (e.g. “Fichero (Dev Local)”, plus “Local iOS” variants) — for engine development; the app connects to an engine you run yourself with `bash fichero-server/scripts/start_backend.sh`. Over the network the engine speaks HTTPS on `127.0.0.1:8765` and the app pins the certificate fail-closed — a plain-HTTP engine cannot connect. Never run a bare `uvicorn`.

iPhone and iPad cannot embed the engine; they connect to one running on a Mac. For engine-only work, every Python command needs `PYTHONPATH=fichero-server/src` (with the venv activated):

    PYTHONPATH=fichero-server/src python -c "import fichero_server"

`start_backend.sh` defaults to `FICHERO_FEATURE_TIER=dev` so local testing shows staged surfaces; override with `FICHERO_FEATURE_TIER=release` when checking release-tier behavior. Core routes must work in `release` tier.

### Day-to-day commands

    # Backend lint + unit tests
    PYTHONPATH=fichero-server/src ruff check fichero-server/src/
    PYTHONPATH=fichero-server/src pytest fichero-server/tests/unit/ --ignore=fichero-server/tests/unit/_archived

    # Frontend lint
    swiftlint lint fichero/fichero/

    # OpenAPI sync after any backend API change
    ./fichero-server/scripts/sync_openapi_schema.sh

Swift tests run from Xcode (the FicheroTests scheme) or via `scripts/verify_all.sh`, which wraps lint, the backend suite, and the platform build/test legs.

Working in a git worktree? A worktree has no `.venv` of its own — activate the one from your main checkout, but keep `PYTHONPATH=fichero-server/src` **relative to the worktree**. The venv is an editable install pointing at the main checkout; without the worktree-relative path you lint and test the *other* tree and get a green run that means nothing.

### Verification tiers

`scripts/verify_all.sh` is the top-level verification entry point, tiered:

- `--fast` — Swift lint, backend `ruff`, the cheap `scripts/check_*.py` guardrails, the version-date check, and the OpenAPI model-sync validator.
- `--standard` — everything in `--fast` plus backend unit tests.
- `--full` — `--standard` plus the requested platform legs (`--macos` / `--ios`; both by default). The manager/integrator owns `--full`.

Workers verify their own diff (focused lint and tests, small isolated commits); the manager/integrator owns the Xcode build, the full `FicheroTests` run, and the cross-stack gate. `verify_all.sh` always writes `build/verify_all_report.json`, even on failure; `--file-issues` opts into filing follow-up GitHub issues from failures. `scripts/check_verify_all_modes.py` keeps the documented tiers from drifting. Parse the summary — merge only on **0 failed**.

### Contributing mechanics

- **New Swift files require registration.** The `Fichero` main target uses traditional PBX file references — a `.swift` file on disk is invisible to the compiler until you run `ruby scripts/add-swift-file.rb fichero/fichero/Views/MyFolder/MyView.swift`. Never edit `project.pbxproj` by hand. Test-target files are the exception (synchronized groups pick them up automatically).
- **No per-task branches.** Commit directly to the milestone/lane branch. Isolated worktrees live under `~/code/fichero-worktrees/<name>`.
- **Conventional commits with issue references**: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`, `style:` — e.g. `feat: add document tagging endpoint (#420)`. GitHub Issues + Milestones is the backlog’s source of truth.
- **Never push directly to** `main`**.** All work goes through a PR against `integration`; the same merge gates run on every change. Contributors agree to the CLA (state agreement in the PR description until the automated check lands).
- **0.0.x schema rule.** New columns declared on a Pydantic model are picked up by `_ensure_table` on fresh databases — no migration needed. But real persisted libraries need idempotent `ALTER`+backfill work in `db_migrations.py` for any column or structural change that must land against existing data. Never nuke or recreate a library database to fix a schema issue; treat every local DuckDB file as user data.
- **Iterate, never replace.** Build on the existing code; no wholesale rewrites. Fail loudly, never fall back silently: renames are atomic (new path only, every caller repointed in the same commit), no compatibility shims, no defaults that quietly substitute a different id or value.
- **Path-keyed guardrails move with the file.** A rename or move must update every `scripts/check_*.py` `TARGET_FILES`-style constant and allowlist in the same commit; grep for the old path across `scripts/` before committing.

### The two-stack habit

Before completing a backend route change, ask: does OpenAPI need updating? Do the generated Swift files need regenerating? Do frontend callers need updating? And when triaging a bug: engine bug or rendering bug? The typed `fichero` CLI mirrors every endpoint reachable from SwiftUI — reproduce against the CLI first; if it fails the same way, the engine owns it (chapter 12).
