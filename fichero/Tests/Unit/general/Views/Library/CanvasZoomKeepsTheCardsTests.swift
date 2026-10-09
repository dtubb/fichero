//
//  CanvasZoomKeepsTheCardsTests.swift
//  FicheroTests
//
//  #5476 (`library.canvas.a-folder-previews-as-its-canvas`, `library.canvas.positions-persist`):
//  a folder's 2D canvas in the Preview (chinese-vertical, two tall pages) opened with the two cards
//  side by side; a pinch then made them jump into one column, overlapping. The canvas must open at
//  the saved places and keep them through zoom.
//
//  Why it broke: `CanvasSceneView` resolved its board only inside RealityView's `update` closure,
//  which SwiftUI does not observe. Saved rows that loaded, page aspects that landed (they set the
//  grid pitch) and the pane's real size all changed without redrawing anything. The next unrelated
//  update, a pinch's gesture state, applied them all at once, so zooming looked like it moved the
//  cards. The overlap was the same staleness: the column was laid out on the nominal pitch while the
//  tall page textures had not landed, then the cards took their tall shape and nothing re-laid them.
//
//  These host the REAL view with the REAL `CanvasLayoutStore` and the REAL renderer, because the
//  defect lives in what the view observes; a test that calls `reconcile` by hand cannot see it.
//

#if os(macOS)
import AppKit
@testable import Fichero
import FicheroAPIClient
import Foundation
import Observation
import simd
import SwiftUI
import Testing

@MainActor
@Suite("Canvas: zooming keeps the cards where they are (#5476)", .tags(.library), .serialized)
struct CanvasZoomKeepsTheCardsTests {

    /// Two pages, each with its own source id so a test's page aspects never leak into another's.
    private func pages() -> [SpatialNode] {
        let run = UUID().uuidString
        return ["a", "b"].map {
            SpatialNode(
                id: "doc:\($0)-\(run)", roomId: wholeLibraryRoomId, nodeType: .source,
                sourceId: "src-\($0)-\(run)", label: $0, positionX: 0, positionY: 0
            )
        }
    }

    private func makeStore() -> CanvasLayoutStore {
        CanvasLayoutStore(client: FicheroClient(libraryPath: "/tmp/test.fichero"))
    }

    /// The canvas as both hosts mount it, in a window of `size`. The scope is the whole library
    /// (nil folder) so no load runs against a backend; the rows are spliced into the store as a
    /// load would publish them.
    private func mount(
        _ nodes: [SpatialNode], store: CanvasLayoutStore, renderer: CanvasOrtho2DRenderer, size: CGSize
    ) -> (NSWindow, NSHostingView<AnyView>) {
        let view = CanvasSceneView(
            nodes: nodes, connections: [], selectedNodeIds: .constant([]),
            layoutStore: store, renderer: renderer
        )
        let window = NSWindow(
            contentRect: CGRect(origin: CGPoint(x: 100, y: 100), size: size),
            styleMask: [.borderless], backing: .buffered, defer: false
        )
        let host = NSHostingView(rootView: AnyView(view.frame(width: size.width, height: size.height)))
        window.contentView = host
        return (window, host)
    }

    /// Let SwiftUI run its update passes until `done` holds (or about three seconds pass).
    @discardableResult
    private func settle(_ host: NSView, until done: () -> Bool) async -> Bool {
        for _ in 0..<300 {
            host.layoutSubtreeIfNeeded()
            if done() { return true }
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
        return done()
    }

    private func positions(_ renderer: CanvasOrtho2DRenderer) -> [String: SIMD3<Double>] {
        renderer.placeablesById.mapValues(\.position)
    }

    private func rows(_ nodes: [SpatialNode]) -> [CanvasItemLayout] {
        [
            CanvasItemLayout(itemId: nodes[0].id, x: 0, y: 0),
            CanvasItemLayout(itemId: nodes[1].id, x: 1.5, y: 0)
        ]
    }

    private func drawn(_ rows: [CanvasItemLayout]) -> [String: SIMD3<Double>] {
        Dictionary(uniqueKeysWithValues: rows.map { ($0.itemId, SIMD3<Double>($0.x, $0.y, $0.z)) })
    }

    // WHY: the root cause. The saved places land AFTER the canvas is up (the load is async), and
    // the view must draw them then. Before the fix nothing redrew until a pinch, so the first frame
    // showed the default layout and the zoom showed the saved one: the cards "jumped" on zoom.
    @Test("saved places that load after the canvas opens are drawn without any zoom")
    func savedPlacesDrawOnLoad() async {
        let nodes = pages(), store = makeStore(), renderer = CanvasOrtho2DRenderer()
        let (window, host) = mount(nodes, store: store, renderer: renderer, size: CGSize(width: 700, height: 600))
        defer { window.contentView = nil }
        #expect(await settle(host) { renderer.placeablesById.count == 2 }, "the canvas drew its cards")

        let saved = rows(nodes)
        store.layouts[wholeLibraryRoomId] = saved

        let arrived = await settle(host) { positions(renderer) == drawn(saved) }
        #expect(arrived, "the saved places are drawn when they load: \(positions(renderer))")
    }

    // WHY: the issue's own words: zooming changes the camera only. A pinch must leave every card
    // where it was, saved or not; the next update pass after it (which the pinch's gesture state
    // causes) must find nothing to move.
    @Test("zooming changes the camera and never a card's position")
    func zoomMovesTheCameraOnly() async {
        let nodes = pages(), store = makeStore(), renderer = CanvasOrtho2DRenderer()
        store.layouts[wholeLibraryRoomId] = rows(nodes)
        let (window, host) = mount(nodes, store: store, renderer: renderer, size: CGSize(width: 700, height: 600))
        defer { window.contentView = nil }
        #expect(await settle(host) { positions(renderer) == drawn(rows(nodes)) }, "opens at the saved places")
        let before = positions(renderer), scale = renderer.orthoScale

        renderer.setOrthoScale(scale / 3)
        // An update pass, as the pinch's gesture state causes one.
        store.layouts[wholeLibraryRoomId] = store.layout(for: wholeLibraryRoomId)
        await settle(host) { false }

        #expect(renderer.orthoScale != scale, "the camera zoomed")
        #expect(positions(renderer) == before, "no card moved on zoom")
    }

    // WHY: ruled 2026-10-09 (#5629): no card moves unless the person moves it. Page shapes that
    // land after the board is up (they set the grid's spacing) used to re-lay never-placed cards;
    // now they change nothing, and neither does a zoom after them. A board that knows its shapes
    // when it opens is laid out on them and its tall cards do not overlap.
    @Test("page shapes landing after open move no card; known at open, they lay the board out")
    func lateShapesMoveNothing() async {
        let nodes = pages(), size = CGSize(width: 700, height: 600)
        let lateStore = makeStore(), late = CanvasOrtho2DRenderer()
        let (lateWindow, lateHost) = mount(nodes, store: lateStore, renderer: late, size: size)
        defer { lateWindow.contentView = nil }
        #expect(await settle(lateHost) { late.placeablesById.count == 2 })
        let opened = positions(late)

        // chinese-vertical's two pages are 2876×4926 and 2811×4853: about 0.58 wide per 1 tall.
        for node in nodes { CanvasCardGeometry.recordAspect(0.58, forSourceId: node.sourceId ?? "") }
        await settle(lateHost) { false }
        #expect(positions(late) == opened, "late page shapes moved the cards")

        late.setOrthoScale(late.orthoScale / 3)
        lateStore.layouts[wholeLibraryRoomId] = []
        await settle(lateHost) { false }
        #expect(positions(late) == opened, "a zoom afterwards moves nothing")

        let knownStore = makeStore(), known = CanvasOrtho2DRenderer()
        let (knownWindow, knownHost) = mount(nodes, store: knownStore, renderer: known, size: size)
        defer { knownWindow.contentView = nil }
        #expect(await settle(knownHost) { known.placeablesById.count == 2 })
        let ids = nodes.map(\.id)
        if let first = positions(known)[ids[0]], let second = positions(known)[ids[1]] {
            let tall = CanvasCardGeometry.dimensions(
                area: Float(CanvasGridPlacement.cardArea), aspect: 0.58, fallback: 4 / 3
            )
            let apart = abs(first.x - second.x) >= Double(tall.width) || abs(first.y - second.y) >= Double(tall.height)
            #expect(apart, "the two pages overlap: \(first) and \(second)")
        }
    }

    // WHY: the default grid's columns follow the pane's shape, so a pane resize used to re-lay
    // every never-placed card. Through the real view: resizing the pane moves nothing.
    @Test("resizing the pane moves no card")
    func resizeMovesNothing() async {
        let nodes = pages() + pages(), store = makeStore(), renderer = CanvasOrtho2DRenderer()
        let (window, host) = mount(nodes, store: store, renderer: renderer, size: CGSize(width: 1100, height: 400))
        defer { window.contentView = nil }
        #expect(await settle(host) { renderer.placeablesById.count == 4 })
        let opened = positions(renderer)

        let view = CanvasSceneView(
            nodes: nodes, connections: [], selectedNodeIds: .constant([]),
            layoutStore: store, renderer: renderer
        )
        host.rootView = AnyView(view.frame(width: 300, height: 900))
        await settle(host) { false }

        #expect(positions(renderer) == opened, "a resize re-laid the board")
    }

    // WHY: one position source. The Preview's folder canvas (a narrow pane) and the Library's canvas
    // (a wide one) read the same store under the same scope, so the same saved places draw the same
    // board in both; a pane's shape may only decide where never-placed cards go.
    @Test("the Preview's canvas and the Library's canvas draw the same saved places")
    func previewAndLibraryAgree() async {
        let nodes = pages(), shared = makeStore()
        shared.layouts[wholeLibraryRoomId] = rows(nodes)
        let preview = CanvasOrtho2DRenderer(), library = CanvasOrtho2DRenderer()
        let (previewWindow, previewHost) = mount(nodes, store: shared, renderer: preview, size: CGSize(width: 360, height: 640))
        defer { previewWindow.contentView = nil }
        let (libraryWindow, libraryHost) = mount(nodes, store: shared, renderer: library, size: CGSize(width: 1100, height: 640))
        defer { libraryWindow.contentView = nil }

        #expect(await settle(previewHost) { positions(preview) == drawn(rows(nodes)) })
        #expect(await settle(libraryHost) { positions(library) == drawn(rows(nodes)) })
        #expect(positions(preview) == positions(library))
    }

    // WHY: the page-shape memo is what the grid pitch is computed from; it must tell an observing
    // view when a shape lands, or the board keeps a pitch for shapes it no longer has.
    @Test("a page shape landing is observable")
    func aspectLandingIsObserved() {
        let id = "src-observed-\(UUID().uuidString)"
        let fired = Fired()
        withObservationTracking {
            _ = CanvasCardGeometry.knownAspects(forSourceIds: [id])
        } onChange: {
            fired.value = true
        }
        CanvasCardGeometry.recordAspect(0.58, forSourceId: id)
        #expect(fired.value)
    }
}

private final class Fired: @unchecked Sendable {
    var value = false
}
#endif
