import Foundation
import Testing

/// Source-surface guards for ⌘A over the preview (Daniel, 2026-08-31). The
/// policy lives inside a SwiftUI view extension that cannot be instantiated
/// in-process, so the two properties that make the chord correct are pinned
/// here: the ARMED TOOL picks the set, and every read goes through the
/// frame-matched list — a geometry measured on another rendition's pixels
/// scattered its boxes beside the page.
struct PreviewSelectAllPolicyGuardTests {
    private func regionsSource() throws -> String {
        let url = try AppSource.root().appendingPathComponent(
            "Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Regions.swift"
        )
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("the text tools select WORD boxes, everything else what is shown")
    func armedToolPicksTheSet() throws {
        let source = try regionsSource()
        #expect(source.contains("func selectAllGeometryForArmedTool()"))
        #expect(source.contains("case .textSelect, .wordSelect:"))
        #expect(source.contains("all.indices.filter { all[$0].level == \"word\" }"))
        // The visible-surface ruling: the default path selects what the
        // overlay is DRAWING, not the whole geometry behind it.
        #expect(source.contains("let shown = displayedGeometryBoxes.map(\\.index)"))
    }

    @Test("both paths fall back to the full frame-matched list, never to nothing")
    func bothPathsFallBack() throws {
        let source = try regionsSource()
        #expect(source.contains("indices = words.isEmpty ? Array(all.indices) : words"))
        #expect(source.contains("indices = shown.isEmpty ? Array(all.indices) : shown"))
        // …and the list it starts from is the gated one.
        #expect(source.contains("let all = frameMatchedGeometryBoxes"))
        #expect(source.contains("guard !all.isEmpty else { return }"))
        #expect(source.contains("RegionSelection.shared.selectAll("))
    }

    @Test("the interaction layer reads the frame-gated list, not the raw geometry")
    func interactionLayerIsFrameGated() throws {
        let source = try regionsSource()
        #expect(source.contains("allBoxes: frameMatchedGeometryBoxes"))
        #expect(
            !source.contains("allBoxes: ocrGeometry?.boxes"),
            "selection highlights drawn from an unmatched frame land beside the page"
        )
        #expect(source.contains("var frameMatchedGeometryBoxes: [OCRGeometryBox]"))
        #expect(source.contains("geometryFrameMatchesDisplay(ocrGeometry)"))
    }

    @Test("⌘A is published as a focused action, not key-handled locally")
    func chordIsPublishedNotHandled() throws {
        let viewer = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift"
            ), encoding: .utf8
        )
        #expect(viewer.contains("\\.previewSelectAll"))
        #expect(viewer.contains("run: { selectAllGeometryForArmedTool() }"))
    }
}

/// Sticky-tool arming (Daniel, 2026-08-31: "draw region doesn't do anything",
/// "star seems to star document, but not the actual location"). Both tools
/// now arm a DRAW mode; the star in particular must never take the old
/// fire-immediately path, which stamped a document-level mark and left the
/// page untouched.
struct StickyMarkupArmingGuardTests {
    private func source(_ rel: String) throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(rel), encoding: .utf8
        )
    }

    @Test("Draw Region arms the rubber-band ADD mode the context menu uses")
    func drawRegionArmsAddMode() throws {
        let viewer = try source("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        #expect(viewer.contains(
            "case .drawRegion:\n                    isDrawingRegion = false"
        ))
        #expect(viewer.contains("isDrawingRegion = false\n                    isAddingRegion = true"))
        // Every other tool must DISARM the add mode, or the marquee outlives
        // its own tool and the next drag makes a region nobody asked for.
        #expect(viewer.contains("if tool != .drawRegion { isAddingRegion = false }"))
    }

    @Test("the star arms the bookmark draw mode instead of firing at once")
    func starArmsBookmarkDraw() throws {
        let viewer = try source("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        #expect(viewer.contains("case .star: pendingAnnotationTool = .bookmark; isDrawingRegion = true"))

        let annotations = try source(
            "Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Annotations.swift"
        )
        #expect(annotations.contains("pendingAnnotationTool = .bookmark\n            isDrawingRegion = true"))
        #expect(
            !annotations.contains("createAnnotation(box: nil, tool: .bookmark)"),
            "a boxless bookmark stars the document, not the place on the page"
        )
        // …and the star stays sticky after a save, like the other draw tools.
        #expect(annotations.contains("|| sticky == .star"))
    }
}

/// The magnifier's ± steppers (2026-08-31): a bare `minus` glyph is a ~1pt
/// line, so the plain-button hit target was all but unclickable. Both
/// platforms' steppers must carry an explicit frame AND a `contentShape`,
/// since the frame alone does not extend a plain button's hit region.
struct MagnifierStepperHitBoxGuardTests {
    @Test("every ± stepper has a non-trivial frame and a rectangular hit shape")
    func steppersHaveRealHitTargets() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Preview/ImageViewer/MagnifierPanel.swift"
            ), encoding: .utf8
        )
        // Mac 16×16, touch 24×24 — two steppers each, so four of each pairing.
        let shapes = source.components(separatedBy: ".contentShape(Rectangle())").count - 1
        #expect(shapes >= 4, "a ± stepper lost its hit shape (\(shapes) found)")
        #expect(source.components(separatedBy: ".frame(width: 16, height: 16)").count - 1 >= 2)
        #expect(source.components(separatedBy: ".frame(width: 24, height: 24)").count - 1 >= 2)
    }
}
