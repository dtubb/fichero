# TODO-126 Context: Swift Type Conversion Analysis

## Current Code to Remove

### WorkflowServiceGenerated.swift Conversion Functions

```swift
// Lines 416-450: Tool conversion
private func convertToToolInfo(_ apiTool: ...) -> ToolInfo

// Lines 593-666: Node conversion (74 lines)
private func convertNodeDefOutputToWorkflowNode(_ node: ...) -> WorkflowNode

// Lines 849-869: Workflow definition conversion
private func convertToGeneratedWorkflowDef(_ workflow: Workflow) -> ...

// Lines 871-942: Node definition creation (72 lines)
private func createNodeDef(from node: WorkflowNode, ...) -> NodeDefInput
```

### WorkflowTypes.swift Manual Types

Currently defines:
- `WorkflowNode` (shadows generated type)
- `WorkflowEdge` (shadows generated type)
- `PortInfo` (shadows generated type)
- `ToolInfo` (shadows generated type)
- `InputMapping` (shadows generated type)
- `OutputSchema` (shadows generated type)
- `AnyCodableValue` (might still be needed for config)
- `AgentType` (might still be needed)

### GeneratedTypeExtensions.swift Bridging

Currently has:
- Type aliases that conflict with manual types
- Bridging computed properties for name mismatches
- Identifiable conformances (keep these)

## After Cleanup

### WorkflowServiceGenerated.swift (Target)

```swift
// Direct usage of generated types - no conversion
func listWorkflows() async throws -> [Components.Schemas.WorkflowResponse] {
    let response = try await ficheroClient.api.listWorkflows()
    guard case .ok(let ok) = response else { throw error }
    return try ok.body.json
}

func getWorkflow(id: String) async throws -> Components.Schemas.WorkflowResponse {
    let response = try await ficheroClient.api.getWorkflow(path: .init(workflow_id: id))
    guard case .ok(let ok) = response else { throw error }
    return try ok.body.json
}
```

### GeneratedTypeExtensions.swift (Target)

```swift
// Only Identifiable conformances and minimal computed properties
extension Components.Schemas.NodeDefOutput: Identifiable {
    public var id: String { self.id ?? "node-\(tool)" }
}

extension Components.Schemas.EdgeDef: Identifiable {
    public var id: String { self.id ?? "edge-\(source)-\(target)" }
}

extension Components.Schemas.WorkflowResponse: Identifiable {}
extension Components.Schemas.ToolResponse: Identifiable {
    public var id: String { name }
}
```

### Views (Target)

```swift
// Before
struct WorkflowNodeView: View {
    let node: WorkflowNode  // manual type
    ...
}

// After
struct WorkflowNodeView: View {
    let node: Components.Schemas.NodeDefOutput  // generated type
    ...
}
```

## Type Mapping Reference

| Manual Type | Generated Type | Action |
|------------|----------------|--------|
| `Workflow` | `Components.Schemas.WorkflowResponse` | Use generated |
| `WorkflowNode` | `Components.Schemas.NodeDefOutput` | Use generated |
| `WorkflowEdge` | `Components.Schemas.EdgeDef` | Use generated |
| `PortInfo` | `Components.Schemas.PortDef` | Use generated |
| `ToolInfo` | `Components.Schemas.ToolResponse` | Use generated |
| `InputMapping` | `Components.Schemas.InputMapping` | Use generated |
| `OutputSchema` | `Components.Schemas.OutputSchema` | Use generated |
| `AnyCodableValue` | varies | Keep if needed for config |
| `AgentType` | not generated | Keep |

## Build Verification Commands

```bash
# Clean and rebuild
cd Fichero
rm -rf ~/Library/Developer/Xcode/DerivedData/Fichero-*
xcodebuild -project Fichero.xcodeproj -scheme Fichero clean

# Rebuild FicheroAPIClient
cd FicheroAPIClient
swift build

# Build main project
cd ..
xcodebuild -project Fichero.xcodeproj -scheme Fichero -configuration Debug

# Run SwiftLint
swiftlint lint --path Fichero/
```

## Preview Provider Updates

Each preview using `WorkflowNode` will need updating:

```swift
// Before
#Preview {
    WorkflowNodeView(
        node: WorkflowNode(
            tool: "transcribe",
            label: "Test",
            positionX: 0,
            positionY: 0
        ),
        ...
    )
}

// After
#Preview {
    WorkflowNodeView(
        node: .init(
            id: "test-1",
            tool: "transcribe",
            inputPorts: [],
            outputPorts: [],
            positionX: 0,
            positionY: 0,
            label: "Test"
        ),
        ...
    )
}
```
