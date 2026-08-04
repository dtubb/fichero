@testable import Fichero
import Foundation
import XCTest

/// #4346 — after a run stopped (or its SSE stream died without a terminal
/// frame, #4349), documents that had received `fileStart` but never a
/// `fileComplete`/`fileError` kept their `.processing` override forever:
/// `flushPendingFanoutCompletions` only settles fanout slots that COMPLETED,
/// so mid-flight documents span the gap and spun until app restart.
///
/// `clearResidualProcessing` is the terminal boundary's backstop: every
/// identity still marked `.processing` reverts (default `.pending` — a
/// stopped run is not a failure, #4321) and the busy derivation goes quiet.
@MainActor
final class DocumentStoreResidualProcessingTests: XCTestCase {

    private func makeStore() -> DocumentStore {
        DocumentStore(apiClient: APIClient())
    }

    private func identity(_ id: String) -> FileProgressIdentity {
        FileProgressIdentity(
            filePath: "/lib/files/\(id).pdf", documentId: id,
            pageId: nil, displayName: nil, sequence: nil
        )
    }

    func testMidFlightDocumentStopsSpinningAfterClear() {
        let store = makeStore()
        store.updateProcessingStatus(for: identity("page-1"), status: .processing)
        XCTAssertTrue(store.isDocumentBusy("page-1"))

        // Run stops; no fileComplete/fileError ever arrives for page-1.
        store.flushPendingFanoutCompletions(status: .failed)   // settles nothing here
        XCTAssertTrue(store.isDocumentBusy("page-1"), "flush alone must not settle mid-flight docs")

        store.clearResidualProcessing()
        XCTAssertFalse(store.isDocumentBusy("page-1"))
        XCTAssertNil(store.workflowStatusOverrides["page-1"], "a stopped run leaves no failure badge")
    }

    func testCompletedFanoutSlotIsNotResidual() {
        let store = makeStore()
        store.updateProcessingStatus(for: identity("page-1"), status: .processing)
        store.recordFanoutComplete(for: identity("page-1"))
        store.flushPendingFanoutCompletions(status: .completed)

        XCTAssertEqual(store.workflowStatusOverrides["page-1"], .completed)
        store.clearResidualProcessing()
        // The green check must survive — only `.processing` residuals clear.
        XCTAssertEqual(store.workflowStatusOverrides["page-1"], .completed)
    }

    func testFailedDocumentKeepsItsFailureBadge() {
        let store = makeStore()
        store.updateProcessingStatus(for: identity("page-1"), status: .processing)
        store.updateProcessingStatus(for: identity("page-1"), status: .failed)

        store.clearResidualProcessing()
        XCTAssertEqual(store.workflowStatusOverrides["page-1"], .failed)
    }

    func testClearSettlesEveryLiveContainerCopy() {
        let store = makeStore()
        store.childrenCache["pdf-1"] = [
            Document(id: "page-1", parentId: "pdf-1", docType: .page, name: "page-1", status: .pending)
        ]
        store.updateProcessingStatus(for: identity("page-1"), status: .processing)
        XCTAssertEqual(store.childrenCache["pdf-1"]?.first?.status, .processing)

        store.clearResidualProcessing()
        XCTAssertEqual(store.childrenCache["pdf-1"]?.first?.status, .pending)
        XCTAssertFalse(store.folderHasBusyChild("pdf-1"))
    }

    func testClearIsIdempotentAndScopedToTrackedIdentities() {
        let store = makeStore()
        // A status override written by some other mechanism, never marked
        // processing through the stream path, is not touched.
        store.workflowStatusOverrides["other-doc"] = .processing
        store.updateProcessingStatus(for: identity("page-1"), status: .processing)

        store.clearResidualProcessing()
        store.clearResidualProcessing()

        XCTAssertNil(store.workflowStatusOverrides["page-1"])
        XCTAssertEqual(store.workflowStatusOverrides["other-doc"], .processing)
    }
}
