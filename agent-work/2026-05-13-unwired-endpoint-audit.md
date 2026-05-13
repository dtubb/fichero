# Unwired Backend → SwiftUI Endpoints (audit 2026-05-13)

OpenAPI exposes 30 endpoint groups; SwiftUI Services consumes ~22. The gap is real product surface — 51 endpoints with no Swift consumer.

## Unwired (no dedicated Service class)

| Group | Endpoints | Product hook |
|---|---:|---|
| annotations | 4 | Document annotation overlays; pairs with KG verbatim quotes |
| bibliography | 5 | Bibliography list + edit, citation graph (#974) prerequisite |
| citations | 7 | In-text [@key] → bib entry → claim, library-wide graph (#974) |
| classifications | 2 | Doc type classification surface (could feed view filters) |
| multilingual | 6 | Language detection + translation hooks (workflow polish, #926) |
| notes | 6 | Per-document or per-claim free-text notes |
| projects | 6 | Project-level organization (above library) |
| tasks | 13 | Hazel-like automation tasks list / status |
| sources | 2 | KG source linkage (claim → source span) |

## Next-wave candidates (highest leverage)

1. **CitationService + BibliographyService** — wires #974 (citation graph) and tightens claim→source rendering for #959 (already in flight via Stream B). These are read-mostly; small.
2. **AnnotationService** — overlays on PDFs/images, can be the surface for "show me the highlighted span this claim came from."
3. **TasksService** — Hazel automation already partly exposed in Integrations; surfacing the task list closes a UX loop.

## Already wired (no action)

activity, artifacts, batches, chat, documents, entities (via EntityServiceGenerated), folders (via DocumentService), health, ingest (ImportServiceGenerated), kg-partial, mcp, models, providers, search, storage, workflow-execution, workflows, settings (via AppState).

## Decision

Hold the next-wave dispatch until Streams A/B/C land — adding writers now would conflict on `EntityServiceGenerated.swift` and `DocumentInspector.swift`. After merge: dispatch a Stream D (CitationService + BibliographyService) and Stream E (#901 inline claim PATCH UI).
