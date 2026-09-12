(AI generated. Not reviewed.)

# KG Endpoints Reference

Every backend endpoint the Swift inspector needs to know about. All
require `FICHERO_FEATURE_TIER=dev` on the engine + the standard
`Authorization: Bearer $TOKEN` and `X-Fichero-Library-Path: $LIB`
headers.

Generated 2026-05-12 after the overnight build-out.

> **Knowledge-object terminology (canonical, 2026-06-06):** the code models
> knowledge as a small fixed set of object types — use these words exactly:
> - **claim (SVO)** — a fact/assertion as a subject–verb–object triple,
>   classified by the `claim_type` enum (`fact`/`analysis`/`interpretation`/
>   `argument`/`historiography`/`theory`). Model: `KnowledgeClaim`
>   (`knowledge_models.py`). This is the *only* "statement" object; the
>   phrase **"ontological statement" is deprecated** — say "claim".
> - **interpretation (hermeneutic)** — a meaning-making statement produced by
>   applying an `InterpretiveFramework` to a claim/passage. A *distinct* object,
>   not a claim. Model: `Interpretation` (`hermeneutics_models.py`).
>   (Note: `claim_type="interpretation"` is a claim *classification*, not the
>   same thing as an `Interpretation` object.)
> - **entity** — `KnowledgeEntity`; **annotation** — `Annotation` (surface mark
>   on a document region); **note** — `Note` (free-floating Zettelkasten unit).
> - **attribute** — a *field* of an entity or claim (e.g. `confidence`,
>   `claim_type`, `subject_canonical`), **not** a separate object type.

## 1. Aggregate inspector — one call per selection

**These are the workhorses for the right-side inspector.** Use these
instead of N small calls.

| Endpoint | Returns |
|---|---|
| `GET /api/documents/{id}/inspector` | document + source_metadata + claims + entities + annotations + notes + citations (both directions) + interpretations + project memberships |
| `GET /api/entities/{id}/inspector` | entity + claims + documents + annotations + notes + projects + similar_entities (LanceDB cosine) + triangulated_facts |

## 2. CRUD primitives

### KnowledgeEntity
```
POST   /api/entities          upsert (uses fuzzy match)
GET    /api/entities?q=&entity_type=
GET    /api/entities/{id}
PATCH  /api/entities/{id}     partial — refreshes LanceDB vector
DELETE /api/entities/{id}?cascade_claims=true|false
POST   /api/entities/{id}/aliases
```

### KnowledgeClaim
```
POST   /api/claims
GET    /api/claims/{id}
GET    /api/claims?entity_id=&source_document_id=
PATCH  /api/claims/{id}
DELETE /api/claims/{id}
POST   /api/claims/{id}/links     (KnowledgeClaimLink — supports/contradicts/refines)
```

### Annotation (#914)
```
POST   /api/annotations
GET    /api/annotations?document_id=&kind=&tag=&min_rating=
GET    /api/annotations/{id}
PATCH  /api/annotations/{id}
DELETE /api/annotations/{id}
POST   /api/annotations/{id}/promote-to-claim   creates a KnowledgeClaim
```

### Note (#917)
```
POST   /api/notes
GET    /api/notes?kind=&tag=&linked_entity_id=&q=    full-text search included
GET    /api/notes/{id}
PATCH  /api/notes/{id}
DELETE /api/notes/{id}
POST   /api/notes/{id}/links              bidirectional NoteLink
DELETE /api/notes/{id}/links/{link_id}
GET    /api/notes/{id}/backlinks          what points here
GET    /api/notes/{id}/forward-links      what this points to
```

### Project (#918)
```
POST   /api/projects
GET    /api/projects?status=active
GET    /api/projects/{id}
PATCH  /api/projects/{id}
DELETE /api/projects/{id}               cascades inclusions
POST   /api/projects/{id}/include       body: {target_id, target_type, role, notes}
DELETE /api/projects/{id}/include/{inclusion_id}
GET    /api/projects/{id}/items?target_type=
GET    /api/projects/membership/{target_id}?target_type=    which projects include this row?
```

### Interpretation + InterpretiveFramework (#905)
```
POST   /api/kg/interpretations/frameworks
GET    /api/kg/interpretations/frameworks
GET    /api/kg/interpretations/frameworks/{id}
PATCH  /api/kg/interpretations/frameworks/{id}
DELETE /api/kg/interpretations/frameworks/{id}

POST   /api/kg/interpretations
GET    /api/kg/interpretations?framework_id=&claim_id=&document_id=
GET    /api/kg/interpretations/{id}
PATCH  /api/kg/interpretations/{id}
DELETE /api/kg/interpretations/{id}
```

### DocumentCitation graph (#906)
```
POST   /api/citations/graph
GET    /api/citations/graph?source_document_id=&target_document_id=&detector=&min_confidence=
GET    /api/citations/graph/document/{id}/outbound    what it cites
GET    /api/citations/graph/document/{id}/inbound     what cites it
PATCH  /api/citations/graph/{id}
DELETE /api/citations/graph/{id}
```

### ClassificationValue (#915)
```
GET    /api/classifications?dimension=epistemic_status|claim_type|entity_type
POST   /api/classifications      custom value
PATCH  /api/classifications/{id}
DELETE /api/classifications/{id} 409 on built-in
```

## 3. Bibliography

### Stored metadata
```
GET    /api/bibliography/document/{id}
PATCH  /api/bibliography/document/{id}    body: {metadata: {...}}
POST   /api/bibliography/document/{id}/extract?use_llm=true|false
                            PyMuPDF + Apple Intelligence cover-pages
POST   /api/bibliography/resolve          body: {doi or isbn} ?document_id=
                            Crossref + Open Library online lookup
POST   /api/bibliography/import           body: {text, format?}  parses BibTeX/RIS/CSL
POST   /api/bibliography/export.bib       body: {document_ids: [...]}
```

### Citation rendering (#912)
```
GET    /api/citations/document/{id}?style=bibtex|chicago|apa|mla
GET    /api/citations/document/{id}.bib    plaintext download
GET    /api/citations/export?document_ids=A&document_ids=B   bulk BibTeX
```

## 4. KG analytics

### Triangulation (#900)
```
GET    /api/kg/triangulation?threshold=3       triples with support_count >= threshold
GET    /api/kg/triangulation/entity/{id}       triples involving entity as subject
```
Response includes `weighted_support` (scaled by SourceAuthority) so the
inspector can show "triangulated (3 primary + 1 secondary)".

### Graph traversal (#376)
```
GET    /api/kg/graph/centrality?top_k=20&entity_type=person
GET    /api/kg/graph/cooccurrence/{entity_id}   neighbours + edge weights
GET    /api/kg/graph/path?source=A&target=B
```

### PyKEEN link prediction (#377)
```
POST   /api/kg/pykeen/train?model=TransE&num_epochs=50
GET    /api/kg/pykeen/predict/{entity_id}?top_k=10
```

## 5. Curation loop

### Review queue (#899 Phase D)
```
GET    /api/kg/review/pairs                pending pairs, newest first
POST   /api/kg/review/pairs                manually queue a pair
POST   /api/kg/review/pairs/{id}/accept    merge candidate into survivor
POST   /api/kg/review/pairs/{id}/reject    labelled negative
GET    /api/kg/review/labels               accumulated decisions
```
Auto-retrains PyKEEN every 10 decisions.

### Mutation log + undo (#901)
```
GET    /api/kg/mutations
POST   /api/kg/mutations/{id}/undo         restores before-state
```

### Rebuild derived stores
```
POST   /api/kg/rebuild      body: {vectors?: true, triples?: true}
```

## 6. Mixed-type search

```
GET    /api/kg/search?q=&types=entity&types=note&limit=50
```
Returns hits across entities + claims + notes + annotations, each
tagged with `hit_type` so the inspector renders the right preview.

## Curl recipe — full inspector flow

```bash
TOKEN=$(cat ~/Library/Application\ Support/Fichero/.api-key)
LIB="$HOME/Library/Application Support/com.fichero.fichero/global.fichero"
H=(-H "Authorization: Bearer $TOKEN" -H "X-Fichero-Library-Path: $LIB")

# One call to populate the document inspector
curl -sS "${H[@]}" http://localhost:8765/api/documents/<doc-id>/inspector | jq

# One call for the entity detail view
curl -sS "${H[@]}" http://localhost:8765/api/entities/<entity-id>/inspector | jq

# Mixed-type search bar
curl -sS "${H[@]}" "http://localhost:8765/api/kg/search?q=davidson&limit=20" | jq

# Triangulation badges
curl -sS "${H[@]}" "http://localhost:8765/api/kg/triangulation?threshold=2" | jq

# Render a citation (4 styles)
curl -sS "${H[@]}" "http://localhost:8765/api/citations/document/<doc>?style=chicago" | jq

# Bulk BibTeX export
curl -sS "${H[@]}" -X POST -H "Content-Type: application/json" \
  -d '{"document_ids": ["a","b","c"]}' \
  http://localhost:8765/api/bibliography/export.bib

# Curation: get pending pairs, accept one
curl -sS "${H[@]}" http://localhost:8765/api/kg/review/pairs | jq
curl -sS "${H[@]}" -X POST http://localhost:8765/api/kg/review/pairs/<pair-id>/accept

# Train PyKEEN, get predictions
curl -sS "${H[@]}" -X POST "http://localhost:8765/api/kg/pykeen/train?num_epochs=50"
curl -sS "${H[@]}" "http://localhost:8765/api/kg/pykeen/predict/<entity-id>?top_k=10"
```
