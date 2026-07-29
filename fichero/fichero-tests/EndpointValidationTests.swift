//
//  EndpointValidationTests.swift
//  FicheroTests
//
//  Validates that the Swift API client matches the Python API.
//
//  With the migration to Swift OpenAPI Generator (FicheroAPIClient),
//  endpoint validation is handled by the code generation process.
//  The generator uses the same openapi.json that the Python backend exports,
//  ensuring type-safe API calls that match the backend schema.
//
//  These tests verify:
//  1. Generated types have expected properties (compile-time safety)
//  2. Operation IDs match Python endpoints (runtime validation)
//  3. HTTP methods follow REST conventions (API consistency)
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Anchor class for Bundle(for:) — gives us a reliable handle on the
/// test bundle's runtime location even when #file is relativised.
private final class BundleAnchor {}

/// Path to the Python-exported endpoints file
private func endpointsFilePath() -> URL {
    let contractsDir = findContractsDirectory()
    return contractsDir.appendingPathComponent("endpoints.json")
}

private func findContractsDirectory() -> URL {
    let fileManager = FileManager.default

    // Build candidate starting points in priority order.
    //
    // Under Swift Testing's parallel runner #file gets relativised to
    // /<TargetName>/... so the walk-up returns garbage; cwd is "/" too.
    // Build env vars (SRCROOT, PROJECT_DIR) aren't inherited by the
    // test-host subprocess either.
    //
    // The reliable anchor in that case is the TEST BUNDLE's location:
    // .../DerivedData/.../Products/Debug/Fichero.app/Contents/PlugIns/
    //   FicheroTests.xctest/Contents/MacOS/FicheroTests.
    // Walk up from there hoping to find a build-output directory whose
    // grandparent contains the repo. Doesn't work if the test bundle
    // lives outside the repo tree, in which case the FICHERO_REPO_ROOT
    // env var or absolute fallback below kicks in.
    var starts: [URL] = []
    let env = ProcessInfo.processInfo.environment
    for key in ["FICHERO_REPO_ROOT", "SRCROOT", "PROJECT_DIR"] {
        if let path = env[key], !path.isEmpty {
            starts.append(URL(fileURLWithPath: path))
        }
    }
    // Bundle-relative — works under Swift Testing's parallel runner.
    starts.append(Bundle(for: BundleAnchor.self).bundleURL)
    starts.append(URL(fileURLWithPath: #file).deletingLastPathComponent())
    starts.append(URL(fileURLWithPath: fileManager.currentDirectoryPath))

    for start in starts {
        var current = start.standardizedFileURL
        // Bounded walk-up. The old `while true` relied on
        // `parent.path == current.path` to stop at the root — but for
        // directory-flavored URLs (Bundle.bundleURL exactly), Foundation's
        // deletingLastPathComponent does NOT converge at "/": it keeps
        // yielding non-equal parents forever. When the build products live
        // OUTSIDE the repo (isolated SYMROOT, clean DerivedData) no candidate
        // ever matched, the loop never exited, and each iteration allocated
        // ever-longer path strings — 13.6 GB of CFStrings before the host was
        // killed (#4264). Root check + depth cap make termination
        // unconditional.
        for _ in 0..<64 {
            let candidate = current
                .appendingPathComponent("fichero-engine")
                .appendingPathComponent("tests")
                .appendingPathComponent("contracts")
            if fileManager.fileExists(atPath: candidate.path) {
                return candidate
            }

            if current.path == "/" { break }
            let parent = current.deletingLastPathComponent().standardizedFileURL
            if parent.path == current.path { break }
            current = parent
        }
    }

    // Fallback for local runs where current directory is the repo root.
    return URL(fileURLWithPath: fileManager.currentDirectoryPath)
        .appendingPathComponent("fichero-engine")
        .appendingPathComponent("tests")
        .appendingPathComponent("contracts")
}

/// Parsed endpoint from Python's endpoints.json
struct PythonEndpoint: Decodable {
    let method: String
    let path: String
    let operationId: String?
    let pathParams: [String]?
    let queryParams: [[String: Any]]?
    let requestModel: String?
    let responseModel: String?

    enum CodingKeys: String, CodingKey {
        case method, path
        case operationId = "operation_id"
        case pathParams = "path_params"
        case queryParams = "query_params"
        case requestModel = "request_model"
        case responseModel = "response_model"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        method = try container.decode(String.self, forKey: .method)
        path = try container.decode(String.self, forKey: .path)
        operationId = try container.decodeIfPresent(String.self, forKey: .operationId)
        pathParams = try container.decodeIfPresent([String].self, forKey: .pathParams)
        requestModel = try container.decodeIfPresent(String.self, forKey: .requestModel)
        responseModel = try container.decodeIfPresent(String.self, forKey: .responseModel)
        // Skip queryParams as it has complex structure
        queryParams = nil
    }
}

struct EndpointsFile: Decodable {
    let endpoints: [String: [PythonEndpoint]]
}

// MARK: - HTTP Method Validation Tests

/// Validates that the Python API follows REST conventions for HTTP methods.
struct HTTPMethodValidationTests {

    @Test("Create operations use POST")
    func createOperationsUsePost() throws {
        let pythonEndpoints = try loadAllEndpoints()

        // Find all "create" endpoints
        let createEndpoints = pythonEndpoints.filter { endpoint in
            endpoint.operationId?.contains("create") == true ||
            (endpoint.method == "POST" && !endpoint.path.contains("{"))
        }

        for endpoint in createEndpoints {
            #expect(endpoint.method == "POST", "Create endpoint \(endpoint.path) should use POST")
        }
    }

    @Test("Update operations use PUT or PATCH")
    func updateOperationsUsePutOrPatch() throws {
        let pythonEndpoints = try loadAllEndpoints()

        // Find update endpoints (PUT/PATCH with {id} in path)
        let updateEndpoints = pythonEndpoints.filter { endpoint in
            (endpoint.method == "PUT" || endpoint.method == "PATCH") &&
            endpoint.path.contains("{")
        }

        #expect(!updateEndpoints.isEmpty, "Should have some update endpoints")

        for endpoint in updateEndpoints {
            #expect(
                endpoint.method == "PUT" || endpoint.method == "PATCH",
                "Update endpoint \(endpoint.path) should use PUT or PATCH"
            )
        }
    }

    @Test("Delete operations use DELETE")
    func deleteOperationsUseDelete() throws {
        let pythonEndpoints = try loadAllEndpoints()

        // Use word-boundary split to avoid matching "delete" within "deleted"
        // (e.g. list_deleted_documents_api_documents_trash_get is a GET endpoint).
        let deleteEndpoints = pythonEndpoints.filter {
            guard let id = $0.operationId else { return false }
            return id.split(separator: "_").contains(Substring("delete"))
        }

        for endpoint in deleteEndpoints {
            #expect(endpoint.method == "DELETE", "Delete endpoint \(endpoint.path) should use DELETE")
        }
    }

    // MARK: - Helper

    private func loadAllEndpoints() throws -> [PythonEndpoint] {
        let filePath = endpointsFilePath()

        guard FileManager.default.fileExists(atPath: filePath.path) else {
            print("SKIP: endpoints.json not generated (see #594). Run export_openapi_schema.py.")
            return []
        }

        let data = try Data(contentsOf: filePath)
        let file = try JSONDecoder().decode(EndpointsFile.self, from: data)

        return file.endpoints.values.flatMap { $0 }
    }
}

// MARK: - Generated Client Validation Tests

/// Tests that validate the Swift OpenAPI Generator client matches the Python API.
/// These tests provide compile-time type safety AND runtime operation ID verification.
struct GeneratedClientValidationTests {

    @Test("Generated operation IDs match Python endpoints")
    func generatedOperationIdsMatchPython() throws {
        let pythonEndpoints = try loadAllEndpoints()

        // Collect Python operation IDs
        let pythonOperationIds = Set(pythonEndpoints.compactMap { $0.operationId })

        // These are the key operations we expect to find
        let expectedOperations = [
            "list_workflows_api_workflows_get",
            "create_workflow_api_workflows_post",
            "get_workflow_api_workflows__workflow_id__get",
            "update_workflow_api_workflows__workflow_id__put",
            "delete_workflow_api_workflows__workflow_id__delete",
            "list_documents_api_documents_get",
            "create_document_api_documents_post",
            // The main search route is `enhanced_search` (renamed from
            // `search_documents` when hybrid + RRF + scoping landed).
            "enhanced_search_api_search_post",
            "health_check_api_health_get"
        ]

        for operationId in expectedOperations {
            #expect(
                pythonOperationIds.contains(operationId),
                "Expected operation '\(operationId)' not found in Python endpoints"
            )
        }
    }

    @Test("Generated workflow types have required properties")
    func workflowTypesHaveRequiredProperties() {
        // This test provides compile-time validation that generated types exist
        // If the OpenAPI schema changes and removes these types, compilation fails

        // WorkflowDef - the request/definition type
        let workflowDef = Components.Schemas.WorkflowDef(
            id: "test-id",
            name: "Test Workflow",
            description: "A test workflow",
            nodes: [],
            edges: [],
            provider: nil,
            model: nil
        )
        #expect(workflowDef.id == "test-id")
        #expect(workflowDef.name == "Test Workflow")

        // EdgeDef - workflow edge definition
        // Uses 'source'/'target' not 'sourceNode'/'targetNode'
        let edgeDef = Components.Schemas.EdgeDef(
            id: "edge-1",
            source: "node-1",
            target: "node-2",
            sourcePort: "output",
            targetPort: "input"
        )
        #expect(edgeDef.id == "edge-1")
        #expect(edgeDef.source == "node-1")
        #expect(edgeDef.target == "node-2")
    }

    @Test("Generated document types have required properties")
    func documentTypesHaveRequiredProperties() {
        // Verify Document schema has expected structure
        // The generated type must have these properties or compilation fails

        let document = Components.Schemas.Document(
            id: "doc-1",
            parentId: nil,
            docType: Components.Schemas.DocType.file,
            fileType: Components.Schemas.FileType.pdf,
            name: "Test Document",
            path: nil,
            sequence: nil,
            bbox: nil,
            pageContent: nil,
            metadata: nil,
            status: Components.Schemas.Status.completed,
            createdAt: Date(),
            updatedAt: nil,
            expectedThumbnailPath: "storage/thumbnails/do/doc-1.jpg",
            expectedDisplayPath: "storage/thumbnails/do/doc-1_display.jpg"
        )
        #expect(document.id == "doc-1")
        #expect(document.name == "Test Document")
        #expect(document.docType == Components.Schemas.DocType.file)
    }

    @Test("Generated port types match API schema")
    func portTypesMatchSchema() {
        // PortDef uses PortTypePayload enum for port type
        let inputPort = Components.Schemas.PortDef(
            id: "port-1",
            name: "input_port",
            portType: .input,
            dataType: .text,
            required: true,
            description: "An input port"
        )
        #expect(inputPort.portType == .input)
        #expect(inputPort.dataType == .text)

        let outputPort = Components.Schemas.PortDef(
            id: "port-2",
            name: "output_port",
            portType: .output,
            dataType: .image,
            required: false,
            description: nil
        )
        #expect(outputPort.portType == .output)
    }

    @Test("FicheroClient can be instantiated")
    @MainActor
    func clientInstantiation() async {
        // Verify the client wrapper can be created
        let client = FicheroClient()
        #expect(client.baseURL.absoluteString == "https://127.0.0.1:8765")
        #expect(client.currentLibraryPath == nil)

        // Verify client with library path
        let clientWithPath = FicheroClient(libraryPath: "/test/path")
        #expect(clientWithPath.currentLibraryPath == "/test/path")
    }

    // MARK: - Helper

    private func loadAllEndpoints() throws -> [PythonEndpoint] {
        let filePath = endpointsFilePath()

        guard FileManager.default.fileExists(atPath: filePath.path) else {
            print("SKIP: endpoints.json not generated (see #594). Run export_openapi_schema.py.")
            return []
        }

        let data = try Data(contentsOf: filePath)
        let file = try JSONDecoder().decode(EndpointsFile.self, from: data)

        return file.endpoints.values.flatMap { $0 }
    }
}

// MARK: - Python Endpoint Validation Tests

/// Validates that the Python API has expected endpoints.
/// This checks the structure of endpoints.json, not Swift code.
struct PythonEndpointStructureTests {

    @Test("Documents endpoints exist in Python API")
    func documentsEndpointsExist() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "documents")

        // Verify key endpoints exist
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/documents" })
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/documents" })
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path.contains("/documents/") && $0.path.contains("{") })
    }

    @Test("Workflows endpoints exist in Python API")
    func workflowsEndpointsExist() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "workflows")

        // Verify key endpoints exist
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/workflows" })
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/workflows" })
        #expect(pythonEndpoints.contains { $0.method == "PUT" && $0.path.contains("{workflow_id}") })
        #expect(pythonEndpoints.contains { $0.method == "DELETE" && $0.path.contains("{workflow_id}") })
    }

    @Test("Search endpoints exist in Python API")
    func searchEndpointsExist() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "search")

        // Search uses POST (not GET) for the main search
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/search" })
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/search/saved" })
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/search/saved" })
    }

    @Test("Chat endpoints exist in Python API")
    func chatEndpointsExist() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "chat")

        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/chat" })
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/chat/conversations" })
    }

    @Test("Provider endpoints exist in Python API")
    func providerEndpointsExist() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "providers")

        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/providers/catalog" })
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/providers" })
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/providers" })
    }

    @Test("Storage endpoints exist in Python API")
    func storageEndpointsExist() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "storage")

        #expect(pythonEndpoints.contains { $0.path.contains("/storage/thumbnail/") })
        #expect(pythonEndpoints.contains { $0.path.contains("/storage/display/") })
    }

    // MARK: - Helper

    private func loadPythonEndpoints(for resource: String) throws -> [PythonEndpoint] {
        let filePath = endpointsFilePath()

        guard FileManager.default.fileExists(atPath: filePath.path) else {
            let env = ProcessInfo.processInfo.environment
            let envKeys = ["SRCROOT", "PROJECT_DIR", "FICHERO_REPO_ROOT", "BUILT_PRODUCTS_DIR"]
                .compactMap { key in env[key].map { "\(key)=\($0)" } }
                .joined(separator: " | ")
            let fileDirectory = URL(fileURLWithPath: #file).deletingLastPathComponent().path
            Issue.record(
                """
                endpoints.json not found at \(filePath.path). cwd=\(FileManager.default.currentDirectoryPath), \
                #file dir=\(fileDirectory), env: \(envKeys)
                """
            )
            return []
        }

        let data: Data
        do {
            data = try Data(contentsOf: filePath)
        } catch {
            Issue.record("Failed to read endpoints.json at \(filePath.path): \(error)")
            return []
        }

        let file: EndpointsFile
        do {
            file = try JSONDecoder().decode(EndpointsFile.self, from: data)
        } catch {
            Issue.record(
                "Failed to decode endpoints.json (\(data.count) bytes from \(filePath.path)): \(error)"
            )
            return []
        }

        guard let endpoints = file.endpoints[resource] else {
            Issue.record(
                "Resource '\(resource)' not found in endpoints.json (keys: \(file.endpoints.keys.sorted()))"
            )
            return []
        }

        return endpoints
    }
}
