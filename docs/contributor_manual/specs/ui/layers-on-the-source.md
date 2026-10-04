# Layers on the source: translation, entities, statements, notes — Design Spec

> Milestone: TBD (proposed: `layers-on-the-source`; until then the work lives on the issues cited per behaviour)
> Manual: TBD — the user manual needs a section, "What is drawn on a page", explaining the layers
> (boxes, text, translation, names, statements, notes and the rest), how to turn each on or off,
> what a dashed versus a solid mark means (a model's versus a person's), and that the same layers
> appear in Preview, the Reader's lines mode and on a canvas card.

> Design-led (Testing Constitution). **Status: DRAFT** (2026-10-04), written from the code at
> `lane/lead` 658b398de. The maintainer ruled on its six questions on 2026-10-04 (see "Ruled
> 2026-10-04" below): build all of it, in the slices of the Plan.
> Tags: **[OK]** behaves this way today · **[PARTIAL]** part built or not wired · **[BROKEN]** the
> code contradicts the line · **[GAP]** intended, not built. Every non-[OK] line cites an issue.

## Intent (the design)

The maintainer asked whether Preview could show translations well, and show which parts of a
source are entities and which statements (subject–verb–object claims) come from it. Two
additions followed: the same layers must appear on a page shown on the 2D and 3D canvases, and
notes anchored to a page, region, line or span are a layer too.

So this spec defines **one layer model** that any page surface draws. A layer is a named kind of
thing that sits on a page: segment boxes, inline text, a translation, where an entity is named,
which statements a passage supports, notes, and so on. Each layer is read from the engine against
a page and resolves to a **segment** (a region, line or word, with its shape) or a **span** (a
stretch of characters in one named reading of a segment). Every page surface draws the same
layers from the same read: **Preview** (`ZoomableImagePreviewMac`, `DocumentOverlay`), the
**Reader's lines mode** (#5414, not built), and a page card on the **2D canvas**
(`CanvasOrtho2DRenderer`) and the **3D canvas** (`CanvasScene3DRenderer`). A surface draws the
layers; it never owns their data.

What this spec does not do: it does not merge surfaces. **Preview, Reader and Inspector are three
surfaces and never merge** (`preview-surface.md`, `reader-view.md`, `PaneContentPlan.Plan`'s doc
comment). A layer marks a place on the page; the detail behind a mark (an entity's card, a
statement's text and its review) stays in the Inspector, reached by selecting the mark.

**Rulings honoured, not restated:**
- `source/segment-editor.md` `source.editor.two-switches` (ruled 2026-09-27): the view switches
  are layers, the image and the overlays each on or off, with workspace defaults. This spec
  extends that list; it adds no second switch mechanism.
- #5414: a Reader lines mode (each line's image above its editable text) and a Preview
  double-click popover that uses the same view as one row of that mode. #5411: inline text
  follows the line's direction and fits its box.
- Language rules: a machine's claim is recorded as a model's; a model never curates; a person
  decides (`kg-tables.md` `kg.entity.says-who-made-it`, `hermeneutic-layer.md`
  `kg.claim.provenance-kind-is-server-stated`).
- Where a mark draws when the image is cropped or turned is owned by
  `reader-overlay-frame-identity.md`; what an annotation is, by `reading-markup-annotations.md`;
  pointing at a segment or span, by `source/segments-and-geometry.md` (`source.point.*`,
  `source.statement.*`). Cited, not re-specified.

## Prior art

- **IIIF Presentation 3 and W3C Web Annotation.** A page (Canvas) carries annotation pages, each a
  list of annotations whose target is the canvas with a selector (`#xywh`, an SVG selector, or a
  text-position selector). Viewers such as Mirador show each annotation page as a layer to turn
  on or off. Fichero's `SourceAnchor` (`models/anchors.py:366`) already holds the same parts (a
  rectangle or polygon, `char_start`/`char_end`, the `segment_id` and the `representation_id` the
  span was measured on), and annotations already export as W3C JSON-LD. We adopt the shape: one
  layer is one annotation page per page per kind.
- **TEI.** Translations aligned to the original by `@corresp` on lines or `<linkGrp>`; names by
  `<persName>`/`<placeName>` with `@ref` to an authority; editorial facts by
  `<unclear>`/`<supplied>`/`<gap>`/`<del>`. Our readings of kind `translation`, entity links and
  editorial facts are the same ideas, kept as records rather than markup.
- **eScriptorium and Transkribus** show transcription layers over the line polygons and a
  line-by-line text view; **Recogito** tags named entities on both the text and the image, with a
  verified or unverified state on each tag. We follow Recogito's pattern for entities: the tag sits
  on the text and the image, and its state is visible.
- **The factoid model** (prosopography): a statement is attached to the passage that supports it.
  That is `source.statement.on-segment`.

## Behaviours

### A. One layer model, every page surface

- `layers.model.one-read` — **[GAP]** (#5418) the layers for a page come from one engine read
  that returns, per layer, the items on that page with their anchor (segment id with its live
  shape, or segment id plus reading id plus character span) and their state (who made it,
  curation state). Every surface draws from that read. Today each overlay is gathered separately
  in Swift (`ZoomableImagePreviewMac+Regions.swift:33-66` builds `DocumentOverlay` from boxes,
  annotations and marquees), and there is no engine read for layers.
- `layers.anchor.most-precise` — **[GAP]** (#5418) a mark sits on the most precise anchor its
  item has, on this ladder, finest first:
  1. **stroke**: a path inside a segment (`SourceAnchor` shapes, `models/anchors.py:366-447`);
  2. **character**: a span in a named reading (`segment_id`, `representation_id`,
     `char_start`/`char_end`), or a character segment;
  3. **word**: a word segment;
  4. **line**: a line segment;
  5. **paragraph or region**: a region segment;
  6. **page**: the page, with no place on it.
  **Fallback:** when a rung cannot be resolved now, the mark drops to the next rung that can,
  and the hover says so ("placed on its line; the exact words were not found"). A span whose
  reading has changed is carried over only by matching its characters, else reported as unplaced
  (`replace_stretch`, `readings.py:637-692`); a deleted segment is drawn at its stored shape
  through the one resolver (`source.point.anchor-names-its-segment`). A position is never guessed.
  Today items reach different rungs (see the inventory below): entities stop at the page,
  statements at a page-text span with no segment.
- `layers.preview.draws-today` — **[OK]** Preview draws four layers today from one
  `DocumentOverlay` value through one AppKit `DocumentOverlayView`: segment boxes and shapes (with
  OCR confidence as stroke opacity and dashing, `DocumentOverlayView.swift:216-240`), regions,
  annotation marks by kind (`AnnotationMarkRendering.swift`) and inline text; the image itself is
  a fifth switch. Pinned for the boxes: `ImportedPageDrawsItsBoxesTests`
  (`fichero/Tests/Unit/general/Models/ImportedPageDrawsItsBoxesTests.swift`).
- `layers.reader.lines-mode-draws-layers` — **[GAP]** (#5414) in the Reader's lines mode, each
  line's image strip carries the same layers as Preview (the line's box, its entity and statement
  marks, its notes), and the text under the strip carries the span layers. The Preview
  double-click popover is the same row view, so it carries them too.
- `layers.canvas2d.page-card-draws-layers` — **[GAP]** (#4931, #3105) a page card on the 2D
  canvas draws the layers that are on, over the page image. Today a card is a flat plane whose
  material is swapped for the page thumbnail at `.thumbnail` tier
  (`CanvasOrtho2DRenderer.swift:356-376`, `2D/...+Thumbnails.swift:22-40`); the `.fullTexture`
  tier is declared (`Engine/CanvasDetailTier.swift:17,36`) and used by no renderer; a card holds
  only its source id and a texture, so it has no page geometry to draw on. Needed: a card at full
  detail reads the page's layers (the same read as `layers.model.one-read`) and draws them as
  child entities or into its texture, positioned through the image frame the anchor was measured
  on.
- `layers.canvas3d.page-card-draws-layers` — **[GAP]** (#4192) the same for the 3D canvas
  (`CanvasSpaceView` / `CanvasScene3DRenderer.swift:290-306`, thumbnails at
  `3D/...+Thumbnails.swift:32-47`), which today draws a thumbnail and nothing on it. Both
  canvases are RealityKit; #4192's SceneKit wording for 2D is superseded in the code
  (`CanvasOrtho2DRenderer.swift:20-23`, "2D stays RealityKit").
- `layers.text.font-from-script-and-period` — **[GAP]** (#5438) transcription text (inline on the
  image, in the lines mode, in text panes; never the app's own chrome, which keeps semantic system
  fonts) is drawn in the font setup derived for the library's script and period: Junicode for
  medieval Latin (MUFI letters, long s), a Noto face for a script macOS lacks. Each pane's What to
  show menu can change it, and the choice is remembered per library. It is the per-script `font`
  fact of `source/languages-scripts-signs.md` `source.fonts.per-script` ([GAP], #5210), defaulted
  at setup. **Today:** `GET /api/recipes/derived` names a bundled font per script
  (`recipes/derived.py`, `FONT_SCRIPTS`), but none for Latin (`_SYSTEM_DRAWS`), with no period
  input, and stores nothing (no `font` fact exists in the engine). Bundled, each SIL OFL 1.1 with
  its licence text and `resources/fonts/PROVENANCE.md`: Junicode and Noto Sans Syriac (with
  Western and Eastern), Mongolian, Coptic and Cherokee, Regular weight only
  (`api/routes/system/fonts.py`; `source.fonts.bundled`, [PARTIAL], #5206). The inline text on the
  image is drawn in `NSFont.systemFont` (`Regions/DocumentOverlayView.swift:351,354`), outside the
  `BundledFonts` cascade the Inspector and labels already use.

**Box colours** are owned by `source/segment-editor.md`, "Box colour and the segment hierarchy"
(ruled 2026-10-04, #5426, #5463). A box's colour is its region's hue, shaded along the working
pass's reading order, and a child is drawn as its parent's child. The earlier proposal here, a
pane menu choosing among reading order, region, who made it and confidence, is withdrawn: who made
a box and how sure it is stay as its stroke (`layers.state.drawn`), not its colour.

- `layers.spread.show-one-page` — **[GAP]** (#5427) a Preview pane can show a two-page photograph
  whole, or only its left or right page, by cropping the view to that page's region; no record
  changes. This is the alternative to the gutter split, which makes child page documents. Every
  layer still draws on its ink through the crop (`reader-overlay-frame-identity.md`). **The crop
  has no source today:** `split_pages` (`workflows/tools/split_pages.py`) finds Apple Vision's
  document outline and each page's box, but stores a page's box only when it cuts, as a child
  document's `region_in_parent` (`persist_workflow_child_regions`, :155-158); a proposed split (an
  unclear gutter) or a cover keeps its boxes only in the run's output, and the four-corner outline
  is not stored as geometry (`source/image-preparation.md` `prep.find-the-page`, [PARTIAL],
  #5382). **Engine work:** finding the pages stores each page's region on the photograph as a
  segment of granularity `page`, with its decision and confidence, and the outline as geometry,
  without cutting; making child documents stays a separate step.
- `layers.text.follows-line-direction` — **[GAP]** (#5411) any layer that draws text on the page
  (inline text, a translation, a name label) is laid out in its line's direction and fitted to the
  line's box. Today `InlineWords.draw` is always horizontal from `rect.minX`
  (`Regions/DocumentOverlayView.swift:349-358`) and only the hover label follows direction
  (`OCRGeometryOverlay.swift:139-150`, via `SegmentStore.direction(of:)`).

### B. Translation as a layer

- `layers.translation.engine-holds-a-line-translation` — **[OK]** a segment can hold readings of
  kind `translation` (`models/readings.py:57-74`; `ContentRepresentationKind.translation`,
  `models/__init__.py:870-891`), each with `language`, `script`, its producer (`producer_model`,
  `producer_tool`, `created_by`, `provenance_kind`) and the reading it was made from
  (`derived_from_representation_id`). `GET /api/segments/{id}/readings?kind=translation` lists
  them; `GET /api/segments/document/{id}/text?kind=translation` builds a page's translation from
  each line's counting translation. See `source/readings-and-apparatus.md` `source.reading.kinds`,
  `source.reading.read-from` (both [OK], #4934).
- `layers.translation.which-counts` — **[OK]** the translation that counts for a line is a
  person's choice, one per segment per kind, so choosing a transcription never changes which
  translation counts (`ReadingChoice`, `readings.py:194-224`; the `reading.choose` action refuses a
  machine actor through `_assert_a_person`, `content_representations.py:676-730`). With no choice,
  the counting reading is worked out by the project rule (`source.reading.chosen-is-worked-out`,
  [OK], #4934).
- `layers.translation.chosen-per-pane` — **[GAP]** (#2093) each Preview pane chooses, in its own
  "What to show" menu, which text it draws inline: a transcription, another transcription, or a
  translation (one text per pane, so texts never overprint). A window can hold three Previews side
  by side (the image; the original transcription with the image off; the translation), or several
  transcriptions and a translation. A line with no reading of the chosen kind shows nothing, not
  another text in its place. Today Preview's inline text is the OCR box text only
  (`OCRGeometryOverlay.swift:117`) and never a translation; per-pane storage already exists
  (`layers.toggle.remembered-per-pane`).
- `layers.translation.lines-mode-shows-several` — **[GAP]** (#5414) the Reader's lines mode can show
  more than one text under each line's image (for example the transcription, then the
  translation), each labelled by its kind and language, in the order chosen in its menu.
- `layers.translation.model-makes-one-per-line` — **[GAP]** (#3325) a model translates as a job,
  line by line: the recipe job `translate-transliterate-normalise` (`recipes/jobs.py:114-116`,
  line readings in, line readings out) writes one `translation` reading per line, made from that
  line's counting transcription, recorded as the model's. Today the job has no entry in
  `WORKFLOW_FOR_JOB` (`recipes/start.py:20-28`), so nothing runs it, and every translator that does
  run (`translate`, `text_translate`, `artifact.translate`) writes one document-level `Artifact`
  of type `translation` (`workflows/tools/translate.py:138`, `artifacts.py:1277`), never a
  reading.
- `layers.translation.document-artifacts-still-shown` — **[PARTIAL]** (#2093) the immersive
  Reader already shows a document's translation artifacts by language, with a Source/language
  picker and the label "AI translation · unreviewed"
  (`Views/Reader/Page/Immersive/ImmersiveReaderView+Translations.swift:9-35`,
  `TranslationRep.swift`). That is a whole-document text, so it cannot sit on a line; it stays as
  it is until per-line readings exist, and is not drawn as a layer.
- `layers.translation.person-types-one` — **[GAP]** (#5414) a person can type a line's
  translation in the lines mode (a second field under the transcription when the layer is on). It
  is saved as a person's reading of kind `translation`, through the same save action as a
  transcription edit (one code path, `source/line-editor.md` `source.lineeditor.strip`, #5209).
- `layers.translation.target-direction` — **[GAP]** (#4938) a translation is drawn in its own
  language's script and direction, not the source line's: an English translation of a vertical
  Chinese line reads left to right under (or beside) the column. Today a reading has `language`
  and `script` but no `direction` (`models/__init__.py:914-915`), and `resolve_direction`
  (`llm/language_policy.py:974`) has a reading rung that nothing can fill; the page-text read
  calls it without a reading (`segment_readings.py:968-979`). Needed: the direction of a reading
  is worked out from its script (the cascade in `source/languages-scripts-signs.md`).

### C. Entities on the source

- `layers.entities.engine-knows-where-a-name-is` — **[GAP]** (#4932, #1659) each mention of an
  entity is stored with its place: a supporting source on the entity whose `SourceAnchor` names
  the segment and, when known, the reading and character span. Today an entity records only the
  documents or pages it came from (`source_document_ids`, `models/knowledge.py:866`); its
  `source_supports` is never written (the only appends are for claims, `_entity_writer.py:1611`,
  `claim/curation.py:339`); spaCy's `start_char`/`end_char` (`knowledge/spacy_ner.py:444-469`,
  first occurrence only) are dropped by its callers (`extract_entities_only.py:413-425`,
  `workflows/tools/entities.py:242-248`). A typed `names` link from a segment to an entity exists
  (`models/typed_links.py:169-189`, read by `GET /api/links/naming`), but only a person makes one
  by hand. **Engine work:** the extractor writes one support per mention, with segment id, reading
  id and span, recorded as the model's.
- `layers.entities.read-per-segment` — **[PARTIAL]** (#4932) `GET /api/segments/{id}/statements`
  returns, for one segment, the entities one of whose supporting sources names it
  (`MentionOnSegment`, `segment_readings.py:1365-1420`), and the Inspector's Statements section
  reads it (`InspectorStatementsSection.swift:50`). Because nothing writes those supports (above),
  it is empty for extracted entities. The layer needs the same answer for a whole page in one read
  (`layers.model.one-read`).
- `layers.entities.shown-on-text-and-image` — **[GAP]** (#1659) with the Names layer on, a mention
  anchored to a span is underlined in the text (Reader lines mode, inline text) and its line's box
  carries a light wash on the image; a mention anchored to a segment only washes that segment.
  The mark's colour follows the entity type; its stroke follows its state
  (`layers.state.drawn`).
- `layers.entities.hover-and-click` — **[GAP]** (#1659) hovering a mark names the entity, its type
  and its state. Clicking it selects the entity: the Inspector shows the existing entity card
  (`Views/Inspector/Knowledge/EntityDigestView.swift`), whose sources list the other places it is
  named (`GET /api/entities/{id}/documents`). The click does not move Preview or the Reader.

### D. Statements from the source

- `layers.statements.anchored-to-a-passage` — **[PARTIAL]** (#4932) an extracted claim stores a
  character span (`source_char_start`/`end`) in the page excerpt the extractor was given, a quoted
  `source_excerpt`, and a rectangle only when the model supplied one
  (`workflows/tools/extractors.py:2636-2670`); its anchor never carries a segment id or the reading
  the span was measured on, and `source_segment_id` is a legacy field that is not a segment
  (`source.statement.old-segment-field-left-alone`). So a statement can be found on its page by
  offsets or by searching its excerpt (`PageContentClaimSourceHighlight.match`,
  `DocumentTextReader.swift:34-89`), not on a line. **Engine work:** the extractor fills the
  anchor's `segment_id` and `representation_id` (`source.statement.on-segment`, [GAP], #4932).
- `layers.statements.which-lines-carry-them` — **[GAP]** (#4932) with the Statements layer on,
  each line that supports at least one statement is marked on the image and in the lines mode,
  with the count. Selecting the line shows its statements in the Inspector's existing Statements
  section (`source.statement.both-ways`, [GAP], #4932); the passage a selected statement rests on
  is highlighted, through the one location resolver already used by the claim reveal
  (`POST /api/locations/resolve`, `LocationService.swift:25`; `kg.read.span-reuses-existing-location-resolver`,
  [BROKEN], #4834).
- `layers.statements.confirm-or-reject-from-the-passage` — **[GAP]** (#4834) from a statement shown
  for a selected line, a person can confirm or reject it. It goes through the existing audited,
  undoable action `claim.transition` (`claim/curation.py:1456`) or `claim.batch_transition` for
  several; no second path.
- `layers.statements.only-a-person-curates` — **[GAP]** (#5416) `claim.transition` refuses a
  machine actor, as `reading.choose` does (`_assert_a_person`). Today its request defaults
  `reviewed_by` to `"human"` (`claim/curation.py:49-57`) and no refusal of a machine actor was
  found, so a model calling it would be recorded as a person's review.

### E. Trust state, one rule for every layer

- `layers.state.recorded` — **[OK]** each item says who made it: claims carry `created_by`
  (`"extractor"` for extracted ones), `provenance_kind`, `provider`, `model`
  (`_entity_writer.py:2575-2583`), `curation_state` (unreviewed, shortlisted, curated, rejected) and
  `epistemic_status`; entities carry `curation_state` (unreviewed, verified, rejected, merged) and an
  `attribution_chain`; readings carry `provenance_kind` and their producer. Pinned for entities:
  `kg.entity.says-who-made-it` ([OK], `kg-tables.md`).
- `layers.state.drawn` — **[GAP]** (#5417) every knowledge layer draws state the same way: a
  model's item is dashed until a person confirms it, solid once confirmed (or when a person made
  it), and hidden once rejected. The hover says it in words ("Proposed by <model>, not reviewed").

### F. Notes as a layer

- `layers.notes.marks-drawn` — **[OK]** annotations (highlight, note, rating, bookmark, comment,
  line, underline, strikethrough) are drawn on the page by kind
  (`Views/Preview/ImageViewer/AnnotationMarkRendering.swift`), anchored to a span (`targets[]`,
  segment plus character range in its counting reading, `models/knowledge.py:1588`), a region or a
  page. Owned by `reading-markup-annotations.md`; this spec only lists it as the Notes layer.
- `layers.notes.placed-note-is-an-annotation` — **[GAP]** (#2102) a note placed on a page, region,
  line or span is an anchored `Annotation` of kind `note` (anchored on the ladder of
  `layers.anchor.most-precise`); a research note (the Zettel `Note`, `models/knowledge.py:1405`)
  links to that annotation rather than carrying an anchor of its own, so there is one pointing
  mechanism. Today the annotation side is built; a `Note` links only to documents and a page
  (`linked_document_ids`, `page_id`, `:1433`) and cannot link to an annotation, and an
  `AgentNote` has a span but no segment and is drawn nowhere.

### G. Show and hide

- `layers.toggle.one-menu-per-surface` — **[PARTIAL]** (#4941) the layers are switched in the
  surface's existing "What to show" menu (`previewWhatToShow`, `Views/Reader/ReaderToolbar.swift:217-253`:
  Show Image, Annotations, Word Bounding Boxes, Regions, Text Inline, then Edit Segments). New
  layers join it as toggles: Names, Statements, Notes, and the pane's choice of text
  (`layers.translation.chosen-per-pane`). Layers are switched per pane: the Reader's lines mode and
  a canvas's toolbar carry the same menu for their own pane; there is no shared global setting and
  no second control style. The sidebar's bottom-bar toggle (#5413) is a separate control that only
  hides sidebar rows; it never switches a layer.
  The menu moves into the pane menu (What to Show ▸) under `panes-workspaces.md`'s
  `panes.chrome.one-pane-menu` (#5435); the layers do not change with it.
- `layers.toggle.remembered-per-pane` — **[OK]** each switch is remembered per pane, with workspace
  defaults: `@PaneStorage` keys `preview.annotationsEnabled`, `preview.regionsEnabled`,
  `imagePreview.inlineTextEnabled` (`ZoomableImagePreviewMac.swift:176-196`) and
  `PreviewLayerDefaults` for image and word boxes (`Layers/ImageLayer.swift`). New layers use the
  same storage.
- `layers.toggle.empty-layer-says-so` — **[GAP]** (#4941) a layer with nothing on this page stays
  in the menu, dimmed, with "None on this page" as its help, so turning it on is never a silent
  no-op. (This follows the rule of #5413, where the sidebar's knowledge rows appear only when they
  hold something; a page menu dims rather than hides so its layout does not shift page to page.)

## What else the engine already holds (candidate layers)

Found on disk 2026-10-04. "Resolves to" is the finest anchor stored and served today.

| Candidate layer | Engine record | Resolves to today | Drawn on the page today | Issue |
|---|---|---|---|---|
| Segment boxes, lines, baselines | `Segment` (`models/segments.py:620`) | segment (shape) | yes, Preview | — |
| OCR confidence | `Segment.confidence`, `OCRGeometryBox.confidence` | segment / box | yes (stroke) | — |
| Per-character confidence | `ContentRepresentation.char_confidences` (`models/__init__.py:1002`) | span (character) | no | #4935 |
| Markup annotations and their notes | `Annotation` (`knowledge.py:1525`) | span or region | yes | — |
| Research notes | `Note` (`knowledge.py:1405`) | document / page only | no | #2102 |
| Agent notes | `AgentNote` (`models/__init__.py:1497`) | span, no segment | no | #2102 |
| Editorial facts (unclear, lost, supplied, deleted, added) | `EditorialFact` (`models/editorial.py:48`) | span (segment + reading + range), or whole segment | no (Inspector only) | #4935, #5179 |
| Hands | `HandAttribution` (`models/hands.py:55`) | segment, with certainty | no (no Swift UI) | #5161 |
| Campaigns (stages of writing) | `models/campaigns.py:26-58` | segment / reading | no | #4935 |
| Reading order | `ReadingOrderEntry` (`models/reading_orders.py:85`) | segment + position | marquee only, no numbers | #4941 |
| Typed links | `TypedLink` (`models/typed_links.py:169`) | segment (or other ends), no span | no (Inspector list) | #4931 |
| Georeference control points | `control-point` segment + `world-point` reading (`models/geo.py`) | segment | no | #4933 |
| Table cells | `TableCellPlace` (`segments.py:108`) | segment | no | #5168 |
| Dates in the text | `EvidentialDateRange.source_char_start/end` (`knowledge.py:557`) | span, no reading id | no | #4932 |
| Entity mentions | none stored (see C) | document / page | no | #4932, #1659 |
| Statements | `KnowledgeClaim.source_char_*`, `source_anchor` | page-text span, optional rectangle; no segment | no | #4932 |
| Translation | reading of kind `translation` | segment (reading) | no | #3325, #2093 |

Not stored anywhere, only worked out on request: Leiden-bracket text
(`editorial/leiden.py:57`), the georeference transform and residuals, entity mentions found by
name search (`db/__init__.py:772-842`).

## Engine work, by layer

| Layer | Data today | Engine work needed | Issue |
|---|---|---|---|
| Translation | per-line kind and choice exist; no writer | line-by-line job writes readings; a reading's direction from its script | #3325, #4938 |
| Names (entities) | document / page only | extractor stores one anchored support per mention (segment, reading, span) | #4932, #1659 |
| Statements | page-text offsets, no segment | extractor fills `segment_id` and `representation_id` on the anchor | #4932 |
| Notes | annotations anchored; research notes not | a research note links to a `note` annotation | #2102 |
| Any layer on any surface | gathered per overlay in Swift | one per-page layers read (`layers.model.one-read`) | #5418 |
| Canvas cards | thumbnail only | full-detail texture plus the layers read | #3105, #4192 |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | layer state → stroke; anchor ladder fallback; direction of a text layer; menu entries per pane | LayersOnTheSourceTests (to write, in the Swift unit tests under Views/Preview) |
| Availability (Swift) | y | the What to show menu offers every layer on Preview, lines mode and canvases | same |
| Backend (pytest) | y | per-page layers read; mention and statement anchors written with segment and reading; translation readings per line; `claim.transition` refuses a machine | test_layers_on_the_source (to write, in the engine unit tests under api) |
| MCP | y | the layers read is a tool | `fichero-mcp/tests/test_mcp_full.py` |
| CLI | y | `fichero` reads a page's layers | `fichero-cli/tests/` |
| Click-around (XCUITest, Mac) | y | turn Names on, click a mark, the Inspector shows the entity card | `fichero/Tests/UI/` |
| iPhone / iPad | n (later) | — | — |
| Load (#4634) | y | a page with a thousand marks draws in bounded time | `fichero-server/tests/perf/` |

Tests must drive the real host and store, not injected services: a suite once passed while the
window drew no boxes (`ImportedPageDrawsItsBoxesTests.swift:382-387`).

## Documentation matrix

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y | the maintainer's (see Manual above) |
| Contributor | developer docs | y | this spec |
| AI / agent | MCP tool description | y | the layers-read tool |
| Scripter | CLI `--help` | y | the layers command |
| Reference | endpoint reference | y | generated |

## Accessibility identifiers

- `previewWhatToShow` — the existing menu (built).
- `previewInlineTextChoice`, `previewShowNames`, `previewShowStatements`, `previewShowNotes` — the new
  toggles.
- `layers.mark.<layer>.<id>` — a drawn mark, so the click-around test can click a name or a
  statement count.

| Control (a11y id) | Label | Tooltip/help text | Verified by |
|---|---|---|---|
| `previewInlineTextChoice` | Text on the Page | Which text this pane draws on each line: a transcription or a translation | [GAP] |
| `previewShowNames` | Show Names | Where people, places and things are named on this page | [GAP] |
| `previewShowStatements` | Show Statements | Lines that support a statement, with how many | [GAP] |
| `previewShowNotes` | Show Notes | Notes placed on this page, a region, a line or a stretch of text | [GAP] |


## Ruled 2026-10-04

The maintainer answered this spec's six questions, and added three rulings (7 to 9); the behaviours above are written to match.

1. **Scope:** build every layer in this spec, steadily, in the slices of the Plan below.
2. **Translation:** the text a Preview shows is chosen per pane, so several Previews can stand side
   by side (the image, a transcription, a translation), and the lines mode can show more than one
   text under each line (`layers.translation.chosen-per-pane`,
   `layers.translation.lines-mode-shows-several`).
3. **A model's marks:** dashed until a person confirms them, solid once confirmed, hidden once
   rejected (`layers.state.drawn`).
4. **Where a mark sits:** on the most precise anchor available, on the ladder stroke, character,
   word, line, paragraph or region, page, dropping a rung when a finer one cannot be resolved
   (`layers.anchor.most-precise`).
5. **Notes:** a note placed on the source is an anchored annotation of kind `note`; research notes
   link to it (`layers.notes.placed-note-is-an-annotation`).
6. **Switching:** layers are switched per pane, in each pane's "What to show" menu; the sidebar's
   bottom-bar toggle (#5413) is separate and only hides sidebar rows
   (`layers.toggle.one-menu-per-surface`).
7. **Box colours** (ruled 2026-10-04, superseding the pane's choice): a box's colour is its
   region's hue, shaded as a gradient along the working pass's reading order; nothing is coloured
   at random; a child is drawn as its parent's child. Owned by `source/segment-editor.md`, "Box
   colour and the segment hierarchy" (`source.editor.colour.*`, `source.editor.hierarchy.*`).
8. **One page of a spread:** Preview can show the whole photograph or just its left or right page
   by cropping the view to that page's region, with no change to records, as an alternative to
   splitting it into child documents (`layers.spread.show-one-page`).
9. **Transcription font:** transcription text is drawn in the font setup derived for the
   library's script and period, changeable in each pane's What to show menu and remembered per
   library; the app's chrome keeps system fonts (`layers.text.font-from-script-and-period`).

## Plan

Each slice is one reviewable commit with its tests. Engine slices land with the contract
regenerated; app slices drive the real host and store, never injected services.

| # | Slice | Spec ids | Engine work | App work | Pinned by | Depends on |
|---|---|---|---|---|---|---|
| 1 | A model cannot review a claim | `layers.statements.only-a-person-curates` | `claim.transition`, `claim.batch_transition`, `claim.batch_curation` refuse a machine actor; the reviewer is the context's actor | — | pytest: refused as a workflow or agent, recorded as the person otherwise | — (#5416) |
| 2 | The page layers read | `layers.model.one-read`, `layers.anchor.most-precise` | one route per page returning boxes, regions, annotations and their state, each on its finest resolvable rung with the fallback named; MCP tool; CLI command | — | pytest contract and ladder fallback (a changed reading drops a span to its line); MCP; CLI | — (#5418) |
| 3 | Preview draws from the read | `layers.preview.draws-today` | — | `DocumentOverlay` built from the read; what is drawn does not change | `ImportedPageDrawsItsBoxesTests` stays green; a test that the real host reads the route | 2 |
| 4 | State drawn one way | `layers.state.drawn` | — | dashed, solid, hidden by state; the hover in words | Swift pure rule; one click-around: confirm turns dashed to solid | 3 (#5417) |
| 5 | Text follows its line | `layers.text.follows-line-direction` | — | inline text laid out in the line's direction and fitted to its box | Swift layout rule on a vertical and a right-to-left line | 3 (#5411) |
| 6 | A reading's direction | `layers.translation.target-direction` | a reading's direction worked out from its script; the reading rung of `resolve_direction` filled | — | pytest: English translation of a vertical line reads left to right | — (#4938) |
| 7 | A model translates line by line | `layers.translation.model-makes-one-per-line` | `translate-transliterate-normalise` wired in `WORKFLOW_FOR_JOB`; writes one `translation` reading per line from its counting transcription, recorded as the model's | — | pytest with a stub model: one reading per line, provenance the model's, choice untouched | — (#3325) |
| 8 | Each pane picks its text | `layers.translation.chosen-per-pane` | the layers read carries the chosen kind's readings | the menu's text choice, stored per pane | Swift: two panes, two texts; pytest: read by kind | 2, 3, 5, 6, 7 (#2093) |
| 9 | Lines mode carries layers and several texts | `layers.reader.lines-mode-draws-layers`, `layers.translation.lines-mode-shows-several`, `layers.translation.person-types-one` | — | the #5414 lines mode draws the read on each strip; several texts under a line; a typed translation saved through the one save action | Swift against the real store; save is a person's reading of kind `translation` | 2, 8; #5414's lines mode (#5209) |
| 10 | Statements anchored to a line | `layers.statements.anchored-to-a-passage` | the extractor fills `segment_id` and `representation_id` on a claim's anchor | — | pytest: an extracted claim names its line and reading | — (#4932) |
| 11 | Names anchored to a span | `layers.entities.engine-knows-where-a-name-is`, `layers.entities.read-per-segment` | NER and the extractor write one supporting source per mention (segment, reading, span), the model's | — | pytest: a name extracted twice on a page has two anchored mentions; `/segments/{id}/statements` returns them | — (#4932, #1659) |
| 12 | The Names layer | `layers.entities.shown-on-text-and-image`, `layers.entities.hover-and-click` | the read carries mentions | underline on text, wash on image; click selects the entity, the Inspector shows its card | Swift; click-around: click a name, the card shows | 4, 11 (#1659) |
| 13 | The Statements layer | `layers.statements.which-lines-carry-them`, `layers.statements.confirm-or-reject-from-the-passage` | the read carries claims per line | line marks with a count; the Inspector's Statements section confirms or rejects through `claim.transition` | Swift; click-around: reject hides the mark | 1, 4, 10 (#4932, #4834) |
| 14 | Placed notes | `layers.notes.placed-note-is-an-annotation` | a research note links to a `note` annotation | the Notes layer shows linked research notes on their annotation | pytest link; Swift draw | 2 (#2102) |
| 15 | Layers already on lines | candidate layers: editorial facts, hands, reading order numbers, control points | each added to the read (one commit per layer) | each drawn, with its toggle | pytest per layer; Swift per layer | 2, 3 (#4935, #5161, #4941, #4933) |
| 16 | An empty layer says so | `layers.toggle.empty-layer-says-so` | the read says which layers are empty on this page | dimmed toggle, "None on this page" | Swift | 2 (#4941) |
| 17 | The 2D canvas card | `layers.canvas2d.page-card-draws-layers` | — | a full-detail page card reads the layers and draws them through its image frame | Swift renderer test on a card's child entities | 2, 4; full-texture tier (#3105, #4931) |
| 18 | The 3D canvas card | `layers.canvas3d.page-card-draws-layers` | — | the same for the 3D renderer | Swift renderer test | 17 (#4192) |
| 19 | Colour is the region, shaded by order | `source.editor.colour.*`, `source.editor.hierarchy.*` (in `source/segment-editor.md`) | — (regions and the reading order already in the read) | region hues in region order; a gradient along the reading order inside each region; region-less lines one implicit region; children inside their parent, lighter | Swift pure rule: same page, same colours; a gradient along the order, an out-of-order pair breaks it; a word page still draws its lines; the real host draws it | 2, 3 (#5426, #5463) |
| 20 | Pages of a spread found, not cut | `layers.spread.show-one-page` (engine half) | finding the pages stores each page region as a `page` segment on the photograph, with decision and confidence, and the outline as geometry; no children made | — | pytest: a proposed split stores two page regions and makes no child | — (#5427, #5382) |
| 21 | Show one page of a spread | `layers.spread.show-one-page` (app half) | — | Whole, Left page, Right page in the pane menu when page regions exist; the crop is a view transform | Swift: the crop changes no record; boxes stay on their ink | 3, 20 (#5427) |
| 22 | Transcription font from setup | `layers.text.font-from-script-and-period` | setup stores the derived font as the library's `font` fact per script, with a period rule (medieval Latin → Junicode); the layers read names the resolved font | inline text, lines mode and text panes draw through the resolved family and the `BundledFonts` cascade; the pane menu offers the bundled and project fonts, remembered per library | pytest: derived and stored for Latn + medieval; Swift: inline text uses the resolved family; per-library memory | 2, 3; `source.fonts.per-script` engine half (#5210) (#5438) |

Order: slices 1, 2, 6, 7, 10, 11 and 20 are engine work with no dependency on each other and can run in
parallel lanes with disjoint files; the app slices follow the read (2 → 3).

## Triaged from the backlog (2026-10-04)
- `layers.boxes.visible-with-order-numbers` **[GAP]** (#5288): segment boxes are easy to see at a glance on a dark, busy manuscript page, not faint dashes, and the layers menu has an option, off by default and kept per pane, to label each line with its reading-order number and each region with its region order. (Colour by region and reading order is `source.editor.colour.reading-order-gradient` in `source/segment-editor.md`.)
