@testable import Fichero
import Foundation
import Testing

/// What each Preview mode puts on the markup row (`source.editor.toolbar-follows-the-mode`): reading offers no box or
/// pixel tool, segments offers the shape tools and no annotation, image offers no markup tool at all.
struct PreviewWorkModeToolsTests {
    private let annotation: Set<String> = [
        "previewMarkupTextSelect", "previewMarkupWordSelect", "previewMarkupHighlight", "previewMarkupLine",
        "previewMarkupNote", "previewMarkupStar", "previewMarkupCheck"
    ]
    private let shapes: Set<String> = [
        "previewMarkupSelect", "previewMarkupDrawRegion", "previewMarkupShapeKind", "previewMarkupDelete",
        "previewMarkupCombine"
    ]

    @Test("Read offers the annotation tools and no shape tool")
    func read() {
        #expect(PreviewWorkMode.read.tools == annotation)
        #expect(shapes.allSatisfy { !PreviewWorkMode.read.offers($0) })
    }

    @Test("Segments offers the shape tools and no annotation tool")
    func segments() {
        #expect(PreviewWorkMode.segments.tools == shapes)
        #expect(annotation.allSatisfy { !PreviewWorkMode.segments.offers($0) })
    }

    @Test("Image offers no markup tool: its operations are the image controls")
    func image() {
        #expect(PreviewWorkMode.image.tools.isEmpty)
    }

    @Test("the mode and Edit Segments are one state, whichever is set")
    func oneState() {
        let state = WindowState(libraryId: UUID())
        state.isEditingSegments = true
        #expect(state.previewMode == .segments)
        state.previewMode = .image
        #expect(!state.isEditingSegments)
        state.previewMode = .segments
        #expect(state.isEditingSegments)
        state.isEditingSegments = false
        #expect(state.previewMode == .read)
    }
}
