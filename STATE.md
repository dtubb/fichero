# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

1. Stabilize paleography/transcription workflow quality in small batches.
2. Improve KG visual rendering in SwiftUI so extracted content is legible and navigable.
3. Keep activity/workflow polling robust (`/api/activity` correctness under live UI polling).

## In Progress

- Image pipeline improvements (#1176: non-destructive parametric pipeline + transient cache).
- CLI verification harness for batched corpora checks (#1177).
- KG sidebar/detail visual polish (entity row readability + OCR-garbage suppression, #1168).
- RAG-assisted transcription review (#1179: query LanceDB reference corpus in Pass 2).
- Verification gate tasks #253/#254/#255/#256 (verify_python.sh → CrossLanguageGateTests → verify_all.sh → docs).
- Baseline cleanup #257 (stale test updates) + #258 (3 real route 500s).

## Blocked

- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.
- Full `xcodebuild test -scheme Fichero` still needs a clean uninterrupted run.

## Next Session — Start Here

1. **Build is green** (commit `6b6273e1`): entity claim count badges + WorkflowEdge routeKey/routeMap sync are shipped.
2. **KG visual polish** (#1168): entity row readability and OCR-garbage suppression are next in the KG browser — check the issue for specifics.
3. **RAG transcription review** (#1179): design `vector_search` node or `reference` port on `transcribe_review` to inject period vocabulary from LanceDB.
4. **Verification gate** (#253–#256): `verify_python.sh` → `CrossLanguageGateTests.swift` → `verify_all.sh` — pick up from task #253.
5. Backend tests baseline: 2926 passed, 21 skipped, 21 xfailed — healthy.
