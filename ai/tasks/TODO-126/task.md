# TODO-126: Remove Swift Workflow Type Conversion Layer

## Status: [!] Blocked

## Priority: P1 (High)

## Category: Frontend, Infrastructure

## Blocked By: TODO-125 (Backend Port Cleanup)

## Problem Statement

Swift frontend has ~1750 lines of redundant type conversion code that exists only because:
1. Python sends ports with nodes (when they should come from registry)
2. Property names don't match between Python and Swift
3. Manual Swift types shadow generated OpenAPI types

Once TODO-125 is complete, this code can be removed.

## Implementation Steps

### Step 1: Regenerate Swift OpenAPI Types
- [ ] Export updated OpenAPI spec from FastAPI: `python -c "from fichero.api.main import app; import json; print(json.dumps(app.openapi()))" > openapi.json`
- [ ] Copy to FicheroAPIClient package
- [ ] Rebuild: `cd Fichero/FicheroAPIClient && swift build`
- [ ] Verify new types match minimal format

### Step 2: Remove Manual Type Definitions
- [ ] Archive `WorkflowTypes.swift` (move to archived folder)
- [ ] Or keep only types not generated (AgentType, AnyCodableValue if needed)
- [ ] Update Xcode project file references

### Step 3: Simplify GeneratedTypeExtensions.swift
- [ ] Keep only Identifiable conformances
- [ ] Remove bridging properties (sourceNodeId, etc.) - no longer needed
- [ ] Remove type aliases that conflict

### Step 4: Remove Conversion Functions in WorkflowServiceGenerated.swift
Functions to remove/simplify:
- [ ] `convertToToolInfo` (lines 416-450)
- [ ] `convertNodeDefOutputToWorkflowNode` (lines 593-666)
- [ ] `convertToGeneratedWorkflowDef` (lines 849-869)
- [ ] `createNodeDef` (lines 871-942)
- [ ] `convertPortDef` helpers
- [ ] `convertEdgeDefToWorkflowEdge`

Expected reduction: ~700 lines

### Step 5: Update Views to Use Generated Types
- [ ] WorkflowCanvasView - use `Components.Schemas.NodeDefOutput` directly
- [ ] WorkflowNodeView - update node parameter types
- [ ] WorkflowEditor - update workflow handling
- [ ] NodePopover - update node configuration
- [ ] Preview providers - update sample data

### Step 6: Update Xcode Project
- [ ] Remove archived file references
- [ ] Fix any missing file issues
- [ ] Clean build folder

### Step 7: Build and Test
- [ ] `xcodebuild -project Fichero/Fichero.xcodeproj -scheme Fichero -configuration Debug`
- [ ] Fix any build errors
- [ ] Run SwiftLint: `swiftlint lint --path Fichero/Fichero/`
- [ ] Manual testing of workflow editor

## Files to Modify

### Files to Simplify/Remove
- `Fichero/Models/WorkflowTypes.swift` - archive or remove most content
- `Fichero/Models/GeneratedTypeExtensions.swift` - keep minimal extensions only
- `Fichero/Services/WorkflowServiceGenerated.swift` - remove conversion functions

### Files to Update
- `Fichero/Views/Workflow/WorkflowCanvasView.swift`
- `Fichero/Views/Workflow/WorkflowNodeView.swift`
- `Fichero/Views/Workflow/WorkflowEditor.swift`
- `Fichero/Views/Workflow/NodePopover.swift`
- All preview providers using WorkflowNode

## Expected Benefits

1. **Code Reduction**: ~1750 lines removed
2. **Type Safety**: Single source of truth from OpenAPI
3. **Maintenance**: No manual type sync needed
4. **Performance**: Less object conversion at runtime

## Acceptance Criteria

1. [ ] Build succeeds with no errors
2. [ ] SwiftLint passes
3. [ ] Workflow editor loads and displays nodes
4. [ ] Can create, edit, delete workflows
5. [ ] Can execute workflows
6. [ ] No manual type conversion in service layer

## Rollback Plan

If issues arise:
1. Restore WorkflowTypes.swift from archive
2. Restore GeneratedTypeExtensions.swift
3. Both manual and generated types can coexist

## Notes

This task cannot start until TODO-125 is complete because:
- Generated types will change when Python models change
- Property names must match before removing bridging code
- Ports must be removed from NodeDef before simplifying Swift
