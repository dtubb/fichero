//
//  EndpointValidationTests.swift
//  FicheroTests
//
//  Validates that Swift's APIEndpoints match the Python API.
//  This catches endpoint drift between frontend and backend.
//

import Foundation
import Testing
@testable import Fichero

/// Path to the Python-exported endpoints file
private func endpointsFilePath() -> URL {
    // From: Fichero/FicheroTests/EndpointValidationTests.swift
    // To: tests/contracts/endpoints.json
    let thisFile = URL(fileURLWithPath: #file)
    return thisFile
        .deletingLastPathComponent()  // FicheroTests
        .deletingLastPathComponent()  // Fichero
        .deletingLastPathComponent()  // Fichero (project folder)
        .appendingPathComponent("tests")
        .appendingPathComponent("contracts")
        .appendingPathComponent("endpoints.json")
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

// MARK: - Endpoint Path Validation Tests

struct EndpointPathValidationTests {

    @Test("Documents endpoints match Python API")
    func documentsEndpoints() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "documents")

        // Verify key endpoints exist
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/documents" })
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/documents" })
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path.contains("/documents/") && $0.path.contains("{") })

        // Verify Swift constants match
        #expect(APIEndpoints.Documents.list == "/documents")
        #expect(APIEndpoints.Documents.create == "/documents")
        #expect(APIEndpoints.Documents.collections == "/documents/collections")
    }

    @Test("Workflows endpoints match Python API")
    func workflowsEndpoints() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "workflows")

        // Verify key endpoints exist
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/workflows" })
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/workflows" })
        #expect(pythonEndpoints.contains { $0.method == "PUT" && $0.path.contains("{workflow_id}") })
        #expect(pythonEndpoints.contains { $0.method == "DELETE" && $0.path.contains("{workflow_id}") })

        // Verify Swift constants match
        #expect(APIEndpoints.Workflows.list == "/workflows")
        #expect(APIEndpoints.Workflows.create == "/workflows")
        #expect(APIEndpoints.Workflows.tools == "/workflows/tools")
    }

    @Test("Search endpoints match Python API")
    func searchEndpoints() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "search")

        // Search uses POST (not GET) for the main search
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/search" })
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/search/saved" })
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/search/saved" })

        // Verify Swift constants match
        #expect(APIEndpoints.Search.search == "/search")
        #expect(APIEndpoints.Search.saved == "/search/saved")
    }

    @Test("Chat endpoints match Python API")
    func chatEndpoints() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "chat")

        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/chat" })
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/chat/conversations" })

        // Verify Swift constants match
        #expect(APIEndpoints.Chat.send == "/chat")
        #expect(APIEndpoints.Chat.conversations == "/chat/conversations")
    }

    @Test("Provider endpoints match Python API")
    func providerEndpoints() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "providers")

        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/providers/catalog" })
        #expect(pythonEndpoints.contains { $0.method == "GET" && $0.path == "/providers" })
        #expect(pythonEndpoints.contains { $0.method == "POST" && $0.path == "/providers" })

        // Verify Swift constants match
        #expect(APIEndpoints.Providers.catalog == "/providers/catalog")
        #expect(APIEndpoints.Providers.list == "/providers")
    }

    @Test("Storage endpoints match Python API")
    func storageEndpoints() throws {
        let pythonEndpoints = try loadPythonEndpoints(for: "storage")

        #expect(pythonEndpoints.contains { $0.path.contains("/storage/thumbnail/") })
        #expect(pythonEndpoints.contains { $0.path.contains("/storage/display/") })

        // Verify Swift constants produce correct paths
        #expect(APIEndpoints.Storage.thumbnail("test").contains("/storage/thumbnail/"))
        #expect(APIEndpoints.Storage.display("test").contains("/storage/display/"))
    }

    // MARK: - Helper

    private func loadPythonEndpoints(for resource: String) throws -> [PythonEndpoint] {
        let filePath = endpointsFilePath()

        guard FileManager.default.fileExists(atPath: filePath.path) else {
            Issue.record("endpoints.json not found. Run: python scripts/export_openapi_schema.py")
            return []
        }

        let data = try Data(contentsOf: filePath)
        let file = try JSONDecoder().decode(EndpointsFile.self, from: data)

        guard let endpoints = file.endpoints[resource] else {
            Issue.record("Resource '\(resource)' not found in endpoints.json")
            return []
        }

        return endpoints
    }
}

// MARK: - HTTP Method Validation Tests

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

        #expect(updateEndpoints.count > 0, "Should have some update endpoints")

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

        let deleteEndpoints = pythonEndpoints.filter {
            $0.operationId?.contains("delete") == true
        }

        for endpoint in deleteEndpoints {
            #expect(endpoint.method == "DELETE", "Delete endpoint \(endpoint.path) should use DELETE")
        }
    }

    // MARK: - Helper

    private func loadAllEndpoints() throws -> [PythonEndpoint] {
        let filePath = endpointsFilePath()

        guard FileManager.default.fileExists(atPath: filePath.path) else {
            Issue.record("endpoints.json not found. Run: python scripts/export_openapi_schema.py")
            return []
        }

        let data = try Data(contentsOf: filePath)
        let file = try JSONDecoder().decode(EndpointsFile.self, from: data)

        return file.endpoints.values.flatMap { $0 }
    }
}

// MARK: - Endpoint Definition Tests

struct EndpointDefinitionTests {

    @Test("EndpointDefinitions match Python API")
    func definitionsMatchPython() throws {
        let pythonEndpoints = try loadAllEndpoints()

        for definition in EndpointDefinition.definitions {
            // Convert Swift pattern to regex
            let pattern = definition.pathPattern
                .replacingOccurrences(of: "{id}", with: "\\{[^}]+\\}")
                .replacingOccurrences(of: "/", with: "\\/")

            let regex = try? NSRegularExpression(pattern: "^\(pattern)$")

            let matching = pythonEndpoints.filter { endpoint in
                guard endpoint.method == definition.method else { return false }
                let range = NSRange(endpoint.path.startIndex..., in: endpoint.path)
                return regex?.firstMatch(in: endpoint.path, range: range) != nil
            }

            #expect(
                !matching.isEmpty,
                "No Python endpoint matches \(definition.method) \(definition.pathPattern)"
            )
        }
    }

    // MARK: - Helper

    private func loadAllEndpoints() throws -> [PythonEndpoint] {
        let filePath = endpointsFilePath()

        guard FileManager.default.fileExists(atPath: filePath.path) else {
            Issue.record("endpoints.json not found")
            return []
        }

        let data = try Data(contentsOf: filePath)
        let file = try JSONDecoder().decode(EndpointsFile.self, from: data)

        return file.endpoints.values.flatMap { $0 }
    }
}
