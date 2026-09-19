@testable import Fichero
import FicheroAPIClient
import XCTest

/// #4886 (kg.tables.entities-master-claims-detail): the Claims pane's entity
/// scope reads/acts through the EXISTING `ClaimStore` — not a mirrored loader
/// (see `ClaimsLibraryContent.claimStore`'s own doc comment for the collision
/// trace that cleared this). This proves the STORE half of that wiring with a
/// real `ClaimStore` against a mock transport — the harness is copied from
/// `ClaimStoreTests.swift`, matching its own "copied locally, not shared" note.
@MainActor
final class ClaimsLibraryContentEntityScopeWiringTests: XCTestCase {

    // MARK: - Mock transport (copied, not shared)

    private struct Stub {
        let pathContains: String
        let method: String
        let status: Int
        let body: Data
    }

    private final class MockTransportURLProtocol: URLProtocol {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var stubs: [Stub] = []
        nonisolated(unsafe) private static var requests: [URLRequest] = []

        static func reset(_ stubs: [Stub]) {
            lock.lock()
            self.stubs = stubs
            requests = []
            lock.unlock()
        }

        static func recorded() -> [URLRequest] {
            lock.lock()
            defer { lock.unlock() }
            return requests
        }

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.host == "127.0.0.1" && request.url?.path.hasPrefix("/api/") == true
        }

        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest {
            request
        }

        override func startLoading() {
            let path = request.url?.path ?? ""
            let method = request.httpMethod ?? ""
            Self.lock.lock()
            Self.requests.append(request)
            let stub = Self.stubs.first {
                !$0.pathContains.isEmpty && path.contains($0.pathContains) && $0.method == method
            }
            Self.lock.unlock()

            let resolved = stub ?? Stub(pathContains: "", method: "", status: 200, body: Data("{}".utf8))
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: resolved.status,
                httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: resolved.body)
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}
    }

    override func setUp() {
        super.setUp()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        MockTransportURLProtocol.reset([])
    }

    private static func storeWithMockTransport() -> ClaimStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/ClaimsLibraryContentEntityScopeWiringTests.fichero",
            session: session
        )
        return ClaimStore(
            entityService: EntityService(ficheroClient: client),
            kgCurationService: KGCurationService(ficheroClient: client),
            libraryPath: "/tmp/ClaimsLibraryContentEntityScopeWiringTests.fichero"
        )
    }

    /// `KnowledgeClaim` requires only `text` — everything else optional.
    private static func claimJSON(id: String, text: String = "hello") -> [String: Any] {
        ["id": id, "text": text]
    }

    func testStorePreSeededForAnEntityYieldsThoseClaimsToTheNarrowedScope() async throws {
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/claims", method: "GET", status: 200,
                body: try JSONSerialization.data(withJSONObject: [
                    "items": [Self.claimJSON(id: "c1"), Self.claimJSON(id: "c2")],
                    "count": 2
                ] as [String: Any])
            )
        ])
        let store = Self.storeWithMockTransport()

        // The exact call `ClaimsLibraryContent`'s `.task(id: kgFocusState?
        // .focusedEntityId)` makes when an entity is focused.
        await store.loadClaims(forEntity: "e1")

        // The pane's own scope decision, driving which store backs `items`.
        let scope = ClaimsLibraryContent.effectiveScope(
            focusedEntityId: "e1", folderId: "folder-1", showingAllOverride: false
        )
        XCTAssertEqual(scope, .entity("e1"))
        XCTAssertEqual(store.claims.map(\.id), ["c1", "c2"], "the pre-seeded entity claims must be what the narrowed scope reads")

        // Assert the actual request, not a constant ("test the value the app sent").
        let request = MockTransportURLProtocol.recorded().first { $0.url?.path.contains("/api/claims") == true }
        XCTAssertEqual(request?.url?.query?.contains("entity_id=e1"), true)
    }

    func testAFolderChangeWhileAnEntityIsFocusedStaysEntityScoped() {
        // The focus-wins-over-folder ordering, pinned explicitly: a naive `??`
        // in the wrong direction would let a folder change silently drop the
        // narrowing.
        let scopeBeforeFolderChange = ClaimsLibraryContent.effectiveScope(
            focusedEntityId: "e1", folderId: "folder-1", showingAllOverride: false
        )
        let scopeAfterFolderChange = ClaimsLibraryContent.effectiveScope(
            focusedEntityId: "e1", folderId: "folder-2", showingAllOverride: false
        )
        XCTAssertEqual(scopeBeforeFolderChange, .entity("e1"))
        XCTAssertEqual(scopeAfterFolderChange, .entity("e1"))
    }
}
