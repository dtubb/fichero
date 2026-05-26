# sonnet branch — session-end status (2026-05-26)

All 6 queue items committed to `sonnet`; branch is clean, NOT yet merged (Daniel reviews).

- **#1248** (KG-write fix): extract_all now writes entity/claim rows correctly; root cause was a missing `_write_kg_rows` call on the two-stage path.
- **#1254/#1263** (guardrail + incremental KG): low-quality guardrail falls back to the configured larger model (not hardcoded); KG rows written per-file/page as each completes — partial runs leave partial KG instead of nothing.
- **#1249** (page-child claims in view): `/view/document/{id}` now unions parent + child page doc IDs when querying KnowledgeClaim, so claims stored on page children surface in the parent view.
- **#1252** (RTF strip): `_strip_rtf` state machine in document_loader guards against kreuzberg returning raw RTF markup for `.rtf` files; 11 unit tests including a real macOS clipboard sample.
- **#1251** (extract_all logging): start banner logs doc-id, text chars, record count, mode, provider/model; done log reports chunks → entities → KG rows; visible on both oneshot and two-stage paths.
- **#1237** (XLSX import): `xlsx_reader.py` (stdlib-only, no openpyxl) reads xlsx → list of row dicts with configurable `column_map` (by header name or column letter); `POST /api/ingest/xlsx` previews or creates Documents; 19 unit tests with in-memory fixture.

**Gotchas**: RTF `skip_until_depth` counter bug took two iterations (original decrement logic let body text leak). XLSX `_make_sheet` helper in tests uses a two-return-value tuple that callers must unpack correctly. OpenAPI sync was already wired into contracts — don't run `sync_openapi_schema.sh` from the worktree (no `.venv`), use the trunk venv path directly.
