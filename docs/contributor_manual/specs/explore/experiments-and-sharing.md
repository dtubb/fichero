# Explore: experiments, saved views, sharing and care — Design Spec (#5032)

> Milestone: explore
> Manual: TBD — a section of "Exploring a project": trying a view and throwing it away; keeping
> one so it can be run again; comparing two methods; exporting a view with its data; publishing
> one; what never leaves the machine; care in how people are shown.
>
> **Status: DRAFT — first pass, 2026-09-20.** Foundation, words and common rules: `explore.md`.

## Intent (the design)

The maintainer's principle for this whole layer (2026-09-20, paraphrased): Fichero should make
it EASY TO EXPERIMENT. Not a fixed set of charts but a bench. A researcher wonders what their
pages would look like laid out by meaning, or who travels with whom in 1926, and can try it in a
minute, see it, keep it or throw it away. That gives four requirements, RULED in the brief:

- **cheap and disposable**: run on a selection, a folder or a search result; nothing about the
  project changes; discard leaves no trace; keeping saves how to make the picture, not the
  picture;
- **methods behind one seam**: projection, grouping, labelling, layout, linking, each a named
  method with its settings shown, so two can be compared and a result says how it was made;
- **local, always**: everything computes on the researcher's machine. **No hosted service is
  used for visualisation, ever** (RULED 2026-09-20; this replaces the brief's "outside by
  choice"): doing locally what a hosted embedding-map service does is the purpose of the app;
- **easy in and out**: one command exports what is showing as FILES in standard formats (what
  a researcher does with a file outside the app is theirs), and the command line and agents can
  run the same experiments.

This file also holds the two things that make the work leave the machine well: **publishing**
(a saved view on the web; a dataset others can join to) and **care in representation**.

## Prior art

Nomic Atlas's developer flow (embed, map, label, explore, share) is the model of ease, and
only a model: it is hosted, and nothing here uses it.
Observable and Jupyter are the model of "the picture is a program that can be run again".
Enslaved.org is the model for publishable, joinable linked open data with provenance on every
statement and deliberate care about people recorded as property. The CARE principles for
Indigenous data governance and the FAIR principles are the two standards a published dataset is
held to; the source-model set's rights and access file (`source.rights.*`, → #4953) is where
Fichero enforces them, and this family obeys it rather than restating it. Reproducible-research
practice supplies the rule that a figure travels with its data and its method.

## What exists

- Saved searches: create, list, reorder, duplicate (`api/routes/search/core.py`). The compiled
  form of a natural-language query is returned and editable. This is the nearest thing to a
  saved view and the proposed thing to grow.
- One audited action layer; one background throttle; one export record stream; an Eleventy
  static-site export with entity pages, claim indexes and a search page; RDF export with a named
  JSON-LD context; MCP and CLI for search and the knowledge graph.
- Things that already call outside the machine: Wikidata enrichment (sends entity names to
  Wikidata), MapKit (fetches map tiles from Apple), any cloud model a researcher has configured.
- Rights and access: specified (`source.rights.*`), not built (→ #4953). Claim authorship is
  absent from every export (`export/exporter.md`).
- **No method seam, no experiment, no saved view, no comparison, no published view.**

## Behaviors

Experiments
- `explore.experiment.one-step-from-a-set` — **[GAP]** (#5032) from any set, choosing a view
  makes it, with sensible defaults and no form to fill in first. Settings are adjusted AFTER
  the first picture, not before.
- `explore.experiment.changes-nothing` — **[GAP]** (#5032) an experiment writes nothing to the
  project: no positions, no tags, no claims, no audit entries.
- `explore.experiment.discard-leaves-no-trace` — **[GAP]** (#5032) leaving an experiment without
  keeping it removes everything it computed. Nothing accumulates.
- `explore.experiment.cancellable` — **[GAP]** (#5032) an experiment that takes more than a
  moment shows progress and can be cancelled; cancelling frees what it was using at once.
- `explore.experiment.one-heavy-thing-at-a-time` — **[GAP]** (#5032) heavy experiments queue
  rather than run side by side, and yield to anything the researcher is doing in the
  foreground.

Methods behind one seam
- `explore.method.one-seam` — **[GAP]** (#5032) every computation in this set is a named method
  registered in one place in the engine, taking a set and settings and returning marks with
  their evidence ids, the method's name, version, settings and seed. There is no second way to
  compute a view.
- `explore.method.settings-are-shown-and-few` — **[GAP]** (#5032) a method shows the settings
  that change the picture, in plain words, with defaults that are right for the size of the
  set. Dead-simple rule: no setting is offered that a researcher cannot see the effect of.
- `explore.method.deterministic` — **[GAP]** (#5032) the same set, method, settings and seed
  give the same result, on the app, the command line and an agent.
- `explore.method.says-what-it-used` — **[GAP]** (#5032) a result records which vectors (model
  id), which readings, which claims (as of what moment in the project's history) it was made
  from, so that a later difference can be explained.
- `explore.method.adding-one-is-small` — **[GAP]** (#5032) adding a method adds it to the menu,
  the command line and the agent tools at once, with no new view code.

Keeping, comparing
- `explore.saved.keep-is-one-action` — **[GAP]** (#5032) keeping an experiment is one typed,
  audited action that stores the set's description, the view, the method and its settings, any
  renamed labels and any pinned positions. It never stores the picture as the truth.
- `explore.saved.is-a-node` — **[GAP]** (#5032) a saved view is a node in the sidebar beside
  saved searches (nodes, not modes): selecting it shows that set in that view in the Library
  pane. PROPOSED: it is a saved search that also remembers its view (open; see the questions file).
- `explore.saved.re-run-says-what-changed` — **[GAP]** (#5032) opening a saved view runs it
  again on the project as it is now, and says what is different since it was kept (items added,
  claims changed, vectors remade).
- `explore.saved.results-are-worked-out-things` — **[GAP]** (#5032) a kept result may be cached
  so it opens quickly, but the cache can always be deleted and remade, is never synced as
  research data, and is removed by a purge of what it was made from
  (`source.rights.purge-reaches-derivatives`).
- `explore.saved.compare-two` — **[GAP]** (#5032) two experiments on the same set (two methods,
  two settings, two dates) open side by side in two panes with the same selection, so that the
  same items can be found in both. No new comparison surface. Two panes side by side work
  today; the SHARED selection is BLOCKED on the pane-linking design session (#4881).
- `explore.saved.shareable-as-a-file` — **[GAP]** (#5032) a saved view can be exported and
  imported as a small readable file (its description only, no research data), so a colleague
  with the same kind of project can run it. This follows the ruling that recipes are files.

In and out
- `explore.out.export-what-is-showing` — **[GAP]** (#5034) one command exports the current view:
  its table (CSV, Parquet), its network (GEXF, GraphML), its places (GeoJSON), its vectors and
  positions (Parquet), and a picture (PDF or PNG), each with a small file saying how it was
  made and from what. Through the existing export stream.
- `explore.out.citable` — **[GAP]** (#5032) an exported picture carries a caption a historian
  can cite: the project, the set, the method and settings, the date, the count of what was left
  out.
- `explore.out.agents-and-cli-run-the-same` — **[GAP]** (#5032) every method and export is an
  MCP tool and a CLI command through the same seam, so a notebook or an agent can drive them.
  An agent's experiment is attributed to the agent as a user, as the action layer already does.
- `explore.out.rights-apply` — **[GAP]** (#5032, waits on → #4953) every export leaves out what
  the rights record restricts, and says how much it left out.

Publishing
- `explore.publish.saved-view-on-the-static-site` — **[GAP]** (#5032) a saved view can be
  included in the project's static-site export as a page: the view's data and a small bundled
  HTML drawing of it, with each mark linking to the published page of its source where that
  source is published, and to a citation where it is not.
- `explore.publish.one-data-shape` — **[GAP]** (#5032) the native view in the app and the
  published HTML page draw the SAME data, in one documented shape. This is how the web
  advantage is kept without running WebKit while working.
- `explore.publish.is-an-explicit-act` — **[GAP]** (#5032) publishing is a deliberate, audited
  action that lists exactly what will leave, runs the rights check, and shows what was held
  back. Nothing in this set publishes as a side effect.
- `explore.publish.joinable-dataset` — **[PARTIAL]** (#5032) a project's people, places, events
  and claims can leave as linked open data (RDF with the named JSON-LD context), with stable
  identifiers, outside identifiers where reconciled (Wikidata, a gazetteer), and the provenance
  of every statement. The RDF export is built; stable published identifiers and claim
  authorship in the export are not.
- `explore.publish.and-come-back` — **[GAP]** (#5032) a dataset published this way, by this or
  another project, can be imported, arriving as claims asserted by that dataset (never as the
  researcher's own), so that two projects can be joined and looked at together.

Never (RULED 2026-09-20)
- `explore.outside.no-hosted-service-ever` — **[GAP]** (#5032) no behaviour in this set sends
  project content, vectors, names, positions or labels to any hosted service, and there is no
  setting, export target or per-act exception that does. Labels, groups, layouts and summaries
  are made by local methods only. A cloud model a researcher has configured for other work is
  never used by this set.
- `explore.outside.files-are-the-way-out` — **[GAP]** (#5032) what leaves, leaves as FILES in
  standard formats that the researcher saves (`explore.out.export-what-is-showing`) or as a
  publication they perform (`explore.publish.is-an-explicit-act`). The app uploads nothing to a
  visualisation service on anyone's behalf.
- `explore.outside.existing-calls-are-named` — **[GAP]** (#5032) the calls that already leave the
  machine near this layer (Wikidata reconciliation sends names; Apple's map fetches tiles for
  the region in view) are stated to the researcher where they happen, and each has an off
  position that still leaves a working view (`explore.place.works-offline`).

Care in representation
- `explore.care.names-before-numbers` — **[GAP]** (#5032) where a set is of people, an aggregate
  always opens to the named individuals and their sources; no view of people is ONLY counts.
- `explore.care.the-record-is-not-the-person` — **[GAP]** (#5032) labels in views of people use
  the project's chosen terms, not the source's where the source's terms are ones of ownership,
  race or crime; the source's own words remain one step away, in the evidence. The terms are
  the project's to set (a vocabulary, with the source-model's profile), and a view says that it
  is using them.
- `explore.care.restricted-people-are-not-drawn-around` — **[GAP]** (#5032, waits on → #4953) a
  restricted person is not identifiable from what surrounds them in a view: a network does not
  leave a named gap, a map does not leave a single unnamed pin at a home.
- `explore.care.publishing-asks-about-people` — **[GAP]** (#5032) publishing a view or dataset
  that includes people asks, once, whether any are living or have living descendants or
  communities with a say, and points to the rights record to set it. The decision is recorded
  with the publication.
- `explore.care.silences-are-visible` — **[GAP]** (#5032) every view's count of what it could not
  draw (`explore.source.nothing-silently-left-out`) is part of the published and exported form
  too: who is missing from the record is part of the finding.

## How it is drawn

The seam, the saved view and the exports are engine work with thin native controls. The only
HTML in this set is the published page.

## Test matrix (legs this family touches)

Backend (the seam: determinism, evidence ids, "says what it used"; experiments leave no rows
behind; every exporter validates against its standard; rights are applied); MCP and CLI (every
method and export, same result as the app: the set's hard gate); pure Swift (the kept record
round-trips); click-around (try, discard, nothing remains; keep, reopen, same picture); load
(heavy experiments queue and yield).

## Open questions for the creative director

Still open, not blocking: whether a saved view is a saved search that remembers its view; the
word "recipe"; the vocabulary of care (whose job, and when). Full text in `agent-work/dh-layer/questions-for-the-maintainer.md`.
