//
//  ChangeStreamReconnectRegistersLibraryTests.swift
//  FicheroTests
//
//  #5468: the engine serves a project the owner registered (`POST /api/registry/add`) only
//  until it stops. An engine that restarts while the app keeps running has forgotten every open
//  project and refuses them (403, `failed_check=roots`) until they are registered again. The
//  change stream's reconnect is the moment the app knows the engine came back, so it registers
//  the project again, through the SAME registry call an open makes, BEFORE it asks for the stream.
//
//  Driven through the real reconnect loop (`LibraryChangeStream.start()`, its backoff and
//  `hasConnectedBefore`) and the real `KnownLibraryRegistryStore` on a mock-transported client;
//  the hook is wired exactly as `LibraryReference.changeStream` wires it.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Records the registry requests, scoped to this suite's host so no other suite's mock sees them.
private final class ReconnectRegistryURLProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var adds: [String] = []

    static func reset() {
        lock.lock(); adds = []; lock.unlock()
    }

    static func recordedAdds() -> [String] {
        lock.lock(); defer { lock.unlock() }
        return adds
    }

    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "127.0.0.1" && request.url?.path.hasPrefix("/api/registry") == true
    }

    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else { return }
        if request.httpMethod == "POST", url.path == "/api/registry/add" {
            let path = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                .queryItems?.first { $0.name == "path" }?.value ?? ""
            Self.lock.lock(); Self.adds.append(path); Self.lock.unlock()
        }
        let body = url.path == "/api/registry/add"
            ? Data(#"{"path":"/Users/Shared/ReconnectTest.fichero"}"#.utf8)
            : Data(#"{"libraries":[]}"#.utf8)
        let response = HTTPURLResponse(
            url: url, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct ChangeStreamReconnectRegistersLibraryTests {

    /// Each connect ends cleanly at once (the engine went away), so the loop reconnects after its
    /// first backoff. Records how many registry adds had landed when each connect was made.
    private final class EndingTransport: ChangeStreamTransport {
        var addsSeenAtConnect: [Int] = []

        func connect(_ request: URLRequest) async throws
            -> (status: Int, lines: AsyncThrowingStream<String, any Error>) {
            addsSeenAtConnect.append(ReconnectRegistryURLProtocol.recordedAdds().count)
            let lines = AsyncThrowingStream<String, any Error> { $0.finish() }
            return (200, lines)
        }
    }

    private func makeRegistry() -> KnownLibraryRegistryStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ReconnectRegistryURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: nil,
            session: URLSession(configuration: configuration)
        )
        return KnownLibraryRegistryStore(apiClient: APIClient(client: client))
    }

    /// WHY: #5468. If this goes red, an engine restart leaves every open project refused
    /// (403, roots) until the app relaunches: the reconnect must register the project again,
    /// even though it was already registered once this session, and BEFORE the stream connects.
    @Test("a reconnect registers the open project again, before the stream reconnects")
    func reconnectReRegistersTheOpenProject() async throws {
        ReconnectRegistryURLProtocol.reset()
        // The loopback token, as the other mock-transported suites set it, so no request waits on a token read.
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let registry = makeRegistry()
        let url = URL(fileURLWithPath: "/Users/Shared/ReconnectTest.fichero")

        // Opened earlier this session: one registration, as an open makes it.
        await registry.noteOpenedLibrary(url: url, displayName: "Reconnect Test")
        #expect(ReconnectRegistryURLProtocol.recordedAdds() == [url.path])

        let transport = EndingTransport()
        let stream = LibraryChangeStream(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: url.path,
            transport: transport,
            beforeReconnect: { await registry.noteReconnected(url: url, displayName: "Reconnect Test") }
        )
        stream.start()
        defer { stream.stop() }

        // First connect at once; the reconnect after the 1s backoff (bounded at 30s).
        for _ in 0..<300 where transport.addsSeenAtConnect.count < 2 {
            try await Task.sleep(for: .milliseconds(100))
        }

        #expect(transport.addsSeenAtConnect.count >= 2, "the stream never reconnected")
        #expect(transport.addsSeenAtConnect.first == 1, "the FIRST connect does not register again")
        #expect(
            transport.addsSeenAtConnect.dropFirst().first == 2,
            "the reconnect registered the project before it asked for the stream"
        )
        #expect(Array(ReconnectRegistryURLProtocol.recordedAdds().prefix(2)) == [url.path, url.path])
    }
}
