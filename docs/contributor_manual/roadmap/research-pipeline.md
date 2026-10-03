# The research pipeline: Fichero's roadmap

The maintainer's plan for what Fichero does, end to end, from an image to a published edition
(2026-10-03). It is the map the specs are written against: `../specs/SPEC-PLAN.md` says, stage by
stage, which spec covers each part, what is built, and which specs are still to write. The tools
and models named here are the candidates the field offers today; the specs decide what Fichero
actually uses, cheapest and local first (`../specs/source/models-chains-and-projects.md`).

## 1. Ingest and storage

Image acquisition, manifest parsing and storage.

- High-resolution images through IIIF Image and Presentation APIs, by reference where possible.
- The local storage layout, object storage, and page metadata staging.

## 2. Layout analysis and segmentation

Structure, reading order and style, before any text is read.

- Segments at every level: character, word, line, block, column, interlinear gloss, marginalia.
- Reading direction: left to right, right to left, top to bottom, boustrophedon.
- Palaeographic classification: identifying the scribe or hand, and the cursive style, before
  transcription.
- Georeferencing and spatial warping of historical maps and page sketches.

Fast visual detection (YOLO-family detectors) and historical segmenters (Kraken, LayPa) separate
main text, marginalia and glosses and work out line order; a layout model (LayoutLM-class) orders
regions and classifies hands and script styles; for maps, ground control points warp the image
onto modern coordinates (Allmaps, Mapwarper).

## 3. Reading the text

Low-resource handwritten text recognition and multimodal reasoning, in tiers:

- **Tier 1, frontier reasoning models in the cloud** (Claude, GPT, Gemini): zero-shot page reading,
  and drafting ground truth.
- **Tier 2, open vision-language models** (Qwen-VL, Llama Vision, SmolVLM and the like): private
  block transcription on the Mac or a cluster.
- **Tier 3, dedicated line readers** (Kraken, TrOCR, PyLaia, Calamari): fast local line reading.

Also:
- Grapheme and allograph mapping: long and short s, ligatures, brevigraphs.
- Standards-compliant encoding: extinct glyphs to MUFI code points; TEI `<choice>` with
  `<orig>` and `<reg>`.
- An adaptive distillation loop: Tier 1 drafts ground truth that, once checked, fine-tunes the
  local engines on a specific hand (Hugging Face PEFT, LoRA).
- Where it runs: Apple Silicon (MPS, Core ML, the Neural Engine); ACENET and the Digital Research
  Alliance clusters (Slurm); open cloud endpoints.

## 4. Structuring, cleaning and post-correction

- Post-correction of character-level recognition noise with character-aware models (ByT5) and
  local open language models.
- Abbreviation and spelling normalisation: expanding scribal abbreviations and archaic spellings
  to standard forms.
- Document structure: sentence, paragraph and chapter boundaries; headers and footers; entities.
- TEI encoding and export: page breaks, marginal additions and strike-throughs mapped into valid
  TEI P5.

## 5. Entities, relations, time and place

- Named entities: people, places, dates, institutions, money; zero-shot and fine-tuned.
- Subject-verb-object and open relation extraction from narrative prose.
- Temporal normalisation: historical dates, feast days and regnal years to ISO 8601.
- Geoparsing: archaic toponyms and relative descriptions to gazetteers and WGS 84 coordinates.
- Coreference and spatio-temporal knowledge graphs (resolving forms such as "su merced").
- Distillation: small local models fine-tuned on extraction schemas drafted by Tier 1 models.

Candidate tools: GLiNER, spaCy, GeospaCy, FastCoref, NuExtract; the World Historical Gazetteer,
Getty TGN, Pleiades, Nominatim; DuckDB (with its spatial extension), NetworkX, JSON-LD, GeoJSON,
RDF.

## 6. Grounding, georeferencing and maps

- Georeferencing IIIF map images with the IIIF Georeference extension, without heavy tiles.
- Reconciling historical toponyms and boundaries through SPARQL endpoints.
- Linking places to global authorities (WHG, Pleiades, Getty TGN, Wikidata) for stable URIs and
  geometries.
- Exporting GeoJSON and SpatiaLite layers to overlay maps and the movements found in stage 5.

## 7. Curation and editing

- A native workspace: source images beside model drafts, to read, transcribe, edit and annotate.
- A person can override any low-confidence reading, tag, statement or place in place.
- Edits feed back as checked ground truth, so the models adapt to a hand (Kraken, LoRA).
- Edit history, provenance and quality measures (CER, WER, entity F1) tracked as the corpus is
  refined.

## 8. Model adaptation

- Domain adaptation on low-resource scripts.
- Distilling large vision-language models into small local engines.
- Active learning and retraining (PEFT, CER and WER measurement, PyTorch on Apple's GPU), on the
  Mac or in batches on ACENET from the accumulated edits.

## 9. Knowledge representation and search

- Cultural-heritage ontologies: CIDOC-CRM (events, people, places), Linked Open Data, W3C Web
  Annotation.
- Graphs stored inside the library, with no external database server.
- Several kinds of vectors: text for meaning search, image patches for hand similarity, entities.
- Hybrid search: full text with vector similarity.
- Graph embeddings and completion (PyKEEN-class) to suggest unrecorded social, family, legal and
  economic ties, as proposals.
- Graph-augmented retrieval: vector search with multi-hop graph walks, maps through time, and
  network exploration.

## 10. Natural-language generation

Readable summaries of the archive, critical apparatus, prose descriptions of networks, and
translation, made by local open models. Written from the claims and their sources, showing what
the record says rather than interpreting it.

## 11. Publishing

Curated editions, networks and spatial narratives compiled into standalone static websites
(Eleventy, Markdown templates) for GitHub Pages, Netlify or an institution's server.
