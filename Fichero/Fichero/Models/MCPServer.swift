import Foundation

// MARK: - MCP Transport Type

/// MCP server transport type
enum MCPTransport: String, Codable, CaseIterable {
    case stdio
    case sse
    case http
    case websocket

    var displayName: String {
        switch self {
        case .stdio: return "Standard I/O"
        case .sse: return "Server-Sent Events"
        case .http: return "HTTP"
        case .websocket: return "WebSocket"
        }
    }

    var icon: String {
        switch self {
        case .stdio: return "terminal"
        case .sse: return "arrow.down.circle"
        case .http: return "network"
        case .websocket: return "bolt.horizontal"
        }
    }

    /// Whether this transport requires a command
    var requiresCommand: Bool {
        self == .stdio
    }

    /// Whether this transport requires a URL
    var requiresURL: Bool {
        self != .stdio
    }
}

// MARK: - MCP Server Model

/// MCP (Model Context Protocol) server configuration.
/// Matches Python MCPServer model in fichero/models.py
///
/// MCP servers provide tools that can be used in workflows.
/// Supports multiple transport types: stdio, HTTP, SSE, WebSocket.
struct MCPServer: Identifiable, Codable, Hashable {
    let id: String
    var name: String
    var serverDescription: String

    // Transport configuration
    var transport: MCPTransport

    // Transport-specific parameters
    var command: String?
    var args: [String]
    var env: [String: String]
    var url: String?
    var headers: [String: String]

    // Tool configuration
    var toolNamePrefix: Bool
    var enabled: Bool

    // Timestamps
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case serverDescription = "description"
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

    init(
        id: String = UUID().uuidString,
        name: String,
        serverDescription: String = "",
        transport: MCPTransport,
        command: String? = nil,
        args: [String] = [],
        env: [String: String] = [:],
        url: String? = nil,
        headers: [String: String] = [:],
        toolNamePrefix: Bool = true,
        enabled: Bool = true,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.name = name
        self.serverDescription = serverDescription
        self.transport = transport
        self.command = command
        self.args = args
        self.env = env
        self.url = url
        self.headers = headers
        self.toolNamePrefix = toolNamePrefix
        self.enabled = enabled
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

// MARK: - MCP Server Helpers

extension MCPServer {
    /// Validate the server configuration
    var isValid: Bool {
        guard !name.isEmpty else { return false }

        switch transport {
        case .stdio:
            return command != nil && !command!.isEmpty
        case .sse, .http, .websocket:
            return url != nil && !url!.isEmpty
        }
    }

    /// Get validation error message if invalid
    var validationError: String? {
        if name.isEmpty {
            return "Server name is required"
        }

        switch transport {
        case .stdio:
            if command == nil || command!.isEmpty {
                return "Command is required for stdio transport"
            }
        case .sse, .http, .websocket:
            if url == nil || url!.isEmpty {
                return "URL is required for \(transport.displayName) transport"
            }
        }

        return nil
    }

    /// Full command with arguments for display
    var fullCommand: String? {
        guard transport == .stdio, let cmd = command else { return nil }
        if args.isEmpty {
            return cmd
        }
        return ([cmd] + args).joined(separator: " ")
    }

    /// Status display based on enabled state
    var statusText: String {
        enabled ? "Enabled" : "Disabled"
    }

    /// Status icon
    var statusIcon: String {
        enabled ? "checkmark.circle.fill" : "xmark.circle"
    }

    /// Status color
    var statusColor: String {
        enabled ? "green" : "gray"
    }
}

// MARK: - MCP Tool

/// A tool provided by an MCP server
struct MCPTool: Identifiable, Codable, Hashable {
    var id: String { name }
    let name: String
    let toolDescription: String
    let inputSchema: [String: AnyCodable]?
    let serverId: String

    enum CodingKeys: String, CodingKey {
        case name
        case toolDescription = "description"
        case inputSchema = "input_schema"
        case serverId = "server_id"
    }

    init(
        name: String,
        toolDescription: String = "",
        inputSchema: [String: AnyCodable]? = nil,
        serverId: String
    ) {
        self.name = name
        self.toolDescription = toolDescription
        self.inputSchema = inputSchema
        self.serverId = serverId
    }
}
