@testable import Fichero
import SwiftUI
import Testing

/// One rubber band everywhere (#4601, `library.selection.one-rubber-band`; owner 2026-11-11: Finder's band, neutral grey,
/// never the accent, which may be yellow). What breaks without this: one surface keeps its own accent box and the
/// boards, the grid and the Preview each sweep in a different colour.
struct RubberBandEverywhereTests {
    private static let bands = [
        "Views/Library/ViewModes/Canvas/2D/CanvasSceneView+Gestures.swift",
        "Views/Library/ViewModes/Canvas/3D/CanvasSpaceView.swift",
        "Views/Library/ViewModes/Icon/LibraryMarquee.swift",
        "Views/Preview/ImageViewer/Regions/RegionInteractionLayer.swift",
        "Views/Preview/ImageEditor/ImageMarqueeOverlay.swift"
    ]

    @Test("every band draws the one RubberBand", arguments: bands)
    func everyBandIsTheOne(_ path: String) throws {
        #expect(try AppSource.code(path).contains("RubberBand()"), "\(path) draws its own band")
    }

    @Test("the band is grey and semantic, never the accent")
    func theBandIsNeutral() throws {
        let source = try AppSource.code("Views/Components/RubberBand.swift")
        #expect(!source.contains("accentColor"))
        #expect(RubberBand.fill == Color.secondary.opacity(0.12))
        #expect(RubberBand.border == Color.secondary.opacity(0.5))
        #expect(RubberBand.lineWidth == 1)
        // The icon grid's marquee no longer carries the accent in its own band.
        #expect(!(try AppSource.code("Views/Library/ViewModes/Icon/LibraryMarquee.swift")).contains("Color.accentColor.opacity(0.15)"))
    }
}
