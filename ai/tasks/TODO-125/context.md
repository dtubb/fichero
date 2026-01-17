# TODO-125 Context: Workflow Type Architecture

## Current Architecture Issues

### Problem 1: Port Duplication

Ports are defined in the tool registry but duplicated to every node:

```python
# Tool Registry (correct single source)
"transcribe": {
    "input_ports": [{"id": "input", "name": "Files", ...}],
    "output_ports": [{"id": "text", "name": "Text", ...}]
}

# NodeDef in database (incorrectly stores copies)
{
    "id": "node-1",
    "tool": "transcribe",
    "input_ports": [{"id": "input", ...}],  # DUPLICATE - remove
    "output_ports": [{"id": "text", ...}],  # DUPLICATE - remove
    ...
}
```

### Problem 2: Property Name Mismatch

Python and Swift have different naming conventions:

| Python Model | Swift Expected | Issue |
|-------------|---------------|-------|
| `source` | `sourceNodeId` | Name mismatch |
| `target` | `targetNodeId` | Name mismatch |
| `usesLlm` | `usesLLM` | Case mismatch |

### Problem 3: Excessive Conversion Code

Files with redundant code:
- `WorkflowServiceGenerated.swift` (1050 lines)
  - `convertToToolInfo` (lines 416-450)
  - `convertNodeDefOutputToWorkflowNode` (lines 593-666)
  - `convertToGeneratedWorkflowDef` (lines 849-869)
  - `createNodeDef` (lines 871-942)
- `WorkflowTypes.swift` (~350 lines of manual types)
- `GeneratedTypeExtensions.swift` (~140 lines of bridging)

## Desired Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     PYTHON BACKEND                               │
├─────────────────────────────────────────────────────────────────┤
│  Tool Registry                                                   │
│  ├── Port definitions (single source of truth)                   │
│  ├── Tool metadata                                               │
│  └── Validation rules                                            │
│                                                                  │
│  Workflow Store (DuckDB)                                         │
│  ├── Minimal NodeDef: {id, tool, position, config, label}        │
│  └── EdgeDef: {id, source, target, sourcePort, targetPort}       │
│                                                                  │
│  API Layer                                                       │
│  ├── Returns minimal types                                       │
│  └── Enriches with ports only for tool palette/execution         │
│                                                                  │
│  LangGraph Builder                                               │
│  ├── Fetches ports from registry                                 │
│  └── Constructs executable graph                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/REST (minimal JSON)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SWIFT FRONTEND                               │
├─────────────────────────────────────────────────────────────────┤
│  Generated Types (from OpenAPI)                                  │
│  ├── Components.Schemas.NodeDefOutput                            │
│  └── Components.Schemas.EdgeDef                                  │
│                                                                  │
│  Minimal Extensions                                              │
│  ├── Identifiable conformances                                   │
│  └── Computed properties for compatibility                       │
│                                                                  │
│  Views use generated types directly                              │
│  └── No conversion layer needed                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Key Files Reference

### Python (to modify)
- `src/fichero/workflows/types.py:NodeDef` - Remove port storage
- `src/fichero/workflows/registry.py` - Port definitions (keep)
- `src/fichero/models.py` - Pydantic models for API
- `src/fichero/api/routes/workflows.py` - API endpoints

### Swift (will be simplified after Python changes)
- `Fichero/Models/WorkflowTypes.swift` - Manual types (to simplify/remove)
- `Fichero/Models/GeneratedTypeExtensions.swift` - Extensions (to simplify)
- `Fichero/Services/WorkflowServiceGenerated.swift` - Conversion code (to remove)

## Migration Strategy

1. **Phase 1**: Fix Python backend (TODO-125)
   - Remove port storage from NodeDef
   - Add enrichment function for execution
   - Fix property name aliases

2. **Phase 2**: Regenerate OpenAPI spec
   - Export new spec from FastAPI
   - Rebuild Swift OpenAPI package

3. **Phase 3**: Simplify Swift (TODO-126)
   - Remove manual types
   - Remove conversion functions
   - Use generated types directly
