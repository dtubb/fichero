(AI generated. Not reviewed.)

> **ARCHIVED 2026-06-27** — historical completed-work log for #1759 (CLOSED).
> The backend parity it describes shipped. Kept for provenance only.

# Notes + Annotations Audit (#1759)

## Scope

Backend-only audit and parity fix for add/delete/list of notes and annotations at:

- page scope
- folder scope

No Swift files were edited in this lane.

## What Existed Before

### Notes

- `POST /api/notes`, `GET /api/notes`, `GET /api/notes/{id}`, `PATCH /api/notes/{id}`, `DELETE /api/notes/{id}` already existed.
- Notes could reference documents indirectly through `linked_document_ids`.
- Page or folder scope was not explicit on the model or request/query surface.
- Delete by note id already worked.

### Annotations

- `POST /api/annotations`, `GET /api/annotations`, `GET /api/annotations/{id}`, `PATCH /api/annotations/{id}`, `DELETE /api/annotations/{id}` already existed.
- Annotation creation/listing was document-centric via `document_id`.
- Page annotations worked only implicitly when callers passed a page document id as `document_id`.
- Folder scope was not explicit or typed on the annotation model/API surface.
- Delete by annotation id already worked.

## Backend Changes Added

### Shared scope shape

Added explicit scope fields on both knowledge models:

- `page_id: str | None`
- `folder_id: str | None`

This keeps page/folder scope first-class instead of relying on ad hoc document-link conventions.

### Notes

Updated note create/list/patch handling to support:

- `page_id`
- `folder_id`

Behavior:

- page scope validates that the target document is a `DocType.page`
- folder scope validates that the target document is a `DocType.folder`
- scoped ids are merged into `linked_document_ids` for backward compatibility with existing note consumers
- list filters now accept `page_id` and `folder_id`

### Annotations

Updated annotation create/list/patch handling to support:

- `page_id`
- `folder_id`

Behavior:

- page scope validates `DocType.page` and normalizes `document_id = page_id`
- folder scope validates `DocType.folder`
- list filters now accept `page_id` and `folder_id`
- folder-scoped annotations remain add/list/delete capable, but crop/promote-to-claim now return a clear `400` because they do not have page content backing them

## CLI / Generated Surface

- Extended the custom `fichero notes` CLI commands to accept `--page` and `--folder`.
- Regenerated OpenAPI schema and generated CLI surface so annotation scope parameters are represented in the generated command layer too.

## Tests Added

Added backend unit coverage for:

- page-scoped note create/list/delete
- folder-scoped note create/list/delete
- page-scoped annotation create/list/delete
- folder-scoped annotation create/list/delete

## SwiftUI Follow-up

Frontend lane should:

- call the explicit `page_id` / `folder_id` API fields instead of inferring scope indirectly
- wire page/folder add/delete UI for both notes and annotations against the regenerated typed API surface
- decide whether folder-scoped annotations should expose crop/promote actions in UI; backend currently rejects those operations intentionally

## Audit Outcome

Backend parity now exists for:

- notes: add + list + delete at page scope and folder scope
- annotations: add + list + delete at page scope and folder scope
