@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// #5003: one page change made five artifact requests, and a typed request poisoned the cache.
/// Both rules live in `ArtifactService.getArtifacts`, the one seam every caller shares, so they
/// are pinned here against a recording transport (the `EntityServiceTransportTests` pattern):
/// what is asserted is the REQUESTS THE APP SENT, not the service's internals.
@MainActor
final class ArtifactServiceCoalescingTests: XCTestCase {

    private final class RecordingURLProtocol: URLProtocol {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var requests: [URLRequest] = []
        nonisolated(unsafe) static var body = Data()

        static func reset(body: Data) {
            lock.lock(); requests = []; self.body = body; lock.unlock()
        }

        static func artifactRequests() -> [URLRequest] {
            lock.lock(); defer { lock.unlock() }
            return requests.filter { $0.url?.path.contains("/api/artifacts/document/") == true }
        }

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.host == "127.0.0.1" && request.url?.path.hasPrefix("/api/") == true
        }

        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            Self.lock.lock(); Self.requests.append(request); let body = Self.body; Self.lock.unlock()
            let response = HTTPURLResponse(
                url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            // Answer a little later, so callers that ask "at once" really do overlap.
            DispatchQueue.global().asyncAfter(deadline: .now() + 0.15) { [self] in
                client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                client?.urlProtocol(self, didLoad: body)
                client?.urlProtocolDidFinishLoading(self)
            }
        }

        override func stopLoading() {}
    }

    private static func artifactJSON(id: String, type: String) -> String {
        """
        {"id": "\(id)", "document_id": "doc-1", "artifact_type": "\(type)", "version": 1,
         "reviewed": false, "created_at": "2026-09-20T12:00:00Z"}
        """
    }

    private func makeService() -> ArtifactService {
        let items = [
            Self.artifactJSON(id: "a1", type: "transcription"),
            Self.artifactJSON(id: "a2", type: "translation"),
        ].joined(separator: ",")
        RecordingURLProtocol.reset(body: Data("{\"items\": [\(items)], \"count\": 2}".utf8))
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RecordingURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/artifact-service-coalescing-test.fichero",
            session: URLSession(configuration: configuration)
        )
        return ArtifactService(ficheroClient: client)
    }

    override func setUp() async throws {
        try await super.setUp()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
    }

    func testFiveCallersAtOnceSendOneRequest() async throws {
        let service = makeService()
        async let preview = service.getArtifacts(forDocumentId: "doc-1")
        async let reader = service.getArtifacts(forDocumentId: "doc-1", type: "translation")
        async let store = service.getArtifacts(forDocumentId: "doc-1", forceRefresh: true)
        async let overlay = service.getArtifacts(forDocumentId: "doc-1", type: "transcription")
        async let strip = service.getArtifacts(forDocumentId: "doc-1")
        let counts = try await [preview.count, reader.count, store.count, overlay.count, strip.count]
        XCTAssertEqual(counts, [2, 1, 2, 1, 2], "every caller gets its own answer")
        XCTAssertEqual(
            RecordingURLProtocol.artifactRequests().count, 1,
            "one page change must send ONE artifacts request, not one per view"
        )
    }

    func testATypedRequestDoesNotPoisonTheCacheForAnUntypedCaller() async throws {
        let service = makeService()
        let translations = try await service.getArtifacts(forDocumentId: "doc-1", type: "translation")
        XCTAssertEqual(translations.map(\.id), ["a2"])
        let all = try await service.getArtifacts(forDocumentId: "doc-1")
        XCTAssertEqual(Set(all.map(\.id)), ["a1", "a2"], "the cache holds the FULL list, never a filtered one")
        let query = RecordingURLProtocol.artifactRequests().first?.url?.query ?? ""
        XCTAssertFalse(query.contains("artifact_type"), "the server is always asked for every type")
        XCTAssertEqual(RecordingURLProtocol.artifactRequests().count, 1, "the second call is served from the cache")
    }

    func testAForcedRefreshAfterTheFetchHasLandedSendsANewRequest() async throws {
        let service = makeService()
        _ = try await service.getArtifacts(forDocumentId: "doc-1")
        _ = try await service.getArtifacts(forDocumentId: "doc-1", forceRefresh: true)
        XCTAssertEqual(RecordingURLProtocol.artifactRequests().count, 2)
    }

    func testAFetchStartedBeforeACacheClearIsNotJoinedAndNotStored() async throws {
        let service = makeService()
        async let early = service.getArtifacts(forDocumentId: "doc-1")
        // Let the early fetch register, then invalidate: what is on its way may be stale.
        try await Task.sleep(nanoseconds: 30_000_000)
        service.clearCache(forDocumentId: "doc-1")
        let late = try await service.getArtifacts(forDocumentId: "doc-1")
        _ = try await early
        XCTAssertEqual(late.count, 2)
        XCTAssertEqual(
            RecordingURLProtocol.artifactRequests().count, 2,
            "a caller after a write or a clear must not join the older fetch"
        )
    }
}
