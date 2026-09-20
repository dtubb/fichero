# Source Model — Formats in and out, and training — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — an "Bringing work in and taking it out" section: importing a PageXML, ALTO or
> TEI project; exporting one; what each format can and cannot carry; and making a training
> set to teach a small model a new hand or script.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT.** A slice of the source model: read `source-model.md`
> first. Evidence in `source-survey.md`. Behaviour ids below have **no tags yet**; everything
> is design unless the foundation's "What exists today" says otherwise. (Today: no PageXML,
> ALTO, TEI, MEI, SVG or YOLO code; the Parquet export has no geometry; Kraken only reads,
> it is not trained. `export/exporter.md` owns the exporter as a whole; this slice owns what
> the source model needs from it.)

## Intent

Fichero has its own model, richer than any standard (ruled). The standards are the ways in
and out, and every one of them goes **both ways** (ruled). A scholar can bring in years of
work from another tool, keep working, and take it out again for a publisher, an archive, or
a model trainer, and always knows what a format could not carry.

## The design

### One general mapping system, and what is built first (ruled 2026-09-19)

**PageXML, ALTO and TEI are all built first**, together with YOLO's text labels. They are not
three separate pieces of code: they sit on **one general mapping system**, in which a format
is described (what each of its elements means in the source model, what it cannot hold, how
it is validated) and the same machinery reads, writes, validates and reports losses for all
of them. Adding MEI, hOCR or a format nobody has asked for yet is then a new description, not
a new importer and exporter. **Every export is validated.**

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
| **W3C annotations / IIIF** | yes | yes | pointers to shapes and text; notes on notes; control points for maps | it is not a transcription format |
| **hOCR** | yes | yes | lines, words, boxes or polygons, baselines, character cuts and confidence | most scholarly detail |
| **Transkribus and eScriptorium packages** | yes | yes | a zip of images and PageXML, optionally with a METS file: someone else's whole project | as PageXML |
| **YOLO labels** | yes | yes | a class and a box or polygon for each object | everything else |
| **Kraken training data** | yes | yes | ALTO or PageXML; line picture plus text; the compiled Arrow file | everything but lines, regions and text |
| **Columnar dataset (Arrow / Parquet)** | yes | yes | one row per segment: picture, shape, kind, reading, language, script, hand, period, source, guideline, level, licence, split | links and structure, unless asked for as extra tables |
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
- A training set carries a **description of itself** in the field's own terms (HTR-United's:
  language, script, period, hands, volume, guidelines, licence, who did what, Unicode
  normalisation), so it can be catalogued and shared without retyping.
- Each row keeps what Kraken's own file drops: hand, script, period, source, guideline, level
  of normalisation. Mixed corpora stay usable.
- Whether training *runs inside Fichero* is a separate matter for a Kraken training spec
  (not written). This slice guarantees only that Fichero can produce, and take in, what
  training needs.

## Behaviors (ids proposed; untagged until approval)

Rules for every format
- `source.format.one-mapping-system` — every format is read, written, validated and
  loss-reported by one general mapping system; adding a format adds a description, not a new
  importer or exporter.
- `source.format.first-four` — PageXML, ALTO, TEI and YOLO text labels are the first formats
  built on it.
- `source.format.import-is-pass` — an import arrives as a new pass with its provenance and
  overwrites nothing.
- `source.format.reimport-recognised` — importing the same file again is recognised, not
  duplicated silently.
- `source.format.keeps-unrecognised` — content the model has no field for is kept, labelled,
  and written back on export to that format.
- `source.format.export-validated` — an export is validated against its schema; an invalid
  one is a reported failure.
- `source.format.loss-report` — every export states what it could not carry.
- `source.format.round-trip-<format>` — one behaviour beside each in-and-out pair below: export
  then import returns the same segments, shapes, orders and readings, less what the loss
  report named.
- `source.format.export-choices` — an export names the pass, reading order and reading kind
  it writes, with defaults.
- `source.format.everywhere` — import and export work from the app, MCP and the command line,
  with a remote engine.

Each format (one import and one export behaviour each)
- `source.format.pagexml-in` · `source.format.pagexml-out`
- `source.format.alto-in` · `source.format.alto-out`
- `source.format.tei-in` · `source.format.tei-out`
- `source.format.mei-in` · `source.format.mei-out`
- `source.format.w3c-in` · `source.format.w3c-out`
- `source.format.hocr-in` · `source.format.hocr-out`
- `source.format.foreign-package-in` · `source.format.foreign-package-out` — a Transkribus or
  eScriptorium project as a whole.
- `source.format.yolo-in` · `source.format.yolo-out`
- `source.format.kraken-in` · `source.format.kraken-out`
- `source.format.columnar-in` · `source.format.columnar-out`
- `source.format.geo-in` · `source.format.geo-out`
- `source.format.table-in` · `source.format.table-out` — a table segment as CSV or a
  spreadsheet, each cell carrying a reference to its segment.
- `source.format.svg-out` — the page as SVG, text in its direction and along its baseline,
  with descriptions.
- `source.format.pdf-out` — a searchable PDF with text in place and descriptions as alt text.

Training
- `source.train.set-from-selection` — a training set is made from chosen sources, pass, kinds
  and readings.
- `source.train.line-pictures` — line pictures are cut to the polygon and straightened on the
  baseline.
- `source.train.human-checked-by-default` — only human-checked readings are included by
  default; including others is deliberate and is recorded row by row in the set.
- `source.train.ground-truth` — a fully corrected page can be marked as ground truth.
- `source.train.measured` — a model's pass can be scored against ground truth by page and by
  hand, and the score is kept with the date, model and training set.
- `source.train.model-lineage` — a pass made by a fine-tuned model names that model, and the
  model names the training set it came from.
- `source.train.split-by-manuscript` — training, validation and test are split by manuscript.
- `source.train.self-describing` — a training set carries a description in HTR-United's terms.
- `source.train.rows-keep-context` — each row keeps hand, script, period, source, guideline
  and level.
- `source.train.sign-pictures` — pictures of characters and declared signs can be exported as
  a labelled set.
- `source.train.output-is-pass` — a fine-tuned model's output arrives as a new pass and new
  readings.
- `source.train.projection-only` — a training set is made on demand and is never the record.

## Test matrix

To be filled at approval. Each format needs a real sample file from the field as a fixture,
and its schema for validation.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
