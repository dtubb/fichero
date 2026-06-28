## 2026-06-28

- Expanded `docs/api-reference/index.md` with grounded path-level callouts for:
  `/api/bookmarks`,
  `/api/bookmarks/{bookmark_id}/resolve`,
  `/api/search/saved`,
  `/api/search/saved/{search_id}`,
  `/api/search/saved/{search_id}/duplicate`,
  and `/api/search/saved/reorder`.
- Verified method, purpose, and request/response shapes against
  `fichero-engine/src/fichero/api/routes/bookmarks.py`,
  `fichero-engine/src/fichero/api/routes/search.py`, and the committed
  `fichero-engine/tests/contracts/openapi.json`.
- Removed the now-documented bookmark and saved-search paths from
  `docs/api-reference/path_allowlist.json` so the docs-drift guard measures
  fewer real gaps.
- Ran:
  `PYTHONPATH=fichero-engine/src pytest fichero-engine/tests/contracts/test_docs_coverage.py -q`
  -> `1 passed`
- Ran:
  `~/.venv/bin/mkdocs build --strict`
  -> passed
