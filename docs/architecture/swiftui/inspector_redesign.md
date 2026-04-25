# Document Inspector Redesign — Tinderbox-style "Display Attributes + Artifact Panels"

**Status:** Design + Phase 1 implementation in progress.
**Date:** 2026-04-25.
**Trigger:** Repeated brittle bugs in the single-content `DocumentInspectorContentTab` (RTF bold loss, save races, "modifying state during view update" warnings on font-size change, transcription clobbering user edits).

## Why the current design fails

`DocumentInspectorContentTab.swift` is 299 lines of state management for displaying **one** text. `DocumentInspectorContentState.swift` adds 144 lines of similar logic. Together they manage:

- A `draftAttributedText` representing what the user is editing.
- An `originalPlainContent` and `originalRTFBase64` to detect changes.
- A `pendingExternalSignature` to defer reloads while the user is typing.
- A `lastLoadedSignature` to avoid no-op reloads.
- A `lastSavedPayloadSignature` so the auto-save doesn't fight itself.
- An `editorRevision` integer to force `NSTextView.setAttributedString` re-application.
- An `isApplyingModelUpdate` flag in the Coordinator to break delegate-callback feedback.
- Debounce loops for auto-save.
- A separate refresh path triggered by `executionObserver.fileCompletedCount` storms.
- RTF round-tripping through metadata-stored base64.
- A `normalizeForEditor` pass that's been rewritten three times because each version stripped some user formatting.
- A typography-change branch that overwrites `.font` across the whole text storage and writes back to the `@Binding` — the source of the "Modifying state during view update" warning.

Every one of these exists because the current model jams **multiple distinct concepts** (transcription output, catalogue output, user notes, future workflow artifacts) into a **single mutable text slot** (`page_content`). When the slot is shared, every writer has to fight every other writer, and every re-render has to detect "did someone else clobber what I'm editing?"

The bold-loss bug is one symptom. The "modifying state during view update" warning is another. There will be more — they're inevitable consequences of the shared-slot model.

## What Tinderbox does

A Tinderbox note's right pane is laid out as:

1. **Title** at top.
2. **Display Attributes** — a compact strip of key-value pairs (e.g. `Container`, `Tags`, `TitleLevel`). Read-only by default; clicking a value opens an editor.
3. **Body text** — the actual prose / content of the note. Single editable area.
4. **Inbound Links / Outbound Links / Suggested** — three columns at the bottom.

Two design choices matter for us:

- **Attributes are visually distinct from body.** The user always knows whether they're editing an attribute or the body. They never compete.
- **Adding a new attribute or link doesn't affect the body.** Whatever the user is typing in the body survives any concurrent attribute change. There is no "did the workflow rewrite my prose?" race.

## Proposed Fichero design

```
┌──────────────────────────────────────────────────┐
│ [Info icon] [Content icon]                        │  ← existing tab bar
├──────────────────────────────────────────────────┤
│ Status         Completed                         │
│ Kind           Image (JPG)                       │  ← Display Attributes strip
│ Ingest mode    LINK                              │     (compact, read-mostly)
│ Created        Apr 23, 2026                      │
│ Last edited    1 day ago                         │
├──────────────────────────────────────────────────┤
│ ▼ Notes (your edits, RTF)                        │
│   [editable text view — bold, italic, lists]     │
│                                                   │
├──────────────────────────────────────────────────┤
│ ▼ Transcription · qwen3-vl-32b · 1 min ago       │
│   algumas familias de apellido Mina; envíele…    │  ← read-only artifact panel
│                                                   │
├──────────────────────────────────────────────────┤
│ ▼ Catalogue · DashScope · 5 min ago              │  ← another panel, same shape
│   ## People                                       │
│   ## Dates                                        │
│   ## Rivers                                       │
└──────────────────────────────────────────────────┘
```

### Properties

1. **Each panel is independent.** It owns its own state. No shared draft. No cross-panel signatures.
2. **Notes is editable. Workflow artifacts are read-only.** Bold/italic/lists belong to Notes only. There's no need for an RTF round-trip on workflow output — workflow output is what the model emitted.
3. **A new artifact never replaces an old one.** It appears as an additional panel. The user can collapse panels they don't want to see, or pin one they care about.
4. **Multiple panels can be shown side-by-side.** A second-level toolbar lets the user split a panel into two columns (compare two transcription runs from different models, e.g. Apple Vision vs Qwen) or three.
5. **Display Attributes are computed from `document` + `metadata`.** They don't take user edits in V1 — read-only. (V2 may allow editing specific attributes.)
6. **No `page_content` field on the wire for the inspector.** Notes round-trip as their own artifact (`artifact_type="notes"`, `provider="user"`, `model="user"`). `page_content` is kept on the Document model for backward-compat with workflows that read it (Catalogue, search indexing) but the inspector no longer touches it directly.

### Rich text — where it lives

The current attempt to round-trip RTF through `metadata["page_content_rtf"]` works at the wire but is fragile to display. In the new design:

- **Notes panel** is a `NotesArtifact` with content stored as RTF data (or HTML or Markdown — pick one). On save, the panel writes a single artifact row. On load, it decodes that artifact's content. No metadata key collision, no overlap with `page_content`, no normalize/typography overrides.
- **Workflow artifacts** stay plain text (or whatever the tool emitted). We don't try to make them rich.

This means **the bold bug stops mattering** for workflow output — which is most of the content — because workflow output isn't styled. Bold only matters for user notes, where the editor is the single source of truth and there's no second writer.

### Performance

Loading 10 panels is cheaper than the current single-panel logic, because:
- Each panel reads one artifact row directly. No `page_content` + RTF metadata combo.
- No signature recomputation on every diff.
- No debounce loop tuning per workflow.
- No `editorRevision` integer dance.

A 100-file workflow run that fires 100 `file_completed` events used to trigger 100 inspector re-renders (debounced to 1 every 500ms). In the new design, only the **artifact list reload** runs in response — and the user's Notes panel is unaffected because it's decoupled.

## Phased implementation

### Phase 1 — this session

Goal: add the new layout *behind a feature flag* so the old `ContentTab` continues to work for users who haven't opted in. Phase 1 is read-only — no save changes yet.

Files added (target: under 100 lines each):
- `Views/Library/DocumentInspector/V2/ArtifactPanel.swift` — read-only display of one artifact.
- `Views/Library/DocumentInspector/V2/DisplayAttributesStrip.swift` — top key-value strip.
- `Views/Library/DocumentInspector/V2/DocumentInspectorContentV2.swift` — orchestration (loads artifacts + page_content, lays out panels).
- `Views/Library/DocumentInspector/V2/ArtifactPanelHeader.swift` — small subview.

Wiring:
- New feature flag `inspector_v2` on `FeatureManager` — default off.
- `DocumentInspector.documentDetail` switches between old `DocumentInspectorContentTab` and new `DocumentInspectorContentV2` based on the flag.

Out of scope this phase:
- Editing Notes via the new panel — V1 shows the existing `page_content` rich text inside one of the panels (read-only) so users can verify the layout works.
- Side-by-side multi-column.
- Notes-as-artifact migration.
- Removing the old code.

### Phase 2 — later

- Add a `notes` artifact type on the backend.
- Migrate existing `page_content` + `page_content_rtf` data into a `notes` artifact per document.
- Make the V2 Notes panel editable (single source of truth: the artifact row).
- Side-by-side comparison toggle.
- Remove the old `ContentTab`, `ContentState`, `AttributedTextEditor` typography-override branch.
- Promote V2 to default-on.

### Phase 3 — much later

- User-configurable Display Attributes (which keys show in the strip).
- Per-panel actions (copy, export, regenerate).
- Drag a panel out into a separate window (Tinderbox-like).

## Backward compatibility

- Existing data unchanged: `page_content`, `metadata.page_content_rtf`, all artifact rows continue to work.
- Old inspector still functional behind the flag.
- No backend schema changes in Phase 1.
- No openapi changes in Phase 1.
- Phase 2 adds a `notes` artifact type but doesn't remove existing fields.

## Risks and trade-offs

- **Two parallel inspector implementations during Phase 1–2.** Maintenance cost is real but bounded — old code is frozen, no new features go in.
- **Users may want bold/italic in workflow artifact panels too** (e.g. to highlight an entity). Solution: V3 adds a Notes-on-Artifact pattern (a sub-artifact for user annotations of a specific output). Out of Phase 1.
- **The "Notes is just an artifact" framing leaks state into the artifacts API.** Mitigation: filter `notes`-type artifacts out of "Workflow Artifacts" listings; treat them as a first-class user concept in the UI.
