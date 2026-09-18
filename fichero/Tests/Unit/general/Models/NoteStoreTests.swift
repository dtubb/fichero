@testable import Fichero
import FicheroAPIClient
import XCTest

/// #4824 — `NoteStore`'s create/update/delete mutators used to throw away
/// `NoteService`'s already-correct in-place splice by calling `await
/// reload()` (a full server re-fetch) right after. These are the FIRST tests
/// for this store (none existed before this delivery). They assert IDENTITY
/// preservation — untouched notes are unchanged, in the same order, and no
/// list re-fetch (`GET /api/notes`) happens alongside the mutation's own
/// request — plus `Scope.belongs(_:to:)`, the pure predicate that decides
/// whether a mutated note belongs on the CURRENTLY-VISIBLE list.
///
/// Mock transport copied locally from `ProviderAPIServiceKeyPersistenceTests.swift`
/// (not shared, per this session's established instruction). Same #4024
/// limitation applies: `httpBody` is unreadable through the stub, so
/// assertions are on recorded method/path, never wire body content.
@MainActor
final class NoteStoreTests: XCTestCase {

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
            // Runtime values — a force-unwrap here would crash the whole test
            // host on a malformed fixture, not just fail one test. Fail the
            // individual load instead.
            guard let url = request.url,
                  let response = HTTPURLResponse(
                      url: url,
                      statusCode: resolved.status,
                      httpVersion: "HTTP/1.1",
                      headerFields: ["Content-Type": "application/json"]
                  ) else {
                client?.urlProtocol(self, didFailWithError: URLError(.badURL))
                return
            }
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

    private static func storeWithMockTransport() -> NoteStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/NoteStoreTests.fichero",
            session: session
        )
        let service = NoteService(ficheroClient: client)
        return NoteStore(noteService: service)
    }

    /// A store whose `scope` is already `.document(documentId)` with an empty
    /// list — the state every real caller is in before creating/editing/
    /// deleting a note in a document-scoped view. `belongs(_:to:)` reads
    /// `store.scope`, so every mutator test needs this established first.
    private static func storeScopedToDocument(_ documentId: String) async -> NoteStore {
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes", method: "GET", status: 200, body: Data(#"{"items":[],"count":0}"#.utf8))
        ])
        let store = Self.storeWithMockTransport()
        await store.loadNotes(forDocument: documentId)
        MockTransportURLProtocol.reset([])
        return store
    }

    private static func noteJSON(id: String, documentId: String? = nil, kind: String = "reference") -> Data {
        var fields: [String: Any] = ["id": id, "body": "hello", "kind": kind, "tags": []]
        if let documentId { fields["linked_document_ids"] = [documentId] }
        return try! JSONSerialization.data(withJSONObject: fields)
    }

    // MARK: - Scope.belongs(_:to:) — pure, exhaustive

    func testBelongsToDocumentScope() throws {
        let note = try JSONDecoder().decode(NoteItem.self, from: Self.noteJSON(id: "n1", documentId: "doc-1"))
        XCTAssertTrue(NoteStore.belongs(note, to: .document("doc-1")))
        XCTAssertFalse(NoteStore.belongs(note, to: .document("doc-2")))
    }

    func testBelongsToPageScope() throws {
        let data = try JSONSerialization.data(withJSONObject: [
            "id": "n1", "body": "hello", "kind": "reference", "tags": [], "page_id": "page-1"
        ])
        let note = try JSONDecoder().decode(NoteItem.self, from: data)
        XCTAssertTrue(NoteStore.belongs(note, to: .page("page-1")))
        XCTAssertFalse(NoteStore.belongs(note, to: .page("page-2")))
    }

    func testBelongsToFolderScope() throws {
        let data = try JSONSerialization.data(withJSONObject: [
            "id": "n1", "body": "hello", "kind": "reference", "tags": [], "folder_id": "folder-1"
        ])
        let note = try JSONDecoder().decode(NoteItem.self, from: data)
        XCTAssertTrue(NoteStore.belongs(note, to: .folder("folder-1")))
        XCTAssertFalse(NoteStore.belongs(note, to: .folder("folder-2")))
    }

    func testBelongsToEntityScope() throws {
        let data = try JSONSerialization.data(withJSONObject: [
            "id": "n1", "body": "hello", "kind": "reference", "tags": [], "linked_entity_ids": ["entity-1"]
        ])
        let note = try JSONDecoder().decode(NoteItem.self, from: data)
        XCTAssertTrue(NoteStore.belongs(note, to: .entity("entity-1")))
        XCTAssertFalse(NoteStore.belongs(note, to: .entity("entity-2")))
    }

    func testBelongsToAllScopeMatchesOnKindWhenTagAndQueryAreEmpty() throws {
        let note = try JSONDecoder().decode(NoteItem.self, from: Self.noteJSON(id: "n1", kind: "reference"))
        XCTAssertTrue(NoteStore.belongs(note, to: .all(kind: "reference", tag: "", query: "")))
        XCTAssertFalse(NoteStore.belongs(note, to: .all(kind: "highlight", tag: "", query: "")))
    }

    func testBelongsToAllScopeSkipsSpliceWhenQueryOrTagIsPresent() throws {
        // A full-text query can't be re-evaluated client-side from the
        // returned item alone — the predicate must refuse to guess.
        let note = try JSONDecoder().decode(NoteItem.self, from: Self.noteJSON(id: "n1", kind: "reference"))
        XCTAssertFalse(NoteStore.belongs(note, to: .all(kind: "", tag: "", query: "search term")))
        XCTAssertFalse(NoteStore.belongs(note, to: .all(kind: "", tag: "urgent", query: "")))
    }

    func testBelongsToNoneScopeIsAlwaysFalse() throws {
        let note = try JSONDecoder().decode(NoteItem.self, from: Self.noteJSON(id: "n1"))
        XCTAssertFalse(NoteStore.belongs(note, to: .none))
    }

    // MARK: - Mutators splice in place, no reload

    func testCreateForDocumentSplicesInPlaceWithoutReload() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes", method: "POST", status: 200, body: Self.noteJSON(id: "n2", documentId: "doc-1"))
        ])

        let created = try await store.createForDocument("doc-1", body: "new note")

        XCTAssertEqual(created.id, "n2")
        XCTAssertTrue(store.notes.contains { $0.id == "n2" }, "the created note must be spliced into the list")
        // Only the create's own POST fired — no GET /api/notes list re-fetch.
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1)
        XCTAssertEqual(requests.first?.httpMethod, "POST")
    }

    func testCreateForDocumentSkipsSpliceWhenTheNoteIsOutOfTheCurrentScope() async throws {
        // Store is scoped to document "doc-1"; the service returns a note
        // linked to a DIFFERENT document — must not leak into the list.
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes", method: "POST", status: 200, body: Self.noteJSON(id: "n3", documentId: "doc-99"))
        ])

        let created = try await store.createForDocument("doc-1", body: "misrouted")

        XCTAssertEqual(created.id, "n3", "the created note is still returned to the caller")
        XCTAssertFalse(store.notes.contains { $0.id == "n3" }, "an out-of-scope note must not appear in the current list")
    }

    func testUpdateSplicesInPlaceByIndex() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes", method: "POST", status: 200, body: Self.noteJSON(id: "n1", documentId: "doc-1"))
        ])
        _ = try await store.createForDocument("doc-1", body: "original")
        XCTAssertEqual(store.notes.count, 1)

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes/n1", method: "PATCH", status: 200, body: Self.noteJSON(id: "n1", documentId: "doc-1"))
        ])
        _ = try await store.update(noteId: "n1", body: "edited")

        XCTAssertEqual(store.notes.count, 1, "update must not change the list's length")
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the PATCH — no list re-fetch")
        XCTAssertEqual(requests.first?.httpMethod, "PATCH")
    }

    func testUpdateRemovesTheRowWhenTheEditMovesItOutOfScope() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes", method: "POST", status: 200, body: Self.noteJSON(id: "n1", documentId: "doc-1"))
        ])
        _ = try await store.createForDocument("doc-1", body: "original")
        XCTAssertEqual(store.notes.count, 1)

        // The PATCH response now links the note to a DIFFERENT document —
        // it should drop out of this document-scoped list.
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes/n1", method: "PATCH", status: 200, body: Self.noteJSON(id: "n1", documentId: "doc-99"))
        ])
        _ = try await store.update(noteId: "n1", body: "moved")

        XCTAssertTrue(store.notes.isEmpty, "a note edited out of the current scope must leave the list")
    }

    func testDeleteRemovesInPlaceWithoutReload() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes", method: "POST", status: 200, body: Self.noteJSON(id: "n1", documentId: "doc-1"))
        ])
        _ = try await store.createForDocument("doc-1", body: "original")
        XCTAssertEqual(store.notes.count, 1)

        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes/n1", method: "DELETE", status: 204, body: Data())
        ])
        try await store.delete(noteId: "n1")

        XCTAssertTrue(store.notes.isEmpty)
        let requests = MockTransportURLProtocol.recorded()
        XCTAssertEqual(requests.count, 1, "only the DELETE — no list re-fetch")
    }

    func testDeleteFailureLeavesTheListUntouched() async throws {
        let store = await Self.storeScopedToDocument("doc-1")
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes", method: "POST", status: 200, body: Self.noteJSON(id: "n1", documentId: "doc-1"))
        ])
        _ = try await store.createForDocument("doc-1", body: "original")
        XCTAssertEqual(store.notes.count, 1)

        // A 422 makes NoteService.delete throw before it ever reaches
        // `notes.removeAll` — the store's mutator must propagate that same
        // failure and never touch its own list either.
        MockTransportURLProtocol.reset([
            Stub(pathContains: "/api/notes/n1", method: "DELETE", status: 422, body: Data(#"{"detail":"nope"}"#.utf8))
        ])
        do {
            try await store.delete(noteId: "n1")
            XCTFail("expected the failed delete to throw")
        } catch {
            // Expected.
        }

        XCTAssertEqual(store.notes.count, 1, "a failed delete must not remove the row")
    }
}
