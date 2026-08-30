@testable import Fichero
import Foundation
import XCTest

/// Tests for the generic change-stream substrate (#1995) and its first consumer,
/// DocumentStore (#1996). Covers the two pieces exercisable without a live
/// backend: the `ReloadDebouncer` coalescing (the #1973 beachball fix) and
/// DocumentStore's synchronous, network-free `document.deleted` granular apply.
/// The `updated`/`created` apply paths fetch a single document and are left to
/// the integration build.
@MainActor
final class ObservableDomainStoreTests: XCTestCase {

    // MARK: - ReloadDebouncer

    /// A burst of schedules must collapse into exactly one trailing action — the
    /// guarantee that keeps a workflow event storm from firing one reload per
    /// event and stalling the main thread (#1973).
    func testReloadDebouncerCoalescesBurstIntoSingleAction() async {
        let debouncer = ReloadDebouncer(delay: .milliseconds(30))
        let counter = Counter()

        for _ in 0..<5 {
            debouncer.schedule { await counter.increment() }
        }

        try? await Task.sleep(for: .milliseconds(150))
        let count = await counter.value
        XCTAssertEqual(count, 1, "5 rapid schedules should fire the action exactly once")
    }

    /// `cancel()` drops a pending action so it never runs (teardown / stop).
    func testReloadDebouncerCancelPreventsAction() async {
        let debouncer = ReloadDebouncer(delay: .milliseconds(30))
        let counter = Counter()

        debouncer.schedule { await counter.increment() }
        debouncer.cancel()

        try? await Task.sleep(for: .milliseconds(150))
        let count = await counter.value
        XCTAssertEqual(count, 0, "a cancelled schedule must not fire")
    }

    // MARK: - DocumentStore granular apply (document.deleted)

    /// `document.deleted` removes the affected rows in place from every list and
    /// the children cache, leaving the untouched rows behind — no wholesale
    /// reload, no network call.
    func testApplyDeletedRemovesRowsInPlaceAcrossListsAndCache() throws {
        let store = DocumentStore(apiClient: APIClient())
        let docA = makeDoc(id: "a", name: "Alpha")
        let docB = makeDoc(id: "b", name: "Beta")
        store.collections = [docA, docB]
        store.currentDocuments = [docA, docB]
        store.workspaces = [docA, docB]
        store.childrenCache["root"] = [docA, docB]

        store.apply(try makeEvent(type: "document.deleted", documentIds: ["a"]))

        XCTAssertEqual(store.collections.map(\.id), ["b"])
        XCTAssertEqual(store.currentDocuments.map(\.id), ["b"])
        XCTAssertEqual(store.workspaces.map(\.id), ["b"])
        XCTAssertEqual(store.childrenCache["root"]?.map(\.id), ["b"])
    }

    /// An event with no document ids is a no-op — nothing is touched.
    func testApplyWithNoDocumentIdsIsNoOp() throws {
        let store = DocumentStore(apiClient: APIClient())
        let docA = makeDoc(id: "a", name: "Alpha")
        store.collections = [docA]
        store.currentDocuments = [docA]

        store.apply(try makeEvent(type: "document.deleted", documentIds: []))

        XCTAssertEqual(store.collections.map(\.id), ["a"])
        XCTAssertEqual(store.currentDocuments.map(\.id), ["a"])
    }

    /// The store reports the `document` domain so the change-stream routes
    /// `document.*` events to it.
    func testChangeDomainIsDocument() {
        let store = DocumentStore(apiClient: APIClient())
        XCTAssertEqual(store.changeDomain, "document")
        XCTAssertEqual(store.changeDomains, ["document"])
    }

    // MARK: - DocumentStore granular apply (document.created) — #4065/#4067

    /// A ``document.created`` event records the affected ids in
    /// ``pendingPatchIds`` so the debounced flush fetches + splices each one
    /// in place — the progressive-population contract the folder ingest relies
    /// on (#4065). The engine now emits one created event per ingested file;
    /// each event lands here and patches the sidebar incrementally rather than
    /// waiting for the whole import to finish. The debounced network flush is
    /// cancelled so this stays a synchronous, network-free test.
    func testApplyCreatedRecordsPendingPatchIdsForProgressiveStreaming() throws {
        let store = DocumentStore(apiClient: APIClient())
        let docA = makeDoc(id: "a", name: "Alpha")
        let docB = makeDoc(id: "b", name: "Beta")
        store.collections = [docA]
        store.currentDocuments = [docA]

        // First file lands → only "b" is new to the stream.
        store.apply(try makeEvent(type: "document.created", documentIds: ["b"]))
        // Cancel the scheduled network flush so the test stays synchronous.
        store.reloadDebouncer.cancel()
        XCTAssertEqual(Set(store.pendingPatchIds), ["b"])

        // Second event (another file mid-import) accumulates alongside.
        store.apply(try makeEvent(type: "document.created", documentIds: ["c"]))
        store.reloadDebouncer.cancel()
        XCTAssertEqual(Set(store.pendingPatchIds), ["b", "c"])
    }

    /// The completion event (the action's trailing bulk ``document.created``
    /// carrying every created id) records the FULL set in ``pendingPatchIds``
    /// so the store refreshes promptly when the spinner stops (#4067) — even if
    /// every per-file streaming event had been lost in flight, the bulk event
    /// alone arms a single debounced flush that re-splices every row.
    func testApplyCreatedCompletionEventRecordsFullIdSet() throws {
        let store = DocumentStore(apiClient: APIClient())

        store.apply(try makeEvent(type: "document.created", documentIds: ["a", "b", "c", "d"]))
        store.reloadDebouncer.cancel()

        XCTAssertEqual(Set(store.pendingPatchIds), ["a", "b", "c", "d"])
    }

    // MARK: - Helpers

    /// Tiny actor so the `@Sendable` debouncer closure can count fires safely.
    private actor Counter {
        private(set) var value = 0
        func increment() { value += 1 }
    }

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
