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
- KG sidebar/detail visual polish (entity row readability + OCR-garbage suppression).
- RAG-assisted transcription review (#1179: query LanceDB reference corpus in Pass 2).

## Blocked

- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.
- Full `xcodebuild test -scheme Fichero` still needs a clean uninterrupted run.

## Next Session — Start Here

1. **Paleography + image pipeline**: continue #1176 (non-destructive image pipeline) and #1175 (stageable chains A/B/C). Two-pass HTR/paleography presets are live — test on a real folder.
2. **Classify-then-route**: build the "Transcribe (Auto-Detect)" workflow — `files → classify_script → [route to appropriate transcription profile]`. The `classify_script` tool is registered; needs a routing/conditional node wired up.
3. **RAG reference corpus** (#1179): design the `vector_search` node or a `reference` port on `transcribe_review` to inject period vocabulary from LanceDB.
4. **Haggard PDF**: still worth reading pages 40–108 (Chapters III–IV: Procedure + Special Aids for abbreviation glossaries) to enrich the prompts further.
5. Backend tests: 2909 passing, 21 skipped, 21 xfailed — baseline is healthy.
