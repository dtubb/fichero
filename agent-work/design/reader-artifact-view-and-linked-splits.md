# Reader: an artifact view, and linked side-by-side readers

**Status:** ruled by Daniel 2026-08-30 (afternoon), design queued — next
reader lane. Screenshot evidence: a Marshall "table" artifact rendering as
RAW pipe-text in the reader (the table renderer that landed 2026-08-30
overnight did not engage for it — first bug to chase).

## The ruling (paraphrased)

1. The reader needs an ARTIFACT view: pick any artifact of the scope and see
   it rendered — the extract-CSV as a real table, a translation as prose.
   (The `?representation=` switcher exists; it offers type families, not the
   full artifact list. The artifact view is "show me THIS artifact".)
2. Two readers side by side — transcript left, translation right — using the
   existing reader split. Each split pane needs its OWN representation/
   artifact choice (today the lens is per-window state).
3. Linked by default: unpinned panes follow the same selection/page
   together, so paging the transcript pages the translation. A PINNED pane
   detaches (the pin already means exactly this elsewhere — same grammar).

## What already exists to build on

- Reader splits: SplittablePane covers the two-pane layout; per-pane pin
  state exists in the preview surfaces (mirror it in reader panes).
- `/view/document?representation=` + `table_payload()` (csv/json_rows/
  markdown branches) render tables; `ReaderRepresentation.tableTypes`
  gates the switcher.
- Bug found 2026-08-30: a pipe-markdown "table" artifact reached the
  reader as raw text (screenshot, Marshall calendar page). Check
  table_payload's markdown branch vs this artifact's actual type/content.

## Sketch

- Per-pane representation state: move the lens selection from window state
  onto the split-pane identity (the storageKey the split coordinator
  already mints), so left=transcript right=translation persists.
- The lens menu grows an "Artifacts…" section listing the scope's
  artifacts by display name (WorkflowStore.workflowStepCache names them);
  choosing one renders it via the same WebKit path with an
  `?artifact_id=` filter (engine: representation lookup by id — small
  addition to /view/document).
- Linkage: unpinned reader panes share the existing selection seam
  (they already follow selection); pinning freezes a pane's document,
  which the pin already does. Verify paging propagates.
