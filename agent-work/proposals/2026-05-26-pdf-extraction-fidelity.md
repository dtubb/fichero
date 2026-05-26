# PDF Extraction Fidelity Audit

- Engine: `http://127.0.0.1:8799`
- Library: `/var/folders/mw/xbc46_p565j0t1msw963wlk80000gp/T/fichero-pdf-audit4.XXXXXX.fichero`
- Workflow: `Catalogue` (645b816da6ec4ae8a8cf484928e9664d)
- PDF source directory: `/Users/danieltubb/Desktop/PDFS`
- Scope: read-only fidelity audit; no product code changes

## Verdict
Belcher 2019 did not finish within the validation window and is reported separately as a stalled case. The remaining three PDFs completed and are summarized below.
On the two text-layer PDFs that completed cleanly (`salas2015venez.pdf` and `Weber - 2012 - The effects of a natural gas boom on employment an.pdf`), the per-page transcription text matches the source text on the pages I checked, but the document-level concatenation is out of order enough to drag the aggregate similarity way down. More importantly, the KG store stayed empty on every completed run: 0 entities, 0 claims.

## Per-document summary
| File | Pages | Source text pages | Transcription similarity | KG entities | KG claims | Claim support | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `belcher2019writj.pdf` | 443 | 417 | stalled | n/a | n/a | n/a | Stalled on import / workflow run |
| `salas2015venez.pdf` | 14 | 14 | 0.062 | 0 | 0 | 0/0 | Needs review |
| `Weber - 2012 - The effects of a natural gas boom on employment an.pdf` | 9 | 9 | 0.128 | 0 | 0 | 0/0 | Needs review |
| `Tubb 2006.pdf` | 26 | 0 | 1.000 | 0 | 0 | 0/0 | OK |

## Belcher 2019 WritJ
- The engine never returned a completed import/workflow result in the validation window.
- `/api/health` timed out while this run was in flight, and the engine process sat at sustained high CPU.
- Verdict: this file is not presently suitable for a bounded fidelity check in this harness; treat as a separate performance/stability issue.

## salas2015venez.pdf
- Document id: `82823a082cd5465587a37c67d32e0f00`
- Final workflow status: `completed`
- Source pages: 14 total, 14 with text-layer text
- Transcription similarity: `0.062`
- KG: 0 entities, 0 claims
- Claim support: 0/0 verifiable claims matched the source page text
- Interpretation: the first few page transcriptions match the source text exactly, but the artifact list is returned in later-page-first order (`14`, `13`, `12`, …), so concatenating artifacts in response order makes the doc-level similarity look bad even though the individual page text is faithful.
- Artifact sample:
  - `transcription` provider=`apple` model=`apple-vision` confidence=`None`
    - `14 Introduction sparked renewed interest in those countries whose earlier challenges to United States policy had already generated an upsurge in scholarly interest. As was previous…`
  - `transcription` provider=`apple` model=`apple-vision` confidence=`None`
    - `Introduction 13 However, the conservative opposition’s concerns are much deeper than simply politics or economics. Many sectors pre- sumed that oil permitted Venezuela to claim a d…`
  - `transcription` provider=`apple` model=`apple-vision` confidence=`None`
    - `12 Introduction of the government to fulfill its promise of political and socio- economic change and improve their standard of living. The social forces unleashed in the last decad…`
- Sample page comparisons:
  - Page 1: similarity `1.000`
    - actual: `INTRODUCTION The first thing most people outside of Venezuela know about the country is its former president, Hugo Rafael Chávez Frías, one of the most charismatic and controversia…`
    - extracted: `INTRODUCTION The first thing most people outside of Venezuela know about the country is its former president, Hugo Rafael Chávez Frías, one of the most charismatic and controversia…`
  - Page 2: similarity `1.000`
    - actual: `2 Introduction country outside its borders. Aside from an occasional article in National Geographic that usually highlighted the beauty of its natural environment, the purported ex…`
    - extracted: `2 Introduction country outside its borders. Aside from an occasional article in National Geographic that usually highlighted the beauty of its natural environment, the purported ex…`
  - Page 3: similarity `1.000`
    - actual: `Introduction 3 numbers had increased to 215,023. Even accounting for an undocumented population or any recent unlisted increases, Venezuela has over thirty million people, suggesti…`
    - extracted: `Introduction 3 numbers had increased to 215,023. Even accounting for an undocumented population or any recent unlisted increases, Venezuela has over thirty million people, suggesti…`

## Weber - 2012 - The effects of a natural gas boom on employment an.pdf
- Document id: `9a0a78fb61974e61bc0e9ff3b3ca5a2c`
- Final workflow status: `completed`
- Source pages: 9 total, 9 with text-layer text
- Transcription similarity: `0.128`
- KG: 0 entities, 0 claims
- Claim support: 0/0 verifiable claims matched the source page text
- Interpretation: same pattern as Salas. The page-level transcription on the checked pages is faithful, but the overall artifact order does not line up with the PDF page order, so the concatenated similarity is misleading.
- Artifact sample:
  - `transcription` provider=`apple` model=`apple-vision` confidence=`None`
    - `Brabant, S., Gramling, R., 1997. Resource extraction and ﬂuctuations in poverty: a case study. Soc. Nat. Resour. Int. J. 10, 97–106. Caselli, F., Michaels, G., 2009. Do Oil Windfal…`
  - `transcription` provider=`apple` model=`apple-vision` confidence=`None`
    - `study estimated that 88.8 billion cubic feet in gas production in 2007 would directly and indirectly create 9533 jobs in the state. According to the Energy Information Agency, the …`
  - `transcription` provider=`apple` model=`apple-vision` confidence=`None`
    - `and salary income, median household income, and the poverty rate) are .07, .07, .92, and .56. Based on the exogeneity test results, I emphasize the IV estimates for the ﬁrst two mo…`
- Sample page comparisons:
  - Page 1: similarity `1.000`
    - actual: `The effects of a natural gas boom on employment and income in Colorado, Texas, and Wyoming☆ Jeremy G. Weber ⁎ USDA/Economic Research Service, 355 E Street SW Washington, DC 20024-3…`
    - extracted: `The effects of a natural gas boom on employment and income in Colorado, Texas, and Wyoming☆ Jeremy G. Weber ⁎ USDA/Economic Research Service, 355 E Street SW Washington, DC 20024-3…`
  - Page 2: similarity `1.000`
    - actual: `production from 1998/99 to 2007/08 affected total employment, total wage and salary income, median household income, and poverty rates in the county of production in Colorado, Wyom…`
    - extracted: `production from 1998/99 to 2007/08 affected total employment, total wage and salary income, median household income, and poverty rates in the county of production in Colorado, Wyom…`
  - Page 3: similarity `1.000`
    - actual: `2.2. Empirical studies Much research explores how a country's economic dependence on natural resources affects its institutions and economic growth (see Stevens (2003) for an overv…`
    - extracted: `2.2. Empirical studies Much research explores how a country's economic dependence on natural resources affects its institutions and economic growth (see Stevens (2003) for an overv…`

## Tubb 2006.pdf
- Document id: `cfdfb074716649589c91ef305703dbcd`
- Final workflow status: `completed`
- Source pages: 26 total, 0 with text-layer text
- Transcription similarity: `1.000`
- KG: 0 entities, 0 claims
- Claim support: 0/0 verifiable claims matched the source page text
- Interpretation: the PDF has no extractable text layer in `pdftotext`/PyMuPDF, and the workflow did not emit any transcription artifacts or KG rows. That makes this file non-comparable in text-only mode.
- Sample page comparisons:
  - Page 1: similarity `1.000`
    - actual: ``
    - extracted: ``
  - Page 2: similarity `1.000`
    - actual: ``
    - extracted: ``
  - Page 3: similarity `1.000`
    - actual: ``
    - extracted: ``
