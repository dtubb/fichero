FEATURE AUDIT — Fichero Library View Surface — 2026-03-15
Issue: #114 ([QA] Library View Surface Audit)

## Frontend (SwiftUI Library View)

| Feature | Status | Tests | Notes |
|---|---|---|---|
| Document List Rendering (Icon/Grid) | Working | Untested | LazyVGrid with zoom scaling (0.5–3.0x) |
| Document List Rendering (List) | Working | Untested | Mail-style compact rows, LazyVStack |
| Document List Rendering (Table) | Working | Untested | 9 configurable columns, native SwiftUI Table |
| Document List Rendering (Map) | Working | Untested | Tinderbox-style draggable canvas cards |
| Document Selection (single) | Working | Untested | Click replaces selection |
| Document Selection (multi) | Working | Untested | Cmd+click toggle, Shift+click range, anchor-based |
| Inspector Updates on Selection | Working | Untested | Reactive binding; 4 tabs (Content, Info, Metadata, Artifacts) |
| Inspector Empty State | Working | Untested | "No Selection" message with helper text |
| Search/Filter in Library | Working | Untested | Name + content + status search; feature-flagged filter toolbar |
| Sorting | Working | Untested | 5 fields (name, created, updated, type, status); per-folder persistence |
| Import: File Dialog | Working | Untested | fileImporter for .package type |
| Import: External Drag-Drop | Working | Untested | Global .dropDestination on window, progress overlay |
| Import: Progress Feedback | Working | Untested | Modal ProgressView with file name |
| Drag-Drop (Within Library) | Partial | Untested | Documents are .draggable but library view has NO drop target |
| Drag-Drop (Sidebar Reorg) | Working | Untested | Sidebar accepts drops for folder reorganization |
| Error States (Mutations) | Partial | Untested | Delete/rename errors caught; logged to console, not user-facing |
| Error States (Connection/API) | Not Started | Untested | No connection error UI despite DocumentStore having isConnected |
| Empty State | Working | Untested | "No Documents" with conditional subtitle |
| Inline Editing (Rename) | Working | Untested | Context menu → TextField with Enter/Escape handling |
| Keyboard: Arrow Navigation | Working | Untested | Up/Down/Left/Right + PageUp/PageDown |
| Keyboard: Type-to-Select | Working | Untested | Alphanumeric prefix matching with 500ms timeout |
| Keyboard: Delete | Working | Untested | Confirmation dialog with count-aware message |
| Keyboard: Return/Space | Working | Untested | Open in inspector / QuickLook toggle |
| Keyboard: Cmd+A | Working | Untested | Select all visible documents |
| Keyboard: Cmd+F | Working | Untested | Toggle filter bar |
| Keyboard: Zoom (Cmd+/-) | Working | Untested | Icon/map view zoom |
| Batch: Delete Selected | Working | Untested | Confirmation → batch delete with per-item error handling |
| Batch: Run Workflow | Working | Untested | WorkflowPickerSheet → batch execution via batchService |
| Batch: Tag/Move/Copy | Not Started | N/A | No implementation exists |
| Column Configuration | Working | Untested | 9 columns, visibility toggles persisted via @AppStorage |
| Size Column Data | Partial | Untested | Hardcoded "-" — file size not populated |

## Backend (Python API)

| Feature | Status | Tests | Notes |
|---|---|---|---|
| Document CRUD (list/get/create/update/delete) | Working | Tested | Full coverage; cascade delete verified |
| Document Hierarchy (children/ancestors) | Working | Partial | Children tested; ancestors untested |
| Document Collections/Roots | Working | Partial | Collections tested; roots redundant endpoint |
| Document Move/Reorder | Working | Untested | Move endpoint validates parent existence |
| Orphan Cleanup | Working | Tested | Depth-first graph traversal |
| Search (semantic/fulltext/hybrid) | Working | Tested | All 3 types tested; Pandas fulltext may not scale |
| Search Stats | Working | Tested | Embedding statistics |
| Search Reindex | Working | Untested | Background task, no task ID returned |
| Search Embed Single Doc | Working | Untested | Only embeds if content ≥ 10 chars |
| Saved Searches (CRUD) | Working | Untested | Full CRUD + duplicate + reorder |
| File Ingest (single) | Working | Module tested | Synchronous; supports LINK/COPY modes |
| Folder Ingest | Working | Module tested | Async background task; in-memory task tracking |
| Ingest Status | Working | Untested | Task data lost on server restart |
| Storage: Thumbnails | Working | Untested | Lazy generation, 1-day cache |
| Storage: Display Images | Working | Untested | Larger than thumbnail |
| Folder Organization | Working | Untested | Virtual folders; entity-type agnostic |
| Artifacts | Working | Untested | Per-document listing with pagination |
| API Contracts | Working | Tested | 13 contract tests verify schema alignment |
| Feature Gating | Working | Tested | Clean release/dev tier split |
| Document Import (multipart) | Working | Untested | File upload → ingest pipeline |

## Test Coverage Summary

| Layer | Total Tests | Library-Related | Coverage |
|---|---|---|---|
| Swift Unit | 24 | 14 (LibraryManager) | Library CRUD: 100%, UI: 0% |
| Python Unit | 681 | ~60 (doc CRUD, db, ingest) | Backend CRUD: 90%, Search: partial |
| Python Integration | 143 | ~24 (ingest, contracts) | Ingest: 95%, contracts: good |
| Swift UI Tests | 2 | 0 | 0% — launch tests only |

## SUMMARY

- **Working:** 26 / 32 features
- **Partial:** 4 / 32 (drag-drop in library, error states, batch ops, size column)
- **Not Started:** 2 / 32 (connection error UI, batch tag/move/copy)
- **Has tests:** ~10 / 32 (backend only; zero Swift UI tests for library features)

## Priority Fixes

1. **Connection/API error state UI** — DocumentStore has `isConnected` and `error` but LibraryView never reads them. Users get a blank view on backend failure.
2. **Size column stub** — Table view Size column shows "-" instead of file size. Data exists in ingest metadata.
3. **Error handling UX** — Mutation errors (delete, rename) log to console via `print()` instead of using ErrorService for user-facing alerts.

## RECOMMENDED NEXT STEPS

1. Add connection error banner in LibraryView when `documentStore.isConnected == false` or `documentStore.error != nil`
2. Populate Size column from document metadata (file_size field from ingest)
3. Replace `print()` error logging with `ErrorService.shared.reportError()` in rename/delete handlers
4. Add Swift UI tests for inspector text edit/save/revert flow (QA checklist item 2.5)
5. Add drop target to library view for document reorganization (currently sidebar-only)
6. Consider expanding batch operations (tag, move) based on user priority
