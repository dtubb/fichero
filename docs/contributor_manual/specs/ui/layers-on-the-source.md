# Layers on the source: translation, entities, statements, notes — Design Spec

> Milestone: TBD (proposed: `layers-on-the-source`; until then the work lives on the issues cited per behaviour)
> Manual: TBD — the user manual needs a section, "What is drawn on a page", explaining the layers
> (boxes, text, translation, names, statements, notes and the rest), how to turn each on or off,
> what a dashed versus a solid mark means (a model's versus a person's), and that the same layers
> appear in Preview, the Reader's lines mode and on a canvas card.

> Design-led (Testing Constitution). **Status: DRAFT** (2026-10-04), written from the code at
> `lane/lead` 658b398de. Not yet reviewed by the maintainer.
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

- `layers.model.one-read` — **[GAP]** (#4941) the layers for a page come from one engine read
  that returns, per layer, the items on that page with their anchor (segment id with its live
  shape, or segment id plus reading id plus character span) and their state (who made it,
  curation state). Every surface draws from that read. Today each overlay is gathered separately
  in Swift (`ZoomableImagePreviewMac+Regions.swift:33-66` builds `DocumentOverlay` from boxes,
  annotations and marquees), and there is no engine read for layers.
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
- `layers.translation.shown-beside-or-instead` — **[GAP]** (#2093) with the Translation layer on,
  the Reader's lines mode shows the line's counting translation under its transcription, and
  Preview's inline text shows the translation in place of the transcription (one inline text at a
  time on the image, so the two never overprint). A line with no translation shows nothing, not
  the transcription in its place. Today Preview's inline text is the OCR box text only
  (`OCRGeometryOverlay.swift:117`) and never a translation.
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
- `layers.statements.only-a-person-curates` — **[GAP]** (#4868) `claim.transition` refuses a
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
- `layers.state.drawn` — **[GAP]** (#1659) every knowledge layer draws state the same way: a
  model's unreviewed item is dashed, an item a person made or confirmed is solid, and a rejected
  item is not drawn. The hover says it in words ("Proposed by <model>, not reviewed").

### F. Notes as a layer

- `layers.notes.marks-drawn` — **[OK]** annotations (highlight, note, rating, bookmark, comment,
  line, underline, strikethrough) are drawn on the page by kind
  (`Views/Preview/ImageViewer/AnnotationMarkRendering.swift`), anchored to a span (`targets[]`,
  segment plus character range in its counting reading, `models/knowledge.py:1588`), a region or a
  page. Owned by `reading-markup-annotations.md`; this spec only lists it as the Notes layer.
- `layers.notes.research-notes-on-the-page` — **[GAP]** (#2102) a research note (the Zettel `Note`,
  `models/knowledge.py:1405`) can be placed on a page, region, line or span and then appears in the
  Notes layer. Today a `Note` links only to documents and a page (`linked_document_ids`, `page_id`,
  `:1433`), with no region or span; an `AgentNote` has a span but no segment and is drawn nowhere.

### G. Show and hide

- `layers.toggle.one-menu-per-surface` — **[PARTIAL]** (#4941) the layers are switched in the
  surface's existing "What to show" menu (`previewWhatToShow`, `Views/Reader/ReaderToolbar.swift:217-253`:
  Show Image, Annotations, Word Bounding Boxes, Regions, Text Inline, then Edit Segments). New
  layers join it as toggles: Translation, Names, Statements, Notes. The Reader's lines mode and a
  canvas's toolbar carry the same menu; there is no second control style.
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
| Notes | annotations anchored; research notes not | a research note takes an anchor, or links to an annotation | #2102 |
| Any layer on any surface | gathered per overlay in Swift | one per-page layers read (`layers.model.one-read`) | #4941 |
| Canvas cards | thumbnail only | full-detail texture plus the layers read | #3105, #4192 |

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | layer state → stroke; direction of a text layer; menu entries per surface | `fichero/Tests/Unit/general/Views/Preview/LayersOnTheSourceTests.swift` (to write) |
| Availability (Swift) | y | the What to show menu offers every layer on Preview, lines mode and canvases | same |
| Backend (pytest) | y | per-page layers read; mention and statement anchors written with segment and reading; translation readings per line; `claim.transition` refuses a machine | `fichero-server/tests/unit/api/test_layers_on_the_source.py` (to write) |
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
- `previewShowTranslation`, `previewShowNames`, `previewShowStatements`, `previewShowNotes` — the new
  toggles.
- `layers.mark.<layer>.<id>` — a drawn mark, so the click-around test can click a name or a
  statement count.

| Control (a11y id) | Label | Tooltip/help text | Verified by |
|---|---|---|---|
| `previewShowTranslation` | Show Translation | Each line's translation, in place of its text on the image and under it in lines | [GAP] |
| `previewShowNames` | Show Names | Where people, places and things are named on this page | [GAP] |
| `previewShowStatements` | Show Statements | Lines that support a statement, with how many | [GAP] |
| `previewShowNotes` | Show Notes | Notes placed on this page, a region, a line or a stretch of text | [GAP] |

## Open questions for the maintainer

1. **Which layers first?** (a) the three you asked for (Translation, Names, Statements), which all
   need engine work first; (b) the ones the engine can already place on a line with no new data
   (editorial facts, hands, reading order numbers, control points); (c) the layer model plus
   Translation now, then Names and Statements once the extractor writes segment anchors.
   **Recommend (c):** translation's data shape exists and needs one job; Names and Statements wait
   on the same anchor work (#4932), so build that once for both.
2. **Translation on the image: beside or instead?** (a) Preview's inline text swaps to the
   translation, and the lines mode shows both, one under the other; (b) Preview shows both on the
   image, translation under each line; (c) translation only in the lines mode and the Reader, never
   on the image. **Recommend (a):** two texts on one line box overprint, and the lines mode has
   room for both.
3. **How fine should a name's place be?** (a) a span in a named reading of the segment, falling
   back to the whole segment; (b) the segment only. **Recommend (a):** spans already survive
   re-transcription by matching (`replace_stretch`, `readings.py:637-692`), and a segment-only
   mark cannot underline a word in a long line.
4. **How are a model's marks shown?** (a) dashed until a person confirms, solid after, rejected
   hidden; (b) hidden until a person confirms; (c) drawn alike, the state only in the hover.
   **Recommend (a):** the page shows what the model proposed without passing it off as checked.
5. **A note on the page: which record?** (a) a placed note is an annotation of kind `note` (already
   anchored to a span or region), and a research note links to it; (b) the research note itself
   gains an anchor. **Recommend (a):** one anchored record, no second pointing mechanism.
6. **One control style?** (a) each page surface keeps the "What to show" menu (toolbar), and the
   sidebar's knowledge-row control (#5413) stays a separate single toggle in the bottom bar;
   (b) one shared layers setting across Preview, the lines mode and the canvases; (c) a toggle
   button per layer in the bottom bar. **Recommend (a):** layers are a property of the pane you are
   looking at, as `source.editor.two-switches` ruled; the sidebar control hides rows, not marks.
