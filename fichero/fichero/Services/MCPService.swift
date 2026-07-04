import FicheroAPIClient
import Foundation
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "MCPService")

/// Service for managing MCP (Model Context Protocol) servers and tools.
@MainActor
class MCPService: ObservableObject {
    private let api: APIClient

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - MCP Server Management

    /// List all MCP servers.
    func listServers() async throws -> [MCPServerResponse] {
        let response = try await api.api.listMcpServersApiMcpServersGet()
        switch response {
        case .ok(let ok):
            return try ok.body.json.items.map { MCPServerResponse(response: $0) }
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
        case .ok(let ok):
            return MCPServerResponse(response: try ok.body.json)
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
        case .ok(let ok):
            return MCPServerResponse(response: try ok.body.json)
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
        case .ok(let ok):
            return MCPServerResponse(response: try ok.body.json)
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
        case .ok(let ok):
            return LoadToolsResponse(response: try ok.body.json)
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
        case .ok(let ok):
            return AllToolsResponse(response: try ok.body.json)
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    /// Load all MCP tools into the workflow registry.
    func loadToolsIntoWorkflowRegistry() async throws -> RegistryLoadResponse {
        let response = try await api.api
            .loadMcpToolsIntoWorkflowRegistryApiMcpServersToolsLoadIntoWorkflowRegistryPost()
        switch response {
        case .ok(let ok):
            return RegistryLoadResponse(response: try ok.body.json)
        default:
            throw MCPServiceError.unexpectedResponse
        }
    }

    /// Reload MCP tools in the workflow registry.
    func reloadToolsInWorkflowRegistry() async throws -> RegistryLoadResponse {
        let response = try await api.api
            .reloadMcpToolsInWorkflowRegistryApiMcpServersToolsReloadWorkflowRegistryPost()
        switch response {
        case .ok(let ok):
            return RegistryLoadResponse(response: try ok.body.json)
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

// MARK: - Request Models

struct CreateMCPServerRequest: Codable {
    let name: String
    let description: String
    let transport: String  // "stdio", "sse", "http", "websocket"
    let command: String?
    let args: [String]
    let env: [String: String]
    let url: String?
    let headers: [String: String]
    let toolNamePrefix: Bool
    let enabled: Bool

    enum CodingKeys: String, CodingKey {
        case name
        case description
        case transport
        case command
        case args
        case env
        case url
        case headers
        case toolNamePrefix = "tool_name_prefix"
        case enabled
    }

    init(
        name: String,
        description: String = "",
        transport: String,
        command: String? = nil,
        args: [String] = [],
        env: [String: String] = [:],
        url: String? = nil,
        headers: [String: String] = [:],
        toolNamePrefix: Bool = true,
        enabled: Bool = true
    ) {
        self.name = name
        self.description = description
        self.transport = transport
        self.command = command
        self.args = args
        self.env = env
        self.url = url
        self.headers = headers
        self.toolNamePrefix = toolNamePrefix
        self.enabled = enabled
    }
}

struct UpdateMCPServerRequest: Codable {
    let name: String?
    let description: String?
    let transport: String?
    let command: String?
    let args: [String]?
    let env: [String: String]?
    let url: String?
    let headers: [String: String]?
    let toolNamePrefix: Bool?
    let enabled: Bool?

    enum CodingKeys: String, CodingKey {
        case name
        case description
        case transport
        case command
        case args
        case env
        case url
        case headers
        case toolNamePrefix = "tool_name_prefix"
        case enabled
    }

    init(
        name: String? = nil,
        description: String? = nil,
        transport: String? = nil,
        command: String? = nil,
        args: [String]? = nil,
        env: [String: String]? = nil,
        url: String? = nil,
        headers: [String: String]? = nil,
        toolNamePrefix: Bool? = nil,
        enabled: Bool? = nil
    ) {
        self.name = name
        self.description = description
        self.transport = transport
        self.command = command
        self.args = args
        self.env = env
        self.url = url
        self.headers = headers
        self.toolNamePrefix = toolNamePrefix
        self.enabled = enabled
    }
}

// MARK: - Response Models

struct MCPServerResponse: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let description: String
    let transport: String
    let command: String?
    let args: [String]
    let env: [String: String]
    let url: String?
    let headers: [String: String]
    let toolNamePrefix: Bool
    let enabled: Bool
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case description
        case transport
        case command
        case args
        case env
        case url
        case headers
        case toolNamePrefix = "tool_name_prefix"
        case enabled
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    /// Transport type for display
    var transportDisplayName: String {
        switch transport {
        case "stdio": return "Process (stdio)"
        case "sse": return "Server-Sent Events"
        case "http": return "HTTP"
        case "websocket": return "WebSocket"
        default: return transport
        }
    }

    /// Whether this server is connection-based (needs URL)
    var needsURL: Bool {
        transport != "stdio"
    }

    /// Whether this server needs a command
    var needsCommand: Bool {
        transport == "stdio"
    }

    /// Icon for server type
    var icon: String {
        switch transport {
        case "stdio": return "terminal"
        case "sse": return "antenna.radiowaves.left.and.right"
        case "http": return "network"
        case "websocket": return "bolt.horizontal"
        default: return "server.rack"
        }
    }

    /// Color for server type
    var color: Color {
        switch transport {
        case "stdio": return .blue
        case "sse": return .orange
        case "http": return .green
        case "websocket": return .purple
        default: return .gray
        }
    }
}

struct MCPToolInfo: Codable, Identifiable, Hashable {
    let name: String
    let description: String
    let serverName: String

    var id: String { name }

    enum CodingKeys: String, CodingKey {
        case name
        case description
        case serverName = "server_name"
    }
}

struct LoadToolsResponse: Codable {
    let serverId: String
    let serverName: String
    let toolCount: Int
    let tools: [MCPToolInfo]

    enum CodingKeys: String, CodingKey {
        case serverId = "server_id"
        case serverName = "server_name"
        case toolCount = "tool_count"
        case tools
    }
}

struct AllToolsResponse: Codable {
    let toolCount: Int
    let tools: [MCPToolInfo]

    enum CodingKeys: String, CodingKey {
        case toolCount = "tool_count"
        case tools
    }
}

struct RegistryLoadResponse: Codable {
    let toolCount: Int
    let message: String

    enum CodingKeys: String, CodingKey {
        case toolCount = "tool_count"
        case message
    }
}

// MARK: - Generated ↔ App Mappers (#3030)
// Inline in this (already-in-target) file to avoid a separate pbxproj membership.
// MCP timestamp fields are plain strings in the schema (no date-time), so no
// Date↔String conversion is needed here.

extension MCPServerResponse {
    init(response: Components.Schemas.MCPServerResponse) {
        self.init(
            id: response.id,
            name: response.name,
            description: response.description,
            transport: response.transport,
            command: response.command,
            args: response.args,
            env: response.env.additionalProperties,
            url: response.url,
            headers: response.headers.additionalProperties,
            toolNamePrefix: response.toolNamePrefix,
            enabled: response.enabled,
            createdAt: response.createdAt,
            updatedAt: response.updatedAt
        )
    }
}

extension MCPToolInfo {
    init(response: Components.Schemas.MCPToolInfo) {
        self.init(name: response.name, description: response.description, serverName: response.serverName)
    }
}

extension LoadToolsResponse {
    init(response: Components.Schemas.MCPServerToolsResponse) {
        self.init(
            serverId: response.serverId,
            serverName: response.serverName,
            toolCount: response.toolCount,
            tools: response.tools.map { MCPToolInfo(response: $0) }
        )
    }
}

extension AllToolsResponse {
    init(response: Components.Schemas.MCPToolListResponse) {
        self.init(toolCount: response.count, tools: response.items.map { MCPToolInfo(response: $0) })
    }
}

extension RegistryLoadResponse {
    init(response: Components.Schemas.MCPToolRegistryResponse) {
        self.init(toolCount: response.toolCount, message: response.message)
    }
}

extension Components.Schemas.CreateMCPServerRequest {
    init(app response: CreateMCPServerRequest) {
        self.init(
            name: response.name,
            description: response.description,
            transport: response.transport,
            command: response.command,
            args: response.args,
            env: .init(additionalProperties: response.env),
            url: response.url,
            headers: .init(additionalProperties: response.headers),
            toolNamePrefix: response.toolNamePrefix,
            enabled: response.enabled
        )
    }
}

extension Components.Schemas.UpdateMCPServerRequest {
    init(app response: UpdateMCPServerRequest) {
        self.init(
            name: response.name,
            description: response.description,
            transport: response.transport,
            command: response.command,
            args: response.args,
            env: response.env.map { .init(additionalProperties: $0) },
            url: response.url,
            headers: response.headers.map { .init(additionalProperties: $0) },
            toolNamePrefix: response.toolNamePrefix,
            enabled: response.enabled
        )
    }
}
