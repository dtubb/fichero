# Library View Backend Perf Notes

## What I checked

The library view repeatedly hits three backend paths:

- `GET /api/documents`
- `GET /api/documents/{doc_id}/children`
- `GET /api/storage/thumbnail/{doc_id}`

I added lightweight timing logs around those hot paths so the backend now emits one-line `PERF ...` entries with request shape, row counts, cache state, and wall-clock time.

## Findings

- The document list and children endpoints were not the primary regression in this pass. On a local synthetic library with 300 children under one parent, both routes stayed in the ~15 ms range.
- The thumbnail path was the more meaningful cost center. There was already a legacy on-disk thumbnail alias (`{doc_id}.jpg`), so thumbnails were not being regenerated on every single request, but the cache had two gaps:
  - no versioned cache key tied to source `mtime`, so cache state was opaque
  - no instrumentation to tell cache hit from regenerate/miss
- That opacity matches Daniel's report: the UI can issue a burst of thumbnail requests, cancel some of them, and the backend had no clear way to show whether those were cheap cache hits or expensive renders.

## Changes

- Added `fichero.perf.perf_span()` and wired it into:
  - `library.list_documents`
  - `library.get_children`
  - `library.thumbnail.endpoint`
  - `library.thumbnail.ensure`
- Reworked thumbnail caching to use a versioned disk key:
  - `{doc_id}__{width}x{height}__{source_mtime_ns}.jpg`
- Kept the legacy `{doc_id}.jpg` file as an alias to the active cache entry so existing behavior and tests stay intact.
- On cache lookup:
  - current versioned file is an immediate hit
  - a fresh legacy alias is promoted into the versioned cache
  - stale variants for the same document are removed after regeneration
- Updated orphan cleanup so versioned cache files still map back to the owning document id.

## Local numbers

Measured with a local synthetic test library and `TestClient`:

- `GET /api/documents?parent_id=...`: `14.58 ms`
- `GET /api/documents/{doc_id}/children`: `15.79 ms`
- First `GET /api/storage/thumbnail/{doc_id}`: `44.00 ms`
- Second `GET /api/storage/thumbnail/{doc_id}`: `4.51 ms`

That puts the warm thumbnail path at about a 10x improvement versus the cold render in this local measurement.

## How to read the logs

Examples:

```text
PERF library.list_documents duration_ms=14.58 filters=parent_id matched_rows=300 returned_rows=300
PERF library.get_children doc_id=... duration_ms=15.79 matched_rows=300 returned_rows=300
PERF library.thumbnail.ensure cache_state=miss doc_id=... duration_ms=39.11 source_mtime_ns=...
PERF library.thumbnail.endpoint cache_state=generated doc_id=... duration_ms=44.00 thumbnail_path=...
PERF library.thumbnail.endpoint cache_state=hit doc_id=... duration_ms=4.51 thumbnail_path=...
```

`cache_state=hit` means the request stayed on disk. `generated` means the endpoint had to render a new thumbnail first.
