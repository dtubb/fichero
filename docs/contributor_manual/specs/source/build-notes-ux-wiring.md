# Build notes: UX wiring -- where the app reaches what the engine does (audit, 2026-09-27)

Asked for by the maintainer after his try-out of 2026-09-27: everything built must be hooked into the
UX, systematically. `SegmentDisplay` was the pattern that prompted it -- a seam tested twenty ways that
seemed never to reach the screen (#5146; it did reach the screen, and the defect was the ranking
inside it). This file records, for EVERY `source.*` behaviour a spec tags **[OK]** or **[PARTIAL]**,
where the app reaches it, whether it is on screen, and its end-to-end test. Read on disk on
`spec/page-model` at `6dc912235`, from code; nothing was built or run. A behaviour's spec tag is
about the ENGINE; this file is about the person.

**The rule from now on** (2026-09-27): a slice is not done until one end-to-end test goes through the
exact call the screen makes, on a real imported file.

## The headline

Of **144** behaviours: **26** wired and visible, **18** reachable in part, **39** not reachable
(31 with no Swift caller at all), **60** engine-internal (no screen of their own), 1 unsure. Of the
source-model routes, **8** have an app caller. Two Swift types have no caller: `SegmentSelection`
(its `shared` instance is never written) and `SegmentEditCommand`.

The most urgent gap is not a spec row: **a box on an imported page draws but cannot be selected or
edited** (#5152) -- so on an imported page the Inspector's segment level, Edit Segments and undo are
unreachable. It comes first.

## The build order: one issue per gap, ranked by what the maintainer reaches for first

The 49 gaps below (section "GAPS") are grouped into 18 issues, one per SURFACE a person would reach
for, because a gap list split finer than the surface that closes it gets built piecemeal:

1. **#5152** a box on an imported page cannot be selected or edited -- source.editor.shapes-in-source-view, source.editor.selection-shared (imported pages)
2. **#5153** choose which reading counts, and see a reading's full record, in the Inspector's Text section -- source.reading.chosen-is-worked-out, source.reading.chosen-follows-project-rule, source.reading.written-read-pair, source.reading.corrections-are-new, source.reading.level-recorded, source.reading.read-from, source.reading.char-confidence-on-line
3. **#5154** type a correction in the Reader as a new reading; Return splits a line, Backspace joins -- source.reading.set, source.textedit.typing-is-a-new-reading, source.textedit.reader-shows-segments, source.textedit.return-splits-the-line, source.textedit.backspace-joins-in-reading-order
4. **#5155** one selection across the Source view, the Reader and the Inspector -- source.editor.selection-shared
5. **#5156** show, hide and compare a page's passes, and choose the working pass -- source.pass.named-authored, source.pass.working
6. **#5157** set kind, direction and language/script on the selection (the Segment menu) -- source.editor.set-kind, source.editor.set-direction, source.editor.set-language-script, source.lang.many-per-page, source.dir.per-segment
7. **#5158** the Inspector's Language & script section -- the three facts and where each came from -- source.lang.three-facts, source.lang.says-where-from, source.lang.reading-overrides, source.lang.cascade, source.lang.project-declared
8. **#5159** join selected segments by id; group lines into a region and ungroup -- source.editor.join-group
9. **#5160** pick, create and step through named reading orders and flows -- source.order.named-multiple, source.order.next-previous, source.segment.flow, source.editor.reorder
10. **#5161** hands in the Inspector -- browse and create hands, attribute a segment, ink vs record -- source.hand.record, source.hand.attributed, source.hand.not-provenance
11. **#5162** choose what to export, export hOCR and YOLO from the menu, and import/export a page on iOS -- source.format.export-choices, source.format.first-four, source.format.everywhere
12. **#5163** a segment's history, its picture and its baseline -- source.segment.versioned-alone, source.segment.picture-by-shape, source.segment.curved-baseline, source.segment.shape-kinds
13. **#5164** typed links between segments, a segment's links, copy its reference, open a fichero:segment link -- source.link.typed, source.link.both-ways, source.form.label-and-answer, source.segment.citable
14. **#5165** review proposed segment matches and carry readings/marks across -- source.segment.match-record, source.segment.carry-across-a-match
15. **#5166** signs -- declare a sign, look it up, the project list, variants, gather instances -- source.sign.declared, source.sign.list-authority, source.sign.project-list, source.sign.in-readings, source.sign.variants, source.sign.gather-instances
16. **#5167** attach a rights or consent record and see the effective rights -- source.rights.record
17. **#5168** tables -- a cell's row and column, draw a table or its cells -- source.segment.table-cells, source.table.is-a-segment
18. **#5169** georeferencing -- export a georeferencing pass, import one into the library, choose gazetteer candidates -- source.geo.iiif-georef-out, source.geo.iiif-georef-in, source.geo.gazetteer-candidates

## What is wired today

- Boxes over the image and the PDF page come from the segment seam (`OCRGeometryOverlay.loadOCRGeometry`,
  `PDFPageView+OCRBoxes`), imported pages included since #5146.
- Inspector › Source: with a box selected, the path head, the Text section (readings, maker, which
  counts and why, sic/corr pairs) and the Order section (children, drag and ⌥⌘ keys, ⌘Z).
- The Reader's ⌥⌘ keys move the caret's line in the order (`ReaderLineMove`).
- File › Export › Export Page As (PAGE XML, ALTO, TEI) and Import Page From…, macOS only.
- Edit Segments: move, delete, combine, with undo and redo, on artifact-backed pages.


Method: every generated operation (openapi.json operationId → camelCase Swift name) was grepped across `fichero/fichero/**/*.swift`. Of the source-model routes, **only 8 have an app caller**:
`listDocumentSegments…`, `getSegment…`, `listSegmentReadings…` (SegmentService); `listDocumentOrders…`, `listOrderEntries…`, `placeInReadingOrder…` (ReadingOrderService); `exportDocumentPage…`, `importDocumentPage…` (DocumentService+PageIO). The preview's box edits go through the older `PUT /api/artifacts/{id}/regions` (ArtifactService+RegionCuration), which the engine now routes into `segment.convert_and_edit`. The app's generic `ActionsService.invokeAction(name:)` is called only with document/claim/entity/artifact action names (the only language one is `document.set_language`); it is never called with a segment, reading, hand, sign, rights, link or order action.
**Uncalled source routes** (0 app callers): all segment writes (`POST/PUT/PATCH /api/segments…`, merge, split, delete, undelete, carry, matches, passes, restore-version, versions, picture, reference), `POST …/readings/choice`, `GET /api/segments/document/{id}/text`, `GET /api/reading-orders/{id}/neighbours`, `POST /api/reading-orders`, `GET /api/formats`, all `/api/links`, `/api/signs`, `/api/rights`, `/api/hands`, `/api/content-representations`, `GET /api/source-settings/resolve`, and the authority `refresh` and `link` routes.

Short names used in the table:
- **SS** = `fichero/fichero/Services/SegmentService.swift`; **STORE** = `Models/SegmentStore.swift` (`SegmentStore.shared(for:)`, owned by `LibraryManager`)
- **OVL** = `Views/Preview/ImageViewer/OCRGeometryOverlay.swift:loadOCRGeometry` → `SegmentDisplay.selected(for:store:)`; **PDFBOX** = `Views/Preview/PDFViewer/PDFPageView+OCRBoxes.swift`
- **INSP** = `Views/Inspector/Source/SourceSectionView.swift` (mounted by `DocumentInspector+Sections.swift:contentTab`) → `SegmentInspectorView` (path head, **Text** section = `InspectorTextSection`, **Order** section = `ReadingOrderList`). It is shown only when the focused preview's `RegionSelection` resolves to segment ids.
- **ORDER** = `Services/ReadingOrderService.swift` → `Models/ReadingOrderStore.swift` → `Views/Components/ReadingOrderList.swift` (Inspector ▸ Source ▸ **Order** tab, and the Order section at a selected level). **RLM** = `Views/Reader/Knowledge/ReaderLineMove.swift` ← `DocumentKGWebPaneCoordinatorMacOS.moveLine` (⌥⌘↑/↓/⇞/⇟ on the Reader caret line; the engine's `document_view.html` posts `lineMove`).
- **PIO** = `Services/DocumentService+PageIO.swift` `exportPage`/`importPage` ← `App/Menus/PageExportRunner.swift` / `PageImportRunner.swift` ← `App/Menus/ReaderExportCommands.swift:ReaderExportMenuItems`. That menu is **File ▸ Export ▸ "Export Page As ▸ PAGE XML/ALTO/TEI"** and **"Import Page From…"**, also in the reader head menu (`ReadingPaneView.swift:529`). It is macOS only (`#else EmptyView`) and needs a single document.
- **RGN** = `Services/ArtifactService+RegionCuration.swift` (PUT `/api/artifacts/{id}/regions` → action `segment.convert_and_edit`) ← `Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Regions.swift` (`commitRegionMove`, `deleteSelectedRegions`, `combineSelectedRegions`, `promoteMarquees`, `promoteSelectedWords`, `registerRegionUndo`). It is gated on `WindowState.isEditingSegments`, the **Edit Segments** toggle in the preview head (`PreviewHeadControls.swift`) and the what-to-show menu (`ReaderToolbar.swift:240`).
- **IMPORTED-PAGE CAVEAT** (read from code, not run): an imported pass has no `sourceArtifactId`, so OVL sets `ocrGeometryArtifactId = nil`. `RegionInteractionLayer` selects only `if let artifactId` (lines 378–386) and `RegionEditTarget.forDirectEdit/forSelectionEdit` refuse a nil artifact. On a page whose shown pass came from **Import Page From…**, the boxes draw (#5146) but they **cannot be selected or edited**. The Inspector's segment level (INSP) is therefore unreachable there too, because `selectedSegmentIds` needs `pass.sourceArtifactId == selection.artifactId`.

Python e2e test paths are relative to `fichero-server/tests/unit/`. "Real data" means a real interchange file or corpus page imported through `format.import` or the import route.

## Table 1 — behaviours

### formats-and-training.md (19)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.format.one-model-one-harness | formats-and-training.md | OK | `formats/` registry + `SourcePage`, harness | n/a | engine-internal (format architecture) | n/a | |
| source.format.schemas-on-disk | formats-and-training.md | OK | `formats/schemas/`, offline validation | n/a | engine-internal (validation never goes to the network) | n/a | |
| source.format.first-four | formats-and-training.md | PARTIAL | format registry (pagexml, alto, tei, hocr, yolo, iiif_georef); `GET /api/formats`; export/import routes | PIO; `PageExportRunner.Format` is a hard-coded enum `pagexml, alto, tei`; `listFormatsApiFormatsGet` is uncalled | partial — import accepts any recognised file; export offers only PAGE XML/ALTO/TEI | `formats/test_import_into_library.py::TestTheImportRoute::test_a_person_uploads_a_file_and_gets_a_pass` (real OCR-D PAGE file, the app's route) | hOCR and YOLO export are not in the menu; the menu is not built from `GET /api/formats` |
| source.format.package-folder | formats-and-training.md | PARTIAL | `POST /api/ingest/folder` → `import.folder` → `interchange_pairing.plan_pairs` → `format.import` | `Services/ImportService+Ingest.swift` / `DocumentService.ingestFolder` (the existing folder import) | yes — the ordinary folder import/drop | none via the route; action-level on real files: `importers/test_folder_of_images_and_layout.py::TestDroppingTheFolder::test_the_images_become_pages_with_their_passes` | |
| source.format.import-is-pass | formats-and-training.md | OK | `POST /api/documents/{doc_id}/import` (action `format.import`) | PIO `importPage` ← `PageImportRunner.importPage` ← ReaderExportMenuItems | yes — File ▸ Export ▸ Import Page From… (macOS) | `formats/test_import_into_library.py::TestTheImportRoute::test_a_person_uploads_a_file_and_gets_a_pass`; unit: `PageImportTextTests` | no way to see or choose the new pass afterwards (see source.pass.named-authored) |
| source.format.reimport-recognised | formats-and-training.md | OK | same route, 409 naming the pass | PIO `importPage` → `.alreadyImported(detail:)` → PageImportRunner alert | yes — the alert names the pass that holds the bytes | `formats/test_import_into_library.py::TestReimportIsRecognised` (unsure whether through the HTTP route) | |
| source.format.keeps-unrecognised | formats-and-training.md | OK | `format.import` → `metadata["foreign"]`; `page_export` writes it back | carried through PIO; nothing displays it | engine-internal (kept and written back; nothing to show) | `formats/test_import_into_library.py::TestWhatTheImportKeptSurvivesTheExport::test_the_library_round_trip_keeps_it_the_way_a_format_round_trip_does` (import+export routes, real file) | |
| source.format.export-validated | formats-and-training.md | OK | harness validation inside the export route | the refusal sentence reaches PageExportRunner via `DocumentServiceError.serverError` | engine-internal (a refused export shows the engine's sentence) | route-level on synthetic rows: `api/test_page_export_route.py::TestTheRefusalsAreDeclaredAndNotOnlyRaised` | |
| source.format.validate-a-directory | formats-and-training.md | OK | `scripts/validate_exports.py` | n/a | engine-internal (dev/CI command) | n/a | |
| source.format.every-writer-is-validated | formats-and-training.md | OK | guard `formats/test_export_validation.py` | n/a | engine-internal (CI guard) | n/a | |
| source.format.loss-report | formats-and-training.md | OK | export response `losses` | PIO `exportPage` → `PageExportRunner.Text.losses` in the completion alert (selectable) | yes — the Export Page As completion message | none on real data; route test on a synthetic page: `api/test_page_export_route.py::TestExportingAPage::test_the_loss_report_reaches_the_caller`; unit: `PageExportTextTests` | |
| source.format.round-trip-pagexml | formats-and-training.md | OK | pagexml reader/writer | n/a | engine-internal (format property; reached via Import/Export Page) | format-level `formats/test_pagexml_round_trip.py`, `test_pagexml_real_file.py` | |
| source.format.round-trip-alto | formats-and-training.md | OK | alto reader/writer | n/a | engine-internal (format property) | format-level `formats/test_alto.py::TestTheAltoRoundTrip` | |
| source.format.round-trip-hocr | formats-and-training.md | OK | hocr reader/writer | n/a | engine-internal (format property; hOCR export is not offered in the app) | format-level `formats/test_hocr_and_yolo.py::TestHocrRoundTrip` | |
| source.format.round-trip-yolo | formats-and-training.md | OK | yolo reader/writer | n/a | engine-internal (format property; YOLO export is not offered in the app) | format-level `test_hocr_and_yolo.py::TestYoloIsHonestAboutLosingAlmostEverything` | |
| source.format.export-choices | formats-and-training.md | OK | `GET /api/documents/{id}/export/{fmt}?pass_id&order_id&reading_kind` | PIO `exportPage` sends only the path (engine defaults); `PageExportRunner.Text.summary` shows pass, order and kind | partial — the choices are reported, not choosable | route on synthetic rows: `api/test_working_pass_across_surfaces.py::TestPageExportFollowsTheWorkingPass`; none on real data | the app cannot pick which pass, order or reading kind to export |
| source.format.everywhere | formats-and-training.md | OK | the two routes above; CLI `fichero export/import page`; MCP `fichero_page_export/import` | PIO ← ReaderExportMenuItems | yes on macOS; **no on iOS** (`#else EmptyView`) | `formats/test_import_into_library.py::TestTheImportRoute::test_a_person_uploads_a_file_and_gets_a_pass`, `::TestWhatTheImportKeptSurvivesTheExport::test_a_files_custom_survives_import_then_export` | iOS has no page import or export |
| source.format.alto-in | formats-and-training.md | OK | alto reader via the import route | PIO importPage | yes — through Import Page From… | none via the route (format-level `formats/test_alto.py::TestReadingARealAltoFile`) | |
| source.format.alto-out | formats-and-training.md | OK | alto writer (ALTO 4.4) via the export route | PIO exportPage (`Format.alto`) | yes — Export Page As ▸ ALTO | none via the route on a real file (format-level `test_alto.py`) | |

### languages-scripts-signs.md (17)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.lang.three-facts | languages-scripts-signs.md | OK | `Segment.language/script` + provenance; `LibraryScript.encoding`; `segment.update` | `Segment.language/script/direction` are decoded (`Models/Segment.swift:223`) but no view reads them | no | none | the Inspector does not show a segment's language, script or encoding |
| source.lang.registries | languages-scripts-signs.md | PARTIAL | ISO 15924 vocabulary, `LanguageSpec.glottocode` | none | engine-internal (vocabulary; BCP 47 half is GAP #5078) | n/a | |
| source.lang.project-declared | languages-scripts-signs.md | OK | `LibraryScript` + `assert_known_script` (in `representation.create`, `segment.update`) | none | no | none | no way to declare a project script in the app |
| source.lang.unknown-is-not-unexamined | languages-scripts-signs.md | OK | cascade resolution control flow | only the pre-existing document language row (`DocumentInspectorInfoTab+Language.swift`, `document.set_language`, "clear" back to never-determined) | engine-internal (resolution rule) | n/a | |
| source.lang.cascade | languages-scripts-signs.md | OK | `source_settings` action (project/node) + `segment.update`; `GET /api/source-settings/resolve` | only the document level, via `document.set_language` in the Info tab (predates the programme); `resolveSourceSettings…` is uncalled | partial — document level only | none | cannot set at folder/page/segment level or see the inherited value |
| source.lang.says-where-from | languages-scripts-signs.md | OK | `GET /api/source-settings/resolve` → `LanguageResolution.level` | none | no | none | a shown language does not say which level it came from |
| source.lang.reading-overrides | languages-scripts-signs.md | OK | cascade (reading rung) | none (`InspectorText.Reading` has no language/script) | no | none | the Inspector's Text section does not show a reading's language/script |
| source.lang.many-per-page | languages-scripts-signs.md | OK | `PUT /api/segments/{id}` (`segment.update` language/script) | none (`updateSegment…` uncalled; `SegmentEditCommand.plan` has no caller) | no | route-level on synthetic regions: `api/test_many_languages_per_page.py::TestManyPerPageEndToEnd::test_three_regions_are_SET_to_three_scripts_and_READ_BACK_as_three` | cannot set a region's language/script |
| source.dir.per-segment | languages-scripts-signs.md | PARTIAL | `segment.update` direction; `resolve_direction` | none | no | none | cannot set or see a segment's direction |
| source.dir.logical-order-stored | languages-scripts-signs.md | OK | engine never reorders text | display bidi by WebKit/SwiftUI | engine-internal (storage rule) | n/a | |
| source.sign.declared | languages-scripts-signs.md | PARTIAL | `POST /api/signs` (`sign.declare`) | none | no | none | declare a sign from a segment (spec: waits for wireframes) |
| source.sign.list-authority | languages-scripts-signs.md | PARTIAL | `sign.declare` with authority + number | none | no | none | look up a sign by catalogue number |
| source.sign.project-list | languages-scripts-signs.md | PARTIAL | `GET /api/signs`, `POST /api/signs/{id}/withdraw` | none | no | none | see or export the project's sign list |
| source.sign.in-readings | languages-scripts-signs.md | PARTIAL | text keeps the PUA character; `DeclaredSign` gives its meaning | reading text is shown as plain text in INSP | partial — the character shows, its declared meaning does not | none | show which declared sign a character is |
| source.sign.variants | languages-scripts-signs.md | PARTIAL | `sign.declare` (variant fields) | none | no | none | declare or mark a variant |
| source.sign.gather-instances | languages-scripts-signs.md | PARTIAL | `GET /api/signs/{id}/instances` | none | no | none | list every instance of a sign |
| source.sign.export-honest | languages-scripts-signs.md | PARTIAL | TEI writer `<g ref>` + `charDecl`; other writers' loss report | PIO exportPage (TEI) | partial — automatic in Export Page As ▸ TEI; losses shown in the alert | none via the route on real data (`api/test_declared_signs.py` exports through `/export/tei` on a MUFI page — unsure whether through the client) | |

### maps-and-georeference.md (4)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.geo.gazetteer-candidates | maps-and-georeference.md | PARTIAL | external authority reconciliation: `POST /api/kg/entity-curation/authority/refresh`, `/link` | `KGCurationService.swift` calls only the authority **settings** get/put; refresh and link are uncalled | no (settings only; where they show is unsure) | none | see and choose authority candidates for an entity |
| source.geo.iiif-georef-in | maps-and-georeference.md | PARTIAL | `formats/iiif_georef.py` reader (registered); library half #5122 | possibly PIO importPage (the registry holds iiif_georef) — unsure whether the route accepts it | unsure | none via the route (format-level `formats/test_iiif_georef.py`) | library half (#5122); no map view |
| source.geo.iiif-georef-out | maps-and-georeference.md | PARTIAL | `iiif_georef` writer | none (`PageExportRunner.Format` has no georef) | no | none via the route | export a georeferencing pass |
| source.geo.iiif-georef-round-trip | maps-and-georeference.md | OK | format-to-format round trip | n/a | engine-internal (format property) | format-level `test_iiif_georef.py::TestWriting::test_the_round_trip_keeps_gcps_mask_and_transformation` | |

### readings-and-apparatus.md (17)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.reading.set | readings-and-apparatus.md | OK | action `representation.create`; `POST /api/content-representations`; read `GET /api/segments/{id}/readings` | read: `SS.readings(segmentId:)` ← `SegmentInspectorView.task` (INSP); write: none | partial — readings are **listed** (INSP ▸ Text); none can be added | none on real data (route test on synthetic rows: `api/test_segment_readings.py::TestReadingsAreWritten::test_three_readings_of_one_line_coexist_and_adding_one_changes_no_other`); unit `InspectorTextTests` | type or add a reading (Reader typing not built, #5001); not reachable on imported pages (caveat) |
| source.reading.kinds | readings-and-apparatus.md | OK | reading-kind registry | INSP groups readings by kind | yes — headings per kind in the Text section | none | |
| source.reading.level-recorded | readings-and-apparatus.md | OK | `ContentRepresentation.level` | not mapped into `InspectorText.Reading` | no | none | the Text section does not show a reading's normalisation level |
| source.reading.read-from | readings-and-apparatus.md | OK | reading's rendition + `derived_from` | not mapped | no | none | does not show which image or reading it was read from |
| source.reading.author-and-guideline | readings-and-apparatus.md | OK | `created_by`, `guideline` | `InspectorText.Reading.author/guideline` → `InspectorTextSection.detail` | yes — INSP Text row detail line | none on real data; unit `InspectorTextTests` | |
| source.reading.corrections-are-new | readings-and-apparatus.md | OK | `representation.create` with a correction target | none (the target is not mapped) | no | none | make a correction; see what a correction corrects |
| source.reading.equal-alternatives | readings-and-apparatus.md | OK | counting rule | INSP lists every live reading per kind | yes — all alternatives are listed | none | |
| source.reading.chosen-is-worked-out | readings-and-apparatus.md | OK | `counting` + `basis` in the readings route; `POST …/readings/choice` (`reading.choose`) | read: `InspectorText.Counting/Why` (checkmark + "Chosen by a person" etc.); choose: none (`chooseSegmentReading…` uncalled) | partial — which counts, and why, is shown; cannot choose | none | choose the reading that counts |
| source.reading.chosen-follows-project-rule | readings-and-apparatus.md | OK | project strict/relaxed rule | shown only via `Why` labels | partial — the rule is reflected, not settable | none | no project setting for strict/relaxed (unsure whether one exists elsewhere) |
| source.reading.machine-is-labelled | readings-and-apparatus.md | OK | `provenance_kind` on the reading; export marks | `InspectorText.Reading.maker` shown capitalised; "Machine reading, not yet checked" | yes — INSP Text | none | |
| source.reading.maker-set-by-engine | readings-and-apparatus.md | OK | engine-set `ProvenanceKind` | n/a | engine-internal (never sent by a client) | n/a | |
| source.reading.stretch-names-its-reading | readings-and-apparatus.md | OK | anchor `representation_id` + offset carry-over | `Segment.swift` maps the anchor field | engine-internal (bookkeeping) | n/a | |
| source.reading.written-read-pair | readings-and-apparatus.md | OK | `representation.pair` / `unpair` | read: `pairRole` (sic/corr) in the INSP row; write: none | partial — shown, cannot be made | none | join two readings as written/read |
| source.reading.char-confidence-on-line | readings-and-apparatus.md | OK | per-character detail on the line reading | none | no | none | show per-character confidence |
| source.hand.record | readings-and-apparatus.md | OK | `POST/GET /api/hands`, `hand.create/withdraw`, `GET /api/hands/{id}/attributions` | none | no | none | make or browse hands |
| source.hand.attributed | readings-and-apparatus.md | PARTIAL | `POST /api/hands/attributions` (`hand.attribute`); EpiDoc `handShift` → hand on `format.import` | import only: attributions arrive through PIO importPage; nothing reads them (`handsOfSegment…` uncalled) | no | none | attribute a segment to a hand; see a segment's hands |
| source.hand.not-provenance | readings-and-apparatus.md | PARTIAL | attribution vs `created_by` / `provenance_kind` | none | no | none | the Inspector shows neither the hand nor who judged it |

### rights-and-access.md (3)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.rights.record | rights-and-access.md | PARTIAL | `POST /api/rights` (`rights.set`), `…/withdraw` | none | no | none | attach a rights/consent record to a project, source or segment |
| source.rights.tighten-only | rights-and-access.md | OK | `effective_rights`; `GET /api/rights/effective` | none | engine-internal (combination rule), but nothing shows the effective answer | none | (see record: no view of effective rights) |
| source.rights.who-acts | rights-and-access.md | PARTIAL | write-check on `rights.set` | none | engine-internal (permission check) | n/a | |

### segment-editor.md (30)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.app.one-segment-store | segment-editor.md | OK | `GET /api/segments/document/{doc_id}` | STORE → `SS.listDocumentSegments`; readers OVL, PDFBOX, INSP, ReadingOrderList labels | yes (indirect: the boxes on the image/PDF) | Swift `Tests/Unit/general/Models/ImportedPageDrawsItsBoxesTests.swift::testTheImportedSyriacPageDrawsTheFilesRegionsAndLines` (recorded engine answer for a real imported PAGE file, transport stubbed) + `api/test_imported_page_draws_its_boxes.py::test_an_imported_page_s_segments_reach_the_canvas_s_call_as_the_file_s_regions_and_lines`; unit `SegmentStoreTests` | |
| source.app.index-is-the-engines | segment-editor.md | OK | seam box index | `SegmentDisplay.geometry` (placeholders; refuses gapped passes) | engine-internal / app-internal invariant (addressing) | unit `SegmentDisplayTests` | |
| source.app.edits-name-the-chosen-pass | segment-editor.md | OK | PUT `/api/artifacts/{id}/regions` | `RegionEditTarget.forDirectEdit/forSelectionEdit` in RGN | yes — preview edits in Edit Segments | none on real data; unit `RegionEditTargetTests` | imported passes have no artifact, so no edit is sent at all (caveat) |
| source.app.curated-pass-stays-on-top | segment-editor.md | OK | seam pass provenance | `OCRGeometrySelection.rankedPasses` via `SegmentDisplay.selected` in OVL/PDFBOX | yes — which boxes are drawn | unit `OCRGeometrySelectionTests.rankedPassesAuthorityBeatsRecency`, `OCRGeometryCurationAuthorityTests` | |
| source.app.overlays-draw-from-the-seam | segment-editor.md | PARTIAL | `GET /api/segments/document/{doc_id}` | OVL + PDFBOX → `SegmentDisplay.selected(for:store:)`, artifact fallback | yes — Source view image and PDF | `ImportedPageDrawsItsBoxesTests::testTheImportedSyriacPageDrawsTheFilesRegionsAndLines` + `api/test_imported_page_draws_its_boxes.py::test_an_imported_page_s_segments_reach_the_canvas_s_call_as_the_file_s_regions_and_lines` | imported-page boxes draw but cannot be selected (caveat) |
| source.app.segment-events-patch-in-place | segment-editor.md | PARTIAL | change stream `segment.*`/`pass.*` ids; `GET /api/segments/{id}` | `LibraryManager.swift:274` registers STORE (`ChangeEventConsumer`) → `SS.segment(id:)` | yes (indirect: the overlay refreshes) | engine half `api/test_change_stream_segment_ids.py::TestChangeSpecReachesSubscriber::test_changespec_segment_and_pass_ids_reach_the_subscriber`; app half unit `SegmentStoreTests.testAnEventNamingHeldSegmentsPatchesThoseAndDoesNotReload` (spec: "not yet compiled by anyone") | |
| source.editor.segment-focus | segment-editor.md | PARTIAL | n/a (UI mode) | `WindowState.isEditingSegments`; `SegmentEditingMode`; toggle in `PreviewHeadControls` and `ReaderToolbar` ("Edit Segments") | yes — preview head button + what-to-show toggle | unit `SegmentEditingModeTests` | |
| source.textedit.reader-shows-segments | segment-editor.md | PARTIAL | `document_text()` blocks; Reader HTML `GET /view/document/{id}` line map (`views.py:page_line_map`) | Reader web view (engine-rendered); `GET …/text` is not called by Swift | partial — the Reader shows the page text in order, with a hidden line map; not per-block, not editable, no line pictures | `api/test_reader_line_map.py::test_the_map_names_each_line_and_covers_its_text` (real CLM page, the Reader route) | editable per-line text in the Reader; line pictures when no Source view is open |
| source.textedit.typing-is-a-new-reading | segment-editor.md | PARTIAL | `representation.create` (maker from context) | none | no | none | type in the Reader to correct a line |
| source.textedit.return-splits-the-line | segment-editor.md | PARTIAL | `POST /api/segments/split` (`segment.split`) | none (`splitSegment…` uncalled) | no | none | Return splits a line |
| source.textedit.backspace-joins-in-reading-order | segment-editor.md | PARTIAL | `POST /api/segments/merge` (`segment.merge`) | none from the Reader (`mergeSegments…` uncalled) | no | none | Backspace joins lines |
| source.editor.one-overlay | segment-editor.md | PARTIAL | n/a | OVL (Canvas) + PDFBOX (`PDFAnnotation`), both fed by `SegmentDisplay` | yes (two renderers, one geometry source) | covered by the overlay rows above | spec wording vs platform (two renderers); no user-facing gap |
| source.editor.shapes-in-source-view | segment-editor.md | PARTIAL | PUT `/api/artifacts/{id}/regions` → `segment.convert_and_edit` | RGN (Source view) and `ArtifactPanel+Regions` (Inspector Combine) both call `ArtifactService.combineRegions` | yes — move, delete, combine, add in the Source view; Combine in the Inspector's regions panel | none on real data (route tests `test_first_edit_conversion.py`, `test_artifact_regions_edit.py`, synthetic rows) | reshaping a polygon/baseline (unsure it exists); imported pages not editable |
| source.editor.selection-shared | segment-editor.md | PARTIAL | n/a | `RegionSelection.shared` (preview ↔ Inspector); `.readerTextSelection` notification (Reader → preview); **`SegmentSelection.shared` is never written** | partial — Source view → Inspector works (artifact passes only); Reader ↔ others is text ranges; Source → Reader absent | unit `SegmentSelectionTests` only | selecting in the Reader or the Order list does not select the segment elsewhere |
| source.editor.edits-are-actions | segment-editor.md | PARTIAL | `segment.convert_and_edit` (undoable, one audit row) | RGN | yes (for the edits that exist) | none on real data; route-level synthetic `api/test_first_edit_conversion.py::TestTheFirstEditConvertsAndEdits::test_one_action_and_one_undo_step` | |
| source.editor.redo-works | segment-editor.md | PARTIAL | `POST /api/actions/audit/{id}/undo` (redo = undo of undo) | `RegionEditResult.registerUndo` / `ActionUndo.swift` | yes — Edit ▸ Redo after a region edit | none (engine `test_action_undo.py`, `TestSegmentUpdateUndoRedo`) | |
| source.editor.system-undo | segment-editor.md | PARTIAL | the audit undo route; the regions route returns `audit_id` | `ZoomableImagePreviewMac+Regions.registerRegionUndo`; `ReadingOrderStore.registerUndo` (ORDER, RLM) | yes — ⌘Z/⇧⌘Z after a region edit or a reorder | none e2e in Swift; reorder undo on real pages: `api/test_text_follows_the_order.py::test_a_move_shows_in_the_text_and_undo_restores_it_byte_for_byte` | |
| source.editor.agent-parity | segment-editor.md | PARTIAL | CLI generated surface; MCP tools | n/a | engine-internal (other surfaces) | n/a | |
| source.editor.join-group | segment-editor.md | PARTIAL | `POST /api/segments/merge` (`segment.merge`); grouping lines into a region is unbuilt | model only: `SegmentEditCommand.mergePlan` (no caller outside its tests); the existing Combine uses RGN `combineRegions` instead | partial — Combine exists (artifact regions); segment merge via the plan and grouping do not | unit `SegmentMergePlanTests` | merge by segment id; group lines into a region / ungroup |
| source.editor.set-kind | segment-editor.md | PARTIAL | `PUT /api/segments/{id}` / `PATCH /api/segments` (`segment.update(_many)`) | model only: `SegmentEditCommand.plan` — no caller | no | unit `SegmentEditCommandTests` | set a selection's kind (text/furniture) |
| source.editor.set-direction | segment-editor.md | PARTIAL | `segment.update` direction | model only: `SegmentEditCommand.plan` — no caller | no | unit `SegmentEditCommandTests` | set a direction / reverse a line |
| source.editor.set-language-script | segment-editor.md | PARTIAL | `segment.update` language/script | model only: `SegmentEditCommand.plan` — no caller | no | unit `SegmentEditCommandTests` | set a selection's language/script |
| source.editor.reorder | segment-editor.md | PARTIAL | `POST /api/reading-orders/{id}/place` (`reading_order.place`); `GET …/document/{id}`, `GET …/{id}/entries` | ORDER (drag `onMove`, ⌥⌘ arrow buttons) and RLM (Reader keys) | yes — Inspector ▸ Source ▸ Order tab, the Order section at a level, and the Reader caret keys | `api/test_text_follows_the_order.py::test_a_move_shows_in_the_text_and_undo_restores_it_byte_for_byte` (real imported pages, the place route); unit `ReadingOrderMoveTests`, `ReadingOrderStoreTests` | on-page "click segments in turn" is not built; only the `as-written` order is loaded (no picker for other named orders) |
| source.perf.worst-frame-not-mean | segment-editor.md | PARTIAL | `scripts/perf_trial` verdict | n/a | engine-internal (perf harness) | n/a | |
| source.perf.five-runs-median | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |
| source.perf.names-its-machine | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |
| source.perf.declared-fixture | segment-editor.md | OK | `scripts/perf_fixture.py` | n/a | engine-internal (fixture) | n/a | |
| source.perf.void-when-throttled | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |
| source.perf.baseline-or-fail | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |
| source.perf.memory-growth | segment-editor.md | PARTIAL | perf harness | n/a | engine-internal (perf harness) | n/a | |

### segments-and-geometry.md (52)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.segment.lasting-id | segments-and-geometry.md | OK | `segment.create/update`, engine-made ids | STORE keys by id | engine-internal (identity invariant) | n/a | |
| source.segment.rerun-is-new-pass | segments-and-geometry.md | OK | `segment.pass_create` | n/a | engine-internal (storage rule) | n/a | |
| source.segment.carry-across-a-match | segments-and-geometry.md | OK | `POST /api/segments/carry` (`segment.carry`) | none | no | none | carry readings/marks across an accepted match |
| source.segment.versioned-alone | segments-and-geometry.md | OK | `GET /api/segments/{id}/versions`, `POST …/restore-version` | none | no | none | see a segment's history, compare, restore |
| source.segment.delete-is-undoable | segments-and-geometry.md | OK | `segment.delete/undelete`; in the app via `segment.convert_and_edit` + audit undo | RGN `deleteSelectedRegions` + `registerRegionUndo` | yes — ⌫ in Edit Segments, then ⌘Z | none on real data | imported pages cannot be selected for delete (caveat) |
| source.segment.shape-kinds | segments-and-geometry.md | OK | `SourceAnchor` shapes | `AnchorShapeValue`/`SourceAnchorValue` decode points, lines, areas, time; `SegmentDisplay` draws boxes | partial — drawn as boxes; point/line/time shapes not drawn as such (unsure) | unit `SegmentMappingTests` | draw points and lines as themselves (unsure) |
| source.segment.box-is-derived | segments-and-geometry.md | OK | bbox from anchor | n/a | engine-internal | n/a | |
| source.segment.curved-baseline | segments-and-geometry.md | OK | baseline shape; `GET /api/segments/{id}/picture` levelling | none | no (baselines not drawn — unsure) | none | show and edit a line's baseline |
| source.segment.names-its-image | segments-and-geometry.md | OK | seam rendition id | `SegmentDisplay.geometry(... renditionId:)` | engine-internal (coordinate frame) | n/a | |
| source.segment.picture-by-shape | segments-and-geometry.md | OK | `GET /api/segments/{id}/picture` | none (`getSegmentPicture…` uncalled) | no | none | see a segment's cut-out picture |
| source.segment.one-primitive | segments-and-geometry.md | OK | one `Segment` table with kind | `Segment.kind` | engine-internal (model) | n/a | |
| source.segment.open-kinds | segments-and-geometry.md | OK | kind + `kind_raw` | `Segment.kind` used in INSP crumbs/counts and ReadingOrderList labels | partial — the kind is shown as a label | unit `SegmentMappingTests` | |
| source.segment.flow | segments-and-geometry.md | PARTIAL | `reading_order` of kind flow (reading straight through is GAP #5090) | none (ORDER loads only as-written) | no | none | make or follow a flow across columns/pages |
| source.segment.table-cells | segments-and-geometry.md | PARTIAL | PAGE `TableCell` → region with row/col/spans on `format.import` | via PIO importPage (boxes drawn by OVL) | partial — cells draw as boxes; row/column not shown | none via the route (format-level `test_transkribus_real_files.py`) | see a cell's row/column; make cells |
| source.table.is-a-segment | segments-and-geometry.md | PARTIAL | `table` kind on import | via import | partial — drawn as a box | none via the route | draw a table |
| source.table.cell-text-is-lines | segments-and-geometry.md | PARTIAL | cell parent on import | via import | engine-internal (structure) | n/a | |
| source.form.label-and-answer | segments-and-geometry.md | PARTIAL | `labels`/`answers` link types (`POST /api/links`) | none | no | none | link a form's label to its answer |
| source.pass.named-authored | segments-and-geometry.md | OK | `SegmentPass` name/author; `POST/DELETE /api/segments/passes` | STORE holds passes; the shown pass follows `FocusedArtifact` (Artifacts inspector) for artifact passes only | partial — no pass list; imported passes cannot be picked, hidden or compared | none | show, hide and compare passes (incl. imported ones) |
| source.pass.never-overwrites | segments-and-geometry.md | OK | pass storage | n/a | engine-internal | n/a | |
| source.pass.working-follows-project-rule | segments-and-geometry.md | OK | working-pass rule | n/a | engine-internal (rule) | n/a | |
| source.pass.working | segments-and-geometry.md | PARTIAL | action `pass.choose_working` (no typed route in the contract); export and derived text follow it | none; the overlay ranks passes itself (`OCRGeometrySelection.rankedPasses`), not by the engine's working pass | no | route-level on synthetic rows: `api/test_working_pass_across_surfaces.py` | choose the working pass; show which pass is working |
| source.order.named-multiple | segments-and-geometry.md | OK | `GET /api/reading-orders/document/{id}`, `POST /api/reading-orders` | ORDER `orders(documentId:)` — `ReadingOrderStore.load` uses the as-written one | partial — one order shown; no picker; cannot create | route tests on synthetic rows `api/test_reading_orders.py::TestSeveralOrdersOverOnePage` | choose between or create named orders |
| source.order.next-previous | segments-and-geometry.md | OK | `GET /api/reading-orders/{id}/neighbours` | none (`orderNeighbours…` uncalled) | no | none | step next/previous through a named order |
| source.link.typed | segments-and-geometry.md | PARTIAL | `POST /api/links`, `GET /api/links/types` | none | no | none | link two segments with a type |
| source.link.both-ways | segments-and-geometry.md | OK | `GET /api/links/of/{end_id}` | none | no | none | see a segment's links from either end |
| source.point.by-id-or-span | segments-and-geometry.md | OK | anchor `segment_id` / span | `SourceAnchorValue` decodes | engine-internal (pointer model) | n/a | |
| source.point.text-is-derived | segments-and-geometry.md | OK | `document_text()`; `GET …/text`; `page_content` cache | Reader shows the derived text via the engine view (Swift does not call `…/text`) | yes (indirect: Reader text follows the segments/order) | `api/test_page_text_follows_the_file.py::test_the_syriac_lines_follow_the_files_reading_order` (real file; function-level, not the route) | |
| source.point.anchor-names-its-segment | segments-and-geometry.md | OK | anchor `segment_id` on readings/marks/claims | n/a | engine-internal | n/a | |
| source.statement.old-segment-field-left-alone | segments-and-geometry.md | OK | claim `source_segment_id` unchanged | n/a | engine-internal (data invariant) | n/a | |
| source.segment.match-record | segments-and-geometry.md | OK | `POST /api/segments/matches`, `…/accept`, `…/reject` | none | no | none | review a machine's proposed match and accept or reject it |
| source.segment.forwarding-notes | segments-and-geometry.md | OK | forwarding resolution in `GET /api/segments/{id}` | `SS.segment(id:)` (resolves through forwarding, used by the STORE patch) | engine-internal (resolution; used implicitly) | n/a | |
| source.segment.citable | segments-and-geometry.md | OK | `GET /api/segments/{id}/reference` → `fichero:segment/<lib>/<doc>/<seg>` | none; no `onOpenURL` handler parses `fichero:segment` (`FicheroApp.swift:368`, `SessionStore.swift`) | no | none | copy a segment's reference; open one in the app |
| source.edit.stale-is-refused | segments-and-geometry.md | OK | `expected_version` compare-and-set | RGN edits (the refusal sentence is shown — unsure) | engine-internal (refusal) | n/a | |
| source.derived.recomputable | segments-and-geometry.md | OK | derived records name their inputs | n/a | engine-internal | n/a | |
| source.seam.read-either-store | segments-and-geometry.md | OK | `GET /api/segments/document/{doc_id}` | STORE via `SS.listDocumentSegments` | engine-internal (the app reads one call; boxes visible via OVL) | `api/test_imported_page_draws_its_boxes.py::test_an_imported_page_s_segments_reach_the_canvas_s_call_as_the_file_s_regions_and_lines` | |
| source.seam.maker-for-each-segment | segments-and-geometry.md | OK | seam `provenance_kind` | used by `OCRGeometrySelection` ranking | engine-internal (drives ranking, not shown) | n/a | |
| source.seam.provisional-ids-refused | segments-and-geometry.md | OK | typed refusal on writes | `Segment.swift` notes provisional ids | engine-internal | n/a | |
| source.events.segment-ids | segments-and-geometry.md | OK | change stream `ChangeSpec` segment/pass ids | `LibraryChangeStream` → STORE | engine-internal (plumbing; see segment-events-patch-in-place) | `api/test_change_stream_segment_ids.py::TestChangeSpecReachesSubscriber::test_changespec_segment_and_pass_ids_reach_the_subscriber` | |
| source.store.one-page-per-conversion | segments-and-geometry.md | OK | conversion action | n/a | engine-internal | n/a | |
| source.store.undo-first-edit-keeps-conversion | segments-and-geometry.md | OK | `segment.convert_and_edit` invert | reached by ⌘Z after the first region edit | engine-internal (invariant) | n/a | |
| source.store.conversion-changes-nothing-seen | segments-and-geometry.md | OK | conversion | n/a | engine-internal | n/a | |
| source.store.conversion-ids-repeatable | segments-and-geometry.md | OK | conversion ids | n/a | engine-internal | n/a | |
| source.store.converted-boxes-keep-their-maker | segments-and-geometry.md | OK | conversion provenance | n/a | engine-internal | n/a | |
| source.store.old-app-still-works | segments-and-geometry.md | OK | live geometry projection | artifact fallback in OVL/PDFBOX | engine-internal (compatibility) | n/a | |
| source.store.bounded-reads | segments-and-geometry.md | OK | filtered queries | n/a | engine-internal (performance) | n/a | |
| source.store.record-per-segment | segments-and-geometry.md | OK | per-segment rows | n/a | engine-internal | n/a | |
| source.convert.only-the-running-engine | segments-and-geometry.md | OK | project conversion lock | n/a | engine-internal (migration safety) | n/a | |
| source.convert.snapshot-first-and-proved | segments-and-geometry.md | OK | pre-conversion snapshot | n/a | engine-internal (migration safety) | n/a | |
| source.convert.refused-when-disk-is-short | segments-and-geometry.md | OK | preflight | n/a | engine-internal (migration safety; the report's surfacing in the app is unsure) | n/a | |
| source.convert.the-machine-stays-usable | segments-and-geometry.md | OK | background priority | n/a | engine-internal | n/a | |
| source.convert.stops-starts-and-repeats-safely | segments-and-geometry.md | OK | resumable runner | n/a | engine-internal | n/a | |
| source.convert.half-done-reads-the-same | segments-and-geometry.md | OK | invisibility of a partial conversion | n/a | engine-internal | n/a | |

### source-model.md (2)

| id | spec file | tag | engine | swift_caller | visible | e2e_test | gap |
|---|---|---|---|---|---|---|---|
| source.one-store | source-model.md | OK | `GET /api/segments/document/{doc_id}` (either store) | STORE/SS; `Segment.init(generated:)` | yes (indirect: boxes drawn) | `ImportedPageDrawsItsBoxesTests::testTheImportedSyriacPageDrawsTheFilesRegionsAndLines`; unit `SegmentMappingTests` | |
| source.builds-on-the-anchor | source-model.md | OK | `SourceAnchor` | `SourceAnchorValue` | engine-internal (model) | n/a | |

### Counts (by the `visible` column)

Counted by script over the table rows.

- behaviours audited: **144**
- **yes** (wired and visible, including indirect ones such as boxes drawn and the Reader text): **26**
- **partial** (reachable, but part of the behaviour has no surface): **18**
- **no**: **39** in total:
  - **3 model/service only, with no UI caller**: `set-kind`, `set-direction` and `set-language-script`, all through `SegmentEditCommand.plan`. `join-group`'s `mergePlan` is also uncalled, but that row is counted under partial because the existing Combine covers part of it.
  - **5 where some Swift touches the data** but nothing shows it: fields decoded but unshown (`lang.three-facts`, `reading.level-recorded`, `reading.read-from`), hand attributions arriving by import, and authority settings only.
  - **31 with no Swift caller at all**.
- **engine-internal**: **60**
- **unsure**: **1** (`source.geo.iiif-georef-in`)
- There is **no "service only" case among the network services**. Every `SegmentService`, `ReadingOrderService` and PageIO method has a UI caller; the unwired parts are either uncalled generated routes or the pure `SegmentEditCommand` / `SegmentSelection`.

## Table 2 — Swift types added by the source-model programme, and their callers

Callers are outside the type's own file, excluding tests. The source is `grep -w` over `fichero/fichero`, with each hit checked by reading the line (doc-comment mentions do not count).

| type | file | callers (outside own file and tests) |
|---|---|---|
| `Segment` | Models/Segment.swift | SegmentStore, SegmentService, SegmentDisplay, OCRGeometrySelection, InspectorPath, WindowState, LibraryChangeStream, ReadingOrderList, SegmentInspectorView, SegmentEditingMode (the `Segment` hits in Workflow*/ImageEdit*/BreadcrumbBuilder are other words — unsure for BreadcrumbBuilder) |
| `SegmentPassValue` | Models/Segment.swift | SegmentStore, SegmentService, SegmentDisplay, OCRGeometrySelection, InspectorPath |
| `AnchorShapeValue`, `SourceAnchorValue` | Models/Segment.swift | **no caller outside Segment.swift** (used only as `Segment`'s anchor fields; no view reads the shapes) |
| `SegmentStore` | Models/SegmentStore.swift | LibraryManager (owns it and registers it on the change stream, :274), SegmentDisplay, LibraryChangeStream, SegmentService, OCRGeometryOverlay, PDFPageView+OCRBoxes, PDFPageWithToolbar, SourceSectionView, SegmentInspectorView, ReadingOrderList, ArtifactPanel+Regions, LibraryServiceEnvironment |
| `SegmentService` (+ `SegmentServiceError`) | Services/SegmentService.swift | LibraryManager, SegmentStore, LibraryServiceEnvironment (env), SourceSectionView, SegmentInspectorView, ReadingOrderList, ArtifactPanel+Regions, ZoomableImagePreviewMac, PDFPageWithToolbar. `SegmentServiceError`: only thrown inside its own file |
| `SegmentDisplay` | Models/SegmentDisplay.swift | OCRGeometryOverlay, PDFPageView+OCRBoxes, SourceSectionView, InspectorPath, RegionEditTarget, OCRGeometrySelection, SegmentStore |
| `OCRGeometrySelection` (programme-extended: `rankedPasses`) | Models/OCRGeometrySelection.swift | SegmentDisplay, OCRGeometryOverlay, PDFPageView+OCRBoxes |
| `InspectorText` | Models/InspectorText.swift | SegmentService (`readings(segmentId:)`), SegmentInspectorView (`InspectorTextSection`) |
| `InspectorPath` | Models/InspectorPath.swift | SourceSectionView (`segmentIds(selectedIndices:…)`), SegmentInspectorView (crumbs, `kindCounts`) |
| `SegmentInspectorView` / `InspectorTextSection` (views) | Views/Inspector/Source/SegmentInspectorView.swift | SourceSectionView |
| `ReadingOrderMove` | Models/ReadingOrderMove.swift | ReadingOrderStore, ReadingOrderService, ReadingOrderList, ReaderLineMove, InspectorPath |
| `ReadingOrderStore` | Models/ReadingOrderStore.swift | ReadingOrderList, ReaderLineMove, DocumentKGWebPaneCoordinatorMacOS (`lineOrderStore`), SegmentInspectorView (via ReadingOrderList), LibraryManager |
| `ReadingOrderService` / `ReadingOrderTransport` / `ReadingOrderSummary` | Services/ReadingOrderService.swift | LibraryManager (`readingOrderService`), ReadingOrderList (env), ReadingOrderStore, DocumentKGWebPaneCoordinatorMacOS |
| `ReadingOrderList` (view) | Views/Components/ReadingOrderList.swift | SourceSectionView (Order tab), SegmentInspectorView (Order section) |
| `ReaderLineMove` | Views/Reader/Knowledge/ReaderLineMove.swift | DocumentKGWebPaneCoordinatorMacOS (`handleLineMove`/`moveLine`) |
| `RegionEditTarget` | Models/RegionEditTarget.swift | ZoomableImagePreviewMac+Regions (`commitRegionMove`, `deleteSelectedRegions`, `combineSelectedRegions`) |
| `SegmentEditingMode` (+ `SegmentEditAction`, `SegmentDeleteKeyAction`, same file) | Views/Preview/ImageViewer/Regions/SegmentEditingMode.swift | WindowState, RegionInteractionLayer, ZoomableImagePreviewMac, ZoomableImagePreviewMac+Regions |
| `SegmentEditCommand` (`plan`, `mergePlan`, `Update`, `Merge`, refusals) | Models/SegmentEditCommand.swift | **uncalled** — the only other mention is a doc comment in ReadingOrderMove.swift:14 |
| `SegmentSelection` | Models/SegmentSelection.swift | **uncalled, CONFIRMED** — referenced only by SegmentEditCommand (itself uncalled). `SegmentSelection.shared` is declared (:30) and never read or written anywhere else in the app, so nothing writes a selection into it |
| `PageExportRunner` / `PageImportRunner` | App/Menus/*.swift | ReaderExportMenuItems (ReaderExportCommands.swift:110–131), which FileMenuCommands.swift:192 and ReadingPaneView.swift:529 mount; `PageImportRunner.Outcome/Result` also in DocumentService+PageIO |
| `DocumentService.exportPage/importPage` (extension) | Services/DocumentService+PageIO.swift | PageExportRunner, PageImportRunner |


## GAPS: what the maintainer would do in the app (grouped into the issues above)

Ordered roughly by how much of the programme each unblocks.

1. **Imported pages (cross-cutting; not a spec row of its own; read from code, not run): select or edit a box on a page whose pass came from Import Page From…** Today such boxes draw but a click selects nothing: `RegionInteractionLayer` requires an artifact id, and imported passes have none. This also blocks the Inspector's segment level, reading display, move/delete/combine and delete-undo on those pages.
2. source.pass.named-authored: **show, hide and compare passes** on a page, including imported ones. Only artifact passes can be chosen, indirectly through the Artifacts inspector.
3. source.pass.working: **choose the working pass** and see which one it is. `pass.choose_working` has no typed route, and the overlay ranks passes by its own rule.
4. source.reading.set / source.textedit.typing-is-a-new-reading: **type a correction** in the Reader, which records a new reading. There is no reading write path in the app.
5. source.reading.chosen-is-worked-out: **choose the reading that counts** from the Inspector's Text list (`POST …/readings/choice` is uncalled).
6. source.reading.chosen-follows-project-rule: **set the project to strict or relaxed** (no setting found; unsure one exists).
7. source.reading.written-read-pair: **join two readings as written/read** (sic/corr). The pair is shown, but cannot be made.
8. source.reading.corrections-are-new: **see what a correction corrects**, and make one.
9. source.reading.level-recorded / source.reading.read-from / source.reading.char-confidence-on-line: **see a reading's normalisation level, its source image or reading, and per-character confidence** in the Text section.
10. source.textedit.reader-shows-segments: **edit the Reader's text line by line** (blocks per region and direction), and see line pictures when no Source view is open.
11. source.textedit.return-splits-the-line: **press Return** to split a line.
12. source.textedit.backspace-joins-in-reading-order: **press Backspace** at a line start to join it to the previous line.
13. source.editor.join-group: **merge the selected segments by id** (`SegmentEditCommand.mergePlan`, uncalled), and **group lines into a region / ungroup**.
14. source.editor.set-kind: **set the selection's kind** (text or furniture); `SegmentEditCommand.plan` is uncalled.
15. source.editor.set-direction: **set the selection's direction / reverse a line**.
16. source.editor.set-language-script and source.lang.many-per-page: **set a region's language/script**.
17. source.lang.three-facts / source.lang.says-where-from / source.lang.reading-overrides: **see a segment's or reading's language, script and encoding, and which level each came from**.
18. source.lang.cascade: **set language/script at folder/page/segment level and see the inherited value** (only the document level exists).
19. source.lang.project-declared: **declare a project script**.
20. source.dir.per-segment: **see or set a segment's direction**.
21. source.editor.selection-shared: **select a line in the Reader or the Order list and have it selected in the Source view and Inspector** (`SegmentSelection.shared` has no writer). Source → Reader is absent.
22. source.editor.shapes-in-source-view: **reshape a polygon/baseline** (unsure whether it exists), and edit imported pages (see 1).
23. source.editor.reorder and source.order.named-multiple: **pick between named reading orders, create one, and set an order by clicking segments in turn on the page**. Only as-written is loaded.
24. source.order.next-previous: **step to the next/previous segment in a named order** (neighbours route uncalled).
25. source.segment.flow: **make and follow a flow** across columns or pages.
26. source.segment.versioned-alone: **open a segment's history, compare versions, restore one**.
27. source.segment.picture-by-shape / source.segment.curved-baseline: **see a segment's cut-out, straightened picture**, and see or edit a line's baseline.
28. source.segment.shape-kinds: **draw points, lines and time spans as themselves** rather than as boxes (unsure whether they are drawn today).
29. source.segment.match-record: **review proposed matches** (accept or reject).
30. source.segment.carry-across-a-match: **carry readings and marks across an accepted match**.
31. source.segment.citable: **copy a segment's reference, and open a `fichero:segment/…` link** (no URL handler parses it).
32. source.link.typed / source.link.both-ways / source.form.label-and-answer: **link two segments with a type and see a segment's links** (incl. form label → answer).
33. source.segment.table-cells / source.table.is-a-segment: **see a cell's row and column; draw a table or its cells**.
34. source.hand.record: **create or browse hands**.
35. source.hand.attributed: **attribute a segment to a hand**, and see imported EpiDoc attributions.
36. source.hand.not-provenance: **see in the Inspector who wrote the ink versus who judged it**.
37. source.sign.declared: **declare a sign from a segment**.
38. source.sign.list-authority: **look a sign up by catalogue number**.
39. source.sign.project-list: **browse and export the project sign list**.
40. source.sign.in-readings: **see what a PUA character in a reading means**.
41. source.sign.variants: **mark a variant**.
42. source.sign.gather-instances: **gather every instance of a sign**.
43. source.rights.record: **attach a rights or consent record** to a project, source or segment. Nothing shows the effective rights either.
44. source.format.export-choices: **choose which pass, order and reading kind to export**. Today the engine's defaults are only reported.
45. source.format.first-four: **export hOCR and YOLO from the menu**, and build the menu from `GET /api/formats`.
46. source.format.everywhere: **import and export a page on iOS** (the menu is macOS only).
47. source.geo.iiif-georef-out: **export a georeferencing pass**.
48. source.geo.iiif-georef-in: the library half (#5122). Unsure whether Import Page From… already accepts the file.
49. source.geo.gazetteer-candidates: **see and choose authority or gazetteer candidates** for an entity. Only the authority settings are called.
