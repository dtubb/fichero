# Search, Entities, and the Knowledge Graph

## Table of Contents

- [Global Search](#global-search)
- [Saved Searches, Suggestions, and Keywords](#saved-searches-suggestions-and-keywords)
- [What Relevance Means](#what-relevance-means)
- [Entities and Claims](#entities-and-claims)
- [Knowledge Graph Views in the Inspector](#knowledge-graph-views-in-the-inspector)

## Global Search

The dedicated search view uses the toolbar search field. As you type, Fichero re-runs the query with a short debounce, and you can also submit explicitly with Return.

The current search experience includes:

- live search-as-you-type
- result sorting by relevance, date, name, or size
- save-search support when a result set is worth keeping
- keyword cloud and recent-query shortcuts in the empty state

## Saved Searches, Suggestions, and Keywords

When search results are present and you are not already viewing a saved search, the toolbar shows `Save Search`. Saved searches become sidebar items you can reopen later.

The search surface also exposes:

- suggestions returned with the result set
- recent searches stored per window/session state
- a keyword cloud built from the library

Clicking a keyword cloud term runs a scoped keyword query rather than generic free text.

## What Relevance Means

Today, Fichero's main `/api/search` route is document-centric. In practical terms, relevance comes from a blend of:

- semantic similarity against embedded document or page text
- full-text matching against indexed text
- reciprocal-rank fusion when both retrieval methods contribute

That means highly ranked results are usually pages or documents whose indexed text is both semantically close to your query and a good literal text match.

## Entities and Claims

Fichero distinguishes between:

- `entities`: people, places, organizations, events, concepts, and related named things
- `claims`: statements associated with those entities and extracted from source material

The user-facing app does not treat those as an abstract theory layer. You see them in specific surfaces:

- `Entities` tab in the inspector
- `Knowledge Graph` tab in the inspector
- entity detail views in the knowledge-graph browser

### About Scopes

The current search parser understands explicit scoped fields for:

- `people:`
- `places:`
- `organizations:`
- `dates:`
- `events:`
- `keywords:`

Examples:

- `people:Asprilla`
- `places:"Quibdó"`
- `keywords:"social license"`

There is not currently a separate user-facing toolbar scope for `claims:` or `entities:` in the main `/api/search` route. Instead:

- content search happens in the main search view
- entity and claim inspection happens through the inspector and knowledge-graph surfaces
- tapping entity lozenges or names can launch scoped library searches based on the entity type

## Knowledge Graph Views in the Inspector

The `Knowledge Graph` tab is the main place to inspect extracted graph material for a document.

It supports:

- a `Text` digest mode for compact prose summaries
- a `List` mode for grouped expandable rows
- per-kind filtering, persisted across launches
- claim multi-selection
- claim approval, rejection, suppression, merging, and pruning
- page-or-folder scope and library-wide scope where supported
- source navigation back to the originating page

The broader KG surface also includes timeline and map-oriented views for document-related graph material, plus entity inspection when you focus a specific entity.
