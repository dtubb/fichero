# Source Model — The catalogue workbook: one row per folder, in the archive's template — Design Spec (#6282)

> Milestone: source-model
> Manual: TBD — a section, "Exporting your catalogue", telling a researcher that the recipe's last step
> writes the catalogue as a workbook (Excel) or sheets (CSV) in their archive's own template, one row per
> digital folder, with the people, places and institutions as lists beside it, and how to change the
> columns in the table view.
>
> Design-led (Testing Constitution). **Status: PROPOSED** (2026-10-28; revised 2026-10-29 after the
> review in the maintainer's working notes, `export-review-2026-10-29`). Written for the owner from his
> idea, paraphrased: a cataloguer's workbook must come out of the app by itself, driven by the folders'
> attributes, in the archive's own template, and the same columns must be seen and edited in a table in
> the app. His real cataloguing workbook and the one a worker built by hand on 2026-10-29 were read for
> their structure only; neither is copied into the repo or the app. Builds on `cataloguing.md` (the
> fields as folder attributes, `folder.promote_catalogue`, the EDTF date), `export/exporter.md` (the one
> record stream and its Excel emitter), `structured-data.md` (the dataset sheet),
> `../ui/catalogue-table.md` (the table view: the same template, seen and edited) and
> `models-chains-and-projects.md` (`source.onboard.kept-exported`, the export step).

Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built. Each line
names its test.

## Why its own spec

`cataloguing.md` owns the fields and already lists `catalogue.export-standards` [GAP] in one line.
`export/exporter.md` owns the record stream and its emitters (documents, entities, claims as fixed
tables). Neither says what a cataloguer's **workbook** is: a template of columns in the archive's own
words, filled from each folder's attributes and facts, with the names beside it and the provenance
behind it. That is one surface with its own template data, its own sheets and its own doors, so it gets
one spec; `cataloguing.md`'s export line points here, and the record-stream emitters stay where they
are. The table view that shows and edits the same columns is `../ui/catalogue-table.md`; the template
is defined here and used there.

## Intent (the design)

A person presses Start on a recipe whose last step is "Keep files". When the run ends they open the
folder the step names and find `Catálogo.xlsx`: sheet 1 is the catalogue, one row per digital folder (a
digital folder is one archival document or file), the columns of their archive's template in its words
and order, two header rows (the funder's English, the team's Spanish); beside it the sheets the team is
used to: `Entidades`, `Personas`, `Lugares` (the institutions, people and places the rows name, one row
each, with the folders that name them), `Catálogo` (every catalogue attribute as it stands, dates as
written and normalised), `Páginas` (the page texts), `Nombres` (the names step's entities), `Declaraciones`
(the statements) and `Notas` (who or what set each cell). They can hand it to the archive or the funder
as it is, or open the same columns in the app's table, correct a cell, and export again. Nothing in it
was invented at export: every cell is an attribute of the folder as it stands, a fact of the folder
(its name, its files, its count, its blank pages), or a name the rows carry. A cell with no value is
empty, never guessed. Writing the workbook never runs a model (`never-rerun-a-model-pass`, #6127).

It lives in `fichero-server/src/fichero_server/export_service.py` (the Excel writer gains the
template sheet, more than one header row and the extra sheets), a new
fichero-server/src/fichero_server/catalogue_sheet.py (to write: the template, the column sources,
the row builder, the problems, the shared read the table uses), shipped presets under
`fichero-server/src/fichero_server/resources/` (to write), one kept-export format
(`fichero-server/src/fichero_server/kept_export.py` `FORMATS`), one route in
`fichero-server/src/fichero_server/api/routes/ingest/export.py` and the recipe's export card in
`fichero-server/src/fichero_server/recipes/runner.py`. The app shows the template's columns and edits
the cells (`../ui/catalogue-table.md`); no rule lives in Swift.

## Prior art / best practices (don't invent from scratch)

- **The British Library Endangered Archives Programme (EAP) listing template.** The team's workbook is
  it: a first header row in EAP English (Digital Folder Name, Digital File Name (First), Digital File
  Name (Last), Number of Digital Files, Title (In Original Language/Script), Original Reference, Dates
  of Material (Gregorian Calendar), Related Towns/Cities, Related Subjects), a second row in the team's
  Spanish. We ship it as the first preset, both rows; the EAP instruction text is a column's help, not
  a third row (the hand-built sheet had two rows, and the preset reproduces it).
- **ISAD(G) and EAD.** Title, dates, extent, reference code, scope and content, access points. Every
  column of the preset maps to one ISAD(G) element, so an EAD export later
  (`catalogue.export-standards`) reads the same template.
- **Access points, typed** (ISAAR-CPF for persons and corporate bodies, the Getty TGN for places). An
  archive's access points are typed lists. Fichero's Catalogue stage writes one untyped list
  (`catalogue_access_points`); this spec types it from the project's own knowledge graph (an entity's
  type), deterministically, and keeps the untyped rest visible.
- **EDTF (Library of Congress Extended Date/Time Format).** The engine already stores
  `catalogue_date_normalised` as EDTF; the sheet RENDERS it in the archive's format and never
  re-reads the Spanish text.
- **Excel's own conventions for sheets handed around.** Text cells for everything (a date written
  "17/Marzo/1892" must not become a serial number); frozen header rows; UTF-8 with a byte-order mark
  for CSV so Excel on a Spanish Mac reads accents. The existing writer (`export_excel_xlsx`, hand-rolled
  SpreadsheetML, every cell an inline string) is kept and extended, not replaced by openpyxl.
- **Fichero's own rulings honoured, not restated.** No analysis in a catalogue (`catalogue.no-ai-analysis`);
  a field is the folder's attribute with its source (`workflows/attribute_sources.py`: a person's value
  outranks a machine's, a machine's names its run and model); one audited action per capability; no
  local paths from the app (the workbook comes back as the response or goes to a kept export's folder
  the person granted); deliverables come from the app, never a script beside it (owner 2026-10-29).

## Where each column comes from

The team's thirteen headings, kept as given. "Source" is the column's source in the template's
vocabulary (below); "empty" says what the cell holds when there is nothing.

| # | Heading (row 2, Spanish, as given) | EAP heading (row 1) | Source | Empty |
|---|---|---|---|---|
| 1 | Tu nombre | — | `cataloguer`: the account name of the person whose edit or acceptance last touched any field of the row (`attribute_sources` `by: person`); when every field is a machine's, "Fichero (<model>)" from the machine source, as `catalogue.folder-description-fields` rules. | The template's cataloguer name; else empty. |
| 2 | Nombre de carpeta digital | Digital Folder Name | `folder.name` | Never empty. |
| 3 | Digital File Name (First) | Digital File Name (First) | `folder.first_file`: the original file stem of the folder's first page in reading order (`metadata.source_filename`, else the page's name). | Empty when the folder has no pages. |
| 4 | Nombre de archivo digital (segundo) | Digital File Name (Last) | `folder.last_file`: the stem of the last page ("segundo" is the team's word for the last file, `_IMG_001` … `_IMG_125`). | Empty; equal to 3 when one page. |
| 5 | Número de archivos digitales en carpeta | Number of Digital Files | `folder.page_count`: pages directly in the folder and its subfolders. | "0". |
| 6 | Título del documento | Title (In Original Language/Script) | `attribute:catalogue_title` | Empty. |
| 7 | Referencia original de archivo físico | Original Reference | `attribute:catalogue_original_reference` (NEW optional field: a reference the records carry, a cover number, a legajo and folio; proposed by the stage only when the pages state one). | Empty. |
| 8 | Fecha de inicio del proceso legal | Dates of Material (Gregorian Calendar) | `attribute:catalogue_date_normalised` through the format `d/Mes/aaaa`: the START side of the EDTF interval, at its precision ("17/Marzo/1892"; "Marzo/1892"; "1892"); `?` and `~` are dropped and the uncertainty goes to Problemas. | Empty when no normalised date; the Dates text then goes to Problemas. |
| 9 | Lugares mencionados (Pueblos, regiones, países, ríos, quebradas, cerros, minas, fincas y otros referentes geográficos) | Related Towns/Cities | `attribute:catalogue_places` (typed from the access points, below), joined "; ". | Empty. |
| 10 | Nombres de personas mencionadas | — | `attribute:catalogue_people`, joined "; ". | Empty. |
| 11 | Descripción breve del documento: ¿Sobre qué es? | — | `description`: the folder's content when it is the promoted catalogue description (`catalogue_content_from` set), else the latest `catalogue.narrative` artifact's text. | Empty. |
| 12 | Problemas para resolver | — | `problems`: the person's `attribute:catalogue_problems`, then the computed problems (below), each one clause, "; " between. | Empty. |
| 13 | — | Related Subjects | `attribute:catalogue_subjects` (NEW optional field, terms from the project's `Tema` list only), joined "; ". | Empty. |

Institutions are not a column of the EAP preset; they are the `Entidades` sheet, from
`attribute:catalogue_institutions`. Columns 7, 12 and 13 are new optional fields of
`catalogue.folder-description-fields` (they join the stage's option list; the stage never invents
them; 12 is a person's field the model never fills).

### Typed access points

`catalogue_access_points` is one list. At promote time (`folder.promote_catalogue`, the re-parse step
that already runs with no model) each point is looked up in the project's knowledge graph by canonical
name or alias, exact after NFC and case folding: a `person` goes to `catalogue_people`, a `location` to
`catalogue_places`, an `organization` to `catalogue_institutions`, and a point no entity matches to
`catalogue_access_points_other`. The three typed lists are ordinary attributes: a person edits them in
the table, the edit is theirs, a later promote never overwrites a person's list (it may still fill an
empty one). The original list is kept unchanged. No model, no heuristics on the words: the graph types,
the person corrects.

### Computed problems

Read at export and in the table from facts the engine holds, never stored, each one clause:
- pages sorted blank (`material = blank`), as image ranges by file stem: "en blanco: IMG_017–IMG_019, IMG_025";
- pages with no lines on the working pass and not blank: "sin líneas: IMG_031";
- a gap in the image numbering: "faltan IMG_040–IMG_042";
- `lint_flags` on the folder's catalogue data, as written;
- a Dates text with no digit, or a text with no normalised date: "fecha en palabras: «mil novecientos nueve»";
- an uncertain or approximate normalised date: "fecha incierta";
- untyped access points: "sin clasificar: Juzgado del Circuito";
- a check rejection on a statement of the folder (`checking/verdicts.py`): "declaración rechazada: …".

## The template as data

- A **catalogue template** is a list of columns, each: a stable key, one or more header rows, an
  optional help line, a source, a join string (default "; ") and a format (dates only). The source
  vocabulary is fixed: `folder.name`, `folder.first_file`, `folder.last_file`, `folder.page_count`,
  `folder.path`, `attribute:<key>`, `description`, `problems`, `cataloguer`. Nothing else; no formulas.
- A project has one template: the setting `catalogue_template` on the project, a preset id or the
  project's own columns. Presets ship as JSON under the engine's resources and are read-only:
  **"EAP / Catalogación básica"** (the thirteen columns above, both header rows, dates `d/Mes/aaaa`
  with Spanish month names, the cataloguer name blank), **"EAP (English only)"** (the BL table alone:
  columns 2 to 9 and 13, one header row) and **"Todos los atributos"** (every `catalogue_*` key seen
  in the scope, alphabetically, one header row: today's Excel export).
- A person changes the template (drop, rename, reorder, add an attribute column, change the join or
  the date format) in the table view's column menu or in Settings; the change is the audited
  `catalogue.template.put`; a changed preset is saved as the project's own template; the preset is never
  edited in place.
- A CSV of headings can be imported as a template with every column's source "empty" until the person
  picks one (later; not in the build order).
- Month names and date formats are template data (`months` per language in the preset), not code.

## The sheets

Sheet 1, the catalogue, is named by the template (`Catalogación básica` in the EAP preset). Then, in
this order, each from the rows of sheet 1 or the scope's pages and graph, every cell text:

- **Entidades**, **Personas**, **Lugares**: one row per distinct value of `catalogue_institutions`,
  `catalogue_people`, `catalogue_places` across the rows, sorted by the value; columns: the value as the
  rows write it; the graph's canonical name where matched (and for Personas "Apellido, Nombre"; for
  Lugares the gazetteer's type and parent place where linked, `knowledge/linked_places.py`, else empty);
  the folders that name it ("; "); Comentarios (empty, the person's).
- **Catálogo**: one row per folder, every `catalogue_*` attribute as it stands, alphabetically, with
  `catalogue_dates` and `catalogue_date_normalised` side by side (the "Todos los atributos" preset).
- **Páginas**: the existing Documents rows (`export_excel_xlsx`'s page rows for the scope) with the
  folder name, the file stem, the page's text.
- **Nombres**: the graph's `person` entities sourced in the scope's pages that the names step wrote
  (the `find-names-tag-words` run's tool, not the spaCy pass), not rejected or merged away: canonical
  name, aliases, type, the folders, the run; a header note says which run and model.
- **Declaraciones**: the statements (`find-statements`) of the scope's pages, as the existing Claims
  sheet, filtered to the scope: subject, verb, object, the page, the excerpt.
- **Notas**: one row per (folder, column key, by: person name or "Fichero (<model>)", step, run id,
  when, what the model said, accepted by). A computed column has no Notas row.

A sheet with no rows is still written with its header, so the workbook always has the same sheets.

## Formats

- **XLSX**: one workbook; sheet 1 the catalogue with its header rows frozen, every cell text, then the
  sheets above; written in the existing writer, in write-only order (a sheet is streamed as its rows
  are made).
- **CSV**: one file per sheet in a folder (`Catálogo/Catalogación básica.csv`, `Entidades.csv` …),
  UTF-8 with a byte-order mark, comma-separated, every field quoted, CRLF, the header rows as the first
  lines.
- One row per folder; a folder with subfolders is one row for itself (its own pages' count and files)
  and one row per subfolder, in sidebar order, so a box is a block of rows.
- Accents and ñ are written as the attribute holds them (NFC, `historical-text-normalization.md`).

## When it runs

- **As the recipe's last step.** The export card (`recipes/runner.py` `_run_export`) gains the format
  `catalogue-workbook` (one file per **folder scope**, not per page), kept as a kept export
  (`kept_export.FORMATS`, `source.onboard.kept-exported`), written after Catalogue on the run's last
  batch, and rewritten by the quiet-period hook when a folder's attributes or description change. A run
  with no Catalogue stage still writes the workbook, with the fact columns filled and the fields empty.
- **On demand** from a folder or a project: File ▸ Export ▸ Catalogue workbook…, the folder's context
  menu, and the table view's Export button, through `POST /api/export/catalogue-workbook` (scope: a
  folder or project id; format `xlsx` or `csv`; the project's template unless one is named), returning
  the file as the response, or writing into a kept export's folder when one is named. No local path in
  the request.
- **CLI and MCP** reach the same route through the generated surface (`fichero export
  catalogue-workbook`, `fichero_export_catalogue_workbook`).
- **Never a model.** The builder reads attributes, pages, entities, claims and the run's record. A folder
  the Catalogue stage has not described has empty field columns; the Activity line says how many
  ("Catálogo.xlsx: 552 filas, 14 sin describir").

## At 100k pages

A collection of 100,000 pages is some thousands of folders. Folders are read in batches of 500 (one
query for the folders, one for their pages' names, order and `material`, one for the attributes and
sources, one for the entities of the batch's pages, one for the flags and verdicts: five queries per
batch, never one per folder); each batch's rows go to the CSV or the write-only workbook as they are
made. The authority sheets keep only distinct values and folder names across batches. A workbook of
5,000 folders writes in under a minute on the M1; the job runs on the background `database` lane like
every kept export.

## Behaviors

- `catalogue.export.attr-columns-today` — **[OK]** (#6267, #6270) `POST /api/export/excel`'s Documents
  sheet has folder rows and one `attr:<key>` column per attribute key, alphabetical, with
  `catalogue_date_normalised` among them; a promoted folder's description prints once. This is the
  "Todos los atributos" preset's content and stays as it is. Tests:
  `fichero-server/tests/unit/api/test_routes_export.py::TestExcelExportAttributes`,
  `::TestCatalogueTextOnlyDroppedInExcel::test_excel_has_the_normalised_date_column`.
- `catalogue.export.one-row-per-folder` — **[GAP]** (#6282) the catalogue sheet holds one row per
  folder in the scope, in sidebar order, a folder with subfolders first and its subfolders after it;
  the fact columns (name, first file, last file, page count) are filled for every row from the folder
  and its pages alone; file stems come from `metadata.source_filename`, else the page name. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_rows.py.
- `catalogue.export.cells-from-attributes-never-guessed` — **[GAP]** (#6282) a field column holds the
  folder's attribute of that key as it stands (a person's value over a machine's); a folder with no
  value has an empty cell; writing the workbook never calls a model or reruns the Catalogue stage
  (#6127); a run with no Catalogue stage writes the fact columns and leaves the fields empty. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_rows.py.
- `catalogue.export.cataloguer-column` — **[GAP]** (#6282) Tu nombre is the account name of the person
  whose edit or acceptance last touched any field of the row, else "Fichero (<model>)" from the machine
  source, else the template's cataloguer name, else empty. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_rows.py.
- `catalogue.export.access-points-typed-by-the-graph` — **[GAP]** (#6282, #6267) `folder.promote_catalogue`
  types each access point by the project's entities (canonical name or alias, exact after NFC and case
  folding, no model) into `catalogue_people`, `catalogue_places`, `catalogue_institutions`, the rest
  into `catalogue_access_points_other`; `catalogue_access_points` is unchanged; a list a person set is
  never overwritten; the undo puts the four back. Test:
  fichero-server/tests/unit/recipes/test_catalogue_access_points_typed.py.
- `catalogue.export.people-places-institutions-columns` — **[GAP]** (#6282) Lugares and Nombres read
  `catalogue_places` and `catalogue_people` joined "; " in the attribute's order; institutions never
  appear in either and go to the Entidades sheet. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_rows.py.
- `catalogue.export.dates-in-the-archives-format` — **[GAP]** (#6282, #6270) the date column renders the
  start side of `catalogue_date_normalised` through the template's format: "17/Marzo/1892" for a day,
  "Marzo/1892" for a month, "1892" for a year, empty when there is none; `?` and `~` are dropped and
  noted in Problemas; the month names come from the template, not the code; `catalogue_dates` text is
  never parsed at export. Test: fichero-server/tests/unit/export/test_catalogue_sheet_dates.py.
- `catalogue.export.problems-column` — **[GAP]** (#6282) Problemas para resolver joins the person's
  `catalogue_problems`, then the computed clauses: blank pages as image ranges, pages without lines,
  numbering gaps, `lint_flags`, a Dates text in words or without a normalised date, an uncertain date,
  untyped access points, a rejected statement; one function computes them for the export and the
  table; nothing computed is stored. Test: fichero-server/tests/unit/export/test_catalogue_sheet_problems.py.
- `catalogue.export.new-optional-fields` — **[GAP]** (#6087, #6282) the Catalogue stage's option list
  gains Referencia original de archivo físico (`catalogue_original_reference`), Problemas para resolver
  (`catalogue_problems`, a person's field the model never fills) and Related Subjects
  (`catalogue_subjects`, from the project's Tema list only); a model fills a field only from evidence in
  the records. Test: fichero-server/tests/unit/recipes/test_catalogue_stage_optional_fields.py.
- `catalogue.export.template-is-data` — **[GAP]** (#6282) a template is a list of columns (key, header
  rows, help, source from the fixed vocabulary, join, format); the three presets ship as read-only JSON
  resources; a project's template is the setting `catalogue_template`; `GET /api/projects/{id}/catalogue-template`
  returns it resolved; the audited `catalogue.template.put` saves a changed one as the project's own and
  never edits a preset; an unknown source or attribute key is refused in words. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_template.py.
- `catalogue.export.eap-preset-reproduces-the-sheet` — **[GAP]** (#6282) the preset "EAP / Catalogación
  básica" writes the thirteen columns above in that order, row 1 the EAP English, row 2 the Spanish as
  given, both frozen, and a fixture of three folders (one described by a fake model, one typed by a
  person, one undescribed) renders cell for cell as the matrix says, from attributes alone, with no
  model client in the process. Test: fichero-server/tests/unit/export/test_catalogue_sheet_eap_preset.py.
- `catalogue.export.authority-sheets-from-the-rows` — **[GAP]** (#6282, #5380) Entidades, Personas and
  Lugares hold one row per distinct value of the typed attributes across the rows, sorted, with the
  graph's canonical form where matched ("Apellido, Nombre" for a person; type and parent place for a
  linked place, else empty), the folders that name it, and an empty Comentarios; a sheet with no rows
  still has its header. Test: fichero-server/tests/unit/export/test_catalogue_sheet_authorities.py.
- `catalogue.export.names-and-statements-sheets` — **[GAP]** (#6282) Nombres holds the `person`
  entities sourced in the scope that the names step's tool wrote, not rejected or merged away, with a
  header note naming the run and model; Declaraciones holds the statements step's claims of the scope;
  Páginas holds the scope's page rows; Catálogo holds every `catalogue_*` attribute. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_kg_sheets.py.
- `catalogue.export.notas-sheet-is-the-provenance` — **[GAP]** (#6282) Notas holds one row per folder
  and attribute key with by, step, run, when, what the model said and accepted by, from
  `attribute_sources`; a computed column has no row; a person's one-field edit appears as theirs.
  Test: fichero-server/tests/unit/export/test_catalogue_sheet_notas.py.
- `catalogue.export.xlsx-and-csv` — **[GAP]** (#6282) XLSX is one workbook (the catalogue first with its
  header rows frozen, then the sheets in the order above, every cell text); CSV is one file per sheet,
  UTF-8 with a byte-order mark, every field quoted, CRLF; both carry accents and ñ unchanged. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_formats.py.
- `catalogue.export.recipe-last-step` — **[GAP]** (#5485, #6282) the export card accepts the format
  `catalogue-workbook` per folder scope; it is written after Catalogue on the run's last batch, kept as
  a kept export and rewritten by the quiet-period hook when a folder's attributes or description
  change. Test: fichero-server/tests/unit/recipes/test_recipe_export_catalogue_workbook.py.
- `catalogue.export.on-demand-route` — **[GAP]** (#6282) `POST /api/export/catalogue-workbook` takes a
  folder or project id, a format and an optional template id, returns the file as the response or
  writes into a named kept export; the CLI and MCP reach it through the generated surface; the route
  runs the same builder as the recipe step. Test:
  fichero-server/tests/unit/api/test_export_catalogue_workbook_route.py.
- `catalogue.export.app-doors` — **[GAP]** (#6282, #507) File ▸ Export ▸ Catalogue workbook…, the
  folder's context menu and the table view's Export button call the route and offer a save panel; no
  local path is sent. Test: fichero/Tests/Unit/general/Views/Library/CatalogueExportCommandTests.swift.
- `catalogue.export.streams-at-scale` — **[GAP]** (#6282) folders are read and written in batches of
  500 with five queries per batch and no per-folder query; a 5,000-folder workbook holds no more than
  one batch of rows in memory at a time. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_streaming.py (counts queries on a fake
  database of 2,000 folders).

## Build order

### Stage 1 — The sheet from what exists
#### Step 1.1 — Typed access points at promote
- Behaviours: `catalogue.export.access-points-typed-by-the-graph`
- Tests: fichero-server/tests/unit/recipes/test_catalogue_access_points_typed.py
- Size: S
#### Step 1.2 — The template and its presets
- Behaviours: `catalogue.export.template-is-data`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_template.py
- Size: M
#### Step 1.3 — Rows from folders and attributes
- Behaviours: `catalogue.export.one-row-per-folder`, `catalogue.export.cells-from-attributes-never-guessed`, `catalogue.export.cataloguer-column`, `catalogue.export.people-places-institutions-columns`, `catalogue.export.dates-in-the-archives-format`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_rows.py, fichero-server/tests/unit/export/test_catalogue_sheet_dates.py
- Depends on: 1.1, 1.2
- Size: M
#### Step 1.4 — Problems and the EAP preset end to end
- Behaviours: `catalogue.export.problems-column`, `catalogue.export.eap-preset-reproduces-the-sheet`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_problems.py, fichero-server/tests/unit/export/test_catalogue_sheet_eap_preset.py
- Depends on: 1.3
- Size: M

### Stage 2 — The workbook and its doors
#### Step 2.1 — The other sheets and the two formats
- Behaviours: `catalogue.export.authority-sheets-from-the-rows`, `catalogue.export.names-and-statements-sheets`, `catalogue.export.notas-sheet-is-the-provenance`, `catalogue.export.xlsx-and-csv`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_authorities.py, fichero-server/tests/unit/export/test_catalogue_sheet_kg_sheets.py, fichero-server/tests/unit/export/test_catalogue_sheet_notas.py, fichero-server/tests/unit/export/test_catalogue_sheet_formats.py
- Size: M
#### Step 2.2 — The route and the recipe step
- Behaviours: `catalogue.export.on-demand-route`, `catalogue.export.recipe-last-step`, `catalogue.export.streams-at-scale`
- Tests: fichero-server/tests/unit/api/test_export_catalogue_workbook_route.py, fichero-server/tests/unit/recipes/test_recipe_export_catalogue_workbook.py, fichero-server/tests/unit/export/test_catalogue_sheet_streaming.py
- Depends on: 2.1
- Size: M
#### Step 2.3 — The new optional fields and the app's doors
- Behaviours: `catalogue.export.new-optional-fields`, `catalogue.export.app-doors`
- Tests: fichero-server/tests/unit/recipes/test_catalogue_stage_optional_fields.py, fichero/Tests/Unit/general/Views/Library/CatalogueExportCommandTests.swift
- Depends on: 2.2
- Size: M

Stage 3 is the table view (`../ui/catalogue-table.md`), which depends on 1.2 and 1.4.

## Test matrix

To be filled at approval. Fixture: a scratch project of three folders built with
`seed_test_library.py` (one described by a fake model with typed access points, one typed by a
person including a corrected date, one undescribed with two blank pages), with the thirteen cells
each row should render; the team's workbook is never a fixture.

## Open questions for the owner

1. **Type the access points by the graph into three attributes at promote, the rest to Problemas?**
   Recommendation: yes. It is deterministic, needs no model, and a person corrects the three lists in
   the table. The alternative, the raw graph per folder, is what the hand-built workbook rejected.
2. **Authority sheets from the rows (what the sheet names), or from the graph?** Recommendation: from
   the rows, with the graph's canonical form beside each value; a graph-wide authority export belongs
   to `kg/project-gazetteer-and-names.md` (`gazetteer.export`).
3. **The date column from the normalised EDTF start, with the Spanish text only flagged?**
   Recommendation: yes; a date in words is never rewritten at export, it is a Problemas clause and a
   cell a person fixes once in the table (the fix is stamped and shows in Notas).
4. **Nombres from the names step only, not spaCy?** Recommendation: yes, with the header note naming
   the run; a project with no names run gets an empty Nombres sheet, never the spaCy pass.
5. **One template per project, edited in the table's column menu?** Recommendation: yes; per-folder
   templates and CSV import of headings wait for a second archive.
6. **Tu nombre when a person corrected one field of a machine's row?** Recommendation: the person's
   name; the model stays named in Notas.
