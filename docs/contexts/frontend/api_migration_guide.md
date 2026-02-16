# API Client Migration Guide

## Overview

This guide documents the migration from the legacy `APIClient` to the generated `FicheroAPIClient` using Swift OpenAPI Generator.

## Critical Architecture Note

**See TODO-125 and TODO-126 for workflow type cleanup tasks.**

The current codebase has ~1750 lines of redundant type conversion code because:
1. Ports are stored with nodes (should come from registry)
2. Property names don't match (source vs sourceNodeId)
3. Manual Swift types shadow generated types

After TODO-125 (Python cleanup), regenerate the OpenAPI spec and much of this guide becomes simpler.

## Migration Scope

Based on codebase analysis:
- **20 files** use the manual apiClient
- **106+ API calls** need migration
- **15 service files** are primary migration targets

### Files by Priority

**High Priority (16+ calls each):**
1. `AutomationService.swift` - 16 calls
2. `WorkflowService.swift` - 15 calls
3. `ProviderService.swift` - 14 calls
4. `ActivityService.swift` - 12 calls

**Medium Priority (6-11 calls):**
5. `DocumentService.swift` - 11 calls
6. `SavedSearchService.swift` - 7 calls
7. `ConversationService.swift` - 7 calls
8. `ChatService.swift` - 6 calls

**Low Priority (1-4 calls):**
9. `SearchService.swift` - 4 calls
10. `ModelService.swift` - 3 calls
11. `ImportService.swift` - 2 calls
12. `StorageService.swift` - 1 call
13. `MCPService.swift`
14. `ChainService.swift`
15. `WorkflowStreamService.swift`

**Direct View/Model Usage:**
- `SearchView.swift` - 1 call
- `ChatInspector.swift` - 2 calls
- `LibraryManager.swift` - 1 call

## Migration Strategy

### Phase 1: Coexistence (Current)

Both clients work side-by-side:
- Legacy `APIClient` continues working
- New `FicheroAPIClient` available for new code
- Services can be migrated gradually

### Phase 2: Service Migration

Migrate services one-by-one while maintaining the same public interface:

```swift
// Service interface stays the same
func listWorkflows() async throws -> [WorkflowResponse]

// Implementation changes from:
func listWorkflows() async throws -> [WorkflowResponse] {
    try await apiClient.get("/api/workflows")
}

// To:
func listWorkflows() async throws -> [WorkflowResponse] {
    let response = try await ficheroClient.api.listWorkflowsApiWorkflowsGet(.init())
    switch response {
    case .ok(let ok):
        return try ok.body.json.map { WorkflowResponse(from: $0) }
    default:
        throw APIError.unexpectedResponse
    }
}
```

### Phase 3: Cleanup

Once all services are migrated:
- Remove legacy `APIClient`
- Remove `APIEndpoints.swift` (replaced by generated code)
- Update tests

## Code Patterns

### Before (Legacy APIClient)

```swift
// Simple GET
let workflows: [WorkflowResponse] = try await apiClient.get("/api/workflows")

// GET with path parameter
let workflow: WorkflowDefinition = try await apiClient.get("/api/workflows/\(id)")

// POST with body
let response: WorkflowResponse = try await apiClient.post("/api/workflows", body: request)

// DELETE
try await apiClient.delete("/api/workflows/\(id)")

// PUT with body
let updated: WorkflowResponse = try await apiClient.put("/api/workflows/\(id)", body: workflow)
```

### After (Generated Client)

```swift
// Simple GET
let response = try await ficheroClient.api.listWorkflowsApiWorkflowsGet(.init())
guard case .ok(let ok) = response else { throw APIError.unexpectedResponse }
let workflows = try ok.body.json

// GET with path parameter
let response = try await ficheroClient.api.getWorkflowApiWorkflowsWorkflowIdGet(.init(
    path: .init(workflow_id: id)
))
guard case .ok(let ok) = response else { throw APIError.unexpectedResponse }
let workflow = try ok.body.json

// POST with body
let response = try await ficheroClient.api.createWorkflowApiWorkflowsPost(.init(
    body: .json(.init(name: name, description: description))
))
guard case .created(let created) = response else { throw APIError.unexpectedResponse }
let newWorkflow = try created.body.json

// DELETE
let response = try await ficheroClient.api.deleteWorkflowApiWorkflowsWorkflowIdDelete(.init(
    path: .init(workflow_id: id)
))
guard case .ok = response else { throw APIError.unexpectedResponse }

// PUT with body
let response = try await ficheroClient.api.updateWorkflowApiWorkflowsWorkflowIdPut(.init(
    path: .init(workflow_id: id),
    body: .json(workflowRequest)
))
guard case .ok(let ok) = response else { throw APIError.unexpectedResponse }
let updated = try ok.body.json
```

## Error Handling

### Legacy Pattern
```swift
do {
    let result: T = try await apiClient.get(path)
} catch APIError.notFound(let message) {
    // Handle 404
} catch APIError.badRequest(let message) {
    // Handle 400
}
```

### Generated Pattern
```swift
let response = try await client.api.someOperation(.init())
switch response {
case .ok(let ok):
    return try ok.body.json
case .notFound(let notFound):
    throw APIError.notFound(try notFound.body.json.detail)
case .unprocessableContent(let error):
    throw APIError.validationError(...)
default:
    throw APIError.unexpectedResponse
}
```

## Model Mapping

The generated types may differ from existing Swift models. Options:

1. **Use generated types directly** - Update views to use `Components.Schemas.WorkflowDef`
2. **Create mapping extensions** - Convert between generated and existing types
3. **Keep existing models** - Parse generated response into existing models

Example mapping:
```swift
extension WorkflowResponse {
    init(from generated: Components.Schemas.WorkflowResponse) {
        self.id = generated.id
        self.name = generated.name
        self.description = generated.description
        // ... map all fields
    }
}
```

## Testing Strategy

1. **Contract Tests** - Verify generated types match Python schema
2. **Service Tests** - Test each migrated service independently
3. **Integration Tests** - End-to-end with running backend

## Rollback Plan

If issues arise:
1. Revert service to use legacy `APIClient`
2. Both clients remain functional
3. Gradual migration continues

## Checklist Per Service

- [ ] Add `import FicheroAPIClient`
- [ ] Add `FicheroClient` property
- [ ] Update each API call to use generated method
- [ ] Handle response enums (ok, notFound, etc.)
- [ ] Map generated types to existing models if needed
- [ ] Update error handling
- [ ] Test service in isolation
- [ ] Test in app with running backend
