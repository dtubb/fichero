//
//  MCPMigrationTests.swift
//  FicheroTests
//
//  #3030 (post-#3131) — MCPService migrated onto the generated typed operations.
//  Decodes a real MCPServerResponse list through the generated client and runs it
//  through the app MCPServerResponse mapper (env/headers typed additionalProperties;
//  timestamps are plain strings — no Date conversion). Uses a dedicated
//  MCPMockURLProtocol (own static handler, route-scoped canInit, serialized
//  suite) so parallel test execution can't race with other suites — #4024.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Dedicated mock protocol for this suite — NOT the shared `MockURLProtocol`
/// from StorageServiceTests. Suites sharing one global protocol/handler race
/// and intercept each other's requests under parallel execution (#4024).
/// Scoped to `/api/mcp-servers...` (list + get-by-id) only.
private final class MCPMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path.hasPrefix("/api/mcp-servers") == true
    }

    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MCPMockURLProtocol.requestHandler else {
            client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct MCPMigrationTests {

    private func makeClient(
        handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> FicheroClient {
        MCPMockURLProtocol.requestHandler = handler
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MCPMockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: session
        )
    }

    @Test("list_mcp_servers decodes + maps items (env/headers typed dicts)")
    func listServersMaps() async throws {
        defer { MCPMockURLProtocol.requestHandler = nil }
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

    @Test("MCPService surfaces a 422's detail as validationError")
    func getServerValidationErrorPreservesDetail() async throws {
        defer { MCPMockURLProtocol.requestHandler = nil }
        let service = MCPService(apiClient: APIClient(client: makeClient { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 422, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            let body = #"{"detail":[{"loc":["body","name"],"msg":"field required","type":"missing"}]}"#
            return (response, Data(body.utf8))
        }))
        do {
            _ = try await service.getServer("srv1")
            Issue.record("expected a throw on 422")
        } catch let MCPServiceError.validationError(message) {
            #expect(message.contains("field required"))
        } catch {
            Issue.record("expected .validationError, got \(error)")
        }
    }

    @Test("MCPService.listServers throws on a 500 (never a silently empty list)")
    func listServersThrowsOn500() async throws {
        defer { MCPMockURLProtocol.requestHandler = nil }
        let service = MCPService(apiClient: APIClient(client: makeClient { request in
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 500, httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (response, Data(#"{"detail":"boom"}"#.utf8))
        }))
        await #expect(throws: MCPServiceError.self) {
            _ = try await service.listServers()
        }
    }

    @Test("get_mcp_server non-.ok surfaces as non-.ok (never a silent empty server)")
    func getServerNonOk() async throws {
        defer { MCPMockURLProtocol.requestHandler = nil }
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
