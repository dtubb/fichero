# Interchange fixtures — files other tools wrote

**These are not ours and must never be edited.** The point of each one is that another program
produced it: a file we wrote to look like another tool's output tests our idea of that tool, and our
idea is the thing under test. If one of these fails to parse, the fix is in our reader.

| File | Source | Fetched | Licence | What it exercises |
|---|---|---|---|---|
| `ocrd_kant_0017.page.xml` | `https://raw.githubusercontent.com/OCR-D/assets/master/data/kant_aufklaerung_1784/data/OCR-D-GT-PAGE/PAGE_0017_PAGE.xml` | 2026-09-26 | **NOT AUDITED.** The `OCR-D/assets` repository declares no licence (GitHub reports none, and the README states none). The Kant text (1784) is public domain; the annotations' terms are unknown. Until confirmed this file is all-rights-reserved by default, which matters before the repository goes public. | Real PAGE XML ground truth from the OCR-D corpus (Kant, *Was ist Aufklärung?*, 1784 — the text is public domain). 89,077 bytes, 2019 namespace, 11 regions, 24 lines, `Word` elements, `Baseline` on lines, a genuine `ReadingOrder`, `TextStyle`, and `custom="readingOrder {index:0;} structure {type:heading;}"` — the attribute PAGE XML uses for what it has no element for. `primaryLanguage="German"`, which is independent confirmation that PAGE XML's language vocabulary is NAMES. |
| `tei_consortium_testtranscr.xml` | `https://raw.githubusercontent.com/TEIC/TEI/dev/P5/Test/testtranscr.xml` (blob `31e4e1caaebf`, last commit to that path) | 2026-09-26 | **CC BY 3.0 OR BSD-2-Clause**, at the user's choice (`TEIC/TEI/LICENSE.md`; attribution to the TEI Consortium is required). Chosen deliberately over a Van Gogh Letters file (CC BY-NC-SA), whose non-commercial clause cannot sit in a repository licensed AGPL. | The TEI Consortium's own transcription test file: 3,891 bytes, a `<surface>` with a NON-ZERO ORIGIN (`ulx="358"`) and eight rectangular zones plus one polygon zone, text that points at them with `@facs` on `<s>` (not on `<lb>`), empty `<lb/>` milestones, `<sp>`/`<l>` drama with `<lb n>`, and `<subst>`/`<add>`/`<del>` transcription markup including Greek. Small and Guidelines-derived, so it is thinner than an edition; a real edition file with a permissive licence is still wanted. |

**Still owed: a file from eScriptorium itself.** This is OCR-D ground truth, which is a real
PAGE XML file written by another tool — but eScriptorium is the named target, its export is what a
Fichero user would bring, and its files are not identical to OCR-D's (it leans on `Baseline` and
writes the 2013 namespace in places). Recorded as residue rather than treated as equivalent.

| `altoxml_glyph_00001.alto.xml` | `https://raw.githubusercontent.com/altoxml/documentation/master/v3/Glyph/00001.xml` | 2026-09-26 | Real ALTO from the ALTO project's own documentation corpus — **a different producer from OCR-D**, which is the point. 40,497 bytes, ALTO **v2** namespace, 7 TextBlocks, 27 TextLines, 209 Strings, and **`MeasurementUnit` `mm10`** — tenths of a millimetre, not pixels. That unit is the trap a reader assuming pixels fails silently. |

**Also read but NOT vendored:** the Bibliothèque nationale de France's own ALTO
(`use-cases/alto-dialect/ALTO-BnF-V2.xml`, 597,044 bytes, ALTO v3 namespace, `MeasurementUnit`
`pixel`, 119 TextBlocks, 433 TextLines, 2,615 Strings, ISO-8859-1 encoded). It parses and reads
correctly, and it is left out of the repository for its size. **Residue: no real PIXEL-unit ALTO
file is vendored**, so the pixel path is exercised only by our own writer's output and by the
smaller mm10 file's unit handling. A smaller real pixel-unit file is worth finding.
