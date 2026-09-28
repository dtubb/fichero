# Interchange fixtures — files other tools wrote

**These are not ours and must never be edited.** The point of each one is that another program
produced it: a file we wrote to look like another tool's output tests our idea of that tool, and our
idea is the thing under test. If one of these fails to parse, the fix is in our reader.

| File | Source | Licence | Fetched | What it exercises |
|---|---|---|---|---|
| `ocrd_gt_aepinus_0020.page.xml` | `https://raw.githubusercontent.com/OCR-D/gt_structure_text/master/data/aepinus_bekentnis_1548/GT-PAGE/aepinus_bekentnis_1548_0020.xml` | **CC-BY-SA-4.0**, © OCR-D (`OCR-D/gt_structure_text`) | 2026-09-26 | Real PAGE XML ground truth. 49,433 bytes, 2019 namespace, 4 regions, 21 lines, 108 words, a `GraphicRegion`, baselines, a genuine `ReadingOrder`, `TextEquiv` on regions AND lines, `custom="readingOrder {index:0;} structure {type:...;}"`, and region types `heading`, `paragraph`, **`catch-word`** and **`footer`** — the last two are FURNITURE in the model's sense, which no other fixture exercises. `primaryLanguage="German"`: independent confirmation that PAGE XML's language vocabulary is NAMES. |

**Still owed: a file from eScriptorium itself.** This is OCR-D ground truth, which is a real
PAGE XML file written by another tool — but eScriptorium is the named target, its export is what a
Fichero user would bring, and its files are not identical to OCR-D's (it leans on `Baseline` and
writes the 2013 namespace in places). Recorded as residue rather than treated as equivalent.

| `altoxml_glyph_00001.alto.xml` | `https://raw.githubusercontent.com/altoxml/documentation/master/v3/Glyph/00001.xml` | **not audited** — the ALTO project publishes these as documentation examples and states no licence in the repository; recorded honestly rather than assumed | 2026-09-26 | Real ALTO from the ALTO project's own documentation corpus — **a different producer from OCR-D**, which is the point. 40,497 bytes, ALTO **v2** namespace, 7 TextBlocks, 27 TextLines, 209 Strings, and **`MeasurementUnit` `mm10`** — tenths of a millimetre, not pixels. That unit is the trap a reader assuming pixels fails silently. |

**Also read but NOT vendored:** the Bibliothèque nationale de France's own ALTO
(`use-cases/alto-dialect/ALTO-BnF-V2.xml`, 597,044 bytes, ALTO v3 namespace, `MeasurementUnit`
`pixel`, 119 TextBlocks, 433 TextLines, 2,615 Strings, ISO-8859-1 encoded). It parses and reads
correctly, and it is left out of the repository for its size. **Residue: no real PIXEL-unit ALTO
file is vendored**, so the pixel path is exercised only by our own writer's output and by the
smaller mm10 file's unit handling. A smaller real pixel-unit file is worth finding.

## eScriptorium's own exports — the residue, closed 2026-09-26

| File | Source | Licence | What it exercises |
|---|---|---|---|
| `escriptorium_export.page.xml` | `https://gitlab.com/scripta/escriptorium/-/raw/develop/app/apps/imports/tests/samples/pagexml_export_full_part1.xml` | **MIT** (eScriptorium, © 2018 Robin Tissot / PSL) | eScriptorium's OWN PAGE XML export, 2,378 bytes: `<Creator>escriptorium</Creator>`, 2019 namespace, `eSc_textblock_*` / `eSc_line_*` ids, and `custom="structure {type:title;}"` — the attribute eScriptorium uses for what PAGE XML has no element for. **This is the path a real Fichero user walks.** |
| `escriptorium_export.alto.xml` | `.../samples/alto_export_full_part1.xml` | **MIT**, same repository | eScriptorium's own ALTO export, 3,131 bytes, ALTO **v4**, `MeasurementUnit` **`pixel`** — which also closes the "no real pixel-unit ALTO file" residue recorded above. |
| `tei_consortium_testtranscr.xml` | `https://raw.githubusercontent.com/TEIC/TEI/dev/P5/Test/testtranscr.xml` (blob `31e4e1caaebf`, last commit to that path) | **CC BY 3.0 OR BSD-2-Clause**, at the user's choice (`TEIC/TEI/LICENSE.md`; attribution to the TEI Consortium is required). Chosen deliberately over a Van Gogh Letters file (CC BY-NC-SA), whose non-commercial clause cannot sit in a repository licensed AGPL. | 2026-09-26 | The TEI Consortium's own transcription test file: 3,891 bytes, a `<surface>` with a NON-ZERO ORIGIN (`ulx="358"`) and eight rectangular zones plus one polygon zone, text that points at them with `@facs` on `<s>` (not on `<lb>`), empty `<lb/>` milestones, `<sp>`/`<l>` drama with `<lb n>`, and `<subst>`/`<add>`/`<del>` transcription markup including Greek. Small and Guidelines-derived, so it is thinner than an edition; a real edition file with a permissive licence is still wanted. |

**The licence was checked BEFORE vendoring**, and that is now the rule: eScriptorium's repository is
MIT, so these files may live in an AGPL repository and in its permanent git history. A fixture under
a non-commercial or share-alike licence is not vendored however useful it is — once committed it is
in the history for good.


## The licence column, and what removing a file does not do

**The licence column belongs here from the FIRST vendored file.** It arrived after the second one
raised the question, which is one file too late: the original PAGE XML fixture came from
`OCR-D/assets`, a repository that declares **no licence at all** — worse than a restrictive one,
because a restrictive licence at least tells you where you stand. The Kant text is public domain by
age; **the ground-truth annotations are not covered by that**, and they are the part the tests
actually assert against.

**It was removed from the tree on 2026-09-26 and IT REMAINS IN GIT HISTORY.** Deleting a file does
not delete the commit that added it (`4c3187307`). That is a fact for the maintainer to decide about
before the repository is published — accept it, or rewrite history — and not something to tidy away
quietly. Flagged rather than chosen.

**Attribution, as CC-BY-SA-4.0 requires:** `ocrd_gt_aepinus_0020.page.xml` is from OCR-D's
`gt_structure_text` corpus, © OCR-D, licensed CC-BY-SA-4.0, unmodified.

## hOCR: no real engine output is vendored, and that is residue

**hOCR's tests use a fixture written BY US**, in `test_hocr_and_yolo.py`, labelled as ours in the
code. It is shaped like tesseract's output — page `bbox`, `ocr_carea`, `ocr_line` with a baseline
polynomial, `ocrx_word` with `x_wconf` — but **a file we wrote to look like tesseract tests our idea
of tesseract**, which is the trap every other fixture here exists to avoid.

Two reasons it is not a real file, both stated rather than worked around:

- `tesseract` is **not installed on this machine**, so no genuine engine output could be produced.
- The third-party hOCR available is `ocropus/hocr-tools`' conformance corpus (Apache-2.0, checked):
  its samples are minimal spec cases with **no bounding boxes at all**, so they exercise the
  microformat and none of the geometry.

**SEARCHED 2026-09-27 AND NOT FOUND. Recorded as refused rather than left open**, because "still
owed" invites someone to satisfy it with a file we wrote.

What was checked, licence metadata only — **no content was fetched from anything whose licence was
absent**:

| Candidate | Licence | Why not |
|---|---|---|
| `ocropus/hocr-tools` | Apache-2.0 | Its samples are spec-conformance minimums with **no bounding boxes at all**, so they exercise the microformat and none of the geometry. |
| `thebabellibrarybot/BabelHistoricAnnotator` | MIT | One 342-byte `example/index.html` — a page of the tool's own UI, not hOCR output. |
| `rich-info/Net-Core-hOCR` | MIT | No hOCR file in the repository at all. |
| `qurator-spk/dinglehopper`, `OCR-D/core` | Apache-2.0 | Neither ships an hOCR path; their test data is PAGE XML and ALTO. |
| `thebabellibrarybot/BabelAnno-Test`, `trevormunoz/dpi-dinglehopper-eval`, `tesseract-ocr/tessdoc` | **none declared** | Not fetched. An unlicensed fixture is worse than a missing one. |

`tesseract` is not installed on this machine, so no genuine engine output could be produced here
either — and generating one would only reproduce **our own idea of the format**, which is what the
existing fixture already is and what we now know cannot find a defect: every silent drop tonight was
caught by somebody else's file.

**So hOCR's reader is tested against a fixture we wrote, knowingly, and the gap is named rather than
papered over.** The thing that would close it is one page of tesseract `-c hocr` output from a
corpus with a declared licence, or tesseract installed here.

**YOLO needs no fixture**: the format is five numbers a line, so a file that exercises it is a file
anybody can read at a glance, and there is nothing a real one would contain that ours does not.

## A real right-to-left page — the residue that mattered most, closed 2026-09-27

Until this file, **every real fixture here was Latin-script European**, so "any language, any
direction" — the north star — was proven only against pages we built ourselves. Five defects tonight
came from somebody else's file; none could have come from ours.

| File | Source | Licence | Fetched | What it exercises |
|---|---|---|---|---|
| `tarima_arabic_0498.page.xml` | `https://raw.githubusercontent.com/calfa-co/tarima/main/page/litho/BULAC_RES_MON_4_3416_0498.xml` | **Apache-2.0**, declared and LICENSE file read before fetching (Calfa, *Tarima* project — HTR of Maghrebi Arabic documents; page from BULAC, the Bibliothèque universitaire des langues et civilisations) | 2026-09-27 | 10,928 bytes, PAGE XML **2013** namespace, one `TextRegion`, **25 `TextLine`s each with a `Baseline`**, real Maghrebi Arabic text. **It declares NO `readingDirection`, `primaryLanguage` or `primaryScript`** — which is the finding: a real Arabic corpus states none of the three, so a reader that inferred `rtl` from the text would be inventing a fact the file does not state. |

**Licence checked BEFORE fetching**, as the rule now says: the repository declares Apache-2.0 and
its `LICENSE` file is the Apache 2.0 text. Nothing was downloaded from the candidates whose licence
was absent or unstated, and the search itself only read GitHub's licence metadata.

**What is still owed**: a right-to-left page that DOES state its direction, and one page of genuine
engine hOCR. The first would exercise the writer's `rtl` path against somebody else's file rather
than ours; this one exercises the reader's honesty about absence, which is the other half.

## Tables and a page with no text — the Transkribus ecosystem, 2026-09-27

Both from `Transkribus/TranskribusDU`, **BSD-3-Clause** (© 2016-2019 NAVER LABS
EUROPE), `LICENSE` read in full before either was fetched. A different producer again:
the tool chain here is NCSR LayoutAnalysis / NCSR LineSegmentationTool inside the
Transkribus ecosystem, not eScriptorium and not OCR-D.

| File | Source | Licence | Fetched | What it exercises |
| --- | --- | --- | --- | --- |
| `transkribus_abp_table_0019.page.xml` | `https://raw.githubusercontent.com/Transkribus/TranskribusDU/master/usecases/ABP/resources/abp_150/col/S_Rinchnach_013-01_0019.xml` | **BSD-3-Clause** | 2026-09-27 | 178,004 bytes, PAGE **2013** namespace, a real parish register from the Archiv des Bistums Passau: **one `TableRegion` with 172 `TableCell`s**, 17 `TextRegion`s, 355 `TextLine`s each with a `Baseline`, 31 `SeparatorRegion`s, and `custom="readingOrder {index:N;}"` on nearly everything. **The only fixture with a table, and the only one with nesting three deep** (table → cell → line). Its `<TextEquiv><Unicode/></TextEquiv>` elements are EMPTY: layout ground truth, not a transcription, which is a state a reader can easily turn into 372 blank readings. |
| `transkribus_regions_only_0002.page.xml` | `.../TranskribusDU/spm/testVertical/M_Otter_012/page/M_Otterskirchen_012_0002.xml` | **BSD-3-Clause** | 2026-09-27 | 2,275 bytes, PAGE **2013**: three tall narrow `TextRegion`s (523 × 3171 px), three `SeparatorRegion`s, a genuine `ReadingOrder`/`OrderedGroup` over the regions — and **no `TextLine` and no text at all**. The ordinary state of a page between layout analysis and OCR, which nothing else here covers. |

**What the table file broke, and why no round trip could have found it.** `TableCell`
was not in the PAGE reader's `ELEMENT_KINDS`, so cells were skipped and the parent walk
climbed past them to the `TableRegion`. All 355 lines came back parented to the table —
and the schema forbids a `TextLine` directly under a `TableRegion`, so the export
refused: *"This element is not expected"*. **Import worked and export could not.** A
round trip could never have shown it, because our writer has never emitted a table.

Fixed by reading a cell as a `region` — which is what PAGE XML itself says a cell is
(PAGE 2019 gives a `TextRegion` inside a `TableRegion` a `TableCellRole`) — with its
`row`, `col`, `rowSpan` and `colSpan` kept in `foreign` until
`source.segment.table-cells` (#4928) gives the model fields for them.

## A file that states a fact where its own schema forbids it — 2026-09-27

| File | Source | Licence | Fetched | What it exercises |
| --- | --- | --- | --- | --- |
| `kraken_alto_multilingual_bsb00084914.alto.xml` | `https://raw.githubusercontent.com/mittagessen/kraken/main/tests/resources/alto/bsb00084914_00007.xml` | **Apache-2.0** (kraken, © Benjamin Kiessling), LICENSE read before fetching | 2026-09-27 | 58,543 bytes, ALTO **v4**, an eScriptorium export of a Hebrew manuscript from the Bayerische Staatsbibliothek: 5 blocks, 31 lines, 86 strings — and **three languages in one file**, which no other fixture has. `<Page ... LANG="hbo">` (Ancient Hebrew) plus two lines declaring `heb` and `iai` of their own. |

**The finding.** ALTO v4's schema puts `LANG` on `TextLine` and `String` and **not on
`Page`** — so this real export is non-conformant, and the fact it states is true. That
makes the honest handling asymmetric, which is worth writing down because it looks like
an inconsistency until you know why:

- the reader **keeps** `Page@LANG`. Dropping a language a file states, because it states
  it in the wrong place, would lose real information to a schema argument.
- the writer **will not emit it**. An export that does not validate is not written at all
  (`source.format.export-validated`), and `Page@LANG` fails v4 — so the page's language
  is reported as a loss instead, which is what stops it being a silent drop.

Before this file, `alto.py` asserted in a comment that "ALTO has no page-level language,
script or direction: `LANG` is per element and there is no `Page@LANG`". Half right: v4
has no *valid* one, and a real file in the wild uses one anyway.

## Still wanted, named so it is not discovered at the end

- **Vertical text.** No fixture has a `ttb` reading direction or a CJK page. The
  PAGE reader maps `ttb` to a loss on purpose (the attribute covers horizontal reading
  only), and that path has never met a real file. The `testVertical` corpus above is
  *tall narrow columns*, not vertical script — a different thing, and worth not
  confusing.
- **A real hOCR page from an engine.** Searched and refused for licence reasons; the
  table of candidates is above.
- **A real TEI edition** with a permissive licence. The Consortium's own test file is
  vendored and is thinner than an edition.
- **A Transkribus export in the 2019 namespace.** Both files here are 2013.

## IIIF Georeference Annotations (Allmaps), vendored 2026-09-27 (#5125)

Licence checked BEFORE fetching, at the source: each file's own package declares MIT in a
`LICENSE.md` and in `package.json` (the repository root declares none). The map images the
annotations point at are **not** fetched or vendored; the tests need the pixel and world
coordinates, not the pixels. Unmodified; the git blob hashes below are upstream's.

| File | Source | Licence | Blob | What it exercises |
|---|---|---|---|---|
| `allmaps_paris_thin_plate_spline.georef.json` | `github.com/allmaps/allmaps`, `main`, `packages/annotation/test/input/annotation.1.body-transformation-thin-plate-spline.json` | **MIT**, © Bert Spaan (`packages/annotation/LICENSE.md`) | `044d48c1` | The PUBLISHED dialect: georef/1 context, `SpecificResource` target, `ImageService2` source with width and height, a 4-point SVG mask, `thinPlateSpline`, four GCPs as `resourceCoords` + WGS 84 Points (a plan of Paris). Passes the checker as-is. |
| `allmaps_delft_earlier_dialect.georef.json` | same repository, `apps/cli/test/input/annotations/7a69f9470b49a744-resourceCrs.json` | **MIT**, © Manuel Claeys Bouuaert (`apps/cli/LICENSE.md`) | `b17998e6` | The EARLIER dialect: an `AnnotationPage`, a target of `type: Image` with the image service beside it, a 14-point mask, GCPs as `pixelCoords`, pixel size only in the SVG (a plan in Delft). **Fails the published checker** (no georef context, `pixelCoords`), which is true and is why the reader is tolerant and the writer strict. The `resourceCrs` in its name is a CLI option under test, not a field in the file. |
| `allmaps_qgis_no_crs.points` | same repository, `main` @ `1586076d`, `apps/cli/test/input/gcps/gcps-qgis.points` | **MIT**, © Manuel Claeys Bouuaert (`apps/cli/LICENSE.md`) | `1586076d` | A QGIS georeferencer `.points` file (#5122, `source.geo.gcp-tables`): five GCPs, **no `#CRS` line** (so the map coordinates' CRS is not stated and is held `unknown`, never assumed WGS 84), pixel y negative downwards. Its dX/dY/residual columns are identical on every row, so a tool rather than QGIS itself probably wrote them; the format is QGIS's. |
| `allmaps_qgis_laea_3035.points` | same repository, `apps/cli/test/input/gcps/gcps-qgis-projection.points` | **MIT**, as above | `1586076d` | The same five GCPs with a `#CRS:` WKT line naming **EPSG:3035** (ETRS89 / LAEA Europe): a projected CRS, held unconverted until PROJ ships (`source.geo.proj-at-build`). |

**Still wanted:** a Georeference Annotation from a second producer (Mapwarper, QGIS), so one
producer's reading of the format is not the only one tested.

**A Tesseract box file** (#5174, read-only format `tesseract-box`). Not in `corpus/`: that directory
holds files our writer must export back out, and this format is read only. Copied unmodified from
`~/Fichero Test Corpus/Cree - handwritten syllabics (Tesseract box files, no XML)/`.

| File | Source | Licence | sha256 | What it exercises |
|---|---|---|---|---|
| `zenodo_cree_syllabics_02ad26d9.box` | Handwritten Cree Syllabics, `https://doi.org/10.5281/zenodo.6915296` (`02ad26d9dee18fabb436e3042b23d94a.box`) | **CC-BY-4.0** — Zenodo record 6915296, licence field | `1bd01aa38537` | One page of Canadian Aboriginal Syllabics as 327 character boxes, `glyph left bottom right top page`, pixels from the BOTTOM-left, page 0 throughout. Its image (not vendored, 1.1 MB) is a 1560 x 2067 grayscale PNG, read from the PNG header; the tests give the page that size, as ingest records it. |
