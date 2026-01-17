# TODO-125: Refactor Workflow Types - Backend Port Cleanup

## Status: [ ] Available

## Priority: P0 (High)

## Category: Backend, Infrastructure

## Problem Statement

The workflow system has ~1750 lines of redundant conversion code because:

1. **Ports are stored with workflow nodes** - Ports are duplicated from the tool registry into every node, then transmitted over the API, when they should be fetched from the registry on-demand
2. **Property name mismatches** - Python uses `source`/`target`, but Swift views expect `sourceNodeId`/`targetNodeId`
3. **LangGraph conversion happens partially in Swift** - The Python backend should handle all graph construction

## Root Cause Analysis

### Current Flow (Inefficient)
```
Python Tool Registry → Stores ports in NodeDef → API Response includes all ports
→ Swift receives full NodeDefOutput → Swift converts to WorkflowNode
→ Swift converts back to NodeDefInput for saves → Round-trip conversion everywhere
```

### Ideal Flow
```
Python Tool Registry (single source of truth for ports)
→ API returns minimal NodeDef (tool, position, config)
→ Swift uses minimal types directly
→ Python enriches nodes from registry when needed for execution
```

## Implementation Steps

### Step 1: Audit Current Python Port Storage
- [ ] Review `src/fichero/workflows/types.py` - where NodeDef stores ports
- [ ] Review `src/fichero/workflows/registry.py` - where tool definitions live
- [ ] Review `src/fichero/db.py` - how workflows are persisted
- [ ] Document current flow with file:line references

### Step 2: Modify Python NodeDef Model
- [ ] Remove `input_ports` and `output_ports` from NodeDef storage
- [ ] Keep only: `id`, `tool`, `position_x`, `position_y`, `label`, `config`, `enabled`
- [ ] Update Pydantic models in `models.py` and `types.py`

### Step 3: Create Port Enrichment Layer
- [ ] Add `enrich_node_ports(node: NodeDef, registry: ToolRegistry)` function
- [ ] Call enrichment only when needed (execution, tool validation)
- [ ] Keep API responses minimal

### Step 4: Fix Property Name Sync
- [ ] In Python EdgeDef: rename or add aliases for `sourceNodeId`/`targetNodeId`
- [ ] In Python: standardize on snake_case internally, use Pydantic `alias` for API
- [ ] Regenerate OpenAPI spec after changes

### Step 5: Verify LangGraph Builder
- [ ] Ensure `src/fichero/workflows/builder.py` fetches ports from registry
- [ ] Ensure execution doesn't rely on stored ports
- [ ] Add tests for port enrichment

### Step 6: Update Tests
- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/unit/ --ignore=tests/unit/_archived`
- [ ] Fix any broken workflow tests
- [ ] Add specific tests for minimal NodeDef format

## Files to Modify

### Primary Files
- `src/fichero/workflows/types.py` - NodeDef definition
- `src/fichero/models.py` - Pydantic models
- `src/fichero/workflows/registry.py` - Tool registry
- `src/fichero/db.py` - Workflow persistence

### Secondary Files
- `src/fichero/workflows/builder.py` - LangGraph construction
- `src/fichero/api/routes/workflows.py` - API endpoints
- `tests/unit/test_workflow_*.py` - Unit tests

## Acceptance Criteria

1. [ ] NodeDef in database does NOT contain ports
2. [ ] API responses use minimal NodeDef format
3. [ ] Tool registry is single source of truth for port definitions
4. [ ] All Python tests pass
5. [ ] OpenAPI spec regenerated

## Dependencies

- None (this is foundational work)

## Blocked By

- None

## Blocks

- TODO-126: Swift Conversion Code Removal

## Notes

From code review session:
- `WorkflowServiceGenerated.swift` has ~700 lines of conversion functions
- Additional ~1050 lines in type definitions and extensions
- Total redundant code: ~1750 lines
- Root cause is Python sending too much data that Swift has to convert
