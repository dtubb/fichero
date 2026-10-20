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
- `catalogue.contents-from-claims` — **[GAP]** (#5365) an optional contents field lists what the item
  contains from confirmed claims, each item linked to its text.
- `catalogue.recipes-ship-prototypes` — **[GAP]** (#5365, #5364) a recipe or profile can carry its
  prototypes and their fields.
- `catalogue.export-standards` — **[GAP]** (#5365) fields export to EAD (ISAD(G)), Dublin Core, CSV and
  Excel, and IIIF manifest metadata.

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
