import CoreGraphics
@testable import Fichero
import Foundation
import simd
import Testing

/// `library.canvas.camera-is-saved-when-it-rests` (#4601): a board's camera is written to the preferences once a pan
/// has rested, not on every scroll tick, because every preferences write re-runs the window's `@AppStorage` views.
@MainActor
@Suite("Canvas: the camera is saved when it rests (#4601)")
struct CanvasCameraSaveRestsTests {

    private func board() -> CanvasOrtho2DRenderer {
        let nodes = (0..<3).map {
            SpatialNode(id: "doc:\($0)", roomId: "room", nodeType: .source, label: "\($0)", positionX: 0, positionY: 0)
        }
        let state = CanvasSceneState.resolve(
            nodes: nodes, connections: [], links: [], layoutRows: [], items: [], defaultPlacement: .grid(columns: 3)
        )
        let renderer = CanvasOrtho2DRenderer()
        renderer.viewportSize = CGSize(width: 900, height: 600)
        renderer.needsFitOnNextContent = true
        renderer.reconcile(to: state)
        return renderer
    }

    @Test("a run of pan ticks saves nothing until it rests, then the last pose once")
    func panTicksSaveOnce() {
        let renderer = board()
        var saved: [SIMD3<Float>] = []
        renderer.onCameraChange = { saved.append($0.position) }
        for _ in 0..<5 { renderer.panCamera(worldDelta: SIMD2(0.01, 0)) }
        #expect(saved.isEmpty)
        renderer.saveCameraNow()
        #expect(saved == [renderer.cameraSnapshot().position])
        renderer.saveCameraNow()
        #expect(saved.count == 1)
    }

    @Test("a rested pan saves by itself after the delay")
    func restedPanSaves() async throws {
        let renderer = board()
        var saves = 0
        renderer.onCameraChange = { _ in saves += 1 }
        renderer.panCamera(worldDelta: SIMD2(0.01, 0))
        renderer.panCamera(worldDelta: SIMD2(0.01, 0))
        try await Task.sleep(for: .seconds(CanvasOrtho2DRenderer.cameraSaveDelay + 0.4))
        #expect(saves == 1)
    }

    @Test("a save pending when the board switches folder goes to the folder it was made in")
    func pendingSaveKeepsItsFolder() {
        let renderer = board()
        var savedFor: [String] = []
        renderer.onCameraChange = { _ in savedFor.append("first") }
        renderer.panCamera(worldDelta: SIMD2(0.01, 0))
        renderer.onCameraChange = { _ in savedFor.append("second") }
        renderer.saveCameraNow()
        #expect(savedFor == ["first"])
    }

    @Test("fitting the board is not saved as the person's camera")
    func fitIsNotSaved() {
        let renderer = board()
        var saves = 0
        renderer.onCameraChange = { _ in saves += 1 }
        renderer.fit()
        renderer.saveCameraNow()
        #expect(saves == 0)
    }
}
