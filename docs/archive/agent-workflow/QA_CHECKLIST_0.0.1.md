# Manual QA Checklist — Fichero 0.0.1

**Date:** _______________
**Tester:** _______________
**Build:** _______________
**Result:** PASS / FAIL

---

## Prerequisites

1. Build the app: `xcodebuild -project fichero/fichero.xcodeproj -scheme fichero -configuration Debug -sdk macosx build`
2. Start the backend: `PYTHONPATH=fichero-engine/src python -m fichero` (or however the server launches)
3. Launch the app from Xcode or the build output
4. Have a test PDF or DOCX file ready for ingest

---

## 1. Core App Launch

- [ ] App launches without crash
- [ ] Backend starts and is reachable at `localhost:8765`
- [ ] Sidebar loads and is visible
- [ ] No error dialogs or alerts on fresh launch

## 2. Backend Health

- [ ] `GET http://localhost:8765/health` returns 200
- [ ] `GET http://localhost:8765/stats` returns 200

## 3. Library Mode

- [ ] Library mode is visible in the sidebar
- [ ] Selecting Library shows the document browser
- [ ] Grid view renders correctly
- [ ] List view renders correctly
- [ ] Table view renders correctly
- [ ] Selecting a document opens its detail/inspector
- [ ] Document metadata displays correctly in inspector

## 4. Search Mode

- [ ] Search mode is visible in the sidebar
- [ ] Selecting Search shows the search interface
- [ ] Typing a query returns results (requires at least one ingested document)
- [ ] Search results display document titles and relevant info
- [ ] Selecting a search result navigates to the document

## 5. Ingest

- [ ] Can trigger document ingest (file import)
- [ ] PDF file ingests successfully
- [ ] Ingested document appears in the Library
- [ ] Ingested document is searchable

## 6. Folders

- [ ] Can create a new folder
- [ ] Can move a document into a folder
- [ ] Folder hierarchy displays correctly in sidebar/browser

## 7. Settings

- [ ] Settings panel is accessible
- [ ] Settings values persist after closing and reopening

## 8. Sidebar Navigation — Gated Surfaces Are Hidden

**All of the following must NOT be visible in the sidebar (default build, no env vars):**

- [ ] Chat is NOT visible
- [ ] Workflows is NOT visible
- [ ] Batches is NOT visible
- [ ] Automation is NOT visible
- [ ] Activity is NOT visible

## 9. Backend Route Gating (Default: `release` tier)

**Off-tier routes must return 404:**

- [ ] `GET /chat/...` returns 404
- [ ] `GET /workflows/...` returns 404
- [ ] `GET /workflow-execution/...` returns 404
- [ ] `GET /batch/...` returns 404
- [ ] `GET /activity/...` returns 404
- [ ] `GET /schedules/...` returns 404
- [ ] `GET /triggers/...` returns 404
- [ ] `GET /integrations/...` returns 404
- [ ] `GET /actions/...` returns 404
- [ ] `GET /mcp-servers/...` returns 404
- [ ] `GET /model-comparison/...` returns 404
- [ ] `GET /chains/...` returns 404
- [ ] `GET /local-models/...` returns 404

**Dev-tier routes must also be hidden at default tier:**

- [ ] `GET /providers/...` returns 404
- [ ] `GET /models/...` returns 404

## 10. Dev Tier — Provider Surface (env var override)

`FICHERO_FEATURE_TIER` only changes backend route availability. It does not expose hidden frontend UI by itself.

**Restart backend with `FICHERO_FEATURE_TIER=dev`:**

- [ ] `GET /providers/...` now returns 200
- [ ] `GET /models/...` now returns 200
- [ ] Off-tier routes (chat, workflows, etc.) still return 404

`FICHERO_ALL_FEATURES=1` only changes frontend feature visibility. It does not make backend-only routes available unless the backend is also running with `FICHERO_FEATURE_TIER=dev`.

**Restart frontend with `FICHERO_ALL_FEATURES=1`:**

- [ ] All sidebar modes become visible (Chat, Workflows, etc.)

---

## Notes

_Record any issues, unexpected behavior, or observations here:_

---

**Estimated time:** ~20–30 minutes
