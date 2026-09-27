# Interchange fixtures — files other tools wrote

**These are not ours and must never be edited.** The point of each one is that another program
produced it: a file we wrote to look like another tool's output tests our idea of that tool, and our
idea is the thing under test. If one of these fails to parse, the fix is in our reader.

| File | Source | Fetched | What it exercises |
|---|---|---|---|
| `ocrd_kant_0017.page.xml` | `https://raw.githubusercontent.com/OCR-D/assets/master/data/kant_aufklaerung_1784/data/OCR-D-GT-PAGE/PAGE_0017_PAGE.xml` | 2026-09-26 | Real PAGE XML ground truth from the OCR-D corpus (Kant, *Was ist Aufklärung?*, 1784 — the text is public domain). 89,077 bytes, 2019 namespace, 11 regions, 24 lines, `Word` elements, `Baseline` on lines, a genuine `ReadingOrder`, `TextStyle`, and `custom="readingOrder {index:0;} structure {type:heading;}"` — the attribute PAGE XML uses for what it has no element for. `primaryLanguage="German"`, which is independent confirmation that PAGE XML's language vocabulary is NAMES. |

**Still owed: a file from eScriptorium itself.** This is OCR-D ground truth, which is a real
PAGE XML file written by another tool — but eScriptorium is the named target, its export is what a
Fichero user would bring, and its files are not identical to OCR-D's (it leans on `Baseline` and
writes the 2013 namespace in places). Recorded as residue rather than treated as equivalent.
