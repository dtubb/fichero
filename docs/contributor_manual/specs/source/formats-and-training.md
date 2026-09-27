# Source Model — Formats in and out, and training — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — an "Bringing work in and taking it out" section: importing a PageXML, ALTO or
> TEI project; exporting one; what each format can and cannot carry; and making a training
> set to teach a small model a new hand or script.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Evidence in `source-survey.md`. Build notes, and the decisions the real files forced on
> the way: `build-notes-formats-harness.md`. Each behaviour below carries its own tag and its
> issue — **[GAP]** was true of all of them when this was written, and the harness, PAGE XML,
> ALTO, hOCR, YOLO and the import path have since landed; TEI has not. Everything still tagged
> **[GAP]** is design unless the foundation's "What exists today" says otherwise. (Today: no PageXML,
> ALTO, TEI, MEI, hOCR or YOLO code; a Convert-to-SVG tool exists (a vision model redraws the
> page; it is not made from geometry); Parquet, IIIF, W3C annotation and RDF export ship
> through one record stream, which carries no geometry; a IIIF and W3C-annotation importer
> ships; Kraken only reads, it is not trained. `export/exporter.md` owns the exporter as a
> whole, including continuous export to disk (#4640); `importer/importer.md` owns import.
> This slice owns what the source model needs from them.)

## Intent

Fichero has its own model, richer than any standard (ruled). The standards are the ways in
and out, and every one of them goes **both ways** (ruled). A scholar can bring in years of
work from another tool, keep working, and take it out again for a publisher, an archive, or
a model trainer, and always knows what a format could not carry.

## The design

### One model in the middle and one harness, and what is built first (ruled 2026-09-19)

**PageXML, ALTO and TEI are all built first**, together with YOLO's text labels, and **every
export is validated**. The maintainer ruled one general system that makes adding a format
easy. How that is met, after review:

- **One model in the middle** (the source model's own segments, passes, orders and readings)
  and **one harness** that every format uses: validate against the format's schema; write the
  loss report; run the round-trip test. That is where the real sharing is.
- **A reader and a writer for each format against that model.** PageXML, ALTO and hOCR are the
  same shape spelled differently and share nearly everything. **TEI is not the same shape**: its
  text is a document with its own structure, and the zones on the page are a second tree the
  text points into. It gets its own reader and writer (and its own build milestone), on the
  same harness. Forcing it through a table of field-to-field mappings would produce TEI
  nobody in the field accepts.
- **What already ships stays where it is.** Parquet, IIIF, W3C annotations, RDF and CSV go out
  through the exporter's one record stream (`export_service.py`); this work makes that stream
  **carry segments**, it does not build a second one. The XML family, YOLO, Kraken's formats,
  SVG made from geometry, and the map formats are the new readers and writers. The columnar
  training set rides the existing Parquet path (ruled).
- **Rights are filtered once**, in that one stream, before any writer sees a record; not in
  fourteen writers (routed to `export/exporter.md`).
- **Validation needs real schemas on disk.** The schemas are kept with Fichero (no fetching one
  at export time, in an app that works offline); an XML validator becomes a declared
  dependency; files from outside are parsed with entities and network access off.
- **The loss report and validation are for every export**, the shipped ones included (routed).

### The rules for every format

- **A format is a mapping, not a model.** Adding one adds no fields to segments.
- **Import arrives as a new pass** with its own provenance (the file, its checksum, the tool
  that made it, when). It never overwrites what is in the project. Importing the same file
  again is recognised.
- **Nothing unrecognised is thrown away.** What the model has no field for is kept on the
  segment, labelled with its source, and written back on export to the same format.
- **Export is validated** against the format's schema where it has one. An export that does
  not validate has failed, and says so.
- **Every export comes with a loss report**: plainly, what this format could not carry ("2
  reading orders reduced to 1; 14 hand attributions dropped; 3 declared signs replaced by
  placeholders").
- **Round trip is tested**: export then import gives back the same segments, shapes, orders
  and readings, less exactly what the loss report named.
- Import and export work from the app, over MCP and from the command line, and never assume
  the engine shares a disk with the app.
- Export always says which pass, which reading order, and which kind of reading it is
  writing, with sensible defaults (the working pass; the order as written; the chosen
  reading).

### The formats

| Format | In | Out | Carries | Loses (reported) |
|---|---|---|---|---|
| **PageXML** | yes | yes | regions, lines, words, glyphs; polygons; baselines; kinds; one order; direction (four); language and script; ranked readings; simple links; the format's own z-layers | extra reading orders; typed links; hands; campaigns; editorial facts; declared signs |
| **ALTO** | yes | yes | blocks, lines, strings, glyphs; polygons; baselines; language; direction and order; alternatives and confidence; tags; processing history | as PageXML, and more of the link and kind detail |
| **TEI** | yes | yes | zones linked to text; glosses and additions with place; reorder marks; hands; editorial facts; written and read pairs; apparatus for rival readings; declared signs; free links; page furniture | fine geometry below the zone in some encodings; direction beyond a style hint |
| **MEI** | yes | yes | music zones, and the notes or neumes where a music reading exists (otherwise zones only, and the loss report says so) | polygons (its zones are boxes) |
| **W3C annotations / IIIF** | yes | yes | pointers to shapes and text; notes on notes; control points for maps (specified in `maps-and-georeference.md`) | it is not a transcription format |
| **hOCR** | yes | yes | lines, words, boxes or polygons, baselines, character cuts and confidence | most scholarly detail |
| **Transkribus and eScriptorium packages** | yes | yes | a zip of images and PageXML, optionally with a METS file: someone else's whole project | as PageXML |
| **YOLO labels** | yes | yes | a class and a box or polygon for each object | everything else |
| **Kraken training data** | yes | yes | ALTO or PageXML; line picture plus text; the compiled Arrow file | everything but lines, regions and text |
| **Columnar dataset (Arrow / Parquet)** | yes | yes | one row per segment: picture, shape, kind, reading, language, script, hand, period, source, guideline, level, licence, split | links and structure, unless asked for as extra tables |
| **Geographic** (IIIF Georeference Annotation, GCP tables, world file / GeoTIFF, GeoJSON, GeoPackage, Linked Places Format) | yes (georef, GCPs, world file) | yes | control points as segments with their CRS; the worked-out transform; places with gazetteer identifiers; places over time | specified in `maps-and-georeference.md`, whose Formats behaviours these are |
| **CSV / spreadsheet** | yes | yes | a table segment as rows and columns; each cell keeps a reference back to its segment | everything that is not the table |
| **SVG** | no | yes | the page to look at: image, shapes, text in its direction and along its baseline, descriptions | it is a picture, not data |
| **Searchable PDF** | as a source | yes | the text in place under the image; descriptions as alt text | it is a picture, not data |
| **GeoJSON, world file / GeoTIFF** | yes | yes | a georeferenced map and the places on it | everything not geographic |

### Training: from a few corrected pages to a local model

The loop:

1. A large vision model reads a few pages: regions, lines, readings.
2. A person corrects them on the page, in the editor.
3. Fichero makes a **training set** from chosen sources, pass, kinds and readings: line
   pictures (cut to the polygon, straightened on the baseline) with their readings, for a
   line recogniser (Kraken); page images with region and line shapes and kinds, for a
   segmenter (Kraken) or a layout detector (the YOLO family).
4. The small model is fine-tuned, locally or elsewhere.
5. The small model reads the rest of the collection, locally. Its output arrives as a new
   pass and new readings, like any other machine's.

What the survey established, and the design follows:

- Kraken learns from **lines**, not from cut-out characters. The unit of recognition training
  is the corrected line. Character and sign pictures still matter: for a sign classifier, for
  palaeographic comparison, and for declared signs.
- A training set is a **projection**. It is made from the project when wanted, and is never
  the record.
- Only **human-checked** readings go into a training set by default. A machine's guess must
  not be taught back to a machine as truth. A researcher can deliberately include unchecked
  readings (to bootstrap), and then the set's description says so, row by row.
- **Measuring.** A page a person has fully corrected can be marked as **ground truth**. Any
  model's pass can then be scored against it (character and word error rate, for each page
  and each hand), and the score is kept with the date, the model and the training set that
  made the model. Without this nobody can tell whether fine-tuning helped.
- The split between training, validation and test is made **by manuscript**, not by line, so
  a model is never tested on a hand it has seen.
- The engine already has a training-export route and a Hugging Face dataset bundle in hand
  (`export/exporter.md`, #4069, #2181, #1806). Training sets here **extend those**; the
  HTR-United description rides on the same bundle.
- A training set carries a **description of itself** in the field's own terms (HTR-United's:
  language, script, period, hands, volume, guidelines, licence, who did what, Unicode
  normalisation), so it can be catalogued and shared without retyping.
- Each row keeps what Kraken's own file drops: hand, script, period, source, guideline, level
  of normalisation. Mixed corpora stay usable.
- Whether training *runs inside Fichero* is a separate matter for a Kraken training spec
  (not written). This slice guarantees only that Fichero can produce, and take in, what
  training needs.

## Behaviors (every one is **[GAP]**: designed, not built; each cites its issue on milestone `source-model`, 322)

Rules for every format
- `source.format.one-model-one-harness` — **[OK]** (→ #4943) every format reads into and writes out of the one
  source model, and shares one harness for validation, the loss report and the round-trip
  test; adding a format adds a reader and a writer, and no field to segments. `formats/` holds the
  registry and `SourcePage`; **readers and writers touch no database**, which is what makes every
  format testable from a fixture with no library and stops a format learning a second way to write
  a segment. Pinned by
  `tests/unit/formats/test_harness.py::TestWritersCannotReachTheDatabase::test_the_page_a_writer_sees_holds_no_row_and_no_id_of_ours`
  and, across two formats, by
  `test_alto.py::TestTheWriterNamesItsLossesWithoutValidating::test_a_pagexml_file_crosses_to_alto_through_the_model`
  — PAGE XML in, ALTO out, with `SourcePage` the only thing between them.
- `source.format.reuses-the-one-stream` — **[GAP]** (#4943) Parquet, IIIF, W3C annotations, RDF and CSV go out
  through the exporter's existing record stream, extended to carry segments; no second stream
  is built.
- `source.format.rights-filtered-once` — **[GAP]** (#4943) restricted material is filtered in that one stream,
  not in each writer.
- `source.format.schemas-on-disk` — **[OK]** (→ #4943) schemas are kept with Fichero and validation never goes to
  the network; outside files are parsed with entities and network access off.
  `formats/schemas/` with a `PROVENANCE.md` recording every file's origin; imports are resolved
  from disk and an unvendored one **raises** rather than being fetched or ignored. Pinned by
  `tests/unit/formats/test_pagexml_read.py::TestTheFileIsParsedSafely::test_an_external_entity_is_not_resolved`
  — an archival tool is exactly the program people aim at files they did not write.
- `source.format.first-four` — **[PARTIAL]** (#4943) PageXML, ALTO, TEI and YOLO text labels are the
  first formats built on it. **PAGE XML, hOCR and YOLO are complete both ways; ALTO reads and its
  writer is complete but its export refuses** until the xlink schema ALTO imports is vendored (#5082);
  TEI is the other lane's (#4945). `first-four` is data rather than a branch: the registry is the
  only thing that knows the list, and it now holds five.
- `source.format.import-is-pass` — **[OK]** (→ #4943) an import arrives as a new pass with its provenance and
  overwrites nothing. `format.import` writes a pass, its segments, their readings and the file's
  order in four batches; the pass records `import_file` and `import_checksum` (fields slice 1 had
  already put there). Pinned by
  `tests/unit/formats/test_import_into_library.py::TestAnImportArrivesAsAPass`, including that **it
  does NOT become the working pass** (arriving is not winning — promoting it would answer a
  scholarly question with a file operation) and that a pre-existing pass's segments are identical
  afterwards.
- `source.format.reimport-recognised` — **[OK]** (→ #4943) importing the same file again is recognised, not
  duplicated silently — by the mechanism the spec names, the content hash on
  `SegmentPass.import_checksum`, and **no second dedupe table**. Pinned by
  `test_import_into_library.py::TestReimportIsRecognised`: the same bytes are a 409 naming the pass
  that already holds them, a **renamed** copy is still recognised (the hash is of content), a
  different file is accepted, and the same file on another document is accepted because the hash is
  scoped to the document.
- `source.format.keeps-unrecognised` — **[OK]** (→ #4943) content the model has no field for is kept,
  labelled, and written back on export to that format — **in a format's own round trip and through a
  library**. PAGE XML's `custom` and hOCR's `x_wconf` / baseline polynomial are read into `foreign`
  and written back, pinned by
  `test_escriptorium.py::TestTheRoundTripAUserActuallyWalks::test_escriptoriums_custom_is_written_BACK_not_merely_kept`
  and `test_hocr_and_yolo.py::TestHocrRoundTrip::test_hocrs_own_baseline_is_written_back_not_declared_lost`.
  The import keeps it on the segment's `metadata["foreign"]`
  (`::test_unrecognised_content_rides_along_on_the_segment`), and `page_export` reads it back out, so
  file → library → file loses no more than file → file does, pinned by
  `test_import_into_library.py::TestWhatTheImportKeptSurvivesTheExport::test_the_library_round_trip_keeps_it_the_way_a_format_round_trip_does`.
  It was `[PARTIAL]` until 2026-09-27 because the library-page builder mapped columns and not
  `metadata["foreign"]`: the write-back half was true format-to-format and **false
  library-to-format**, which is how it passed every round trip — a round trip never puts a library in
  the middle.
- `source.format.export-validated` — **[OK]** (→ #4943) an export is validated against its schema; an invalid
  one is a reported failure — **and no file**, because a file that exists and does not validate is
  one somebody sends to a colleague. Validation lives in the harness, so no format implements it and
  the fifth cannot forget it.
  **THE TWO-FACTS SPLIT, which is the part most likely to be "simplified" later:** a format with no
  schema BY NATURE (YOLO labels are lines of numbers) returns no problems, while a schema MISSING
  from the install **raises**. Collapsing them would make a broken install report every export as
  valid — validation passing vacuously. Pinned by
  `test_harness.py::TestValidationNeverPassesVacuously::test_a_format_with_no_schema_has_nothing_to_report`
  and `::test_a_format_whose_schema_is_missing_RAISES_rather_than_passing`. It earned its place
  immediately: validating against PRImA's real XSD found that `primaryLanguage` is a closed list of
  language NAMES, that `script` is `"Arab - Arabic"`, that the attribute is `primaryScript`, and
  that a region's `TextEquiv` must follow its lines — four defects an unvalidated writer would have
  shipped.
- `source.format.validate-a-directory` — **[OK]** (→ #4943) one command answers the question that
  matters, **does OUR export validate?**, for every interchange file in a directory, offline:
  `PYTHONPATH=fichero-server/src .venv/bin/python scripts/validate_exports.py <dir> [-r] [--inputs]`.
  **Ruled 2026-09-27: we export the latest schema, and our export is what is tested.** Every file is
  an INPUT, in whatever version: PAGE 2013, ALTO 2 or 4.3, files invalid by their own schema. Reading
  them is how material gets in. The default reads each file, writes it back out through our writer
  for its format, and validates our output against the latest schema that writer targets (PAGE
  2019, ALTO 4.4, TEI P5, IIIF georef/1). It **exits 1 only for our own failures**: an export that
  does not validate, or a recognised file we could not read or write, which is ours too. It also
  exits 1 when nothing was exported, because an empty directory is not a pass. Each input's own
  validity is printed alongside **as information**, in five outcomes: valid, INVALID, **other
  version** (a version we vendor no schema for, such as ALTO 2.x, whose schema states no licence),
  no schema, and unrecognised. PAGE 2013 and ALTO 4.2 and 4.3 are vendored so that inputs in those
  versions can be checked against their own version's schema. ALTO keeps one namespace for all of
  4.x, so the version is told by the schema file a file declares. **Real files are not all valid:**
  Kraken's ALTO omits the required `OtherTag@LABEL` and uses 4.4's `Page@LANG` while declaring 4.3.
  A Transkribus table page carries `DU_*` attributes. Allmaps' earlier-dialect annotation fails
  georef/1. Every one of them exports valid through our writer. `--inputs` checks the inputs alone.
  Pinned by
  `tests/unit/formats/test_export_validation.py::TestTheDefaultIsOurExport::test_the_fixtures_pass_because_every_one_of_our_exports_validates`,
  `::TestTheDefaultIsOurExport::test_one_invalid_export_of_ours_is_a_red`,
  `::TestTheDefaultIsOurExport::test_nothing_exported_is_not_a_pass`,
  `::TestTheScriptSaysWhatItDidNotCheck::test_a_version_we_vendor_no_schema_for_is_neither_valid_nor_invalid`,
  `::TestTheScriptSaysWhatItDidNotCheck::test_pagexml_2013_is_checked_against_2013_not_2019` and
  `::TestTheScriptSaysWhatItDidNotCheck::test_alto_4_3_is_told_from_4_2_by_the_file_it_declares`.
  **The corpus lane's files find our own failures:** run recursively over `fixtures/`, three of the
  corpus files do not export (two PAGE files, a segment with no shape written without `<Coords>`;
  one Transkribus TEI refused on read): the corpus lane's two defect classes, fixed next.
- `source.format.every-writer-is-validated` — **[OK]** (→ #4943) a format cannot ship a writer with
  nothing checking its output. The guard is parametrised over the registry, so registering a format
  adds a case, and the case fails until the format has **either** a schema or a checker written from
  its normative text **and** a file somebody else wrote, **or** an entry in a reviewed list of formats
  with no schema by nature (hOCR is HTML, YOLO is numbers), each with its reason. **Every real
  fixture, in any version, must re-export valid against the latest schema.** That check found the
  TableCell defect, and it is the one the maintainer's ruling makes central. Pinned by
  `tests/unit/formats/test_export_validation.py::test_a_format_that_writes_has_a_schema_or_says_why_not`,
  `::test_a_format_with_a_schema_has_a_third_party_file_to_export` and
  `::test_every_real_file_re_exports_valid`. To show the guard is not vacuous, both cases were
  shown firing against a throwaway format with no schema and one with a schema but no real file.
- `source.format.loss-report` — **[OK]** (→ #4943; pinned by `tests/unit/formats/test_pagexml_round_trip.py::TestTheLossesAreDeclaredNotDiscovered::test_several_readings_survive_but_WHICH_ONE_COUNTS_is_reported_lost`) every export states what it could not carry.
  **The round trip subtracts exactly what the loss report names** (ruled 2026-09-26). That makes
  honesty the acceptance criterion rather than completeness, which is the only way this work is ever
  finishable — no format carries everything. A writer that drops something silently fails its round
  trip; a writer that drops something and says so passes. So every future loss is a test change
  somebody has to write down, rather than a silent regression: **a loss discovered later is a bug, a
  loss declared in advance is a specification.**
Round trips (export then import returns the same segments, shapes, orders and readings, less
what the loss report named), one for each format that goes both ways:
- `source.format.round-trip-pagexml` — **[OK]** (→ #4944) the PAGEXML round trip holds — **and it holds
  BECAUSE the losses are declared, which is the behaviour being met rather than a caveat on it.**
  PAGE XML cannot carry which reading counts, provenance, the cascade's `level`, or a
  project-declared script; each is named by the writer, and the round trip subtracts exactly those.
  A later reader should not conclude that PAGE XML carries everything. Pinned by
  `tests/unit/formats/test_pagexml_round_trip.py` (11 tests) and, against a file another tool wrote,
  `test_pagexml_real_file.py::TestWritingItBackDeclaresWhatItLost::test_the_losses_are_the_ones_we_declared_and_nothing_silent`.
- `source.format.round-trip-alto` — **[OK]** (→ #4944) the ALTO round trip holds, now that the xlink
  schema ALTO imports is vendored (#5082). Structure, nesting, words, their text, a BCP 47 language
  and boxes to a pixel of the declared page; script, direction and alternative readings are named by
  the writer and subtracted, because ALTO carries geometry and text and little else. Pinned by
  `tests/unit/formats/test_alto.py::TestTheAltoRoundTrip` (5 tests).
- `source.format.round-trip-tei` — **[GAP]** (#4945) the TEI round trip holds.
- `source.format.round-trip-hocr` — **[OK]** (→ #4944) the HOCR round trip holds, to a pixel of the
  page's own declared `bbox`, with hOCR's own properties written back rather than declared lost.
  Pinned by `tests/unit/formats/test_hocr_and_yolo.py::TestHocrRoundTrip` (3 tests: the words and
  their text, the boxes to a pixel, and hOCR's own baseline written back).
- `source.format.round-trip-yolo` — **[OK]** (→ #4944) the yolo round trip holds **for the geometry**,
  which is what the format carries; everything else is in the loss report and the round trip
  subtracts exactly that. Identity cannot survive a format with no ids, so the comparison is by
  sequence and position — the rule that already applies everywhere, made unavoidable here. Pinned by
  `test_hocr_and_yolo.py::TestYoloIsHonestAboutLosingAlmostEverything::test_the_geometry_survives_and_that_is_what_round_trips`
  and `::test_the_centre_first_conversion_is_not_off_by_half_a_box`.
- `source.format.round-trip-columnar` — **[GAP]** (#4946) the columnar round trip holds.
- `source.format.export-choices` — **[OK]** (→ #4943) an export names the pass, reading order and reading kind
  it writes, with defaults. Pinned by
  `fichero-cli/tests/test_export_page_command.py::test_export_page_calls_the_one_route_with_the_choices`
  and by the route's own `test_page_export_route.py`. (The CLI test root was outside `TEST_ROOTS`
  until 2026-09-27, so this behaviour's only evidence was in the one place the pipeline could not
  read — which is why it still read `[GAP]`.)
- `source.format.everywhere` — **[OK]** (→ #4943) import and export work from the app, MCP and the
  command line, with a remote engine. One engine route each way and three thin surfaces over them,
  so no surface has an import or export path of its own.
  **Out**: `GET /api/documents/{id}/export/{format}`, `fichero export page`
  (`fichero-cli/tests/test_export_page_command.py`), `fichero_page_export`
  (`fichero-mcp/tests/test_mcp_server.py::test_page_export_builds_the_route_and_returns_the_choices_and_losses`).
  **In**: `POST /api/documents/{doc_id}/import`
  (`test_import_into_library.py::TestTheImportRoute`), `fichero import page`
  (`fichero-cli/tests/test_import_page_command.py`), `fichero_page_import`
  (`test_mcp_server.py::test_page_import_posts_the_file_and_hands_back_what_landed`).
  The CLI mirrors the app's honesty rather than reporting success: the format that was
  **recognised**, a note when the file's name disagreed with its bytes, the count of shapes the
  engine repaired, and — pinned by
  `test_import_page_command.py::test_reimporting_the_same_bytes_is_an_answer_with_status_zero` —
  **status 0** for a re-import of the same bytes, because a nightly script must not break on "you
  already have this" and must still be able to tell it from a file that was refused. On MCP the loss
  report and the repair count are handed back as data, since a model told only that a file was
  written will describe it as complete.
  This entry read "**Neither on MCP, and no CLI import**" until 2026-09-27, and the first half was
  wrong when it was written: `fichero_page_export` landed in the same commit as the CLI's export
  (`6a458b251`, whose subject says "the route, the CLI and MCP"). The tag was written from what the
  spec's prose expected rather than from the MCP server, which is the error this programme keeps
  making in different costumes.

Each format (one import and one export behaviour each)
- `source.format.pagexml-in` · `source.format.pagexml-out` — **[OK]** (→ #4944). `pagexml-in` is pinned by
  `test_pagexml_real_file.py::TestReadingARealFile` (13 tests) against **OCR-D ground truth**, not a
  file we wrote: a lookalike would test our idea of the format. Reading 2013 and 2019 namespaces,
  writing 2019 (the choice is empirical — see the note at the writer).
- `source.format.alto-in` — **[OK]** (→ #4944), pinned by `test_alto.py::TestReadingARealAltoFile` against a
  real file from the ALTO project's own corpus, in the **v2** namespace with `MeasurementUnit`
  `mm10`. Normalised coordinates are unit-free (the page declares its size in the same unit); a
  non-pixel page reports **no** pixel grid rather than a wrong one, and an unknown unit is refused
  rather than assumed.
- `source.format.alto-out` — **[OK]** (→ #4944): the writer emits and validates against **ALTO 4.4**,
  the latest release (ruled 2026-09-27), declaring it (`SCHEMAVERSION` and the schema file, since
  4.x shares one namespace), and names what it cannot carry. `Page@LANG`, which 4.4 added, is
  written when it is a BCP 47 tag and is no longer a loss
  (`test_alto.py::TestARealHebrewExportStatesItsLanguageWhereAltoDoesNotAllowIt::test_the_page_language_is_written_back_in_4_4_and_is_no_longer_a_loss`). It also invents the `TextBlock` and `TextLine` a bare `String` needs
  (→ #5084) — **marked `fichero-implicit-` and dropped again on re-import**, so a scholar who exports
  and re-imports gets their word back rather than a block nobody drew. Pinned by
  `test_alto.py::TestTheImplicitParentIsWrittenAndMarked` (5 tests, including that a real page with
  proper parents invents nothing).
- `source.format.tei-in` · `source.format.tei-out` — **[OK]** (→ #4945), pinned by
  `tests/unit/formats/test_tei.py::TestTheRoundTripHolds` — granularity and nesting, language,
  script and direction both ways, right-to-left text byte for byte, shapes and baselines to the
  pixel, the reading order as a sequence, and words as segments inside their line. **Residue:** no
  real third-party TEI file is vendored (the one found was CC BY-NC-SA, which cannot go into this
  repository's history), so TEI is the one format whose reader is tested only against our own
  output — the weakness a real file exposed three times in PAGE XML.
- `source.format.mei-in` · `source.format.mei-out` **[GAP]** (#4945)
- `source.format.w3c-in` · `source.format.w3c-out` **[GAP]** (#4946)
- `source.format.hocr-in` · `source.format.hocr-out` — **[OK]** (→ #4944), pinned by
  `tests/unit/formats/test_hocr_and_yolo.py::TestReadingHocr` and `::TestHocrRoundTrip`.
  **hOCR is the honest `schema=None` case**: HTML with an agreed microformat, so there is nothing to
  validate against — a different fact from a schema missing off an install, which raises. It is read
  with an **HTML** parser, not the XML one (real engine output has unclosed `<meta>` tags; our own
  writer's output proved it). `x_wconf`, `x_size` and the baseline POLYNOMIAL are kept verbatim and
  written back, rather than converted into points that would claim a precision the file lacks.
  **Residue**: the fixture is ours, not a real engine's — `tesseract` is not installed here and the
  Apache-2.0 third-party corpus has no bounding boxes (see `fixtures/PROVENANCE.md`).
- `source.format.foreign-package-in` · `source.format.foreign-package-out` — **[GAP]** (#4946) a Transkribus or
  eScriptorium project as a whole.
- `source.format.yolo-in` · `source.format.yolo-out` — **[OK]** (→ #4944), pinned by
  `test_hocr_and_yolo.py::TestYoloIsHonestAboutLosingAlmostEverything`. Five numbers a line, so
  **YOLO is the loss report's hardest case and its best evidence**: no text, no language, no order,
  no nesting, no identity, and the writer names every one of those. A format that carries four
  numbers per box SHOULD produce a long report, and a short one would mean the writer was not
  looking. The centre-first conversion (YOLO stores a box's centre, the model its top-left corner)
  is pinned on its own, because it is the half-a-box error a naive reader makes. A malformed line is
  **refused, never skipped** — a training set with silently dropped boxes teaches a model to miss
  exactly those.
- `source.format.kraken-in` · `source.format.kraken-out` **[GAP]** (#4946)
- `source.format.columnar-in` · `source.format.columnar-out` **[GAP]** (#4946)
- `source.format.geo-in` · `source.format.geo-out` **[GAP]** (#4946, → #5125, #5126) umbrellas for the geographic
  formats; each is specified and tracked in `maps-and-georeference.md`'s Formats behaviours.
- `source.format.table-in` · `source.format.table-out` — **[GAP]** (#4946) a table segment as CSV or a
  spreadsheet, each cell carrying a reference to its segment.
- `source.format.svg-out` — **[GAP]** (#4946) the page as SVG, text in its direction and along its baseline,
  with descriptions.
- `source.format.pdf-out` — **[GAP]** (#4946) a searchable PDF with text in place and descriptions as alt text.

Training
- `source.train.set-from-selection` — **[GAP]** (#4947) a training set is made from chosen sources, pass, kinds
  and readings.
- `source.train.line-pictures` — **[GAP]** (#4947) line pictures are cut to the polygon and straightened on the
  baseline.
- `source.train.human-checked-by-default` — **[GAP]** (#4947) only human-checked readings are included by
  default; including others is deliberate and is recorded row by row in the set.
- `source.train.ground-truth` — **[GAP]** (#4947) a fully corrected page can be marked as ground truth.
- `source.train.measured` — **[GAP]** (#4947) a model's pass can be scored against ground truth by page and by
  hand, and the score is kept with the date, model and training set.
- `source.train.model-lineage` — **[GAP]** (#4947) a pass made by a fine-tuned model names that model, and the
  model names the training set it came from.
- `source.train.split-by-manuscript` — **[GAP]** (#4947) training, validation and test are split by manuscript.
- `source.train.self-describing` — **[GAP]** (#4947) a training set carries a description in HTR-United's terms.
- `source.train.rows-keep-context` — **[GAP]** (#4947) each row keeps hand, script, period, source, guideline
  and level.
- `source.train.sign-pictures` — **[GAP]** (#4947) pictures of characters and declared signs can be exported as
  a labelled set.
- `source.train.output-is-pass` — **[GAP]** (#4947) a fine-tuned model's output arrives as a new pass and new
  readings.
- `source.train.projection-only` — **[GAP]** (#4947) a training set is made on demand and is never the record.

## Test matrix

To be filled at approval. Each format needs a real sample file from the field as a fixture,
and its schema for validation.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
