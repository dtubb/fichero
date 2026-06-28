# Capture Smoke Matrix

Purpose: manual smoke coverage for `#2355` across mobile capture, reconnect upload, watched-folder / DSLR intake, provenance fields, citation fields, and launch-without-backend behavior.

Use this alongside [VIEW_QA_MATRIX.md](./VIEW_QA_MATRIX.md) when validating capture and intake flows before release or after regressions in mobile / import surfaces.

## Reporting Format
- Prefix each note with `[DANIEL]` or `[CODEX]`.
- For each failure record:
  - surface
  - device or host
  - exact action
  - expected result
  - actual result
  - whether the backend was reachable at launch
  - whether the document later produced provenance or citation rows

## Preconditions
- [ ] At least one iPhone or iPad is available for capture testing.
- [ ] A host Mac is available for watched-folder or DSLR intake coverage.
- [ ] One test destination can start with the backend unreachable at launch.
- [ ] One test document set is prepared for provenance/citation validation after ingest.

## Matrix

| Surface | Scenario | Steps | Expected Result | Evidence To Record |
| --- | --- | --- | --- | --- |
| iPhone / iPad | Offline photo capture | Launch app with network/backend unavailable, capture one photo, leave it queued locally | Capture succeeds without crash, item remains pending instead of disappearing, UI explains queued/offline state | Device model, OS version, queued item state, any error text |
| iPhone / iPad | Reconnect upload after offline capture | Restore network/backend, reopen or foreground app, allow sync to resume | Queued photo uploads automatically or with one obvious retry, no duplicate document is created | Time-to-upload, final document count, any manual retry needed |
| iPhone / iPad | No backend at launch | Cold-launch with backend unreachable | App shows the intended connection/offline affordance instead of an empty library or crash | First visible screen, exact copy, whether capture remains accessible |
| iPhone / iPad | Foreground resume after reconnect | While app is backgrounded, restore backend reachability and return to app | App reconnects cleanly and clears stale offline state | Whether reconnect was automatic, any stale banner or stuck spinner |
| Watched Folder | Folder intake | Drop one supported file into the watched folder while the host app/backend is running | File is imported once, appears in the intended library/folder, no duplicate import loop occurs | Host path used, imported document name, duplicate count |
| DSLR / Card Import | New image intake | Copy or ingest a DSLR-originated image into the watched intake path | Large-image ingest succeeds, thumbnail/preview loads, metadata-sensitive path does not stall | File type, size, whether preview/thumbnail rendered |
| Provenance | Workflow provenance fields | Open the imported/captured document and inspect the workflow/info surfaces | Workflow provenance rows identify capture/import path and run metadata clearly enough to trace origin | Screens visited, fields present, missing fields if any |
| Citations | Citation extraction fields | Run or inspect a document expected to yield citations, then open citation detail/inspector | Citation text, page/label, detector, confidence, and related fields appear where expected | Which citation fields were populated or missing |
| Cross-surface | Capture-to-library continuity | From capture/import, navigate to the resulting library item, preview it, and inspect metadata | The same document is reachable end to end with stable identity and no “lost after upload” behavior | Document name/id if visible, any mismatch between capture and library entry |

## Focused Smoke Runs

### Mobile Offline Capture
- [ ] Launch iPhone/iPad app with backend unreachable.
- [ ] Capture at least one photo.
- [ ] Confirm the app stays stable and the capture is visibly queued.
- [ ] Restore backend/network reachability.
- [ ] Confirm upload resumes and the document becomes readable in the library.

### Watched Folder / DSLR Intake
- [ ] Start the Mac host with backend reachable.
- [ ] Add one ordinary image and one DSLR-style image through the watched-folder path.
- [ ] Confirm both appear once, with previews.
- [ ] Confirm there is no duplicate or looping import behavior.

### Provenance / Citation Verification
- [ ] Open at least one newly captured or imported document.
- [ ] Inspect Info / provenance-related surfaces for workflow or origin metadata.
- [ ] Inspect Citations if the test document should produce them.
- [ ] Record any missing page labels, detector names, confidence values, or source linkage.

## Expected Result
- [ ] Mobile capture works when offline, then uploads after reconnect without data loss or duplicates.
- [ ] Launch without a backend shows a stable no-backend path rather than crashing or dropping the user into a broken library state.
- [ ] Watched-folder and DSLR intake import documents exactly once and render previews successfully.
- [ ] Provenance and citation fields are present and useful enough to trace how the document entered the system.
