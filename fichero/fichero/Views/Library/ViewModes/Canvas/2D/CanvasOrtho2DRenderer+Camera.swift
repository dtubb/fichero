import RealityKit
import simd

// MARK: - Camera ops (split from CanvasOrtho2DRenderer for file_length).

extension CanvasOrtho2DRenderer {
    /// Camera pose for double-click zoom's return trip.
    func cameraSnapshot() -> (position: SIMD3<Float>, scale: Float) {
        (camera.position, orthoScale)
    }

    func restoreCamera(_ snapshot: (position: SIMD3<Float>, scale: Float)) {
        camera.position = snapshot.position
        setOrthoScale(snapshot.scale)
    }

    /// Double-click: fill the view with ONE card (user, 2026-08-20:
    /// "double-click zooms node to full screen, double-click again zooms
    /// back"). Scale from the card cell, same basis fit() uses for the board.
    func focusZoom(on id: String) {
        focus(on: id)
        setOrthoScale(Float(CanvasGridPlacement.cellHeight) * 0.7)
    }

    /// Pan the camera across its plane by a world-space delta.
    func panCamera(worldDelta: SIMD2<Float>) {
        camera.position += SIMD3<Float>(worldDelta.x, worldDelta.y, 0)
        // CLAMP to the content bounds plus a one-viewport margin (user,
        // 2026-08-20: "when we scroll to the edge it should give a bit of
        // extra space… right now we can get lost"). The board can never
        // scroll so far that no card remains reachable.
        let points = placeablesById.values.map { Canvas2DProjection.scenePosition($0.position) }
        guard !points.isEmpty else { return }
        let margin = orthoScale * 0.5  // ~half a viewport of slack (Daniel: one was too wide)
        let xCoords = points.map(\.x), yCoords = points.map(\.y)
        camera.position.x = min(max(camera.position.x, xCoords.min()! - margin), xCoords.max()! + margin)
        camera.position.y = min(max(camera.position.y, yCoords.min()! - margin), yCoords.max()! + margin)
    }
}
