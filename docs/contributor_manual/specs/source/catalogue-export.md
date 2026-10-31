# Source Model — The catalogue workbook: one row per folder, in the archive's template — Design Spec (#6282)

> Milestone: source-model
> Manual: TBD — a section, "Exporting your catalogue", telling a researcher that the recipe's last step
> writes the catalogue as a workbook (Excel) or sheets (CSV) in their archive's own template, one row per
> digital folder, with the people, places and institutions as lists beside it, that the same recipe can
> write a page-by-page transcript per folder as Word, and how to change the columns in the table view.
>
> Design-led (Testing Constitution). **Status: PROPOSED** (2026-10-28; revised 2026-10-29 after the
> review in the maintainer's working notes, `export-review-2026-10-29`, and again the same day with the
> owner's rulings, decided below). Written for the owner from his idea, paraphrased: a cataloguer's
> workbook must come out of the app by itself, driven by the folders' attributes, in the archive's own
> template, and the same columns must be seen and edited in a table in the app. His real cataloguing
> workbook and the one a worker built by hand on 2026-10-29 were read for their structure only; neither
> is copied into the repo or the app. Builds on `attributes-and-prototypes.md` (THE FOUNDATION: a
> template is a prototype's columns, the kind and value cascades, the shipped EAP prototypes),
> `cataloguing.md` (the fields as folder attributes, `folder.promote_catalogue`, the EDTF date),
> `export/exporter.md` (the one record stream and its Excel and Word emitters), `structured-data.md`
> (the dataset sheet), `../ui/catalogue-table.md` (the table view: the same template, seen and edited),
> `../kg/kg-entities-and-statements.md` (sections B, D and G: one record per name, proposals resolved
> by a person, the folder's lists read from the record) and `models-chains-and-projects.md`
> (`source.onboard.kept-exported`, the export step).

Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built. Each line
names its test.

## Why its own spec

`cataloguing.md` owns the fields and already lists `catalogue.export-standards` [GAP] in one line.
`export/exporter.md` owns the record stream and its emitters (documents, entities, claims as fixed
tables). `attributes-and-prototypes.md` owns what a template IS. Neither says what a cataloguer's
**workbook** is: the template filled from each folder's attributes and facts, with the names beside it
and the provenance behind it, plus the page-by-page transcript the same team hands over as Word. That
is one surface with its own sheets, its own doors and its own date and name rules, so it gets one
spec; `cataloguing.md`'s export line points here, and the record-stream emitters stay where they are.
The table view that shows and edits the same columns is `../ui/catalogue-table.md`.

## Intent (the design)

A person presses Start on a recipe whose last step is "Keep files". When the run ends they open the
folder the step names and find `Catálogo.xlsx`: sheet 1 is the catalogue, one row per digital folder (a
digital folder is one archival document or file), one such sheet per collection in the scope, the
columns of the folders' prototype in its words and order, three header rows (the funder's English, the
team's Spanish, the instruction line per column); beside it the sheets the team is used to:
`Faltantes` (the rows with something missing or unresolved), `Personas`, `Lugares`, `Entidades` (the
people, places and institutions the rows name, one row each, with the graph's canonical name and its
authority fields beside each and the folders that name it), `Tema` (the controlled subject list),
`Catálogo` (every catalogue attribute as it stands, dates as written and as EDTF), `Páginas` (the
page texts), `Nombres` (the project's ONE canonical set of names in the scope), `Declaraciones` (the
statements) and `Notas` (who or what set each cell). The workbook is the team's "Revisada" sheet made
by the engine: it prints the curated state (a person's values, the canonical forms of names) and marks
what is still a machine's proposal; nothing in it is edited by hand, and every value is visible as an
attribute in the app. Beside the workbook, when the recipe asks for it, one Word file per folder
with the transcript page by page. They can hand it all to the archive or the funder as it is, or open
the same columns in the app's table, correct a cell, and export again. Nothing in it was invented at
export: every cell is an attribute of the folder as it stands, a fact of the folder (its name, its
files, its count, its blank pages), or a name the rows carry. A cell with no value is empty, never
guessed. Writing the workbook never runs a model (`never-rerun-a-model-pass`, #6127).

It lives in `fichero-server/src/fichero_server/export_service.py` (the Excel writer gains the
template sheet, more than one header row and the extra sheets; the Word writer gains its four options),
a new fichero-server/src/fichero_server/catalogue_sheet.py (to write: the row builder over a template,
the computed columns, the problems, the shared read the table uses), the shipped EAP prototypes
(`attributes-and-prototypes.md`, "The shipped prototypes"), two kept-export formats
(`fichero-server/src/fichero_server/kept_export.py` `FORMATS`), one route in
`fichero-server/src/fichero_server/api/routes/ingest/export.py`, the Catalogue stage's prompt and
parser (`fichero-server/src/fichero_server/recipes/catalogue_step.py`) and the recipe's export card in
`fichero-server/src/fichero_server/recipes/runner.py`. The app shows the template's columns and edits
the cells (`../ui/catalogue-table.md`); no rule lives in Swift.

## Prior art / best practices (don't invent from scratch)

- **The British Library Endangered Archives Programme (EAP) listing template.** The team's workbook is
  it: a first header row in EAP English (Digital Folder Name, Digital File Name (First), Digital File
  Name (Last), Number of Digital Files, Title (In Original Language/Script), Original Reference, Dates
  of Material (Gregorian Calendar), Related Towns/Cities, Related Subjects), a second row in the team's
  Spanish, a third row of instructions per column. We ship it as the prototype `eap_digital_folder`,
  both label languages and the instruction line, and the export writes all three rows (the team's
  workbook has three; the earlier hand-built sheet had two).
- **ISAD(G) and EAD.** Title, dates, extent, reference code, scope and content, access points. Every
  column of the EAP prototype maps to one ISAD(G) element, so an EAD export later
  (`catalogue.export-standards`) reads the same template.
- **Access points, typed** (ISAAR-CPF for persons and corporate bodies, the Getty TGN for places). An
  archive's access points are typed lists. Fichero's Catalogue stage writes one untyped list
  (`catalogue_access_points`); this spec types it from the project's own knowledge graph (an entity's
  type), deterministically, and sends the untyped rest to Problemas.
- **EDTF (Library of Congress Extended Date/Time Format).** The engine already stores
  `catalogue_date_normalised` as EDTF; the sheet RENDERS it in the archive's format and never
  re-reads the Spanish text at export. How a date written in words becomes EDTF is "Dates done
  properly" below.
- **Excel's own conventions for sheets handed around.** Text cells for everything (a date written
  "17/Marzo/1892" must not become a serial number); frozen header rows; UTF-8 with a byte-order mark
  for CSV so Excel on a Spanish Mac reads accents. The existing writer (`export_excel_xlsx`, hand-rolled
  SpreadsheetML, every cell an inline string) is kept and extended, not replaced by openpyxl.
- **Fichero's own rulings honoured, not restated.** No analysis in a catalogue (`catalogue.no-ai-analysis`);
  a field is the folder's attribute with its source (`workflows/attribute_sources.py`: a person's value
  outranks a machine's, a machine's names its run and model); one audited action per capability; no
  local paths from the app (the workbook comes back as the response or goes to a kept export's folder
  the person granted); deliverables come from the app, never a script beside it (owner 2026-10-29);
  one record per name, every list derived from it (`kg.one.*`).

## Where each column comes from

The team's thirteen headings, kept as given, as the declarations of the shipped prototype
`eap_digital_folder` in this order. "Source" is the column's source (an attribute, or a computed
source from the fixed vocabulary `attributes-and-prototypes.md` names); "empty" says what the cell
holds when there is nothing.

| # | Heading (row 2, Spanish, as given) | EAP heading (row 1) | Source | Empty |
|---|---|---|---|---|
| 1 | Tu nombre | — | `cataloguer`: everyone involved in the row, from `attribute_sources`: each person who set or accepted any field of the row, by account name, then each model that set a field, as "Fichero (<model>)"; persons first, then models, each once, joined "; " ("Ana Pérez; Fichero (Claude Sonnet 4.5)"). | Empty when no field has a source. |
| 2 | Nombre de carpeta digital | Digital Folder Name | `folder.name` | Never empty. |
| 3 | Digital File Name (First) | Digital File Name (First) | `folder.first_file`: the original file stem of the folder's first page in reading order (`metadata.source_filename`, else the page's name). | Empty when the folder has no pages. |
| 4 | Nombre de archivo digital (segundo) | Digital File Name (Last) | `folder.last_file`: the stem of the last page ("segundo" is the team's word for the last file, `_IMG_001` … `_IMG_125`). | Empty; equal to 3 when one page. |
| 5 | Número de archivos digitales en carpeta | Number of Digital Files | `folder.page_count`: pages directly in the folder and its subfolders. | "0". |
| 6 | Título del documento | Title (In Original Language/Script) | `attribute:catalogue_title` | Empty. |
| 7 | Referencia original de archivo físico | Original Reference | `attribute:catalogue_original_reference`, declared `inherits`: in the team's workbook it is one archive-and-fonds string for a whole collection, so it is set once on the collection node and shows on every row until a folder states its own (a cover number, a legajo and folio the stage proposes only when the pages state one). | Empty. |
| 8 | Fecha de inicio del proceso legal | Dates of Material (Gregorian Calendar) | `attribute:catalogue_date_normalised` through the format `d/Mes/aaaa` at the date's precision: the START side of the EDTF interval ("17/Marzo/1892"; "Marzo/1892"; "1892"; in the team's practice a year); `?` and `~` are dropped and the uncertainty goes to Problemas. | Empty when no normalised date; the reason goes to Problemas. |
| 9 | Lugares mencionados (Pueblos, regiones, países, ríos, quebradas, cerros, minas, fincas y otros referentes geográficos) | Related Towns/Cities | `attribute:catalogue_places` (typed from the access points, below), each the place's canonical form, joined "|" (the revised sheet's convention; the join is a declaration setting). | Empty. |
| 10 | Nombres de personas mencionadas | — | `attribute:catalogue_people`, each as "Apellido, Nombre" from the entity's surnames and given names (`name_order: surname-first`, a declaration setting), joined "|". | Empty. |
| 11 | Descripción breve del documento: ¿Sobre qué es? | — | `description`: the folder's content when it is the promoted catalogue description (`catalogue_content_from` set), else the latest `catalogue.narrative` artifact's text. | Empty. |
| 12 | Problemas para resolver | — | `problems`: the person's `attribute:catalogue_problems`, then the computed problems (below), each one clause, "; " between. | Empty. |
| 13 | — | Related Subjects | `attribute:catalogue_subjects` (NEW optional field, a `multi_select` over the prototype's Tema vocabulary only, printed by its English label), joined "|". | Empty. |

Institutions are not a column of the EAP prototype; they are the `Entidades` sheet, from
`attribute:catalogue_institutions`. Columns 7, 12 and 13 are new optional fields of
`catalogue.folder-description-fields` (they join the stage's option list; the stage never invents
them; 12 is a person's field the model never fills).

### Typed access points (decided)

`catalogue_access_points` is one list the Catalogue stage writes. At promote time
(`folder.promote_catalogue`, the re-parse step that already runs with no model) each point is looked
up in the project's knowledge graph by canonical name or alias, exact after NFC and case folding: a
`person` goes to `catalogue_people`, a `location` to `catalogue_places`, an `organization` to
`catalogue_institutions`, and a point no entity matches goes to Problemas ("sin clasificar: Juzgado
del Circuito") and, as `../kg/kg-entities-and-statements.md` section D rules, becomes a PROPOSED name
in the graph (a mention on the folder's description) for the person to resolve; once resolved, the
next promote types it. The three typed lists are ordinary attributes: a person edits them in the
table, the edit is theirs, a later promote never overwrites a person's list (it may still fill an
empty one). No model, no heuristics on the words: the graph types, the person corrects. When the KG
spec's stage 3 lands, the three lists are written by the engine from the record whenever a name's
state or form changes in the folder's scope (`kg.attr.folder-names-are-attributes`); this promote
rule is the same derivation run at promote, not a second source.

### Dates done properly (decided: the catalogue prompt returns EDTF; the parser is the check)

The owner's two ways were: (a) the Catalogue stage's prompt asks the model for each date as EDTF
beside the text, in a new prompt version, with the deterministic parser kept as the check; (b) a
separate, cheap, text-only "Normalise dates" recipe step, never twice on the same input and model,
cost shown first, the parser the free first pass and the check. **This spec chooses (a), and extends
the parser so a date written in words is read with no model at all.**

- **The prompt.** The next version of the catalogue prompt (after `folder_description_v4`; shipped
  versions are never edited in place) asks, for the Dates field, for the date as the records write it
  AND the same date as EDTF (a date, or an interval start/end, `?` for uncertain, `~` for approximate)
  with the words it read it from. The answer lands as `catalogue_dates` (the text) and a machine
  proposal for `catalogue_date_normalised`, its source the run, model and the words cited.
- **The parser is the free first pass and the check.** `_date_normalised` (`catalogue_step.py`,
  `histdate`) runs on the text at write and at every promote, with no model. It GAINS days and months
  written in words ("a los ocho días del mes de mayo de mil novecientos nueve" → `1909-05-08`;
  "primero de enero" → `-01-01`; "a mediados de" → `~`), beside the spoken years it already reads.
- **Agreement and disagreement.** Parser and model agree (same EDTF after `_plain`): the value is
  written, source the run, "checked by the parser". The parser reads nothing and the model gave an
  EDTF: the model's stands, source the run, Problemas says "fecha: leída por el modelo, sin
  comprobar". The parser reads a date and the model gave none: the parser's stands. Both read and
  DISAGREE: the cell stays EMPTY, the model's EDTF is kept as the pending proposal, and Problemas
  carries both ("fecha: el analizador leyó 1909-05-08, el modelo 1909-05-18") for the person to pick
  in the table; nothing is guessed.
- **A person's correction always wins.** Editing the normalised cell in the table makes it the
  person's (`catalogue.table.date-edit-keeps-the-group`); a later promote or run never writes over
  it; Notas records the model's and the parser's readings beside the person's.
- **Folders already described** are not re-run (#6127). Promote re-parses their Dates text with the
  extended parser, so a date in words becomes EDTF with no model; a text the parser still cannot
  read goes to Problemas and the person fixes it once in the table. A person who wants the model's
  reading on those folders runs the Catalogue stage again on purpose, at the cost shown.

*Trade-offs.* (a) costs nothing extra: the model is already reading the folder, and one more line in
its answer is cheaper than a second call per folder; one prompt version, one source per value, no
second step to schedule or explain. Its weakness is that it reaches only folders catalogued after the
version ships, which the extended parser covers for the backlog. (b) would reach every folder at a
small cost per folder and would let a project choose a cheaper model for dates than for description,
but it adds a step, a cost card, a second model opinion on text the first model wrote, and a second
place a date can be written; two models reading one Dates text is the disagreement case built in.
If the extended parser proves not enough on a second archive's wording, (b) can be added later as the
backfill step, with the same agreement rules.

### Computed problems

Read at export and in the table from facts the engine holds, never stored, each one clause:
- pages sorted blank (`material = blank`), as image ranges by file stem: "en blanco: IMG_017–IMG_019, IMG_025";
- pages with no lines on the working pass and not blank: "sin líneas: IMG_031";
- a gap in the image numbering: "faltan IMG_040–IMG_042";
- `lint_flags` on the folder's catalogue data, as written;
- a date the parser and the model read differently, or one only the model read: as "Dates done
  properly" says; a Dates text with no normalised date at all: "fecha sin normalizar: «…»";
- an uncertain or approximate normalised date: "fecha incierta";
- untyped access points: "sin clasificar: Juzgado del Circuito";
- a name in the row's lists that is still only a proposal in the graph: "nombre sin confirmar: …";
- a check rejection on a statement of the folder (`checking/verdicts.py`): "declaración rechazada: …".

## What the team's workbook taught (structure only; decided)

The owner's team's real cataloguing workbook was read for its structure, never its rows; no name,
title or reference from it is in the repo or a spec. Each pattern below is now a rule, and each rule
is template data on the prototype or an attribute on a record, so the engine writes the same workbook
deterministically from what Fichero holds, and the app shows every value as an attribute:

- **One catalogue sheet per collection.** The team keeps one sheet per collection of the same funder
  project. A collection is a node (a project, or a box that is a collection) carrying the prototype;
  the export writes one catalogue sheet per collection node in the scope, named by the collection.
- **Three header rows.** Row 1 the funder's English, row 2 the team's Spanish, row 3 an instruction
  per column (how to write a date, how to separate places, to look in the Personas tab first). The
  instruction is the declaration's `help`, in the team's language.
- **The folder name, first and last file and count** follow one pattern (a project code, the
  collection, the box, a document number and a short title; the files that stem plus `_IMG_nnn`):
  the fact columns, computed, never typed.
- **The original reference is the same string for a whole collection**: set once on the collection
  node, inherited by every row (`inherits`), overridden where a folder differs.
- **The date is in practice a year**: the EDTF start rendered at its precision does that by itself.
- **The revised sheet is the canonical format**: places joined "|", people as "Apellido, Nombre"
  joined "|"; the earlier sheets used "; " or ", " and "Nombre Apellido". The join and the name order
  are declaration settings, and the EAP preset carries the revised ones.
- **Personas** is an authority list: the compound form as used in the catalogue (a control column,
  "do not edit"), given names, surnames, additional information (a relation, an office, a widow of),
  comments, each with its own instruction. **Lugares** likewise: the place as used (control), the
  corrected place, a place type from a fixed list, the place it lies inside, comments. These are
  attributes of the canonical person and place entities (`given_names`, `surnames`, `note`;
  `place_type`, `parent_place`), owned by the one record (`../kg/kg-entities-and-statements.md`,
  `kg.attr.authority-sheet`); the sheets print them, and a person corrects them in the app's name
  lens, not in the sheet. The control column is the form the catalogue rows print, so a later
  re-import of a corrected sheet can match rows (not in the build order).
- **Tema** is a controlled vocabulary of about 130 subject terms with English and Spanish side by
  side: the `options` of `catalogue_subjects` on the prototype, two labels per term.
- **Faltantes** lists folders that are missing or incomplete: a computed sheet of the catalogue rows
  whose Problemas names a gap, missing pages or an unresolved date, plus rows a person marked.
- **Revisada** is the curated state: the workbook prints a person's values where there are any, the
  canonical forms of names, and marks what is still only a machine's proposal; a delivered export can
  leave proposals out (`proposals: marked | omitted`, marked by default).

## The template is the prototype (decided)

A template is a prototype's column set; there is no template setting of its own. Everything about
the shape (declared order, labels per language, join, date format, computed sources, the kind and
value cascades, how a column change copies a built-in) is `attributes-and-prototypes.md`. What this
spec adds:

- The export and the table use the **effective prototype of the rows shown**: a box carrying
  `eap_box` gives every folder beneath it the `eap_digital_folder` columns with no assignment per
  folder; a folder with its own kind shows its own columns; rows of mixed kinds show the union.
  Rows with no effective prototype get "every `catalogue_*` key, alphabetically": today's Excel export.
- Month names and the date format are declaration data on the prototype (`format: d/Mes/aaaa`,
  `months` per language), not code.
- A CSV of headings can be imported as a prototype with every column's source "empty" until the
  person picks one (later; not in the build order).

## The sheets

The catalogue sheets come first, one per collection node in the scope, each named by the collection
and the prototype's label ("<collection> Catalogación básica"), with the three header rows. Then, in
this order, each from the rows of the catalogue sheets or the scope's pages and graph, every cell text:

- **Faltantes**: the catalogue rows (same columns) whose Problemas names a numbering gap, missing
  pages, an unresolved date or an unconfirmed name, or that a person marked incomplete.
- **Personas**, **Lugares**, **Entidades** (decided: from the rows, with the graph beside each): one
  row per distinct value of `catalogue_people`, `catalogue_places`, `catalogue_institutions` across
  the rows, sorted by the value, each with an instruction row under the headings. Personas: the
  compound form as the rows print it (the control column), given names, surnames, additional
  information, whether confirmed or proposed, the folders that name it, Comentarios. Lugares: the
  place as the rows print it (control), the canonical place, the place type (from the fixed list),
  the place it lies inside (the gazetteer's parent where linked, `knowledge/linked_places.py`),
  confirmed or proposed, the folders, Comentarios. Entidades: the institution as printed, the
  canonical form, the folders, Comentarios. The authority fields are the entity's attributes, read
  from the record, never typed into the sheet.
- **Tema**: the prototype's subject vocabulary, one row per term, English and Spanish labels.
- **Catálogo**: one row per folder, every `catalogue_*` attribute as it stands, alphabetically, with
  `catalogue_dates` and `catalogue_date_normalised` side by side.
- **Páginas**: the existing Documents rows (`export_excel_xlsx`'s page rows for the scope) with the
  folder name, the file stem, the page's text.
- **Nombres**: the ONE canonical set ("Names: one canonical set" below): the graph's entities sourced
  in the scope's pages or folder descriptions that are not rejected and not merged away, one row per
  entity: canonical name, the forms as written, type, confirmed or proposed, the folders, who made it
  (a person; "Fichero (<model>)" with the run; "spaCy" for a draft still unresolved). No run-specific
  header note: the maker is a column.
- **Declaraciones**: the statements (`find-statements`) of the scope's pages, as the existing Claims
  sheet, filtered to the scope: subject, verb, object, the page, the excerpt.
- **Notas**: one row per (folder, column key, by: person name or "Fichero (<model>)", step, run id,
  when, what the model said, accepted by). A computed column has no Notas row.

A sheet with no rows is still written with its header, so the workbook always has the same sheets.

## Names: one canonical set (decided; the rules live in the KG spec)

Names in the catalogue's lists and in Nombres may come from spaCy, from the chosen model (Sonnet or
another) or from a person. All three are PROPOSALS until a person resolves them into the project's one
canonical set; the catalogue reads that set. `../kg/kg-entities-and-statements.md` owns the rules and
this spec points at them rather than repeating them:

- a draft from any source is a proposal in the one record (`kg.names.model-step-is-the-source`, the
  draft layer of its step 1.2); a person accepts, merges or rejects it (`kg.resolve.*`); a merge
  proposal is proposed, never automatic unless unmistakable (`kg.resolve.folder-pass`);
- a superseded draft is taken back or absorbed, never kept as parallel data (`kg.one.entity-is-the-record`,
  `kg.one.entities-artifact-retired`): nothing in this workbook reads a draft that a resolution replaced;
- the folder's three lists are derived from the record (`kg.attr.folder-names-are-attributes`) and
  Nombres is read from the same record through the same scope function (`kg.one.catalogue-reads-the-record`).

**spaCy `es_core_news_sm` on this archive: a free seed, never canonical by itself.** The evidence from
B12 (the 2026-10-26 to 29 runs): "Juzgado" typed as a person; month names as entities; fragments of
names split at line ends; 397 places in one folder of court papers. That is the model doing what it
was trained for (modern news Spanish) on 1900s legal Spanish with line-broken words, and no threshold
fixes a type error. Where it fits: as the free first pass whose proposals a model step or a person
resolves, and as the thing that makes the lens non-empty before anyone has paid; in Nombres and in
the three lists only once resolved, and until then marked "propuesto (spaCy)" and never in a
delivered sheet unless the person asks for proposals. Not canonical by itself, not a source for the
exported authority sheets, and not rerun when a model step covers the same pages (the draft is taken
back as the model writes, KG step 1.2). Whether a project may count unrejected proposals in its
working catalogue is the KG spec's question 2; this spec's exports print confirmed names, and
proposals only when asked, marked (`kg.attr.entry-shows-state`).

## The word transcript: a second template on the same record stream (#6287, decided)

The team also hands over the transcript folder by folder as Word. It is the existing Word emitter
(`export_word_docx`, `export.word-and-excel-and-markdown-folder-are-typed-emitters` [OK]) reading the
same record stream the workbook reads, with four options the B12 export of 2026-10-28 showed missing:

- **Images off.** `include_images: false` prints neither the image nor the "[Image not included…]"
  note; the page is its heading and its text. The default stays on for the Reader's Word export and
  off for the kept transcript (26 GB of TIFF in a .docx is nobody's deliverable).
- **A page break per page.** `page_break_per_page: true` puts a page break before each page's heading
  (today: a Heading 2 only).
- **Blank pages listed once per folder.** A page the run sorted blank (`material = blank`) prints no
  body ("No text content available." 545 times was the B12 file); the folder ends with one line,
  "Páginas en blanco: IMG_017–IMG_019, IMG_025", the same ranges as the Problemas clause, from the same
  function.
- **One file per folder in one call.** `per: folder` on the route returns a zip of one .docx per
  folder in the scope (named by the folder), or writes them as files into a named kept export's
  folder; the kept-export format `word-transcript` does the same on the run's last batch and on the
  quiet-period rewrite. One call for a box of twelve folders, not twelve.

Nothing else changes in the emitter: the heading per folder, the reading order, the derived text
(`text_for`) and the skipped-image record stay.

## Formats

- **XLSX**: one workbook; sheet 1 the catalogue with its header rows frozen, every cell text, then the
  sheets above; written in the existing writer, in write-only order (a sheet is streamed as its rows
  are made).
- **CSV**: one file per sheet in a folder (`Catálogo/Catalogación básica.csv`, `Entidades.csv` …),
  UTF-8 with a byte-order mark, comma-separated, every field quoted, CRLF, the header rows as the first
  lines.
- **DOCX** (the transcript): one file per folder, as above.
- One row per folder; a folder with subfolders is one row for itself (its own pages' count and files)
  and one row per subfolder, in sidebar order, so a box is a block of rows.
- Accents and ñ are written as the attribute holds them (NFC, `historical-text-normalization.md`).

## When it runs

- **As the recipe's last step.** The export card (`recipes/runner.py` `_run_export`) gains the formats
  `catalogue-workbook` and `word-transcript` (one file per **folder scope**, not per page), kept as
  kept exports (`kept_export.FORMATS`, `source.onboard.kept-exported`), written after Catalogue on the
  run's last batch, and rewritten by the quiet-period hook when a folder's attributes, description or
  pages' text change. A run with no Catalogue stage still writes the workbook, with the fact columns
  filled and the fields empty.
- **On demand** from a folder or a project: File ▸ Export ▸ Catalogue workbook… and File ▸ Export ▸
  Transcript (Word, per folder)…, the folder's context menu, and the table view's Export button,
  through `POST /api/export/catalogue-workbook` (scope: a folder or project id; format `xlsx` or
  `csv`; the rows' effective prototype unless one is named) and `POST /api/export/word` with the four
  options, returning the file (or zip) as the response, or writing into a kept export's folder when
  one is named. No local path in the request.
- **CLI and MCP** reach the same routes through the generated surface (`fichero export
  catalogue-workbook`, `fichero_export_catalogue_workbook`; the Word route's new options likewise).
- **Never a model.** The builders read attributes, pages, entities, claims and the run's record. A folder
  the Catalogue stage has not described has empty field columns; the Activity line says how many
  ("Catálogo.xlsx: 552 filas, 14 sin describir").
- **Steps are optional where the recipe says so.** The export step reflects whatever ran. Leave-out
  (`recipes-run.md`) is an optional step, off by default, that a person turns on like any other; it
  is never fixed or always on, and the workbook never waits for it (owner, 2026-10-29).

## At 100k pages

A collection of 100,000 pages is some thousands of folders. Folders are read in batches of 500 (one
query for the folders, one for their pages' names, order and `material`, one for the attributes and
sources, one for the entities of the batch's pages, one for the flags and verdicts: five queries per
batch, never one per folder); each batch's rows go to the CSV or the write-only workbook as they are
made. The authority sheets keep only distinct values and folder names across batches. A workbook of
5,000 folders writes in under a minute on the M1; the job runs on the background `database` lane like
every kept export. The Word transcript streams one folder at a time into the zip.

## Behaviors

- `catalogue.export.attr-columns-today` — **[OK]** (#6267, #6270) `POST /api/export/excel`'s Documents
  sheet has folder rows and one `attr:<key>` column per attribute key, alphabetical, with
  `catalogue_date_normalised` among them; a promoted folder's description prints once. This is what
  rows with no effective prototype get and stays as it is. Tests:
  `fichero-server/tests/unit/api/test_routes_export.py::TestExcelExportAttributes`,
  `::TestCatalogueTextOnlyDroppedInExcel::test_excel_has_the_normalised_date_column`.
- `catalogue.export.one-row-per-folder` — **[OK]** (#6282) the catalogue sheet holds one row per
  folder in the scope, in sidebar order, a folder with subfolders first and its subfolders after it;
  the fact columns (name, first file, last file, page count) are filled for every row from the folder
  and its pages alone; file stems come from `metadata.source_filename`, else the page name. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_rows.py.
- `catalogue.export.cells-from-attributes-never-guessed` — **[OK]** (#6282) a field column holds the
  folder's EFFECTIVE value of that key (its own, else inherited where the declaration says so, else the
  prototype's default; a person's value over a machine's); a folder with no value has an empty cell;
  writing the workbook never calls a model or reruns the Catalogue stage (#6127); a run with no
  Catalogue stage writes the fact columns and leaves the fields empty. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_rows.py.
- `catalogue.export.cataloguer-column` — **[GAP]** (#6282) Tu nombre lists everyone involved in the
  row from `attribute_sources`: each person who set or accepted a field, by account name, then each
  model that set a field as "Fichero (<model>)", persons first then models, each once, joined "; ";
  a row no source touched is empty. Test: fichero-server/tests/unit/export/test_catalogue_sheet_rows.py.
- `catalogue.export.access-points-typed-by-the-graph` — **[GAP]** (#6282, #6267) `folder.promote_catalogue`
  types each access point by the project's entities (canonical name or alias, exact after NFC and case
  folding, no model) into `catalogue_people`, `catalogue_places`, `catalogue_institutions`; an unmatched
  point goes to Problemas and is proposed into the graph as a mention on the folder description;
  `catalogue_access_points` is unchanged; a list a person set is never overwritten; the undo puts the
  lists back. Test: fichero-server/tests/unit/recipes/test_catalogue_access_points_typed.py.
- `catalogue.export.people-places-institutions-columns` — **[GAP]** (#6282) Lugares and Nombres read
  `catalogue_places` and `catalogue_people` joined "; " in the attribute's order; institutions never
  appear in either and go to the Entidades sheet. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_rows.py.
- `catalogue.export.dates-in-the-archives-format` — **[OK]** (#6282, #6270) the date column renders the
  start side of `catalogue_date_normalised` through the prototype's format: "17/Marzo/1892" for a day,
  "Marzo/1892" for a month, "1892" for a year, empty when there is none; `?` and `~` are dropped and
  noted in Problemas; the month names come from the declaration, not the code; `catalogue_dates` text is
  never parsed at export. Test: fichero-server/tests/unit/export/test_catalogue_sheet_dates.py.
- `catalogue.export.dates-prompt-returns-edtf` — **[OK]** (#6282, #6270) the next catalogue prompt
  version asks for each Dates value as text AND as EDTF with the words it was read from; the answer
  lands as `catalogue_dates` and a machine proposal for `catalogue_date_normalised` citing the run,
  the model and the words; shipped prompt versions are not edited; described folders are not rerun.
  Test: fichero-server/tests/unit/recipes/test_catalogue_dates_prompt_edtf.py.
- `catalogue.export.dates-parser-reads-words` — **[OK]** (#6282, #6270) the parser reads days and
  months written in Spanish words beside the years it already reads ("a los ocho días del mes de mayo
  de mil novecientos nueve" → 1909-05-08; "primero de enero de mil ochocientos noventa" →
  1890-01-01; "a mediados de mayo de 1910" → 1910-05~), at write and at every promote, with no model.
  Test: fichero-server/tests/unit/recipes/test_catalogue_dates_in_words.py.
- `catalogue.export.dates-parser-checks-the-model` — **[OK]** (#6282) agreement writes the value with
  the run as source and the parser as check; a model-only reading stands and is noted in Problemas; a
  parser-only reading stands; a disagreement leaves the cell empty, keeps the model's EDTF as the
  pending proposal and puts both readings in Problemas; a person's edit of the normalised cell wins
  and is never written over by a promote or a run. Test:
  fichero-server/tests/unit/recipes/test_catalogue_dates_parser_vs_model.py.
- `catalogue.export.problems-column` — **[OK]** (#6282) Problemas para resolver joins the person's
  `catalogue_problems`, then the computed clauses: blank pages as image ranges, pages without lines,
  numbering gaps, `lint_flags`, the date clauses above, an uncertain date, untyped access points, an
  unconfirmed name in the lists, a rejected statement; one function computes them for the export and
  the table; nothing computed is stored. Test: fichero-server/tests/unit/export/test_catalogue_sheet_problems.py.
- `catalogue.export.new-optional-fields` — **[GAP]** (#6087, #6282) the Catalogue stage's option list
  gains Referencia original de archivo físico (`catalogue_original_reference`, declared inheriting and
  set once on the collection), Problemas para resolver (`catalogue_problems`, a person's field the
  model never fills) and Related Subjects (`catalogue_subjects`, a `multi_select` over the prototype's
  Tema vocabulary only; a term outside it is refused in words); a model fills a field only from
  evidence in the records. Test: fichero-server/tests/unit/recipes/test_catalogue_stage_optional_fields.py.
- `catalogue.export.template-is-the-prototype` — **[OK]** (#6282) the export's columns are the
  effective prototype of the rows in the scope (`attributes-and-prototypes.md`): one kind, its columns
  in declared order with its header rows; mixed kinds, the union in first-seen order; no kind, every
  `catalogue_*` key alphabetically; a named prototype on the request overrides; there is no template
  setting on the project and no template route. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_template.py.
- `catalogue.export.eap-preset-reproduces-the-sheet` — **[OK]** (#6282) a box carrying `eap_box`
  writes its folders with the thirteen columns above in that order, row 1 the EAP English, row 2 the
  Spanish as given, both frozen, and a fixture of three folders (one described by a fake model, one
  typed by a person, one undescribed) renders cell for cell as the matrix says, from attributes alone,
  with no model client in the process. Test: fichero-server/tests/unit/export/test_catalogue_sheet_eap_preset.py.
- `catalogue.export.authority-sheets-from-the-rows` — **[OK]** (#6282, #5380) Personas, Lugares and
  Entidades hold one row per distinct value of the typed attributes across the rows, sorted, with the
  control column as the rows print it and the entity's authority fields from the record (given names,
  surnames, additional information for a person; canonical place, place type, parent place for a
  place; canonical form for an institution), confirmed or proposed, the folders that name it, an
  instruction row under the headings and an empty Comentarios; a sheet with no rows still has its
  header. Test: fichero-server/tests/unit/export/test_catalogue_sheet_formats.py.
- `catalogue.export.one-sheet-per-collection-three-header-rows` — **[OK]** (#6282) the export writes
  one catalogue sheet per collection node in the scope, named by the collection, each with the
  prototype's label rows and its instruction row frozen; a scope that is one collection writes one
  sheet. Built for the XLSX and the CSV (`export_catalogue_xlsx`, tested in test_catalogue_sheet_template.py and test_catalogue_sheet_formats.py). Test: fichero-server/tests/unit/export/test_catalogue_sheet_formats.py.
- `catalogue.export.faltantes-and-revisada` — **[OK]** (#6282) Faltantes holds the catalogue rows
  whose Problemas names a gap, missing pages, an unresolved date or an unconfirmed name, or that a
  person marked incomplete; the workbook prints a person's values and canonical name forms and marks a
  machine's proposals, and `proposals: omitted` leaves them out; Tema holds the prototype's subject
  vocabulary with both labels. Test: fichero-server/tests/unit/export/test_catalogue_sheet_formats.py.
- `catalogue.export.list-cells-follow-the-declaration` — **[GAP]** (#6282) a list column is joined by
  the declaration's `join` ("|" in the EAP preset) and people are printed by its `name_order` from the
  entity's surnames and given names ("Apellido, Nombre"); a name with no split surname prints as
  written; the table and the export print the same string. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_rows.py.
- `catalogue.export.names-sheet-is-the-canonical-set` — **[OK]** (#6282, #6283) Nombres holds one row
  per entity of the scope that is not rejected and not merged away, read through the KG spec's scope
  function: canonical name, forms as written, type, confirmed or proposed, folders, maker; a resolved
  draft never appears twice; spaCy-only names appear only as "propuesto (spaCy)" and only when
  proposals are asked for; Declaraciones holds the statements step's claims of the scope; Páginas holds
  the scope's page rows; Catálogo holds every `catalogue_*` attribute. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_formats.py.
- `catalogue.export.notas-sheet-is-the-provenance` — **[OK]** (#6282) Notas holds one row per folder
  and attribute key with by, step, run, when, what the model said and accepted by, from
  `attribute_sources`, the parser's date reading included; a computed column has no row; a person's
  one-field edit appears as theirs. Test: fichero-server/tests/unit/export/test_catalogue_sheet_formats.py.
- `catalogue.export.xlsx-and-csv` — **[OK]** (#6282) XLSX is one workbook (the catalogue first with its
  header rows frozen, then the sheets in the order above, every cell text); CSV is one file per sheet,
  UTF-8 with a byte-order mark, every field quoted, CRLF; both carry accents and ñ unchanged. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_formats.py.
- `catalogue.export.word-transcript-include-images` — **[OK]** (#6287) `POST /api/export/word` takes
  `include_images` (default true, so the Reader's export is unchanged); false prints neither image nor
  "Image not included" note and never resolves or opens the scan files. Test:
  fichero-server/tests/unit/api/test_export_word_include_images_6287.py
  (`test_images_off_has_no_media_and_no_note`, `test_images_off_never_touches_a_missing_scan`,
  `test_request_model_default_includes_images`, `test_default_and_true_embed_images`).
- `catalogue.export.word-transcript-options` — **[OK]** (#6287) `POST /api/export/word` takes
  `include_images` (off prints neither image nor note), `page_break_per_page`, and lists the folder's
  blank pages once at its end as image ranges instead of a body per blank page, using the same range
  function as Problemas; the Reader's export keeps today's defaults. Test:
  fichero-server/tests/unit/api/test_export_word_transcript_options.py.
- `catalogue.export.word-transcript-per-folder` — **[OK]** (#6287) `per: folder` returns a zip of one
  .docx per folder in the scope, or writes them into a named kept export's folder; the kept-export
  format `word-transcript` writes the same on the run's last batch and the quiet-period rewrite; one
  call for a box. Test: fichero-server/tests/unit/export/test_word_transcript_per_folder.py.
- `catalogue.export.recipe-last-step` — **[OK]** (#5485, #6282) the export card accepts the formats
  `catalogue-workbook` and `word-transcript` per folder scope; they are written after Catalogue on the
  run's last batch, kept as kept exports and rewritten by the quiet-period hook when a folder's
  attributes, description or pages' text change. Test:
  fichero-server/tests/unit/recipes/test_recipe_export_catalogue_workbook.py.
- `catalogue.export.on-demand-route` — **[OK]** (#6282) `POST /api/export/catalogue-workbook` takes a
  folder or project id, a format and an optional prototype key, returns the file as the response or
  writes into a named kept export; the CLI and MCP reach it through the generated surface; the route
  runs the same builder as the recipe step. Test:
  fichero-server/tests/unit/api/test_export_catalogue_workbook_route.py.
- `catalogue.export.app-doors` — **[GAP]** (#6282, #507) File ▸ Export ▸ Catalogue workbook…, File ▸
  Export ▸ Transcript (Word, per folder)…, the folder's context menu and the table view's Export button
  call the routes and offer a save panel; no local path is sent. Known gap until built: `POST /api/export/catalogue-workbook` is
  in the endpoint matrix's known gaps, and `POST /api/export/word` with `per: folder` still takes `output_path` from the caller
  and has no Swift (it needs a path-free, base64 sibling like the workbook's). Test:
  fichero/Tests/Unit/general/Views/Library/CatalogueExportCommandTests.swift.
- `catalogue.export.streams-at-scale` — **[GAP]** (#6282) folders are read and written in batches of
  500 with five queries per batch and no per-folder query; a 5,000-folder workbook holds no more than
  one batch of rows in memory at a time; the transcript zip holds one folder at a time. Test:
  fichero-server/tests/unit/export/test_catalogue_sheet_streaming.py (counts queries on a fake
  database of 2,000 folders).

## Build order

Depends on `attributes-and-prototypes.md` steps 1.1 to 1.3 (declarations, the two walks, templates
from prototypes and the shipped EAP prototypes) before stage 1 here.

### Stage 1 — Dates and names done properly, then the sheet
#### Step 1.1 — The parser reads dates in words; the prompt returns EDTF; the parser checks it
- Behaviours: `catalogue.export.dates-parser-reads-words`, `catalogue.export.dates-prompt-returns-edtf`, `catalogue.export.dates-parser-checks-the-model`
- Tests: fichero-server/tests/unit/recipes/test_catalogue_dates_in_words.py, fichero-server/tests/unit/recipes/test_catalogue_dates_prompt_edtf.py, fichero-server/tests/unit/recipes/test_catalogue_dates_parser_vs_model.py
- Size: M
#### Step 1.2 — Typed access points at promote
- Behaviours: `catalogue.export.access-points-typed-by-the-graph`
- Tests: fichero-server/tests/unit/recipes/test_catalogue_access_points_typed.py
- Size: S
#### Step 1.3 — Rows from folders and effective attributes
- Behaviours: `catalogue.export.one-row-per-folder`, `catalogue.export.cells-from-attributes-never-guessed`, `catalogue.export.cataloguer-column`, `catalogue.export.people-places-institutions-columns`, `catalogue.export.dates-in-the-archives-format`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_rows.py, fichero-server/tests/unit/export/test_catalogue_sheet_dates.py
- Depends on: 1.1, 1.2
- Size: M
#### Step 1.4 — List cells by the declaration
- Behaviours: `catalogue.export.list-cells-follow-the-declaration`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_rows.py
- Depends on: 1.3
- Size: S
#### Step 1.5 — The template from the prototype, problems and the EAP sheet end to end
- Behaviours: `catalogue.export.template-is-the-prototype`, `catalogue.export.problems-column`, `catalogue.export.eap-preset-reproduces-the-sheet`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_template.py, fichero-server/tests/unit/export/test_catalogue_sheet_problems.py, fichero-server/tests/unit/export/test_catalogue_sheet_eap_preset.py
- Depends on: 1.4
- Size: M

### Stage 2 — The workbook, the transcript and their doors
#### Step 2.1 — The other sheets and the two formats
- Behaviours: `catalogue.export.authority-sheets-from-the-rows`, `catalogue.export.names-sheet-is-the-canonical-set`, `catalogue.export.notas-sheet-is-the-provenance`, `catalogue.export.xlsx-and-csv`, `catalogue.export.one-sheet-per-collection-three-header-rows`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_formats.py, fichero-server/tests/unit/export/test_catalogue_sheet_formats.py, fichero-server/tests/unit/export/test_catalogue_sheet_formats.py, fichero-server/tests/unit/export/test_catalogue_sheet_formats.py
- Size: M
#### Step 2.2 — Faltantes, Tema and the revised state
- Behaviours: `catalogue.export.faltantes-and-revisada`
- Tests: fichero-server/tests/unit/export/test_catalogue_sheet_formats.py
- Depends on: 2.1
- Size: S
#### Step 2.3 — The Word transcript's options and one file per folder (#6287)
- Behaviours: `catalogue.export.word-transcript-options`, `catalogue.export.word-transcript-per-folder`
- Tests: fichero-server/tests/unit/api/test_export_word_transcript_options.py, fichero-server/tests/unit/export/test_word_transcript_per_folder.py
- Size: S
#### Step 2.4 — The route and the recipe step
- Behaviours: `catalogue.export.on-demand-route`, `catalogue.export.recipe-last-step`, `catalogue.export.streams-at-scale`
- Tests: fichero-server/tests/unit/api/test_export_catalogue_workbook_route.py, fichero-server/tests/unit/recipes/test_recipe_export_catalogue_workbook.py, fichero-server/tests/unit/export/test_catalogue_sheet_streaming.py
- Depends on: 2.2, 2.3
- Size: M
#### Step 2.5 — The new optional fields and the app's doors
- Behaviours: `catalogue.export.new-optional-fields`, `catalogue.export.app-doors`
- Tests: fichero-server/tests/unit/recipes/test_catalogue_stage_optional_fields.py, fichero/Tests/Unit/general/Views/Library/CatalogueExportCommandTests.swift
- Depends on: 2.4
- Size: M

Stage 3 is the table view (`../ui/catalogue-table.md`), which depends on 1.5 here and on
`attributes-and-prototypes.md` step 2.1. The Nombres sheet reads the KG spec's scope function
(`kg.one.catalogue-reads-the-record`); until that lands it reads the entity table with the same
filter, so step 2.1 does not wait on the KG stage 3.

## Test matrix

To be filled at approval. Fixture: a scratch project of three folders under a box of kind `eap_box`
built with `seed_test_library.py` (one described by a fake model with typed access points and a date
in words, one typed by a person including a corrected date, one undescribed with two blank pages),
with the thirteen cells each row should render and the one-folder Word transcript; the team's
workbook is never a fixture.

## Rulings (owner, 2026-10-29; decided; the owner approved this spec the same afternoon. Status flips to APPROVED when the test matrix is filled and the manual section exists, as the guardrails require)

1. **Access points** are typed by the knowledge graph at promote, with no model, into
   `catalogue_people`, `catalogue_places` and `catalogue_institutions`; anything unmatched goes to
   Problemas.
2. **Personas, Lugares and Entidades** are built from the catalogue rows, with the graph's canonical
   name beside each value.
3. **Dates** are done properly: the catalogue prompt returns EDTF beside the text and the parser,
   extended to dates in words, is the free first pass and the check; a disagreement goes to
   Problemas; a person's correction always wins (the choice and its trade-offs above).
4. **Tu nombre** lists everyone involved in the row: persons first, then models as
   "Fichero (<model>)", joined "; ".
5. **Names** are one canonical set: drafts from spaCy, a model or a person are proposals resolved by
   a person; superseded drafts are not kept beside the result; Nombres shows the canonical set;
   spaCy is a seed, never canonical by itself.
6. **Templates come from prototypes** and cascade (`attributes-and-prototypes.md`): no template
   setting, no template route; the EAP preset is the prototype `eap_digital_folder`.
7. **The Word transcript** (#6287) is a second template on the same record stream, with images off,
   a page break per page, blank pages once per folder and one file per folder in one call.
8. **The team's real workbook is the model** (structure only): one sheet per collection, three header
   rows, a collection-wide reference that cascades, "|" joins and surname-first people from the
   revised sheet, person and place authority fields on the canonical entities, a controlled Tema
   list, a Faltantes sheet, and the workbook as the revised state, generated deterministically from
   attributes and never edited by hand.
9. **Leave-out** is an optional step, off by default, turned on like any other; the export step never
   depends on it.

## Open questions for the owner

None open here. Mixed kinds in one scope is decided in `attributes-and-prototypes.md` (ruling 7);
which names count in a working catalogue is the KG spec's question 2.
