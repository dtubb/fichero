# Durable Lessons Learned / Decisions

*   **Background Task System Pattern (2026-04-11):** Implemented task queue for background jobs using:
    - APScheduler for async task execution with priority-based scheduling
    - DuckDB for persistent task storage (survives restarts)
    - Task status lifecycle: PENDING → RUNNING → COMPLETED/FAILED/CANCELLED
    - Progress tracking with current/total/percent/message updates
    - Type-specific task handlers (reindex, metrics, repair)
    - Automatic recovery of interrupted tasks on startup
    - Integration with existing Database class for operations

*   **SSRF Security Pattern for Research Tools (2026-04-10):** Security audit of research tools (research.py) revealed critical SSRF vulnerabilities:
    - `follow_redirects=True` without redirect chain validation allows open redirect attacks
    - `_is_sandbox_violation()` using `startswith()` is insufficient — must validate resolved IPs
    - Must block RFC1918 ranges (10.x, 172.16-31.x, 192.168.x), loopback (127.x), link-local (169.254.x), cloud metadata
    - URL scheme checks are case-sensitive — need case-normalization
    - DNS rebinding requires resolution-time IP validation, not just hostname checks
    - Security tests should be written *before* fixes to document known vulnerabilities

*   **Agent Research Pattern**: Following the established pattern from knowledge_graph.py, hermeneutics.py, and mind_palace.py, the Agent Research implementation uses:
    - Pydantic models with `model_config = ConfigDict(from_attributes=True, extra="allow")`
    - Separate request/response models for API endpoints
    - Full CRUD with soft-delete (archiving) pattern
    - Status tracking with enums matching other modules
    - Placeholder tool implementations that return example data

*   **Skills Relocation:** Skills moved from `.agents/skills/` to `plugins/fs_session/skills/`. All script invocations now use `SCRIPT_ROOT` resolver that checks both `$HOME/.pi/agent/skills/fs_session/scripts` and repo `plugins/fs_session/skills/...`.

*   **Backend Task Prioritization (2026-04-10):** Created 21 backend-focused GitHub issues for milestones 0.0.3 through 0.1.0. All issues use only pre-configured labels (`area:backend-api`, `type:task`) since custom labels like `area:operations` don't exist in the project. Issues are properly organized by milestone and ready for AI agent claiming. Backend-only work available: #419-440 excluding Swift-requiring tasks.

*   **Branch Convention (2026-04-10):** Implementation work happens on milestone branches (e.g., `0.0.2`, `feature/388-hermeneutics`), not planning branches. The `0.0.2` branch IS the active implementation branch. State is now tracking backend implementation work for 0.0.3-0.1.0 milestones with 21 issues created for AI agent claiming.

*   **Migration Framework Pattern (2026-04-10):** Database migrations use a `MigrationRunner` class pattern:
    - Dry-run mode validates migrations without side effects (count-only)
    - All mutations logged to `MutationLog` with before/after state for rollback
    - Rollback operations reverse mutations in descending timestamp order (LIFO)
    - Batch processing with progress callbacks for large datasets
    - Validation safety checks prevent running unsafe migrations
    - Legacy function wrappers maintain backward compatibility

## Multilingual System Pattern — 2026-04-11

**Pattern:** Language-aware text processing with transliteration support

**Architecture:**
- Language detection using cld3 (optional) with heuristic fallback
- Unicode normalization (NFKC) for consistent representation
- Language-specific rules (Turkish I handling, German ß, Arabic/Hebrew/Thai scripts)
- Transliteration tables for common proper nouns (Tokyo→東京)
- Levenshtein distance for similar-language matching

**Usage:**
```python
from fichero.multilingual import detect_language, normalize_text, find_cross_language_matches

# Detect language
result = detect_language("这是一句中文")
# LanguageDetectionResult(language='zh', confidence=0.9, is_reliable=True)

# Normalize for search
normalized = normalize_text("Straße", "de")  # "straße"

# Cross-language search
candidates = [("id1", "东京", "zh"), ("id2", "Tokyo", "en")]
matches = find_cross_language_matches("tokyo", candidates)
# [("id1", 0.95), ("id2", 1.0)]
```

**Testing:** 45 unit tests covering detection, normalization, stemming, transliteration, and search. Heuristic detection covers CJK, Arabic, Hebrew, Thai, Cyrillic, Devanagari without external deps.

## MCP Adapter Pattern — 2026-04-12

**Pattern:** Thin MCP tool adapters that call canonical backend APIs with zero logic divergence

**Principle:** MCP tools should be pure HTTP adapters, not reimplemented business logic

**Architecture:**
- Dedicated `/api/mcp/tools/*` routes with Pydantic validation
- Request/response models define strict schemas per tool
- Backend operations delegate to existing Database class
- Enum validation helpers ensure type safety with clear errors
- Soft-delete support for all CRUD operations

**MCP Tool Endpoints:**
```python
POST /api/mcp/tools/knowledge/entities/upsert  # Create or update
POST /api/mcp/tools/knowledge/claims/create    # Create new claim
GET    /knowledge/entities/{id}                # Read single
GET    /knowledge/claims/{id}
DELETE /knowledge/entities/{id}                # Soft-delete
DELETE /knowledge/claims/{id}
GET    /knowledge/entities                     # List with filter
GET    /knowledge/claims                       # List with filter
```

**Validation Pattern:**
```python
def _validate_entity_type(entity_type: str) -> EntityType:
    try:
        return EntityType(entity_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type. Valid: {[t.value for t in EntityType]}"
        )
```

**Key Feature:** Entity upsert detects existing by ID — "created" or "updated" in response distinguishes operation

## Review Queue Pattern — 2026-04-12

**Pattern:** Claim review workflow with state transitions and queue views

**State Machine:**
- unreviewed → shortlisted → curated/rejected
- bidirectional transitions supported via PATCH endpoints
- review history tracked in claim.metadata["review_history"]

**Endpoints:**
```python
PATCH /api/claims/{id}/transition        # Single claim
POST /api/claims/batch/transition        # Batch transition
GET /api/claims/queues/unreviewed      # Queue views
GET /api/claims/queues/shortlisted
GET /api/claims/queues/curated
GET /api/claims/queues/rejected
```

**Queue Item Enrichment:**
- Entity IDs resolved to canonical names for display
- Review history included in response
- Text truncated (500 chars) with ellipsis

**Filter Parameters:**
- `?person=<name>` — Match entity names
- `?topic=<topic>` — Match entities or text
- `?question=<text>` — Match claim text

**Review History Entry:**
```json
{
  "from_state": "unreviewed",
  "to_state": "shortlisted",
  "timestamp": "2024-01-01T00:00:00",
  "reviewed_by": "human",
  "reason": "Verified by expert"
}
```

## Search Explanation Pattern — 2026-04-12

**Pattern:** Transparent search with source attribution and RAG mode controls

**Architecture:**
- RAG modes define precision/recall tradeoffs: conservative (0.8), balanced (0.5), speculative (0.3)
- Search explanation includes human-readable description + source attribution
- Metrics: precision estimates, relevance scores, token usage
- Query refinement suggestions based on result count

**RAG Mode Config:**
```python
RAGMode.CONSERVATIVE:  # High precision, low risk
  min_score: 0.8, max_results: 5, context_ratio: 0.3

RAGMode.BALANCED:  # Default
  min_score: 0.5, max_results: 10, context_ratio: 0.5

RAGMode.SPECULATIVE:  # Broad research
  min_score: 0.3, max_results: 20, context_ratio: 0.8
```

**Source Attribution:**
- match_type: semantic/keyword/hybrid
- relevance_score + position rank
- excerpt preview

**Endpoints:**
- POST /api/search/explain — Full explanation
- GET /api/search/modes — Available modes
- GET /api/search/metrics — System metrics

## Interpretations Workspace Pattern — 2026-04-12

**Pattern:** Structured interpretation management with method taxonomy and citation lineage

**Method Taxonomy:**
- Categories: HISTORICAL, TEXTUAL, ANALYTICAL, SYNTHETIC, CRITICAL, COMPARATIVE, EMPIRICAL, CONCEPTUAL
- Techniques: CLOSE_READING, DISCOURSE_ANALYSIS, GENRE_ANALYSIS, NARRATIVE_ANALYSIS, SOURCE_CRITICISM, COMPARATIVE_ANALYSIS, STATISTICAL, THEMATIC_CODING, GROUNDED_THEORY, HERMENEUTIC_CIRCLE, DIALECTICAL

**Citation Lineage:**
- Citation types: primary, secondary, supporting, contradicting, contextual
- Relevance scores (0.0-1.0)
- Links claims to source documents via provenance tracing

**Key Features:**
- Multi-claim interpretations (claim_ids list)
- Method tag confidence and rationale
- Lineage tracing traces through claim → document
- Integration with hermeneutics framework

**Endpoints:**
- POST/GET/PATCH/DELETE /api/interpretations — CRUD
- GET /api/interpretations/{id}/lineage — Traced provenance
- POST /api/interpretations/{id}/tags — Add method tags
- GET /api/interpretations/taxonomy/methods — Available categories/techniques

## Activity Stream Pattern — 2026-04-12

**Pattern:** Time-series activity tracking with aggregation and trend analysis

**Architecture:**
- Activity model: type, level, timestamp, message + metadata
- Entity grouping: workflow, batch, node, system
- In-memory buffer for recent activities (deque)
- DuckDB persistence for historical queries
- Pub/sub pattern for real-time streaming (SSE/WebSocket)

**Aggregation Endpoints:**
- /api/activity/feed — Grouped activities with pagination
- /api/activity/trends — Time-series data (hourly/daily/weekly)
- /api/activity/top — Most active entities with success rates
- /api/activity/metrics/summary — Comprehensive dashboard metrics

**Trend Calculation:**
```python
hourly: bucket_key = ts.strftime("%Y-%m-%dT%H:00:00")
daily:  bucket_key = ts.strftime("%Y-%m-%d")
weekly: bucket_key = ts.strftime("%Y-%W")
```

**Busiest Hour Detection:**
- Count activities per hour
- Return hour with maximum count
- Useful for capacity planning

**Success Rate Formula:**
```python
success_rate = completed / (completed + failed) * 100
```

## Contradiction Triage Pattern — 2026-04-12

**Pattern:** Evidence-based contradiction management with triage workflow

**Severity Levels:**
- MINOR: Discrepancy in details
- MODERATE: Significant disagreement  
- SEVERE: Fundamental conflict
- CRITICAL: Core thesis contradiction

**Evidence Types:**
- PRIMARY_SOURCE — Direct archival/documentary
- SECONDARY_SOURCE — Scholarly analysis
- EXPERT_TESTIMONY — Authority statements
- STATISTICAL — Data-driven evidence
- LOGICAL_INFERENCE — Deductive reasoning

**Resolution Workflow:**
- UNRESOLVED → UNDER_REVIEW → RESOLVED/REFUTED/SUPERSEDED

**Key Endpoints:**
- /claims/{id}/contradictions — List with severity filtering
- /claims/{id}/compare/{id} — Side-by-side analysis
- /claims/{id}/evidence-chain — Chain traversal (claim→sources→claims)
- /claims/{id}/visualization — Graph data for UI

**Comparison Analysis:**
- Semantic similarity (word overlap Jaccard)
- Points of conflict: confidence gap >0.3, status mismatch
- Points of agreement: shared entity_ids, similar confidence, same source
