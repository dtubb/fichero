@testable import Fichero
import Foundation
import XCTest

/// An AI redraw of a page as SVG is another way that page LOOKS, so it joins
/// the preview's up/down rendition flip (Daniel, 2026-09-04: "that'd be cool
/// to demo") — the same move the original↔edited pair made in ce831ebd3.
@MainActor
final class SVGRenditionTests: XCTestCase {

    private let now = Date(timeIntervalSince1970: 1_756_900_000)

    private func artifact(
        _ id: String,
        documentId: String = "page-1",
        type: String = "conversion",
        content: String?,
        model: String? = nil,
        provider: String? = nil,
        minutesAgo: Double = 0
    ) -> Artifact {
        Artifact(
            id: id,
            documentId: documentId,
            artifactType: type,
            content: content,
            provider: provider,
            model: model,
            createdAt: now.addingTimeInterval(-minutesAgo * 60)
        )
    }

    // MARK: - Which artifacts are redraws

    func testAnSVGArtifactBecomesARendition() {
        let renditions = DocumentRendition.svgRenditions(
            documentId: "page-1",
            artifacts: [artifact("a", content: "<svg viewBox=\"0 0 10 10\"></svg>")]
        )
        XCTAssertEqual(renditions.count, 1)
        XCTAssertEqual(renditions.first?.role, DocumentRendition.svgRole)
        XCTAssertEqual(renditions.first?.id, "svg:a")
    }

    /// The load-bearing distinction: `convert` writes `conversion` for five
    /// target formats, so the TYPE cannot say which is a picture. A markdown
    /// conversion joining the flip would be an entry that renders blank.
    func testANonSVGConversionIsNotARendition() {
        let renditions = DocumentRendition.svgRenditions(
            documentId: "page-1",
            artifacts: [artifact("a", content: "# A markdown conversion\n\nText.")]
        )
        XCTAssertTrue(renditions.isEmpty)
    }

    func testAnEmptyOrMissingContentIsNotARendition() {
        XCTAssertTrue(
            DocumentRendition.svgRenditions(
                documentId: "page-1", artifacts: [artifact("a", content: nil)]
            ).isEmpty
        )
        XCTAssertTrue(
            DocumentRendition.svgRenditions(
                documentId: "page-1", artifacts: [artifact("a", content: "")]
            ).isEmpty
        )
    }

    func testAnotherDocumentsRedrawIsNeverThisPagesRendition() {
        let renditions = DocumentRendition.svgRenditions(
            documentId: "page-1",
            artifacts: [artifact("a", documentId: "page-2", content: "<svg></svg>")]
        )
        XCTAssertTrue(renditions.isEmpty)
    }

    func testRedrawsAreOrderedNewestFirst() {
        let renditions = DocumentRendition.svgRenditions(
            documentId: "page-1",
            artifacts: [
                artifact("old", content: "<svg></svg>", minutesAgo: 90),
                artifact("new", content: "<svg></svg>", minutesAgo: 1)
            ]
        )
        XCTAssertEqual(renditions.map(\.id), ["svg:new", "svg:old"])
    }

    // MARK: - What a redraw claims about itself

    /// The honesty that matters most here. A redraw is a NEW drawing, not the
    /// page's own pixels re-processed, so every box normalised to the node's
    /// frame is wrong on it. `hasOwnFrame` is what makes
    /// `overlayFrameMatches` skip them instead of painting a plausible band
    /// over coordinates the picture never had.
    func testARedrawAlwaysDeclaresItsOwnFrame() {
        let rendition = DocumentRendition.svgRenditions(
            documentId: "page-1", artifacts: [artifact("a", content: "<svg></svg>")]
        ).first
        XCTAssertEqual(rendition?.hasOwnFrame, true)
        XCTAssertEqual(
            overlayFrameMatches(required: nil, displayed: "svg:a", displayedHasOwnFrame: true),
            false,
            "A page-frame overlay must not draw over a redrawing of the page."
        )
    }

    func testTheNoteNamesWhoDrewIt() {
        XCTAssertEqual(
            DocumentRendition.renditionNote(
                for: artifact("a", content: "<svg></svg>", model: "claude-opus-5")
            ),
            "Redrawn as SVG by claude-opus-5"
        )
        XCTAssertEqual(
            DocumentRendition.renditionNote(for: artifact("a", content: "<svg></svg>")),
            "Redrawn as SVG",
            "An artifact with no recorded producer says less rather than guessing."
        )
    }

    // MARK: - Id round trip

    func testTheArtifactIdSurvivesTheRenditionId() {
        let id = DocumentRendition.svgArtifactRenditionId(artifactId: "abc-123")
        XCTAssertEqual(DocumentRendition.svgArtifactId(of: id), "abc-123")
    }

    func testARealRenditionIdIsNotAnSVGArtifact() {
        XCTAssertNil(DocumentRendition.svgArtifactId(of: "1f9c-real-rendition"))
        XCTAssertNil(
            DocumentRendition.svgArtifactId(of: "svg:"),
            "A prefix with no artifact behind it addresses nothing."
        )
    }

    func testAnEditStateIsNotAnSVGArtifactAndViceVersa() {
        let edit = DocumentRendition.editStateId(role: "edited", documentId: "d1")
        XCTAssertNil(DocumentRendition.svgArtifactId(of: edit))
        let svg = DocumentRendition.svgArtifactRenditionId(artifactId: "a1")
        XCTAssertNil(
            DocumentRendition.editStateRole(of: svg),
            "The two synthetic id spaces must not overlap — each flip branch keys off its own."
        )
    }

    // MARK: - Where a redraw sits in the sequence

    /// A redraw is never what a page OPENS on, sticky or not: the sticky role
    /// means "keep showing me this KIND as I step through pages", which is
    /// right for background-removed and wrong for a model's interpretation of
    /// the page — it would replace the page before the reader had seen it.
    func testARedrawIsNeverTheLandingRendition() {
        let renditions = [
            DocumentRendition(
                id: "r1", documentId: "d1", role: "original", path: "", isPrimary: true,
                pixelWidth: nil, pixelHeight: nil, isMaterialized: true,
                hasOwnFrame: false, note: nil
            ),
            DocumentRendition(
                id: "svg:a", documentId: "d1", role: DocumentRendition.svgRole, path: "",
                isPrimary: false, pixelWidth: nil, pixelHeight: nil, isMaterialized: true,
                hasOwnFrame: true, note: nil
            )
        ]
        XCTAssertEqual(
            preferredRenditionIndex(in: renditions, stickyRole: DocumentRendition.svgRole), 0
        )
    }

    func testAnOrdinaryStickyRoleStillWins() {
        let renditions = [
            DocumentRendition(
                id: "r1", documentId: "d1", role: "original", path: "", isPrimary: true,
                pixelWidth: nil, pixelHeight: nil, isMaterialized: true,
                hasOwnFrame: false, note: nil
            ),
            DocumentRendition(
                id: "r2", documentId: "d1", role: "background_removed", path: "",
                isPrimary: false, pixelWidth: nil, pixelHeight: nil, isMaterialized: true,
                hasOwnFrame: false, note: nil
            )
        ]
        XCTAssertEqual(
            preferredRenditionIndex(in: renditions, stickyRole: "background_removed"), 1
        )
    }
}
