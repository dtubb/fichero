# Durable Lessons Learned / Decisions

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
