//
//  MCPMigrationTests.swift
//  FicheroTests
//
//  #3030 (post-#3131) — MCPService migrated onto the generated typed operations.
//  Decodes a real MCPServerResponse list through the generated client and runs it
//  through the app MCPServerResponse mapper (env/headers typed additionalProperties;
//  timestamps are plain strings — no Date conversion). Reuses MockURLProtocol.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct MCPMigrationTests {

    private func makeClient(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> FicheroClient {
        MockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
    }

    @Test("list_mcp_servers decodes + maps items (env/headers typed dicts)")
    func listServersMaps() async throws {
        let client = makeClient { request in
            #expect(request.url?.path == "/api/mcp-servers")
            let json = """
            {"count":1,"items":[
              {"id":"srv1","name":"Local","description":"d","transport":"stdio",
               "command":"node","args":["x"],"env":{"K":"V"},"url":null,
               "headers":{"H":"1"},"tool_name_prefix":true,"enabled":true,
               "created_at":"2026-07-04T00:00:00Z","updated_at":"2026-07-04T00:00:00Z"}
            ]}
            """
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(json.utf8))
        }

        let response = try await client.api.listMcpServersApiMcpServersGet()
        guard case .ok(let okResponse) = response else {
            Issue.record("expected .ok")
            return
        }
        let servers = try okResponse.body.json.items.map { MCPServerResponse(response: $0) }
        #expect(servers.count == 1)
        let server = try #require(servers.first)
        #expect(server.id == "srv1")
        #expect(server.transport == "stdio")
        #expect(server.command == "node")
        #expect(server.env == ["K": "V"])
        #expect(server.headers == ["H": "1"])
        #expect(server.enabled)
    }

    @Test("get_mcp_server non-.ok surfaces as non-.ok (never a silent empty server)")
    func getServerNonOk() async throws {
        let client = makeClient { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 500, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data("{\"detail\":\"boom\"}".utf8))
        }

        let response = try await client.api.getMcpServerApiMcpServersServerIdGet(
            .init(path: .init(serverId: "srv1"))
        )
        if case .ok = response {
            Issue.record("500 must not decode as .ok")
        }
    }
}
