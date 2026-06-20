@testable import Fichero
import Foundation
import XCTest

/// Tests for the STORE-OWNED page-content save (#2466).
///
/// The Content-tab editor lives in a SwiftUI view whose debounce / on-blur
/// saves run inside view-owned `Task`s. SwiftUI cancels those tasks on a
/// re-render, focus loss, or selection change — and the old code ran the
/// `updateDocument` PUT *inside* them, so the in-flight request was cancelled
/// mid-flight (NSURLError -999). `DocumentStore.savePageContent` now owns the
/// task, so a view-scope cancellation can no longer abort the save.
@MainActor
final class DocumentStorePageContentSaveTests: XCTestCase {

    /// THE regression test for #2466: cancelling the *caller's* task — exactly
    /// what SwiftUI does to the editor's debounce/blur task on a re-render —
    /// must NOT abort the store-owned save. The PUT runs to completion and the
    /// optimistic local state is updated.
    func testStoreSaveCompletesDespiteCallerCancellation() async throws {
        let store = DocumentStore(apiClient: APIClient())
        let docId = "doc-1"
        store.selectedDocument = Document(id: docId, name: "doc", pageContent: "OLD")
        store.currentDocuments = [store.selectedDocument!]

        let saveStarted = expectation(description: "save closure entered")
        let saveFinished = Box(false)
        let gate = ReleaseGate()

        // Stand in for the editor's view-owned task: it calls the store save and
        // then gets cancelled while the PUT is still "in flight".
        let caller = Task { @MainActor () -> String? in
            await store.savePageContent(documentId: docId) {
                saveStarted.fulfill()
                await gate.wait()              // simulate a slow network PUT
                saveFinished.set(true)
                return Document(id: docId, name: "doc", pageContent: "NEW")
            }
        }

        await fulfillment(of: [saveStarted], timeout: 2)
        caller.cancel()                        // <-- the -999 trigger, pre-fix
        gate.open()                            // let the (store-owned) PUT finish
        let result = await caller.value

        XCTAssertTrue(saveFinished.value, "store save must run to completion despite caller cancellation")
        XCTAssertNil(result, "a completed save reports no error")
        XCTAssertEqual(store.selectedDocument?.pageContent, "NEW",
                       "refreshLocalContent must apply the saved content to local caches")
    }

    /// Happy path with no cancellation: returns nil and applies the content.
    func testStoreSaveAppliesContentOnSuccess() async throws {
        let store = DocumentStore(apiClient: APIClient())
        let docId = "doc-2"
        store.selectedDocument = Document(id: docId, name: "doc", pageContent: "OLD")

        let result = await store.savePageContent(documentId: docId) {
            Document(id: docId, name: "doc", pageContent: "edited")
        }

        XCTAssertNil(result)
        XCTAssertEqual(store.selectedDocument?.pageContent, "edited")
    }

    /// A genuine save failure must still surface (we only kill the spurious
    /// -999 cancellation, never real error handling).
    func testStoreSaveSurfacesRealFailure() async throws {
        let store = DocumentStore(apiClient: APIClient())
        let docId = "doc-3"
        store.selectedDocument = Document(id: docId, name: "doc", pageContent: "OLD")

        let result = await store.savePageContent(documentId: docId) {
            throw NSError(domain: "Test", code: 1, userInfo: [NSLocalizedDescriptionKey: "boom"])
        }

        XCTAssertEqual(result, "boom", "real failures are surfaced as a user-facing string")
        XCTAssertEqual(store.selectedDocument?.pageContent, "OLD",
                       "a failed save must not mutate local state")
    }

    /// Saves of the same document are serialized so the last edit wins, even
    /// when the first save is still in flight when the second arrives.
    func testStoreSavesSerializeLastWriteWins() async throws {
        let store = DocumentStore(apiClient: APIClient())
        let docId = "doc-4"
        store.selectedDocument = Document(id: docId, name: "doc", pageContent: "OLD")

        let firstStarted = expectation(description: "first save entered")
        let firstGate = ReleaseGate()

        let first = Task { @MainActor in
            await store.savePageContent(documentId: docId) {
                firstStarted.fulfill()
                await firstGate.wait()
                return Document(id: docId, name: "doc", pageContent: "first")
            }
        }
        await fulfillment(of: [firstStarted], timeout: 2)

        // Second save queued while the first is still in flight.
        let second = Task { @MainActor in
            await store.savePageContent(documentId: docId) {
                Document(id: docId, name: "doc", pageContent: "second")
            }
        }

        firstGate.open()
        _ = await first.value
        _ = await second.value

        XCTAssertEqual(store.selectedDocument?.pageContent, "second",
                       "the most-recent edit must be the value that lands last")
    }
}

// MARK: - Test helpers

/// Suspends `wait()` until `open()` is called. Lets a test hold a save closure
/// "in flight" while it cancels the caller, then release it.
private final class ReleaseGate: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<Void, Never>?
    private var released = false

    func wait() async {
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            lock.lock()
            if released {
                lock.unlock()
                cont.resume()
            } else {
                continuation = cont
                lock.unlock()
            }
        }
    }

    func open() {
        lock.lock()
        released = true
        let cont = continuation
        continuation = nil
        lock.unlock()
        cont?.resume()
    }
}

/// Minimal thread-safe box for observing a flag set inside a `@Sendable` closure.
private final class Box<T>: @unchecked Sendable {
    private let lock = NSLock()
    private var _value: T
    init(_ value: T) { _value = value }
    var value: T { lock.lock(); defer { lock.unlock() }; return _value }
    func set(_ value: T) { lock.lock(); _value = value; lock.unlock() }
}
