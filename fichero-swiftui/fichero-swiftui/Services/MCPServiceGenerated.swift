import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "MCPServiceGenerated")

/// MCPService using the generated OpenAPI client.
/// Manages MCP (Model Context Protocol) servers and tools.
/// Note: Types (MCPServerResponse, MCPToolInfo, etc.) are kept in MCPService.swift
@MainActor
class MCPServiceGenerated: ObservableObject {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - MCP Server Management

    /// List all MCP servers
    func listServers() async throws -> [MCPServerResponse] {
        let response = try await client.api.listMcpServersApiMcpServersGet()

        switch response {
        case .ok(let okResponse):
            let servers = try okResponse.body.json
            return servers.map { convertToMCPServerResponse($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw MCPServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw MCPServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Get a specific MCP server by ID
    func getServer(_ id: String) async throws -> MCPServerResponse {
        let response = try await client.api.getMcpServerApiMcpServersServerIdGet(
            path: .init(serverId: id)
        )

        switch response {
        case .ok(let okResponse):
            let server = try okResponse.body.json
            return convertToMCPServerResponse(server)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw MCPServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw MCPServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Create a new MCP server
    func createServer(_ request: CreateMCPServerRequest) async throws -> MCPServerResponse {
        // Build env and headers containers
        let envContainer = try OpenAPIObjectContainer(unvalidatedValue: request.env)
        let headersContainer = try OpenAPIObjectContainer(unvalidatedValue: request.headers)

        let response = try await client.api.createMcpServerApiMcpServersPost(
            body: .json(.init(
                name: request.name,
                description: request.description,
                transport: request.transport,
                command: request.command,
                args: request.args,
                env: .init(additionalProperties: envContainer),
                url: request.url,
                headers: .init(additionalProperties: headersContainer),
                toolNamePrefix: request.toolNamePrefix,
                enabled: request.enabled
            ))
        )

        switch response {
        case .ok(let okResponse):
            let server = try okResponse.body.json
            return convertToMCPServerResponse(server)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw MCPServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw MCPServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Update an existing MCP server
    func updateServer(_ id: String, request: UpdateMCPServerRequest) async throws -> MCPServerResponse {
        // Build optional env and headers containers
        var envPayload: Components.Schemas.UpdateMCPServerRequest.EnvPayload?
        if let env = request.env {
            let envContainer = try OpenAPIObjectContainer(unvalidatedValue: env)
            envPayload = .init(additionalProperties: envContainer)
        }

        var headersPayload: Components.Schemas.UpdateMCPServerRequest.HeadersPayload?
        if let headers = request.headers {
            let headersContainer = try OpenAPIObjectContainer(unvalidatedValue: headers)
            headersPayload = .init(additionalProperties: headersContainer)
        }

        let response = try await client.api.updateMcpServerApiMcpServersServerIdPut(
            path: .init(serverId: id),
            body: .json(.init(
                name: request.name,
                description: request.description,
                transport: request.transport,
                command: request.command,
                args: request.args,
                env: envPayload,
                url: request.url,
                headers: headersPayload,
                toolNamePrefix: request.toolNamePrefix,
                enabled: request.enabled
            ))
        )

        switch response {
        case .ok(let okResponse):
            let server = try okResponse.body.json
            return convertToMCPServerResponse(server)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw MCPServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw MCPServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Delete an MCP server
    func deleteServer(_ id: String) async throws {
        let response = try await client.api.deleteMcpServerApiMcpServersServerIdDelete(
            path: .init(serverId: id)
        )

        switch response {
        case .ok:
            logger.info("Deleted MCP server: \(id)")
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw MCPServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw MCPServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Tool Loading

    /// Load tools from a specific server
    func loadServerTools(_ serverId: String, forceReload: Bool = false) async throws -> LoadToolsResponse {
        let response = try await client.api.loadMcpServerToolsApiMcpServersServerIdLoadToolsPost(
            path: .init(serverId: serverId),
            query: .init(forceReload: forceReload)
        )

        switch response {
        case .ok(let okResponse):
            let loadResponse = try okResponse.body.json
            return convertToLoadToolsResponse(loadResponse)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw MCPServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw MCPServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Get all tools from all enabled servers
    func getAllTools() async throws -> AllToolsResponse {
        let response = try await client.api.getAllMcpToolsApiMcpServersToolsAllGet()

        switch response {
        case .ok(let okResponse):
            let allTools = try okResponse.body.json
            return convertToAllToolsResponse(allTools)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw MCPServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw MCPServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Load all MCP tools into the workflow registry
    func loadToolsIntoWorkflowRegistry() async throws -> RegistryLoadResponse {
        let response = try await client.api.loadMcpToolsIntoRegistryApiMcpServersToolsLoadIntoWorkflowRegistryPost()

        switch response {
        case .ok(let okResponse):
            let registryResponse = try okResponse.body.json
            return RegistryLoadResponse(
                toolCount: registryResponse.toolCount,
                message: registryResponse.message
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw MCPServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw MCPServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Reload MCP tools in the workflow registry
    func reloadToolsInWorkflowRegistry() async throws -> RegistryLoadResponse {
        let response = try await client.api.reloadMcpToolsInRegistryApiMcpServersToolsReloadWorkflowRegistryPost()

        switch response {
        case .ok(let okResponse):
            let registryResponse = try okResponse.body.json
            return RegistryLoadResponse(
                toolCount: registryResponse.toolCount,
                message: registryResponse.message
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw MCPServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw MCPServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Type Conversions

    private func convertToMCPServerResponse(_ generated: Components.Schemas.MCPServerResponse) -> MCPServerResponse {
        // Extract env dictionary
        var envDict: [String: String] = [:]
        for (key, value) in generated.env.additionalProperties.value {
            if let strValue = value as? String {
                envDict[key] = strValue
            }
        }

        // Extract headers dictionary
        var headersDict: [String: String] = [:]
        for (key, value) in generated.headers.additionalProperties.value {
            if let strValue = value as? String {
                headersDict[key] = strValue
            }
        }

        return MCPServerResponse(
            id: generated.id,
            name: generated.name,
            description: generated.description,
            transport: generated.transport,
            command: generated.command,
            args: generated.args,
            env: envDict,
            url: generated.url,
            headers: headersDict,
            toolNamePrefix: generated.toolNamePrefix,
            enabled: generated.enabled,
            createdAt: generated.createdAt,
            updatedAt: generated.updatedAt
        )
    }

    private func convertToLoadToolsResponse(_ generated: Components.Schemas.LoadToolsResponse) -> LoadToolsResponse {
        LoadToolsResponse(
            serverId: generated.serverId,
            serverName: generated.serverName,
            toolCount: generated.toolCount,
            tools: generated.tools.map { convertToMCPToolInfo($0) }
        )
    }

    private func convertToAllToolsResponse(_ generated: Components.Schemas.AllToolsResponse) -> AllToolsResponse {
        AllToolsResponse(
            toolCount: generated.toolCount,
            tools: generated.tools.map { convertToMCPToolInfo($0) }
        )
    }

    private func convertToMCPToolInfo(_ generated: Components.Schemas.MCPToolInfo) -> MCPToolInfo {
        MCPToolInfo(
            name: generated.name,
            description: generated.description,
            serverName: generated.serverName
        )
    }
}

// MARK: - Error Types

enum MCPServiceGeneratedError: Error, LocalizedError {
    case unexpectedResponse(Int)
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse(let code):
            return "Unexpected response from MCP service (status: \(code))"
        case .serverError(let message):
            return "Server error: \(message)"
        }
    }
}
