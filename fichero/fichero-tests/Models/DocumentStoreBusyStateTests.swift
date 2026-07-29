@testable import Fichero
import Foundation
import XCTest

/// #4295 — a workflow on a single PDF page showed no spinner on that page's
/// row unless the row's parent happened to be the SELECTED collection.
///
/// The row derived "busy" from `currentDocuments` (selection-scoped) and
/// roots only. `DocumentStore.isDocumentBusy` / `folderHasBusyChild` are the
/// selection-independent derivation: a row is busy because a RUNNING
/// execution targets it — via the run's own target record
/// (`workflowStatusOverrides`, written per target id by
/// `updateProcessingStatus`) or a live `.processing` copy in ANY container,
/// including `childrenCache` where sidebar child rows actually live.
@MainActor
final class DocumentStoreBusyStateTests: XCTestCase {

    private func doc(
        _ id: String, parent: String? = nil,
        docType: DocType = .file, status: Status = .completed
    ) -> Document {
        Document(id: id, parentId: parent, docType: docType, name: id, status: status)
    }

    private func makeStore() -> DocumentStore {
        DocumentStore(apiClient: APIClient())
    }

    // MARK: - The regression: page busy without selection

    func testChildCacheProcessingIsBusyRegardlessOfSelection() {
        // The page lives ONLY in the sidebar's childrenCache — its parent is
        // not the selected collection, currentDocuments is empty.
        let store = makeStore()
        store.childrenCache["pdf-1"] = [
            doc("page-1", parent: "pdf-1", docType: .page, status: .processing)
        ]
        XCTAssertTrue(store.isDocumentBusy("page-1"))
    }

    func testExecutionTargetOverrideIsBusyWithNoContainerCopyAtAll() {
        // The run's target record alone marks the row busy — even before any
        // container holds a live copy (the fully selection-decoupled signal).
        let store = makeStore()
        store.workflowStatusOverrides["page-1"] = .processing
        XCTAssertTrue(store.isDocumentBusy("page-1"))
    }

    func testUpdateProcessingStatusDrivesBusyThroughTheChildCache() {
        // End-to-end through the real write path the workflow stream uses.
        let store = makeStore()
        store.childrenCache["pdf-1"] = [doc("page-1", parent: "pdf-1", docType: .page)]

        store.updateProcessingStatus(
            for: FileProgressIdentity(
                filePath: "/x/page-1.pdf", documentId: "page-1",
                pageId: nil, displayName: nil, sequence: nil
            ),
            status: .processing
        )
        XCTAssertTrue(store.isDocumentBusy("page-1"))

        store.updateProcessingStatus(
            for: FileProgressIdentity(
                filePath: "/x/page-1.pdf", documentId: "page-1",
                pageId: nil, displayName: nil, sequence: nil
            ),
            status: .pending
        )
        XCTAssertFalse(store.isDocumentBusy("page-1"), "pending clears the override")
    }

    func testIdleDocumentIsNotBusy() {
        let store = makeStore()
        store.childrenCache["pdf-1"] = [doc("page-1", parent: "pdf-1", docType: .page)]
        store.currentDocuments = [doc("other", status: .completed)]
        XCTAssertFalse(store.isDocumentBusy("page-1"))
        XCTAssertFalse(store.isDocumentBusy("missing-entirely"))
    }

    func testCompletedOverrideIsNotBusy() {
        // Overrides also remember completed/failed for badge persistence —
        // only .processing means busy.
        let store = makeStore()
        store.workflowStatusOverrides["d1"] = .completed
        XCTAssertFalse(store.isDocumentBusy("d1"))
    }

    // MARK: - Folder aggregation

    func testFolderBusyWhenCachedChildProcessing() {
        let store = makeStore()
        store.childrenCache["folder-1"] = [
            doc("f1-child", parent: "folder-1", status: .processing)
        ]
        XCTAssertTrue(store.folderHasBusyChild("folder-1"))
    }

    func testFolderBusyWhenChildIsAnExecutionTargetWithStaleCacheCopy() {
        // The cached copy still says completed but the run targets the child:
        // the override wins so the folder aggregates correctly.
        let store = makeStore()
        store.childrenCache["folder-1"] = [doc("f1-child", parent: "folder-1")]
        store.workflowStatusOverrides["f1-child"] = .processing
        XCTAssertTrue(store.folderHasBusyChild("folder-1"))
    }

    func testFolderNotBusyWhenChildrenIdle() {
        let store = makeStore()
        store.childrenCache["folder-1"] = [doc("f1-child", parent: "folder-1")]
        XCTAssertFalse(store.folderHasBusyChild("folder-1"))
        XCTAssertFalse(store.folderHasBusyChild("unknown-folder"))
    }

    func testFolderBusyFromSelectedGridChildren() {
        let store = makeStore()
        store.currentDocuments = [
            doc("g-child", parent: "folder-2", status: .processing)
        ]
        XCTAssertTrue(store.folderHasBusyChild("folder-2"))
    }
}
