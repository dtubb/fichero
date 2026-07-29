@testable import Fichero
import Foundation
import XCTest

/// Tests for the inspector text-editor reliability cluster (#2476/#2477/#2478,
/// #2479 consumer-side).
///
/// Two store-level behaviours are unit-testable without a live backend:
///   • Self-echo suppression — a `document.updated` event echoing THIS device's
///     own save is dropped so the row isn't re-fetched + re-spliced (which would
///     reset the page editor, #2478); a genuine remote update still applies in
///     place (#2479).
///   • Active page-edit flush — the focused editor registers a flush the store
///     runs before an external navigation / tab switch changes the document, so
///     the in-flight edit is persisted instead of discarded (#2476).
@MainActor
final class InspectorEditorReliabilityTests: XCTestCase {

    // MARK: - Self-echo suppression (#2478 / #2479)

    /// The echo of our OWN write is dropped: `apply` schedules no patch for it,
    /// so the row is never re-fetched and the editor never rebuilds (#2478).
    func testOwnWriteEchoIsDroppedFromApply() throws {
        let store = DocumentStore(apiClient: APIClient())
        store.markOwnWrite("a")

        store.apply(try makeEvent(type: "document.updated", documentIds: ["a"]))

        XCTAssertTrue(store.pendingPatchIds.isEmpty,
                      "the echo of our own save must not schedule a re-fetch")
    }

    /// An update from ANOTHER device — no own-write marker — is applied in place
    /// (scheduled for the granular patch), so cross-device edits still land (#2479).
    func testRemoteUpdateIsAppliedNotDropped() throws {
        let store = DocumentStore(apiClient: APIClient())

        store.apply(try makeEvent(type: "document.updated", documentIds: ["b"]))

        XCTAssertEqual(store.pendingPatchIds, ["b"],
                      "a remote update with no own-write marker must be patched in place")
    }

    /// A mixed event — one own echo, one genuine remote id — drops only the echo
    /// and keeps the remote id. The self-echo filter is per-document, not
    /// all-or-nothing (#2479).
    func testMixedEventDropsOnlyOwnEcho() throws {
        let store = DocumentStore(apiClient: APIClient())
        store.markOwnWrite("a")

        store.apply(try makeEvent(type: "document.updated", documentIds: ["a", "b"]))

        XCTAssertEqual(store.pendingPatchIds, ["b"],
                      "only the own-write echo is dropped; the remote id is patched")
    }

    /// `consumeOwnWriteEcho` is single-use: the first call (the echo) consumes
    /// the marker, a second call (a genuinely-later remote edit to the same doc)
    /// returns false so it is NOT suppressed.
    func testOwnWriteMarkerIsConsumedOnce() {
        let store = DocumentStore(apiClient: APIClient())
        store.markOwnWrite("a")

        XCTAssertTrue(store.consumeOwnWriteEcho("a"), "the first echo is recognised")
        XCTAssertFalse(store.consumeOwnWriteEcho("a"),
                       "a later edit to the same doc must not be suppressed")
    }

    /// A stale own-write marker (older than the echo window) does NOT suppress:
    /// the event is treated as a legitimate remote update and patched in place.
    func testStaleOwnWriteMarkerDoesNotSuppress() throws {
        let store = DocumentStore(apiClient: APIClient())
        // Force a marker older than the suppression window.
        store.recentOwnWrites["a"] = Date(timeIntervalSinceNow: -(store.ownWriteEchoWindow + 5))

        store.apply(try makeEvent(type: "document.updated", documentIds: ["a"]))

        XCTAssertEqual(store.pendingPatchIds, ["a"],
                      "an expired marker must not drop a later legitimate update")
    }

    /// Self-echo suppression is scoped to updates/creates — a `document.deleted`
    /// for a doc we wrote is still applied (deletes are authoritative).
    func testDeleteIsNotSuppressedByOwnWriteMarker() throws {
        let store = DocumentStore(apiClient: APIClient())
        let docA = makeDoc(id: "a", name: "Alpha")
        store.currentDocuments = [docA]
        store.markOwnWrite("a")

        store.apply(try makeEvent(type: "document.deleted", documentIds: ["a"]))

        XCTAssertTrue(store.currentDocuments.isEmpty,
                      "a delete is authoritative even if we recently wrote the doc")
    }

    // MARK: - Active page-edit flush (#2476)

    /// The store runs the focused editor's registered flush, then a navigation
    /// can proceed knowing the edit is persisted.
    func testFlushActivePageEditRunsRegisteredFlush() async {
        let store = DocumentStore(apiClient: APIClient())
        let flushed = Box(false)
        store.registerActivePageEdit { flushed.set(true) }

        await store.flushActivePageEdit()

        XCTAssertTrue(flushed.value, "flushActivePageEdit must run the registered flush")
    }

    /// After unregister, flushing is a no-op — the editor has left the hierarchy
    /// and there is nothing to persist.
    func testUnregisterStopsFlush() async {
        let store = DocumentStore(apiClient: APIClient())
        let flushed = Box(false)
        store.registerActivePageEdit { flushed.set(true) }
        store.unregisterActivePageEdit()

        await store.flushActivePageEdit()

        XCTAssertFalse(flushed.value, "an unregistered editor must not be flushed")
        XCTAssertNil(store.activePageEditFlush, "unregister clears the hook")
    }

    /// With no editor registered, `flushActivePageEdit` returns immediately so
    /// ordinary navigation pays no cost.
    func testFlushWithNoEditorIsNoOp() async {
        let store = DocumentStore(apiClient: APIClient())
        await store.flushActivePageEdit()
        XCTAssertNil(store.activePageEditFlush)
    }

    // MARK: - Helpers

    private func makeEvent(type: String, documentIds: [String]) throws -> ChangeEvent {
        let payload: [String: Any] = [
            "type": type,
            "document_ids": documentIds,
            "actor": "system"
        ]
        let data = try JSONSerialization.data(withJSONObject: payload)
        return try JSONDecoder().decode(ChangeEvent.self, from: data)
    }

    private func makeDoc(id: String, name: String) -> Document {
        Document(id: id, parentId: "root", docType: .file, name: name)
    }
}

/// Minimal thread-safe box for observing a flag set inside a `@Sendable` flush.
private final class Box<T>: @unchecked Sendable {
    private let lock = NSLock()
    private var _value: T
    init(_ value: T) { _value = value }
    var value: T { lock.lock(); defer { lock.unlock() }; return _value }
    func set(_ value: T) { lock.lock(); _value = value; lock.unlock() }
}
