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

    func testLocalHTTPSStreamFailureExplainsTLSBackendRequirement() throws {
        let message = WorkflowStreamError.streamFailureDescription(
            error: URLError(.cannotConnectToHost),
            streamURL: URL(string: "https://127.0.0.1:8765/api/workflow-execution/stream/thread-123")!
        )

        XCTAssertTrue(message.contains("not reachable over HTTPS"))
        XCTAssertTrue(message.contains("fichero-engine/scripts/start_backend.sh"))
        XCTAssertTrue(message.contains("TLS and pinning"))
    }

    func testPlainHTTPDevEngineHostRemainsInvalid() {
        XCTAssertEqual(
            EngineConfig.hostConfiguration(from: "http://127.0.0.1:8765"),
            .invalid("http://127.0.0.1:8765")
        )
    }

    func testWorkflowStreamStopRequestsCancelNotCheckpointDelete() throws {
        let source = try Self.appSource("Services/WorkflowStreamService.swift")
        let stopRange = try XCTUnwrap(source.range(of: "func stopWorkflow(threadId: String) async throws"))
        let resumeRange = try XCTUnwrap(source.range(
            of: "func resumeWorkflow(threadId: String",
            range: stopRange.upperBound..<source.endIndex
        ))
        let stopBody = String(source[stopRange.lowerBound..<resumeRange.lowerBound])

        XCTAssertTrue(stopBody.contains("executionService.stopWorkflow"))
        XCTAssertFalse(stopBody.contains("deleteThreadApiWorkflowExecutionThreadsThreadIdDelete"))
        XCTAssertFalse(stopBody.contains("cancelWorkflowApiWorkflowExecutionThreadsThreadIdCancelPost"))
    }

    func testWorkflowStreamRESTActionsDelegateToExecutionService() throws {
        let source = try Self.appSource("Services/WorkflowStreamService.swift")

        XCTAssertTrue(source.contains("WorkflowExecutionService(ficheroClient: ficheroClient)"))
        XCTAssertTrue(source.contains("executionService.executeAccepted"))
        XCTAssertTrue(source.contains("executionService.stopWorkflow"))
        XCTAssertTrue(source.contains("executionService.resumeWorkflow"))
    }

    func testLibraryChangeStreamKeepsPinnedSessionAndSharedRequestBuilder() throws {
        let source = try Self.appSource("Services/LibraryChangeStream.swift")

        XCTAssertTrue(source.contains("RemoteCertificatePinning.configuredSession()"))
        XCTAssertTrue(source.contains("engineEventStreamRequest("))
        XCTAssertTrue(source.contains("pathComponents: [\"changes\", \"stream\"]"))
    }

    func testExecutionStatusMapsStableTerminalStatuses() {
        XCTAssertEqual(WorkflowExecutionService.mapStatus("completed"), .completed)
        XCTAssertEqual(WorkflowExecutionService.mapStatus("error"), .error)
        XCTAssertEqual(WorkflowExecutionService.mapStatus("failed"), .failed)
        XCTAssertEqual(WorkflowExecutionService.mapStatus("cancelled"), .cancelled)
        XCTAssertEqual(WorkflowExecutionService.mapStatus("stopped"), .stopped)
        XCTAssertEqual(WorkflowExecutionService.mapStatus("deleted"), .deleted)
    }
}
