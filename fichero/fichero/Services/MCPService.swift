import FicheroAPIClient
import Foundation
import Observation
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "MCPService")

/// Service for managing MCP (Model Context Protocol) servers and tools.
@MainActor
@Observable
class MCPService {
    private let api: APIClient

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - MCP Server Management

    /// List all MCP servers.
    func listServers() async throws -> [MCPServerResponse] {
        let response = try await api.api.listMcpServersApiMcpServersGet()
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map { MCPServerResponse(response: $0) }
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    /// Get a specific MCP server by ID.
    func getServer(_ id: String) async throws -> MCPServerResponse {
        let response = try await api.api.getMcpServerApiMcpServersServerIdGet(
            .init(path: .init(serverId: id))
        )
        switch response {
        case .ok(let okResponse):
            return MCPServerResponse(response: try okResponse.body.json)
        case .unprocessableContent(let error):
            throw MCPServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    /// Create a new MCP server.
    func createServer(_ request: CreateMCPServerRequest) async throws -> MCPServerResponse {
        let response = try await api.api.createMcpServerApiMcpServersPost(
            .init(body: .json(.init(app: request)))
        )
        switch response {
        case .ok(let okResponse):
            return MCPServerResponse(response: try okResponse.body.json)
        case .unprocessableContent(let error):
            throw MCPServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    /// Update an existing MCP server.
    func updateServer(_ id: String, request: UpdateMCPServerRequest) async throws -> MCPServerResponse {
        let response = try await api.api.updateMcpServerApiMcpServersServerIdPut(
            .init(path: .init(serverId: id), body: .json(.init(app: request)))
        )
        switch response {
        case .ok(let okResponse):
            return MCPServerResponse(response: try okResponse.body.json)
        case .unprocessableContent(let error):
            throw MCPServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    /// Delete an MCP server.
    func deleteServer(_ id: String) async throws {
        let response = try await api.api.deleteMcpServerApiMcpServersServerIdDelete(
            .init(path: .init(serverId: id))
        )
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            throw MCPServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    // MARK: - Tool Loading

    /// Load tools from a specific server.
    func loadServerTools(_ serverId: String, forceReload: Bool = false) async throws -> LoadToolsResponse {
        let response = try await api.api.loadServerToolsApiMcpServersServerIdLoadToolsPost(
            .init(path: .init(serverId: serverId), query: .init(forceReload: forceReload))
        )
        switch response {
        case .ok(let okResponse):
            return LoadToolsResponse(response: try okResponse.body.json)
        case .unprocessableContent(let error):
            throw MCPServiceError.validationError(
                (try? error.body.json)?.detail?.description ?? "Validation error"
            )
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    /// Get all tools from all enabled servers.
    func getAllTools() async throws -> AllToolsResponse {
        let response = try await api.api.getAllMcpToolsApiMcpServersToolsAllGet()
        switch response {
        case .ok(let okResponse):
            return AllToolsResponse(response: try okResponse.body.json)
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    /// Load all MCP tools into the workflow registry.
    func loadToolsIntoWorkflowRegistry() async throws -> RegistryLoadResponse {
        let response = try await api.api
            .loadMcpToolsIntoWorkflowRegistryApiMcpServersToolsLoadIntoWorkflowRegistryPost()
        switch response {
        case .ok(let okResponse):
            return RegistryLoadResponse(response: try okResponse.body.json)
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    /// Reload MCP tools in the workflow registry.
    func reloadToolsInWorkflowRegistry() async throws -> RegistryLoadResponse {
        let response = try await api.api
            .reloadMcpToolsInWorkflowRegistryApiMcpServersToolsReloadWorkflowRegistryPost()
        switch response {
        case .ok(let okResponse):
            return RegistryLoadResponse(response: try okResponse.body.json)
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }
}

enum MCPServiceError: LocalizedError {
    case validationError(String)
    case unexpectedResponse

    var errorDescription: String? {
        switch self {
        case .validationError(let message):
            return "Validation error: \(message)"
        case .unexpectedResponse:
            return "Unexpected response from the MCP service."
        }
    }
}
