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

### Phase 2 — shipped (2026-04-27)

Implemented in `0.0.2` rather than waiting for a follow-up release because the
brittleness of the V1 single-slot model was producing recurring bugs during
testing.

- Per-panel **edit-in-place** with auto-save (800ms debounce); RTF round-trip
  through `Components.Schemas.ArtifactUpdate.content` — typed field, not
  `additionalProperties` (see `docs/architecture/swiftui/api_client.md`).
- Per-panel **delete** with `confirmationDialog` and optimistic removal from
  the inspector list.
- Backend `GET /api/artifacts/document/{doc_id}` gained an
  `include_descendants: bool = True` query param. V2 passes `false` for strict
  per-document scope; V1's aggregating behavior (doc + page children + parent)
  stays as the default to avoid breaking the old inspector.
- Backend `PUT /api/artifacts/{artifact_id}` route added with
  `ArtifactUpdate { content?, reviewed? }`. Provider/model/version are
  immutable provenance, never overwritten by the editor.
- **Equal-divide layout**: 1 panel fills, 2 panels split half, 3 split third,
  etc. Wrapped in `ScrollView` only when `panelCount > 1` and the available
  height drops below the 200pt min.
- **Asymmetric horizontal padding**: `NSScrollView.contentInsets` carries
  `marginLeading: marginH, marginTrailing: 0` so the editor's right edge is
  flush with the panel — scroll bar no longer floats with empty pixels.
  `NSTextView.textContainerInset.width` stays 0 (it's symmetric).
- **Always-editable** panels (no edit-mode toggle). The trash and the
  spinner/check save indicator are visible at all times.
- **AppKit ruler + format strip** drives formatting: `usesRuler = true` +
  `rulersVisible = true` shows the `Styles / alignment / Spacing / Lists`
  segmented controls (this is `NSTextRulerView` — same thing Tinderbox
  uses; nothing custom).
- **View → Show / Hide Ruler** (⌃⌘R) toggles `editor.rulersVisible` AppStorage,
  which propagates to every editor in the inspector simultaneously.
- **View → Find in Artifact** (⌘F) sends `performFindPanelAction:` down the
  responder chain. The focused panel's `NSTextView` shows its inline find
  bar (because `usesFindBar = true`). It's per-artifact, distinct from
  app-wide search.
- `RichTextController` (small `ObservableObject` with a weak `NSTextView`
  ref) is wired through but currently unused — the AppKit ruler covers the
  format-bar need. Kept around for the future custom-attribute schema work.

### Phase 2 — deferred

- `notes` artifact type on the backend (still `page_content` + `metadata
  .page_content_rtf` for back-compat).
- Side-by-side comparison toggle.
- Remove the old `ContentTab`/`ContentState` and the typography-override
  branch in `AttributedTextEditor`.
- Promote V2 to default-on (currently `inspector_v2` flag, off by default).

### Phase 3 — 0.0.3: user-defined attribute schema (Daniel 2026-04-27)

The artifact-type system today is a flat string (`transcription`, `catalogue`,
`key_people`, etc.). The renderer guesses an icon from that string. There's
no concept of "what data shape does this artifact carry" — so the inspector
shows a single text panel for every type, even when the underlying data is
a list of names or a structured date.

Daniel's proposal: **a user-editable attribute schema in Settings.** Each
attribute defines:

- **Name** (e.g. `transcription`, `people`, `dates`, `signature`).
- **Payload type**: `rich_text` (RTF), `plain_text`, `list`, `date`, `boolean`,
  `scalar`, `svg`, `image`, `json`, …
- **Display widget**: how the inspector renders it. Derived from payload type
  by default; user can override (a `list` could render as comma-separated
  inline, or as a vertical bullet list, or as a tag cloud).
- **AI prompt template**: when a workflow tool emits this attribute, what
  prompt does the LLM run? What output format does it expect?
- **Canonical-form rules**: e.g. dates normalize via `dateutil.parse` then
  re-emit ISO-8601.

This makes the system end-to-end coherent:

1. User defines a `signature` attribute as `svg`.
2. AI tool registered to `signature` emits SVG.
3. Inspector renders the panel as an SVG preview, editable as text.
4. Future cross-document queries on `signature` know the schema.

Implementation outline (0.0.3):

- New backend table `attribute_schema(name, payload_type, widget, prompt,
  canonical_rules)` plus REST CRUD.
- Pydantic model + OpenAPI regen.
- `Artifact.payload_type` (or rather, derived from `artifact_type` →
  `attribute_schema.payload_type`) so existing artifacts get a shape without
  data migration.
- Inspector V2 panels render based on the resolved schema's widget.
- Settings → Attributes UI: list, add, edit, delete schema entries.

Out of scope for 0.0.2: the schema doesn't exist; V2 always treats artifact
content as RTF-or-plain text. Always-editable, no mode toggle. Remaining
issues become 0.0.3 problems.

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
