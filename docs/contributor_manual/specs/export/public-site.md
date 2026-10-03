# Export — A public research site for an archive (first: Istmina) — Design Spec (#5381)

> Milestone: source-model
> Manual: TBD — a section, "Publishing an archive for the public", explaining what goes on the site,
> what is withheld and why, how people search it, and how it is updated as the work goes on.
>
> Design-led (Testing Constitution). **Status: DRAFT** (2026-10-03). Item 7 of `../SPEC-PLAN.md`.
> Builds on the Eleventy static-site export (`exporter.md`, `export.eleventy-site-is-buildable-and-portable`
> [OK]), IIIF published folders (`../source/iiif.md`), the gazetteer and name list
> (`../kg/project-gazetteer-and-names.md`), cataloguing (`../source/cataloguing.md`), and rights
> (`../source/rights-and-access.md`).

## Intent

The Istmina archive (Chocó, Colombia, 1870s to 1980s) holds the names of the people of a place,
across generations. The people of Istmina should be able to search it, on a phone, for their
families: a name, a place, a year, and the pages that mention them. Fichero builds that site from
the project, as a static website that needs no server, and keeps it up to date as the work goes
on. The same publishing works for any archive; Istmina is the first.

## The design

**What the site has.**
- **Search** by name (every attested form leads to the person's page), place, year and kind of
  document, in Spanish first; it runs in the browser (a prebuilt index), so the site needs no
  server.
- **A page per person and per place** from the name list and gazetteer: the forms used, the
  documents and passages that mention them, dates as attested, places on a map.
- **A page per document**: its catalogue entry (fields only, `catalogue.entry-shows-not-tells`), the
  page images through IIIF (the institution's server, or Fichero's level 0 tiles), and the
  transcription beside them, with what is uncertain marked as such.
- **Show, not tell.** No AI-written summaries or interpretations on the public site; prose is
  rendered from facts.
- **Plain, fast, accessible:** works on a phone and on a slow connection; readable type; Spanish
  and English labels.

**What it never has.** The rights and consent records decide (`rights.*`). By default the
**living and the recently dead are withheld** (a person born within the last 100 years with no
recorded death, or dead within the last 25, unless their family consents), and so are documents
the rights record restricts. Withheld material is absent, not blanked: no name, no count, no
hint (the ruling of 2026-09-28 that a deny hides).

**Kept up to date.** The site is a published folder (`iiif.folder.published`) whose export is
synced: corrections, new pages and confirmed links re-export only what they touched, and the site
is rebuilt and deployed (GitHub Pages, Netlify, or an institution's server).

**Feedback from the community.** Each page offers "I know something about this person or
document": a simple form (or email) whose submissions come back to the project as notes for a
person to review, never published directly.

## Behaviors

- `site.search-in-browser` — **[GAP]** (#5381) the site searches names (every attested form), places,
  years and document kinds with a prebuilt index; no server is needed.
- `site.person-and-place-pages` — **[GAP]** (#5381) each person and place has a page with its forms,
  the passages that mention it, attested dates and a map.
- `site.document-pages` — **[GAP]** (#5381) each document has its catalogue entry, its page images by
  IIIF and its transcription, uncertainty marked.
- `site.show-not-tell` — **[GAP]** (#5381) the site carries no AI-written summary or interpretation.
- `site.living-withheld` — **[GAP]** (#5381) the living and recently dead, and restricted documents, are
  absent from the site (no name, no count), unless consent is recorded.
- `site.kept-current` — **[GAP]** (#5381) changes in the project re-export only what they touched and the
  site is rebuilt and deployed.
- `site.phone-and-slow-connection` — **[GAP]** (#5381) every page works on a phone and on a slow
  connection, in Spanish and English.
- `site.community-notes` — **[GAP]** (#5381) visitors can send what they know about a person or document;
  it reaches the project as a note for review and is never published directly.

## Test matrix

To be filled at approval. Fixtures: a slice of the Istmina library with known living and dead
people, restricted documents, and name variants; the built site checked for absent material and
for search by every variant.

## Open questions

1. **Where it is hosted.** Recommendation: GitHub Pages under the project's organisation first; an
   institution in Chocó later if one will host it.
2. **The thresholds for "recently dead" and "living"** (100 and 25 years above). Recommendation:
   those, set per project, agreed with the community before publishing.
3. **Community notes channel:** a form that files into the project, or plain email. Recommendation:
   email first (no server), a form later.
