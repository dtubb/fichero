# Source Model — Cataloguing and metadata: fields on prototypes, entries that show — Design Spec (#5365)

> Milestone: source-model
> Manual: TBD — a section, "Cataloguing", explaining how a project's kinds of document (a letter, a
> sale record, a diary entry) carry their fields, how values are proposed from the page and
> confirmed, how a catalogue entry is made from them, and how it is exported to standard schemas.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-10-03). Item 2 and 3 of
> `../SPEC-PLAN.md`. Builds on the prototypes that already exist (`models/node_prototypes.py`,
> #2591), the job registry (`describe-for-the-catalogue`, `extract-to-a-table` in
> `models-chains-and-projects.md`), and the cascade (`languages-scripts-signs.md`).

## Intent

A catalogue entry tells a reader what an item **is**: what kind of document, who, when, where,
how long, in what condition, and where it is held. Today Fichero's catalogue entry is a narrative a
language model writes (200 to 450 words for a long file, `resources/prompts/catalogue/narrative_v2.md`)
followed by tables. It is too long, and it analyses. The maintainer's ruling (2026-10-03): **show,
not tell; no AI analysis.**

So a catalogue entry is made from **facts**: the item's metadata fields and the claims that cite
it, each confirmed by a person or marked as proposed. Its prose is a fixed rendering of those facts
(template realisation, the deterministic half of the NLG pipeline), not a model's summary. A
language model may **propose a field's value from the page**, for a person to confirm; it never
writes the entry.

## Prior art

- **Archival description standards:** ISAD(G) (title, dates, level, extent, creator, scope and
  content, conditions of access), its XML form EAD, and Dublin Core for simple items. Fichero maps
  to them; it does not invent its own vocabulary where one fits.
- **Tinderbox prototypes** (the model Fichero's prototypes follow): a note inherits attributes and
  their defaults from its prototype; a change to the prototype reaches every note that inherits.
- **Reiter and Dale's NLG pipeline:** content selection, then document planning, then realisation.
  The selection here is the item's confirmed facts; realisation is a template per kind of document.
  No step chooses what to say beyond the facts.

## What exists today

- **Prototypes with inheritable attributes** (`models/node_prototypes.py`): a prototype names a
  class with `attributes`, merged parent to child; unknown keys and cycles raise.
- **The catalogue workflow tool** (`workflows/tools/catalogue.py`, 1,633 lines): groups documents by
  case, asks a model for a nine-section JSON (summary, keywords, tables of people, places, dates
  and so on) built partly from extracted claims (`_build_data_from_claims`), and renders it as
  Markdown. Its prompt asks for evidentiary verbs and forbids interpretation, but the entry is
  still a model's prose.
- **Document metadata** is a free dictionary per document; there are no declared fields, types or
  vocabularies.

## The design

**Fields live on prototypes.** A prototype (for example `letter`, `sale-record`, `diary-entry`,
`map`) declares its fields: name, type (text, date or date range, number, person, place,
controlled term, extent, condition), a controlled vocabulary where one applies, whether it is
required, and its mapping to ISAD(G) and Dublin Core. A document with that prototype has those
fields; it inherits defaults from the prototype and from the folder above it, by the same cascade
as language. A recipe or profile can ship its prototypes (the flagship ships `letter`,
`notarial-record` and `administrative-record`).

**Values are proposed, then confirmed.** Each value records where it came from: typed by a person,
taken from a confirmed claim, imported from a file, or **proposed** by the
`describe-for-the-catalogue` job (a model reading the page). A proposed value shows as proposed
until a person accepts or changes it, and is never exported as confirmed.

**An entry shows; it does not tell.** A catalogue entry is rendered from the fields alone, by a
template per prototype:

> **Letter**, 12 March 1789, from Juan de Arriaga (Popayán) to Pedro Mosquera (Cartagena).
> 2 leaves. Spanish. Damaged at the lower margin. Names: 6 people, 3 places.

Every phrase is a field. Nothing is interpreted, summarised or characterised. An empty field is
left out, not filled. A proposed value is marked as proposed in the entry. Long files get the same
entry with their extent; their contents are reached through the item, not described in prose.

**A "contents" field, if a project wants one,** holds a short list of what the item contains, built
from confirmed claims (the parties and object of a sale; the dated entries of a diary), each item
linking to the text it came from. A model may propose it; a person confirms it.

**Export.** Entries and fields export to ISAD(G) as EAD, to Dublin Core, to CSV and Excel (one
row per item, one column per field), and into IIIF manifests' `metadata`.

## Behaviors

- `catalogue.fields-on-prototypes` — **[GAP]** (#5365) a prototype declares its fields with type,
  vocabulary, whether required, and standard mappings; a document with that prototype has them.
- `catalogue.fields-cascade` — **[GAP]** (#5365) a field's default comes from the prototype and the
  folders above, and the value shown says where it came from.
- `catalogue.values-proposed-then-confirmed` — **[GAP]** (#5365) a value records its origin (typed,
  claim, import, proposed); a proposed value is shown as proposed until a person confirms it and is
  never exported as confirmed.
- `catalogue.entry-shows-not-tells` — **[GAP]** (#5365) a catalogue entry is rendered from the fields
  by a template per prototype; every phrase is a field; empty fields are left out; no model writes
  the entry.
- `catalogue.no-ai-analysis` — **[GAP]** (#5365) no catalogue surface shows a model's summary,
  interpretation or characterisation of an item; the existing narrative prompt is retired. Until then, model-written entries follow `catalogue.model-entry-is-concise` (#5968).
- `catalogue.model-entry-is-concise` — **[PARTIAL]** (#5968; owner ruling 2026-10-20; until `catalogue.entry-shows-not-tells` replaces model-written entries) every catalogue, summary or folder entry a model writes is a concise statement of what the item contains, in the records' own vocabulary, with no interpretation: an entry for a long file or a folder aims at 150-200 words and is NEVER longer than 200 (owner, restated 2026-10-20): the cap is stated in every such prompt and enforced by the checker and the lint; only a short formulaic record may be shorter, and no entry is padded; a folder entry says what the folder holds (document types and counts), its date span, the principal parties and places as the records name them, and its language(s). The crucial rule is NO ANALYSIS. It never says what a record suggests, reveals or means, its significance, themes or mood, or a purpose the record does not state; words like "suggests", "likely", "appears to", "reveals", "highlights", "sheds light", "provides insight", "important" and "notably" are banned; what a record says is quoted or attributed ("states that …"); names, dates and sums are verbatim and [ilegible]/[uncertain] markers stay. Each prompt that writes such text gets a new version (never a shipped version edited in pla ENFORCED AT WRITE TIME, not only asked for: each produced entry (the catalogue narrative, folder and collection summaries) is checked before it is stored; a finding is sent back to the model once with the finding in the prompt; an entry still over 200 words is cut at the last sentence that ends within 200; a banned word that remains is stored FLAGGED (`lint_flags` on the catalogue data or the folder's metadata, and a warning in the log), never silently. A banned word inside a quotation is the record's own and is not a finding only when the quotation is verbatim in the source text; the model's own framing in quote marks is still flagged (where no source text is at hand, every quotation is taken as the record's: not built). Built (unrun): the live catalogue narrative used inline "150-300 word" prompts and now uses the registered `narrative_v3`; `narrative_v3` and `folder_v1` state the cap and the ban (folder and collection summaries use `folder_v1`, so `style`/`include_themes`/`include_statistics` no longer shape them; removing those config keys needs an OpenAPI regen, held); `llm/catalogue_lint.py` FAILS over 200 words, a banned word or a repeated sentence, and only WARNS under 150 for a long item. Tests (unrun, M4): `fichero-server/tests/unit/llm/test_catalogue_lint_5968.py` (pure checker, the prompts state the cap, and a lint over `golden_catalogue/`, today four SYNTHETIC hand-written recordings, which prove the lint and nothing about a model) and the write-time order with a fake model. Not done: the live comparison on 5 folders (the M4 run writes outputs; `scripts/lint_catalogue_outputs.py <dir>` lints them).
- `catalogue.folder-description-fields` — **[PARTIAL]** (#6087, #6169; owner ruling 2026-10-26, which REVERSES the 2026-10-24 ruling: a person who read the labelled-field version preferred the old plain description, because 'creator and hands' made an accused person a 'creator' and the book/film field list does not fit a court case) the Catalogue stage of a started recipe writes, LAST and at folder level, ONE archival DESCRIPTION per folder: a single prose paragraph of 150-200 words, never longer than 200 (`catalogue.model-entry-is-concise` stands in full: records' own vocabulary, no analysis, banned words, enforced at write time with the same retry, cut and flag), giving the key names and events as the records name them (who, what, where, when, and the outcome if the folder states one). It writes NO labelled fields by default (no Title, Dates, Extent, Creator and hands, Arrangement, Condition or Access points). The fields are OPTIONS, not defaults, offered in this fixed order (owner 2026-10-26; the labels are the person's own list and are shown as written, in Spanish): Tu nombre; Nombre de carpeta digital; Digital File Name (First); Nombre de archivo digital (segundo); Número de archivos digitales en carpeta; Título del documento; Referencia original de archivo físico; Fecha de inicio del proceso legal; Lugares mencionados (pueblos, regiones, países, ríos, quebradas, cerros, minas, fincas y otros referentes geográficos); Nombres de personas mencionadas; Descripción breve del documento: ¿sobre qué es?; Problemas para resolver. Every field the person turns on is saved as an ATTRIBUTE of the folder (one attribute per field, under the label as written), so a folder's fields are its attributes and can be viewed, filtered and sorted as a TABLE with a row per folder and a column per field, in the order above (owner 2026-10-26). A value the model fills is attributed to "Fichero (<model>)", the model as the person's setup names it (for example "Fichero (Google Gemini 3.1 Fast)"); that is the "Tu nombre" of a generated value, and a value a person types carries their own name (owner 2026-10-26). The person may choose which to include (or fill them by a prototype on the folder, `catalogue.fields-on-prototypes`), saved as the folder's attributes, and any field the model fills is told never to invent (a field with no evidence in the records stays empty). The field labels are shown in the project's METADATA LANGUAGE (owner 2026-10-26): the language of the records chosen at onboarding, or a separate metadata language the person picks there (onboarding offers the choice and defaults to the project's primary language); the twelve Spanish labels above are the Spanish set, other languages get translated labels, any label can be edited, and the field attribute keeps one stable key whatever the label says. It is written in the records' own language (the Catalogue workflow's "auto": the project's primary language, else detected from the folder's text). It uses a NEW prompt version (`folder_description_v4`; shipped versions are never edited in place), and folders already described are NOT re-run (`never-rerun-a-model-pass`): a person's own reading is never retracted. The description is stored as a `catalogue.narrative` artifact on the folder and as its `description` reading (`recipes/catalogue_step.py`). Test: `tests/unit/recipes/test_catalogue_stage_6087.py` (pins the paragraph form, the 200-word cap, no fields by default, the optional fields never invented). Not done: the live run on real pages (e2e), the person's field-choice control (the twelve options above, in that order) and the folder-attributes table view.
- `source.recipe.catalogue-follows-new-material` — **[PARTIAL]** (#6087) `describe-for-the-catalogue` is a Start job that needs a text model, and the one Start runs it after every other stage (once, on the run's last batch, over every page the run covered). A folder is described from its pages' readings and its subfolders' descriptions, deepest first. A folder whose covered pages and readings are unchanged since its saved description is left alone, so pages added later (a new folder, or pages in an existing one) redo the new folder and the folders above it that cover them, and no other. Cost: a folder is described again whenever anything under it changed, so a big import into a deep tree redoes each covering folder once (one model call each, a folder's pages cut to a fixed budget), never every folder. It runs last of the work steps and before the exports, so a kept export and the site carry this run's descriptions. A folder with no reading in it gets no description, and the step says how many.
- `catalogue.contents-from-claims` — **[GAP]** (#5365) an optional contents field lists what the item
  contains from confirmed claims, each item linked to its text.
- `catalogue.recipes-ship-prototypes` — **[GAP]** (#5365, #5364) a recipe or profile can carry its
  prototypes and their fields.
- `catalogue.export-standards` — **[GAP]** (#5365) fields export to EAD (ISAD(G)), Dublin Core, CSV and
  Excel, and IIIF manifest metadata.
- `catalogue.fields-parse-wherever-written` — **[OK]** (#6270, engine) each labelled field of the model's answer lands in its own attribute even when the model writes it inline after another ("... de mayo de 1918. Access points: A; B": the access points are a list, not the end of Condition), and a prose label (Scope and content, Description) ends the field before it. The numeric years agree with the Dates text: a year written in Spanish words ("mil novecientos seis" = 1906) counts, and a range whose first year cannot be read has no `catalogue_date_start` or `catalogue_date_end` rather than the end year as both. Test: `fichero-server/tests/unit/recipes/test_catalogue_fields_inline_and_spoken_dates_6270.py`.
- `catalogue.dates-read-colombian-year-forms` — **[OK]** (#6270, engine) the year range reads the forms a Colombian archive writes: a number before "de <month>" is a day, not a short end year ("1913 - 19 de febrero de 1918" is 1913–1918); Spanish thousands punctuation ("1.918" is 1918); years in words as a fallback ("mil novecientos nueve"); and a three-digit 8xx/9xx with the 1 dropped ("del 914") is 18xx/19xx only beside a full year within 30 years. Test: `fichero-server/tests/unit/recipes/test_catalogue_fields_inline_and_spoken_dates_6270.py`.
- `catalogue.scope-and-arrangement-are-attributes` — **[OK]** (#6267, engine) the labelled fields "Scope and content" and
  "Arrangement" of a folder's description are saved as its attributes `catalogue_scope_content` and `catalogue_arrangement`, like
  the other fields (a person's own value is never overwritten; Description stays prose). *Test:*
  `fichero-server/tests/unit/recipes/test_catalogue_promote_scope_arrangement_6267.py::test_scope_and_arrangement_are_parsed_as_attributes`.
- `catalogue.promote-is-undoable-and-idempotent` — **[OK]** (#6267, engine) the action `folder.promote_catalogue` (`folder_id`, or the
  whole project; `recursive`) re-reads each folder's latest `catalogue.narrative` and puts it in the folder's content and attributes
  through `put_in_content` and `put_in_attributes`, with no model call: folders described before a field existed gain it without a rerun.
  A folder already promoted from the same artifact changes nothing on a second call; one audited step, undone to what each folder held.
  *Tests:* `.../test_catalogue_promote_scope_arrangement_6267.py::test_promote_gives_an_earlier_folder_the_new_keys_and_is_idempotent`,
  `::test_promote_is_undone_to_what_the_folder_held`.
- `catalogue.excel-export-prints-description-once` — **[OK]** (#6267) in the Excel export a folder whose content is its catalogue
  description (`catalogue_content_from` set) does not also append its `catalogue.*` artifacts to its text, so the description prints once. The
  Markdown and site exports are unchanged. *Test:* `fichero-server/tests/unit/api/test_routes_export.py::TestExcelExportAttributes::test_a_promoted_folders_description_prints_once`.
- `catalogue.promote-reparses-with-the-current-parser` — **[OK]** (#6267) `folder.promote_catalogue` re-parses the saved description with the
  current parser and overwrites the folder's `catalogue_*` attributes an earlier run wrote (a value a person set is never touched); the undo puts the
  old values back. *Test:* `.../test_catalogue_promote_scope_arrangement_6267.py::test_promote_overwrites_a_machine_value_the_old_parser_got_wrong_and_undo_restores_it`.
- `catalogue.labels-start-a-field-after-a-closing-mark` — **[OK]** (#6267) a multi-word label (Access points, Creator and hands, Language and script,
  Scope and content) starts its field after any space, and any label after a closing bracket or quote, so a name list is never the Condition. In a Spanish
  description the English `[uncertain]` marker is `[incierto]` in the attribute (the description's own text still carries it until a new prompt version).
  *Tests:* `::test_access_points_after_a_closing_bracket_are_not_the_condition`, `::test_the_english_uncertain_marker_is_spanish_in_a_spanish_attribute`.
- `catalogue.a-rerun-is-the-next-version` — **[OK]** (#6267) a folder described again saves its `catalogue.narrative` as version n+1 citing the earlier as
  `source_artifact_id`; the latest (version, then time) is what promote reads and what the Excel export prints. *Test:* `::test_a_rerun_is_version_two_and_promote_reads_the_latest`.
- `catalogue.excel-claims-and-entities-reach-their-pages` — **[OK]** (#6267) in the Excel export a claim with no page label shows its page's name in
  `source_page_label`, and an entity's `source_document_ids` also lists the documents whose claims name it. *Test:* `fichero-server/tests/unit/api/test_routes_export.py::TestExcelExport::test_claims_have_a_page_label_and_entities_reach_their_documents`.
- `catalogue.excel-export-carries-attributes` — **[OK]** (owner goal 2026-10-28) `POST /api/export/excel`'s Documents sheet has one
  `attr:<key>` column per attribute key across the exported rows, and folder rows (the catalogue describes folders) beside the
  documents; `document_count` counts both. *Test:* `fichero-server/tests/unit/api/test_routes_export.py::TestExcelExportAttributes`.

## Test matrix

To be filled at approval. Fixtures: real items from the maintainer's projects (a Jesuit letter, a
1740 sale record, a Marshall diary entry), with the entry each should render and the EAD each
should export.

## Open questions

1. **Retire the narrative catalogue, or keep it as an optional, labelled "description by a model"?**
   Recommendation: retire it from the catalogue; the knowledge graph's readable summaries
   (`kg/kg-readable-representation.md`) are where prose belongs, written from claims.
2. **Which prototypes ship first?** Recommendation: `letter`, `notarial-record` (sale, will,
   contract), `diary-entry`, `map`, `photograph`, from the five real projects.
3. **Controlled vocabularies:** a project's own lists first, with mappings to Getty AAT for kinds of
   document where a project wants them. Recommendation: own lists, AAT optional.

## Future (ideas, not scheduled)
- (#4399) Multi-level cataloguing epic with LLM-proposed grouping; large product vision
