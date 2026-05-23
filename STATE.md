# STATE.md — Fichero

## Snapshot

**Branch:** `0.0.2`

## Current Focus

1. Stabilize paleography/transcription workflow quality in small batches.
2. Improve KG visual rendering in SwiftUI so extracted content is legible and navigable.
3. Keep activity/workflow polling robust (`/api/activity` correctness under live UI polling).

## In Progress

- Workflow/model routing cleanup for transcription profiles and chainable stages (issue #1178).
- CLI verification harness for batched corpora checks under `/Users/danieltubb/Documents/5 Fichero` (issue #1177).
- KG sidebar/detail visual polish (entity row readability + OCR-garbage suppression in details/cards).

## Blocked

- OpenRouter weekly key quota can hard-stop remote vision/extraction runs (`403 Key limit exceeded`) on some libraries.
- Full `xcodebuild test -scheme Fichero` is long-running/noisy in this environment; targeted verification is passing, but full suite completion still needs a clean uninterrupted run.

## Next Session — Start Here

1. Re-run full Swift three-leg gate with correct scheme casing (`Fichero`): lint → build → full tests, capture final pass/fail.
2. Continue KG visual pass: claim/source panel readability and sidebar count/selection ergonomics.
3. Run 1–3-page CLI batches across Tiny/Small/Medium/Large sets and log quality notes into #1177.
4. Implement workflow profile/classifier routing scaffold from #1178 (`typescript/manuscript/HTR/paleography` + explicit human-choice state).
5. Commit/push in focused slices and keep issue threads updated with concrete run evidence.
