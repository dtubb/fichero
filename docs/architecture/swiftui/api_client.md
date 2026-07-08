(AI generated. Not reviewed.)

# Swift API Client - OpenAPI Generator

## Overview

The Fichero Swift frontend uses **Apple's Swift OpenAPI Generator** to create type-safe API clients from the Python backend's OpenAPI schema. This ensures Swift and Python stay in sync - the compiler catches mismatches.

## Architecture

```
Python FastAPI → OpenAPI Schema → Swift OpenAPI Generator → Type-safe Client
     ↓                ↓                      ↓                    ↓
  Pydantic      tests/contracts/       FicheroAPIClient/     Generated code
   models        openapi.json          (local package)       (Client.swift,
                                                              Types.swift)
```

## Key Files

### Swift Package
- `Fichero/FicheroAPIClient/Package.swift` - Package definition with dependencies
- `Fichero/FicheroAPIClient/Sources/FicheroAPIClient/openapi.json` - Schema (copied from Python)
- `Fichero/FicheroAPIClient/Sources/FicheroAPIClient/openapi-generator-config.yaml` - Generator config
- `Fichero/FicheroAPIClient/Sources/FicheroAPIClient/FicheroClient.swift` - Convenience wrapper

### Scripts
- `scripts/export_openapi_schema.py` - Exports schema from FastAPI
- `scripts/sync_openapi_schema.sh` - Syncs Python → Swift and rebuilds

### Contract Files
- `tests/contracts/openapi.json` - Full OpenAPI schema (source of truth)
- `tests/contracts/endpoints.json` - Simplified endpoint list for validation

## Usage

### Importing the Client

```swift
import FicheroAPIClient
import OpenAPIURLSession

let client = Client(
    serverURL: URL(string: "http://localhost:8765/api")!,
    transport: URLSessionTransport()
)
```

### Making API Calls

```swift
// List workflows
let response = try await client.listWorkflowsApiWorkflowsGet(.init())
switch response {
case .ok(let okResponse):
    let workflows = try okResponse.body.json
case .unprocessableContent(let error):
    // Handle validation error
default:
    // Handle other cases
}

// Create a workflow
let createResponse = try await client.createWorkflowApiWorkflowsPost(.init(
    body: .json(.init(name: "My Workflow", description: "..."))
))

// Delete a workflow
try await client.deleteWorkflowApiWorkflowsWorkflowIdDelete(.init(
    path: .init(workflow_id: workflowId)
))
```

### Method Naming Convention

Generated methods follow the pattern: `{operationId}` from OpenAPI spec.

| HTTP | Endpoint | Generated Method |
|------|----------|------------------|
| GET | /api/workflows | `listWorkflowsApiWorkflowsGet()` |
| POST | /api/workflows | `createWorkflowApiWorkflowsPost()` |
| GET | /api/workflows/{id} | `getWorkflowApiWorkflowsWorkflowIdGet()` |
| PUT | /api/workflows/{id} | `updateWorkflowApiWorkflowsWorkflowIdPut()` |
| DELETE | /api/workflows/{id} | `deleteWorkflowApiWorkflowsWorkflowIdDelete()` |

## Syncing When Python API Changes

When you modify Python endpoints or models:

```bash
./scripts/sync_openapi_schema.sh
```

This:
1. Exports fresh OpenAPI schema from Python
2. Converts nullable types for Swift compatibility (Pydantic v2 workaround)
3. Copies schema to Swift package
4. Rebuilds generated client

## Migration Strategy

### Old Approach (Manual)
```swift
// Fragile - can drift from Python
let workflow: WorkflowResponse = try await apiClient.post("/api/workflows", body: request)
try await apiClient.delete("/api/workflows/\(id)")
```

### New Approach (Generated)
```swift
// Type-safe - compiler catches mismatches
let response = try await client.createWorkflowApiWorkflowsPost(.init(body: .json(request)))
let workflow = try response.created.body.json

try await client.deleteWorkflowApiWorkflowsWorkflowIdDelete(.init(path: .init(workflow_id: id)))
```

### Migration Steps for a Service

1. Import `FicheroAPIClient` and `OpenAPIURLSession`
2. Add generated `Client` as a property
3. Replace `apiClient.get/post/put/delete` calls with generated methods
4. Handle response enums (`.ok`, `.created`, `.notFound`, etc.)
5. Update error handling for new response types

## Pydantic v2 Nullable Handling

Pydantic v2 generates OpenAPI 3.1 with `anyOf: [type, null]` for optional fields. Swift OpenAPI Generator shows warnings about this. The export script includes a post-processor that converts to OpenAPI 3.0 style (`nullable: true`) for better Swift compatibility.

This is a known limitation: [FastAPI Discussion #9900](https://github.com/fastapi/fastapi/discussions/9900)

## Dependencies

The FicheroAPIClient package depends on:
- `swift-openapi-generator` (build plugin)
- `swift-openapi-runtime` (runtime types)
- `swift-openapi-urlsession` (HTTP transport)

## Troubleshooting

### "OpenAPIGenerator is disabled" error
First build requires trusting the plugin:
1. Build in Xcode (Cmd+B)
2. Click the error in Issue Navigator
3. Click "Trust & Enable"
4. Build again

### Warnings about nullable schemas
These are informational. The post-processor handles most cases. If you see "skipping" warnings, the field may not be properly optional in generated Swift.

### Schema out of sync
Run `./scripts/sync_openapi_schema.sh` after any Python API changes.
