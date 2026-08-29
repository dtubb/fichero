# Chapter 8. The Knowledge Graph


### About Entities and Claims

As workflows process your documents, Fichero builds a knowledge graph:

- 
- 

**Entities** — people, places, organizations, events, concepts, dates, and other named things.**Claims** — statements extracted from source material and associated with those entities: who did what, where, and when.These are not an abstract theory layer; you meet them in specific surfaces: the inspector’s **Knowledge** section for the selected document, the Reader’s **Knowledge** tab for the current page, and the Knowledge Graph sidebar mode for browsing across the whole library, including entity detail views and timeline- and map-oriented views.

### The Knowledge Section of the Inspector

The inspector’s **Knowledge** section is the main place to inspect extracted graph material for a document. It supports:

- 
- 
- 
- 
- 

### a **Text** digest mode for compact prose summariesa **List** mode for grouped, expandable rowsper-kind filtering, remembered across launchesclaim multi-selectionnavigation back to the source page an item came fromCurating the Graph

Extraction is a draft; curation makes it a record. For selected entities and claims, the inspector exposes:

- 
- 
- 
- 
- 

**Approve** — accept the item as correct.**Reject** — mark it wrong.**Suppress** — hide it, optionally writing a persistent rule.**Merge** — fold duplicates into one surviving canonical item.**Prune trivial** (claims only) — clear out trivially true claims.Most actions can be applied at two scopes: the current page or folder, or library-wide. Library-wide suppression can write a persistent suppress rule, so your decision continues to apply to future imports and later refreshes — if you reject a spurious entity once, it stays rejected.

Merging keeps one surviving canonical item and folds the others into it. The app keeps curation history for entity merge and split operations, with undo available from the audit history in the Knowledge section. Claim unmerge is not yet a finished UI path, so do not expect a polished reverse-merge for claims in current builds.

You can also grow the graph from your own reading: an annotation can be promoted into a claim (Chapter 5).
