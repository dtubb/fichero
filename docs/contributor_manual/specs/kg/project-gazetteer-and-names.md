# Knowledge Graph — The project gazetteer and the canonical name list — Design Spec (#5380)

> Milestone: source-model
> Manual: TBD — a section, "Places and names", explaining the project's gazetteer and name list:
> every way a place or person is written in the sources, the preferred form, the links to Wikidata
> and gazetteers, what was fetched from them, and how to merge, split or correct.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-10-03). Item 4 of `../SPEC-PLAN.md`.
> Builds on `kg-enrichment.md` (authority links, geocoding, the imported-versus-extracted layers),
> `kg-tables.md` (merge), `kg-readable-representation.md` (resolution that avoids bad merges),
> `../source/maps-and-georeference.md`, and the code in `knowledge/places.py` (a place's geometries
> over time) and `knowledge/linked_places.py`.

## Intent

A historian's archive names the same town five ways and the same man in three spellings across
forty years. Two things make the archive usable: **a gazetteer** of its places and **a canonical
name list** of its people and bodies, one of each per project, kept as good as the evidence allows.
Each entry holds every form the sources use, with the passages; a preferred form; links to the
world's authorities; and what those authorities add, kept apart from what the pages say.
Families searching the Istmina archive will find their people through this list.

## Prior art

- **World Historical Gazetteer** and the **Linked Places Format** (GeoJSON-LD with names, types,
  geometries and their time spans, and links): the interchange Fichero already reads and writes in
  `linked_places.py`.
- **Pleiades** (ancient places), **Getty TGN**, **GeoNames**, **Wikidata**: the authorities, each
  linked by its stable URI.
- **Authority files for people:** VIAF, Wikidata, and a project's own list (prosopographies keep
  variant spellings with their sources, and never merge without evidence).
- **Record linkage practice:** candidate pairs scored, then confirmed by a person; a merge is
  reversible and keeps both originals.

## The design

**An entry.** For a place: its forms as written (each with language, period and the passages it
occurs in), a preferred form, types (town, river, hacienda, parish), geometries over time with
their sources (`EvidentialPlace`), and links. For a person or body: forms as written, a preferred
form, roles and dates as attested, relations, and links. Every fact names its source.

**The preferred form** is chosen by a person, or by a stated rule where none has: the form the
project's authority link gives, else the most frequent form in the sources. The rule is shown
beside the form.

**Links are proposed, then confirmed** (`kg.entity.authority-link-create`): candidates from
Wikidata, WHG, Pleiades, TGN and GeoNames, ranked by name, type, place and period, each with its
evidence; a person confirms. A confirmed link can be undone.

**Enrichment from Wikidata and the gazetteers** fills in what the sources do not say (coordinates,
types, alternative names, dates of existence, a parent region) as claims whose source is the
authority and the date fetched, kept in their own layer (`kg.enrich.imported-vs-extracted-layers`).
They never overwrite what the pages say; where they disagree, both stand, marked.

**Merges and splits are proposals.** Two entries that look like one person or place are offered
for merging with the evidence for and against; nothing merges by itself. A merge keeps every form
and passage of both, and can be split again.

**How good it is, shown.** The list shows: how many mentions are linked to an entry, how many are
unresolved (a worklist), entries with conflicting coordinates or dates, likely duplicates, and
entries with no authority link. "As good as possible" is these numbers going down.

**Export:** Linked Places Format for the gazetteer; CSV and Excel for both lists; RDF with the
authority URIs; and the static site's place and name pages.

## Behaviors

- `gazetteer.one-per-project` — **[GAP]** (#5380) a project has one gazetteer of its places, each entry
  with every form as written (language, period, passages), types, geometries over time and links.
- `names.one-per-project` — **[GAP]** (#5380) a project has one canonical name list of its people and
  bodies, each with every attested form and its passages, roles and dates as attested.
- `names.preferred-form-rule` — **[GAP]** (#5380) each entry's preferred form is chosen by a person or by
  the stated rule (the confirmed authority's label, else the most frequent form), shown beside it.
- `gazetteer.links-proposed-confirmed` — **[GAP]** (#5380) authority links are proposed with their
  evidence and confirmed by a person; a confirmed link can be undone.
- `gazetteer.enrichment-kept-apart` — **[GAP]** (#5380) facts fetched from Wikidata or a gazetteer are
  claims sourced to it and the fetch date, in their own layer, never overwriting what the pages say;
  disagreements stand side by side, marked.
- `names.merge-is-a-proposal` — **[GAP]** (#5380) likely duplicates are offered with evidence for and
  against; nothing merges by itself; a merge keeps every form and passage and can be split again.
- `gazetteer.quality-shown` — **[GAP]** (#5380) the lists show linked and unresolved mentions, conflicts,
  likely duplicates and unlinked entries, with the unresolved ones as a worklist.
- `gazetteer.export` — **[GAP]** (#5380) the gazetteer exports as Linked Places Format, both lists as
  CSV and Excel, and both as RDF with authority URIs.

## Test matrix

To be filled at approval. Fixtures: places and people from the Istmina archive and the 1740 sale
records with known variant spellings, and their Wikidata and WHG matches.

## Open questions

1. **Which authorities by default?** Recommendation: Wikidata and WHG for places; Wikidata and the
   project's own list for people; others added per project.
2. **Rate of automatic proposals:** propose links as mentions are found (in the background, as a
   recipe step), or only when a person opens the list? Recommendation: as a recipe step, throttled,
   because the worklist is what makes it improve.
3. **Living people** in a public site (Istmina's later records reach the 1980s): withheld by default
   under the rights record. Recommendation: yes, withhold the living and recently dead by default.
