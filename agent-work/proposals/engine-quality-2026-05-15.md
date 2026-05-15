# Engine quality comparison — 2026-05-15 (loop #1)

**Library:** `~/Documents/Catalogue.fichero`
**Doc:** `00d0dfa689a34130860f41281f5ea330` — `fichero_upload_rgy9oy8u.pdf` (2-page student homework about reading abstracts; not Daniel's "Preface PDF" — only PDF in this library)
**Workflow:** `Catalogue` (`a46727d5c934402b8526eb58cd487c64`)
**Run:** `thread-eabd6fa3f2ab` — status `completed`

## What the engine produced

- `files-source`: 2 page docs emitted (Page 1, Page 2 — fan-out is correct).
- `transcribe`: 2 artifacts:
  - `257d80a1497e439c827f6df295fa229a` — `document_id=00d0dfa689…` (the **parent**), `provider="Apple"`, `model="Vision"`, `len=2087`.
  - `742cd959619b47a9a7477249e383c1a5` — `document_id=932b62b2…` (**Page 1**), `provider="apple"`, `model="apple-vision"`, `len=2052`.
- No `Extract All Entities` output. State has `branch:to:Extract All Entities: None`.
- No KG entities or claims produced.

## What the document actually says (direct read of the PDF)

Page 1 contains a student response with two questions: (1) what they learned reading abstracts (referencing two articles: *Japan's Forgotten Korean Forced Laborers* and *Centering Black Women's Labor History in Latin America*); (2) an abstract about domestic work in Mexico City and gender/class/migration. Page 2 appears blank (no text in the source).

## Findings

### F1 — Catalogue workflow stops after `transcribe`; entity extraction never runs (HIGH)

State shows `branch:to:Extract All Entities: None`. Status reports `completed`. Despite the workflow's name being **Catalogue**, no entities or claims were extracted, so the KG is empty for this document. Either the conditional branch is mis-wired, or it requires an upstream signal that `transcribe` doesn't emit. **The CLI cannot start the engine-quality comparison loop at all if the most-named workflow short-circuits before extraction.**

### F2 — Apple Vision transcription provider/model strings not normalised (MEDIUM)

The same tool produced two different `(provider, model)` tuples in the same run: `("Apple", "Vision")` and `("apple", "apple-vision")`. Provider/model names are part of the artifact's provenance and used for caching, deduplication, and display. Inconsistent strings break all three. Normalise at the writer.

### F3 — Duplicate transcription: parent + Page 1 both got transcribed (HIGH)

After #701/#891 the per-page model is supposed to attach transcription artifacts to page docs, not the parent. This run produced one artifact on the parent (`document_id=00d0dfa689…`) AND one on Page 1 (`document_id=932b62b2…`) with overlapping content. Either the parent shouldn't have been transcribed, or the per-page fan-out re-transcribed Page 1. Cache hit/miss logging would tell us which.

### F4 — Page 2 has no transcription artifact at all (LIKELY-BENIGN, VERIFY)

`/api/artifacts/document/510ce762…` returns only the parent artifact. Page 2's source text is blank in the PDF, so no artifact may be the right answer — but the workflow should still produce a "blank/skipped" record so the user can tell "no text" from "tool didn't run". Confirm with cache hit/miss instrumentation.

### F5 — Workflow run result reports `workflow_id: unknown` / `workflow_name: Unknown` (MEDIUM)

`fichero workflow run … --wait` returns a state where the workflow identity is lost. The thread checkpoint should preserve at least the workflow_id; the CLI should resolve the name. Diagnostics get harder when you can't tell which workflow produced a thread.

### F6 — CLI gap: no `fichero artifacts get <id>` command (MEDIUM)

Comparison-loop verification requires reading artifact content; the only way today is raw `curl` with the `X-Fichero-Library-Path` header. Add a typed `artifacts get` command to the CLI that prints `document_id / artifact_type / provider / model / version / content`.

### F7 — Stale workflow-state keys leak into CLI output (LOW)

`branch:to:Extract All Entities`, `__pregel_tasks`, `parallel_results` all surface to the user. These are LangGraph internals — filter them in the CLI's render path the same way the SwiftUI activity log filters internal node names (`feedback_langgraph_node_display`).

## Recommendations

- F1 is a **release-blocker for "Catalogue is a working workflow."** Investigate `Extract All Entities` branch wiring first thing. If the branch needs `transcribe` to emit a particular signal, document it; if it's a missing edge, add the edge.
- F3 is **important for cache hygiene** — a duplicate transcription means we paid the OCR cost twice. Likely caused by one of: parent-as-input still wired in `Catalogue.json`; per-page fan-out re-running OCR on already-transcribed pages; cache lookup keyed on the wrong (provider, model) pair (see F2).
- F2 should be a one-liner in `process_vision`'s artifact writer.
- F5/F6/F7 are CLI/UX polish but compound — without them the loop is hard to drive.
