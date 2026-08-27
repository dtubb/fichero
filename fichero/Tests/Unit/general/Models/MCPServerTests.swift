@testable import Fichero
import XCTest

/// Tests for MCPServer + MCPTransport. Locks: per-transport validation
/// (stdio needs command, network transports need url), validation error
/// strings (rendered in Settings UI), Codable mapping to Python model
/// (snake_case fields), MCPTool id formula.
final class MCPServerTests: XCTestCase {

    // MARK: - MCPTransport

    func testTransportRequiresCommandOnlyForStdio() {
        XCTAssertTrue(MCPTransport.stdio.requiresCommand)
        XCTAssertFalse(MCPTransport.sse.requiresCommand)
        XCTAssertFalse(MCPTransport.http.requiresCommand)
        XCTAssertFalse(MCPTransport.websocket.requiresCommand)
    }

    func testTransportRequiresURLForAllExceptStdio() {
        XCTAssertFalse(MCPTransport.stdio.requiresURL)
        XCTAssertTrue(MCPTransport.sse.requiresURL)
        XCTAssertTrue(MCPTransport.http.requiresURL)
        XCTAssertTrue(MCPTransport.websocket.requiresURL)
    }

    func testTransportDisplayNames() {
        XCTAssertEqual(MCPTransport.stdio.displayName, "Standard I/O")
        XCTAssertEqual(MCPTransport.sse.displayName, "Server-Sent Events")
        XCTAssertEqual(MCPTransport.http.displayName, "HTTP")
        XCTAssertEqual(MCPTransport.websocket.displayName, "WebSocket")
    }

    func testTransportRawValuesStable() {
        // Persisted to JSON → Python — drift breaks server round-trip.
        XCTAssertEqual(MCPTransport.stdio.rawValue, "stdio")
        XCTAssertEqual(MCPTransport.sse.rawValue, "sse")
        XCTAssertEqual(MCPTransport.http.rawValue, "http")
        XCTAssertEqual(MCPTransport.websocket.rawValue, "websocket")
    }

    func testTransportAllCasesCount() {
        XCTAssertEqual(MCPTransport.allCases.count, 4)
    }

    // MARK: - Validation: stdio

    func testStdioValid() {
        let server = MCPServer(name: "Test", transport: .stdio, command: "npx")
        XCTAssertTrue(server.isValid)
        XCTAssertNil(server.validationError)
    }

    func testStdioMissingCommandInvalid() {
        let server = MCPServer(name: "Test", transport: .stdio, command: nil)
        XCTAssertFalse(server.isValid)
        XCTAssertEqual(server.validationError, "Command is required for stdio transport")
    }

    func testStdioEmptyCommandInvalid() {
        let server = MCPServer(name: "Test", transport: .stdio, command: "")
        XCTAssertFalse(server.isValid)
    }

    // MARK: - Validation: network transports

    func testHTTPValid() {
        let server = MCPServer(
            name: "Test", transport: .http, url: "https://example.com/mcp"
        )
        XCTAssertTrue(server.isValid)
    }

    func testNetworkMissingURLInvalid() {
        for transport in [MCPTransport.sse, .http, .websocket] {
            let server = MCPServer(name: "Test", transport: transport, url: nil)
            XCTAssertFalse(server.isValid, "\(transport.rawValue) should be invalid without url")
            XCTAssertEqual(
                server.validationError,
                "URL is required for \(transport.displayName) transport"
            )
        }
    }

    // MARK: - Validation: name

    func testEmptyNameAlwaysInvalid() {
        let server = MCPServer(name: "", transport: .stdio, command: "npx")
        XCTAssertFalse(server.isValid)
        XCTAssertEqual(server.validationError, "Server name is required")
    }

    // MARK: - fullCommand

    func testFullCommandWithoutArgs() {
        let server = MCPServer(name: "x", transport: .stdio, command: "npx")
        XCTAssertEqual(server.fullCommand, "npx")
    }

    func testFullCommandJoinsArgs() {
        let server = MCPServer(
            name: "x", transport: .stdio, command: "npx", args: ["-y", "@org/pkg"]
        )
        XCTAssertEqual(server.fullCommand, "npx -y @org/pkg")
    }

    func testFullCommandNilForNonStdio() {
        let server = MCPServer(name: "x", transport: .http, url: "https://x")
        XCTAssertNil(server.fullCommand)
    }

    // MARK: - Status helpers

    func testStatusTextAndIconAndColor() {
        var server = MCPServer(name: "x", transport: .stdio, command: "n", enabled: true)
        XCTAssertEqual(server.statusText, "Enabled")
        XCTAssertEqual(server.statusIcon, "checkmark.circle.fill")
        XCTAssertEqual(server.statusColor, "green")
        server.enabled = false
        XCTAssertEqual(server.statusText, "Disabled")
        XCTAssertEqual(server.statusIcon, "xmark.circle")
        XCTAssertEqual(server.statusColor, "gray")
    }

    // MARK: - Codable round-trip with Python snake_case

    func testMCPServerDecodesPythonModel() throws {
        let json = """
        {
            "id": "srv-1",
            "name": "Filesystem",
            "description": "FS access",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "env": {"DEBUG": "1"},
            "url": null,
            "headers": {},
            "tool_name_prefix": false,
            "enabled": true,
            "created_at": "2026-05-10T10:00:00Z",
            "updated_at": "2026-05-10T10:00:00Z"
        }
        """.data(using: .utf8)!
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let server = try decoder.decode(MCPServer.self, from: json)
        XCTAssertEqual(server.id, "srv-1")
        XCTAssertEqual(server.serverDescription, "FS access")  // description → serverDescription
        XCTAssertEqual(server.transport, .stdio)
        XCTAssertEqual(server.args.count, 2)
        XCTAssertEqual(server.env["DEBUG"], "1")
        XCTAssertFalse(server.toolNamePrefix)  // snake_case decoded
    }

    func testMCPServerDefaultsInInit() {
        let server = MCPServer(name: "x", transport: .stdio)
        XCTAssertFalse(server.id.isEmpty)  // UUID default
        XCTAssertEqual(server.serverDescription, "")
        XCTAssertTrue(server.args.isEmpty)
        XCTAssertTrue(server.env.isEmpty)
        XCTAssertTrue(server.toolNamePrefix)  // default true
        XCTAssertTrue(server.enabled)
    }

    // MARK: - MCPTool

    func testMCPToolIdIsName() {
        let tool = MCPTool(name: "read_file", serverId: "srv-1")
        XCTAssertEqual(tool.id, "read_file")
    }

    func testMCPToolDecodesSnakeCase() throws {
        let json = """
        {
            "name": "search",
            "description": "Web search",
            "input_schema": null,
            "server_id": "srv-1"
        }
        """.data(using: .utf8)!
        let tool = try JSONDecoder().decode(MCPTool.self, from: json)
        XCTAssertEqual(tool.name, "search")
        XCTAssertEqual(tool.toolDescription, "Web search")  // description → toolDescription
        XCTAssertEqual(tool.serverId, "srv-1")
        XCTAssertNil(tool.inputSchema)
    }
}
