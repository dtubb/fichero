import FicheroAPIClient
import Foundation
import SwiftUI

//  Extracted for file_length (#5113). Behaviour unchanged: the declarations below are
//  byte-for-byte what they were, moved so the file they came from stays readable.

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
