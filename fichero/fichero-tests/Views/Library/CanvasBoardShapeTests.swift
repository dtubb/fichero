//
//  CanvasBoardShapeTests.swift
//  FicheroTests
//
//  §18.1 defect 3 — 2,228 pages rendered as a narrow vertical ribbon in a wide
//  window: most of the field sat off screen in one axis, and the board's shape
//  carried no information about the data, only about a hardcoded 10.
//
//  Two things are pinned here, and the SECOND is the one that rots:
//   1. the derivation itself — a board whose aspect approximates the viewport's;
//   2. that BOTH canvases route through that one derivation. They share a layout
//      store, so a move in one is a move in the other (user, 2026-08-20); if
//      they ever computed columns separately the same folder would open as two
//      different boards. Only a source scan can see that, so it is a guard test.
//

import CoreGraphics
@testable import Fichero
import Foundation
import Testing

@Suite("Board shape: viewport-derived columns (§18.1 defect 3)")
struct CanvasBoardShapeTests {

    /// How square the board comes out, as `width / height` in world units.
    private func boardAspect(itemCount: Int, viewportSize: CGSize) -> Double {
        let cell = CanvasGridPlacement.nominalCell
        let columns = CanvasGridPlacement.sharedColumnCount(
            itemCount: itemCount, viewportSize: viewportSize
        )
        let rows = Int((Double(itemCount) / Double(columns)).rounded(.up))
        return (Double(columns) * Double(cell.width)) / (Double(rows) * Double(cell.height))
    }

    @Test("a wide window gives a wide board, a tall window a tall one")
    func boardFollowsTheViewport() {
        let wide = CanvasGridPlacement.sharedColumnCount(
            itemCount: 2_228, viewportSize: CGSize(width: 1_600, height: 900)
        )
        let tall = CanvasGridPlacement.sharedColumnCount(
            itemCount: 2_228, viewportSize: CGSize(width: 900, height: 1_600)
        )
        let square = CanvasGridPlacement.sharedColumnCount(
            itemCount: 2_228, viewportSize: CGSize(width: 1_000, height: 1_000)
        )
        #expect(wide > square)
        #expect(square > tall)
        // And the ribbon is gone: the real complaint was 2,228 items at TEN
        // columns — a board 223 rows deep in a 16:9 window.
        #expect(wide > CanvasGridPlacement.defaultColumns)
    }

    @Test("the board's aspect lands near the viewport's, not an order out")
    func boardAspectApproximatesViewport() {
        for size in [CGSize(width: 1_600, height: 900), CGSize(width: 800, height: 1_200),
                     CGSize(width: 1_000, height: 1_000), CGSize(width: 2_560, height: 1_440)] {
            let viewport = Double(size.width) / Double(size.height)
            // Boards of at least ~100 cards. Below that, rounding to whole
            // columns and up to whole rows dominates — a 12-card folder simply
            // has no arrangement whose aspect is 0.67, and forcing one would
            // mean fractional rows.
            for count in [120, 2_228, 4_241] {
                let ratio = boardAspect(itemCount: count, viewportSize: size) / viewport
                // Rounding to whole columns and up to whole rows means this can
                // never be exact; within ±35% is "the same shape as the window"
                // rather than "a ribbon".
                #expect(ratio > 0.65 && ratio < 1.35,
                        "count \(count) in \(size): board/viewport aspect ratio \(ratio)")
            }
        }
    }

    @Test("a small folder is one row, never a wide row with empty slots")
    func smallFoldersDoNotOverflowTheirCards() {
        #expect(CanvasGridPlacement.sharedColumnCount(
            itemCount: 4, viewportSize: CGSize(width: 3_000, height: 400)) == 4)
        #expect(CanvasGridPlacement.sharedColumnCount(
            itemCount: 1, viewportSize: CGSize(width: 1_600, height: 900)) == 1)
    }

    @Test("a degenerate viewport falls back to the shared default, never zero")
    func degenerateViewportFallsBack() {
        let sizes = [CGSize.zero, CGSize(width: 1_600, height: 0), CGSize(width: 0, height: 900),
                     CGSize(width: -100, height: 900), CGSize(width: .nan, height: 900),
                     CGSize(width: .infinity, height: 900)]
        for size in sizes {
            #expect(CanvasGridPlacement.sharedColumnCount(itemCount: 500, viewportSize: size)
                        == CanvasGridPlacement.defaultColumns)
        }
        // An empty scope has no board to shape.
        #expect(CanvasGridPlacement.sharedColumnCount(
            itemCount: 0, viewportSize: CGSize(width: 1_600, height: 900))
                    == CanvasGridPlacement.defaultColumns)
        #expect(CanvasGridPlacement.sharedColumnCount(
            itemCount: -5, viewportSize: CGSize(width: 1_600, height: 900))
                    == CanvasGridPlacement.defaultColumns)
    }

    @Test("a taller cell pitch means fewer columns, so the board stays in shape")
    func pitchFeedsBackIntoTheShape() {
        let viewport = CGSize(width: 1_600, height: 900)
        let nominal = CanvasGridPlacement.sharedColumnCount(itemCount: 500, viewportSize: viewport)
        // Tall pages (aspect 0.5) raise the ROW pitch, so the same board needs
        // fewer, wider columns to keep the window's shape.
        let tall = CanvasGridPlacement.sharedColumnCount(
            itemCount: 500, viewportSize: viewport, cell: CanvasGridPlacement.cell(forAspects: [0.5])
        )
        #expect(tall > nominal)
    }

    @Test("the derivation is deterministic and renderer-free")
    func deterministic() {
        let viewport = CGSize(width: 1_440, height: 900)
        let first = CanvasGridPlacement.sharedColumnCount(itemCount: 2_228, viewportSize: viewport)
        for _ in 0..<5 {
            #expect(CanvasGridPlacement.sharedColumnCount(itemCount: 2_228, viewportSize: viewport) == first)
        }
    }
}

// MARK: - Both canvases route through the ONE derivation

/// Call-site counting: the placement math cannot see whether a renderer stopped
/// asking it. The hardcoded `.grid(columns: 10)` these replace is exactly the
/// kind of literal that gets re-added "just for this one view".
struct CanvasSharedColumnGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    private let canvases = [
        "Views/Library/ViewModes/Canvas/2D/CanvasSceneView.swift",
        "Views/Library/ViewModes/Canvas/3D/CanvasSpaceView.swift",
    ]

    @Test("both canvases ask CanvasGridPlacement for their column count")
    func bothRouteThroughTheSharedDerivation() throws {
        for path in canvases {
            let source = try appSource(path)
            #expect(source.contains("CanvasGridPlacement.sharedColumnCount("), "\(path) forked the derivation")
            // The literal it replaced. A folder must not open as two different
            // boards depending on which canvas you happen to be in.
            #expect(!source.contains(".grid(columns: 10)"), "\(path) reintroduced the hardcoded 10")
        }
    }

    @Test("both canvases resolve against a real viewport, not a fixed size")
    func bothPassTheirViewport() throws {
        for path in canvases {
            let source = try appSource(path)
            #expect(source.contains("resolvedState(in: geo.size)"), "\(path) stopped measuring its viewport")
            #expect(source.contains("viewportSize: viewportSize"), "\(path) is not passing the viewport through")
        }
    }

    @Test("both canvases pass the aspect-derived cell pitch too")
    func bothPassTheDerivedPitch() throws {
        for path in canvases {
            let source = try appSource(path)
            #expect(source.contains("gridCell: gridCell"), "\(path) fell back to the nominal pitch")
            #expect(source.contains("CanvasCardGeometry.knownAspects("), "\(path) stopped reading real card aspects")
        }
    }
}
