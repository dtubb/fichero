# Catalogue Table — folders as rows, the prototype's columns, edits as attribute edits — Design Spec (#6282, #5636)

> Milestone: source-model
> Manual: TBD — a section, "The catalogue table", telling a researcher that a project or box opens as
> a table with one row per folder and the columns of the folders' kind (their prototype), that a cell
> edits in place and is theirs from then on, that a machine's value shows as proposed until accepted,
> that an inherited value shows greyed with where it came from, and that Export writes exactly what
> the table shows.
>
> Design-led (Testing Constitution). **Status: PROPOSED** (2026-10-29; revised the same day with the
> owner's rulings, decided below). Written for the owner from his ruling of the same day, paraphrased:
> the same columns a cataloguer exports must be seen and edited in a table in the app, so what you see
> is what you export; and the columns come from the rows' prototype, which cascades. Builds on
> `../source/attributes-and-prototypes.md` (THE FOUNDATION: the kind and value cascades, a template is
> a prototype's columns, a column change copies a built-in), `../source/catalogue-export.md` (the
> column sources, the computed problems, the date rules: defined there, used here),
> `../source/structured-data.md` (the dataset sheet, `structured.app.sheet-over-a-folder`, and the
> paged dataset query), `../source/cataloguing.md` (`catalogue.folder-description-fields`: "a row per
> folder and a column per field"), `undo-everywhere.md` and `../safety/the-record.md` (every edit one
> audited action).

Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built. Each line
names its test.

## Intent (the design)

A person selects a project or a box in the sidebar and chooses Table. They see one row per folder
(a folder with subfolders first, its subfolders after it, in sidebar order), and the columns of the
rows' effective prototype in its own words: the facts (name, first and last file, page count), the
fields (title, reference, date, places, people, subjects), the description, the problems. A machine's
value shows in the proposed colour with the model's name on hover; a person's value shows plain; a
value inherited from the box or a prototype's default shows greyed with "from Caja 12" or "default"
on hover; an empty cell is empty. They click a cell, type, press Return: the value is saved, it is
theirs, a run never overwrites it, and ⌘Z takes it back. They sort by any column, filter by text or
by state (proposed, accepted, inherited, empty, with problems), hide or reorder columns, and press
Export: the workbook that comes out has exactly these columns in this order
(`../source/catalogue-export.md`). The column menu edits the rows' prototype, so the table and the
export never disagree, and a box whose folders have different kinds shows each kind's columns under
its heading.

It lives in the engine's `catalogue_sheet.py` (the shared read: rows, cells with sources and origin,
problems), one query mode on `POST /api/documents/dataset/query` (`api/routes/document/dataset.py`,
`db/dataset_query.py`: rows = folders, columns = the effective prototype), the existing
`document.update` action (`api/routes/document/documents.py`, person-stamped and undoable) for the
write, the audited `classification.patch` for the column menu, and in the app the dataset Sheet
(`fichero/fichero/Views/Library/ViewModes/Dataset/Grid/DatasetGridView.swift`,
`DatasetModeStore.swift`) given a second source of rows and columns. No rule lives in Swift.

## Prior art / best practices (don't invent from scratch)

- **The dataset Sheet already built** (`structured-data.md`): rows are nodes, columns are declared
  attributes, cells edit in place and commit through the engine, which stamps a person source; the
  query is paged and sorted on the server. The catalogue table is that sheet with folders for rows and
  the effective prototype for columns, not a second grid.
- **Tinderbox attribute browser and Finder's list view**: columns chosen from a menu, sort by a click,
  the selection shared with the rest of the window; an inherited value shown greyed until the note
  sets its own. The Library's outline `Table` (`LibraryView+TableColumns.swift`) already routes
  selection to preview and inspector; the catalogue table keeps that.
- **Spreadsheet conventions for review**: a cell's state by colour (proposed, accepted, person's,
  inherited), a cell's provenance on hover, computed columns read-only and visibly so. Airtable and
  Google Sheets' "computed field" is the model for the problems column: shown, sorted and filtered,
  never typed into.
- **Fichero's own rulings honoured, not restated**: no wholesale list re-render (a commit replaces one
  row); one audited action per capability (`document.update`, `classification.patch`); a person's
  value outranks a machine's (`attribute_sources`); undo everywhere; no local paths; logic in the
  engine.

## The design

- **Rows** are the folders in the scope (a project, a box, or any folder), `doc_type = folder`,
  workflow and workspace nodes left out, in sidebar order, depth shown by indentation of the name. A
  folder with no pages is still a row.
- **Columns** are the rows' effective prototype's columns (`../source/attributes-and-prototypes.md`,
  "A template is a prototype's columns"), headed by the labels in the project's metadata language with
  the other label language on hover; rows of mixed kinds show the union, grouped under each kind's
  name; rows with no kind show every `catalogue_*` key.
- **Cells** are `{value, origin, from, by, model, run_id, accepted_by, computed}` from one engine read
  shared with the export, so a cell renders the same string the export writes (dates included).
  `origin` is here, inherited, default or empty, and `from` names the node or prototype it came from.
  A computed cell (facts, description, problems) is read-only. An attribute cell edits.
- **Edit** commits on Return or focus-out through `document.update` with the row's own attributes
  (as the dataset sheet does); the engine stamps the key as the person's; the store replaces that row
  only; ⌘Z inverts the action. Editing an inherited or default cell writes the row's own value (the
  ancestor is untouched); clearing it makes the cell inherit again. A date cell edits `catalogue_dates`
  and the engine re-derives the normalised date and the years as one group with the parser alone; a
  person may edit the normalised cell directly, and it wins over the text, the parser and the model's
  proposal (`catalogue.export.dates-parser-checks-the-model`). Editing a list cell (people, places,
  institutions, subjects) edits the list separated by the declaration's join ("|" in the EAP preset),
  people shown by its name order; an entry added or removed is a decision on the name in the graph
  (`kg.attr.folder-names-are-attributes`); a subject outside the prototype's Tema vocabulary is
  refused and the cell offers the list.
- **Accept** on a proposed cell (Return without a change, or the row's Accept menu) answers the
  proposal (`accepted_by`), which adds the person to the row's Tu nombre. A date cell with two readings
  (the parser's and the model's) offers both to pick from.
- **Sort and filter** are the dataset query's, on the server: sort by any column (computed ones by
  their rendered string), filter by text in any column, and by state: proposed, accepted, person's,
  inherited, empty, with problems. A filter and sort are remembered per project
  (`structured.view.saved-views-on-folders`).
- **Columns menu**: show, hide, reorder, rename a heading, add an attribute column, change the join or
  date format: each is `classification.patch` on the rows' effective prototype; a built-in is copied
  to a project-owned child on the first change and the change lands there
  (`proto.template.edit-copies-a-builtin`), so the export follows. Set kind… on a row or a selection
  assigns a prototype (`document.assign_prototype`); Clear kind makes it inherit again.
- **Export** button on the table: `POST /api/export/catalogue-workbook` for the table's scope with the
  rows' effective prototype, a save panel, no local path; a second item exports the Word transcript per
  folder (`catalogue.export.word-transcript-per-folder`).
- **At scale**: the query is paged (500 rows) and the grid fetches the next page on scroll; 5,000
  folders scroll without a reload of the rest.

## Behaviors

- `catalogue.table.sheet-exists-today` — **[PARTIAL]** (#5636) the dataset Sheet shows one folder's
  nodes with the prototype's declared attributes as editable columns and commits a cell through
  `document.update`, person-stamped and undoable. Built: `DatasetGridView.swift`, `DatasetModeStore.swift`,
  `api/routes/document/dataset.py`. Not built: folders as rows, the effective prototype's columns,
  cell sources and origin, the column menu patching the prototype. Tests:
  `fichero/Tests/Unit/general/Services/DatasetModeStoreFilterTests.swift`,
  `fichero-server/tests/unit/api/test_dataset_query.py`.
- `catalogue.table.folders-as-rows` — **[GAP]** (#6282) the dataset query takes `rows: folders` with a
  scope id and returns one row per folder in sidebar order, depth included, workflow and workspace
  nodes left out, paged at 500. Test: fichero-server/tests/unit/api/test_dataset_query_folders.py.
- `catalogue.table.columns-from-the-effective-prototype` — **[GAP]** (#6282) the query returns the
  columns of the rows' effective prototype (one kind: its columns in declared order; mixed: the union
  grouped by kind; none: every `catalogue_*` key), or of a named prototype, and per row one cell per
  column with `{value, origin, from, by, model, run_id, accepted_by, computed}`, rendered by the same
  read the export uses, so a cell's string equals the exported cell. Test:
  fichero-server/tests/unit/api/test_dataset_query_template_columns.py.
- `catalogue.table.cell-state-is-visible` — **[GAP]** (#6282) a machine's value shows in the proposed
  colour with the model on hover, a person's plain, an accepted one with a mark, an inherited or
  default value greyed with its origin on hover, an empty cell empty, a computed cell read-only and
  greyed; the column heading is the metadata language's label with the other language on hover; a
  mixed scope shows each kind's name over its columns. Test:
  fichero/Tests/Unit/general/Views/Library/CatalogueTableCellStateTests.swift.
- `catalogue.table.edit-is-an-audited-attribute-edit` — **[GAP]** (#6282) a cell commit calls
  `document.update` with the row's own attributes; the engine stamps the key as the person's; the
  store replaces one row; ⌘Z puts the old value back; a computed cell refuses the edit; a list cell
  edits the list by the declaration's join and name order and a subject outside the vocabulary is
  refused; editing an inherited cell writes the row's own value and leaves the ancestor alone;
  clearing it inherits again. Test:
  fichero/Tests/Unit/general/Views/Library/CatalogueTableEditTests.swift,
  fichero-server/tests/unit/api/test_document_update_stamps_person.py.
- `catalogue.table.date-edit-keeps-the-group` — **[GAP]** (#6282, #6270) editing the Dates text
  re-derives `catalogue_date_normalised`, `_start` and `_end` with the parser and no model; editing the
  normalised cell directly wins over the text, the parser and the model's proposal and is stamped; a
  cell with two readings offers both; both text and EDTF show in the table at once. Test:
  fichero-server/tests/unit/recipes/test_catalogue_date_edit_group.py.
- `catalogue.table.accept-a-proposed-cell` — **[GAP]** (#6282) Return on an unchanged proposed cell,
  or Accept in the row menu, answers the proposal as accepted by the person and adds the person to the
  row's Tu nombre, the model staying listed after them. Test:
  fichero-server/tests/unit/api/test_catalogue_accept_cell.py.
- `catalogue.table.sort-and-filter-on-the-server` — **[GAP]** (#6282, #5636) sort by any column and
  filter by text or by state (proposed, accepted, person's, inherited, empty, with problems) run in the
  dataset query, paged; the grid fetches the next page on scroll. Test:
  fichero-server/tests/unit/api/test_dataset_query_folders.py,
  fichero/Tests/Unit/general/Views/Library/CatalogueTablePagingTests.swift.
- `catalogue.table.column-menu-edits-the-prototype` — **[GAP]** (#6282) show, hide, reorder, rename,
  add an attribute column, change a join or date format call `classification.patch` on the rows'
  effective prototype; a built-in is copied to a project-owned child on the first change; the export
  then follows; ⌘Z undoes the patch; Set kind… and Clear kind on a row or selection call
  `document.assign_prototype`. Test: fichero-server/tests/unit/api/test_prototype_edit_copies_builtin.py,
  fichero/Tests/Unit/general/Views/Library/CatalogueTableColumnMenuTests.swift.
- `catalogue.table.export-what-you-see` — **[GAP]** (#6282) the table's Export button exports the
  table's scope with the rows' effective prototype through the workbook route and a save panel; a
  fixture project's table cells and its exported sheet 1 agree cell for cell; a second item exports the
  Word transcript per folder. Test: fichero-server/tests/unit/export/test_catalogue_table_matches_export.py.

## Build order

Depends on `../source/attributes-and-prototypes.md` step 2.1 (a column change copies a built-in) and
`../source/catalogue-export.md` step 1.5 (the template from the prototype, the problems and the EAP
sheet end to end).

### Stage 1 — The engine's read
#### Step 1.1 — Folders as rows with the effective prototype's columns
- Behaviours: `catalogue.table.folders-as-rows`, `catalogue.table.columns-from-the-effective-prototype`, `catalogue.table.sort-and-filter-on-the-server`
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
#### Step 2.2 — The column menu, Set kind and Export
- Behaviours: `catalogue.table.column-menu-edits-the-prototype`, `catalogue.table.export-what-you-see`
- Tests: fichero/Tests/Unit/general/Views/Library/CatalogueTableColumnMenuTests.swift, fichero-server/tests/unit/export/test_catalogue_table_matches_export.py
- Depends on: 2.1
- Size: M

## Test matrix

To be filled at approval. Fixture: the export spec's three-folder project under an `eap_box`, with the
archive reference set on the box and overridden on one folder; the table's rendered cells, their
origins and the exported sheet compared cell for cell.

## Rulings (owner, 2026-10-29; decided)

1. The table's columns are the effective prototype of the rows shown, following the cascade; the
   column menu edits that prototype; there is no template setting of its own.
2. The table is the dataset Sheet given folders and a prototype, not a new view mode.

## Open questions for the owner

None of its own; see `../source/attributes-and-prototypes.md` (mixed kinds in one scope).
