# FicheroAPIClient

Auto-generated Swift API client from the Python FastAPI backend's OpenAPI schema.

## Setup in Xcode

1. **Add Local Package to Xcode Project**:
   - In Xcode, select **File > Add Package Dependencies...**
   - Click **Add Local...**
   - Navigate to `Fichero/FicheroAPIClient`
   - Select the package and add to the Fichero target

2. **Import in Swift files**:
   ```swift
   import FicheroAPIClient
   ```

## Usage

### Basic Usage

```swift
import FicheroAPIClient
import OpenAPIURLSession

// Create client pointing to backend.
// NOTE: the engine serves HTTPS and the app pins it fail-closed (#2538).
// In the app, do NOT build a bare client here — use the shared `FicheroClient`,
// which wires the pinned TLS session (RemoteCertificatePinning) + engine auth.
let client = Client(
    serverURL: URL(string: "https://127.0.0.1:8765/api")!,
    transport: URLSessionTransport()
)

// List workflows
let response = try await client.listWorkflowsApiWorkflowsGet(.init())
switch response {
case .ok(let okResponse):
    let workflows = try okResponse.body.json
    print("Found \(workflows.count) workflows")
case .unprocessableContent(let error):
    print("Validation error: \(error)")
default:
    print("Unexpected response")
}
```

### Creating Resources

```swift
// Create a workflow
let createResponse = try await client.createWorkflowApiWorkflowsPost(.init(
    body: .json(.init(
        name: "My Workflow",
        description: "Description here"
    ))
))

switch createResponse {
case .created(let created):
    let workflow = try created.body.json
    print("Created workflow: \(workflow.id)")
case .unprocessableContent(let error):
    print("Validation error")
default:
    print("Error")
}
```

### With Path Parameters

```swift
// Get a specific workflow
let getResponse = try await client.getWorkflowApiWorkflowsWorkflowIdGet(.init(
    path: .init(workflow_id: "some-uuid")
))

// Delete a workflow
let deleteResponse = try await client.deleteWorkflowApiWorkflowsWorkflowIdDelete(.init(
    path: .init(workflow_id: "some-uuid")
))
```

## Migration from Manual APIClient

Before (manual):
```swift
// Old way - can drift from Python API
try await apiClient.post("/api/workflows", body: request)
try await apiClient.delete("/api/workflows/\(id)")
```

After (generated):
```swift
// New way - type-safe, always matches Python
try await client.createWorkflowApiWorkflowsPost(.init(body: .json(request)))
try await client.deleteWorkflowApiWorkflowsWorkflowIdDelete(.init(path: .init(workflow_id: id)))
```

Benefits:
- **Type-safe**: Compiler catches mismatches
- **Auto-complete**: All endpoints discoverable in Xcode
- **Always in sync**: Generated from same OpenAPI schema
- **Request/Response types**: No more Codable boilerplate

## Keeping in Sync

When the Python API changes (also runs automatically in `build-release.sh` and CI):

```bash
./fichero-server/scripts/sync_openapi_schema.sh
```

This:
1. Exports fresh OpenAPI schema from running Python API
2. Copies to Swift package
3. Rebuilds the generated client

## Generated Code

The generator creates:
- `Types.swift`: All request/response models as Swift structs
- `Client.swift`: API client with methods for each endpoint

Method names follow the pattern: `{operationId}` from the OpenAPI spec.
For example:
- `GET /api/workflows` -> `listWorkflowsApiWorkflowsGet()`
- `POST /api/workflows` -> `createWorkflowApiWorkflowsPost()`
- `DELETE /api/workflows/{id}` -> `deleteWorkflowApiWorkflowsWorkflowIdDelete()`

## Handling Optional Fields

Python optional fields (like `config: Optional[dict]`) are handled as Swift optionals.
The generator adds warnings for nullable schemas - these are informational and don't affect functionality.
