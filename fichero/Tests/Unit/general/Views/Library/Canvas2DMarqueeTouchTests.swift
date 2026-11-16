import CoreGraphics
@testable import Fichero
import Foundation
import Testing

/// `library.canvas.rubber-band-selects-what-it-touches` (#5305, owner 2026-11-11): a rubber band on the board takes every
/// card it touches, not only the cards whose centre it covers.
@MainActor
@Suite("Canvas: a rubber band selects what it touches (#5305)")
struct Canvas2DMarqueeTouchTests {

    private let viewSize = CGSize(width: 900, height: 600)

    private func board() -> CanvasOrtho2DRenderer {
        let nodes = (0..<3).map {
            SpatialNode(id: "doc:\($0)", roomId: "room", nodeType: .source, label: "\($0)", positionX: 0, positionY: 0)
        }
        let state = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: [], items: [], defaultPlacement: .grid(columns: 3)
        )
        let renderer = CanvasOrtho2DRenderer()
        renderer.viewportSize = viewSize
        renderer.needsFitOnNextContent = true
        renderer.reconcile(to: state)
        return renderer
    }

    /// Where the renderer draws a card on screen, measured the way its click hit-test measures it.
    private func cardRect(_ id: String, in renderer: CanvasOrtho2DRenderer) throws -> CGRect {
        let placeable = try #require(renderer.placeablesById[id])
        let (width, height) = renderer.cardDimensions(placeable)
        let center = Canvas2DProjection.screenPoint(
            scene: Canvas2DProjection.scenePosition(placeable.position),
            cameraX: renderer.camera.position.x, cameraY: renderer.camera.position.y,
            orthoScale: renderer.orthoScale, viewSize: viewSize
        )
        let rect = Canvas2DProjection.cardScreenRect(
            center: center, width: width, height: height,
            worldPerPoint: Canvas2DProjection.worldPerPoint(orthoScale: renderer.orthoScale, viewHeight: viewSize.height)
        )
        // The click hit-test agrees: a point just inside the edge is this card.
        #expect(renderer.placeableId(atScreenPoint: CGPoint(x: rect.maxX - 1, y: rect.midY), viewSize: viewSize) == id)
        return rect
    }

    @Test("a band over only a card's edge takes the card")
    func bandOverTheEdgeTakesTheCard() throws {
        let renderer = board()
        let card = try cardRect("doc:1", in: renderer)
        // From 4 pt inside the bottom edge to well below it: nowhere near the centre.
        let band = CGRect(x: card.midX - 10, y: card.maxY - 4, width: 20, height: 40)
        #expect(!band.contains(CGPoint(x: card.midX, y: card.midY)))
        #expect(renderer.placeableIds(inScreenRect: band, viewSize: viewSize).contains("doc:1"))
    }

    @Test("a band that stops short of a card leaves it out")
    func bandShortOfTheCardLeavesItOut() throws {
        let renderer = board()
        let card = try cardRect("doc:1", in: renderer)
        let band = CGRect(x: card.midX - 10, y: card.maxY + 3, width: 20, height: 40)
        #expect(!renderer.placeableIds(inScreenRect: band, viewSize: viewSize).contains("doc:1"))
    }

    @Test("a band dragged dead level still takes the cards it crosses")
    func levelBandTakesWhatItCrosses() throws {
        let renderer = board()
        let card = try cardRect("doc:1", in: renderer)
        let band = CGRect(x: card.minX - 30, y: card.midY, width: 60, height: 0)
        #expect(renderer.placeableIds(inScreenRect: band, viewSize: viewSize).contains("doc:1"))
    }
}
