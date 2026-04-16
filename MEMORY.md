# Durable Lessons Learned / Decisions

## File-Splitting Patterns — 2026-04-14

**Mixin pattern for large class splits.** When splitting a large class (e.g., `TaskQueue`), extract method groups into a `*Mixin` class. The mixin references `self.database`, `self._save_task` etc. without owning them — Python resolves `self` at call time, so the mixin works as long as the concrete class provides those attributes. Pattern used in `task_workers.py` / `TaskWorkersMixin`.

**Re-export pattern for backward compatibility.** After splitting a module, add at the bottom of the original file:
```python
from fichero.new_module import func_a, func_b  # noqa: F401, E402 (re-exported)
```
This keeps all existing import paths working. Use `# noqa: F401` because ruff sees these as unused.

**Thin combiner router for split route modules.** When splitting a large route file into sub-modules, make the original a thin combiner:
```python
from fastapi import APIRouter
from .sub_module_a import router as a_router
router = APIRouter()
router.include_router(a_router)
```
This preserves all existing `include_router(research_agents_router)` call sites in `main.py`.

**Schemas module for Pydantic models.** When splitting a route module, move all Pydantic request/response models to a `schemas.py` sibling. Other modules (`core.py`, `runner.py`, `threads.py`) all import from `schemas.py`. This prevents circular imports and keeps models findable.

## Route Test Patterns — 2026-04-14

**Double-prefix gotcha:** When a router has `prefix="/X"` AND is mounted at `/api/X`, actual paths are `/api/X/X/...`. Affects: `tasks`, `migrations`, `iiif`, `review_queue`. Always check `grep "router\b" main.py` and `router = APIRouter(prefix=...)` together.

**Patch lazy imports at the source module, not the route module.** `from fichero.storage import stats` inside a route function body must be patched as `fichero.storage.stats`, not `fichero.api.routes.storage.stats`. But `from fichero.multilingual import detect_language` at module top must be patched as `fichero.api.routes.multilingual.detect_language` (bound name).

**Route return values must be real Pydantic instances.** When a route returns a model directly (FastAPI serializes it), patching must return a real model instance — not `MagicMock(spec=...)`. Pydantic's C-extension serializer rejects `_SentinelObject`.

**Async mock pattern for cleanup routes.** Routes that call `tracker.store.delete_old(dt)` need `tracker.store = MagicMock()` with `tracker.store.delete_old = AsyncMock(return_value=0)` — the store sub-attribute must exist before setting the async mock.

**DocType vs FileType confusion.** `DocType` describes hierarchy role (file, folder, chunk, page). `FileType` describes media format (image, pdf, audio). The IIIF route had this wrong: `DocType.image` doesn't exist — use `doc.file_type` against `FileType.image/pdf`.

**FK-free store.** DuckDB store has no foreign key constraints. `create_plan(project_id="missing")` succeeds (200) — don't write tests expecting 404 on missing parents unless the route explicitly validates them.

## OpenAPI / Swift Client Codegen Patterns — 2026-04-14

**`-> dict` handlers produce empty OpenAPI schemas.** FastAPI only emits named `$ref` schemas for handlers with a `BaseModel` return annotation. `-> dict` / `-> dict[str, Any]` produces `{}` in the spec — `swift-openapi-generator` gets no schema and can't synthesize Swift types. Fix: add a named `BaseModel` subclass as return type on every route handler.

**`gt=0` causes `exclusiveMinimum` parse error in swift-openapi-generator.** FastAPI/Pydantic emits `exclusiveMinimum: 0` (JSON Schema Draft 2020-12 / OpenAPI 3.1 style). The Swift generator targets OpenAPI 3.0 which expects `exclusiveMinimum` as a Bool. Fix: use `ge=1` instead of `gt=0` for integer fields — semantically identical but emits `minimum: 1`.

**Duplicate header from Depends + explicit Header param.** `get_library_database` already declares `x_fichero_library_path: str = Header(...)`. If a route handler also declares it explicitly, FastAPI inlines it twice in the OpenAPI spec — `swift-openapi-generator` generates two Swift properties with the same name and the build fails with "invalid redeclaration". Fix: remove the explicit `Header(...)` param from any handler that also calls `Depends(get_library_database)`.

**Pydantic v2: never name a field `json`.** `json` shadows `BaseModel.json()` — Pydantic emits a `UserWarning` and the field behaves unexpectedly. Use `json_data` or similar. Tests calling `r.json()["json"]` will also break.

**Class ordering matters for return type annotations.** A `BaseModel` used as a return type annotation must be defined at module level BEFORE the function. If placed after (even logically nearby), Python raises `NameError` at import time. Place new response models at the top of the file, after `router = APIRouter()`.

## FastAPI Route Registration Pattern — 2026-04-12

**Pattern:** Adding new API routes to the FastAPI application

**Required Steps:**
1. Create route module with FastAPI router in `fichero-api/src/fichero/api/routes/`
2. Add module to `fichero-api/src/fichero/api/routes/__init__.py` `__all__` list
3. Import router in `fichero-api/src/fichero/api/main.py` from routes package
4. Add tuple to `_CORE_ROUTE_SPECS` or `_DEV_ROUTE_SPECS`: `(router, "/api/prefix", ["feature-flag-tags"])`

**Verification:**
- Check `/openapi.json` for new endpoints
- Run: `PYTHONPATH=fichero-api/src python -c "from fichero.api.main import app; print([r.path for r in app.routes])"`

**Test Pattern:**
- Create `test_<feature>_api.py` in `fichero-api/tests/unit/`
- Test Pydantic models, route handlers, and integration points
- Avoid TestClient for simple unit tests (test logic directly)

## Multilingual NLP Pattern — 2026-04-12

**Pattern:** Cross-language text processing using cld3 and custom utilities

**Language Detection:**
```python
from fichero.multilingual import detect_language
result = detect_language("Hello world")  # LanguageDetectionResult
# Returns: language (ISO 639-1), confidence (0-1), is_reliable (confidence > 0.7)
```

**Text Normalization:**
```python
from fichero.multilingual import normalize_text
normalized = normalize_text(text, language_code)  # NFKC Unicode + lowercase (Latin only)
```

**Cross-Language Matching:**
```python
from fichero.multilingual import calculate_cross_language_similarity, find_cross_language_matches
score = calculate_cross_language_similarity(text1, lang1, text2, lang2)
matches = find_cross_language_matches(query, candidates, threshold=0.5)
```

**Language Persistence:**
- `KnowledgeEntity.language`: entity's primary language (ISO 639-1)
- `KnowledgeClaim.language`: claim text language
- `KnowledgeClaim.source_languages`: list of source document languages
- `KnowledgeEntity.aliases`: supports transliterations (e.g., ["東京", "Tokyo"])

**Supported Languages:** 20+ including en, es, fr, de, it, pt, ja, ko, zh, ar, ru, hi, th, he

## MCP Knowledge Adapter Pattern — 2026-04-12

**Pattern:** Thin MCP adapters that map 1:1 to canonical Knowledge API operations

**Purpose:** Enable Claude Code and other MCP clients to manipulate knowledge graph entities and claims through standardized tools.

**Architecture:**
```
MCP Client (Claude Code)
    ↓
MCP Server (fichero/mcp_server.py)
    ↓ HTTP request
FastAPI MCP Tools Routes (fichero/api/routes/mcp_tools.py)
    ↓ direct DB access
Database (DuckDB)
```

**Key Principle:** No business-logic divergence between MCP and HTTP paths. MCP tools are thin wrappers that:
1. Validate input (Pydantic models)
2. Call canonical Knowledge API (or equivalent DB operations)
3. Return standardized response

**Endpoints:**
- `POST /mcp/tools/knowledge/entities/upsert` — Create or update entity
- `POST /mcp/tools/knowledge/claims/create` — Create claim
- `GET /mcp/tools/knowledge/entities/{id}` — Retrieve entity
- `GET /mcp/tools/knowledge/claims/{id}` — Retrieve claim
- `DELETE /mcp/tools/knowledge/entities/{id}` — Soft-delete entity
- `DELETE /mcp/tools/knowledge/claims/{id}` — Soft-delete claim
- `GET /mcp/tools/knowledge/entities` — List entities (with filters)
- `GET /mcp/tools/knowledge/claims` — List claims (with filters)

**MCP Server Tool Handlers:**
Call canonical API endpoints via `FicheroAPIClient`:
```python
async def call_tool(name, args):
    if name == "fichero_kg_upsert_entity":
        return await api_client.request("POST", "/knowledge-graph/entities", data=args)
```

**Testing Strategy:**
- Unit tests for adapter logic (validation, mapping)
- Integration tests for end-to-end workflow
- Verify both direct route access and MCP server invocation

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

*   **Canonical Knowledge Route Module Pattern (2026-04-12):** Splitting knowledge_graph.py into dedicated modules:
    - entities.py: POST/GET/PATCH /entities, aliasing, resolution
    - claims.py: POST/GET/PATCH /claims, referential integrity
    - claim_links.py: POST/GET/PATCH/DELETE claim linking (bidirectional)
    - Register in _CORE_ROUTE_SPECS with tuple: (router, "/api", ["tag"])
    - Referential integrity: entities must exist before claim creation
    - No soft-delete for links (hard delete only)
    - Patterns extracted from knowledge_graph.py lines ~950-1150

## NetworkX Graph Reasoning Pattern — 2026-04-12

**Pattern:** Algorithmic graph analysis using NetworkX on knowledge graph data

**Graph Construction:**
```python
# Entities become nodes with metadata
G.add_node(entity.id, type="entity", label=entity.canonical_name)

# Claims become nodes connected to entities
G.add_node(claim.id, type="claim", label=claim.text, confidence=claim.confidence)
for entity_id in claim.entity_ids:
    G.add_edge(entity_id, claim.id, relation="mentions", weight=claim.confidence)

# Claim links connect claims to claims
for link in links:
    G.add_edge(link.claim_id, link.related_claim_id, relation=link.relation_type, weight=link.link_quality)
```

**Centrality Algorithms:**
- degree_centrality: Count of edges per node
- betweenness_centrality: Nodes on most shortest paths
- closeness_centrality: Inverse of average distance to others
- eigenvector_centrality: Importance from important neighbors
- pagerank: Iterative importance with damping factor

**Community Detection:**
- louvain: Modularity optimization, O(n log n) complexity
- greedy_modularity: Hierarchical modularity maximization
- label_propagation: Fast O(m) complexity, good for large graphs

**Graceful Degradation:**
- Optional dependency - works without NetworkX installed
- Enabled/disabled via endpoint
- All functions check `reasoner.is_available()` before use
- Tests skip when NetworkX not available

**Metrics:**
- Density: fraction of possible edges present
- Clustering: probability that neighbors are connected
- Connected components: number of disconnected subgraphs
- Modularity: community detection quality (0 = random, 1 = perfect)

**Sources Routes Registration Issue — 2026-04-12**

**Problem:** Attempting to add `/api/sources` routes for issue #364, routes were not appearing in running API despite:
- sources.py file created with FastAPI router
- router registered in main.py _CORE_ROUTE_SPECS
- sources module added to routes/__init__.py __all__

**Findings:**
- Routes appeared in /openapi.json but 404 on actual requests
- sources module import was failing during main.py import
- Workaround: sources routes working via POST/GET with proper `X-Fichero-Library-Path` header when tested directly

**Status:** Routes implemented but runtime registration needs further debugging

## Backend-First Autonomous Loop Policy — 2026-04-11

- For cheap-model `/session-start-auto` loops, **persist execution policy in repo files** (`STATE.md`, `MEMORY.md`, `AGENTS.md`) and GitHub issue comments; chat-only instructions are not durable.
- Backend delivery order is milestone-sequenced: **0.0.3 → 0.0.4 → 0.0.5 → 0.1.0** before frontend re-expansion.
- Per-issue execution gate: claim issue → add/update tests (including security tests if network/file/model code) → implement → run pytest + ruff evidence → PR/merge → close issue.
- Existing repo-wide Ruff test debt can fail global lint despite backend correctness; treat this as separate cleanup scope instead of blocking backend issue completion.

## Sources/API Runtime Drift Lesson — 2026-04-11

- `scripts/start-backend.sh` must prefer project-local `.venv` over ambient `$VIRTUAL_ENV`; otherwise cross-worktree imports can produce route drift (e.g., OpenAPI/routes mismatch and 404 confusion).
- When route appears in code but not runtime, verify importing file path with `python -c 'import fichero.api.main as m; print(m.__file__)'` and inspect live `/openapi.json` before deeper refactors.

## Cherry-Pick Conflict Patterns — 2026-04-13

**When cherry-picking onto an evolved branch, these patterns recur:**

- **research_agents.py + research_models.py must stay in sync**: If you take `--ours` on `research_agents.py` (to keep SSRF security hardening), you must also restore `research_models.py` and the test file to match. The two files form a coherent set — mixed versions break imports.
- **project.pbxproj file references**: Cherry-pick may try to add references to files that don't exist in HEAD (e.g., `BatchDetailView.swift`, `BatchRow.swift`). Always check with `find` before accepting `--theirs` on project.pbxproj; take `--ours` if referenced files don't exist.
- **`@SceneStorage` vs `@AppStorage` for view state**: Bug fix #330 deliberately changed `iconViewScale` from `@SceneStorage` (per-window) to `@AppStorage` (app-wide persistent). When this conflict appears, take `--theirs` — it's the intentional fix.
- **Empty cherry-picks**: When a cherry-pick resolves as empty ("possibly due to conflict resolution"), use `git cherry-pick --skip` — HEAD already contains equivalent changes.

## Branch Cleanup Lesson — 2026-04-13

- After consolidation, verify branch count with `git branch -r` — only `origin/0.0.2` and `origin/main` should remain.
- `git worktree remove --force` still fails if the directory has content git can't delete itself. Follow up with `git worktree prune && rm -rf <path>`.
- `.kreuzberg/extraction/*.msgpack` binary files appear as modified during cherry-picks of branches that processed documents. Always resolve with `--theirs` — these are cache files.

## Swift Target File Sync — 2026-04-16

- Only `fichero-swiftui-tests/` and `fichero-swiftui-ui-tests/` are `PBXFileSystemSynchronizedRootGroup`. The **main `Fichero` target is not** — new `.swift` files inside `fichero-swiftui/fichero-swiftui/…` must be added to `project.pbxproj` explicitly or they won't compile into the app (SourceKit will even error with `Cannot find type 'X' in scope`).
- Workaround when adding a small extension: merge it into an existing file already in the target (e.g. append `extension Document { … }` to the bottom of `Document.swift`) rather than creating a new file. Avoids touching the pbxproj.
- If you *must* create a new file in the main target: edit pbxproj manually (add `PBXFileReference` + `PBXBuildFile` entries and list the file in the target's `PBXSourcesBuildPhase`) or use Xcode.app to add it.

## Swift Tests — Pattern for Testing View Logic — 2026-04-16

- SwiftUI `View` types can't practically be instantiated in unit tests — they need bindings, observed objects, environment values. **Extract pure logic onto the model** (e.g. `Document.isNavigableContainer` instead of `LibraryView.canNavigateInto(_:)`) and have the view call into it. The test then just builds a `Document` value and asserts against the computed property.
- **"All cases" tripwire pattern**: when a function's contract is "only X is true", assert `FileType.allCases.filter { … } == [.pdf]` rather than enumerating every false case. If someone adds a new case and accidentally makes it match, the test fires without needing maintenance.
- **PDF fixtures at test time, not on disk**: build multi-page PDFs with `PDFDocument() + PDFPage(image: NSImage)` drawn with `NSColor.setFill()`. Different colors per page let you pixel-diff TIFF representations to prove the renderer honors `pageIndex`. Tear down in `defer { try? FileManager.default.removeItem(at: url) }` — no binary fixtures to check in.
- **`build.db is locked`** during `xcodebuild` means Xcode.app is holding the lock (`lsof` shows `SWBBuildS`). Run with `-derivedDataPath /tmp/some-dir` to use a separate build database rather than asking the user to quit Xcode.

## Milestone Worktree Convention — 2026-04-15

**Each milestone gets its own worktree at `~/code/fichero-<version>/`** (e.g. `~/code/fichero-0.0.3`). Never per-task branches — commit all milestone work directly to the milestone branch.

**Two-ahead rule:** Never more than one milestone ahead of what Daniel is testing. Layout at any time:
- Released: N
- Daniel testing: N+1 (`~/code/fichero-<N+1>`)
- Claude building: N+2 (`~/code/fichero-<N+2>`)
- Do NOT start N+3 until Daniel approves N+1.

**Create worktree:** `git worktree add ~/code/fichero-0.0.X -b 0.0.X` (from the current milestone's repo)

## Milestone + Release Architecture — 2026-04-15

**40 milestones, one testable feature each (0.0.1–0.9.0).** Each milestone has one `release-gate` issue with Daniel's human test checklist. Testing pipeline: backend tests → SwiftLint + Xcode build → MCP API tests → Peekaboo screenshots → Daniel human test → bug loop → tag+ship. See `docs/architecture/release-process.md`.

**Bug priority rule in `.claude/agent-briefing.md`:** autonomous sessions (`/session-start-auto`) always fix `type:bug` issues before picking feature work. Daniel files bugs via `/bug` skill → GitHub issue with `type:bug` label → auto-prioritised next session.

**Skills live in plugins only.** `~/.claude/skills/` has been deleted. All skills are in `fichero-skills/plugins/`. Never copy skills back to `~/.claude/skills/` — that creates duplicates in the skill picker.

## PyKEEN Knowledge Graph Embedding Pattern — 2026-04-12

**Pattern:** Latent inference for knowledge graphs using PyKEEN embeddings and link prediction

**Graph Construction:**
```python
# Entities -> mentions -> Claims
(entity_id, "mentions", claim_id)

# Claims -> related -> Claims  
(claim1_id, "supports", claim2_id)

# Entities -> co_mentioned_with -> Entities
(entity1_id, "co_mentioned_with", entity2_id)  # via shared claims
```

**Model Types:**
- TransE: Translation-based embeddings (geometric)
- RotatE: Rotation-based in complex space
- DistMult: Bilinear interaction (fast, good benchmark)
- ComplEx: Complex-valued embeddings (asymmetric relations)
- ConvE: Convolutional encoder (captures interactions)

**Prediction Types:**
- head_prediction: Given (?, relation, tail), predict head
- tail_prediction: Given (head, relation, ?), predict tail  
- relation_prediction: Given (head, ?, tail), predict relation

**Training Pipeline:**
1. Build triples from knowledge graph
2. Split: 80% train / 10% test / 10% validation
3. Train with early stopping (patience + min_improvement)
4. Evaluate: hits@10, mean_rank, MRR
5. Store model for inference

**Heuristic Fallback:**
When PyKEEN unavailable, use co-occurrence counts:
- tail_prediction: entities co-mentioned with source
- head_prediction: entities that co-mention target
- relation_prediction: most common relation types

**Storage & Verification:**
- Predictions stored with metadata and confidence scores
- User verification: verified=True/False with notes
- Filterable by model_id and verified status
