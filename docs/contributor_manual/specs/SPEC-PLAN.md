# The spec plan: which spec covers what, and which to write next

The specs exist to be built against and tested against: get the spec right, then implement it,
test it against the spec, then update the issues, milestones and the reference manual. This page
is the map from the roadmap (`../roadmap/research-pipeline.md`) and the maintainer's programme of
2026-10-03 to the specs. It names, for each part, the spec that owns it, how far it is built, and
the specs still to write, in the order to write them.

Status words: **built** (behaviours mostly [OK]), **partly built**, **specced** (DRAFT, mostly
[GAP]), **no spec**.

## The pipeline, stage by stage

| Stage | Owning specs | Status | Gaps to spec |
|---|---|---|---|
| 1. Ingest and storage | `importer/importer.md`, `source/iiif.md`, `source/synced-folder.md`, `source/formats-and-training.md` | partly built; IIIF by reference specced | none new; IIIF by reference to build |
| 2. Layout and segmentation | `source/image-preparation.md` (find the page, split at the gutter, turn, clean; DRAFT 2026-10-03, #5382), `source/segments-and-geometry.md`, `source/segment-editor.md`, `source/languages-scripts-signs.md` (direction), `source/maps-and-georeference.md` | partly built | **hand and style classification before reading** (a job in the registry; see `source.hand.*` in `readings-and-apparatus.md`): add as a job, no new spec |
| 3. Reading the text | `source/models-chains-and-projects.md` (jobs, recipes, tiers, bake-off), `ai/local-runtimes.md`, `source/readings-and-apparatus.md`, `source/languages-scripts-signs.md` (MUFI, declared signs) | specced; runtimes partly built | none new |
| 4. Cleaning and post-correction | `source/historical-text-normalization.md`, `source/readings-and-apparatus.md` (editorial facts), `source/formats-and-training.md` (TEI) | partly built | **character-level post-correction** (ByT5-class) as a job, with its A/B; add to the registry |
| 5. Entities, relations, time, place | `kg/*`, `source/historical-text-normalization.md` (dates), `explore/time.md`, `explore/place.md` | partly built | **project gazetteer and canonical name list** (see below) |
| 6. Grounding and maps | `source/maps-and-georeference.md`, `kg/kg-enrichment.md` | partly built | Wikidata and gazetteer enrichment at project level (below) |
| 7. Curation and editing | `source/segment-editor.md`, `source/line-editor.md`, `source/editable-reader.md`, `safety/*` | partly built | none new |
| 8. Model adaptation | `compute/distillation.md`, `compute/jobs-and-fine-tuning.md`, `compute/remote-compute.md` | specced | **the projects harness and the improvement loop** (below) |
| 9. Knowledge and search | `kg/*`, `ui/search.md`, `explore/meaning.md`, `explore/networks.md` | partly built | graph embeddings as proposals: fold into `explore/networks.md` |
| 10. Natural-language generation | `kg/kg-readable-representation.md` | partly built | **summaries that show, not tell** (below) |
| 11. Publishing | `export/exporter.md`, `source/iiif.md` (published folders, static), `source/synced-folder.md` | partly built | **the Istmina public family-history site** (below) |

Running all of it: `ui/activity-and-automatic-work.md` (one job model, the workflow runner inside
it, automatic reprocessing), `ai/local-runtimes.md` (how each model runs), and the recipe and
onboarding sections of `source/models-chains-and-projects.md` (what runs, chosen how). These
three are one connected set and are built together.

## Coverage against the maintainer's pipeline list (checked 2026-10-06)

The maintainer's eleven-stage list (ingest; layout and palaeographic classification; tiered reading
with MUFI/TEI and distillation; post-correction and structure; entities, relations, time, place;
grounding and maps; curation; model adaptation; knowledge, vectors, graph completion and GraphRAG;
generation; static publishing) was checked bullet by bullet against the specs and the job registry.
Almost every bullet has a home above; most are partly built. The recipes catch it through the job
registry (`recipes/jobs.py`, 31 jobs) and the guided path (`source/models-chains-and-projects.md`):
every step can be distilled from a frontier teacher, checked, fine-tuned locally or on Hugging
Face / ACENET, measured, and used, on an 8 GB M1 (`compute/jobs-and-fine-tuning.md`, "Models in
memory"; `compute/distillation.md`, "Best practice").

Built today: Kraken lines; page and line reading by cloud and local models; spaCy + LLM names; regnal
years; the KG in DuckDB with rdflib / JSON-LD / Turtle; PyKEEN link prediction; hybrid full-text +
vector search (LanceDB); Parquet export; the 11ty site; checking by person or model; CER (four
policies); Allmaps georeference annotations; Nominatim geocoding.

The gaps, most important for the goals first:

| # | Gap | Issue | Home |
|---|---|---|---|
| 1 | Hand and script detection before reading | #5456 | a `detect-script-and-hand` job; `recipe.distil.script-and-hand-routed-per-region` |
| 2 | Corrections trigger retraining (the closed loop) | #5404, #5337 | `compute/distillation.md`, `compute.tune.adopted-by-the-recipe` |
| 3 | Tiered and cascade routing by confidence | #4948, #5338 | `source.recipe.reader-tiers`, `distill.cascade.*` |
| 4 | Coreference ("su merced") | #5541 | a `resolve-references` job or `kg/coreference.md` |
| 5 | Feast days and liturgical dates | #5542 | `source.date.*` |
| 6 | Character-level post-correction (ByT5-class) | #5543 | a `correct-characters` job with its A/B |
| 7 | Page furniture, entries, logical structure | #4927, #4949 | `source.segment.furniture`, `source.job.split-into-entries` |
| 8 | Archive-scale ingest and storage backends | #5544, #5540 | `source/iiif.md`, `source/synced-folder.md` |
| 9 | ACENET / Slurm training and reading | #5238, #5457 | `compute/targets-and-connection.md` |
| 10 | F1 and WER as measured behaviours | #5545 | `distill.eval.*` |
| 11 | Money and institutions as typed entities | #5546 | `kg/kg-tables.md` |
| 12 | Map warping in the app | #1755 | `source.geo.map-view-georeference-overlay` |
| 13 | CIDOC-CRM mapping | #1678 | `kg.enrich.ontology-layer` |
| 14 | Image-patch vectors, federated SPARQL, apparatus and collation, network prose, lemmatisation, crowd transcription, GraphRAG | #5547 | as listed in the issue |

Named tools Fichero does not plan to embed, with what it uses instead: LayPa and LayoutLM (Kraken,
YOLO planned); PyLaia and Calamari (Kraken); BookNLP (spaCy); GLiNER and NuExtract (LLM jobs, distilled);
GeospaCy (Nominatim and the gazetteers); JiWER (the engine's own CER); Leaflet and MapLibre (MapKit);
PostGIS (DuckDB Spatial, planned). Allmaps and Mapwarper are exchanged with by file, not embedded. Any
of them can enter as a candidate through discovery (#5519) and be measured in the bake-off (#5533).

## The programme beyond the pipeline

**Onboarding is the user manual.** Each setup step explains itself from the job registry, and the
same text is the manual's page for that step (`source.onboard.*`, "What onboarding teaches"). The
maintainer's step document (Mellel, to come) sets the order. Build next.

**Specs to write, in this order:**

1. **Projects harness and the improvement loop** (`~/code/fichero-projects/SPEC.md`, its own
   private repository). Fichero as the harness for real projects that train models: Sergio
   Mosquera's notebooks (one hand, about 400 pages, a Qwen-VL transcription to correct) and the
   Marshall diary (one hand) first; then the Istmina archive (damaged, many hands, 1870s to 1980s);
   Spanish hands from the twenty-first century backwards. The loop:
   1. a frontier model drafts ground truth;
   2. a person checks it in Fichero;
   3. small models (Kraken lines and text, YOLO regions, a small Qwen-VL with LoRA, spaCy) train;
   4. they are measured by character and word error rate against the checked pages;
   5. the winners become recipe steps;
   6. good ones are released on Hugging Face as part of Fichero.

   Training is proven on Hugging Face Jobs first, so it is known to work reliably, then on
   ACENET; and as much as possible runs locally (fine-tuning YOLO and Kraken inside Fichero on a
   16 GB Mac). The loop also improves Fichero itself: every defect a project hits becomes an
   issue against the specs here.
2. **Catalogue entries that show, not tell** (DRAFT written 2026-10-03: `source/cataloguing.md`, with item 3). Today's catalogue text is too long and analyses.
   Wanted: the facts of each item (what, who, when, where, extent) from its metadata fields and
   claims, with no AI interpretation. Fold into the cataloguing spec (#5365, prototypes).
3. **Cataloguing and metadata on prototypes** (#5365).
4. **Project gazetteer and canonical names** (DRAFT written 2026-10-03: `kg/project-gazetteer-and-names.md`, #5380). One project-level gazetteer and one canonical name
   list, as good as the evidence allows, enriched from Wikidata and the gazetteers in
   `kg/kg-enrichment.md`, every enrichment a claim with its source, kept apart from what the pages
   say.
5. **Better natural-language summaries.** Written from claims with their sources, in plain prose,
   showing what the record says (`kg/kg-readable-representation.md`); measured by readers.
6. **The agents: MCP and the in-app agent.** Clean up and test the MCP surface used by Claude and
   other external agents, and the in-app agent (an external agent through the same audited
   actions is the likely path; a vendor's licence decides what can be embedded).
7. **The Istmina public site** (DRAFT written 2026-10-03: `export/public-site.md`, #5381). A public, searchable site from the Istmina archive for people
   there to look for family history: names, places, dates, the page images by IIIF, built by the
   publishing stage, with rights and consent respected (`source/rights-and-access.md`).

## How a spec moves

DRAFT (written, reviewed against the code) → reviewed by the maintainer → APPROVED with a filled
test matrix → built and tested against it → issues closed as each behaviour turns [OK] → the
reference manual updated (`docs/reference_manual`), and the user manual through onboarding.
