# The real-file corpus: pages other people's software wrote (#5130)

**These are not ours and must never be edited.** Same rule as `../PROVENANCE.md`, whose
precedent this follows: each file is here because another program wrote it, and a file
we edited to make a test pass would test our idea of that program instead.

`tests/unit/formats/test_real_corpus.py` globs this directory, so a file added here is
tested with no code change. **What is tested is OUR export**: whatever version a file
arrives in, it must be recognised from its bytes, import, go out through our writer
valid against the schema we export, and lose nothing the loss report does not name. A
source that is invalid by its own schema, or in an old version, is recorded below as
information about that file — never a failing test. **Add a row here in the same
commit**; the test fails on a file with no row.

**Naming:** `<producer>_<language-or-script>_<short-id>.<page|alto|tei>.xml`, or `.hocr`.

**Licences were read BEFORE anything was downloaded**, and where they were read is in
each row. Nothing with a NonCommercial or NoDerivatives clause, or with no stated
licence, is vendored: this repository is AGPL and git history is permanent. ShareAlike
without NC is accepted, as in `PROVENANCE.md` (the OCR-D fixture is CC-BY-SA-4.0).
**Attribution**, as the CC-BY / CC-BY-SA / Apache licences require, is the row itself:
each file is unmodified, from the named project, under the named licence.

Each row ends with the first 12 hex digits of the file's sha256, so a later copy can be
checked against what was vendored.

## Vendored

| File | Source | Licence, and where it was read | Fetched | What only this file covers |
|---|---|---|---|---|
| `calfa_chinese-vertical_chi1087-0065.page.xml` | `https://raw.githubusercontent.com/calfa-co/chi-know-po/main/page/BULAC_BIULO_CHI_1087_1/BULAC_BIULO_CHI_1087_1_0065.xml` | **Apache-2.0** — repository `LICENSE` (GitHub licence API `apache-2.0`); HTR-United's catalogue lists the dataset as CC-BY 4.0. Both permissive. | 2026-09-27 | **The only CJK page and the only true vertical script.** Classical Chinese (`lzh`, Hant) manuscript from BULAC, 11,451 B, PAGE 2013, Calfa. 3 regions, 25 lines whose **baselines run top to bottom** (e.g. `2500,1390 2511,2272`) in columns stepping right to left. **It states no `readingDirection`, no `textLineOrder`, no language** — so it reads as direction `None`, honestly, and nothing in the model knows it is vertical. sha256 `102164c71944` |
| `transkribus_multidirection_cpas2000.page.xml` | `https://raw.githubusercontent.com/mittagessen/kraken/main/tests/resources/page/cPAS-2000.xml` | **Apache-2.0** — kraken's `LICENSE` (GitHub licence API) | 2026-09-27 | **The only file that STATES `top-to-bottom`, and states all four directions on one page** (`left-to-right` on the page, `bottom-to-top`, `right-to-left` and `top-to-bottom` on regions). Transkribus (`TRP`) 2013, 25,871 B; `primaryLanguage` English and Polish plus `custom="language {type: hbo;}"`; an `ImageRegion`; 97 lines and no text. **It declares the namespace as `https://schema.primaresearch.org/...`** — the wrong scheme, so it is not strictly PAGE — and our reader accepts it. All four directions round-trip with no loss. sha256 `07cd4c9ff5ca` |
| `calfa_arabic-baseline-only_rasam417-0010.page.xml` | `https://raw.githubusercontent.com/calfa-co/rasam-dataset/main/page/rasam1/BULAC_MS_ARA_417_0010.xml` | **Apache-2.0** — repository `LICENSE` (GitHub licence API) | 2026-09-27 | Maghrebi Arabic (RASAM, BULAC MS ARA 417), 4,671 B, PAGE 2013. **Every line is a baseline with an EMPTY polygon: `<Coords points=""/>`.** Imports; **export refused** (#5130) — see findings. sha256 `365a72ef23ca` |
| `escriptorium_syriac_onb-syr1-0001.page.xml` | `https://raw.githubusercontent.com/HTR-School-Vienna/2024--Syriac/main/%C3%96NB_Syr_1/page/0001_00000016.xml` | **CC-BY-SA-4.0** — repository `LICENSE.md` (GitHub licence API `CC-BY-SA-4.0`); the Zenodo deposit 14714089 says CC-BY-4.0 | 2026-09-27 | **The only right-to-left page in the PAGE 2019 namespace**, so the only RTL file whose SOURCE is schema-validated. Syriac (Serto), ÖNB Cod. Syr. 1, eScriptorium's own export, 6,253 B, 4 regions, 12 lines. No direction stated. sha256 `abd92d420878` |
| `escriptorium-transkribus_syriac_smmj36-0004.page.xml` | `https://raw.githubusercontent.com/HTR-School-Vienna/2025-syriac/main/SMMJ_00036/page/0004_SMMJ_00036__009.xml` | **CC-BY-4.0** — Zenodo record 18157525 licence field; GitHub mirror says CC-BY-SA-4.0 | 2026-09-27 | Syriac, St Mark's Monastery Jerusalem MS 36, 84,613 B. **A file that went eScriptorium → Transkribus**: `<Creator>escriptorium</Creator>` beside a `<TranskribusMetadata>` block, PAGE 2013, 10 regions, 138 lines — **and an `eSc_dummyblock_` region with no `<Coords>` at all**, which its own schema requires. Export refused (#5130). sha256 `d3c613a1bc78` |
| `transkribus_greek-polytonic_vatgr2228-0036.page.xml` | Zenodo 20705757, `dataset.zip` → `dataset/pagexml/vat_gr_2228/Vat.gr.2228.pt.1_0036_fa_0015v.xml` | **CC-BY-SA-4.0** — Zenodo record 20705757 licence field | 2026-09-27 | **The only Greek**: medieval polytonic (breathings and accents, e.g. `ἐξηγήσαντο`), Vat. gr. 2228, Transkribus, PAGE 2013, 8,101 B, 1 region, 7 lines. sha256 `b73f47f21068` |
| `transkribus_newa-pracalit_vetala-0221.page.xml` | Zenodo 6967421, `export_job_3435367.zip` → `.../page/MS B Vetala 6414-0221.xml` (one member extracted) | **CC-BY-4.0** — Zenodo record 6967421 licence field | 2026-09-27 | **The only Brahmic manuscript script in a Unicode block outside the BMP** (Newa, U+11400–1147F): Pracalit for Sanskrit/Newar, 3,703 B, PAGE 2013, and a `<Creator>` that is a CITlab/PLANET provenance string with a newline in it. sha256 `61807c7a4805` |
| `transkribus_spanish-notarial_0074.page.xml` | `https://raw.githubusercontent.com/mittagessen/kraken/main/tests/resources/170025120000003,0074.xml` | **Apache-2.0** — kraken's `LICENSE` | 2026-09-27 | **Early-modern Spanish notarial register** (Transkribus `TRP`, PAGE 2013, 22,925 B): 4 regions, 44 lines, text on regions AND lines, and the transcribers' **inline abbreviation and tag conventions** (`dho$.dicho`, `$ofi:Patron`, `$ant:Miguel`). sha256 `1758f378927b` |
| `escriptorium_spanish-medieval_bnfesp33.alto.xml` | `https://raw.githubusercontent.com/HTRogene/spanish/main/data/paris-bnf-esp-33/btv1b10033775d-f6.xml` | **CC-BY-4.0** — repository `htr-united.yml` and `README.md` ("licensed under ... CC BY 4.0") | 2026-09-27 | Medieval Castilian manuscript (BnF Espagnol 33), eScriptorium ALTO v4, 22,062 B, SegmOnto zone tags. Validates as a source. sha256 `3b55554f5bc8` |
| `escriptorium_latin-mufi_clm13027-38r.alto.xml` | `https://raw.githubusercontent.com/HTR-United/CREMMA-Medieval-LAT/main/data/CLM13027/38r.xml` | **CC-BY-4.0** — repository `htr-united.yml` `license:` block | 2026-09-27 | **The only file with private-use (MUFI) characters**: 50 × U+F1AC in medieval Latin, Clm 13027, eScriptorium ALTO v4, 86,774 B, 121 lines. The PUA text round-trips. sha256 `0263a4c7e183` |
| `escriptorium_oldfrench_bnffr412-218.alto.xml` | `https://raw.githubusercontent.com/HTR-United/cremma-medieval/main/data/bnf_fr_412-wauchier/218_5b342_default.chocomufin.xml` | **CC-BY-4.0** — repository `htr-united.yml` and `README.md` ("Models and data are under ... CC-BY 4.0") | 2026-09-27 | Old French (BnF fr. 412), eScriptorium ALTO v4, 48,726 B, 7 blocks / 97 lines — **multiple columns with marginal zones** (`MarginTextZone`, `DropCapitalZone`). sha256 `66d5954fad34` |
| `escriptorium_occitan_flamenca-0001.alto.xml` | `https://raw.githubusercontent.com/HTRogene/occitan/main/data/carcassonne-34/Flamenca0001.xml` | **CC-BY-4.0** — repository `htr-united.yml` and `README.md` | 2026-09-27 | Old Occitan (*Roman de Flamenca*), eScriptorium ALTO v4, 31,725 B. **Fails its own schema**: line ids are UUIDs starting with a digit, not `xsd:ID`s (finding, below). sha256 `e5abfb72127c` |
| `transkribus_hindi-devanagari_diksita1895-02.alto.xml` | heiDATA `doi:10.11588/data/EGOKEI` ("Ground truth data for printed Devanagari"), `diksita1895.zip` → `diksita1895/diksita1895/alto/02.xml` | **CC-BY-4.0** — heiDATA dataset licence field (API `latestVersion.license`) | 2026-09-27 | **The only Devanagari**: Hindi/Braj print (1895), **Transkribus's ALTO** (`READ COOP`) rather than eScriptorium's, with `page:` PAGE namespace declared inside ALTO, 17,656 B. sha256 `1994a95f8400` |
| `transkribus_malayalam_telisseri-0061.alto.xml` | heiDATA `doi:10.11588/data/L2KRZO` ("Ground Truth data for printed Malayalam"), `39A8599.zip` → `39A8599/alto/39A8599_Telisseri-0061.xml` | **CC-BY-4.0** — heiDATA dataset licence field | 2026-09-27 | **The only Dravidian script**, and colonial-era material: the Tellicherry records (Malabar, East India Company correspondence), Transkribus ALTO v4, 30,077 B, Malayalam with embedded Latin and numerals. sha256 `ce2010bf70a3` |
| `tesseract_english_hocrtools-tess.hocr` | `https://raw.githubusercontent.com/ocropus/hocr-tools/master/test/testdata/tess.hocr` | **Apache-2.0** — hocr-tools `LICENSE` file (the licence API says NOASSERTION; the file itself is the Apache 2.0 text) | 2026-09-27 | **The first real engine hOCR** — `ocr-system` `tesseract 3.03`, 64,316 B, `ocr_carea` / `ocr_par` / `ocr_line` / `ocrx_word` with `bbox` and `x_wconf`, `lang='eng'`, 10 areas, 37 lines, 503 words. `PROVENANCE.md` recorded hocr-tools' samples as having no boxes; its `tess.hocr` does. Closes that residue. sha256 `7916237abc00` |
| `dta_german_luther-fabeln.tei.xml` | `https://raw.githubusercontent.com/deutschestextarchiv/DiBiLit-Korpus/main/data/fabel/luther_etliche-fabeln-aus-esopo-verdeutscht_1924.txt.xml` | **CC-BY-SA-4.0** — repository licence (GitHub licence API) | 2026-09-27 | **A real TEI edition** (Deutsches Textarchiv basis format), 34,817 B — with **no `<facsimile>` at all**, so no geometry: it imports as 8 regions of text and reports `page size` as its loss. sha256 `d67395a25cf7` |
| `transkribus_tibetan-layout_pagantibet-corr1.tei.xml` | `https://zenodo.org/records/19205598/files/Corr1-20230809_GT_layout.xml` | **CC-BY-SA-4.0** — Zenodo record 19205598 licence field | 2026-09-27 | **Transkribus's TEI export**, and **26 pages in one file** (26 `<surface>`s, `<l facs>` line pointers, layout only — no Tibetan text). `<pb xml:id>` values are image file names, which are not NCNames: **import fails** (#5130). The smallest file of the deposit (the one first offered, 165 KB, was not taken). sha256 `99ccc8fa9658` |

## Findings — what these files do

**Export refused (#5130, strict xfail):**

- **A segment with no shape is written with no `<Coords>`.** RASAM's lines carry
  `<Coords points=""/>` with a real baseline, and eScriptorium's `eSc_dummyblock_` region
  has no `<Coords>` at all. Both import; the PAGE 2019 writer then emits the segment
  without `<Coords>`, which the schema requires, and the export is refused. Import
  worked and export could not — the same shape as the table-cell defect in
  `PROVENANCE.md`.
- **Transkribus TEI with file-name `xml:id`s cannot be imported.** `xml:id` must be an
  NCName, and `0001_100_003_011_445.png` starts with a digit. The reader's strict lxml
  parse raises. The file is non-conformant; the question for the formats lane is whether
  the reader should recover (the data is otherwise ordinary).

**The same defect classes at scale.** Run over the larger sets below (1,327 files from
CHI-KNOW-PO, RASAM, both Syriac deposits, the Greek set and PaganTibet's `Manual1`),
**1,264 import and export valid, 62 exports are refused — every one a segment with no
shape** (58 lines with `points=""`, 3 `eSc_dummyblock_` regions, 1 self-closing
`<TextLine/>`) — and 1 import fails (`Manual1`, the NCName defect). No other defect
appeared.

**The sources as they arrived — information about the FILES, never a test failure.**
`scripts/validate_exports.py` on this directory (2026-09-27, with the PAGE 2013 and ALTO
4.3 schemas vendored): **8 valid, 7 INVALID, 1 other version, 1 no schema.** Seven of
the eight PAGE files are **PAGE 2013** — an older version, which is the point: each goes
out as PAGE 2019 and validates as that (bar the xfailed shape defect).

- `calfa_chinese-vertical_chi1087-0065.page.xml`: every region and line id is a bare
  number (`79725`, `870630`), which `xs:ID` forbids; `Metadata` lacks `LastChange`.
- `calfa_arabic-baseline-only_rasam417-0010.page.xml`: `points=""` fails the `Coords`
  pattern; `Comments` in the wrong place.
- `escriptorium-transkribus_syriac_smmj36-0004.page.xml` and
  `transkribus_newa-pracalit_vetala-0221.page.xml`: `TranskribusMetadata` is not in the
  2013 schema; the Syriac file's dummy region has no `Coords`.
- `transkribus_greek-polytonic_vatgr2228-0036.page.xml`: `Comments` out of order.
- `escriptorium_occitan_flamenca-0001.alto.xml`: eScriptorium line ids are UUIDs, and
  one starting with a digit is not a valid `TextLineID`.
- `transkribus_tibetan-layout_pagantibet-corr1.tei.xml`: not even well-formed under
  `xml:id` rules (the NCName problem above).
- `transkribus_multidirection_cpas2000.page.xml`: declares its namespace with
  `https://`, so strictly it is no PAGE version at all ("other version"); we read it
  anyway.
- hOCR has no schema by nature.

In every case but the two xfailed defects, **our export of the file is valid** — the
writer mints its own ids and writes the 2019 namespace, so the source's non-conformance
does not travel.

**Silence, recorded honestly:** only one file here states a direction (`cpas2000`), and
only the hOCR and `cpas2000` state a language in a field the model reads. The Chinese,
Arabic and Syriac pages state neither — a real vertical Chinese page and three real RTL
pages that say nothing about direction, so a reader that inferred one would be inventing
it.

## Searched, NOT vendored — so nobody hunts them again

| Candidate | Licence as read | Why not |
|---|---|---|
| BiblIA — medieval Hebrew, ALTO (Zenodo 5167263) | **CC-BY-NC-SA-4.0** on the Zenodo record (HTR-United's catalogue says CC-BY-SA; the record is authoritative) | NonCommercial |
| OpenITI MAKHZAN — Arabic/Persian/Ottoman/Urdu ALTO (Zenodo 19861912) | **CC-BY-NC-SA-4.0** | NonCommercial |
| OpenITI `OCR_GS_Data` | **CC-BY-NC-SA-4.0** (README) | NonCommercial |
| IRHAS — Ibero-Romance in Arabic script / Aljamiado (Zenodo 21824878) | **CC-BY-NC-SA-4.0** on the Zenodo record (API `license.id`) | NonCommercial — and the one bidirectional-in-spirit Spanish source found |
| `dstoekl/sofer_mahir` (Hebrew) | **CC-BY-NC-SA-4.0** (README) | NonCommercial |
| Muharaf (Arabic) | **CC-BY-NC-SA-4.0** | NonCommercial |
| Late medieval Castilian (Zenodo 7386489) | **CC-BY-NC-SA-4.0** | NonCommercial |
| CyrAcademisator-OCS (Zenodo 5163937), Church Slavonic | **CC-BY-NC-4.0** | NonCommercial |
| `MehreenMehreen/ScribeArabic` — PAGE with `readingDirection="right-to-left"` | **none declared** | No licence. The only real file found that STATES `right-to-left`. |
| `kba/hip21_ocrevaluation`, `cneud/hip21_ocrevaluation` — Russian PAGE | **none declared** | No licence |
| Tikkoun Sofrim (Zenodo 4736094) | "Other (Open)", undefined | No recognisable licence |
| eScriptorium's own TEI export sample (`tei_xml_export_full_part1.xml`, MIT repo) | MIT repository, but the file's own `<availability>` says CC-BY-NC-SA 4.0 | Contradictory; left out |
| NDL `ndl-minhon-ocrdataset`, CODH kuzushiji, HJDataset (Japanese) | CC-BY-SA-4.0 / gated | JSON / CSV / COCO, not PAGE, ALTO, TEI or hOCR |
| Cree syllabics (Zenodo 6915296), Tibetan-Cursive-GT, Kuzushiji HTR model (Zenodo 13942714), Old Cyrillic model (Zenodo 7755483) | CC-BY / CC0 | Tesseract `.box`, plain text, or a model with no ground truth |

## Larger sets for a local sample library (not vendored)

`scripts/fetch_sample_corpus.py` downloads these into the git-ignored `sample_corpus/`
directory at the repository root, checking each against the size and md5 recorded in
its manifest. It never runs in tests or CI.

| Set | Licence | Size | What it adds |
|---|---|---|---|
| CHI-KNOW-PO (github.com/calfa-co/chi-know-po) | Apache-2.0 | ~2 MB zip | 14 Classical Chinese manuscripts, vertical, PAGE |
| Syriac, St Mark's MS 36 — `page.zip` and `alto.zip` (Zenodo 18157525) | CC-BY-4.0 | 2.5 + 2.6 MB | the same pages as PAGE (Transkribus) AND ALTO (eScriptorium) |
| Syriac, ÖNB Cod. Syr. 1 — `page.zip` (Zenodo 14714089) | CC-BY-4.0 | 1.1 MB | 140 folios of eScriptorium PAGE 2019 |
| Medieval Greek, Vat. gr. 2228 + Phil. gr. 130 (Zenodo 20705757) | CC-BY-SA-4.0 | 0.9 MB | 46 Transkribus PAGE files |
| PaganTibet layout GT (Zenodo 19205598), `Manual1` file | CC-BY-SA-4.0 | 165 KB | a 66-page Transkribus TEI |
| Printed Devanagari (heiDATA EGOKEI), `diksita1895.zip` | CC-BY-4.0 | 3 MB | Transkribus ALTO + images |
| Printed Malayalam (heiDATA L2KRZO), `39A8599.zip` | CC-BY-4.0 | 6.9 MB | Transkribus ALTO + images |
| RASAM (github.com/calfa-co/rasam-dataset) | Apache-2.0 | ~ tens of MB | 547 Maghrebi Arabic PAGE files |

Too big to fetch by default, listed for reference: CATMuS Medieval (Hugging Face
`CATMuS/medieval`, CC-BY-4.0, parquet, ~1–2 GB), e-NDP Notre-Dame registers with
marginal entries (Zenodo 7575693, CC-BY-4.0, 914 MB), Pracalit Sanskrit/Newar GT
(Zenodo 6967421, CC-BY-4.0, 504 MB), CREMMA Medieval / CREMMA-Medieval-LAT / HTRogène
Spanish and Occitan (GitHub, CC-BY-4.0, clone), TRIDIS (Zenodo 10788591, MIT).

## Gaps this search could not fill

- **No real CJK, Mongolian or Manchu file that STATES vertical** (`readingDirection="top-to-bottom"`
  or `textLineOrder`) exists under a permissive licence anywhere searched: HTR-United's
  whole catalogue (CHI-KNOW-PO is its only CJK entry), Zenodo, kraken's and
  eScriptorium's test samples, NDL Lab, CODH, tesseract's test data. The vertical Chinese
  page here is vertical by geometry only; the one file stating `top-to-bottom` is a
  German/Hebrew papyrus test page. No Japanese, Korean or Mongolian page-level PAGE /
  ALTO / hOCR / TEI was found at all.
- **No Hebrew, Persian, Ottoman or Urdu file beyond the existing kraken Hebrew ALTO**:
  every candidate was NonCommercial. **No bidirectional page and no file stating
  `right-to-left` under a usable licence.**
- **No Indigenous-language material of the Americas** (Nahuatl, Maya, Quechua, Mixtec,
  Zapotec, Guaraní) in any of these formats with a released licence; Primeros Libros,
  Ticha and the New Spain fleets project hold none publicly as PAGE/ALTO/TEI.
- **No Cyrillic, Ge'ez, Armenian or Georgian** with a permissive licence.
- **No file with several readings per line** (PAGE `TextEquiv index` > 0 or ALTO
  `ALTERNATIVE`).
