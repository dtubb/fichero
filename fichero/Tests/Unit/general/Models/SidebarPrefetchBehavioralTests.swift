@testable import Fichero
import FicheroAPIClient
import Foundation
import XCTest

/// #4294 — sidebar one-level chevron prefetch stopped firing (regression watch
/// over the #4228 batching rewrite).
///
/// The existing coverage was a SOURCE-GREP (`testSidebarPrefetchesOneLevelDown
/// ForChevrons` asserts the calls exist in the file) plus pure-function tests
/// of the batch helpers — neither proves that loading roots actually lands
/// grandchildren in `childrenCache`. This suite drives the REAL
/// `DocumentStore` against a stubbed URLProtocol transport (same infra as
/// `EntityServiceTransportTests`; roots/children are GET data-tasks, which the
/// stub intercepts) and asserts the behavior the chevrons depend on:
///
/// - `loadCollections()` fills `childrenCache` one level below the roots with
///   ZERO expansions — the chevron data for "a folder of folders" (#3355).
/// - `loadSidebarChildren(of:)` (the disclosure-toggle path) caches the
///   folder's children AND one level deeper.
/// - The prefetched rows surface through `sidebarDocuments` — the exact input
///   `SidebarItemBuilder`/`sidebarTreeSignature` consume, so a cache fill that
///   never reached the tree would fail here, not just in the UI.
@MainActor
final class SidebarPrefetchBehavioralTests: XCTestCase {

    // MARK: - Stub transport

    private struct Stub {
        let pathSuffix: String
        let body: String
    }

    private final class PrefetchStubURLProtocol: URLProtocol {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var stubs: [Stub] = []
        nonisolated(unsafe) private static var requestedPaths: [String] = []

        static func reset(_ stubs: [Stub]) {
            lock.lock()
            self.stubs = stubs
            requestedPaths = []
            lock.unlock()
        }

        static func recordedPaths() -> [String] {
            lock.lock()
            defer { lock.unlock() }
            return requestedPaths
        }

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.path.hasPrefix("/api/") == true
        }

        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest {
            request
        }

        override func startLoading() {
            let path = request.url?.path ?? ""
            Self.lock.lock()
            Self.requestedPaths.append(path)
            let stub = Self.stubs.first { path.hasSuffix($0.pathSuffix) }
            Self.lock.unlock()

            let body = stub?.body ?? #"{"items":[],"count":0}"#
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}
    }

    // MARK: - Fixtures

    private func docJSON(_ id: String, parent: String?, docType: String) -> String {
        let parentJSON = parent.map { "\"\($0)\"" } ?? "null"
        // The generated Document schema requires name + both expected_* paths.
        return #"{"id":"\#(id)","name":"\#(id)","parent_id":\#(parentJSON),"# +
            #""doc_type":"\#(docType)","status":"completed","# +
            #""expected_thumbnail_path":"thumbnails/\#(id).jpg","# +
            #""expected_display_path":"display/\#(id).jpg"}"#
    }

    private func listJSON(_ docs: [String]) -> String {
        #"{"items":[\#(docs.joined(separator: ","))],"count":\#(docs.count)}"#
    }

    private func makeStore(stubs: [Stub]) -> DocumentStore {
        PrefetchStubURLProtocol.reset(stubs)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [PrefetchStubURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/sidebar-prefetch-test.fichero",
            session: session
        )
        return DocumentStore(apiClient: APIClient(client: client))
    }

    override func setUp() async throws {
        try await super.setUp()
        // AuthTokenMiddleware resolves instantly from the env token on
        // loopback instead of stalling per request on a missing .api-key file.
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
    }

    // MARK: - Root load (#3355 / #4294)

    func testRootLoadPrefetchesOneLevelWithoutAnyExpansion() async throws {
        let store = makeStore(stubs: [
            Stub(pathSuffix: "/api/documents/roots", body: listJSON([
                docJSON("rootA", parent: nil, docType: "folder"),
                docJSON("rootB", parent: nil, docType: "folder"),
                docJSON("rootFile", parent: nil, docType: "file")
            ])),
            Stub(pathSuffix: "/documents/rootA/children", body: listJSON([
                docJSON("subA1", parent: "rootA", docType: "folder")
            ])),
            Stub(pathSuffix: "/documents/rootB/children", body: listJSON([]))
        ])

        await store.loadCollections()

        // The regression this pins: children of every ROOT folder are cached
        // one level down with no click and no expansion anywhere.
        XCTAssertEqual(
            store.childrenCache["rootA"]?.map(\.id), ["subA1"],
            "root folder's children must be prefetched on load — chevrons depend on it (#4294)"
        )
        XCTAssertEqual(
            store.childrenCache["rootB"]?.count, 0,
            "an empty answer is cached too — [] means 'fetched, none', so no re-fetch"
        )

        // Leaf roots are never fetched.
        let paths = PrefetchStubURLProtocol.recordedPaths()
        XCTAssertFalse(
            paths.contains { $0.hasSuffix("/documents/rootFile/children") },
            "files have nothing to disclose — no round-trip"
        )
    }

    func testPrefetchedChildrenSurfaceInSidebarDocuments() async throws {
        // The tree builder and the rebuild signature both read
        // `sidebarDocuments`; a cache fill that never reached it would render
        // no chevron even though the fetch happened.
        let store = makeStore(stubs: [
            Stub(pathSuffix: "/api/documents/roots", body: listJSON([
                docJSON("rootA", parent: nil, docType: "folder")
            ])),
            Stub(pathSuffix: "/documents/rootA/children", body: listJSON([
                docJSON("subA1", parent: "rootA", docType: "folder")
            ]))
        ])

        await store.loadCollections()

        XCTAssertTrue(
            store.sidebarDocuments.contains { $0.id == "subA1" },
            "prefetched child must flow into sidebarDocuments for the tree builder"
        )
    }

    // MARK: - Expansion (disclosure toggle path)

    func testExpansionCachesChildrenAndPrefetchesOneLevelDeeper() async throws {
        let folder = Document(id: "top", parentId: nil, docType: .folder, name: "top")
        let store = makeStore(stubs: [
            Stub(pathSuffix: "/documents/top/children", body: listJSON([
                docJSON("mid", parent: "top", docType: "folder"),
                docJSON("midFile", parent: "top", docType: "file")
            ])),
            Stub(pathSuffix: "/documents/mid/children", body: listJSON([
                docJSON("leaf", parent: "mid", docType: "file")
            ]))
        ])

        await store.loadSidebarChildren(of: folder)

        XCTAssertEqual(
            store.childrenCache["top"]?.map(\.id), ["mid", "midFile"],
            "expanding caches the folder's own children"
        )
        XCTAssertEqual(
            store.childrenCache["mid"]?.map(\.id), ["leaf"],
            "…and one level deeper, so the revealed subfolder has its chevron (#3355)"
        )
        // One level ONLY — the grandchild file has no fetch, and nothing below
        // `mid` was asked for beyond its own children.
        let paths = PrefetchStubURLProtocol.recordedPaths()
        XCTAssertFalse(
            paths.contains { $0.hasSuffix("/documents/leaf/children") },
            "prefetch is bounded to one level below the expansion"
        )
    }

    func testExpansionDoesNotRefetchCachedChildren() async throws {
        let folder = Document(id: "top", parentId: nil, docType: .folder, name: "top")
        let store = makeStore(stubs: [
            Stub(pathSuffix: "/documents/top/children", body: listJSON([
                docJSON("mid", parent: "top", docType: "folder")
            ])),
            Stub(pathSuffix: "/documents/mid/children", body: listJSON([]))
        ])

        await store.loadSidebarChildren(of: folder)
        let pathsAfterFirst = PrefetchStubURLProtocol.recordedPaths().count

        await store.loadSidebarChildren(of: folder)

        XCTAssertEqual(
            PrefetchStubURLProtocol.recordedPaths().count, pathsAfterFirst,
            "a second expansion of a fully cached subtree issues no requests"
        )
    }
}
