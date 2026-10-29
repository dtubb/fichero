# Source Model — Attributes and prototypes: the kind of a node, its fields, and the cascade — Design Spec (#5365, #6282, #5636)

> Milestone: source-model
> Manual: TBD — a section, "Kinds of record and their fields", telling a researcher that a project,
> a box, a folder or a page can be given a kind (a prototype), that the kind decides which fields the
> record has and which columns a table or an export shows, that a folder's kind passes down to what is
> inside it until something below says otherwise, and that every value says who set it.
>
> Design-led (Testing Constitution). **Status: PROPOSED** (2026-10-29). Written for the owner from his
> rulings of 2026-10-29, paraphrased: a template is a prototype's set of columns; a project, a folder,
> a subfolder and a page can each carry a prototype, a folder can change its prototype, and a chain is
> allowed (one prototype for the parent folder, another for its subfolders, another for its pages);
> the table view and the export use the effective prototype of the rows they show; values pass down
> app, library, folder, page, region, line, word, character, with an override at any level; the EAP
> listing preset is a prototype for digital folders. This is the FOUNDATION the catalogue workbook
> (`catalogue-export.md`), the catalogue table (`../ui/catalogue-table.md`), the structured-data sheet
> (`structured-data.md`) and the knowledge graph's folder attributes
> (`../kg/kg-entities-and-statements.md`, section D) build on. It iterates on what exists:
> `models/node_prototypes.py`, `models/prototype_schema.py`, `workflows/attribute_sources.py`, the
> `document.assign_prototype` action and the `classifications` routes.

Tags: [OK] built and pinned · [PARTIAL] exists, partly wired or unpinned · [GAP] not built. Each line
names its test.

## Why its own spec

Three specs each say part of this and none owns it. `structured-data.md` owns the question set (a
prototype's typed fields and the extraction that fills them). `cataloguing.md` lists
`catalogue.fields-on-prototypes` and `catalogue.fields-cascade` in two lines. `finding-documents.md`
owns how a run PROPOSES a kind. `languages-scripts-signs.md` owns one cascade (language, script,
direction) and says its merging rule "is the prototype system's". What nobody says is the whole:
what a prototype is to a node, how a node gets one when nobody assigned it, how a value is found
when the node does not hold it, and how a set of columns follows from all that. That is one
foundation, so it gets one spec, and the three surfaces read it instead of repeating it.

## Words

- **Node**: anything in the tree: the always-there project, a box, a folder, a page, a region, a
  line, a word. All are `Document` rows with a `parent_id`.
- **Prototype**: a kind of node (court case, letter, EAP digital folder, muster entry). It is a
  `ClassificationValue` in the `document_prototype` dimension with a `parent_key` and `attributes`:
  typed declarations (`prototype_schema.py` `AttributeDecl`: type, role, default, options, required,
  the question wording, the label, examples). A prototype's own declarations override its parent
  chain's, root to leaf (`node_prototypes.resolve_prototype_attributes`).
- **Field**: one declared attribute of a prototype, by its stable key. A node of that kind has it,
  filled or empty.
- **Value**: what a node holds for a key, in `Document.attributes`. Its **source** is in
  `metadata.attribute_sources` (a person; or a machine with its tool, step, run, model, what it said
  and what it cited), and a machine's value may be a **proposal** a person accepts or rejects
  (`metadata.proposed_attributes`).
- **Effective prototype** of a node: its own, else the one it inherits (below).
- **Effective value** of a key on a node: its own, else the one it inherits, else the declaration's
  default (below). Every effective value says where it came from.
- **Template**: a prototype's columns: its fields in declared order, with their labels and
  instruction lines, plus the computed columns the prototype declares. The export writes a template;
  the table shows one. One collection (a project, or a box that is a collection) carries one, so
  "one template per collection" is the collection node carrying the prototype.

## Intent (the design)

A person gives a box the kind "EAP digital folder" once. Every folder in the box is now a row with
the thirteen EAP columns, in Spanish with the funder's English above, and the export writes exactly
those. One folder in the box is not a court file but a bundle of letters: they change that folder's
kind to "Letter bundle" and its row shows the letter columns, the rest of the box unchanged. The
pages inside a court file carry the kind "Court page" because the court-file prototype says so,
without anyone assigning it page by page; a page that is a map inside the file is set to "Map" by
hand and keeps it. The archive's reference, set once on the box, appears on every row beneath it,
greyed, marked "from Caja 12", until a folder states its own. In the Inspector every value says
"set here", "from <ancestor>", "default of <prototype>", "Fichero (<model>)" or a person's name, and
a person's value is never written over by a run. Nothing here calls a model.

It lives in the engine: `models/node_prototypes.py` (the inheritance walk, gaining the node-level
walk), `models/prototype_schema.py` (the declarations, gaining order, the per-language labels, the
computed sources and the two "for the nodes beneath" declarations), `workflows/attribute_sources.py`
(sources and proposals, unchanged in shape), `api/routes/document/documents.py`
(`effective-attributes`, gaining the walk and the origin per value; `document.assign_prototype`),
`api/routes/document/classifications.py` (the prototype routes and the audited
`classification.create` / `.patch` / `.delete`), and shipped prototypes under
`fichero-server/src/fichero_server/resources/`. The app's prototype editor
(`fichero/fichero/Views/Prototypes/PrototypeEditorSheet.swift`) and Inspector show what the engine
resolves. No rule lives in Swift.

## Prior art / best practices (don't invent from scratch)

- **Tinderbox prototypes.** A note's attributes come from its prototype; a prototype can have a
  prototype; a container's `OnAdd` and its prototype decide what a new child looks like; an
  inherited value shows greyed until the note sets its own. Fichero's prototypes already follow the
  first two (`node_prototypes.py`); this spec adds the third and the fourth.
- **CSS and the languages cascade.** The nearest ancestor's value wins, a node overrides for itself
  and what is beneath it, and the resolver says which rule fired. `languages-scripts-signs.md`
  ratified this walk (app, project, folder, document, page, region, line, word, character) and named
  its merging rule as the prototype system's; one resolver answers for both.
- **ISAD(G) multi-level description.** Information is given at the highest level it applies to and
  not repeated below (the rule of non-repetition); a lower level inherits what the level above
  states. The value cascade is exactly that rule made mechanical.
- **Fichero's own rulings honoured, not restated.** Logic in the engine; a run proposes a kind, a
  person assigns it (ruled 2026-10-08, `finddocs.*`); a person's value outranks a machine's
  (`attribute_sources`); one audited action per capability; iterate on `node_prototypes.py`, never a
  second prototype system.

## What exists today (verified 2026-10-29)

- A prototype is a `ClassificationValue` (`models/knowledge.py`), dimension `document_prototype`,
  with `parent_key` and typed `attributes`, created, patched and deleted through the audited
  classification actions and validated at save (`_validate_prototype_schema`). Built-ins are
  read-only. **[OK]**
- `resolve_prototype_attributes` merges a prototype's parent chain root to leaf and raises on an
  unknown key or a cycle. `GET /api/classifications/resolved/{key}` returns the declarations and
  defaults. **[OK]**
- A node has one `prototype_key`, set by `document.assign_prototype` (PUT
  `/api/documents/{id}/prototype`; null clears it), which also stamps the source of the key
  `prototype` in `attribute_sources`. A run proposes a kind through `attribute_sources.propose_prototype`;
  accept and reject are audited actions. **[OK]** (#1377, #5600)
- `GET /api/documents/{id}/effective-attributes` returns the prototype's declarations and the
  defaults overlaid with the node's OWN attributes. It does not walk the ancestors and does not say
  where a value came from. **[PARTIAL]**
- Declarations have no order (a dict), one label, no language, no computed source and nothing about
  the nodes beneath. The dataset sheet shows a folder's children by the children's prototype
  (`defaults_by_prototype`), columns per window. **[PARTIAL]**
- `attribute_sources` records who set each value and holds proposals; a run never writes over a
  person's value or an unclaimed one (`machine_may_set`). **[OK]**

## The design

### 1. Where a node's prototype comes from

A node's effective prototype is found in this order, and the answer says which rule gave it:

1. **Its own** `prototype_key` ("set here", with its source: a person, or an accepted proposal
   naming the run).
2. **Inherited by level.** A prototype may declare what the nodes beneath a node of its kind are
   by default: `subfolders: <prototype key>` and `pages: <prototype key>` (and, for a page's kind,
   `regions`, `lines` as the same mechanism; `structured-data.md`'s `entries` is the page-level case
   of this and keeps its name). Walking up from the node, the first ancestor whose effective
   prototype declares a default for the node's level gives it ("from <ancestor>'s kind"). A folder
   inside a folder is a subfolder; a page anywhere beneath is a page; so a box with kind "EAP box"
   whose prototype says `subfolders: eap_digital_folder` makes every folder beneath it an EAP digital
   folder, at any depth, until a folder of its own kind says otherwise for what is beneath it.
3. **None.** Today's behaviour: no declarations, the node's own attributes only.

A node that sets its own prototype breaks the chain for itself AND restarts it for what is beneath
it: the folder set to "Letter bundle" gives its pages what the letter-bundle prototype says, not what
the box says. Clearing a node's own prototype (null) makes it inherit again. The project (the
always-there root) is a node like any other and may carry a prototype; the app level is the shipped
defaults and nothing else.

### 2. Where a value comes from

The effective value of a key on a node is found in this order, and the Inspector, the table and the
export each say which rule gave it:

1. **Set here**: the node's own `attributes[key]`, with its source (a person's name; "Fichero
   (<model>)" for a machine's; "proposed" when it is a proposal nobody answered).
2. **Inherited**: when the declaration is marked `inherits: true`, the nearest ancestor's effective
   value for that key ("from Caja 12"). Only declared-inheriting keys walk up: a title, a date, a
   page count and the people named never inherit; an archive reference, a language, a cataloguer,
   a rights statement and a `Tema` do. The declaration decides, not the reader.
3. **Default of the prototype**: the declaration's `default` ("default of EAP digital folder").
4. **Empty**.

Setting a value on a node is the existing `document.update` (audited, undoable, person-stamped). An
inherited or default value is never copied down into the node's attributes: it is resolved on read,
so a change above shows below at once and a person's override is the only thing stored. A list
value (people, places) does not merge with the ancestor's; it overrides or inherits whole.

The language, script and direction cascade of `languages-scripts-signs.md` is this walk with those
three keys; `llm/language_policy.py` is the resolver both call (`source.resolve.one-cascade`).

### 3. A template is a prototype's columns

- A **column** is one of the prototype's fields (an `attribute:<key>` column: its label per language,
  its type, its join string for a list, its date format) or a **computed column** the prototype
  declares with a `source` from a fixed vocabulary and no stored value: `folder.name`,
  `folder.first_file`, `folder.last_file`, `folder.page_count`, `folder.path`, `description`,
  `problems`, `cataloguer`. The vocabulary and what each produces are defined once, in
  `catalogue-export.md` ("Where each column comes from"); a computed column is read-only everywhere.
- **Order** is the declaration's `order` (an integer; declarations without one follow in key order
  after those with one). A template's columns are the effective declarations in that order.
- **Labels, instructions and vocabularies per language.** A declaration's `label` becomes
  `labels: {<language>: <text>}` with the old single label kept as the project's metadata language
  (`catalogue.folder-description-fields`); it gains `help: {<language>: <text>}`, the instruction a
  cataloguer reads under the heading, and a `select` or `multi_select` declaration's `options` gain a
  label per language too (a controlled list such as the team's Tema terms, English beside Spanish,
  is one vocabulary with two labels, stored once on the prototype). A header row of a table or an
  export is one language's labels; an instruction row is the `help` texts; the EAP preset carries two
  label languages and the instruction row, and the export writes all three rows. A label is never
  the key. A list declaration also carries `join` (the string between values, "; " or "|") and, for
  people, `name_order` (as written, or surname first "Apellido, Nombre"), so a sheet's conventions
  are template data.
- **A scope's template.** The table and the export show rows (folders, or a prototype's units) from
  a scope. The template is the effective prototype of the rows: when every row has the same
  effective prototype, its columns; when they differ, by default the UNION: the columns of each
  prototype in order of the first row that has it, each row filling the columns its own prototype
  has and leaving the rest empty, with the prototype's name as a group heading in the table. A person
  may narrow that for a scope (a per-scope column choice: which columns, or which kind's columns, are
  shown and exported; saved with the scope like a saved view, never a change to any prototype). The
  design aim is that mixed scopes are rare: kinds that share columns do so through a common parent
  prototype (a letter and a court file are both children of `eap_digital_folder`, adding fields, not
  replacing them), so the union is the parent's columns plus a few, and the shipped prototypes are
  built that way. "Todos los atributos" (every `catalogue_*` key seen, alphabetically) is what rows
  with NO effective prototype get, and stays today's export.
- **Changing columns changes the prototype.** Hiding, renaming, reordering or adding a column in the
  table's column menu is the audited `classification.patch` on the rows' effective prototype. A
  built-in prototype is read-only: the first change makes a project-owned prototype whose
  `parent_key` is the built-in, assigns it where the built-in was (the node that carried it, which
  may be the project), and the change lands on the child. The built-in is never edited in place; the
  child inherits every later fix to the built-in it did not override. ⌘Z undoes the patch.

### 4. The shipped prototypes

Shipped as JSON under a new folder, fichero-server/src/fichero_server/resources/prototypes (to write), loaded as built-in
`ClassificationValue`s on open, read-only, migrated forward by key when a shipped file changes:

- **`eap_box`**: a box or project of EAP digital folders: no fields of its own but
  `subfolders: eap_digital_folder`; the archive reference and the cataloguer name declared
  inheriting, so set once on the box they appear on every row.
- **`eap_digital_folder`** ("EAP / Catalogación básica"): the thirteen columns of
  `catalogue-export.md`, in that order, both labels and the instruction line per column, the date
  format `d/Mes/aaaa` at the date's precision with Spanish month names in the declaration, places and
  people joined "|", people surname first, subjects a `multi_select` over the shipped Tema vocabulary
  (about 130 terms, English and Spanish labels), the original reference and the cataloguer declared
  inheriting. A folder's pages: `pages: eap_page` (no fields; the page's own attributes). This is the
  preset the owner named, and it reproduces the revised sheet of the team's workbook from attributes
  alone (`catalogue-export.md`, "What the team's workbook taught").
- **`eap_digital_folder_en`** ("EAP (English only)"): parent `eap_digital_folder`, one label
  language, the funder's nine columns only.
- The existing built-ins (`finding-documents.md`'s kinds: Sentencia, Carta, Telegrama …) stay and
  gain nothing but `order` on their fields.

A recipe may carry prototypes (`catalogue.recipes-ship-prototypes`, `structured.schema.recipes-ship-sets`)
and the onboarding of a project may assign one to the project node; neither is in this build order.

### 5. What a run may do

Unchanged from `attribute_sources`: a run writes a value only into an empty key nobody set or a key
a machine set; it proposes a kind and never assigns one; a person's value or kind is never written
over, and an accepted proposal is the person's. A run reads the effective prototype of the node it
works on (so the Catalogue stage's optional fields are the folder's effective declarations, and a
table extraction asks the questions of the unit's effective prototype), never only the node's own key.

## Behaviors

- `proto.kind.own-and-inherited-by-level` — **[GAP]** (#5365, #6282) a node's effective prototype is
  its own `prototype_key`, else the first ancestor's effective prototype that declares a default for
  the node's level (`subfolders`, `pages`, `regions`, `lines`, `entries`), else none; a node's own
  kind restarts the chain beneath it; clearing it inherits again; the resolver returns the rule that
  fired and the ancestor. Test: fichero-server/tests/unit/models/test_prototype_cascade_kind.py.
- `proto.kind.declared-defaults-for-beneath` — **[OK]** (#5365) a prototype's attributes may declare
  `subfolders`, `pages`, `regions`, `lines` as prototype keys; an unknown key or a cycle through them
  is refused at save with words; `entries` keeps its meaning. Test:
  fichero-server/tests/unit/models/test_prototype_schema.py.
- `proto.kind.assign-and-propose-unchanged` — **[OK]** (#1377, #5600) `document.assign_prototype` sets
  or clears a node's own kind and stamps its source; a run proposes a kind and a person accepts or
  rejects it; a person's kind is never proposed over. Tests:
  `fichero-server/tests/unit/api/test_routes_documents.py::TestDocumentPrototypes`,
  `fichero-server/tests/unit/api/test_mutation_audit_lock.py`.
- `proto.value.set-inherited-default-empty` — **[GAP]** (#5365, `catalogue.fields-cascade`) the
  effective value of a key is the node's own, else the nearest ancestor's effective value when the
  declaration says `inherits`, else the declaration's default, else empty; `effective-attributes`
  returns per key `{value, origin: here|inherited|default|empty, from: <node id or prototype key>,
  source}`; a non-inheriting key never walks up; nothing inherited is stored on the node. Test:
  fichero-server/tests/unit/api/test_effective_attributes_cascade.py.
- `proto.value.one-resolver-with-language` — **[GAP]** (#5517, `source.resolve.one-cascade`) the
  language, script and direction cascade and the attribute value cascade are one walk in one
  resolver; a value set on a folder resolves for its pages through the same call the language does.
  Test: fichero-server/tests/unit/llm/test_language_cascade_levels.py.
- `proto.value.sources-unchanged` — **[OK]** (#5600) a run writes only an empty or machine-set key,
  a person's edit through `document.update` makes the key theirs, a machine value names its tool,
  step, run, model and what it said; a proposal is answered as one audited action. Tests:
  `fichero-server/tests/unit/workflows/test_attributes_cite.py` (and the `structured.cite.*` tests).
- `proto.template.columns-are-the-prototype` — **[GAP]** (#6282) a template is the effective
  declarations of a prototype in `order`, each an attribute column (labels per language, type, join,
  date format) or a computed column with a `source` from the fixed vocabulary; the template of a
  scope is the effective prototype of its rows, the union in first-seen order when they differ (a
  column a child prototype inherits from a shared parent appears once), and "every catalogue key,
  alphabetically" when they have none. Test: fichero-server/tests/unit/models/test_prototype_template.py.
- `proto.template.per-scope-column-choice` — **[GAP]** (#6282) a person may narrow a scope's columns
  (hide columns, or show one kind's columns only); the choice is saved with the scope as a view, not
  on any prototype, the export of that scope follows it, clearing it returns to the union, and ⌘Z
  undoes it. Test: fichero-server/tests/unit/api/test_scope_column_choice.py.
- `proto.template.labels-per-language-and-order` — **[OK]** (#6282) a declaration carries
  `order`, `labels: {language: text}`, `help: {language: text}`, `join`, `name_order`, `format`,
  `inherits`, per-language labels on `options` and, for a computed column, `source`; the old single
  `label` reads as the metadata language's; a label is never shown as the key when one exists. Test:
  fichero-server/tests/unit/models/test_prototype_schema.py.
- `proto.template.edit-copies-a-builtin` — **[GAP]** (#6282) a column change on a built-in prototype
  makes a project-owned child with `parent_key` the built-in, assigns it where the built-in was and
  lands the change on the child; the built-in is unchanged; later changes patch the child; ⌘Z
  undoes the patch and, the first time, the copy and the assignment together. Test:
  fichero-server/tests/unit/api/test_prototype_edit_copies_builtin.py.
- `proto.shipped.eap-prototypes` — **[GAP]** (#6282) `eap_box`, `eap_digital_folder` and
  `eap_digital_folder_en` ship as JSON, load as read-only built-ins on open, migrate forward by key,
  and `eap_digital_folder`'s declarations are the thirteen columns of `catalogue-export.md` in that
  order with both labels, the instruction lines, the "|" joins, surname-first people, the Tema
  vocabulary, the date format and the month names. Test:
  fichero-server/tests/unit/models/test_shipped_prototypes.py.
- `proto.runs.read-the-effective-prototype` — **[GAP]** (#6087, #5636) the Catalogue stage's optional
  fields and the table extraction's questions come from the node's EFFECTIVE prototype, not its own
  key alone, so a folder beneath an `eap_box` is asked the EAP fields with no assignment of its own.
  Test: fichero-server/tests/unit/recipes/test_catalogue_stage_reads_effective_prototype.py.
- `proto.app.inspector-says-where-from` — **[GAP]** (#5365) the Inspector shows each field's value
  with its origin in words ("set here", "from Caja 12", "default of EAP digital folder", "Fichero
  (<model>)", a person's name), greys an inherited or default value, and lets a person set the node's
  own kind or clear it. Test: fichero/Tests/Unit/general/Views/Inspector/EffectiveAttributesOriginTests.swift.

## Build order

### Stage 1 — The two walks in the engine
#### Step 1.1 — Declarations gain order, labels, inherits, source and the levels beneath
- Behaviours: `proto.template.labels-per-language-and-order`, `proto.kind.declared-defaults-for-beneath`
- Tests: fichero-server/tests/unit/models/test_prototype_schema.py
- Size: S
#### Step 1.2 — The kind walk and the value walk
- Behaviours: `proto.kind.own-and-inherited-by-level`, `proto.value.set-inherited-default-empty`, `proto.value.one-resolver-with-language`
- Tests: fichero-server/tests/unit/models/test_prototype_cascade_kind.py, fichero-server/tests/unit/api/test_effective_attributes_cascade.py, fichero-server/tests/unit/llm/test_language_cascade_levels.py
- Depends on: 1.1
- Size: M
#### Step 1.3 — Templates from prototypes and the shipped EAP prototypes
- Behaviours: `proto.template.columns-are-the-prototype`, `proto.template.per-scope-column-choice`, `proto.shipped.eap-prototypes`
- Tests: fichero-server/tests/unit/models/test_prototype_template.py, fichero-server/tests/unit/api/test_scope_column_choice.py, fichero-server/tests/unit/models/test_shipped_prototypes.py
- Depends on: 1.2
- Size: M

### Stage 2 — Editing and the surfaces that read it
#### Step 2.1 — A column change copies a built-in; runs read the effective prototype
- Behaviours: `proto.template.edit-copies-a-builtin`, `proto.runs.read-the-effective-prototype`
- Tests: fichero-server/tests/unit/api/test_prototype_edit_copies_builtin.py, fichero-server/tests/unit/recipes/test_catalogue_stage_reads_effective_prototype.py
- Depends on: 1.3
- Size: M
#### Step 2.2 — The Inspector says where each value came from
- Behaviours: `proto.app.inspector-says-where-from`
- Tests: fichero/Tests/Unit/general/Views/Inspector/EffectiveAttributesOriginTests.swift
- Depends on: 2.1
- Size: S

`catalogue-export.md` stage 1 depends on steps 1.1 to 1.3 here; `../ui/catalogue-table.md` on 2.1.

## Test matrix

To be filled at approval. Fixture: a scratch project (`seed_test_library.py`) with a box of kind
`eap_box` holding three folders (one with no kind of its own, one set to a second prototype, one
whose pages include a page with its own kind), the archive reference set on the box, one folder
overriding it; the effective prototype and the origin of every value asserted per node.

## Rulings (owner, 2026-10-29; decided)

1. A template is a prototype's column set, never a setting of its own.
2. A project, a parent folder, a subfolder and a page can each carry a prototype; a folder can change
   its prototype; a chain of prototypes for the folder, its subfolders and its pages is allowed.
3. The table view and the export use the effective prototype of the rows shown.
4. Values pass down app, library, folder, page, region, line, word, character, with an override at
   any level; the languages cascade and this one are one resolver.
5. The EAP listing preset is a prototype for digital folders.
6. (Later the same day) The team's real workbook is the model, read for structure only: one catalogue
   sheet per collection, three header rows (the funder's English, the team's Spanish, an instruction
   line), a collection-wide original reference that cascades, places and people joined "|" with
   people surname first in the revised sheet, person and place authority records with their own
   columns, and a controlled Tema list. Each is template data on the prototype or an attribute on
   the record, never a hand edit.
7. (Afternoon) Mixed kinds in one scope show the union of their columns by default, and a person can
   narrow it with a per-scope column choice. The design aim is that kinds share columns through good
   default prototypes (a common parent), so the union is rarely more than the parent's columns.

## Open questions for the owner

None open.
