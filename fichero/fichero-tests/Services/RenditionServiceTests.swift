@testable import Fichero
import XCTest

/// The client-side rendition model (2026-08-20 bbox review).
///
/// These cover the pure parts — label derivation and the flip-sequence rules —
/// without a live engine. The ORDER itself is deliberately not re-tested here:
/// it is decided server-side so every surface agrees what "next" means, and a
/// client-side expectation would just be a second opinion waiting to diverge.
@MainActor
final class RenditionServiceTests: XCTestCase {

    private func rendition(
        _ role: String,
        primary: Bool = false,
        materialized: Bool = true,
        ownFrame: Bool = false
    ) -> DocumentRendition {
        DocumentRendition(
            id: "r-\(role)",
            documentId: "doc-1",
            role: role,
            path: "/\(role).jpg",
            isPrimary: primary,
            pixelWidth: nil,
            pixelHeight: nil,
            isMaterialized: materialized,
            hasOwnFrame: ownFrame,
            note: nil
        )
    }

    // MARK: - Display name

    func testUnderscoredRoleBecomesWords() {
        XCTAssertEqual(rendition("background_removed").displayName, "Background Removed")
    }

    func testSingleWordRoleIsCapitalised() {
        XCTAssertEqual(rendition("enhanced").displayName, "Enhanced")
    }

    /// Roles are free-form so the staging pipeline can invent them without a
    /// client release. An unknown one must still render as words, not fall
    /// through to a raw identifier in the chrome.
    func testUnknownRoleStillRendersAsWords() {
        XCTAssertEqual(rendition("hocr_overlay").displayName, "Hocr Overlay")
    }

    func testEmptyRoleDoesNotCrash() {
        XCTAssertEqual(rendition("").displayName, "")
    }

    // MARK: - The cropped-frame flag

    /// A rendition in its own frame is NOT interchangeable with the others:
    /// the image shape changes and page-frame boxes do not apply unchanged.
    /// The flag is what lets the chrome say so instead of leaving the user to
    /// infer it from a jump.
    func testOwnFrameIsCarriedSeparatelyFromRole() {
        XCTAssertTrue(rendition("enhanced", ownFrame: true).hasOwnFrame)
        XCTAssertFalse(rendition("enhanced").hasOwnFrame)
    }

    // MARK: - Equatable identity

    func testRenditionsAreDistinguishedById() {
        XCTAssertNotEqual(rendition("enhanced"), rendition("original"))
        XCTAssertEqual(rendition("enhanced"), rendition("enhanced"))
    }
}

/// The toolbar's rendition indicator.
///
/// The behaviour worth pinning: it is HIDDEN, not greyed, when there is
/// nothing to say — and it draws no chevrons while flipping is impossible,
/// because a visible control that does nothing is worse than an absent one.
@MainActor
final class ReaderRenditionNavTests: XCTestCase {

    func testIndicatorShowsNameAndPosition() {
        let nav = ReaderRenditionNav(
            name: "Enhanced",
            index: 0,
            count: 3,
            hasOwnFrame: false,
            goPrevious: nil,
            goNext: nil
        )
        XCTAssertEqual(nav.name, "Enhanced")
        XCTAssertEqual(nav.count, 3)
    }

    /// Until a rendition-bytes endpoint exists there is nothing to flip TO,
    /// so both actions are nil and the toolbar renders an indicator only.
    func testNoActionsMeansNoChevrons() {
        let nav = ReaderRenditionNav(
            name: "Original",
            index: 1,
            count: 2,
            hasOwnFrame: false,
            goPrevious: nil,
            goNext: nil
        )
        XCTAssertNil(nav.goPrevious)
        XCTAssertNil(nav.goNext)
    }

    func testActionsAreInvokedWhenPresent() {
        var stepped = 0
        let nav = ReaderRenditionNav(
            name: "Enhanced",
            index: 0,
            count: 2,
            hasOwnFrame: true,
            goPrevious: nil,
            goNext: { stepped += 1 }
        )
        nav.goNext?()
        XCTAssertEqual(stepped, 1)
        XCTAssertTrue(nav.hasOwnFrame)
    }
}
