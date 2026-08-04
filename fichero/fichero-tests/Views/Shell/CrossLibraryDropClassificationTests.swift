@testable import Fichero
import Foundation
import XCTest

/// What a drop can and cannot know about the library a drag came from
/// (#4311), and the #4401 routing it must not regress.
///
/// ## Why this file exists
///
/// #4311 asks for cross-library copy. The blocker is that
/// `classifySidebarDropPayload` has no library in its signature and every
/// discriminator below it is library-blind. Making it library-aware is only
/// possible for drags whose wire payload actually carries a library — and the
/// two in-app drag shapes differ on exactly that point. These tests pin that
/// asymmetry as an executable fact rather than a claim in a commit message,
/// and they pin the #4401 routing that must survive any fix.
final class CrossLibraryDropClassificationTests: XCTestCase {

    private let sourceLibrary = UUID(uuidString: "11111111-2222-3333-4444-555555555555")!

    /// A library-pane drag as it actually crosses the wire: `LibraryItemDrag`'s
    /// first representation is `CodableRepresentation(contentType: .json)`.
    private func libraryPaneDragJSON(documentId: String, libraryId: UUID?) -> String {
        var fields = [
            "\"kind\": \"document\"",
            "\"id\": \"\(documentId)\"",
            "\"documentId\": \"\(documentId)\"",
            "\"text\": \"some transcript\"",
            "\"name\": \"Paper.pdf\""
        ]
        if let libraryId {
            fields.append("\"libraryId\": \"\(libraryId.uuidString)\"")
        }
        return "{" + fields.joined(separator: ", ") + "}"
    }

    // MARK: - #4401 must not regress

    /// A sidebar row drag. `hasExternalPayload` is TRUE on purpose: since #4123 an
    /// internal drag also advertises a real file, and the whole #4401 fix is
    /// that positive id identification WINS over that. If this ever returns
    /// `.externalFiles`, the hollow-duplicate bug is back.
    func testASidebarRowDragIsStillAMoveEvenThoughItAlsoOffersAFile() {
        let payload = classifySidebarDropPayload(
            loadedIDs: ["doc:abc-123"],
            hasExternalPayload: true,
            carriesOwnProcessFlavor: true
        )

        XCTAssertEqual(payload, .internalItems(["doc:abc-123"]))
    }

    /// The library pane's own shape, which #4401's follow-up taught the
    /// classifier to recognise. Also a move, not an import.
    func testALibraryPaneDragIsStillAMove() {
        let json = libraryPaneDragJSON(documentId: "abc-123", libraryId: sourceLibrary)

        let payload = classifySidebarDropPayload(
            loadedIDs: [json],
            hasExternalPayload: true,
            carriesOwnProcessFlavor: true
        )

        XCTAssertEqual(
            payload, .internalItems(["doc:abc-123"]),
            "a library-pane row dragged to a sidebar folder is the ordinary way to file a document"
        )
    }

    /// The control: a genuine Finder drop is still an import. Without this,
    /// a classifier that answered `.internalItems` for everything would pass
    /// both tests above.
    func testAGenuineExternalDropIsStillAnImport() {
        let payload = classifySidebarDropPayload(
            loadedIDs: [],
            hasExternalPayload: true,
            carriesOwnProcessFlavor: false
        )

        XCTAssertEqual(payload, .externalFiles)
    }

    /// An in-app drag whose id could not be read must never fall through to
    /// ingestion — re-importing something already stored is the data-loss
    /// shape #4401 is about.
    func testAnUnreadableInAppDragIsNeverAnImport() {
        let payload = classifySidebarDropPayload(
            loadedIDs: ["a transcript, not an id"],
            hasExternalPayload: true,
            carriesOwnProcessFlavor: true
        )

        XCTAssertEqual(payload, .unreadableInternal)
    }

    // MARK: - The asymmetry that blocks #4311

    /// The library pane's payload DOES carry its source library, so a
    /// library-aware classifier is possible for this shape without touching
    /// the drag source.
    func testTheLibraryPaneDragCarriesItsSourceLibraryOnTheWire() throws {
        let json = libraryPaneDragJSON(documentId: "abc-123", libraryId: sourceLibrary)
        let decoded = try JSONDecoder().decode(
            LibraryItemDrag.self, from: Data(json.utf8)
        )

        XCTAssertEqual(
            decoded.libraryId, sourceLibrary,
            "the source library is on the wire — this is what makes a cross-library "
                + "decision possible for library-pane drags"
        )
    }

    /// And the sidebar's payload does NOT.
    ///
    /// `SidebarDragID.transferRepresentation` leads with
    /// `ProxyRepresentation(exporting: \.id)`, so what arrives is the bare
    /// string `doc:<uuid>`. The struct HAS a `libraryId`; it never crosses the
    /// wire. There is nothing to parse a library out of, which is why #4311
    /// cannot be finished on the receiving side alone for this shape.
    func testTheSidebarRowDragCarriesNoLibraryOnTheWire() {
        let wireForm = "doc:abc-123"

        XCTAssertTrue(isInternalSidebarItemID(wireForm), "it is a valid internal id")
        XCTAssertNil(
            internalSidebarItemID(fromLibraryDragJSON: wireForm),
            "and it is not structured — there is no field to read a source library from"
        )
    }

    /// A library-pane drag with no library set is the honest ambiguous case: a
    /// classifier must not treat "no library stated" as "a different library".
    func testALibraryPaneDragWithNoLibraryIsNotEvidenceOfADifferentLibrary() throws {
        let json = libraryPaneDragJSON(documentId: "abc-123", libraryId: nil)
        let decoded = try JSONDecoder().decode(
            LibraryItemDrag.self, from: Data(json.utf8)
        )

        XCTAssertNil(decoded.libraryId)
        XCTAssertEqual(
            classifySidebarDropPayload(
                loadedIDs: [json], hasExternalPayload: true, carriesOwnProcessFlavor: true
            ),
            .internalItems(["doc:abc-123"]),
            "absent is not foreign — an unstated library must keep the existing move route"
        )
    }
}
