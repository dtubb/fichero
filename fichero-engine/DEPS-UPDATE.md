# Backend Python Dependency Update (#2248)

**Date:** 2026-06-14
**Branch:** `ms/deps-update`
**Worktree:** `~/code/fichero-worktrees/deps-update`
**Isolated venv:** `.venv-deps` (Python 3.12.13) — the shared
`~/code/fichero/.venv` was never touched.

## TL;DR

Moved `fichero-engine` to the latest mutually-compatible versions of every
dependency. **Zero source-code changes were required** — the latest resolvable
set is API-compatible with the current codebase. The only edits are
documentation comments in `pyproject.toml` clarifying the one deliberate pin.

- Full unit suite: **5031 passed, 22 skipped, 21 xfailed, 0 failed** in `.venv-deps`.
- `pip check`: **No broken requirements found.**
- One deliberate pin retained with a real, current reason: **`websockets<14`**.

## How "latest" is expressed

`pyproject.toml` deps are **unpinned** (they float), so "latest" is achieved at
install time by the resolver. There are no per-package version bumps to write —
a fresh `pip install -e ".[dev]"` already pulls the newest compatible release of
each package. The two existing version constraints are `websockets<14`
(deliberate, see below) and `Pillow>=12.2.0` (floor only — resolves to 12.2.0,
the latest).

Because nothing is pinned, the resolver always selects the maximum
mutually-compatible set. The held-back packages below are each capped by a
*transitive* dependency that is itself already at its latest version, so no
explicit pins are added (adding them would only make the manifest more brittle).

## Verification

```bash
# from the worktree root, using the ISOLATED venv
PYTHONPATH=fichero-engine/src .venv-deps/bin/pytest \
  fichero-engine/tests/unit/ --ignore=fichero-engine/tests/unit/_archived -q
# => 5031 passed, 22 skipped, 21 xfailed
.venv-deps/bin/pip check     # => No broken requirements found.
```

Note: the fresh venv needed the spaCy language models (`en_core_web_sm`,
`es_core_news_sm`) downloaded — these are model *data* packages, not part of the
dependency bump. Without them, 5 KG-NER tests fail with "Can't find model";
after `python -m spacy download …` they pass. The shared venv already had them.

## The one deliberate pin: `websockets<14`

This is the "real incompat forces a pin" case from the task.

- **Why:** uvicorn 0.49's `ws="auto"` still routes to the *legacy*
  `websockets_impl` (`uvicorn/protocols/websockets/auto.py` imports
  `WebSocketProtocol` from `websockets_impl`, **not** the newer
  `websockets_sansio_impl`). On `websockets>=14` that legacy path logs
  `websockets.legacy` deprecation noise on every connection.
- **Cost of holding it:** `langgraph-sdk>=0.4` requires `websockets>=14,<16`.
  Holding `websockets<14` therefore caps the LangChain/LangGraph chain at the
  latest releases whose `langgraph-sdk` is `<0.4`:
  - `langchain==1.3.2` (1.3.9 available, needs sdk 0.4)
  - `langgraph==1.2.2` (1.2.5 available, needs sdk 0.4)
  - `langgraph-sdk==0.3.15` (0.4.2 available, needs websockets>=14)
- **To unblock in future:** set the server's uvicorn option to
  `ws="websockets-sansio"` (the modern impl, no legacy logging), then drop the
  `websockets<14` pin. That lets websockets float to 15.x and the
  LangChain/LangGraph chain to the newest line. Deferred here because it is a
  server-launch code change, not a dependency bump, and the held-back releases
  are only patch-level.

## Packages capped by an already-latest transitive dependency

| Package | Resolved | Newer exists | Capped by |
|---|---|---|---|
| `langchain` | 1.3.2 | 1.3.9 | `websockets<14` → `langgraph-sdk<0.4` |
| `langgraph` | 1.2.2 | 1.2.5 | `websockets<14` → `langgraph-sdk<0.4` |
| `langgraph-sdk` | 0.3.15 | 0.4.2 | `websockets<14` (sdk 0.4 needs ws>=14) |
| `typer` | 0.25.1 | 0.26.7 | `huggingface-hub<0.26.0` (hf-hub already latest, 1.19.0) |
| `cohere` | 5.21.1 | 7.0.4 | `langchain-cohere>=5.18,<6.0` (lc-cohere already latest, 0.6.0) |
| `pydantic-core` | 2.46.4 | 2.47.0 | pinned `==` by `pydantic==2.13.4` (latest pydantic) |
| `websockets` | 13.1 | 16.0 | deliberate `websockets<14` pin (see above) |

## Notable version bumps (vs the live `~/code/fichero/.venv` baseline)

~44 packages moved forward, e.g.:

- `anthropic` 0.105.2 → 0.109.1
- `openai` 2.38.0 → 2.41.1
- `litellm` 1.86.2 → 1.89.0
- `langchain-core` 1.4.0 → 1.4.7
- `langchain-openai` 1.2.2 → 1.3.2
- `langchain-mcp-adapters` 0.2.2 → 0.3.0
- `langchain-cohere` 0.5.1 → 0.6.0
- `fastapi` 0.136.3 → 0.137.0
- `starlette` 1.2.0 → 1.3.1
- `uvicorn` 0.48.0 → 0.49.0
- `aiohttp` 3.13.5 → 3.14.1
- `cryptography` 48.0.0 → 49.0.0
- `huggingface-hub` 1.17.0 → 1.19.0
- `scikit-learn` 1.8.0 → 1.9.0
- `google-genai` 2.7.0 → 2.8.0
- `python-multipart` 0.0.29 → 0.0.32
- `lance-namespace` 0.7.7 → 0.8.6

Unchanged at their current latest: `duckdb` 1.5.3, `lancedb` 0.33.0,
`pydantic` 2.13.4, `mcp` 1.27.2, `spacy` 3.8.14, `splink` 4.0.16,
`pykeen` 1.11.1, `fastembed` 0.8.0, `rdflib` 7.6.0, `torch` 2.12.0,
`PyMuPDF` 1.27.2.3, `Pillow` 12.2.0, `numpy` 2.4.6.

## Code changes

- `fichero-engine/pyproject.toml` — refreshed the two `websockets<14` comments
  to document the current (uvicorn 0.49) rationale and the `langgraph-sdk>=0.4`
  conflict. No dependency lines added, removed, or version-pinned.

## On #2235 (LangGraph msgpack landmine)

Not resolved by this update and out of scope for a deps bump. LangGraph remains
on the 1.x line (1.2.2), where unregistered `fichero.models` types still
*warn* but do not block on checkpoint deserialization. The block lands in a
future LangGraph; the fix (register types / store primitives /
`LANGGRAPH_STRICT_MSGPACK=true` in CI) is tracked separately in #2235.
