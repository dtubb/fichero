# Implementation Plan: Workflow Type Cleanup (TODO-125)

## Code Review Summary

### Python Backend Issues Found

**File: `src/fichero/workflows/types.py`**

1. **Lines 164-172**: NodeDef stores `input_ports` and `output_ports`
   - These are duplicated from the tool registry
   - Should be removed from storage, enriched at runtime

2. **Line 210**: Property `uses_llm` (snake_case)
   - Swift expects `usesLLM` (camelCase with uppercase acronym)
   - Need Pydantic alias for serialization

3. **Lines 233-234**: EdgeDef uses `source`/`target`
   - Swift views expect `sourceNodeId`/`targetNodeId`
   - Need Pydantic aliases for serialization

**File: `src/fichero/workflows/registry.py`**

4. **Lines 147-180**: `create_node_from_tool()` copies ports from tool to node
   - This is the root cause of port duplication
   - Should NOT copy ports to node

### Swift Frontend Issues Found

**File: `Fichero/Services/WorkflowServiceGenerated.swift`**

5. **Lines 593-666**: `convertNodeDefOutputToWorkflowNode()` - 74 lines of conversion
   - Exists only because generated types have different property names
   - Will be unnecessary after Python aliases added

6. **Lines 871-942**: `createNodeDef()` - 72 lines
   - Manually constructs NodeDefInput from WorkflowNode
   - Will be simplified after Python changes

**File: `Fichero/Models/WorkflowTypes.swift`**

7. Manual type definitions shadow generated types
   - `WorkflowNode` conflicts with what could be a direct use of generated type
   - `PortInfo` duplicates generated `PortDef`

## Implementation Steps

### Phase 1: Python Backend Changes

#### Step 1.1: Add Property Aliases to NodeDef

```python
# In types.py, update NodeDef class:

class NodeDef(BaseModel):
    # ... existing fields ...

    # Property with alias for Swift compatibility
    uses_llm: bool = Field(
        default=False,
        alias="usesLlm",  # Swift/JSON serialization name
        serialization_alias="usesLlm"
    )

    class Config:
        populate_by_name = True
```

#### Step 1.2: Add Property Aliases to EdgeDef

```python
# In types.py, update EdgeDef class:

class EdgeDef(BaseModel):
    source: str = Field(
        ...,
        alias="sourceNodeId",
        serialization_alias="source"  # Keep internal as source
    )
    target: str = Field(
        ...,
        alias="targetNodeId",
        serialization_alias="target"
    )
```

**Alternative approach**: Since this is an API change, we could instead keep `source`/`target` in Python and add computed properties in Swift. The current `GeneratedTypeExtensions.swift` already has this with `sourceNodeId` computed property.

**Decision**: Keep Python canonical names (`source`, `target`, `uses_llm`), use Swift extensions for compatibility. This is already partially done.

#### Step 1.3: Remove Port Storage from NodeDef

This is the bigger change. Options:

**Option A: Remove ports entirely from NodeDef**
- Pros: Clean, minimal storage
- Cons: Breaking change, requires frontend update

**Option B: Make ports optional, deprecate**
- Pros: Backwards compatible
- Cons: Code complexity

**Recommended: Option A with migration**

```python
# In types.py, update NodeDef:

class NodeDef(BaseModel):
    id: str = Field(default_factory=_new_id)
    tool: str = Field(...)

    # REMOVED: input_ports, output_ports
    # Ports now come from registry via enrich_node_ports()

    input_mappings: list[InputMapping] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    output_schema: OutputSchema | None = None

    position_x: float = 0.0
    position_y: float = 0.0

    label: str = ""
    description: str = ""
    enabled: bool = True

    provider_name: str = ""
    model_name: str = ""
    uses_llm: bool = False
```

#### Step 1.4: Create Port Enrichment Function

```python
# In registry.py, add:

def enrich_node_ports(node: NodeDef) -> NodeDefWithPorts:
    """Add ports to a node from the tool registry.

    Used for:
    - Execution (to validate connections)
    - UI display (to show port names)

    NOT stored in database.
    """
    tool_def = get_tool_def(node.tool)
    if not tool_def:
        return NodeDefWithPorts(
            **node.model_dump(),
            input_ports=[],
            output_ports=[]
        )

    return NodeDefWithPorts(
        **node.model_dump(),
        input_ports=tool_def.input_ports,
        output_ports=tool_def.output_ports
    )


class NodeDefWithPorts(NodeDef):
    """NodeDef enriched with ports from registry. Not persisted."""
    input_ports: list[PortDef] = Field(default_factory=list)
    output_ports: list[PortDef] = Field(default_factory=list)
```

#### Step 1.5: Update API Routes

```python
# In routes/workflows.py:

@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str) -> WorkflowResponse:
    workflow = await store.get_workflow(workflow_id)

    # Enrich nodes with ports for UI
    enriched_nodes = [
        enrich_node_ports(node) for node in workflow.nodes
    ]

    return WorkflowResponse(
        **workflow.model_dump(exclude={"nodes"}),
        nodes=enriched_nodes
    )
```

#### Step 1.6: Update create_node_from_tool()

```python
# In registry.py, update:

def create_node_from_tool(tool_name: str, position_x: float = 0, position_y: float = 0) -> NodeDef | None:
    """Create a new node instance from a tool definition.

    Note: Does NOT include ports - ports come from registry at runtime.
    """
    tool_def = get_tool_def(tool_name)
    if not tool_def:
        return None

    return NodeDef(
        id=uuid.uuid4().hex,
        tool=tool_name,
        position_x=position_x,
        position_y=position_y,
        label=tool_def.display_name,
        uses_llm=tool_def.uses_llm,
        # NO ports - they're fetched from registry when needed
    )
```

### Phase 2: Regenerate OpenAPI Spec

```bash
# After Python changes:
./scripts/sync_openapi_schema.sh

# Or manually:
cd /Users/dtubb/code/fichero_main/fichero
python -c "from fichero.api.main import app; import json; print(json.dumps(app.openapi(), indent=2))" > tests/contracts/openapi.json
```

### Phase 3: Swift Frontend Simplification (TODO-126)

After Phase 2, generated Swift types will have correct structure.

1. Remove manual types from `WorkflowTypes.swift`
2. Simplify `GeneratedTypeExtensions.swift`
3. Remove conversion functions from `WorkflowServiceGenerated.swift`
4. Update views to use generated types directly

## Testing Plan

### Backend Tests

```bash
# Run existing tests
PYTHONPATH=src .venv/bin/pytest tests/unit/test_workflow*.py -v

# Add new tests
# - test_node_without_ports_persists()
# - test_enrich_node_ports()
# - test_api_returns_enriched_nodes()
```

### Frontend Tests

```bash
# Build after changes
xcodebuild -project Fichero/Fichero.xcodeproj -scheme Fichero -configuration Debug

# Run SwiftLint
swiftlint lint --path Fichero/Fichero/
```

### Integration Tests

1. Create workflow via UI
2. Save workflow
3. Load workflow
4. Verify nodes have ports in UI
5. Execute workflow
6. Verify results

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Existing workflows break | Medium | High | Migration script to strip ports |
| Swift type mismatches | Low | Medium | Keep bridging extensions until stable |
| Execution fails without ports | Low | High | Always enrich before execution |

## Rollback Plan

If issues arise:
1. Revert Python changes
2. Keep ports in NodeDef
3. Swift bridging code remains necessary

## Timeline Estimate

- Phase 1 (Python): 2-4 hours
- Phase 2 (Regenerate): 15 minutes
- Phase 3 (Swift): 2-4 hours (separate task TODO-126)
- Testing: 1-2 hours

Total: ~8 hours of focused work
