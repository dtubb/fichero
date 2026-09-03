#if os(macOS)
@testable import Fichero
import FicheroAPIClient
import XCTest

/// Annotations and region boxes describe the same thing — a normalized rect
/// on a page — but until 2026-09-03 only region boxes knew WHICH pixels they
/// were measured on. The engine has carried `SourceAnchor.rendition_id` since
/// the anchor type replaced the bare bbox; this client never set it, so every
/// annotation ever written claimed the node's own frame, and the overlay drew
/// marks over any rendition without asking.
///
/// These tests pin the three halves of the convergence: the frame goes out on
/// write, comes back on read, and gates drawing through the SAME matrix the
/// region overlay uses.
final class AnnotationFrameIdentityTests: XCTestCase {

    // MARK: - Write: the anchor names the frame

    func testWireAnchorCarriesTheRenditionItWasDrawnOn() {
        let anchor = AnnotationService.wireAnchor(
            bbox: [0.1, 0.2, 0.3, 0.4],
            documentId: "doc-1", pageId: nil, folderId: nil,
            renditionId: "rend-deskewed"
        )
        XCTAssertEqual(anchor?.renditionId, "rend-deskewed")
        XCTAssertEqual(anchor?.rect, [0.1, 0.2, 0.3, 0.4])
        XCTAssertEqual(anchor?.space, .normalized)
    }

    /// The base image is a real answer, not a missing one: nil means "the
    /// node's own frame", which the gate reads as "any rendition that keeps
    /// that frame".
    func testWireAnchorLeavesTheFrameNilForTheNodesOwnImage() {
        let anchor = AnnotationService.wireAnchor(
            bbox: [0, 0, 1, 1], documentId: "doc-1", pageId: nil, folderId: nil
        )
        XCTAssertNil(anchor?.renditionId)
    }

    func testWireAnchorStaysNilWithoutARect() {
        XCTAssertNil(AnnotationService.wireAnchor(
            bbox: nil, documentId: "doc-1", pageId: nil, folderId: nil,
            renditionId: "rend-1"
        ))
    }

    // MARK: - Read: the frame survives the round trip into the mark layer

    func testAnnotationExposesTheAnchorsRendition() {
        let annotation = DocumentAnnotation(
            id: "a1", documentId: "doc-1",
            anchor: AnnotationAnchor(
                rect: [0.1, 0.1, 0.2, 0.2], space: "normalized", renditionId: "rend-crop"
            ),
            kind: .highlight
        )
        XCTAssertEqual(annotation.renditionId, "rend-crop")
        XCTAssertTrue(annotation.hasRegion)
    }

    func testMarkCarriesTheAnnotationsFrame() {
        let annotation = DocumentAnnotation(
            id: "a1", documentId: "doc-1",
            anchor: AnnotationAnchor(
                rect: [0.1, 0.1, 0.2, 0.2], space: "normalized", renditionId: "rend-crop"
            ),
            kind: .highlight
        )
        XCTAssertEqual(AnnotationMark(annotation: annotation).renditionId, "rend-crop")
    }

    /// A legacy row has no anchor at all; it must read as "unknown frame",
    /// which the gate treats as the node's own — the only honest reading of a
    /// rect written before frames existed.
    func testLegacyBboxRowHasNoFrame() {
        let annotation = DocumentAnnotation(
            id: "a1", documentId: "doc-1", bbox: [0.1, 0.1, 0.2, 0.2], kind: .highlight
        )
        XCTAssertNil(annotation.renditionId)
        XCTAssertTrue(annotation.hasRegion)
    }

    // MARK: - Gate: one matrix for both layers

    /// The same expectations `geometryFrameMatchesDisplay` is held to. If
    /// these ever diverge, a highlight and the region box under it can
    /// disagree about whether the page on screen is theirs.
    func testAnnotationFrameGateMatchesTheRegionMatrix() {
        // Node's own frame: draws on the base image and on a same-frame
        // rendition (background removal, enhancement) …
        XCTAssertTrue(overlayFrameMatches(
            required: nil, displayed: nil, displayedHasOwnFrame: false
        ))
        XCTAssertTrue(overlayFrameMatches(
            required: nil, displayed: "rend-enhanced", displayedHasOwnFrame: false
        ))
        // … and never on a rendition that reframed the pixels.
        XCTAssertFalse(overlayFrameMatches(
            required: nil, displayed: "rend-crop", displayedHasOwnFrame: true
        ))
        // Drawn on a specific rendition: only that rendition's pixels.
        XCTAssertTrue(overlayFrameMatches(
            required: "rend-crop", displayed: "rend-crop", displayedHasOwnFrame: true
        ))
        XCTAssertFalse(overlayFrameMatches(
            required: "rend-crop", displayed: nil, displayedHasOwnFrame: false
        ))
        XCTAssertFalse(overlayFrameMatches(
            required: "rend-crop", displayed: "rend-deskew", displayedHasOwnFrame: true
        ))
    }
}
#endif

#if os(macOS)
import SwiftUI

/// The inspector's annotation rows had no wire to the page. Region rows have
/// lit their box since 2026-08-29 (`RegionSelection` → the region overlay);
/// clicking an annotation row said nothing about WHERE on the page it was
/// (Daniel, 2026-09-03). `AnnotationMarkLayer` now takes the focused id and
/// draws the same accent ring — this pins where it lands.
final class AnnotationSelectionHighlightTests: XCTestCase {

    private let unitVisible = CGRect(x: 0, y: 0, width: 1, height: 1)
    private let size = CGSize(width: 200, height: 100)

    private func layer(_ marks: [AnnotationMark]) -> AnnotationMarkLayer {
        AnnotationMarkLayer(marks: marks, visible: unitVisible, selectedId: nil)
    }

    func testSelectedMarkResolvesToItsBoxOnThePage() {
        let mark = AnnotationMark(id: "a1", kind: .highlight, rect: [0.25, 0.5, 0.5, 0.25])
        let rect = layer([mark]).selectionRect(for: "a1", in: size)
        XCTAssertEqual(rect, CGRect(x: 50, y: 50, width: 100, height: 25))
    }

    /// A row for another page, or one the frame gate dropped, must light
    /// nothing rather than light something plausible in the wrong place.
    func testSelectionOfAMarkThisPageIsNotShowingResolvesToNothing() {
        let mark = AnnotationMark(id: "a1", kind: .highlight, rect: [0.25, 0.5, 0.5, 0.25])
        XCTAssertNil(layer([mark]).selectionRect(for: "a2", in: size))
    }

    /// A whole-page bookmark has no box; there is nothing to ring.
    func testSelectionOfARegionlessMarkResolvesToNothing() {
        let mark = AnnotationMark(id: "a1", kind: .bookmark, rect: nil)
        XCTAssertNil(layer([mark]).selectionRect(for: "a1", in: size))
    }

    /// The ring rides the zoom window exactly as the mark under it does.
    func testSelectionRectFollowsTheVisibleWindow() {
        let mark = AnnotationMark(id: "a1", kind: .highlight, rect: [0.5, 0.5, 0.25, 0.25])
        let zoomed = AnnotationMarkLayer(
            marks: [mark],
            visible: CGRect(x: 0.5, y: 0.5, width: 0.5, height: 0.5),
            selectedId: "a1"
        )
        let rect = zoomed.selectionRect(for: "a1", in: size)
        XCTAssertEqual(rect?.minX ?? -1, 0, accuracy: 0.001)
        XCTAssertEqual(rect?.minY ?? -1, 0, accuracy: 0.001)
        XCTAssertEqual(rect?.width ?? -1, 100, accuracy: 0.001)
    }
}
#endif
