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

**Still owed: one page of real engine hOCR** — tesseract `-c hocr` output, or a sample from a
digitisation whose licence is declared. Until then hOCR's reader is tested against our own idea of
the format, exactly the weakness that a real PAGE XML file exposed three times in one evening.

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
