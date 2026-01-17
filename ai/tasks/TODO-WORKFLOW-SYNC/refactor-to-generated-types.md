# Refactor to Use Generated OpenAPI Types Directly

## Status: IN PROGRESS

## Goal
Eliminate manual Swift types and use Swift OpenAPI Generator types directly in views. This makes Python Pydantic models the true single source of truth.

## Current Architecture (BEFORE)
```
Python Pydantic → OpenAPI → Generated Types → Conversion Functions → Manual Types → Views
                            (Components.Schemas.*)    (extractXXX)     (WorkflowNode)
```

## Target Architecture (AFTER)
```
Python Pydantic → OpenAPI → Generated Types → Extensions → Views
                            (Components.Schemas.*)  (Identifiable, etc.)
```

## Phase 1: Fix Python API Response Types

The root cause: Python API returns `list[dict]` instead of typed `list[NodeDef]`.

**Files to update:**
- `src/fichero/api/routes/workflows.py` - Update `WorkflowResponse` to use typed `NodeDef`/`EdgeDef`

**Changes:**
```python
# BEFORE
class WorkflowResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]

# AFTER
class WorkflowResponse(BaseModel):
    nodes: list[NodeDef]
    edges: list[EdgeDef]
```

Then regenerate OpenAPI spec: `./scripts/sync_openapi_schema.sh`

## Phase 2: Create Swift Extensions for Generated Types

Create `Fichero/Fichero/Models/GeneratedTypeExtensions.swift`:
- Type aliases for readability (optional)
- `Identifiable` conformance where needed
- Convenience computed properties

## Phase 3: Update Swift Services

Update service files to pass generated types directly without conversion:
- `WorkflowServiceGenerated.swift` - Remove `extractWorkflowNode()`, `convertToToolInfo()`, etc.
- Other services as needed

## Phase 4: Update Swift Views

Replace manual types with generated types in view files:
- `Views/Workflow/*.swift` - Use `Components.Schemas.NodeDef` instead of `WorkflowNode`

## Phase 5: Clean Up

- Remove `WorkflowTypes.swift` (or keep only utility types like `AnyCodableValue`, `DraggedEdge`)
- Remove `validate_model_sync.py` (no longer needed)
- Update imports across codebase

## Type Mapping Reference

| Manual Swift Type | Generated Equivalent | Notes |
|-------------------|---------------------|-------|
| `WorkflowDefinition` | `Components.Schemas.WorkflowDef` | Need typed nodes/edges |
| `WorkflowNode` | `Components.Schemas.NodeDef` | Already exists, properly typed |
| `WorkflowEdge` | `Components.Schemas.EdgeDef` | Already exists |
| `ToolInfo` | `Components.Schemas.ToolResponse` | Already exists |
| `PortInfo` | `Components.Schemas.PortResponse` | Already exists |
| `CategoryTools` | `Components.Schemas.CategoryToolsResponse` | Already exists |
| `InputMapping` | `Components.Schemas.InputMapping` | Already exists |
| `OutputSchema` | `Components.Schemas.OutputSchema` | Already exists |
| `MCPServer` | `Components.Schemas.MCPServerResponse` | Already exists |
| `ScheduleInfo` | `Components.Schemas.ScheduleResponse` | Already exists |
| `TriggerInfo` | `Components.Schemas.TriggerResponse` | Already exists |
| `ActionItem` | `Components.Schemas.ActionResponse` | Already exists |

## Types to Keep (Swift-only)

- `AnyCodableValue` - Used for dynamic JSON in SwiftUI (keep or bridge to OpenAPIObjectContainer)
- `DraggedEdge` - UI-only drag state
- `AgentType` - Swift enum with computed properties for UI
- Custom error enums

## Execution Order

1. [ ] Fix Python `WorkflowResponse` to use typed arrays
2. [ ] Regenerate OpenAPI spec
3. [ ] Rebuild FicheroAPIClient package
4. [ ] Create `GeneratedTypeExtensions.swift`
5. [ ] Update `WorkflowServiceGenerated.swift`
6. [ ] Update workflow views one by one
7. [ ] Repeat for MCP, Automation, Actions
8. [ ] Remove unused manual types
9. [ ] Test thoroughly
