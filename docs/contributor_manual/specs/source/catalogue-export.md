# Source Model — The catalogue sheet: what was catalogued, one row per folder — Design Spec (#5365, #6087)

> Milestone: source-model
> Manual: TBD — a section, "Exporting your catalogue", telling a researcher that the recipe's last step
> writes the catalogue as a sheet (Excel or CSV) in their archive's own template, one row per folder,
> with the people and places as authority lists beside it, and how to change the columns.
>
> Design-led (Testing Constitution). **Status: PROPOSED** (2026-10-28, written for the owner from his
> idea of the same day, paraphrased: the recipe's keep-files / export step should export what was
> CATALOGUED for each folder as a sheet, one row per digital folder, in the headings of his existing
> cataloguing template; and from his real cataloguing workbook, read for its structure only, never
> copied into the repo or the app). **Needs a new issue** for its own work (the behaviours below cite
> the parent issues #5365, `catalogue.export-standards`, and #6087, the Catalogue stage, until it is
> filed). Builds on `cataloguing.md` (the twelve fields as folder attributes,
> `catalogue.folder-description-fields`), `export/exporter.md` (the one record stream and its Excel
> emitter), `models-chains-and-projects.md` (`source.onboard.kept-exported`, the export step) and
> `../kg/project-gazetteer-and-names.md` (the project's canonical names and places).

Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built. Every line here
is [GAP] (PROPOSED); each names the test file to write.

## Why its own spec

`cataloguing.md` owns the fields and already lists `catalogue.export-standards` [GAP] (EAD, Dublin Core,
CSV, Excel, IIIF metadata) in one line. `export/exporter.md` owns the record stream and its six emitters
(documents, entities, claims as fixed tables). Neither says what a cataloguer's **sheet** is: a template
of columns in the archive's own words, filled from the folder's attributes, the knowledge graph and the
run's record, with authority lists beside it. That is one surface with its own template data, its own
formats and its own place in the recipe, so it gets one spec; `cataloguing.md`'s export line will point
here when this is approved, and the record-stream emitters stay where they are.

## Intent (the design)

A person presses Start on a recipe whose last step is "Keep files". When the run ends they open the folder
the step names and find `Catálogo.xlsx` (and, if they asked, `Catálogo.csv`): one sheet with one row per
digital folder (a digital folder is one archival document or file), the columns of their own cataloguing
template, in their words and order, and beside it the sheets `Personas`, `Lugares` and `Tema` filled from
the project's knowledge graph. They can hand the workbook to the archive or the funder as it is. Nothing in
it was invented at export: every cell is a value the Catalogue stage proposed and a person could see on the
folder, a fact of the folder (its name, its files, its count), or a name the graph holds. A cell with no
value is empty, never guessed. Writing the sheet never runs a model (`never-rerun-a-model-pass`, #6127).

It lives in a new fichero-server/src/fichero_server/catalogue_sheet.py (to write; the template, the row builder,
the two writers), a new kept-export format in `fichero-server/src/fichero_server/kept_export.py`
(`FORMATS`), one route in `fichero-server/src/fichero_server/api/routes/ingest/export.py`, and the
recipe's export card in `fichero-server/src/fichero_server/recipes/runner.py` (`_run_export`). The app
shows and edits the template; no rule lives in Swift.

## Prior art / best practices (don't invent from scratch)

- **The British Library Endangered Archives Programme (EAP) listing template.** The owner's workbook is
  it: a first header row in EAP English (Digital Folder Name, Digital File Name (First), Digital File Name
  (Last), Number of Digital Files, Title (In Original Language/Script), Original Reference, Dates of
  Material (Gregorian Calendar), Related Towns/Cities, Related Subjects), a second header row in the
  team's Spanish, a third row of instructions to the cataloguer. We ship it as the first preset, both
  header rows, and let the instructions row be the column's help text.
- **ISAD(G) and EAD.** Title, dates, extent, reference code, scope and content, access points. Every
  column of the preset maps to one ISAD(G) element, so an EAD export later (`catalogue.export-standards`)
  reads the same template.
- **Archival authority lists (ISAAR-CPF, the Getty TGN, GeoNames' feature classes).** The `Personas`
  and `Lugares` sheets are authority files: one row per entity, the control form, the parts of the name,
  the place's type and the place it is within. We write them from the knowledge graph's entities, which
  already carry a canonical name, aliases, a type and curation state (`models/knowledge.py`,
  `KnowledgeEntity`), rather than inventing a second list.
- **Excel's own conventions for sheets handed around.** UTF-8 with a byte-order mark for CSV, so Excel on
  a Spanish Mac opens the accents right; text cells for everything (a date written "17/Marzo/1892" must
  not become a serial number); frozen header rows. The existing Excel emitter
  (`export_service.export_excel_xlsx`) already writes a workbook; the sheet reuses its writer in
  write-only (streaming) mode.
- **Fichero's own rulings honoured, not restated.** No analysis in a catalogue (`catalogue.no-ai-analysis`);
  fields are the folder's attributes with provenance (`workflows/attribute_sources.py`: a person's value
  outranks a machine's, a machine's names its run, model and artifact); one audited action per capability;
  no local paths in the app (the sheet goes to a kept-export folder the person granted, or comes back as a
  download through the route).

## Where each column comes from

The owner's twelve headings, kept as given. "Source" names the existing field, step output or new thing;
"empty" says what the cell holds when there is nothing.

| # | Heading (row 2, Spanish, as given) | EAP heading (row 1) | Source | Empty |
|---|---|---|---|---|
| 1 | Tu nombre | — (not in the BL table) | The cataloguer of the row: the person whose account set or accepted the row's fields (`attribute_sources` `by: person`, the account's display name); when every field is a machine's, "Fichero (<model>)" as `catalogue.folder-description-fields` already rules (provider and model from the machine source). | The project's cataloguer name from the template settings; else empty. |
| 2 | Nombre de carpeta digital | Digital Folder Name | The folder's name (`Document.name` of the folder). | Never empty: a folder has a name. |
| 3 | Digital File Name (First) | Digital File Name (First) | The original file stem of the folder's FIRST page in reading order, as import recorded it (`importers/ingest.py` keeps the file name on the page). | Empty when the folder has no pages. |
| 4 | Nombre de archivo digital (segundo) | Digital File Name (Last) | The original file stem of the folder's LAST page in reading order ("segundo" means the last file in the owner's practice: `_IMG_001` … `_IMG_125`). | Empty when the folder has no pages; equal to column 3 when it has one. |
| 5 | Número de archivos digitales en carpeta | Number of Digital Files | The count of pages (images) directly in the folder and its subfolders. | "0". |
| 6 | Título del documento | Title (In Original Language/Script) | The folder attribute `catalogue_title` (the Catalogue stage's Title field, `recipes/catalogue_step.py` `ATTRIBUTE_FIELDS`). | Empty. |
| 7 | Referencia original de archivo físico | Original Reference | NEW folder attribute `catalogue_original_reference`: a reference the records carry (a cover number, a legajo and folio). Proposed by the Catalogue stage as one more optional field, only when the pages state one; otherwise typed by a person. | Empty. |
| 8 | Fecha de inicio del proceso legal | Dates of Material (Gregorian Calendar) | The folder's `catalogue_dates` field (proposed by the Catalogue stage from the readings) through the archive's date format: the earliest full date it names as "17/Marzo/1892"; a year alone ("1892") when only the year is known (`catalogue_date_start`). Work out dates' normalised mentions are the evidence the stage reads; the sheet never dates a folder itself. | Empty. |
| 9 | Lugares mencionados (Pueblos, regiones, países, ríos, quebradas, cerros, minas, fincas y otros referentes geográficos) | Related Towns/Cities | The knowledge graph's `location` entities whose `source_document_ids` fall in the folder's pages, by canonical name, verified and unreviewed alike (a rejected or merged-away entity is left out), joined with "; ". | Empty. |
| 10 | Nombres de personas mencionadas | — (not in the BL table) | The graph's `person` entities for the folder's pages, written "Nombre Apellido" (the canonical name's order), joined with "; ". | Empty. |
| 11 | Descripción breve del documento: ¿Sobre qué es? | — (EAP has no description column; kept as the team's own) | The folder's description: its `catalogue.narrative` artifact / `description` reading written by the Catalogue stage (150-200 words, no analysis). | Empty. |
| 12 | Problemas para resolver | — | Free text, joined with "; ": the person's own attribute `catalogue_problems` (NEW), then the run's flags on the folder (`lint_flags` on its catalogue data; pages that failed to read; a gap in the images' numbering, "faltan IMG_017-IMG_019"; a `check.verdict` rejection on a statement of the folder, `checking/verdicts.py`). | Empty. |
| — | Related Subjects (EAP row 1 only, no Spanish heading in the owner's row 2) | Related Subjects | NEW folder attribute `catalogue_subjects`: terms from the project's controlled `Tema` list (English SubjectTerms, "Anthropology"), chosen by a person or proposed by the Catalogue stage from that list only, joined with "; ". | Empty. |

Fields 7, 12 and Related Subjects are new optional fields of `catalogue.folder-description-fields`
(they join the stage's option list; the stage never invents them). The stage already writes fields 6 and 8
and the description; columns 2 to 5 are facts of the folder; 9 and 10 are the graph's.

## The template as data

- A **catalogue sheet template** is a list of columns, saved with the project's recipe answers
  (`recipes/answers.py`), each column: a stable key, one or more header rows (row 1 EAP English, row 2 the
  team's heading, in the project's metadata language), an optional instruction line (row 3), a source (one
  of the sources in the table above, by name: `folder.name`, `folder.first_file`, `folder.last_file`,
  `folder.page_count`, `attribute:<key>`, `kg:person`, `kg:location`, `description`, `problems`,
  `cataloguer`), a join string (default "; ") and a format (for dates: the archive's date format).
- The owner's sheet is the first preset, **"EAP / Catalogación básica"**: the twelve headings above in
  that order, both header rows, the instruction row, people and places joined "; ", dates
  "d/Mes/aaaa" with the month written out in Spanish. A second preset, **"EAP (English only)"**, is the
  BL table alone (no Tu nombre, no people, no description).
- A person edits the template (drop a column, rename a heading, reorder, add an attribute column, change
  the join or date format); the edit is the audited `catalogue.sheet-template.put`; a preset is never
  edited in place, a changed preset is saved as the project's own template.
- Another archive's template is the same data with other headings and sources; a CSV of headings can be
  imported as a template with every column mapped to "empty" until the person picks each source.

## The authority sheets

Written beside the catalogue sheet from the knowledge graph, one row per entity whose sources fall in the
exported scope, control form first, sorted by it:

- **Personas**: Nombre compuesto ("Apellido, Nombre", the control form: the canonical name inverted at its
  last word, or as a person's own `names` entry says), Nombres, Apellidos (the parts of the canonical
  name; one word fills Nombres), Información adicional (the roles the graph holds on the entity:
  "hijo", "padre", "presbítero", "viuda de X", from its claims' roles and its `description`),
  Comentarios (empty; a person's column, for corrections and duplicates to merge).
- **Lugares**: Lugar (control) (the canonical name), Lugar (the name as the records write it, the
  aliases joined "; "), Tipo de lugar (País, Departamento, Provincia, Municipio, Ciudad, Pueblo, Barrio,
  Río or Otro, from the gazetteer's feature class where the place is linked, `knowledge/linked_places.py`,
  else Otro), dentro de (the parent place, "Quibdó → Chocó → Colombia", from the gazetteer's hierarchy
  where linked, else empty), Comentarios (empty).
- **Tema**: the project's controlled subject list (SubjectTerms), one per row, as the project holds it
  (a classification dimension, `api/routes/document/classifications.py`), with the count of folders that
  carry each.

An authority sheet is written only in XLSX (as sheets) and, for CSV, as `Personas.csv`, `Lugares.csv`,
`Tema.csv` beside `Catálogo.csv`.

## Formats

- **XLSX**: one workbook; sheet 1 the catalogue (frozen header rows, every cell text), then the
  authority sheets; written in the Excel writer's streaming (write-only) mode.
- **CSV**: UTF-8 with a byte-order mark (Excel on a Spanish Mac then reads "Catalogación" and "Río"
  right), comma-separated, every field quoted, CRLF line ends, the header rows as the first lines.
- One row per folder; people and places joined with "; " (one space after the semicolon); dates in the
  archive's format; a folder with subfolders is one row for itself (its own pages' count and files) and
  one row per subfolder, in sidebar order, so a box of documents is a block of rows.
- Spanish accents and ñ are written as the attribute holds them (NFC, `historical-text-normalization.md`).

## When it runs

- **As the recipe's last step.** The export card (`recipes/runner.py` `_run_export`) gains the format
  `catalogue-sheet` (one file per **folder scope**, not per page), kept as a kept export
  (`kept_export.FORMATS`, `source.onboard.kept-exported`); it is written after Catalogue, on the run's
  last batch, and rewritten by the kept-export quiet-period hook when a folder's attributes or
  description change. A run with no Catalogue stage still writes the sheet, with the fact columns filled
  and the field columns empty.
- **On demand** from a folder or a project (the Inspector's Kept Exported section, Write Now; or
  File › Export › Catalogue sheet…) through `POST /api/export/catalogue-sheet` (scope: a folder or project
  id; format `xlsx` or `csv`; template id), returning the file, or writing to a kept export's folder.
- **CLI and MCP** reach the same route through the generated surface (`fichero export catalogue-sheet`,
  `fichero_export_catalogue_sheet`), as every route does.
- **Never a model.** Writing the sheet reads attributes, entities and the run's record only. A folder the
  Catalogue stage has not described has empty field columns; the sheet says how many such rows in its
  Activity line ("Catálogo.xlsx: 552 filas, 14 sin describir") and never runs the stage to fill them.

## At 100k pages

A collection of 100,000 pages is some thousands of folders. The sheet is **streamed**: folders are read
in batches of 500 (one query for the folders, one for their page counts and first/last file names, one
for the folder attributes, one for the entities of the batch's pages, one for the flags: five queries per
batch, never one per folder), each batch's rows written to the CSV or the write-only workbook as they are
made, nothing held beyond a batch. The authority sheets are built from a set of entity ids kept across
batches (ids only) and written last, in batches of the same size. A sheet of 5,000 folders writes in
under a minute on the M1; the job runs on the background `database` lane like every kept export.

## Behaviors

- `catalogue.export.one-row-per-folder` — **[GAP]** (#5365; new issue needed) the sheet holds one row per
  folder in the scope, in sidebar order, a folder with subfolders first and its subfolders after it; the
  fact columns (name, first file, last file, page count) are filled for every row from the folder and its
  pages alone. Test: fichero-server/tests/unit/export/test_catalogue_sheet_rows.py (to write).
- `catalogue.export.cells-from-attributes-never-guessed` — **[GAP]** (#5365, #6087; new issue needed) a
  field column holds the folder's attribute of that key as it stands (a person's value over a
  machine's); a folder with no value has an empty cell; writing the sheet never calls a model or reruns
  the Catalogue stage (#6127). Test: fichero-server/tests/unit/export/test_catalogue_sheet_rows.py (to write).
- `catalogue.export.cataloguer-column` — **[GAP]** (#5365; new issue needed) Tu nombre is the account name
  of the person who set or accepted the row's fields, else "Fichero (<model>)" from the machine source,
  else the template's cataloguer name, else empty. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_rows.py (to write).
- `catalogue.export.people-and-places-from-the-graph` — **[GAP]** (#5365; new issue needed) Lugares and
  Nombres list the graph's `location` and `person` entities sourced in the folder's pages by canonical
  name, merged-away and rejected ones left out, joined "; ", sorted by first appearance. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_graph_columns.py (to write).
- `catalogue.export.dates-in-the-archives-format` — **[GAP]** (#5365; new issue needed) a date column
  renders `catalogue_dates` through the template's date format: "17/Marzo/1892" for a full date, "1892"
  when only the year is known, empty when the field is empty; the month names are Spanish in the preset
  and come from the template, not the code. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_dates.py (to write).
- `catalogue.export.problems-column` — **[GAP]** (#5365; new issue needed) Problemas para resolver joins the
  person's `catalogue_problems` attribute, the folder's catalogue `lint_flags`, its pages that failed to
  read, a gap in the images' numbering and a check rejection on its statements, each as one short clause,
  "; " between. Test: fichero-server/tests/unit/export/test_catalogue_sheet_problems.py (to write).
- `catalogue.export.new-optional-fields` — **[GAP]** (#6087; new issue needed) the Catalogue stage's option
  list gains Referencia original de archivo físico (`catalogue_original_reference`), Problemas para
  resolver (`catalogue_problems`, a person's field the model never fills) and Related Subjects
  (`catalogue_subjects`, from the project's Tema list only); a model fills a field only from evidence in
  the records, as `catalogue.folder-description-fields` rules. Test:
  fichero-server/tests/unit/recipes/test_catalogue_stage_optional_fields.py (to write).
- `catalogue.export.template-is-data` — **[GAP]** (#5365; new issue needed) a template is saved with the
  project's recipe answers as a list of columns (key, header rows, instruction, source, join, format);
  the preset "EAP / Catalogación básica" carries the owner's twelve headings in order with both header
  rows and the instruction row; a preset is never edited in place; a changed one is saved as the
  project's own; the edit is the audited `catalogue.sheet-template.put`. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_template.py (to write).
- `catalogue.export.two-header-rows` — **[GAP]** (#5365; new issue needed) the preset writes row 1 in EAP
  English, row 2 in the project's metadata language (the owner's Spanish set), row 3 the instructions;
  a template with one header row writes one; the header rows are frozen in XLSX. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_template.py (to write).
- `catalogue.export.authority-sheets` — **[GAP]** (#5365, #5380; new issue needed) Personas (Nombre
  compuesto "Apellido, Nombre", Nombres, Apellidos, Información adicional, Comentarios), Lugares (Lugar
  (control), Lugar, Tipo de lugar from the fixed list, dentro de, Comentarios) and Tema are written beside
  the catalogue from the graph's entities in scope; Comentarios is always empty; a place with no
  gazetteer link has Tipo "Otro" and an empty dentro de. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_authorities.py (to write).
- `catalogue.export.xlsx-and-csv` — **[GAP]** (#5365; new issue needed) XLSX is one workbook (catalogue
  first, then the authority sheets, every cell text, header rows frozen); CSV is UTF-8 with a byte-order
  mark, every field quoted, CRLF, one file per sheet; both carry Spanish accents and ñ unchanged. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_formats.py (to write).
- `catalogue.export.recipe-last-step` — **[GAP]** (#5485, #6087; new issue needed) the export card accepts
  the format `catalogue-sheet` per folder scope; it is written after Catalogue on the run's last batch,
  kept as a kept export and rewritten by the quiet-period hook when a folder's attributes or description
  change; a run without a Catalogue stage writes the fact columns and leaves the fields empty. Test:
  fichero-server/tests/unit/recipes/test_recipe_export_catalogue_sheet.py (to write).
- `catalogue.export.on-demand-route` — **[GAP]** (#5365; new issue needed) `POST /api/export/catalogue-sheet`
  takes a folder or project id, a format and a template id and returns the file or writes to a kept
  export's folder; the CLI and MCP reach it through the generated surface; the route runs the same
  builder as the recipe step. Test: fichero-server/tests/unit/api/test_export_catalogue_sheet_route.py (to write).
- `catalogue.export.streams-at-scale` — **[GAP]** (#5365; new issue needed) folders are read and written
  in batches of 500 with five queries per batch and no per-folder query; the workbook is written in
  write-only mode; a 5,000-folder sheet holds no more than one batch of rows in memory at a time. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_streaming.py (to write) (counts queries on a fake
  database of 2,000 folders).

## Build order

### Stage 1 — The sheet from what exists
#### Step 1.1 — Rows from folders, attributes and the graph
- Behaviours: `catalogue.export.one-row-per-folder`, `catalogue.export.cells-from-attributes-never-guessed`, `catalogue.export.cataloguer-column`, `catalogue.export.people-and-places-from-the-graph`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_rows.py, fichero-server/tests/unit/export/test_catalogue_sheet_graph_columns.py
- Size: M
#### Step 1.2 — The template and its preset
- Behaviours: `catalogue.export.template-is-data`, `catalogue.export.two-header-rows`, `catalogue.export.dates-in-the-archives-format`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_template.py, fichero-server/tests/unit/export/test_catalogue_sheet_dates.py
- Depends on: 1.1
- Size: M
#### Step 1.3 — XLSX and CSV, streamed
- Behaviours: `catalogue.export.xlsx-and-csv`, `catalogue.export.streams-at-scale`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_formats.py, fichero-server/tests/unit/export/test_catalogue_sheet_streaming.py
- Depends on: 1.2
- Size: M

### Stage 2 — In the recipe and on demand
#### Step 2.1 — The export card's new format and the route
- Behaviours: `catalogue.export.recipe-last-step`, `catalogue.export.on-demand-route`
- Tests: fichero-server/tests/unit/recipes/test_recipe_export_catalogue_sheet.py, fichero-server/tests/unit/api/test_export_catalogue_sheet_route.py
- Depends on: 1.3
- Size: M
#### Step 2.2 — The new fields and the problems column
- Behaviours: `catalogue.export.new-optional-fields`, `catalogue.export.problems-column`
- Tests: fichero-server/tests/unit/recipes/test_catalogue_stage_optional_fields.py, fichero-server/tests/unit/export/test_catalogue_sheet_problems.py
- Depends on: 2.1
- Size: M
#### Step 2.3 — The authority sheets
- Behaviours: `catalogue.export.authority-sheets`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_authorities.py
- Depends on: 2.2
- Size: M

Stage 3 (the app's template editor and the Tema list's import) follows approval and a look at the
engine's output on the owner's own project.

## Test matrix

To be filled at approval. Fixtures: a scratch project of three folders built with
`seed_test_library.py` (one described by a fake model, one typed by a person, one undescribed), with the
sheet each row should render; the owner's workbook is never a fixture.

## Open questions for the owner

1. **"Segundo" is the LAST file?** The workbook's row 1 says Digital File Name (Last) and the files run
   `_IMG_001` to `_IMG_125`. Recommendation: last file; keep the Spanish heading as written.
2. **Which names go in Lugares and Nombres: every entity the graph found, or only verified ones?**
   Recommendation: every entity that is not rejected or merged away, with a template switch
   "confirmed only" off by default; a cataloguer reviewing the sheet wants to see what was found.
3. **What dates "Fecha de inicio del proceso legal"?** Recommendation: the Catalogue stage's Dates field
   (its earliest date), since choosing the start of a legal process is a reading of the records the
   stage already makes; the sheet only formats it. If the owner wants a separate field, it is one more
   optional field, "Fecha de inicio", filled only when the records state it.
4. **CSV with a byte-order mark?** Excel needs it for accents; some tools dislike it. Recommendation:
   BOM on, as a template setting.
5. **Tu nombre when a person corrected one field of a machine's row?** Recommendation: the person's
   name (a person's touch makes it theirs), the model named in Problemas only if asked.
6. **Related Subjects (Tema): proposed by the model from the controlled list, or a person's only?**
   Recommendation: proposed from the list only, shown as proposed until accepted, as every field.
7. **Where does the Tema list come from?** Recommendation: a classification dimension of the project,
   imported once from the owner's Tema sheet by the person (the app's classification values), never
   shipped in the repo.
