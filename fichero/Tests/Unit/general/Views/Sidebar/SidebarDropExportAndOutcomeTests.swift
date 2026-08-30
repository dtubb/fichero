import Foundation
import XCTest

@testable import Fichero

/// The two purely-presentational halves of the drop story, split out of
/// `SidebarDropGrammarBoundaryTests` to keep each file inside the lint budget:
/// recognising OUR OWN drag export by its URL alone (the one route that cannot
/// ask the providers), and the sentence the user is shown when a folder-cell
/// drop fails.
@MainActor
final class SidebarDropExportAndOutcomeTests: XCTestCase {

    // MARK: - Our own export, recognised by URL alone

    /// The widest-scope drop target cannot see providers, so it recognises our
    /// export by the temp-directory prefix. Any path COMPONENT counts, at any
    /// depth — the exported file sits inside a per-drag directory.
    func testOurOwnExportIsRecognisedAtAnyDepth() {
        XCTAssertTrue(isFicheroInternalDragExport(
            URL(fileURLWithPath: "/var/folders/zz/fichero-drag-ABC/Scan.pdf")
        ))
        XCTAssertTrue(isFicheroInternalDragExport(
            URL(fileURLWithPath: "/tmp/fichero-drag-1/nested/deeper/Scan.pdf")
        ))
    }

    /// The INBOUND staging prefix is deliberately a different string. Treating
    /// `fichero-drop-` as our own export would refuse every external drop that
    /// had been staged, which is all of them.
    func testTheInboundStagingPrefixIsNotOurExport() {
        XCTAssertFalse(isFicheroInternalDragExport(
            URL(fileURLWithPath: "/tmp/fichero-drop-7/Scan.pdf")
        ))
    }

    /// Ordinary external files partition out untouched, and the split keeps
    /// each side's order — the import call downstream receives exactly the
    /// external URLs, in the order the user dropped them.
    func testThePartitionKeepsEveryExternalURLInOrder() {
        let urls = [
            URL(fileURLWithPath: "/Users/d/A.pdf"),
            URL(fileURLWithPath: "/tmp/fichero-drag-1/Mine.pdf"),
            URL(fileURLWithPath: "/Users/d/B.pdf"),
            URL(fileURLWithPath: "/tmp/fichero-drag-2/Also.pdf"),
            URL(fileURLWithPath: "/Users/d/C.pdf")
        ]
        let split = partitionFicheroInternalDragExports(urls)
        XCTAssertEqual(split.external.map(\.lastPathComponent), ["A.pdf", "B.pdf", "C.pdf"])
        XCTAssertEqual(split.internalExports.map(\.lastPathComponent), ["Mine.pdf", "Also.pdf"])
    }

    func testAnEmptyPartitionIsEmptyOnBothSides() {
        let split = partitionFicheroInternalDragExports([])
        XCTAssertTrue(split.external.isEmpty)
        XCTAssertTrue(split.internalExports.isEmpty)
    }

    /// CHARACTERISATION, not endorsement: the predicate matches any path
    /// component STARTING with the prefix, so a user folder literally named
    /// `fichero-drag-scans` makes every file inside it look like our own
    /// export — and those files are silently dropped from the import rather
    /// than refused with a message. Narrow but real; pinned so a future
    /// tightening (match the temp directory too, not just the name) has a test
    /// that changes.
    func testAUserFolderNamedLikeOurExportIsCurrentlySwallowed() {
        let userFile = URL(fileURLWithPath: "/Users/d/fichero-drag-scans/Diary.pdf")
        XCTAssertTrue(
            isFicheroInternalDragExport(userFile),
            "name-only matching: this is a real user file being treated as our export"
        )
    }

    // MARK: - What the user is told when a cell drop fails

    /// Nil means "everything applied" — the message must not appear at all on
    /// a wholly successful drop.
    func testNoFailuresSaysNothing() {
        XCTAssertNil(libraryCellDropOutcomeMessage(attempted: 3, failures: []))
        XCTAssertNil(libraryCellDropOutcomeMessage(attempted: 0, failures: []))
    }

    /// One item, all failed: singular throughout, and the reason is carried.
    func testASingleTotalFailureReadsSingular() {
        let message = libraryCellDropOutcomeMessage(attempted: 1, failures: ["Folder is read-only."])
        XCTAssertEqual(message, "Couldn’t drop that item. Folder is read-only.")
    }

    /// Several items, all failed: plural, with the count.
    func testATotalFailureOfSeveralItemsCountsThem() {
        let message = libraryCellDropOutcomeMessage(
            attempted: 3, failures: ["a", "b", "c"]
        )
        XCTAssertEqual(message, "Couldn’t drop those 3 items. a")
    }

    /// A PARTIAL failure must say so — reporting a partial failure as a total
    /// one would tell the user nothing moved when some of it did.
    func testAPartialFailureNamesBothCounts() {
        let message = libraryCellDropOutcomeMessage(attempted: 4, failures: ["x"])
        XCTAssertEqual(message, "1 of 4 items couldn’t be dropped. x")
    }

    /// The singular noun is chosen from the ATTEMPTED count, not the failure
    /// count — one failure out of two is still "2 items".
    func testTheNounFollowsTheAttemptedCount() {
        XCTAssertEqual(
            libraryCellDropOutcomeMessage(attempted: 2, failures: ["x"]),
            "1 of 2 items couldn’t be dropped. x"
        )
    }

    /// Only the FIRST reason is shown; the rest are in the log. Pinned so a
    /// future change to concatenate them is a deliberate one.
    func testOnlyTheFirstReasonIsShown() {
        let message = libraryCellDropOutcomeMessage(
            attempted: 2, failures: ["first reason", "second reason"]
        )
        XCTAssertEqual(message, "Couldn’t drop those 2 items. first reason")
        XCTAssertFalse(message?.contains("second reason") ?? true)
    }

    /// A failure with an EMPTY reason string still produces a message — a
    /// trailing space is ugly, but a nil here would mean a failed drop said
    /// nothing at all, which is the defect the whole function exists to close.
    func testAnEmptyReasonStillProducesAMessage() {
        let message = libraryCellDropOutcomeMessage(attempted: 1, failures: [""])
        XCTAssertNotNil(message)
        XCTAssertTrue(message?.hasPrefix("Couldn’t drop that item.") ?? false)
    }
}
