@testable import Fichero
import FicheroAPIClient
import XCTest

/// source-model App slice A stage 1 (#4954): `source.app.one-segment-store`.
/// `SegmentStore`/`SegmentService` had NO test at all (test audit, F-none-
/// numbered but named directly: "no test that `SegmentStore`/`SegmentService`
/// exist"). This is their first.
///
/// First tests for this store. Mock transport copied locally (not shared) —
/// the same idiom `ArtifactStoreTests`/`InterpretationStoreTests` use, not a
/// new mocking layer.
@MainActor
final class SegmentStoreTests: XCTestCase {

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
            // host on a malformed fixture, not just fail one test.
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

    private static func storeWithMockTransport() -> SegmentStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockTransportURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/SegmentStoreTests.fichero",
            session: session
        )
        let service = SegmentService(ficheroClient: client)
        return SegmentStore(service: service)
    }

    // MARK: - Fixture JSON (every stub satisfies its response schema's `required` fields)

    private static func passJSON(id: String, documentId: String, name: String = "transcription") -> [String: Any] {
        [
            "id": id, "provisional": false, "document_id": documentId,
            "name": name, "provenance_kind": "workflow"
        ]
    }

    private static func segmentJSON(
        id: String, documentId: String, passId: String, boxIndex: Int, text: String
    ) -> [String: Any] {
        [
            "id": id, "provisional": false, "document_id": documentId, "pass_id": passId,
            "kind": "word", "provenance_kind": "workflow",
            "anchor": ["document_id": documentId, "rect": [0.1, 0.1, 0.2, 0.2]],
            "box_index": boxIndex, "text": text
        ]
    }

    private static func listResponseJSON(
        documentId: String, passes: [[String: Any]], segments: [[String: Any]]
    ) -> Data {
        try! JSONSerialization.data(withJSONObject: [
            "document_id": documentId, "passes": passes, "segments": segments
        ])
    }

    private static func stubSuccess(documentId: String, passes: [[String: Any]], segments: [[String: Any]]) {
        MockTransportURLProtocol.reset([
            Stub(
                pathContains: "/api/segments/document/\(documentId)", method: "GET", status: 200,
                body: listResponseJSON(documentId: documentId, passes: passes, segments: segments)
            )
        ])
    }

    private static func stubFailure(documentId: String, status: Int = 422) -> Stub {
        Stub(
            pathContains: "/api/segments/document/\(documentId)", method: "GET", status: status,
            body: Data(#"{"detail":"nope"}"#.utf8)
        )
    }

    // MARK: - load(documentId:) replaces ONLY that document's entry

    func testLoadReplacesOnlyTheNamedDocumentsEntryLeavesOthersUntouched() async throws {
        let store = Self.storeWithMockTransport()

        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one")]
        )
        await store.load(documentId: "doc-1")
        XCTAssertEqual(store.segments(documentId: "doc-1").map(\.id), ["seg-1"])

        Self.stubSuccess(
            documentId: "doc-2",
            passes: [Self.passJSON(id: "pass-2", documentId: "doc-2")],
            segments: [Self.segmentJSON(id: "seg-2", documentId: "doc-2", passId: "pass-2", boxIndex: 0, text: "two")]
        )
        await store.load(documentId: "doc-2")

        XCTAssertEqual(store.segments(documentId: "doc-2").map(\.id), ["seg-2"], "doc-2 loaded its own segments")
        XCTAssertEqual(
            store.segments(documentId: "doc-1").map(\.id), ["seg-1"],
            "loading doc-2 must not touch doc-1's already-loaded entry"
        )
        XCTAssertEqual(store.passes(documentId: "doc-1").map(\.id), ["pass-1"], "doc-1's passes are also untouched")
    }

    // MARK: - a forced second load replaces in place, not a merge

    func testForceReloadReplacesADocumentsEntryRatherThanMerging() async throws {
        let store = Self.storeWithMockTransport()

        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-old", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "old")]
        )
        await store.load(documentId: "doc-1")
        XCTAssertEqual(store.segments(documentId: "doc-1").map(\.id), ["seg-old"])

        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-2", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-new", documentId: "doc-1", passId: "pass-2", boxIndex: 0, text: "new")]
        )
        await store.load(documentId: "doc-1", force: true)

        XCTAssertEqual(
            store.segments(documentId: "doc-1").map(\.id), ["seg-new"],
            "a forced reload REPLACES the document's entry — the old segment must be gone, not unioned with the new one"
        )
        XCTAssertEqual(store.passes(documentId: "doc-1").map(\.id), ["pass-2"])
    }

    // MARK: - without force, an already-loaded document is not re-fetched

    func testWithoutForceASecondLoadOfAnAlreadyLoadedDocumentDoesNotRefetch() async throws {
        let store = Self.storeWithMockTransport()
        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one")]
        )
        await store.load(documentId: "doc-1")
        await store.load(documentId: "doc-1")  // no force — same document, already loaded, no error

        XCTAssertEqual(
            MockTransportURLProtocol.recorded().count, 1,
            "an unforced load of an already-loaded, error-free document must not issue a second request"
        )
    }

    // MARK: - force bypasses the "already loaded" skip

    func testForceLoadRefetchesEvenWhenAlreadyLoadedSuccessfully() async throws {
        let store = Self.storeWithMockTransport()
        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one")]
        )
        await store.load(documentId: "doc-1")
        await store.load(documentId: "doc-1", force: true)

        XCTAssertEqual(
            MockTransportURLProtocol.recorded().count, 2,
            "force: true must issue a second request even though the document already loaded without error"
        )
    }

    // MARK: - a failed load leaves the previous data and surfaces the error

    /// What the store does today, confirmed by reading `SegmentStore.load(documentId:force:)`:
    /// on `catch`, `segmentsByDocument[documentId]`/`passesByDocument[documentId]`
    /// are NOT written — the previous entry is left exactly as it was — and
    /// `loadErrorsByDocumentId[documentId]` is set from the caught error's
    /// `localizedDescription`. This is NOT a silent swallow: the error is
    /// surfaced through `loadError(documentId:)`. This test pins that
    /// behaviour positively rather than reporting it as a defect.
    func testAFailedForcedReloadKeepsThePreviousDataAndSurfacesTheError() async throws {
        let store = Self.storeWithMockTransport()
        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one")]
        )
        await store.load(documentId: "doc-1")
        XCTAssertNil(store.loadError(documentId: "doc-1"))

        MockTransportURLProtocol.reset([Self.stubFailure(documentId: "doc-1")])
        await store.load(documentId: "doc-1", force: true)

        XCTAssertEqual(
            store.segments(documentId: "doc-1").map(\.id), ["seg-1"],
            "a failed reload must leave the previously loaded segments in place"
        )
        let error = try XCTUnwrap(store.loadError(documentId: "doc-1"), "the failure must be surfaced, not swallowed")
        XCTAssertFalse(error.isEmpty)
    }

    /// The failure half of a document that has NEVER loaded successfully:
    /// no previous data to preserve, but the error still surfaces and the
    /// arrays read back empty rather than crashing.
    func testAFailedFirstLoadSurfacesTheErrorWithEmptyArrays() async throws {
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([Self.stubFailure(documentId: "doc-1", status: 500)])

        await store.load(documentId: "doc-1")

        XCTAssertTrue(store.segments(documentId: "doc-1").isEmpty)
        XCTAssertTrue(store.passes(documentId: "doc-1").isEmpty)
        XCTAssertNotNil(store.loadError(documentId: "doc-1"))
    }

    /// A DELIBERATE consequence of the guard's third condition
    /// (`loadErrorsByDocumentId[documentId] == nil`): once a document has a
    /// recorded error, the NEXT `load` call re-fetches even WITHOUT
    /// `force: true` — the store does not need to be told to retry a document
    /// it knows failed. Pinned here so a future edit to the guard's three
    /// conditions is deliberate, not accidental.
    func testAfterAFailedLoadTheNextCallRetriesWithoutNeedingForce() async throws {
        let store = Self.storeWithMockTransport()
        MockTransportURLProtocol.reset([Self.stubFailure(documentId: "doc-1")])
        await store.load(documentId: "doc-1")
        XCTAssertNotNil(store.loadError(documentId: "doc-1"))

        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one")]
        )
        await store.load(documentId: "doc-1")  // still no force

        XCTAssertEqual(store.segments(documentId: "doc-1").map(\.id), ["seg-1"])
        XCTAssertNil(store.loadError(documentId: "doc-1"), "a successful retry clears the prior error")
    }

    // MARK: - Reacting to change events (source.app.segment-events-patch-in-place)
    //
    // The behaviour: "when the engine says which segments changed, the store
    // replaces those items and no others; when it says this document's results
    // changed, it re-reads that one document". The decision is tested as a
    // decision — `plan` is pure — because "those items and no others" is a claim
    // about what the store CHOOSES, and a test of the choice cannot be fooled by
    // a coincidentally-correct fetch.

    private func changeEvent(
        type: String, documentIds: [String] = [], segmentIds: [String] = []
    ) throws -> ChangeEvent {
        let payload: [String: Any] = [
            "type": type, "document_ids": documentIds, "segment_ids": segmentIds,
            "actor": "historian",
        ]
        return try JSONDecoder().decode(
            ChangeEvent.self, from: try JSONSerialization.data(withJSONObject: payload)
        )
    }

    func testAnEventNamingHeldSegmentsPatchesThoseAndDoesNotReload() throws {
        let event = try changeEvent(
            type: "segment.updated", documentIds: ["doc-1"], segmentIds: ["seg-2"]
        )

        let plan = SegmentStore.plan(
            for: event, heldSegmentIds: ["seg-1", "seg-2"], loadedDocumentIds: ["doc-1"]
        )

        XCTAssertEqual(plan, .patch(segmentIds: ["seg-2"]))
    }

    /// A split adds a row and a delete removes one, so "this document's results
    /// changed" cannot be expressed as a patch of named ids — there is no id for a
    /// row that did not exist before. ONE document, never the whole store.
    func testAnEventNamingNoSegmentReloadsThatOneDocumentOnly() throws {
        let event = try changeEvent(type: "pass.created", documentIds: ["doc-1"])

        let plan = SegmentStore.plan(
            for: event, heldSegmentIds: ["seg-1"], loadedDocumentIds: ["doc-1", "doc-2"]
        )

        XCTAssertEqual(plan, .reload(documentIds: ["doc-1"]))
    }

    func testAnEventAboutADocumentThisStoreNeverLoadedDoesNothing() throws {
        let event = try changeEvent(
            type: "segment.updated", documentIds: ["doc-99"], segmentIds: ["seg-99"]
        )

        let plan = SegmentStore.plan(
            for: event, heldSegmentIds: ["seg-1"], loadedDocumentIds: ["doc-1"]
        )

        XCTAssertEqual(plan, .nothing, "loading a page nobody is looking at is not a repair")
    }

    /// Every segment event also names its document. If the document branch ran
    /// first, every patchable event would become a page reload and the behaviour
    /// would be unimplementable — this ordering IS the behaviour.
    func testPatchWinsOverReloadWhenAnEventCarriesBoth() throws {
        let event = try changeEvent(
            type: "segment.updated", documentIds: ["doc-1"], segmentIds: ["seg-1"]
        )

        let plan = SegmentStore.plan(
            for: event, heldSegmentIds: ["seg-1"], loadedDocumentIds: ["doc-1"]
        )

        XCTAssertEqual(plan, .patch(segmentIds: ["seg-1"]))
    }

    func testPatchReplacesARowInPlaceWithoutMovingAnyOther() async throws {
        let store = Self.storeWithMockTransport()
        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [
                Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one"),
                Self.segmentJSON(id: "seg-2", documentId: "doc-1", passId: "pass-1", boxIndex: 1, text: "two"),
                Self.segmentJSON(id: "seg-3", documentId: "doc-1", passId: "pass-1", boxIndex: 2, text: "three"),
            ]
        )
        await store.load(documentId: "doc-1")

        let json = try JSONSerialization.data(withJSONObject: Self.segmentJSON(
            id: "seg-2", documentId: "doc-1", passId: "pass-1", boxIndex: 1, text: "TWO"
        ))
        let generated = try JSONDecoder().decode(Components.Schemas.SegmentRead.self, from: json)
        store.patch(segmentId: "seg-2", with: Segment(generated: generated))

        // Position is the engine's index (source.app.index-is-the-engines): a patch
        // that reordered would change what every index-addressed reader means.
        XCTAssertEqual(store.segments(documentId: "doc-1").map(\.id), ["seg-1", "seg-2", "seg-3"])
        XCTAssertEqual(store.segments(documentId: "doc-1")[1].text, "TWO")
    }

    /// A surface that SNAPSHOTS this store (the image Preview copies it into its draw
    /// model) keys its reload on `revision(for:)`. Without the bump, ⌘Z on a region edit
    /// -- a segment event, patched here -- left the page drawing the undone edit.
    func testAPatchBumpsThatDocumentsRevisionAndNoOther() async throws {
        let store = Self.storeWithMockTransport()
        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one")]
        )
        await store.load(documentId: "doc-1")
        XCTAssertEqual(
            store.revision(for: "doc-1"), 0,
            "a first load is asked for by the surface; bumping it would re-fire that surface's own task"
        )

        store.patch(segmentId: "seg-1", with: nil)

        XCTAssertEqual(store.revision(for: "doc-1"), 1)
        XCTAssertEqual(store.revision(for: "doc-other"), 0)
    }

    func testAForcedReloadBumpsTheRevisionAndAPatchOfAnUnheldIdDoesNot() async throws {
        let store = Self.storeWithMockTransport()
        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one")]
        )
        await store.load(documentId: "doc-1")
        store.patch(segmentId: "seg-elsewhere", with: nil)
        XCTAssertEqual(store.revision(for: "doc-1"), 0)

        await store.load(documentId: "doc-1", force: true)

        XCTAssertEqual(store.revision(for: "doc-1"), 1)
    }

    func testPatchingWithNothingDropsTheRowRatherThanKeepingAStaleCopy() async throws {
        let store = Self.storeWithMockTransport()
        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [
                Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one"),
                Self.segmentJSON(id: "seg-2", documentId: "doc-1", passId: "pass-1", boxIndex: 1, text: "two"),
            ]
        )
        await store.load(documentId: "doc-1")

        store.patch(segmentId: "seg-1", with: nil)

        XCTAssertEqual(store.segments(documentId: "doc-1").map(\.id), ["seg-2"])
    }

    func testPatchingAnIdThisStoreDoesNotHoldChangesNothing() async throws {
        let store = Self.storeWithMockTransport()
        Self.stubSuccess(
            documentId: "doc-1",
            passes: [Self.passJSON(id: "pass-1", documentId: "doc-1")],
            segments: [Self.segmentJSON(id: "seg-1", documentId: "doc-1", passId: "pass-1", boxIndex: 0, text: "one")]
        )
        await store.load(documentId: "doc-1")

        store.patch(segmentId: "seg-elsewhere", with: nil)

        XCTAssertEqual(
            store.segments(documentId: "doc-1").map(\.id), ["seg-1"],
            "an event about somebody else's page is not an instruction to change this one"
        )
    }

    func testTheStoreConsumesSegmentAndPassEventsOnly() {
        let store = Self.storeWithMockTransport()

        XCTAssertEqual(store.changeDomains, ["segment", "pass"])
    }
}
