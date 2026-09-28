# Acceptance run: real pages in, every level back out (2026-09-27)

This run took a few pages of each hard shape from `~/Fichero Test Corpus/` and put them into
one new library, `~/Fichero Test Library/Acceptance 2026-09-27.fichero`. They went in through
the real folder import (#5132). The run then read every page back through the engine's public
surface, exported each page in its original format, and timed the main operations. The engine
ran from this branch's source on its own socket (`/tmp/fichero-acceptance.sock`), with its
own state directory and key file, so it shared nothing with the maintainer's app. It was stopped
at the end of every step.

The scripts are in `scripts/acceptance/`. `_engine.py` starts the engine and always stops it,
and the engine also exits if the script dies (`FICHERO_PARENT_PID`). The steps are
`create_library.py`, `import_corpus.py`, `readback.py`, `mcp_check.py`, `export_check.py`
and `speed.py`. `source_truth.py` reads the source files with plain lxml, not with the engine's
own readers, so the expected side of every comparison does not depend on the code under test.
Results go to `acceptance-out/` (or `ACCEPTANCE_OUT`), which is not committed.

## Import

Each folder was staged (a few pages copied), then dropped with `POST /api/ingest/folder`
(copy mode, recursive), and the run polled `GET /api/ingest/status/{id}` until it finished,
the way the app does. TEI and YOLO labels do not pair with an image by design. They went in
next through the one-file import (`fichero import page`, `POST /api/documents/{id}/import`).

| Shape | Folder | Pages | Pages with a pass | Segments | Time |
|---|---|---|---|---|---|
| Right-to-left, PAGE | Syriac, Vienna Cod. Syr. 1 | 3 | 3 | 62 | 0.53 s |
| Right-to-left, ALTO | Hebrew, BiblIA | 2 | 2 | 98 | 6.98 s |
| Vertical Chinese | Chinese, classical (CHI-KNOW-PO) | 2 | 2 | 56 | 1.67 s |
| TEI facsimile | Tale of Genji | 2 | 0 | 0 | 5.01 s (TEI refused, see below) |
| MUFI private use | Clm 13027 | 2 | 2 | 500 | 1.11 s |
| Interlinear glosses | Eutyches | 2 | 2 | 299 | 1.29 s |
| Table (TableRegion/TableCell) | Reichsanzeiger | 2 | 0 | 0 | 0.56 s (images refused, see below) |
| Table (TableRegion) | USS Albatross logbook | 1 | 1 | 759 | 0.88 s |
| ALTO in mm10 | Padeřov Bible | 2 | 2 | 346 | 2.07 s |
| ALTO in inch1200, densest page | Cherokee Phoenix p. 2 | 1 | 1 | 4,525 | 5.95 s |
| Line language tags | Rule of St Benedict | 2 | 2 | 72 | 1.69 s |
| YOLO labels | YALTAi SegmOnto | 2 | 2 (ALTO + YOLO) | 22 | 1.66 s |

Every task ended `completed`, including Reichsanzeiger, where both images were refused and
neither page got a pass.

## Read-back

Segments were matched to source elements by level and position. The engine keeps no source
element id (see the defects). A text counts as exact when the engine's reading is `==` the
source string, which after UTF-8 means byte for byte. Across all pages that went in,
**every one of 4,997 segment texts checked was exact**. That covers 100 Syriac lines and Hebrew
words with right-to-left characters, 94 words with MUFI private-use characters, 347 texts with
combining marks, and all 3,910 words of the Cherokee page. Every
segment count matched the source at every level, and every polygon survived.

| Page set | Regions | Lines | Words | Glyphs | Baselines | Language / script / direction | Nesting | Order |
|---|---|---|---|---|---|---|---|---|
| Syriac (PAGE) | pass | pass | none in source | none | pass | FAIL (block direction `ltr`) | pass | FAIL (1 step back on 2 of 3 pages) |
| Hebrew (ALTO) | pass | pass | pass | none | FAIL (lost) | FAIL (block direction `ltr`) | not readable | pass |
| Chinese vertical (PAGE) | pass | pass | none | none | pass | none in source | pass | FAIL (scrambled) |
| Clm 13027 MUFI (ALTO) | pass | pass | pass | none | FAIL (lost) | none in source | not readable | FAIL (columns interleaved) |
| Eutyches (ALTO) | pass | pass | pass | none | FAIL (lost) | none in source | not readable | FAIL |
| Albatross table (PAGE) | pass (2 tables, 436 cells) | pass | none | none | pass | none in source | pass | FAIL (112 steps back) |
| Padeřov mm10 (ALTO) | pass | pass | pass | none | FAIL (lost) | none in source | not readable | FAIL on one page |
| Cherokee inch1200 (ALTO) | pass | pass | pass (3,910) | none | none in source | none in source | not readable | FAIL (1,243 steps back) |
| Benedict (ALTO) | pass | pass | pass | none | FAIL (lost) | FAIL (line types dropped) | not readable | pass |
| YOLO SegmOnto | FAIL (drop capital read as `word`) | none | none | none | none | none | none | none |
| Genji TEI, Reichsanzeiger | not imported | | | | | | | |

No page in the corpus that went in has glyph-level shapes. None of the files state
`primaryLanguage`, `primaryScript`, `readingDirection` or ALTO `LANG` on a segment, so
language and script per segment could only be checked as "nothing invented", and nothing was.
"Not readable" under nesting means the public surface does not expose a segment's parent (see
the defects). "Order" compares the spans of the derived page text
(`GET /api/segments/document/{id}/text`) with the file's own order, and counts each step that
goes backwards.

**Through the CLI**, every level can be reached. `segments list-document` gives the shapes,
`segments list-readings` the exact text of one segment, `segments get-document-text` the page,
and `reading-orders` the orders. **Through MCP**, `fichero_segments` and `fichero_segment` give
the shapes, but no tool returns a segment's text or the page's text. An agent can list 4,525
segments and read none of them, except by exporting the whole page as XML.

## Export

Every page that has a pass exported in its original format, and every export passed
`scripts/validate_exports.py`'s schema check: 19 of 19 (PAGE 2019 or ALTO 4.4). Across all
levels, the set of texts in each export equals the set that went in. These fail:

| Check | Result |
|---|---|
| Texts in the same order as the input | FAIL on every ALTO page's words and on every PAGE page's lines (the export follows the same derived order as the text route) |
| Region membership | FAIL on PAGE: Syriac 2-3 regions became 4-16, Chinese 3 became 16, Albatross 438 became 587. Lines are placed in invented `fichero {implicit:true;}` regions, and the Chinese table-of-contents lines end up under the wrong region. |
| ALTO baselines | lost on every ALTO page (the reader never reads `BASELINE`, and the writer does not write it) |
| PAGE baselines | pass |
| Reichsanzeiger, Genji | nothing to export (404, "no pass to export") |

## Speed

The machine was a MacBookPro17,1 (M1) on macOS 27.0, running the engine from source and
measured through the CLI's own client over the Unix socket. Each figure is 5 measured runs
after 1 discarded cold run. The 1-minute load is given; other lanes kept the machine at 10-140
throughout. The segment totals come from the library's 6,739 segments.

| Operation | Median | Max | Load | Target |
|---|---|---|---|---|
| Folder import, densest page (4,525 segments, one run) | 5.95 s | — | ~20 | none |
| Pass import of the densest page's ALTO (`format.import`) | 9.77 s (2.16 s per 1,000 segments) | 14.10 s | 78.6 | none |
| List a document's segments, densest page | 381 ms | 797 ms | 14.8 | none |
| List a document's segments, 20-segment page | 20 ms | 61 ms | 14.8 | none |
| `GET /api/segments`, library scope, first 200 | 59 ms | 64 ms | 14.8 | none |
| `GET /api/segments`, library scope, last 1,000 | 146 ms | 215 ms | 14.8 | none |
| `GET /api/segments`, whole library paged by 1,000 | 583 ms | 605 ms | 14.3 | none |
| Read one line's text (readings route) | 4.3 ms | 4.6 ms | 14.3 | 100 ms edit budget (reference only) |
| Read one word's text on the densest page | 4.4 ms | 4.5 ms | 14.3 | same |
| Derive the densest page's whole text | 576 ms | 745 ms | 13.8 | see below |
| Export the densest page as ALTO | 4.73 s | 5.04 s | 11.1 | none |
| Read one line's text via the CLI process | 2.74 s | 3.04 s | 9.3 | none |

Slice 12 (`source.perf.*`) sets two numeric budgets: 16.7 ms per frame, which is for the app
and cannot be measured here, and 100 ms for an engine edit and its undo
(`engine-edit-undo`). Nothing in this run is an edit. The only engine read the spec measures is
the derived page text, recorded at about 80-100 ms warm for its generated 20,000-shape fixture.
Here the real 4,525-shape Cherokee page took 576 ms at load 14, about six times as long for a
quarter of the shapes. That difference is worth a trial of its own. The fixture's shapes are
mostly words and characters that carry no reading of their own, while every word on the
Cherokee page carries one. Import, listing, scoped listing and export have no target to compare
with. The CLI's own process start (about 2.7 s) dominates any single CLI read.

## Defects

Each defect below is one line: the call, what came back, and what was expected.

1. `POST /api/ingest/folder` on the Reichsanzeiger pages: the task reports `completed`, but each
   image fails with "Image too large for ingest (9632x6648 pixels)" (the limit is 50 MP), and
   its PAGE file becomes no pass. Expected: a real 64 MP newspaper scan imported, or at least a
   task that does not say `completed` while its pages are empty.
2. `GET /api/ingest/status/{id}`: never carries the pairing report (`imported_as_passes`,
   `unpaired`, `not_imported`). A layout file that did not become a pass is only logged in the
   engine. Expected: the report in the task status, so the app and the CLI can name the file.
3. `fichero import page <R0000022> kouigenji-01-kiritsubo.tei.xml` returns 422 "segments lie
   outside the page ... l3, l4, l5, l6", but the TEI lines have no position at all. Their place is
   the `<zone>` named by the preceding `<pb corresp>`. Expected: lines placed in their zone, or a
   refusal that says they have no geometry.
4. `fichero import page <000.jpg> 000.txt --format yolo`: `classes.txt` beside the labels is not
   sent. Class 2 (DropCapitalZone) is stored as kind `word`, and the class name is kept nowhere
   (`kind_raw` null). Expected: the class names used, or the import refused without them.
5. ALTO import drops `TextLine@BASELINE`, both the space form and the comma form: 0 of 647
   baselines on Clm, Hebrew, Eutyches, Padeřov and Benedict. The export writes none either.
   Expected: baselines kept, as on PAGE.
6. ALTO import drops `TAGREFS` block and line types (SegmOnto MainZone, DropCapitalZone,
   Benedict's LatinLine and EnglishLine). `kind_raw` is null and `metadata` is empty. Expected:
   them kept, at least as `kind_raw` or foreign.
7. `GET /api/segments/document/{id}/text` on Syriac and Hebrew pages returns every block's
   `direction` as `ltr`. Expected: `rtl` derived from the script when the file states nothing.
8. `GET /api/segments/document/{id}/text` on the two-column Clm 13027 38r interleaves the
   columns line by line (source indices 0, 61, 1, 2, 62, ...). The same happens on the Cherokee
   page (2,234 blocks for 600 lines, 1,243 backward steps). Expected: the file's block, line and
   word order, which the engine itself names `as-written`.
9. The same route on the vertical Chinese pages returns lines in a scrambled order (0, 1, 21, 7,
   11, 17, 5, ...). Expected: the file's right-to-left column order.
10. `GET /api/documents/{id}/export/pagexml` on the Syriac, Chinese and Albatross pages invents
    `fichero {implicit:true;}` regions for lines that had a region in the source (for example,
    Syriac 3 regions became 15). Lines end up in the wrong region. Expected: each line written
    inside the region it was imported in.
11. `GET /api/segments/document/{id}`, `GET /api/segments`, `GET /api/segments/{id}` and the
    MCP `fichero_segments` / `fichero_segment` tools all return `text: null` for every real
    segment, and no parent (`parent_segment_id` is not in the response). Expected: the text and
    parent a caller needs, without one readings request per segment.
12. MCP has no tool for a segment's readings, the page text, the reading orders or the scoped
    `GET /api/segments`. Expected: an agent can read the text it can already see the shapes of.
13. The engine keeps no source element id: the PAGE `@id` and ALTO `@ID` are not in
    `metadata`. Expected: kept, so a segment can be traced back to the file it came from.
14. Any request carrying `X-Fichero-Library-Path` (the first was `GET /api/health`) creates the
    named package and its missing parent folders on disk. Expected: only `POST /api/library`
    creates a library.
15. `FicheroClient(library_path="")` is documented as "explicit no library", but
    `library_path or os.environ[...]` turns `""` back into the environment's path. Expected: the
    empty string honoured.

## Re-run after the fixes (2026-09-27, evening)

The same selection and scripts, from integration at `fbc059708`, into a FRESH library,
`~/Fichero Test Library/Acceptance 2026-09-27b.fichero`. The first run's library was not
touched: `_engine.py` now takes `ACCEPTANCE_LIBRARY` (a package name under the test-library
folder), and `create_library.py` refuses an existing package rather than an existing folder.
The steps run were create_library, import_corpus, readback, mcp_check, dump, export_check and
`validate_exports.py` over the exports. speed.py was not run, because the machine's load stood
at 40-140 and its timings would have been void.

Every page that went in reads back exactly: **4,997 of 4,997 segment texts are exact**, every
count matches at every level, and every one of the 1,072 stated baselines on those pages
survives (the other 1,323 in the source files are on the Reichsanzeiger pages, which did not go
in). Checked through each segment's `parent_segment_id` against plain lxml's parents, nesting is
right for all 6,229 child segments, with none wrong. The 19 exports all validate
(`validate_exports.py`: 19 exported, 0 invalid), and none writes an invented region.

| # | Defect | Now | Evidence from the re-run | Fixed by |
|---|---|---|---|---|
| 1 | Folder import `completed` while its scans were refused | FIXED (reporting) | Reichsanzeiger: task `failed`, `error` names both scans (9448x6520, 9632x6648) and both PAGE files left out. Importing a 64 MP scan is still refused; downscaling or raising the cap is with the maintainer. | 447fe14b1 |
| 2 | No pairing report in the task status | FIXED | status carries `imported_as_passes`, `not_imported`, `unpaired` | 447fe14b1 |
| 3 | Genji TEI refused ("outside the page") | FIXED | the Genji folder drop pairs its pages with its scans: R0000022 gets page 1 (14 lines), R0000023 pages 2 and 3 (28 lines), each line anchored in its zone (left or right half). A later one-file import of the same file is a 409, because it is already there. | 8fb3c9ef1, e229e4aad, e3680c831, 1bf7fe4b3 |
| 4 | YOLO class 2 stored as `word`, no class name | FIXED | `kind_raw` DropCapitalZone, MainZone, RunningTitleZone; `classes.txt` sent with the labels | d3a08c01f, 7428fc536 |
| 5 | ALTO baselines dropped, on import and export | FIXED | 647 of 647 on the five ALTO page sets, kept and written back (`BASELINE` on every exported TextLine) | d3a08c01f |
| 6 | ALTO TAGREFS types dropped | FIXED | `kind_raw` MainZone, DefaultLine, InterlinearLine, LatinLine, MarginTextZone | d3a08c01f |
| 7 | Syriac and Hebrew blocks `ltr` | FIXED | Hebrew: every block `rtl`; Syriac: the text blocks `rtl`, the numbering zone (digits) `ltr` | 62c62fbbd |
| 8 | Clm columns interleaved; Cherokee out of order | FIXED | 0 backward steps on Clm 38r and 41v; Cherokee 0 backward steps in 3,910 spans, 600 blocks for 600 lines (was 2,234 and 1,243) | 62c62fbbd, fdfdc8fae, 76953b774 |
| 9 | Vertical Chinese lines scrambled | FIXED | 0 backward steps on both pages | 62c62fbbd |
| 10 | PAGE export invents `implicit` regions | FIXED | Syriac 3, 2, 2, Chinese 3, 4, Albatross 438 regions written, as in the source; `implicit:true` appears 0 times | d3a08c01f |
| 11 | Segment lists `text: null`, no parent | FIXED | every text-bearing segment has its text (a line whose text lives in its words, and a region, stay null); `parent_segment_id` on every segment | b16db7917 |
| 12 | MCP cannot read text | FIXED | `fichero_segment_readings`, `fichero_document_text`, `fichero_reading_orders`, `fichero_reading_order_entries`, `fichero_segments_in_scope` | 7765cbf7c |
| 13 | No source element id | FIXED | `metadata.source_id` on every segment whose element has an id; ALTO `String`s in these files carry none | d3a08c01f |
| 14 | A library header creates the package | FIXED | `GET /api/health` naming a missing package answers `unhealthy` ("Library does not exist ..."); `GET /api/documents` answers 404; nothing on disk, parent folder included | 0d777f05a |
| 15 | `FicheroClient(library_path="")` falls back to the env | FIXED | `library_path == ""` with `FICHERO_LIBRARY_PATH` set | 0d777f05a |

**New, filed:** #5145. The Albatross page reads its text region first. The file's
`<ReadingOrder>` names only that region, at index 2, and its two tables carry index 0 and 1 in
`custom="readingOrder {index:n;}"`. That leaves one backward step in the page text, and the PAGE
export writes its lines in that order. It is the only order problem left on these pages.

**Not defects, noted:**
* The vertical Chinese and Genji blocks report `ltr`. The files state no direction, and the
  engine's ruling (`language_policy._MAYBE_VERTICAL_SCRIPTS`) resolves a script that *may* be
  vertical to `ltr` rather than guessing.
* Two of the harness's own checks are now out of date. `readback.py`'s nesting check maps words
  to regions through the text route's blocks, and the blocks are now one per line, so it reports
  0 for words. Nesting checked through `parent_segment_id` is 100% right. `import_corpus.py`'s
  one-file TEI import after the folder drop gets a 409, because the folder drop now imports the
  file itself. `dump.py` could not write into a fresh `ACCEPTANCE_OUT`; `save()` now makes the
  folder.

## Directions in the Reader (2026-09-27, night)

The Reader now lays each page out in its own direction (2eba3a6dd, #5147 Reader half). An `rtl`
page gets `dir="rtl"` and a `ttb` page gets `writing-mode: vertical-rl`. A run in the other
horizontal direction becomes a `<span dir>` isolate, and the Unicode bidi algorithm orders the
text inside a line. A line move and its ⌘Z patch the one page in place instead of reloading it
(8e891c1ec, #5170).

Each file below is a real page from the Fichero Test Corpus, copied into a temporary library and
run through `format.import` with the scan size ingest records. The page's own `pageBodyMarkup` was
cut from the served `/view/document/{id}` and run in node. "Map" is the set of directions in the
served line map; "body" is the page element the Reader draws.

| Case | File | Expected | Result |
|---|---|---|---|
| a. RTL page, Maghrebi Arabic | `BULAC_MS_ARA_417_0003.xml` | rtl | PASS: map {rtl}, body `dir="rtl"`, 13 lines |
| a. RTL page, Urdu | `7219_1668198.xml` | rtl | PASS: map {rtl}, `dir="rtl"` |
| a. RTL page, Ottoman Turkish | `2939_598100.xml` | rtl | PASS: map {rtl}, `dir="rtl"`, 20 lines |
| b. Persian nastaliq with English on the page | `136_21220.xml` | rtl page; `Herbert LLoyd`, `Chunar` ltr isolates | PASS for the English lines. The digit-only line `1773` also resolves `ltr`: **FAIL, #5172** (it renders correctly, but it is reported as an English line) |
| b. LTR inside an RTL line (Hebrew line with a Latin letter) | `btv1b10539358v.xml` | the line stays rtl; bidi orders the letter | PASS: map {rtl}, one text node, bidi orders the run |
| c. Arabic with interlinear Persian (two hands, both RTL) | `1461_184094.xml` | rtl throughout | PASS: map {rtl} |
| c. Syriac with a Latin folio number | `0001_00000016.xml` (Vienna Syr. 1) | rtl page; `1v` an ltr isolate | PASS: body `dir="rtl"`, one `<span dir="ltr">1v` |
| c. Latin with Hebrew | none | ltr page, Hebrew rtl isolate | NOT RUN: the corpus has no Latin page with Hebrew on it (the Eutyches and Notre-Dame pages have none). The isolate path is covered by the Syriac case in reverse |
| d. Aljamiado (Spanish in Arabic script) | `BNE_MSS5301_Hadiz-de-los-dos-amigos.pdf_page_1.xml` | rtl, decided by the letters | PASS: its 17 text lines are rtl. Its digit-only lines `2` and `1` are `ltr`: **#5172**. The `BNE_MSS:5302_Historias_*` pages have no text in the file (every `String` has an empty `CONTENT`), so they show nothing |
| e. Chinese classical, vertical | `BULAC_BIULO_CHI_1087_1_0068.xml` | ttb from the line shapes, vertical-rl | PASS: map {ttb}, body `data-direction="ttb"` |
| e. Genji, direction stated on the source | `kouigenji-01-kiritsubo.tei.xml` + `source_setting.set direction=ttb` | ttb | **FAIL, #5171**: `document_text` blocks are `ttb`, but the served line map stays `ltr`, because the setting does not refresh the page-text cache |
| f. Mongolian, vertical-lr | none | vertical-lr | NOT RUN: the corpus has no Mongolian page. **Model gap, #5173**: `ttb` cannot say which way columns advance, so the Reader draws every `ttb` page `vertical-rl` and does not guess from the script |
| g. Caret and ⌥⌘↑ in an RTL block | `BULAC_MS_ARA_417_0003.xml` | the caret's line is the one `lineMove` names; after a real move the caret is back on it | PASS: `segmentAtOffset` names the caret's line, `lineMoveMessage` returns `{segmentId, pageId, step: "up"}`, and `caretAfterMove` lands on the moved line in the new offsets |
| g. Caret and ⌥⌘↑ in a vertical block | `BULAC_BIULO_CHI_1087_1_0068.xml` | same | PASS, same three checks; map {ttb} |

The caret and move checks are logical offsets and do not depend on direction. The DOM step (the
selection put back with `selection.collapse`) was not run in a browser here. Nothing in the
engine or in node exercises it, so it needs one look in the app.

**Fixed after the run:** #5171 in a156fd9fd (the Reader resolves each line's direction at render, so the Genji
set to `ttb` is columns at once), and #5172 in b01e0eb47 (a line with no letters takes its page's direction:
the Persian `1773`, the Aljamiado `2` and `1` and the Vienna Syriac `2` are `rtl`; `1v` stays `ltr`).

In the repo, `test_reader_directions.py` pins the rtl page, the Syriac folio isolate, the page of
columns and the caret after a move (rtl and vertical) on the vendored fixture pages. All six tests
fail on the code before 2eba3a6dd and 8e891c1ec.
