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
        try await api.get("/mcp-servers")
    }

    /// Get a specific MCP server by ID.
    func getServer(_ id: String) async throws -> MCPServerResponse {
        try await api.get("/mcp-servers/\(id)")
    }

    /// Create a new MCP server.
    func createServer(_ request: CreateMCPServerRequest) async throws -> MCPServerResponse {
        try await api.post("/mcp-servers", body: request)
    }

    /// Update an existing MCP server.
    func updateServer(_ id: String, request: UpdateMCPServerRequest) async throws -> MCPServerResponse {
        try await api.put("/mcp-servers/\(id)", body: request)
    }

    /// Delete an MCP server.
    func deleteServer(_ id: String) async throws {
        try await api.delete("/mcp-servers/\(id)")
    }

    // MARK: - Tool Loading

    /// Load tools from a specific server.
    func loadServerTools(_ serverId: String, forceReload: Bool = false) async throws -> LoadToolsResponse {
        let path = forceReload
            ? "/mcp-servers/\(serverId)/load-tools?force_reload=true"
            : "/mcp-servers/\(serverId)/load-tools"
        return try await api.post(path, body: EmptyRequest())
    }

    /// Get all tools from all enabled servers.
    func getAllTools() async throws -> AllToolsResponse {
        try await api.get("/mcp-servers/tools/all")
    }

    /// Load all MCP tools into the workflow registry.
    func loadToolsIntoWorkflowRegistry() async throws -> RegistryLoadResponse {
        try await api.post("/mcp-servers/tools/load-into-workflow-registry", body: EmptyRequest())
    }

    /// Reload MCP tools in the workflow registry.
    func reloadToolsInWorkflowRegistry() async throws -> RegistryLoadResponse {
        try await api.post("/mcp-servers/tools/reload-workflow-registry", body: EmptyRequest())
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

struct EmptyRequest: Codable {}

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
