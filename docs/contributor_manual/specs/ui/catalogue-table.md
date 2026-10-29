# Catalogue Table — folders as rows, template columns, edits as attribute edits — Design Spec (#6282, #5636)

> Milestone: source-model
> Manual: TBD — a section, "The catalogue table", telling a researcher that a project or box opens as
> a table with one row per folder and the columns of their archive's template, that a cell edits in
> place and is theirs from then on, that a machine's value shows as proposed until accepted, and that
> Export writes exactly what the table shows.
>
> Design-led (Testing Constitution). **Status: PROPOSED** (2026-10-29). Written for the owner from his
> ruling of the same day, paraphrased: the same columns a cataloguer exports must be seen and edited in
> a table in the app, so what you see is what you export. Builds on `../source/catalogue-export.md`
> (the template, the column sources, the computed problems: defined there, used here),
> `../source/structured-data.md` (the dataset sheet, `structured.app.sheet-over-a-folder`, and the
> paged dataset query), `../source/cataloguing.md` (`catalogue.folder-description-fields`: "a row per
> folder and a column per field"), `undo-everywhere.md` and `../safety/the-record.md` (every edit one
> audited action).

Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built. Each line
names its test.

## Intent (the design)

A person selects a project or a box in the sidebar and chooses Table. They see one row per folder
(a folder with subfolders first, its subfolders after it, in sidebar order), and the columns of the
project's catalogue template in the template's own words: the facts (name, first and last file, page
count), the fields (title, reference, date, places, people, subjects), the description, the problems.
A machine's value shows in the proposed colour with the model's name on hover; a person's value shows
plain; an empty cell is empty. They click a cell, type, press Return: the value is saved, it is theirs,
a run never overwrites it, and ⌘Z takes it back. They sort by any column, filter by text or by state
(proposed, accepted, empty, with problems), hide or reorder columns, and press Export: the workbook
that comes out has exactly these columns in this order (`../source/catalogue-export.md`). The column
menu edits the project's template, so the table and the export never disagree.

It lives in the engine's `catalogue_sheet.py` (the shared read: rows, cells with sources, problems),
one query mode on `POST /api/documents/dataset/query` (`api/routes/document/dataset.py`,
`db/dataset_query.py`: rows = folders, columns = the template), the existing `document.update` action
(`api/routes/document/documents.py`, person-stamped and undoable) for the write, and in the app the
dataset Sheet (`fichero/fichero/Views/Library/ViewModes/Dataset/Grid/DatasetGridView.swift`,
`DatasetModeStore.swift`) given a second source of rows and columns. No rule lives in Swift.

## Prior art / best practices (don't invent from scratch)

- **The dataset Sheet already built** (`structured-data.md`): rows are nodes, columns are declared
  attributes, cells edit in place and commit through the engine, which stamps a person source; the
  query is paged and sorted on the server. The catalogue table is that sheet with folders for rows and
  a template for columns, not a second grid.
- **Tinderbox attribute browser and Finder's list view**: columns chosen from a menu, sort by a click,
  the selection shared with the rest of the window. The Library's outline `Table`
  (`LibraryView+TableColumns.swift`) already routes selection to preview and inspector; the catalogue
  table keeps that.
- **Spreadsheet conventions for review**: a cell's state by colour (proposed, accepted, person's), a
  cell's provenance on hover, computed columns read-only and visibly so. Airtable and Google Sheets'
  "computed field" is the model for the problems column: shown, sorted and filtered, never typed into.
- **Fichero's own rulings honoured, not restated**: no wholesale list re-render (a commit replaces one
  row); one audited action per capability (`document.update`); a person's value outranks a machine's
  (`attribute_sources`); undo everywhere; no local paths.

## The design

- **Rows** are the folders in the scope (a project, a box, or any folder), `doc_type = folder`,
  workflow and workspace nodes left out, in sidebar order, depth shown by indentation of the name. A
  folder with no pages is still a row.
- **Columns** are the project's template's columns (`../source/catalogue-export.md`, "The template as
  data"), headed by the template's second header row (the team's language) with the first row on
  hover; the "Todos los atributos" preset shows every `catalogue_*` key.
- **Cells** are `{value, by, model, run_id, accepted_by, computed}` from one engine read shared with
  the export, so a cell renders the same string the export writes (dates included). A computed cell
  (facts, description, problems) is read-only. An attribute cell edits.
- **Edit** commits on Return or focus-out through `document.update` with the row's own attributes
  (as the dataset sheet does); the engine stamps the key as the person's; the store replaces that row
  only; ⌘Z inverts the action. A date cell edits `catalogue_dates` and the engine re-derives the
  normalised date and the years as one group; a person may edit the normalised cell directly, and it
  wins. Editing a list cell (people, places, institutions, subjects) edits the list "; "-separated.
- **Accept** on a proposed cell (Return without a change, or the row's Accept menu) answers the
  proposal (`accepted_by`), which makes the row's Tu nombre the person's.
- **Sort and filter** are the dataset query's, on the server: sort by any column (computed ones by
  their rendered string), filter by text in any column, and by state: proposed, accepted, person's,
  empty, with problems. A filter and sort are remembered per project (`structured.view.saved-views-on-folders`).
- **Columns menu**: show, hide, reorder, rename a heading, add an attribute column, change the join or
  date format: each is `catalogue.template.put` on the project's template, so the export follows. A
  preset is copied to the project's own template on the first change.
- **Export** button on the table: `POST /api/export/catalogue-workbook` for the table's scope with the
  project's template, a save panel, no local path.
- **At scale**: the query is paged (500 rows) and the grid fetches the next page on scroll; 5,000
  folders scroll without a reload of the rest.

## Behaviors

- `catalogue.table.sheet-exists-today` — **[PARTIAL]** (#5636) the dataset Sheet shows one folder's
  nodes with the prototype's declared attributes as editable columns and commits a cell through
  `document.update`, person-stamped and undoable. Built: `DatasetGridView.swift`, `DatasetModeStore.swift`,
  `api/routes/document/dataset.py`. Not built: folders as rows, template columns, cell sources, the
  column menu writing a template. Tests:
  `fichero/Tests/Unit/general/Services/DatasetModeStoreFilterTests.swift`,
  `fichero-server/tests/unit/api/test_dataset_query.py`.
- `catalogue.table.folders-as-rows` — **[GAP]** (#6282) the dataset query takes `rows: folders` with a
  scope id and returns one row per folder in sidebar order, depth included, workflow and workspace
  nodes left out, paged at 500. Test: fichero-server/tests/unit/api/test_dataset_query_folders.py.
- `catalogue.table.columns-from-the-template` — **[GAP]** (#6282) the query takes the project's
  template (or a named one) and returns, per row, one cell per column with `{value, by, model, run_id,
  accepted_by, computed}`, rendered by the same read the export uses, so a cell's string equals the
  exported cell. Test: fichero-server/tests/unit/api/test_dataset_query_template_columns.py.
- `catalogue.table.cell-state-is-visible` — **[GAP]** (#6282) a machine's value shows in the proposed
  colour with the model on hover, a person's plain, an accepted one with a mark, an empty cell empty,
  a computed cell read-only and greyed; the column heading is the template's second row with the
  first on hover. Test: fichero/Tests/Unit/general/Views/Library/CatalogueTableCellStateTests.swift.
- `catalogue.table.edit-is-an-audited-attribute-edit` — **[GAP]** (#6282) a cell commit calls
  `document.update` with the row's own attributes; the engine stamps the key as the person's; the
  store replaces one row; ⌘Z puts the old value back; a computed cell refuses the edit; a list cell
  edits the "; "-joined list. Test: fichero/Tests/Unit/general/Views/Library/CatalogueTableEditTests.swift,
  fichero-server/tests/unit/api/test_document_update_stamps_person.py.
- `catalogue.table.date-edit-keeps-the-group` — **[GAP]** (#6282, #6270) editing the Dates text
  re-derives `catalogue_date_normalised`, `_start` and `_end` with no model; editing the normalised
  cell directly wins over the text and is stamped; both show in the table at once. Test:
  fichero-server/tests/unit/recipes/test_catalogue_date_edit_group.py.
- `catalogue.table.accept-a-proposed-cell` — **[GAP]** (#6282) Return on an unchanged proposed cell,
  or Accept in the row menu, answers the proposal as accepted by the person and the row's cataloguer
  becomes the person. Test: fichero-server/tests/unit/api/test_catalogue_accept_cell.py.
- `catalogue.table.sort-and-filter-on-the-server` — **[GAP]** (#6282, #5636) sort by any column and
  filter by text or by state (proposed, accepted, person's, empty, with problems) run in the dataset
  query, paged; the grid fetches the next page on scroll. Test:
  fichero-server/tests/unit/api/test_dataset_query_folders.py,
  fichero/Tests/Unit/general/Views/Library/CatalogueTablePagingTests.swift.
- `catalogue.table.column-menu-edits-the-template` — **[GAP]** (#6282) show, hide, reorder, rename,
  add an attribute column, change a join or date format call `catalogue.template.put`; a preset is
  copied to the project's own template on the first change; the export then follows; ⌘Z undoes the
  template change. Test: fichero-server/tests/unit/export/test_catalogue_sheet_template.py,
  fichero/Tests/Unit/general/Views/Library/CatalogueTableColumnMenuTests.swift.
- `catalogue.table.export-what-you-see` — **[GAP]** (#6282) the table's Export button exports the
  table's scope with the project's template through the workbook route and a save panel; a fixture
  project's table cells and its exported sheet 1 agree cell for cell. Test:
  fichero-server/tests/unit/export/test_catalogue_table_matches_export.py.

## Build order

### Stage 1 — The engine's read
#### Step 1.1 — Folders as rows with template columns
- Behaviours: `catalogue.table.folders-as-rows`, `catalogue.table.columns-from-the-template`, `catalogue.table.sort-and-filter-on-the-server`
- Tests: fichero-server/tests/unit/api/test_dataset_query_folders.py, fichero-server/tests/unit/api/test_dataset_query_template_columns.py
- Size: M
#### Step 1.2 — Edits, dates and acceptance
- Behaviours: `catalogue.table.edit-is-an-audited-attribute-edit`, `catalogue.table.date-edit-keeps-the-group`, `catalogue.table.accept-a-proposed-cell`
- Tests: fichero-server/tests/unit/api/test_document_update_stamps_person.py, fichero-server/tests/unit/recipes/test_catalogue_date_edit_group.py, fichero-server/tests/unit/api/test_catalogue_accept_cell.py
- Depends on: 1.1
- Size: M

### Stage 2 — The app's table
#### Step 2.1 — The grid over folders
- Behaviours: `catalogue.table.sheet-exists-today`, `catalogue.table.cell-state-is-visible`
- Tests: fichero/Tests/Unit/general/Views/Library/CatalogueTableCellStateTests.swift, fichero/Tests/Unit/general/Views/Library/CatalogueTableEditTests.swift, fichero/Tests/Unit/general/Views/Library/CatalogueTablePagingTests.swift
- Depends on: 1.2
- Size: M
#### Step 2.2 — The column menu and Export
- Behaviours: `catalogue.table.column-menu-edits-the-template`, `catalogue.table.export-what-you-see`
- Tests: fichero/Tests/Unit/general/Views/Library/CatalogueTableColumnMenuTests.swift, fichero-server/tests/unit/export/test_catalogue_table_matches_export.py
- Depends on: 2.1
- Size: M

Depends on `../source/catalogue-export.md` steps 1.2 (the template) and 1.4 (the problems and the
preset end to end).

## Test matrix

To be filled at approval. Fixture: the export spec's three-folder project; the table's rendered cells
and the exported sheet compared cell for cell.

## Open questions for the owner

See `../source/catalogue-export.md`; the table adds none of its own. One recommendation to confirm:
the table is the dataset Sheet given folders and a template, not a new view mode.
