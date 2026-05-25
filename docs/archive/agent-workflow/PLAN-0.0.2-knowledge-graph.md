# Plan: Fichero 0.0.2 Knowledge Graph — Full Stack Architecture

## Context

We have a 0.0.1 codebase with:
- **SwiftUI frontend**: Three-column layout (Sidebar | Content | Inspector)
- **Python backend**: FastAPI with DuckDB storage, existing knowledge graph models
- **Goal**: Expand to a complete research knowledge system with agent research, claims ontology, visual assembly, and synthesis workspace

### User Requirements (Final)

> "A claim might have one source, multiple sources, or synthesis source. Always need to go back to source (image, archive, journal, book, page)."

> "PyKEEN for link prediction - claims about next logical claim/source"

> "We want an interconnected claims ontology"

> "Four-state curation: unreviewed → shortlisted → curated → rejected"

> "Flat claim model, but emergent categories: fact, analysis, interpretation, argument, historiography, theory"

> "Epistemology: what the claims mean. E.g., person A is a gold miner - all gold miners in archive suggests a pattern."

> "Mixed provenance: claims from humans, AI, or the source itself."

> "Multi-language: a claim might reference three documents in different languages (Spanish doc says X, Dutch doc says Y)."

> **NEW:** "We need research agents that can systematically search the internet, organize findings into projects/tasks/steps, save to the database — without filesystem or CLI access."

> **NEW:** "A visual layer where AI and user can assemble sources, claims, transcriptions in 3D space — see connections, make links, think spatially."

> **NEW:** "A synthesis layer where AI and user assemble texts, make connections between claims and ontologies."

## Knowledge Model Design

### The Seven-Layer Architecture

```
Layer 0: Agent Research (Pre-sources — Systematic Investigation)
├── Research Projects: Top-level research initiatives
│   └── "Southern Colombia Mining History 1880-1920"
├── Plans: Phased approach to project goals
│   └── "Phase 1: Archive search", "Phase 2: Geolocation mapping"
├── Tasks: Concrete units of work
│   └── "Search Colombian National Archive for Bogotá mining records"
├── Steps: Executable search actions
│   └── "Query: gold mining Bogotá 1890-1900", "Query: minas Colombia archivo"
├── Sources to Search: Curated search targets
│   ├── Archive URLs with authentication
│   ├── Search folders (e.g., ~/maps_southern_colombia)
│   ├── Database connections
│   └── API endpoints
├── Notes & Issues: Research observations
├── Checklists: Verification steps
├── Agent Tools (Sandboxed):
│   ├── Web search tool (curl-like HTTP requests)
│   ├── Browser automation (playwright/selenium sandbox)
│   ├── Document fetcher (respects robots.txt, rate limits)
│   └── Database writer (saves to Fichero, no filesystem escape)
└── Output: Sources discovered → Layer 1

Layer 1: Sources (Documents — Canonical Evidence)
├── Image (jpg, png, tiff)
├── PDF
├── Archive (folder structure)
├── Book
├── Page within PDF
├── Web pages captured by agents
├── Archive documents retrieved by agents
└── Metadata: language, path, source_url, provenance (agent_id, task_id, step_id)

Layer 2: Claims (Statements about entities, grounded in sources)
├── "Daniel Tubb worked as a miner in Colombia in 1959."
├── "Bogota is the capital of Colombia."
├── "The author references Bogota repeatedly on pages 3, 5, 7."
├── Source: document_id, page_label, segment_id
├── Confidence: 0.72 (human's certainty)
├── Prediction: {ai model, entities, uncertainty spans}
├── Claim type: fact|analysis|interpretation|argument
├── Curation: unreviewed|shortlisted|curated|rejected
├── Entity references: [ent-daniel, ent-bogota, ent-gold-miner]
└── Embedding: vector (stored in LanceDB for semantic search)

Layer 3: Ontology (Entity-centric view — the "what")
├── Entity: "Daniel Tubb"
│   ├── entity_type: person
│   ├── aliases: ["Daniel", "Dan", "Daniel Tubb"]
│   ├── extracted_from: [doc-1, doc-2, ...]
│   ├── embedding: vector (for entity similarity)
│   └── claims: [claim-1, claim-2, ..., claim-30]
│       └── "worked as gold miner in 1959" (source: doc-1, p.3)
│       └── "born in Medellín" (source: doc-2, p.1)
│       └── "moved to Bogota in 1960" (source: doc-3, p.5)
└── The ontology = Daniel's complete life story, stitched from all claims

Layer 4: Epistemology (Evidence relationships — the "how we know")
├── Claim relationships:
│   ├── "Claim A - supports - Claim B"
│   ├── "Claim C - contradicts - Claim D"
│   ├── "Claim E - refines - Claim F"
│   └── "Claim G - next_logical - Claim H" (PyKEEN prediction)
├── Evidence strength scoring
├── Confidence aggregation across sources
└── AI can generate relationships, user can curate certainty, both work

Layer 5: Hermeneutics (Interpretation & Meaning — the "what it means")
├── Claim Types (nature of the statement):
│   ├── fact: Documented observation from source
│   ├── analysis: Breaking down into components
│   ├── interpretation: Assigning meaning in context
│   ├── argument: Assertion requiring support
│   ├── historiography: Reflection on historical methods/sources
│   └── theory: Generalizing explanation across cases
├── Interpretive Frameworks:
│   ├── Historical context layers (time period, region, culture)
│   ├── Disciplinary lenses (anthropology, history, economics)
│   ├── Thematic frames (labor, migration, environment)
│   └── Methodological approaches (archival, oral history, ethnographic)
├── Meaning Extraction:
│   ├── Contextual significance (why this matters in its context)
│   ├── Pattern recognition (all gold miners suggest a labor system)
│   ├── Anomaly detection (this claim contradicts the pattern)
│   └── Cross-case synthesis (Colombia vs. Peru mining patterns)
├── Interpretive Acts:
│   ├── Reading: What the source explicitly states
│   ├── Translation: Across languages, across time
│   ├── Contextualization: Placing in historical/social setting
│   ├── Synthesis: Combining multiple claims into understanding
│   └── Critique: Questioning assumptions, power, silence
├── Hermeneutic Circle:
│   ├── Part ↔ Whole: Understanding details through context
│   ├── Text ↔ Reader: Meaning emerges in encounter
│   ├── Past ↔ Present: Historical distance enables understanding
│   └── Question ↔ Answer: Sources answer the questions we bring
└── AI + Human Interpretation:
    ├── AI suggests patterns and frameworks
    ├── User provides contextual knowledge and judgment
    ├── Both can annotate interpretations
    └── Disagreement is visible and discussable

Layer 6: Mind Palace (Synthesis Workspace — Visual + Text Assembly)
├── 3D Visual Assembly Space:
│   ├── Rooms: "Gold Mining Research Room", "Bogotá Geography Room"
│   ├── Spatial Nodes: Sources, claims, transcriptions placed in 3D
│   │   ├── Document proxies (cards/thumbnails)
│   │   ├── Claim cards with text previews
│   │   ├── Transcription panels
│   │   └── Entity "bio" panels
│   ├── Connections: Visual links between nodes
│   │   ├── Evidentiary: source → claim
│   │   ├── Semantic: claim ↔ claim
│   │   ├── Ontological: entity → claims
│   │   └── Hermeneutic: interpretation → sources
│   ├── Stacks and Clusters: Grouped materials
│   ├── Camera and Navigation (zoom, focus, return bookmark)
│   └── AI + Human Co-arrangement (suggest, drag, connect, log)
├── Text Assembly Surface:
│   ├── Native Notes: User-authored, AI-authored, hypotheses, synthesis
│   ├── Drag claims into narrative flow
│   ├── Arrange evidence beside assertions
│   ├── Build arguments with visible claim connections
│   ├── Write prose with inline source citations
│   └── Tinderbox bidirectional integration
├── Hermeneutic Tools in Space:
│   ├── Apply interpretive framework to selection
│   ├── Compare across contexts (split view)
│   ├── Trace hermeneutic circle (part ↔ whole navigation)
│   └── Surface AI interpretation suggestions
├── Link Types:
│   ├── Evidentiary: derived_from, quotes, summarizes, contrasts_with
│   ├── Semantic: related_to, supports, challenges, extends
│   ├── Hermeneutic: interprets, contextualizes, synthesizes, critiques
│   └── Organizational: appears_in, stacked_with, alias_of
├── MCP Tools for Spatial + Text Manipulation:
│   ├── create_room, place_node, move_node, stack_nodes, link_nodes
│   ├── focus_node, capture_viewport, read_scene_summary
│   ├── create_note, update_note, merge_notes, annotate_note
│   ├── apply_framework, suggest_interpretation, compare_contexts
│   └── read_hermeneutic_state, export_to_tinderbox
└── Lifecycle: draft → active → surfaced → accepted → archived/discarded
```

## Key Distinctions

| Layer | Concept | What it IS | How it's used |
|-------|---------|------------|---------------|
| **0** | Research Task | Systematic search with sandboxed tools | Agents discover sources |
| **1** | Source | Original document/image/archive/web | Canonical evidence |
| **2** | Claim | Single statement grounded in source(s) | Atomic knowledge unit |
| **3** | Ontology | All claims about ONE entity | Entity "bio" |
| **4** | Epistemology | Evidence relationships | How we know |
| **5** | Hermeneutics | Interpretation & meaning-making | What it means |
| **6** | Mind Palace | Visual + text assembly workspace | Synthesis & writing |

### The Three Meaning Layers (Epistemology → Hermeneutics → Mind Palace)

**Epistemology** asks: *How do we know this?*
- What evidence supports this claim?
- Does it contradict other claims?
- How confident should we be?

**Hermeneutics** asks: *What does this mean?*
- How do we interpret this in context?
- What patterns emerge?
- What frameworks help us understand?

**Mind Palace** asks: *How do we assemble this into understanding?*
- How do we arrange materials to see connections?
- How do we write this into narrative?
- How do we synthesize across sources?

## Implementation Plan

### Phase 0: Layer 0 — Agent Research Infrastructure

**New File:** `fichero-engine/src/fichero/research_models.py`

```python
class ResearchProject(BaseModel):
    """Top-level research initiative."""
    id: str
    name: str
    description: str
    status: Literal["active", "paused", "completed", "archived"]
    created_at: datetime
    updated_at: datetime
    metadata: dict = Field(default_factory=dict)

class ResearchPlan(BaseModel):
    """Phased approach to project goals."""
    id: str
    project_id: str
    name: str
    description: str
    phase_number: int
    status: Literal["pending", "in_progress", "completed"]

class ResearchTask(BaseModel):
    """Concrete unit of work."""
    id: str
    plan_id: str
    name: str
    description: str
    status: Literal["todo", "in_progress", "completed", "blocked"]
    assigned_agent: str | None = None
    priority: int = 0

class ResearchStep(BaseModel):
    """Executable search action."""
    id: str
    task_id: str
    action_type: Literal["web_search", "archive_query", "browser_navigate", "document_fetch", "note_create"]
    parameters: dict  # Tool-specific parameters
    status: Literal["pending", "running", "completed", "failed"]
    result: dict | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

class SearchSource(BaseModel):
    """Curated search target configuration."""
    id: str
    project_id: str
    source_type: Literal["url", "folder", "database", "api"]
    name: str
    config: dict  # {url, auth_method, headers} or {folder_path} etc.
    search_terms: list[str] = Field(default_factory=list)

class ResearchNote(BaseModel):
    """Research observation or finding."""
    id: str
    project_id: str
    step_id: str | None = None
    content: str
    note_type: Literal["observation", "finding", "issue", "question"]
    linked_sources: list[str] = Field(default_factory=list)

class ResearchChecklist(BaseModel):
    """Verification steps for systematic research."""
    id: str
    task_id: str
    items: list[dict]  # [{description, checked, evidence}]
```

**New File:** `fichero-engine/src/fichero/api/routes/research_agents.py`

Sandboxed agent tools (no filesystem/CLI access):

```python
@router.post("/research/projects")
async def create_project(project: ResearchProject) -> ResearchProject

@router.get("/research/projects/{project_id}/plans")
async def list_plans(project_id: str) -> list[ResearchPlan]

@router.post("/research/tasks/{task_id}/steps")
async def create_step(step: ResearchStep) -> ResearchStep

# Sandboxed tool execution
@router.post("/research/tools/web-search")
async def web_search_tool(
    query: str,
    sources: list[str],  # URLs from SearchSource
    max_results: int = 10
) -> list[WebSearchResult]

@router.post("/research/tools/browser-navigate")
async def browser_navigate_tool(
    url: str,
    wait_for: str | None = None,  # CSS selector
    timeout: int = 30
) -> BrowserPage  # HTML content, screenshot, links

@router.post("/research/tools/document-fetch")
async def document_fetch_tool(
    url: str,
    save_to_fichero: bool = True
) -> Document  # Creates Layer 1 Source

@router.post("/research/tools/save-to-database")
async def save_research_artifact(
    artifact_type: Literal["note", "claim", "source"],
    content: dict
) -> dict  # Saved record with ID
```

**Security Model:**
- Agents can only write to Fichero database, never filesystem
- Web requests go through sandboxed HTTP client with rate limiting
- Browser automation runs in isolated process
- All actions logged with agent_id attribution

---

### Phase 1: Layers 1-4 — Knowledge Graph Core

#### 1. Enhanced Models (knowledge_models.py)

**File:** `fichero-engine/src/fichero/knowledge_models.py`

Add new enums:

```python
class SourceType(str, Enum):
    document = "document"
    claim = "claim"
    multiple = "multiple"
    synthesis = "synthesis"

class ClaimType(str, Enum):
    fact = "fact"
    analysis = "analysis"
    interpretation = "interpretation"
    argument = "argument"
    historiography = "historiography"
    theory = "theory"

class EpistemicStatus(str, Enum):
    tentative = "tentative"
    confirmed = "confirmed"
    rejected = "rejected"
```

Add Prediction models:

```python
class PredictionEntity(BaseModel):
    text: str
    type: str  # person, location, organization, date, etc.
    start: int
    end: int

class PredictionUncertaintySpan(BaseModel):
    start: int
    end: int
    reason: str

class PredictionLink(BaseModel):
    target_claim_id: str
    link_type: str  # next_logical, supports, contradicts, refines

class PredictionMetadata(BaseModel):
    confidence: float
    model: str
    entities: list[PredictionEntity]
    uncertainty_spans: list[PredictionUncertaintySpan]
    predicted_links: list[PredictionLink] | None = None
```

Update `KnowledgeClaim`:

```python
class KnowledgeClaim(BaseModel):
    # ... existing fields ...
    source_type: SourceType = SourceType.document
    source_ids: list[str] = Field(default_factory=list)
    source_page_labels: list[str] = Field(default_factory=list)
    source_languages: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    prediction: PredictionMetadata | None = None
    claim_type: ClaimType | None = None
    epistemic_status: EpistemicStatus | None = None
```

### 2. New Endpoints (knowledge_graph.py)

**File:** `fichero-engine/src/fichero/api/routes/knowledge_graph.py`

**Design Principle:** SwiftUI should have simple, focused endpoints. Three separate endpoints for claims (simpler than one endpoint with many filters).

#### A. `GET /api/knowledge-graph/claims`

**Purpose:** List claims with basic filters (existing endpoint extended)

**Query params:**
- `q`: Text search
- `entity_id`: Filter by referenced entity
- `curation_state`: Filter by status
- `scope_type`: `library|folder|document`
- `target_id`: Scope ID
- `page`, `limit`: Pagination

#### B. `GET /api/knowledge-graph/claims/filtered`

**Purpose:** Advanced claim search with all new filter types

**Query params:**
- `q`: Text search
- `claim_type`: Filter by type (fact|analysis|interpretation|argument|historiography|theory)
- `curation_state`: Filter by status (unreviewed|shortlisted|curated|rejected)
- `epistemic_status`: Filter by epistemic status (tentative|confirmed|rejected)
- `entity_id`: Filter by referenced entity
- `source_language`: Filter by source language (e.g., "es", "nl", "en")
- `source_type`: Filter by source type (document|claim|multiple|synthesis)
- `scope_type`: `library|folder|document`
- `target_id`: Scope ID
- `page`, `limit`: Pagination

#### C. `GET /api/knowledge-graph/claims/{claim_id}/sources`

**Purpose:** Full source reference resolution for a claim

**Response:** List of resolved source objects with language info

#### D. `GET /api/knowledge-graph/claims/{claim_id}/ontology`

**Purpose:** Get ALL claims about entities referenced by this claim (the ontology view)

**Response:** List of claims that share entities with this claim

#### E. `GET /api/knowledge-graph/predictions`

**Purpose:** List all AI predictions (for review queue)

**Query params:**
- `claim_id`: Filter by source claim
- `model`: Filter by prediction model
- `link_type`: Filter by link type (next_logical|supports|contradicts|refines)
- `page`, `limit`: Pagination

#### F. `POST /api/knowledge-graph/predictions`

**Purpose:** Create a new prediction (from AI or heuristics)

**Body:**
```json
{
  "claim_id": "claim-123",
  "predicted_claim_text": "Daniel moved to Bogota in 1960",
  "link_type": "next_logical",
  "confidence": 0.85,
  "model_name": "heuristic-v1"
}
```

#### G. `POST /api/knowledge-graph/predictions/{prediction_id}/apply`

**Purpose:** Apply a prediction to create a real claim

**Response:** The newly created claim

### 3. Helper Functions

**File:** `fichero-engine/src/fichero/api/routes/knowledge_graph.py`

```python
def _resolve_sources(db: Database, sources: list[str]) -> list[dict]:
    """Resolve source IDs to full metadata with language info."""
    result = []
    for source_id in sources:
        doc = db.get(Document, source_id)
        if doc:
            result.append({
                "source_id": source_id,
                "source_type": "document",
                "name": doc.name,
                "path": doc.path,
                "doc_type": doc.doc_type.value,
                "language": doc.metadata.get("language"),
            })
            continue
        claim = db.get(KnowledgeClaim, source_id)
        if claim:
            result.append({
                "source_id": source_id,
                "source_type": "claim",
                "text_preview": claim.text[:100],
                "claim_type": claim.claim_type,
            })
    return result


def _migrate_claim_to_multi_source(claim: KnowledgeClaim) -> KnowledgeClaim:
    """One-time migration: convert legacy single-source claim to multi-source."""
    if claim.source_type != SourceType.document or claim.source_ids:
        return claim  # Already migrated
    
    claim.source_ids = [claim.source_document_id]
    claim.source_page_labels = [claim.source_page_label] if claim.source_page_label else []
    claim.source_languages = [claim.language] if claim.language else []
    return claim
```

### 4. Embeddings Integration (LanceDB)

**File:** `fichero-engine/src/fichero/db.py` (existing infrastructure)

**Existing Embedding Infrastructure:**
- `db.embed(doc)` - Create embedding for a document/claim
- `db.search_similar(query_vector, limit)` - Vector similarity search
- `db.search(query, search_type="hybrid")` - Hybrid semantic + full-text search
- LanceDB storage at `~/Library/Application Support/com.tubb.fichero/vectors/`
- Default model: `intfloat/multilingual-e5-large` (Spanish + English support)

**Knowledge Graph Embedding Strategy:**

#### A. Claim Embeddings

```python
# When creating a claim, auto-embed its text
@router.post("/claims")
async def create_claim(claim_data: KnowledgeClaim, db: Database = Depends(get_library_database)):
    # Save claim
    db.save(claim_data)
    
    # Create embedding for semantic search
    db.embed(claim_data)  # Uses claim.text for embedding
    
    return claim_data
```

**Embedding table structure in LanceDB:**
```python
# Table: kg_claims
{
    "id": str,              # Claim ID
    "vector": list[float],  # 768-dim embedding (multilingual-e5-large)
    "text": str,            # Claim text (first 500 chars)
    "claim_type": str,      # fact|analysis|interpretation|argument|historiography|theory
    "entity_ids": list[str], # Referenced entities
    "source_languages": list[str], # Source document languages
    "metadata": dict        # Additional metadata
}
```

#### B. Entity Embeddings

```python
# When creating an entity, embed its canonical name + aliases
@router.post("/entities")
async def create_entity(entity_data: KnowledgeEntity, db: Database = Depends(get_library_database)):
    db.save(entity_data)
    
    # Embed entity description (canonical name + aliases + description)
    embed_text = f"{entity_data.canonical_name}: {', '.join(entity_data.aliases)}"
    if entity_data.description:
        embed_text += f". {entity_data.description}"
    
    # Store entity embedding separately for entity-centric search
    db.save_embedding(entity_data, vector, embed_text, table_name="kg_entities")
    
    return entity_data
```

#### C. Semantic Search Endpoints

**Add to `knowledge_graph.py`:**

```python
@router.get("/claims/semantic")
async def semantic_search_claims(
    query: str,
    limit: int = 10,
    entity_id: str | None = None,
    claim_type: ClaimType | None = None,
    db: Database = Depends(get_library_database)
) -> list[SearchResult]:
    """
    Semantic search for claims using vector similarity.
    
    Finds claims similar to the query text, optionally filtered by entity or type.
    """
    # Use existing db.search() with semantic mode
    results, _, _ = db.search(
        query=query,
        limit=limit,
        search_type="semantic",
        filters={"entity_id": entity_id, "claim_type": claim_type} if any([entity_id, claim_type]) else None
    )
    return results


@router.get("/entities/semantic")
async def semantic_search_entities(
    query: str,
    limit: int = 10,
    entity_type: EntityType | None = None,
    db: Database = Depends(get_library_database)
) -> list[KnowledgeEntity]:
    """
    Semantic search for entities using vector similarity.
    
    Finds entities similar to the query text.
    """
    results, _, _ = db.search(
        query=query,
        limit=limit,
        search_type="semantic",
        filters={"entity_type": entity_type.value} if entity_type else None
    )
    # Convert SearchResult to KnowledgeEntity
    return [db.get(KnowledgeEntity, r.document_id) for r in results if r.document_id]


@router.get("/claims/{claim_id}/similar")
async def similar_claims(
    claim_id: str,
    limit: int = 10,
    db: Database = Depends(get_library_database)
) -> list[SearchResult]:
    """
    Find claims similar to a given claim using vector similarity.
    
    Useful for discovering related claims that don't share entities.
    """
    # Get the claim's embedding
    claim = db.get(KnowledgeClaim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    
    # Search for similar claims
    results, _, _ = db.search_similar(
        query_vector=claim.embedding,  # Would need to store/retrieve embedding
        limit=limit + 1,  # +1 to exclude the source claim itself
        model=KnowledgeClaim
    )
    
    # Exclude the source claim
    return [r for r in results if r["id"] != claim_id][:limit]
```

### 5. PyKEEN Integration Strategy (Phased)

**★ Insight ─────────────────────────────────────**
**PyKEEN + Embeddings Synergy:** PyKEEN can leverage LanceDB embeddings for link prediction in two ways:
1. **Entity-based predictions**: Use entity embedding similarity to predict `supports`/`contradicts` links
2. **Claim-based predictions**: Use claim embedding similarity to predict `next_logical` claims

Example: If Claim A (about "Daniel as miner") and Claim B (about "Daniel moving to Bogota") have similar embeddings and share the "Daniel" entity, PyKEEN can learn this pattern and predict similar "life event sequences" for other people in the archive.
`─────────────────────────────────────────────────`

**Phase 1: Prediction Storage (Immediate)**
- Add `KnowledgePrediction` model
- Add prediction CRUD endpoints
- Add prediction review queue UI
- Simple heuristic predictions using embedding similarity (no PyKEEN yet)

**Phase 2: Heuristic Predictions (Embedding-Based)**
```python
# Heuristic: Claims with similar embeddings + shared entities likely have relationships
@router.post("/predictions/generate/heuristic")
async def generate_heuristic_predictions(
    claim_id: str,
    db: Database = Depends(get_library_database)
) -> list[KnowledgePrediction]:
    """Generate predictions using embedding similarity heuristics."""
    claim = db.get(KnowledgeClaim, claim_id)
    
    # Find semantically similar claims
    similar_claims = db.search_similar(
        query_vector=claim.embedding,
        limit=20
    )
    
    predictions = []
    for similar in similar_claims:
        if similar["id"] == claim_id:
            continue
        
        # Check if they share entities
        similar_claim = db.get(KnowledgeClaim, similar["id"])
        shared_entities = set(claim.entity_ids) & set(similar_claim.entity_ids)
        
        if shared_entities:
            # High confidence: similar embeddings + shared entities
            link_type = "supports"  # Default heuristic
            confidence = 0.7 + (len(shared_entities) * 0.1)  # Boost for more shared entities
            
            predictions.append(KnowledgePrediction(
                claim_id=claim_id,
                predicted_claim_text=similar_claim.text,
                link_type=link_type,
                confidence=min(confidence, 0.95),
                model_name="heuristic-embedding-v1"
            ))
    
    return predictions
```

**Phase 3: PyKEEN Integration (ML-Based)**
- Install PyKEEN: `pip install pykeen`
- Train PyKEEN models on claim graph (entities as nodes, claims as edges)
- Use LanceDB embeddings as node features for PyKEEN
- Generate predictions from trained models
- Store PyKEEN predictions alongside heuristics
- A/B test PyKEEN vs heuristics

**PyKEEN Model Configuration:**
```python
from pykeen.pipeline import pipeline

# Train link prediction model
result = pipeline(
    dataset='kg_claims_graph',  # Custom dataset from LanceDB
    model='TransE',  # Or RotatE, DistMult for different relation patterns
    model_kwargs=dict(embedding_dim=256),
    training_kwargs=dict(num_epochs=100),
    node_features=db.load_embeddings_from_lance("kg_claims"),  # Use LanceDB vectors
)
```

**Phase 4: Prediction Application**
- UI for reviewing and applying predictions
- Batch apply predictions
- Feedback loop (accepted/rejected predictions improve heuristics)

### 6. Tests

### 5. Tests

**File:** `fichero-engine/tests/unit/test_knowledge_graph_api.py`

**Core functionality tests:**
- `test_knowledge_graph_claim_create_with_multiple_sources()` - claim with 3 documents
- `test_knowledge_graph_claim_create_with_prediction_metadata()` - AI-generated claim
- `test_knowledge_graph_claim_update_source_type()` - change from document to synthesis

**Endpoint tests (3 endpoint approach):**
- `test_knowledge_graph_claims_basic_filter()` - existing /claims endpoint
- `test_knowledge_graph_claims_filtered_advanced()` - /claims/filtered with all filters
- `test_knowledge_graph_claims_filtered_by_claim_type()`
- `test_knowledge_graph_claims_filtered_by_epistemic_status()`
- `test_knowledge_graph_claims_filtered_by_source_language_spanish()`
- `test_knowledge_graph_claims_filtered_by_source_language_dutch()`
- `test_knowledge_graph_claims_filtered_pagination()`
- `test_knowledge_graph_claim_sources_resolution()` - /claims/{id}/sources
- `test_knowledge_graph_claim_ontology_view()` - /claims/{id}/ontology

**Source resolution tests:**
- `test_knowledge_graph_resolve_document_source_with_language()`
- `test_knowledge_graph_resolve_claim_source()`
- `test_knowledge_graph_resolve_mixed_source_types()`

**Prediction tests (Phase 1):**
- `test_knowledge_graph_prediction_create()`
- `test_knowledge_graph_prediction_list()`
- `test_knowledge_graph_prediction_apply_creates_claim()`
- `test_knowledge_graph_prediction_list_by_claim()`
- `test_knowledge_graph_prediction_list_by_link_type()`

**Migration tests:**
- `test_knowledge_graph_legacy_claim_migration()` - single source → multi-source
- `test_knowledge_graph_migration_idempotent()` - running twice doesn't break

**Edge case tests:**
- `test_knowledge_graph_claim_with_synthesis_source_type()`
- `test_knowledge_graph_claim_with_empty_source_ids()`
- `test_knowledge_graph_filter_by_nonexistent_source_language()`
- `test_knowledge_graph_sources_for_claim_with_no_sources()`

---

### Phase 3: Layer 5 — Hermeneutics (Interpretation & Meaning)

**New File:** `fichero-engine/src/fichero/hermeneutics_models.py`

```python
class InterpretiveFramework(BaseModel):
    """Lens for understanding claims (historical, disciplinary, thematic)."""
    id: str
    name: str  # "Economic History", "Labor Studies", "Environmental Justice"
    framework_type: Literal["historical", "disciplinary", "thematic", "methodological"]
    description: str
    context_fields: dict  # {time_period, region, culture, etc.}
    created_by: str  # user_id or agent_id

class HermeneuticContext(BaseModel):
    """Context applied to a claim for interpretation."""
    id: str
    claim_id: str
    framework_id: str
    contextual_notes: str
    significance_score: float  # 0-1, how significant in this context
    applied_at: datetime
    applied_by: str

class PatternInstance(BaseModel):
    """Recognized pattern across multiple claims."""
    id: str
    pattern_type: Literal["repetition", "anomaly", "trend", "correlation", "contrast"]
    name: str
    description: str
    claim_ids: list[str]
    confidence: float
    detected_by: str  # agent_id or user_id
    detection_method: Literal["ai_suggestion", "user_observation", "algorithmic"]

class InterpretiveAct(BaseModel):
    """Specific act of interpretation (reading, translating, contextualizing, etc.)."""
    id: str
    act_type: Literal["reading", "translation", "contextualization", "synthesis", "critique"]
    source_claim_ids: list[str]
    resulting_claim_id: str | None  # May create a new interpretation claim
    notes: str
    interpreter_id: str  # user or agent
    created_at: datetime

class HermeneuticCircleState(BaseModel):
    """Tracks part-whole navigation during interpretation."""
    id: str
    user_id: str
    current_focus: Literal["part", "whole"]
    part_claim_id: str | None
    whole_context: str | None  # e.g., entity_id, theme
    navigation_history: list[dict]
```

**New File:** `fichero-engine/src/fichero/api/routes/hermeneutics.py`

```python
@router.post("/hermeneutics/frameworks")
async def create_framework(framework: InterpretiveFramework) -> InterpretiveFramework

@router.get("/hermeneutics/frameworks")
async def list_frameworks(
    framework_type: str | None = None
) -> list[InterpretiveFramework]

@router.post("/hermeneutics/claims/{claim_id}/context")
async def apply_context(
    claim_id: str,
    context: HermeneuticContext
) -> HermeneuticContext

@router.get("/hermeneutics/claims/{claim_id}/interpretations")
async def get_claim_interpretations(claim_id: str) -> list[HermeneuticContext]

@router.post("/hermeneutics/patterns")
async def create_pattern(pattern: PatternInstance) -> PatternInstance

@router.get("/hermeneutics/patterns")
async def find_patterns(
    entity_id: str | None = None,
    pattern_type: str | None = None
) -> list[PatternInstance]

@router.post("/hermeneutics/interpret")
async def interpret_claims(
    claim_ids: list[str],
    framework_id: str,
    act_type: str
) -> InterpretiveAct

@router.post("/hermeneutics/suggest-interpretation")
async def ai_suggest_interpretation(
    claim_id: str,
    surrounding_context: str | None = None
) -> dict:  # AI-generated interpretation suggestions

@router.get("/hermeneutics/circle-state/{user_id}")
async def get_hermeneutic_circle_state(user_id: str) -> HermeneuticCircleState

@router.post("/hermeneutics/circle-state/{user_id}/navigate")
async def navigate_part_whole(
    user_id: str,
    direction: Literal["part", "whole"],
    target_id: str
) -> HermeneuticCircleState
```

---

### Phase 4: Layer 6 — Mind Palace (Visual + Text Assembly)

**New File:** `fichero-engine/src/fichero/spatial_models.py`

```python
class SpatialRoom(BaseModel):
    """3D space for organizing materials."""
    id: str
    name: str
    description: str
    room_type: Literal["research", "synthesis", "presentation"]
    owner_id: str
    created_at: datetime

class SpatialNode(BaseModel):
    """Item placed in 3D space (source, claim, note, entity bio)."""
    id: str
    room_id: str
    node_type: Literal["source", "claim", "note", "entity", "transcription"]
    source_id: str  # ID of the underlying item
    position_x: float
    position_y: float
    position_z: float
    rotation_x: float = 0.0
    rotation_y: float = 0.0
    rotation_z: float = 0.0
    scale: float = 1.0
    created_by: str
    created_at: datetime
    updated_at: datetime

class SpatialConnection(BaseModel):
    """Visual link between nodes."""
    id: str
    room_id: str
    source_node_id: str
    target_node_id: str
    connection_type: Literal["evidentiary", "semantic", "ontological", "hermeneutic", "user_drawn"]
    link_subtype: str  # e.g., "supports", "derived_from", "interprets"
    created_by: str

class SpatialStack(BaseModel):
    """Grouped nodes."""
    id: str
    room_id: str
    name: str
    node_ids: list[str]
    position_x: float
    position_y: float
    position_z: float

class NativeNote(BaseModel):
    """First-class text note in Mind Palace."""
    id: str
    content: str
    note_type: Literal["user", "ai_workspace", "ai_hypothesis", "ai_summary", "ai_relation", "shared"]
    author_type: Literal["user", "ai", "agent_team"]
    author_id: str
    status: Literal["draft", "active", "surfaced", "accepted", "archived", "discarded"]
    linked_claim_ids: list[str] = Field(default_factory=list)
    linked_source_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

class SpatialViewport(BaseModel):
    """Camera and focus state."""
    id: str
    room_id: str
    user_id: str
    camera_x: float
    camera_y: float
    camera_z: float
    focus_node_id: str | None
    zoom_level: float
    bookmark_name: str | None
```

**New File:** `fichero-engine/src/fichero/api/routes/mind_palace.py`

```python
# Room Management
@router.post("/mind-palace/rooms")
async def create_room(room: SpatialRoom) -> SpatialRoom

@router.get("/mind-palace/rooms/{room_id}")
async def get_room(room_id: str) -> SpatialRoom

# Node Management
@router.post("/mind-palace/nodes")
async def place_node(node: SpatialNode) -> SpatialNode

@router.patch("/mind-palace/nodes/{node_id}")
async def move_node(
    node_id: str,
    position_x: float,
    position_y: float,
    position_z: float
) -> SpatialNode

@router.delete("/mind-palace/nodes/{node_id}")
async def remove_node(node_id: str)

# Connection Management
@router.post("/mind-palace/connections")
async def create_connection(connection: SpatialConnection) -> SpatialConnection

@router.delete("/mind-palace/connections/{connection_id}")
async def remove_connection(connection_id: str)

# Stack Management
@router.post("/mind-palace/stacks")
async def create_stack(stack: SpatialStack) -> SpatialStack

@router.post("/mind-palace/stacks/{stack_id}/nodes/{node_id}")
async def add_to_stack(stack_id: str, node_id: str) -> SpatialStack

# Note Management
@router.post("/mind-palace/notes")
async def create_note(note: NativeNote) -> NativeNote

@router.patch("/mind-palace/notes/{note_id}")
async def update_note(note_id: str, content: str) -> NativeNote

# Navigation
@router.get("/mind-palace/rooms/{room_id}/scene")
async def get_scene_summary(room_id: str) -> dict:  # Compact scene state

@router.get("/mind-palace/rooms/{room_id}/viewport/{user_id}")
async def get_viewport(room_id: str, user_id: str) -> SpatialViewport

@router.post("/mind-palace/rooms/{room_id}/focus")
async def focus_node(
    room_id: str,
    node_id: str,
    user_id: str
) -> SpatialViewport

@router.post("/mind-palace/rooms/{room_id}/capture")
async def capture_viewport(
    room_id: str,
    region: Literal["full", "focused", "selection"],
    selection_ids: list[str] | None = None
) -> bytes  # Image data

# AI-assisted arrangement
@router.post("/mind-palace/rooms/{room_id}/suggest-arrangement")
async def ai_suggest_arrangement(
    room_id: str,
    node_ids: list[str],
    arrangement_type: Literal["semantic", "chronological", "thematic"]
) -> list[SpatialNode]:  # Proposed positions

# Tinderbox Integration
@router.post("/mind-palace/export/tinderbox")
async def export_to_tinderbox(
    room_id: str,
    tinderbox_note_id: str | None = None
) -> dict  # Reference to created/updated Tinderbox note

@router.post("/mind-palace/import/tinderbox")
async def import_from_tinderbox(
    tinderbox_note_id: str
) -> list[NativeNote]
```

---

### Phase 5: MCP Tools for Agent Control

**File:** `fichero-engine/src/fichero/mcp_server.py` (extension)

```python
# Layer 0: Research Agent Tools
class ResearchTools:
    @mcp.tool()
    async def create_research_project(name: str, description: str) -> str:
        """Create a new research project."""
        
    @mcp.tool()
    async def create_task(project_id: str, name: str, description: str) -> str:
        """Create a task within a project."""
        
    @mcp.tool()
    async def execute_web_search(query: str, sources: list[str]) -> list[dict]:
        """Search the web using configured sources."""
        
    @mcp.tool()
    async def navigate_browser(url: str) -> dict:
        """Navigate to URL and return page content."""
        
    @mcp.tool()
    async def save_research_note(project_id: str, content: str) -> str:
        """Save a research observation."""

# Layer 5: Hermeneutics Tools
class HermeneuticsTools:
    @mcp.tool()
    async def apply_framework(claim_id: str, framework_name: str) -> dict:
        """Apply an interpretive framework to a claim."""
        
    @mcp.tool()
    async def find_patterns(entity_id: str) -> list[dict]:
        """Find patterns among claims about an entity."""
        
    @mcp.tool()
    async def suggest_interpretation(claim_id: str) -> dict:
        """AI suggests interpretive angles."""
        
    @mcp.tool()
    async def navigate_part_whole(direction: str, target_id: str) -> dict:
        """Navigate the hermeneutic circle."""

# Layer 6: Mind Palace Tools
class MindPalaceTools:
    @mcp.tool()
    async def create_room(name: str, description: str) -> str:
        """Create a 3D workspace room."""
        
    @mcp.tool()
    async def place_node(room_id: str, item_id: str, item_type: str, x: float, y: float, z: float) -> str:
        """Place an item in 3D space."""
        
    @mcp.tool()
    async def move_node(node_id: str, x: float, y: float, z: float) -> dict:
        """Move a node to new position."""
        
    @mcp.tool()
    async def link_nodes(source_id: str, target_id: str, link_type: str) -> str:
        """Create a visual connection."""
        
    @mcp.tool()
    async def focus_node(node_id: str) -> dict:
        """Focus camera on a node."""
        
    @mcp.tool()
    async def read_scene(room_id: str) -> dict:
        """Get compact scene summary."""
        
    @mcp.tool()
    async def create_note(content: str, note_type: str) -> str:
        """Create a text note."""
        
    @mcp.tool()
    async def arrange_suggestion(room_id: str, node_ids: list[str]) -> list[dict]:
        """AI suggests spatial arrangement."""
```

---

### Phase 6: SwiftUI Implementation

**SwiftUI Components:**

```
fichero/
├── Views/
│   ├── Research/           # Layer 0: Research Agent UI
│   │   ├── ResearchProjectListView.swift
│   │   ├── ResearchTaskView.swift
│   │   ├── ResearchStepEditor.swift
│   │   └── AgentToolPanel.swift
│   ├── KnowledgeGraph/     # Layers 1-4
│   │   ├── ClaimInspectorView.swift
│   │   ├── OntologyBrowserView.swift
│   │   └── EpistemologyGraphView.swift
│   ├── Hermeneutics/       # Layer 5
│   │   ├── FrameworkSelectorView.swift
│   │   ├── InterpretationPanelView.swift
│   │   ├── PatternBrowserView.swift
│   │   └── PartWholeNavigatorView.swift
│   └── MindPalace/         # Layer 6
│       ├── MindPalaceView.swift           # Main 3D view
│       ├── RealityKitSceneView.swift      # Metal/RealityKit renderer
│       ├── NodeInteractionView.swift      # Drag, connect, stack
│       ├── NoteEditorView.swift          # Text assembly
│       ├── ConnectionPaletteView.swift   # Link type selector
│       ├── FrameworkHUDView.swift        # Hermeneutic overlay
│       └── ViewportControlsView.swift     # Camera, focus, bookmark
```

---

### 6. OpenAPI Schema & Swift Integration

**Step 1: Update OpenAPI Schema**

Update `fichero-engine/tests/contracts/openapi.json` with:
- `KnowledgePrediction` model
- `PredictionMetadata` model
- `PredictionEntity` model
- `PredictionUncertaintySpan` model
- `PredictionLink` model
- `SourceType` enum
- `ClaimType` enum
- `EpistemicStatus` enum

**Step 2: Regenerate Swift Client**

```bash
cd fichero-engine
./scripts/sync_openapi_schema.sh

# Verify new types exported:
grep -A5 "SourceType" fichero-engine/tests/contracts/openapi.json
grep -A10 "PredictionMetadata" fichero-engine/tests/contracts/openapi.json

# Validate Swift compiles:
cd ../fichero
xcodebuild -scheme fichero -destination 'platform=macOS' build
```

**Step 3: Add Swift API Endpoints**

**File:** `fichero/fichero/Services/APIEndpoints.swift`

Add to existing `APIEndpoints` enum:

```swift
enum KnowledgeGraphEndpoints {
    static let base = "/knowledge-graph"
    
    // Entities
    static let entities = "/knowledge-graph/entities"
    static func entity(_ id: String) -> String { "/knowledge-graph/entities/\(id)" }
    
    // Claims - 3 endpoints for simplicity
    static let claims = "/knowledge-graph/claims"
    static let claimsFiltered = "/knowledge-graph/claims/filtered"
    static func claim(_ id: String) -> String { "/knowledge-graph/claims/\(id)" }
    static func claimSources(_ id: String) -> String { "/knowledge-graph/claims/\(id)/sources" }
    static func claimOntology(_ id: String) -> String { "/knowledge-graph/claims/\(id)/ontology" }
    
    // Predictions
    static let predictions = "/knowledge-graph/predictions"
    static func prediction(_ id: String) -> String { "/knowledge-graph/predictions/\(id)" }
    static func predictionApply(_ id: String) -> String { "/knowledge-graph/predictions/\(id)/apply" }
    
    // Claim Links
    static func claimLinks(_ claimId: String) -> String { "/knowledge-graph/claims/\(claimId)/links" }
    
    // Inclusion
    static let inclusion = "/knowledge-graph/inclusion"
    
    // Overview
    static let overview = "/knowledge-graph/overview"
}
```

**Swift Consumption Pattern:**

SwiftUI uses `APIClient` same as other features. Example:

```swift
// Get claims for entity
let claims = try await apiClient.get(
    KnowledgeGraphEndpoints.claimsFiltered,
    query: ["entity_id": entityId, "claim_type": "fact"]
)

// Get sources for claim
let sources = try await apiClient.get(
    KnowledgeGraphEndpoints.claimSources(claimId)
)

// Get ontology view
let ontologyClaims = try await apiClient.get(
    KnowledgeGraphEndpoints.claimOntology(claimId)
)
```

## Implementation Order

**Principle:** Layer-by-layer implementation. Each layer is fully integrated (models → routes → MCP → SwiftUI → tests) before proceeding to the next. PyKEEN and RealityKit are included, not deferred.

---

### Phase 1: Layers 1-4 — Knowledge Graph Core (Foundation)

**Goal:** Multi-source claims, entity ontology, epistemology relationships, PyKEEN link prediction.

**1. Models** (`knowledge_models.py`)
   - Add `SourceType`, `ClaimType`, `EpistemicStatus` enums
   - Add prediction metadata models (`PredictionEntity`, `PredictionUncertaintySpan`, `PredictionLink`, `PredictionMetadata`)
   - Update `KnowledgeClaim` with multi-source support
   - Add `KnowledgePrediction` model

**2. Migration**
   - One-time script: migrate legacy single-source claims to multi-source format

**3. Backend Routes** (`knowledge_graph.py`)
   - Update claims filtering (`GET /claims`, `GET /claims/filtered`)
   - Add source resolution (`GET /claims/{id}/sources`)
   - Add ontology view (`GET /claims/{id}/ontology`)
   - Add prediction CRUD (`GET|POST /predictions`, `POST /predictions/{id}/apply`)

**4. PyKEEN Integration** (NOT deferred)
   - Install: `pip install pykeen`
   - Add heuristic prediction endpoint (`POST /predictions/generate/heuristic`)
   - Train PyKEEN on claim graph
   - Add model inference endpoint (`POST /predictions/generate/pykeen`)

**5. Embeddings Integration** (`db.py`)
   - Claim embeddings table in LanceDB
   - Entity embeddings table
   - Semantic search endpoints (`GET /claims/semantic`, `GET /entities/semantic`)

**6. MCP Tools**
   - `create_claim`, `update_claim`, `list_claims`
   - `resolve_sources`, `view_ontology`
   - `create_prediction`, `apply_prediction`
   - `generate_heuristic_predictions`, `generate_pykeen_predictions`

**7. SwiftUI Views**
   - `ClaimInspectorView` — display and edit claims
   - `OntologyBrowserView` — entity "bio" view with all claims
   - `EpistemologyGraphView` — claim relationships visualization
   - `PredictionReviewView` — review and apply AI predictions

**8. Tests**
   - Multi-source claim tests
   - Ontology view tests
   - Prediction CRUD tests
   - PyKEEN heuristic and model inference tests
   - Migration idempotency tests

**9. OpenAPI Sync**
   - Regenerate schema and Swift client

**Phase 1 Complete When:** User can create multi-source claims, browse ontology, see epistemology relationships, and work with PyKEEN predictions. All quality gates pass.

**Quality Gates (run at each step):**
- [ ] `ruff check fichero-engine/src/` — Python linting
- [ ] `python -m pytest fichero-engine/tests/unit/test_knowledge_graph_api.py` — tests
- [ ] `swiftlint lint fichero/fichero/` — Swift linting
- [ ] `xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero -sdk macosx build` — Swift build
- [ ] Backend running: `source .venv/bin/activate && PYTHONPATH=fichero-engine/src uvicorn fichero.api.main:app --port 8765 --reload`

---

### Phase 2: Layer 5 — Hermeneutics (Interpretation & Meaning)

**Goal:** Interpretive frameworks, pattern recognition, part-whole navigation, meaning extraction.

**1. Models** (`hermeneutics_models.py`)
   - `InterpretiveFramework` — historical, disciplinary, thematic, methodological lenses
   - `HermeneuticContext` — applied interpretations to claims
   - `PatternInstance` — recognized patterns across claims
   - `InterpretiveAct` — reading, translating, contextualizing, synthesizing, critiquing
   - `HermeneuticCircleState` — part-whole navigation tracking

**2. Backend Routes** (`hermeneutics.py`)
   - Framework CRUD (`POST|GET /hermeneutics/frameworks`)
   - Context application (`POST /hermeneutics/claims/{id}/context`)
   - Pattern detection (`GET|POST /hermeneutics/patterns`)
   - Part-whole navigation (`GET|POST /hermeneutics/circle-state`)
   - AI interpretation suggestions (`POST /hermeneutics/suggest-interpretation`)

**3. MCP Tools**
   - `apply_framework`, `find_patterns`
   - `suggest_interpretation`
   - `navigate_part_whole`

**4. SwiftUI Views**
   - `FrameworkSelectorView` — choose interpretive lens
   - `InterpretationPanelView` — apply and view interpretations
   - `PatternBrowserView` — discover and explore patterns
   - `PartWholeNavigatorView` — navigate hermeneutic circle

**5. Tests**
   - Framework CRUD tests
   - Context application tests
   - Pattern detection tests
   - Part-whole navigation tests

**6. OpenAPI Sync**
   - Regenerate schema and Swift client

**Phase 2 Complete When:** User can apply frameworks, see patterns, navigate part-whole, and view AI interpretation suggestions. All quality gates pass.

**Quality Gates:**
- [ ] `ruff check fichero-engine/src/`
- [ ] `python -m pytest fichero-engine/tests/unit/test_hermeneutics_api.py`
- [ ] `swiftlint lint fichero/fichero/`
- [ ] `xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero -sdk macosx build`
- [ ] Backend running with reload

---

### Phase 3: Layer 6 — Mind Palace (Visual + Text Assembly)

**Goal:** 3D spatial workspace with RealityKit, visual assembly, text synthesis, Tinderbox integration.

**1. Models** (`spatial_models.py`)
   - `SpatialRoom` — 3D workspace container
   - `SpatialNode` — positioned sources, claims, notes, entities
   - `SpatialConnection` — visual links (evidentiary, semantic, ontological, hermeneutic, user_drawn)
   - `SpatialStack` — grouped materials
   - `NativeNote` — text notes (user, ai_workspace, ai_hypothesis, ai_summary, shared)
   - `SpatialViewport` — camera position, focus, zoom

**2. Backend Routes** (`mind_palace.py`)
   - Room management (`POST|GET|DELETE /mind-palace/rooms`)
   - Node management (`POST|PATCH|DELETE /mind-palace/nodes`)
   - Connection management (`POST|DELETE /mind-palace/connections`)
   - Stack management (`POST|PATCH /mind-palace/stacks`)
   - Note management (`POST|PATCH /mind-palace/notes`)
   - Viewport control (`GET|POST /mind-palace/viewport`)
   - Capture (`POST /mind-palace/capture`)
   - Tinderbox integration (`POST /mind-palace/export/tinderbox`, `/import/tinderbox`)
   - AI arrangement suggestions (`POST /mind-palace/suggest-arrangement`)

**3. RealityKit Integration** (NOT deferred)
   - `RealityKitSceneManager` — scene setup, camera, lighting
   - `NodeEntity` — RealityKit entities for sources, claims, notes
   - `ConnectionEntity` — visual link rendering
   - Hit testing, drag gestures, focus transitions
   - Still image capture from viewport

**4. MCP Tools**
   - `create_room`, `place_node`, `move_node`, `remove_node`
   - `link_nodes`, `unlink_nodes`
   - `focus_node`, `read_scene`, `capture_viewport`
   - `create_note`, `suggest_arrangement`

**5. SwiftUI Views**
   - `MindPalaceView` — main container with SwiftUI chrome
   - `RealityKitSceneView` — Metal/RealityKit 3D scene (UIViewRepresentable)
   - `NodeInteractionView` — drag, connect, stack gestures
   - `NoteEditorView` — text assembly surface
   - `ConnectionPaletteView` — link type selector
   - `FrameworkHUDView` — hermeneutic overlay in 3D
   - `ViewportControlsView` — camera, focus, bookmark controls

**6. Tests**
   - Room CRUD tests
   - Node placement/movement tests
   - Connection management tests
   - Note CRUD tests
   - Tinderbox integration tests
   - RealityKit scene tests (if feasible in unit tests)

**7. OpenAPI Sync**
   - Regenerate schema and Swift client

**Phase 3 Complete When:** User can create rooms, place nodes in 3D, make connections, edit notes, capture viewport, and export/import with Tinderbox. All quality gates pass.

**Quality Gates:**
- [ ] `ruff check fichero-engine/src/`
- [ ] `python -m pytest fichero-engine/tests/unit/test_mind_palace_api.py`
- [ ] `swiftlint lint fichero/fichero/`
- [ ] `xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero -sdk macosx build`
- [ ] RealityKit scene renders without errors
- [ ] Backend running with reload

---

### Phase 4: Layer 0 — Agent Research (Systematic Discovery)

**Goal:** Sandboxed research agents with web/browser tools, systematic source discovery.

**Why last:** Agents need the full knowledge graph, hermeneutics, and mind palace to save and organize what they discover.

**1. Models** (`research_models.py`)
   - `ResearchProject`, `ResearchPlan`, `ResearchTask`, `ResearchStep`
   - `SearchSource` — curated URLs, folders, databases, APIs
   - `ResearchNote`, `ResearchChecklist`

**2. Backend Routes** (`research_agents.py`)
   - Project/plan/task/step CRUD
   - Sandboxed tool endpoints:
     - `POST /research/tools/web-search` — HTTP requests with rate limiting
     - `POST /research/tools/browser-navigate` — browser automation
     - `POST /research/tools/document-fetch` — fetch and save as Source
   - All writes go to Fichero database (no filesystem/CLI escape)

**3. Sandboxed Tool Implementation**
   - HTTP client with robots.txt respect, rate limiting
   - Browser automation in isolated process (playwright/selenium)
   - All actions logged with agent_id attribution
   - Document fetch creates Layer 1 Source with provenance metadata

**4. MCP Tools**
   - `create_project`, `create_plan`, `create_task`, `create_step`
   - `execute_web_search`, `navigate_browser`, `fetch_document`
   - `save_research_note`, `complete_checklist_item`

**5. SwiftUI Views**
   - `ResearchProjectListView` — browse and create projects
   - `ResearchTaskView` — manage tasks and steps
   - `ResearchStepEditor` — configure search actions
   - `AgentToolPanel` — trigger web search, browser navigation
   - `ResearchActivityView` — monitor agent progress

**6. Tests**
   - Project/plan/task/step CRUD tests
   - Web search tool tests (mock HTTP)
   - Browser navigation tests (mock browser)
   - Document fetch tests (creates Source)
   - Sandbox security tests (attempted filesystem/CLI access blocked)

**7. OpenAPI Sync**
   - Regenerate schema and Swift client

**Phase 4 Complete When:** Agents can execute systematic research, discover sources, and save to the full knowledge graph system. All quality gates pass.

**Quality Gates:**
- [ ] `ruff check fichero-engine/src/`
- [ ] `python -m pytest fichero-engine/tests/unit/test_research_agents_api.py`
- [ ] Sandbox security tests pass (filesystem/CLI escape blocked)
- [ ] `swiftlint lint fichero/fichero/`
- [ ] `xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero -sdk macosx build`
- [ ] Backend running with reload

---

### Phase 5: Integration & Polish

**Goal:** Full system integration, quality assurance, documentation.

**1. Cross-Layer Integration**
   - Agent-discovered sources → Claims extraction → Ontology
   - Hermeneutics frameworks applied in Mind Palace HUD
   - Mind Palace notes exported to Tinderbox
   - All layers accessible via unified MCP interface

**2. Quality Checks**
   - `ruff check fichero-engine/src/`
   - `python -m pytest fichero-engine/tests/unit/`
   - `swiftlint lint fichero/fichero/`
   - Xcode build validation
   - Integration tests (end-to-end workflow)

**3. Documentation**
   - API documentation for all new endpoints
   - MCP tool reference
   - User guide for knowledge graph, hermeneutics, mind palace

**Phase 5 Complete When:** All seven layers work together, tests pass, documentation complete. All quality gates pass.

**Quality Gates:**
- [ ] `ruff check fichero-engine/src/` — zero errors
- [ ] `python -m pytest fichero-engine/tests/unit/` — all tests pass
- [ ] `swiftlint lint fichero/fichero/` — zero warnings
- [ ] `xcodebuild -project fichero/fichero.xcodeproj -scheme Fichero -sdk macosx build` — build succeeds
- [ ] Integration tests pass (end-to-end workflow)
- [ ] OpenAPI schema synced and Swift client regenerated
- [ ] Backend running with reload
- [ ] Manual QA checklist completed

---

### Phase 6: SwiftUI Views (All Layers)
    - Framework selector
    - Pattern browser
    - Part-whole navigator

15. **Create Mind Palace views**
    - RealityKit 3D scene
    - Node interaction (drag, connect, stack)
    - Note editor for text assembly
    - Framework HUD overlay

### Phase 5: Testing & Validation
16. **Add comprehensive tests**
    - Agent research tests
    - Knowledge graph tests
    - Hermeneutics tests
    - Mind Palace tests

17. **Update OpenAPI schema**
    ```bash
    cd fichero-engine
    ./scripts/sync_openapi_schema.sh
    ```

### Phase 6: PyKEEN Integration (Future)
18. **Implement link prediction**
    - Heuristic predictions using embeddings
    - PyKEEN model training on claim graph
    - Model inference for next_logical claims

### Phase 7: Quality Assurance
19. **Run all quality checks**
    - `ruff check fichero-engine/src/`
    - `uvx ruff check fichero-engine/src/`
    - `python -m pytest fichero-engine/tests/unit/`
    - `swiftlint lint fichero/fichero/`
    - Xcode build validation

## Verification Checklist

### Layer 0: Agent Research
- [ ] `ResearchProject`, `ResearchPlan`, `ResearchTask`, `ResearchStep` models defined
- [ ] `SearchSource` model for curated search targets
- [ ] `ResearchNote`, `ResearchChecklist` models defined
- [ ] Sandboxed web search tool (no filesystem/CLI escape)
- [ ] Browser automation tool with isolation
- [ ] Document fetch tool that saves to Fichero database
- [ ] All agent actions logged with attribution
- [ ] SwiftUI project/task/step management views

### Layers 1-4: Knowledge Graph Core
- [ ] `SourceType`, `ClaimType`, `EpistemicStatus` enums defined
- [ ] `PredictionMetadata`, `PredictionEntity`, `PredictionUncertaintySpan`, `PredictionLink` models defined
- [ ] `KnowledgePrediction` model defined
- [ ] `KnowledgeClaim` updated with `source_type`, `source_ids`, `source_page_labels`, `source_languages`
- [ ] One-time migration script created and tested
- [ ] Migration is idempotent (safe to run multiple times)
- [ ] `GET /claims` extended with basic filters
- [ ] `GET /claims/filtered` with advanced filters
- [ ] `GET /claims/{id}/sources` resolves sources with language info
- [ ] `GET /claims/{id}/ontology` returns entity-centric view
- [ ] `GET /predictions` lists predictions
- [ ] `POST /predictions` creates prediction
- [ ] `POST /predictions/{id}/apply` applies prediction to create claim
- [ ] SwiftUI claim inspector and ontology browser views

### Layer 5: Hermeneutics
- [ ] `InterpretiveFramework` model (historical, disciplinary, thematic, methodological)
- [ ] `HermeneuticContext` model for applied interpretations
- [ ] `PatternInstance` model for pattern recognition
- [ ] `InterpretiveAct` model (reading, translation, contextualization, synthesis, critique)
- [ ] `HermeneuticCircleState` model for part-whole navigation
- [ ] Framework CRUD endpoints
- [ ] Context application endpoints
- [ ] Pattern detection and storage endpoints
- [ ] Part-whole navigation endpoints
- [ ] AI interpretation suggestion endpoints
- [ ] SwiftUI framework selector, pattern browser, part-whole navigator views

### Layer 6: Mind Palace
- [ ] `SpatialRoom` model defined
- [ ] `SpatialNode` model with position, rotation, scale
- [ ] `SpatialConnection` model (evidentiary, semantic, ontological, hermeneutic, user_drawn)
- [ ] `SpatialStack` model for grouped materials
- [ ] `NativeNote` model (user, ai_workspace, ai_hypothesis, ai_summary, shared)
- [ ] `SpatialViewport` model for camera/focus state
- [ ] Room CRUD endpoints
- [ ] Node placement, movement, deletion endpoints
- [ ] Connection management endpoints
- [ ] Stack management endpoints
- [ ] Viewport control and capture endpoints
- [ ] Tinderbox integration endpoints
- [ ] AI arrangement suggestion endpoints
- [ ] SwiftUI RealityKit 3D scene view
- [ ] SwiftUI node interaction (drag, connect, stack)
- [ ] SwiftUI note editor for text assembly
- [ ] SwiftUI framework HUD overlay

### Data Integrity
- [ ] Claims can have single or multiple sources
- [ ] Source references include page labels
- [ ] Source languages tracked per source
- [ ] Legacy claims migrated from single-source to multi-source format
- [ ] Agent research artifacts properly attributed
- [ ] Spatial nodes persist positions across sessions

### MCP Tools
- [ ] Research agent tools (create project, execute search, save note)
- [ ] Hermeneutics tools (apply framework, find patterns, navigate part-whole)
- [ ] Mind Palace tools (create room, place/move nodes, link nodes, focus, capture)

### PyKEEN Integration (Phase 1 — NOT deferred)
- [ ] `pykeen` installed in dependencies
- [ ] Heuristic prediction endpoint (`POST /predictions/generate/heuristic`)
- [ ] PyKEEN model training pipeline
- [ ] Model inference endpoint (`POST /predictions/generate/pykeen`)
- [ ] Prediction metadata stores AI confidence, model, entities, uncertainty
- [ ] Prediction application creates claim from prediction
- [ ] SwiftUI `PredictionReviewView` for reviewing/applying predictions

### Swift Integration
- [ ] OpenAPI schema exports all new types
- [ ] Swift client regenerates without errors
- [ ] `APIEndpoints.swift` updated with KnowledgeGraph endpoints
- [ ] Swift can consume all 3 claim endpoints
- [ ] Swift can resolve sources for claims
- [ ] Swift can view ontology (entity-centric claims)

### Testing
- [ ] 20+ tests added covering all new functionality
- [ ] Migration tests pass
- [ ] Edge case tests pass (empty sources, nonexistent languages)
- [ ] Prediction CRUD tests pass
- [ ] Ruff check passes
- [ ] All tests pass
- [ ] Swift build succeeds

## Notes

### Seven-Layer Architecture Summary

| Layer | Name | Purpose | Key Question |
|-------|------|---------|--------------|
| 0 | Agent Research | Systematic discovery with sandboxed tools | "What should we investigate?" |
| 1 | Sources | Canonical evidence | "What do we have?" |
| 2 | Claims | Atomic statements grounded in sources | "What do we know?" |
| 3 | Ontology | Entity-centric views | "What is this entity's story?" |
| 4 | Epistemology | Evidence relationships | "How do we know?" |
| 5 | Hermeneutics | Interpretation & meaning | "What does it mean?" |
| 6 | Mind Palace | Visual + text assembly | "How do we synthesize?" |

### Key Principles

- **Flat claim model** - all claims stored uniformly, categories are query-time filters
- **Ontology = entity-centric** - all claims about ONE entity, forming its "bio"
- **Epistemology = how we know** - claim relationships (supports/contradicts/refines)
- **Hermeneutics = what it means** - interpretation, context, patterns, frameworks
- **Mind Palace = synthesis** - visual and text assembly for human + AI collaboration
- **AI + human collaboration** - AI generates predictions/interpretations, user curates, both work
- **Source languages tracked** - Spanish doc says X, Dutch doc says Y
- **PyKEEN for link prediction** - learns patterns, predicts next logical claims
- **Agent sandbox** - research agents have web/browser tools but no filesystem/CLI escape
- **Swift is dumb display** - backend handles all filtering, sorting, deduplication
- **MCP as core interface** - agents must control the space programmatically

### The Three Meaning Questions

**Epistemology** asks: *How do we know this?*
- What evidence supports this claim?
- Does it contradict other claims?
- How confident should we be?

**Hermeneutics** asks: *What does this mean?*
- How do we interpret this in context?
- What patterns emerge?
- What frameworks help us understand?

**Mind Palace** asks: *How do we assemble this into understanding?*
- How do we arrange materials to see connections?
- How do we write this into narrative?
- How do we synthesize across sources?

### Deferrals (Post-0.0.2)

- Real-time collaborative multi-user spatial sessions
- Mobile AR/VR extensions
- Advanced RealityKit effects (particles, complex shaders)
- Distributed PyKEEN training across multiple machines
