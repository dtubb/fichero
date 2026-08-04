@testable import Fichero
import Foundation
import XCTest

/// Two temp-directory prefixes with opposite lifetimes must never converge
/// (#4311 / #4459).
///
/// ## The two directions
///
/// - `fichero-drop-UUID` stages the bytes of an INBOUND external drop. It is
///   scratch space: once the import has copied out of it, it is ours to delete,
///   and #4459 added that sweep so the directories stop accumulating.
/// - `fichero-drag-UUID` holds a document this app exported for an OUTBOUND
///   drag. Its consumer is **the Finder**, which may still be copying from it
///   after our code has moved on.
///
/// Nothing in the type system keeps these apart — one is a named constant,
/// the other a string literal repeated in three files. If a rename ever made
/// them share a prefix, the #4459 sweep would begin deleting export
/// directories while Finder read from them, and the user would get a truncated
/// or missing file from a drag to the desktop. That failure is silent, happens
/// only under a race, and would be blamed on the Finder.
///
/// These tests are pure — no drag session, no live app — so the invariant is
/// checkable without the one thing that cannot be automated here.
final class DropTempPrefixSeparationTests: XCTestCase {

    private let inboundStaging = "/fichero-drop-"
    private let outboundExport = "/" + ficheroInternalDragExportPrefix

    private func url(_ path: String) -> URL {
        URL(fileURLWithPath: path)
    }

    // MARK: - The prefixes are distinct

    /// The load-bearing assertion. Everything below depends on these two
    /// directory families being separable by name.
    func testInboundStagingAndOutboundExportPrefixesAreDisjoint() {
        XCTAssertNotEqual(
            inboundStaging, outboundExport,
            "the inbound staging prefix and the outbound export prefix must differ — "
                + "if they converge, the drop-cleanup sweep deletes files the Finder is reading"
        )
        XCTAssertFalse(
            inboundStaging.hasPrefix(outboundExport),
            "neither prefix may contain the other; the sweep matches by substring"
        )
        XCTAssertFalse(
            outboundExport.hasPrefix(inboundStaging),
            "neither prefix may contain the other; the sweep matches by substring"
        )
    }

    // MARK: - The sweep selects staging directories only

    func testTheSweepSelectsAnInboundStagingDirectory() {
        let staged = url("/tmp/fichero-drop-ABC/paper.pdf")

        XCTAssertEqual(
            externalDropTemporaryDirectories(for: [staged]).map(\.lastPathComponent),
            ["fichero-drop-ABC"],
            "an inbound drop's scratch directory is exactly what the sweep is for"
        )
    }

    /// The one that matters. A document the user is dragging to the desktop
    /// must never be selected for deletion.
    func testTheSweepNeverSelectsAnOutboundExportDirectory() {
        let exported = url("/tmp/fichero-drag-XYZ/Pompeyo Guzman.pdf")

        XCTAssertTrue(
            externalDropTemporaryDirectories(for: [exported]).isEmpty,
            "a fichero-drag- directory belongs to an in-flight Finder drag — deleting it "
                + "truncates the file the user just dropped on their desktop"
        )
    }

    /// Both kinds present at once: the sweep takes the staging directory and
    /// leaves the export alone, rather than taking all or nothing.
    func testAMixedListSweepsOnlyTheStagingDirectory() {
        let swept = externalDropTemporaryDirectories(for: [
            url("/tmp/fichero-drop-ABC/incoming.pdf"),
            url("/tmp/fichero-drag-XYZ/outgoing.pdf")
        ])

        XCTAssertEqual(swept.map(\.lastPathComponent), ["fichero-drop-ABC"])
    }

    /// An ordinary Finder file is neither, and must not be swept — deleting a
    /// user's own file after linking it would be the worst outcome here.
    func testAnOrdinaryUserFileIsNeverSwept() {
        XCTAssertTrue(
            externalDropTemporaryDirectories(for: [url("/Users/someone/Desktop/paper.pdf")]).isEmpty
        )
    }

    // MARK: - The refusal predicate reads the other prefix

    /// `isFicheroInternalDragExport` and the sweep must key off DIFFERENT
    /// prefixes. If both answered true for the same URL, an export would be
    /// simultaneously refused for import and deleted as scratch.
    func testTheInternalExportPredicateMatchesExportsAndNotStaging() {
        XCTAssertTrue(isFicheroInternalDragExport(url("/tmp/fichero-drag-XYZ/doc.pdf")))
        XCTAssertFalse(
            isFicheroInternalDragExport(url("/tmp/fichero-drop-ABC/doc.pdf")),
            "an inbound staged file is a genuine import, not one of our own exports"
        )
    }
}
