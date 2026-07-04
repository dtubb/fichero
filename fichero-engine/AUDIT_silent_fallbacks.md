# Silent Fallback Audit

Scoped modules audited:

- `src/fichero/export_service.py`
- `src/fichero/discovery.py`
- `src/fichero/library_paths.py`
- `src/fichero/api/routes/library_registry.py`
- `src/fichero/api/routes/canvas.py`
- `src/fichero/api/routes/export.py`
- `src/fichero/api/auth.py`
- `src/fichero/api/routes/tasks.py`

Findings:

- `src/fichero/api/routes/library_registry.py:66-79` — `_document_count()` catches any exception from opening/querying a library and returns `0`. That silently rewrites “library unreadable / db broken / path wrong” into “empty library”, which makes the Unicode-collision report lie about package contents. Fix: log the exception with the package path and either raise so the collision scan fails loudly, or surface an explicit error field instead of a fake count.
- `src/fichero/export_service.py:693-696` — `_eleventy_page_link()` falls back to raw document text when `found_in_page_id` is missing from `page_paths_by_id`. That silently downgrades a broken provenance link into plain text, so the export looks valid while the knowledge page lost navigation. Fix: raise or at least log loudly with the offending record/document id before rendering.
- `src/fichero/export_service.py:760-762` — `_eleventy_search_entries()` silently skips documents whose page path was never generated. That produces a partial static search index with no signal that exported documents disappeared from search. Fix: raise or log an error keyed by document id/name when a document is in `documents` but absent from `page_paths_by_id`.
- `src/fichero/export_service.py:1361-1371` — `_copy_document_assets()` returns `[]` when an image document’s source cannot be resolved. That silently turns an image export into a text-only page with no asset and no warning. Fix: for declared image docs, log loudly or raise when `get_display()/resolve_source()` cannot find a real file.
- `src/fichero/export_service.py:1374-1382` — `_docx_image_source()` returns `None` on missing/bad image source, so Word export quietly omits the image instead of surfacing broken library state. Fix: treat missing files for `FileType.image` as an explicit export error, or at minimum log a warning with document id/path.
- `src/fichero/api/auth.py:285-300` — `actor_from_request()` falls back to `"system"` whenever middleware did not populate `request.state.user`. For user-initiated audited writes, that silently rewrites attribution from a real actor to a synthetic system actor, which is exactly the kind of silent substitution the audit layer should reject. Fix: in request-bound action paths, raise or log an error when neither authenticated user nor an explicit bootstrap/system marker is present.
- `src/fichero/api/routes/tasks.py:394-402` — `get_task_result()` returns HTTP 200 with `null` when a task exists but has not produced a result yet. That silently substitutes “no result yet” for a successful empty payload and makes clients guess whether the task is pending, running, or malformed. Fix: return `409`/`202` with explicit task state, or include a loud status wrapper instead of bare `null`.
- `src/fichero/api/routes/tasks.py:483-488` and `src/fichero/api/routes/tasks.py:677-685` — the metrics result endpoints use `details.get(..., 0/{})` defaults even after asserting the task completed successfully. If the worker stored malformed/incomplete `details`, the API silently fabricates zero counts and empty maps instead of exposing a broken task result. Fix: validate required keys and raise/log when a “successful” task result is structurally incomplete.

No findings worth filing in this pass:

- `src/fichero/discovery.py` — optional-startup fallbacks are warning-logged rather than silent.
- `src/fichero/library_paths.py` — normalization helper is direct, no fallback path.
- `src/fichero/api/routes/canvas.py` — skipped items are returned and warning-logged, not silently dropped.
- `src/fichero/api/routes/export.py` — error mapping is broad, but not a silent substitution in the `#2430` class.
