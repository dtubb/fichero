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
