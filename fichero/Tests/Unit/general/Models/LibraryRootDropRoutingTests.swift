@testable import Fichero
import Foundation
import XCTest

/// #4274 — dragging a folder onto a library's top level didn't import.
///
/// Every root-level drop path (library header row, root content pane, root
/// leaf rows) blanket-routed the import into Inbox. Correct for bare files
/// (invisible at root in the sidebar), wrong for FOLDERS — a folder is a
/// first-class sidebar row at root, so the redirect buried it in Inbox where
/// the user wasn't looking, which reads as "the drop didn't import".
/// `libraryRootImportBatches` is the one shared routing rule all three call
/// sites now use.
final class LibraryRootDropRoutingTests: XCTestCase {

    private let folderURL = URL(fileURLWithPath: "/drop/Archive", isDirectory: true)
    private let fileURL = URL(fileURLWithPath: "/drop/scan.pdf")
    private let otherFileURL = URL(fileURLWithPath: "/drop/notes.txt")

    private func isDir(_ url: URL) -> Bool { url == folderURL }

    func testFolderDropImportsAtRootNotInbox() {
        // The regression: a folder dropped on the library root must land AT
        // the root, never be silently rerouted into Inbox.
        let batches = libraryRootImportBatches(
            urls: [folderURL], inboxId: "inbox-1", isDirectory: isDir
        )
        XCTAssertEqual(batches, [LibraryRootImportBatch(parentId: nil, urls: [folderURL])])
    }

    func testBareFilesStillRouteToInbox() {
        let batches = libraryRootImportBatches(
            urls: [fileURL, otherFileURL], inboxId: "inbox-1", isDirectory: isDir
        )
        XCTAssertEqual(
            batches,
            [LibraryRootImportBatch(parentId: "inbox-1", urls: [fileURL, otherFileURL])]
        )
    }

    func testMixedDropSplitsIntoRootAndInboxBatches() {
        let batches = libraryRootImportBatches(
            urls: [fileURL, folderURL, otherFileURL], inboxId: "inbox-1", isDirectory: isDir
        )
        XCTAssertEqual(batches, [
            LibraryRootImportBatch(parentId: nil, urls: [folderURL]),
            LibraryRootImportBatch(parentId: "inbox-1", urls: [fileURL, otherFileURL])
        ])
    }

    func testNoInboxMeansEverythingLandsAtRoot() {
        // With no Inbox there is nowhere to redirect to — import everything at
        // root rather than dropping the batch on the floor.
        let batches = libraryRootImportBatches(
            urls: [fileURL, folderURL], inboxId: nil, isDirectory: isDir
        )
        XCTAssertEqual(
            batches,
            [LibraryRootImportBatch(parentId: nil, urls: [fileURL, folderURL])]
        )
    }

    func testEmptyDropProducesNoBatches() {
        XCTAssertTrue(
            libraryRootImportBatches(urls: [], inboxId: "inbox-1", isDirectory: isDir).isEmpty
        )
        XCTAssertTrue(
            libraryRootImportBatches(urls: [], inboxId: nil, isDirectory: isDir).isEmpty
        )
    }

    func testOrderWithinABatchIsPreserved() {
        let batches = libraryRootImportBatches(
            urls: [otherFileURL, fileURL], inboxId: "inbox-1", isDirectory: isDir
        )
        XCTAssertEqual(batches.first?.urls, [otherFileURL, fileURL])
    }
}
