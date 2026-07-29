# CLI / MCP test wiring — findings for the manager

Date: 2026-07-29 · Lane: docs + CLI/MCP test suites (#4227) · Worker: Claude Fable 5

New test dirs added this pass: `fichero-cli/tests/` (52 tests) and
`fichero-mcp/tests/` (33 tests). Both are standalone-runnable —
`pytest fichero-cli/tests -q` with **no** `PYTHONPATH` works, because each
`conftest.py` prepends the sibling `src/` trees to `sys.path` (the same seam
`fichero-server/tests/conftest.py` already uses).

## 1. The gates will NOT pick these up (needs a manager decision)

Every gate names `fichero-server/tests/` **explicitly** — there is no directory
discovery to inherit from:

| Gate | Line | What it runs |
|---|---|---|
| `scripts/verify_all.sh` (`run_standard`) | ~357 | `pytest -rf fichero-server/tests/unit/ --ignore=…/_archived` |
| `scripts/verify_all.sh` (`run_standard`) | ~363 | `pytest -rf fichero-server/tests/contracts/` |
| `scripts/verify_python.sh` | step 2 | `pytest fichero-server/tests/unit/ -q -k "not embedding"` |

So `fichero-cli/tests` and `fichero-mcp/tests` are currently **uncovered by the
merge gate**. I did not edit the gate scripts (out of lane). Two options:

- **A (recommended, smallest diff):** add the two paths to the existing pytest
  invocation in `run_standard` and to `verify_python.sh` step 2 —
  `pytest -rf fichero-server/tests/unit/ fichero-cli/tests fichero-mcp/tests`.
  One process, ~13s added, and both conftests are import-safe alongside the
  server suite (they only prepend `sys.path` entries the gate already exports).
  Verified: `pytest fichero-server/tests/unit/cli fichero-server/tests/unit/mcp
  fichero-cli/tests fichero-mcp/tests` → **459 passed, 1 skipped** in one
  process, no conftest collision.
- **B:** move the files under `fichero-server/tests/unit/cli/` and `…/mcp/`,
  where sibling coverage already lives, and keep the product trees test-free.
  This contradicts "each product owns its tests", but needs no script change.

Note there is no root `pytest.ini`/`pyproject.toml`, so a bare `pytest` from the
repo root does not discover anything by config — every path is spelled out.

## 2. `scripts/verify_python.sh` step 5 "cli --help" is broken by the rename

```bash
run "cli --help" "$PY" -m fichero --help
```

`python -m fichero` from the repo root now fails with *"'fichero' is a package
and cannot be directly executed"*: the old `fichero` Python package is gone, so
the name resolves to the `fichero/` **Swift app directory** as a namespace
package. Correct form: `-m fichero_cli`. (Verified by running it; this leg has
been red since #4227's phase 1.) Not fixed here — `scripts/` is another lane's
file.

## 3. Product-code observations (not fixed — filing candidates)

- **`fichero_mcp.full` has no tool descriptions at all.** All 26 tools on that
  surface come back with `description=None` (no docstrings in `full.py`), so an
  MCP client shows a model nothing to choose by. It also has **no console entry
  point** in `fichero-mcp/pyproject.toml` (only `fichero-mcp` → `server:main`
  and `fichero-mcp-simple` → `simple:main`), so it may be a legacy surface:
  either give it docstrings or delete it. `test_tool_registry.py` therefore
  holds only the two shipped surfaces to the description contract, and states
  why in a comment.
- **`docs list` (human path) bypasses `_report_fichero_error`.** In
  `fichero-cli/src/fichero_cli/__main__.py` the non-`--json` branch catches
  `FicheroError` itself and prints `str(exc)`, so a 401 there loses the
  "run `fichero auth login`" hint that every `_invoke`-based command gives. It
  still exits 1 and prints the 401, so this is a UX inconsistency, not a silent
  failure. Pinned as current behavior in
  `fichero-cli/tests/test_cli_server_unreachable.py`.
- **No UDS client transport in `FicheroClient`.** `engine_manager.start` can
  *launch* the server on a Unix-domain socket (`FICHERO_UDS_PATH` →
  `uvicorn fichero_server.api.uds_transport:app --uds`), but the CLI and MCP
  products always dial an HTTP(S) `base_url`. The UDS *client* lives in the
  Swift app. Worth knowing before anyone writes a doc claiming the CLI can talk
  to a sandboxed embedded server over its socket.
- **`docs/contributor/architecture/fichero-server/mcp_simple_interface.md`
  describes a `fichero-mcp` product but sits under the server's architecture
  folder.** Left in place: moving it churns `mkdocs.yml` nav / the docs
  publication allowlist. A later docs-IA pass could relocate it alongside a nav
  update.

## 4. Pre-existing red, unrelated to this pass

`scripts/check_docs_paths.py` exits 1 on `main` with ~8 MISSING test-file paths
named in docs (`fichero-server/tests/unit/test_canonical_knowledge_routes.py`,
`test_check_duplicate_paths.py`, `test_fold_endpoints_validation.py`,
`test_mind_palace_route_guard.py`, …) plus one stale allowlist entry
(`knowledge/test_svo_cleanup.py`, which exists again). Verified identical
before and after my edits, so this pass neither caused nor fixed it.
