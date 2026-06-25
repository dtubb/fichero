@testable import Fichero
@testable import FicheroAPIClient
import Foundation
import XCTest

final class WorkflowStreamConnectionTests: XCTestCase {
    private let remoteHost = "https://streaming.tailnet.example:8765"
    private let remoteToken = "stream-device-token"
    private let engineHostKey = "fichero.engine.host"

    override func setUp() {
        super.setUp()
        UserDefaults.standard.set(remoteHost, forKey: engineHostKey)
        AuthTokenMiddleware.clearRemoteToken(hostString: remoteHost)
    }

    override func tearDown() {
        AuthTokenMiddleware.clearRemoteToken(hostString: remoteHost)
        UserDefaults.standard.removeObject(forKey: engineHostKey)
        super.tearDown()
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static func generatedOpenAPIPaths() throws -> Set<String> {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero-api-client")
            .appendingPathComponent("Sources")
            .appendingPathComponent("FicheroAPIClient")
            .appendingPathComponent("openapi.json")
        let data = try Data(contentsOf: url)
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let paths = try XCTUnwrap(root["paths"] as? [String: Any])
        return Set(paths.keys)
    }

    func testWorkflowEventStreamRequestUsesAPIBaseURLAndEngineAuth() throws {
        try AuthTokenMiddleware.persistRemoteToken(remoteToken, hostString: remoteHost)

        let request = engineEventStreamRequest(
            baseURL: URL(string: remoteHost)!.appendingPathComponent("api"),
            pathComponents: ["workflow-execution", "stream", "thread-123"],
            libraryPath: "/tmp/Test.fichero"
        )

        XCTAssertEqual(
            request.url?.absoluteString,
            "https://streaming.tailnet.example:8765/api/workflow-execution/stream/thread-123"
        )
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "text/event-stream")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer \(remoteToken)")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Fichero-Library-Path"), "/tmp/Test.fichero")
    }

    func testLibraryChangeStreamRequestUsesSharedAPIPathAndEngineAuth() throws {
        try AuthTokenMiddleware.persistRemoteToken(remoteToken, hostString: remoteHost)

        let request = engineEventStreamRequest(
            baseURL: URL(string: remoteHost)!.appendingPathComponent("api"),
            pathComponents: ["changes", "stream"],
            libraryPath: "/tmp/Test.fichero"
        )

        XCTAssertEqual(
            request.url?.absoluteString,
            "https://streaming.tailnet.example:8765/api/changes/stream"
        )
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "text/event-stream")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer \(remoteToken)")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-Fichero-Library-Path"), "/tmp/Test.fichero")
    }

    func testSSEStreamPathsExistInGeneratedOpenAPI() throws {
        let paths = try Self.generatedOpenAPIPaths()

        XCTAssertTrue(paths.contains("/api/changes/stream"))
        XCTAssertTrue(paths.contains("/api/workflow-execution/stream/{thread_id}"))
    }

    func testWorkflowStreamServiceKeepsPinnedSessionAndSharedAPIBaseURL() throws {
        let source = try Self.appSource("Services/WorkflowStreamService.swift")

        XCTAssertTrue(source.contains("RemoteCertificatePinning.configuredSession()"))
        XCTAssertTrue(source.contains("engineEventStreamRequest("))
        XCTAssertTrue(source.contains("baseURL: client.apiBaseURL"))
    }

    func testLibraryChangeStreamKeepsPinnedSessionAndSharedRequestBuilder() throws {
        let source = try Self.appSource("Services/LibraryChangeStream.swift")

        XCTAssertTrue(source.contains("RemoteCertificatePinning.configuredSession()"))
        XCTAssertTrue(source.contains("engineEventStreamRequest("))
        XCTAssertTrue(source.contains("pathComponents: [\"changes\", \"stream\"]"))
    }
}
