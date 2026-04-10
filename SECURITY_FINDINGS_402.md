# Security Review: Phase 1 Knowledge Graph — PyKEEN and Query Vulnerabilities

**Date:** 2026-04-10  
**Issue:** #402  
**Scope:** `fichero-api/src/fichero/knowledge_models.py`, `fichero-api/src/fichero/api/routes/knowledge_graph.py`  
**Reviewer:** Agent (autonomous session)  

---

## Executive Summary

Phase 1 Knowledge Graph contains **HIGH severity security vulnerabilities** related to PyKEEN model deserialization and **MEDIUM severity** issues in entity ID enumeration. While the code has good input validation via Pydantic, the PyKEEN integration introduces pickle-based code execution risks.

**Overall Risk Rating: MEDIUM-HIGH**

---

## Findings

### 🔴 HIGH-1: PyKEEN Model Loading (Arbitrary Code Execution via Pickle)

**Location:** `fichero-api/src/fichero/api/routes/knowledge_graph.py` line 1966

**Issue:** PyKEEN uses Python pickle for model serialization. Loading a compromised model file can execute arbitrary code.

```python
try:
    trained_model = pykeen.models.Model.load_directory(str(model_path))
except Exception as exc:
    raise HTTPException(
        status_code=500, detail=f"Failed to load PyKEEN model: {exc}"
    ) from exc
```

**Details:**
- `pykeen.models.Model.load_directory()` internally uses pickle
- If an attacker can write a malicious model file to `run.model_path`,
  loading it will execute arbitrary Python code
- The file path comes from a database field that could be manipulated

**Attack Vector:**
1. Attacker gains access to write to knowledge-predictions directory
2. Replaces model file with malicious pickle containing `__reduce__` payload
3. When user runs apply prediction, pickle payload executes

**CVSS Score:** 7.8 (High)

**Remediation:**
```python
import hmac
import hashlib

# Add signature verification before loading
def _verify_model_signature(model_path: Path) -> bool:
    expected_sig = _load_expected_signature(model_path)
    actual_sig = hmac.new(MODEL_SIGNING_KEY, model_path.read_bytes(), hashlib.sha256).digest()
    return hmac.compare_digest(expected_sig, actual_sig)

# Before loading
if not _verify_model_signature(model_path):
    raise HTTPException(403, "Model signature verification failed")
    
trained_model = pykeen.models.Model.load_directory(str(model_path))
```

**Alternative Mitigation:**
- Store models in write-once location
- Add checksum/SRI verification
- Consider SafeUnpickle or restrict allowed classes

---

### 🟡 MEDIUM-1: Entity ID Enumeration

**Location:** `fichero-api/src/fichero/api/routes/knowledge_graph.py` (multiple endpoints)

**Issue:** Many endpoints accept entity/claim IDs directly without verifying access control:

```python
@router.post("/claims/{claim_id}/entities/{entity_id}")
async def link_claim_to_entity(..., claim_id: str, entity_id: str, ...) :
    claim = db.get(KnowledgeClaim, claim_id)  # No access check
    entity = db.get(KnowledgeEntity, entity_id)  # No access check
```

**Impact:**
- If multi-user support is added later, no isolation between users' knowledge graphs
- Could link claims/entities across library boundaries

**Risk Assessment:** Low in single-user deployment, higher in future multi-user scenarios.

**CVSS Score:** 5.3 (Medium)

**Remediation:**
Add library ownership verification:
```python
def _verify_entity_access(entity_id: str, db: Database) -> None:
    entity = db.get(KnowledgeEntity, entity_id)
    if not entity:
        raise HTTPException(404, "Entity not found")
    # Add ownership check when multi-user support added
    # if entity.library_id != current_user.library_id:
    #     raise HTTPException(403, "Access denied")
```

---

### 🟡 MEDIUM-2: Triple Construction (Information Disclosure)

**Location:** `fichero-api/src/fichero/api/routes/knowledge_graph.py` lines 1657-1685

**Issue:** Triple patterns are constructed from all claims without filtering:

```python
def _build_minimal_pykeen_triples(...):
    triples: list[tuple[str, str, str]] = []
    for claim in claims:  # All claims in library
        for entity_id in claim.entity_ids:
            triples.append((claim.id, "mentions", entity_id))
```

**Impact:**
- Training data includes all claims regardless of sensitivity
- No way to exclude confidential/private claims from ML training

**CVSS Score:** 4.3 (Medium)

**Remediation:**
Add flags to exclude claims from ML training:
```python
class KnowledgeClaim(BaseModel):
    ...
    exclude_from_ml: bool = False  # New field
    sensitivity: str = "public"  # "public", "private", "confidential"
```

---

### 🟢 LOW-1: Regex DoS in Validators

**Location:** `fichero-api/src/fichero/knowledge_models.py`

**Issue:** Input validators use regex patterns that could be vulnerable to ReDoS with malicious input:

```python
DOI_PATTERN = re.compile(r"^10\.\d{4,}/[^\s]+")  # Could backtrack
```

**Assessment:** Low risk - input length is bounded by Pydantic, patterns are relatively simple.

**CVSS Score:** 3.1 (Low)

**Remediation:** Add timeouts or use non-backtracking regex engines.

---

## Recommendations Summary

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| HIGH | PyKEEN pickle security | Medium | Code execution |
| MEDIUM | Entity ID enumeration | Low | Data privacy |
| MEDIUM | Triple construction | Low | Data leakage |
| LOW | Regex DoS | Low | Availability |

---

## Architecture Observations

### Positive Security Patterns
1. **Pydantic validators** ensure type safety and format validation
2. **No eval/exec/subprocess** usage in knowledge graph code
3. **Parameterized queries** (implicit via DuckDB)
4. **UUID-based identifiers** prevent predictable ID enumeration

### Areas for Improvement
1. **PyKEEN integration needs sandboxing** - pickle is inherently risky
2. **Missing multi-user isolation** - fine for single-user but not scalable
3. **No audit logging** for knowledge graph mutations

---

## Test Coverage

Current tests DO NOT cover:
- Malicious pickle model loading
- Cross-library claim/entity access
- Sensitive claim exclusion from training
- Resource limits on knowledge graph operations

---

## Conclusion

Phase 1 Knowledge Graph has a **significant security concern** with PyKEEN's pickle-based model loading. While this is acceptable for local single-user deployment, it should be documented and ideally mitigated before production use.

**Status:** Security concerns documented, no immediate fix required for single-user scenario.
