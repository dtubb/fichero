# Chapter 7. Searching


### About Search

Search runs from the toolbar search field, and results render into the Library view — so you can use every library layout on a result set. Fichero finds documents by meaning as well as by exact words: relevance blends semantic similarity against embedded text with full-text matching, combined when both contribute. Highly ranked results are usually pages or documents whose text is both semantically close to your query and a good literal match.

As you type, Fichero re-runs the query with a short debounce; you can also submit explicitly with Return. Results can be sorted by relevance, date, name, or size.

### Search Scopes

The search field understands scoped queries for entity types:

- 
- 
- 
- 
- 
- 

`people:` — e.g. `people:Asprilla``places:` — e.g. `places:"Quibdó"``organizations:``dates:``events:``keywords:` — e.g. `keywords:"social license"`Two semantic scopes search the knowledge graph itself: `entities:` and `claims:` (singular forms work too). `entities:Asprilla` finds entities semantically; `claims:mine` finds claims. Clicking an entity name or lozenge elsewhere in the app can launch a scoped search of this kind for you.

### Saved Searches

When search results are present, the toolbar shows **Save Search**. Saved searches become sidebar items you can reopen later. The search surface also offers suggestions returned with each result set, recent searches, and a keyword cloud built from the library — clicking a keyword-cloud term runs a scoped keyword query.
