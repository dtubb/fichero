# Transcript + Catalogue Quality Evaluation — 1960 Francisco Urrutia Case

**Evaluation date:** 2026-05-31  
**Document:** 1960 Francisco Urrutia contra Compañía Minera Chocó Pacífico S.A., demanda laboral; Andagoya; Istmina  
**Source:** 13 JPG scans (Canon PowerShot SX540 HS, 5184×3888 px each), drag-dropped on 2026-05-31 at 08:50

---

## 1. Processing Status in Fichero

**The document has NOT been processed.** All 13 JPG files are `status: pending` in the active library (`app.fichero.fichero/global.fichero`, folder doc ID `104aa3ae28334ba1ae5e0f3d76049f6c`). There are zero transcription artifacts and zero catalogue artifacts for any of the Urrutia pages.

The Catalogue workflow that appears in the activity log (completed 2026-05-30 at 22:44, workflow `112d278565994505bb907ee3ecd5ee21`) ran on the `tubb2020shift - Preface.pdf`, not on the Urrutia images. The orphaned transcription artifact doc IDs (`be6b9e0390af4b91b10aa65303a817ea`, etc.) all contain Preface content.

**Implication for this evaluation:** We cannot compare Fichero's output to human ground truth on this specific run, because there is no Fichero output yet. The evaluation below is therefore a forward-looking quality baseline — it characterises the ground truth so that once Fichero does process the images, a meaningful automated comparison is possible, and it identifies the challenges the AI transcription pipeline will face.

---

## 2. Ground-Truth Summary

### What the document contains (13 pages)
The source folder has 13 JPG photos of a 1960 Colombian labour lawsuit. The human transcript covers pages labeled `_001` through `_019` (some pages have multiple scan variants; the ground-truth transcript covers pages 001–019, ~19 document leaves). The document pages include:

| Page | Document type |
|------|-------------|
| _001 / _002 | Cover-sheet index card (handwritten, abbreviated) |
| _003 | Printed index card — formal docket header |
| _004 | Envelope / folder cover — Depto. Nacional del Trabajo |
| _005 | Power of attorney — handwritten, signed by Victorino Monguíca on behalf of Urrutia |
| _006 | Virtually blank page flagged as "[guesses and uncertain]" |
| _007 | Lawyer's formal demand letter (printed, 2 pages) — core of the lawsuit |
| _008 | Secretary's certification and filing notation |
| _009 | Court's auto de admisión — typed, page 1 |
| _010 | Court's auto de admisión — typed, page 2 |
| _011 / _012 | Secretary's radicación stamp and continuation |
| _013 | Secretariat remission notice |
| _014 | Juzgado letter to Inspector de Policía de Andagoya |
| _015 | Apparently non-case page — "[REVERSED TEXT] [GUARDIA CIVIL] … [EN ALICANTE] [19-3-1950]" |
| _016 | Inspector de Policía Andagoya receipt and notification of Gerente Urke |
| _017 | Inspector's cumplimiento and remisión |
| _018 | Gerente Urke's written reply contesting the demand |
| _019 | Blank or near-blank ("[HOME] [ARTICLE I] [WE THE PEOPLE…]" — appears to be the US Constitution) |
| _021 | Gold-certificate bond text in English ("GUARANTEE / TO / THE BEARER / ON DEMAND / SUM OF TWENTY DOLLARS IN GOLD…") |

**Notable anomalies already visible in ground truth:**
- Page _015 appears to be a Spanish Civil War-era Spanish document (Guardia Civil, Alicante, 1950) accidentally included in the scan folder.
- Pages _019 and _021 are mistakenly scanned US legal/financial documents (US Constitution text, gold bond certificate) — these are clearly cross-contaminations in the folder, not part of the 1960 Colombian case.

### Human transcript fidelity conventions
The human transcribed "Daniel" used these conventions:
- `[text]` = uncertain transcription
- `[UNREADABLE TEXT]` = content present but illegible
- `[guesses and uncertain]` = acknowledgement that the entire block is speculative
- `[REVERSED TEXT]` = content appears in mirror/reverse

---

## 3. Human Catalogue — Key Extracted Fields

From the catalogue .docx:

| Field | Human-extracted value |
|-------|-----------------------|
| **Document type** | Demanda laboral ordinaria de primera instancia |
| **Date range** | 1960-05-06 to 1963-01-12 |
| **Plaintiff** | Francisco Urrutia (ex-lanchero, river worker) |
| **Plaintiff's counsel** | Ramón Lozano Garcés (abogado titulado, Quibdó) |
| **Defendant** | Compañía Minera Chocó Pacífico S.A. (domiciled Andagoya) |
| **Defendant's agent** | Gerente M.A. Burke (US citizen); Counsel Mauro Trujillo Trujillo |
| **Court** | Juzgado del Trabajo del Circuito Judicial de Istmina; appeal Tribunal Superior de Quibdó |
| **Claim** | Pension de jubilación (20 years' service + age); back-salary from 1958-10-30 |
| **Defendant's defence** | Urrutia worked only 14y 8m 10d; dismissed for embriaguez 1958-10-30 |
| **Result** | Absolution of defendant — both first instance (1961-06-28) and on appeal (1962-12-07) |
| **Key dates** | 23 dates extracted with normalised ISO dates — complete and accurate |
| **Key people** | 10 people extracted with roles and contexts |
| **Legal refs** | 16 statutory/doctrinal references (Código Sustantivo del Trabajo arts. 60, 260, 267, 65, etc.) |
| **Places** | Andagoya, Istmina, Quibdó, Condoto; Río San Juan mentioned |
| **Keyword tags** | 14 thematic tags |

---

## 4. What Fichero's AI Pipeline Will Face

This section characterises the anticipated difficulty so results can be benchmarked when processing completes.

### Transcript difficulty

**Easy / high-confidence pages:**
- Pages _009, _010: typed in a clear font, well-lit, content-dense legal text. These are the easiest and should approach ~95% accuracy.
- Page _007: typed demand letter — also reasonably legible.
- Page _016, _017: typed/stamped inspection documents.

**Medium difficulty pages:**
- Pages _005, _008: mix of typed and handwritten cursive (Victorino Monguíca's hand). Spanish cursive from 1960 with ligatures.
- Pages _001, _002, _003: handwritten or typed index cards with abbreviations. Page _002 has "Audagoya" (typo for "Andagoya") and "ago pensión" (clipped) which are authentic transcription challenges.

**Hard / likely to fail:**
- Page _006: described as "[guesses and uncertain]" — likely very faded or damaged.
- Page _011: "[UNREADABLE TEXT]" — the human couldn't read it.
- Pages _015, _019, _021: cross-contamination pages containing Spanish Civil War/US legal documents — the AI will probably transcribe these faithfully but they are not part of the case. This is a **corpus contamination problem** that Fichero should flag or handle.
- Pages _012, _013: contain stamps and marginal writing over printed forms — OCR accuracy typically drops when text overlaps rotated elements.

### Systematic risks specific to this collection

1. **Spanish accents and tildes**: The human transcript consistently uses `ñ`, `é`, `ó`, `ú` correctly. Fichero must handle these; degraded performance here creates garbled personal names ("Ramon Lozano Garces" vs "Ramón Lozano Garcés") and places ("Choco" vs "Chocó").

2. **Proper names with alternative spellings**: The court documents use "urke"/"UNKR"/"urke" (all garbled forms of the gerente's name, M.A. Burke). The human noted these variants and bracketed them as uncertain. The AI may standardise them wrongly or miss that they refer to the same person.

3. **Currency and legal notation**: "$275,00 mensuales", "m[UNREADABLE] un mil", "Cédula … 592 683" — the AI needs to preserve numeric strings accurately; OCR commonly drops or transposes digits.

4. **Cross-contamination detection**: The folder contains at least 3 pages that are clearly not part of the 1960 case. The AI pipeline should ideally flag these as outliers, not include them in catalogue extraction.

5. **Page ordering**: The human transcript processes the pages in a non-sequential order (_002, _003, _001, _004, _006, _005, _008, _009, _007, _011, _010, _012, _013, _015, _014, _016, _017, _021, _018), suggesting the physical folder is not in document order. Fichero processes by filename sort (_001–_013), which corresponds to the photographer's shot sequence, not the document's logical sequence. The catalogue will reflect the photographer's sequence, which may not match the legal narrative order.

---

## 5. Anticipated Transcript vs Ground-Truth Comparison (Prospective)

Since there are no Fichero outputs yet, here are the divergences to test for once processing completes:

### Predicted strong matches
- Typed pages (009, 010, 007, 008, 014, 016, 017): expect ≥85% of text paragraphs to match closely.
- Key proper names on typed pages: "Francisco Urrutia", "Ramón Lozano Garcés", "Compañía Minera Chocó Pacífico", "Istmina", "Andagoya".

### Predicted systematic errors (priority examples to check)
| Human transcript | Expected AI error pattern |
|-----------------|--------------------------|
| `Ramón Lozano Garcés` (consistently used) | Likely `Ramon Lozano Garces` (missing accents) |
| `Mauro Trujillo Trujillo` | Likely `Mauro Trujillo` (drops repeated surname) or OCR garbling |
| `Compañía Minera Chocó Pacífico S/A` | Likely `Compania Minera Choco Pacifico` (no accents/tilde) |
| `[UNREADABLE TEXT]` (human acknowledged inability) | AI will likely generate hallucinated text rather than flag uncertainty |
| `$275,00 mensuales` (comma as decimal separator) | Likely `$275.00` (wrong locale) or `$27500` (drops comma) |
| `Cédula … 592 683 de Istmina` | Likely `Cedula … 592683` or garbled digits |
| `justilación` (sic — appears in original doc as typo) | May correct to `jubilación` or garble further |
| Pages _015/_019/_021 (cross-contaminated) | AI transcribes faithfully but doesn't flag as non-case documents |

### Predicted catalogue accuracy
Based on what the human extracted:
- **Persons table**: AI should correctly identify Urrutia, Lozano Garcés, Trujillo. May miss Victorino Monguíca (only on the handwritten POA). May mislabel M.A. Burke as "urke" due to OCR.
- **Dates**: Should extract most major dates (filing date 1960-05-19, power of attorney 1960-05-06, demand 1960-05-18). Risk of missing the final archive date 1963-01-12 (late in process, may not be in the 13 scanned pages).
- **Summary**: Likely to describe the case correctly at a high level but may miss the outcome (absolution) since the sentencing documents appear to be outside the 13 scanned pages (the outcome dates are from 1961–1963 and the human noted the source folder only has 13 JPGs, which appear to cover only the initial filing phase through the notification to Andagoya, circa May 1960).
- **Legal references**: Human extracted 16 specific statutory citations. The AI is unlikely to identify these from the 13 pages since most citations appear in documents not included in the scanned set (the contestación and sentencia are not present).

---

## 6. Recommendations (Future GitHub Issues)

### Priority 1: Cross-contamination detection
The folder contains pages from unrelated documents (Spanish Civil War document, US Constitution text, gold bond certificate). The AI transcription pipeline has no mechanism to detect or flag pages that are clearly from a different language, era, or jurisdiction. This is a real risk for archival workflows where mixed/mis-filed pages are common.
- **Issue**: Add a per-page anomaly-detection step that flags pages with content inconsistent with the folder's inferred language/period/jurisdiction.

### Priority 2: Uncertainty preservation vs. hallucination
The human transcriber used explicit uncertainty markers (`[text]`, `[UNREADABLE TEXT]`, `[guesses and uncertain]`). For damaged or illegible pages, the AI will likely return plausible-sounding but fabricated text. For an archival use case, confident fabrication is worse than acknowledged uncertainty.
- **Issue**: Add a confidence/legibility score per page, and have the prompt instruct the model to output `[ILLEGIBLE]` or `[UNCERTAIN: ...]` for low-confidence passages rather than inventing text. Compare to what the human transcriber actually did.

### Priority 3: Spanish accent and proper-name fidelity
Systematic stripping of diacritics ("Choco" for "Chocó", "Ramon" for "Ramón") degrades searchability and creates false mismatches in entity linking. This is fixable at the prompt level.
- **Issue**: Audit transcription prompt for explicit instruction to preserve all Spanish diacritics and test on a bilingual benchmark set.

### Bonus: Page-ordering / logical-sequence awareness
Fichero ingests by filename sort; this document's pages are not in logical order. The catalogue may describe events out of sequence. Providing the model with document structure awareness (cover page, index, demand, notification, etc.) would improve catalogue coherence.
- **Issue**: Add document-type–aware page sequencing to the catalogue workflow, or expose a "reorder pages" UI so Daniel can set canonical order before running workflows.

---

## 7. Bottom Line

**Processing status:** Not yet processed. The document is present in the library as 13 pending JPGs with no transcript or catalogue output.

**When it does process, here is the honest expectation:** For the typed pages (roughly 8 of 13), Fichero should achieve reasonable transcript fidelity (~75–85% paragraph-level accuracy), with systematic degradation on Spanish diacritics and proper names. The 3 cross-contaminated pages (US Constitution, gold bond, Spanish Civil Guard) will be transcribed as if legitimate — a silent quality failure Daniel won't notice unless he checks. The 2 genuinely illegible pages will likely produce hallucinated content rather than honest "unreadable" markers.

**Top 3 improvements** that would most close the gap to human quality:
1. Diacritics instruction in the transcription prompt (low-cost, high-impact fix).
2. Confidence/uncertainty output for low-quality pages (prevents silent hallucination).
3. Cross-document-contamination detection (crucial for archival workflows where mis-filed pages are common).
