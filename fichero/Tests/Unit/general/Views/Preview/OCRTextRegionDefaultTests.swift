@testable import Fichero
import Foundation
import Testing

/// Text regions ship ON (#4418).
///
/// The geometry was captured, exposed on the artifact GET, and drawn on both
/// preview surfaces — and then defaulted OFF behind a toggle in an overflow
/// menu. That is the shape #4421's standing rule names as worse than absent: a
/// working capability nobody will find, which reads to the user as "this app
/// cannot show me where the text is".
///
/// The reason it must be ON rather than removed is #4497: Apple Vision is wrong
/// on roughly two characters in five of this material and cannot be tuned
/// better by configuration. A reader who cannot see WHICH two has to trust the
/// transcription wholesale. The boxes are the only thing that turns a
/// transcription into something checkable — a paragraph with no boxes over it
/// is a paragraph the pass never read, and that is visible at a glance.
///
/// These are source-level assertions, deliberately: an `@AppStorage` default
/// and a hit-testing decision are both facts about the shipped source, and
/// neither can be observed without a rendered view. What they cannot prove is
/// that the boxes land in the right PLACE — `applyOCRBoxes`' cropBox-inset
/// correction still has no test, which is recorded in the #4421 audit.
struct OCRTextRegionDefaultTests {

    // MARK: - The decision

    @Test("both preview surfaces default their text regions on")
    func bothSurfacesDefaultOn() throws {
        let surfaces = [
            ("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift", "imagePreview.ocrBoxesEnabled"),
            ("Views/Preview/PDFViewer/PDFPageWithToolbar.swift", "pdfPreview.ocrBoxesEnabled")
        ]

        for (path, key) in surfaces {
            let source = try AppSource.text(path)
            #expect(
                source.contains("@AppStorage(\"\(key)\") var ocrBoxesEnabled = true"),
                "\(key) must default on — see #4418/#4497"
            )
            #expect(
                !source.contains("@AppStorage(\"\(key)\") var ocrBoxesEnabled = false"),
                "\(key) is back to default-off, which ships a switch nobody finds"
            )
        }
    }

    /// The geometry probe re-runs when the DOCUMENT or the TOGGLE changes —
    /// never the page (2026-08-08, "changing page in PDF feels slow"):
    /// `OCRGeometrySelection.load`'s only input is the document id, so a
    /// page-keyed task re-fired the identical artifact queries on every flip.
    @Test("the OCR geometry task is keyed on document+toggle, not the page")
    func geometryTaskIsNotPageKeyed() throws {
        let source = try AppSource.text("Views/Preview/PDFViewer/PDFPageWithToolbar.swift")
        #expect(source.contains(#".task(id: "\(effectiveDocumentId)|\(ocrBoxesEnabled)")"#))
        #expect(
            !source.contains(#"\(effectiveDocumentId)|\(effectivePageIndex)|\(ocrBoxesEnabled)"#),
            "page-keyed geometry probe is back — every page flip refetches the whole document's geometry"
        )
    }

    /// The toggle itself stays. It is a view control ("show me the boxes"),
    /// not a feature flag — the same class of thing as the magnifier — and the
    /// no-needless-toggles rule is about capabilities that are half-built, not
    /// about letting a reader clear the page while they read.
    @Test("the toggle survives so a reader can still clear the page")
    func theToggleSurvives() throws {
        let toolbar = try AppSource.text("Views/Reader/ReaderToolbar+Overflow.swift")
        #expect(toolbar.contains("Text Boxes"))
    }

    // MARK: - On by default changes what hit-testing costs

    /// The regression this decision could have introduced, pinned so it cannot
    /// come back. Every box carries an opaque `.background`, and on a dense
    /// page the boxes cover most of the image. Interactive, always-mounted, and
    /// on by default, the layer would swallow every drag meant for panning or
    /// for drawing a region — on exactly the transcribed pages where both
    /// matter. Its sibling `BoundingBoxOverlay` avoids this by mounting only
    /// when armed; this one is always up, so it must be inert.
    @Test("the OCR layer never intercepts pointer events")
    func theLayerIsInert() throws {
        let source = try AppSource.text("Views/Preview/ImageViewer/OCRGeometryOverlay.swift")

        #expect(source.contains(".allowsHitTesting(false)"))
        #expect(!source.contains(".allowsHitTesting(true)"))
        // Hover machinery would be dead code behind an inert layer, and dead
        // interaction code reads as an affordance that exists.
        #expect(!source.contains(".onHover"))
    }

    /// VoiceOver still reads a box's recognised text even though the hover
    /// tooltip went with the hit-testing. Losing the tooltip was a considered
    /// cost; losing the screen-reader path would not have been (#4416's lesson).
    @Test("each box still names its recognised text to VoiceOver")
    func boxesKeepTheirAccessibilityLabel() throws {
        let source = try AppSource.text("Views/Preview/ImageViewer/OCRGeometryOverlay.swift")
        #expect(source.contains("accessibilityLabel(\"Recognized text: \\(box.text)\")"))
    }

    // MARK: - Absent, not broken

    /// A page with no geometry must render nothing and say nothing. Turning the
    /// layer on by default means every previewed page now asks for geometry,
    /// including the many that have none — the importer writes a zero-box
    /// artifact for every scanned page on purpose. An empty answer is the
    /// normal case, not an error.
    @Test("a page with no boxes renders nothing rather than an empty frame")
    func noGeometryRendersNothing() {
        let empty = OCRGeometry(text: "", provider: "apple_vision", model: nil, boxes: [])

        #expect(empty.wordBoxes.isEmpty)
        #expect(empty.lineBoxes.isEmpty)
    }

    /// Words when the pass produced them, lines otherwise — never both, because
    /// nested rectangles read as clutter rather than as structure. This is the
    /// rule the overlay's `boxes` property applies, restated where it can fail.
    @Test("words win over lines, and lines stand in when there are no words")
    func wordsWinOverLines() {
        let line = OCRGeometryBox(
            text: "Hello world", bbox: [0.1, 0.2, 0.6, 0.1], level: "line",
            confidence: nil, pageIndex: 0, charStart: nil, charEnd: nil
        )
        let word = OCRGeometryBox(
            text: "Hello", bbox: [0.1, 0.2, 0.25, 0.1], level: "word",
            confidence: nil, pageIndex: 0, charStart: nil, charEnd: nil
        )

        let both = OCRGeometry(text: "Hello world", provider: "apple_vision", model: nil, boxes: [line, word])
        let linesOnly = OCRGeometry(text: "Hello world", provider: "apple_vision", model: nil, boxes: [line])

        #expect(both.wordBoxes.map(\.text) == ["Hello"])
        #expect(linesOnly.wordBoxes.isEmpty)
        #expect(linesOnly.lineBoxes.map(\.text) == ["Hello world"])
    }
}
