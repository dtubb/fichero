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

    /// Only when the USER has made an Inbox folder. Nothing creates one.
    func testBareFilesRouteToAUserMadeInbox() {
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
        // The ordinary case since 2026-08-31: no Inbox exists, and the root is
        // where the user dropped things anyway. Root files are visible in both
        // the sidebar and the library pane, so nothing is lost by landing here.
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

    // MARK: - No default Inbox (ruling 2026-08-31)

    /// Nothing creates an Inbox any more — not the engine at bootstrap, not
    /// `LibraryManager` on load, not this routing. The library ROOT is the drop
    /// zone. `inboxId` is now only ever the id of a folder the USER made, and
    /// `nil` is the ordinary case rather than the degraded one.

    func testANewLibraryHasNoInboxSoEveryLooseFileLandsAtRoot() {
        // The default path for every library that has not been given an Inbox
        // by hand: no redirect, no folder conjured to receive the drop.
        let batches = libraryRootImportBatches(
            urls: [fileURL, otherFileURL], inboxId: nil, isDirectory: isDir
        )
        XCTAssertEqual(
            batches,
            [LibraryRootImportBatch(parentId: nil, urls: [fileURL, otherFileURL])]
        )
    }

    /// Routing is a pure function of the id it is HANDED, so the same
    /// user-made Inbox is reused drop after drop — there is no code path that
    /// could mint a second one.
    func testASecondDropReusesTheSameUserMadeInbox() {
        let first = libraryRootImportBatches(
            urls: [fileURL], inboxId: "inbox-1", isDirectory: isDir
        )
        let second = libraryRootImportBatches(
            urls: [otherFileURL], inboxId: "inbox-1", isDirectory: isDir
        )
        XCTAssertEqual(first.first?.parentId, "inbox-1")
        XCTAssertEqual(second.first?.parentId, "inbox-1")
    }

    /// A user who DELETES their Inbox gets `nil` from the lookup on the next
    /// drop, and loose files simply land at the root. Nothing recreates it.
    func testDeletingTheInboxJustSendsLaterDropsToTheRoot() {
        let before = libraryRootImportBatches(
            urls: [fileURL], inboxId: "inbox-1", isDirectory: isDir
        )
        let after = libraryRootImportBatches(
            urls: [fileURL], inboxId: nil, isDirectory: isDir
        )
        XCTAssertEqual(before.first?.parentId, "inbox-1")
        XCTAssertEqual(after.first?.parentId, nil)
    }

    func testOrderWithinABatchIsPreserved() {
        let batches = libraryRootImportBatches(
            urls: [otherFileURL, fileURL], inboxId: "inbox-1", isDirectory: isDir
        )
        XCTAssertEqual(batches.first?.urls, [otherFileURL, fileURL])
    }
}
