import Foundation
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

    /// Every card as the camera frames it: where it is drawn and its size.
    func cameraCards() -> [CanvasCameraFit.Card] {
        placeablesById.values.map { placeable in
            let point = Canvas2DProjection.scenePosition(placeable.position)
            let (width, height) = cardDimensions(placeable)
            return CanvasCameraFit.Card(center: SIMD2(point.x, point.y), size: SIMD2(width, height))
        }
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
        cameraDidChange()
    }

    /// Tell the host where the camera now is, once the board has content, so it can remember where
    /// this person left this folder's board (2026-09-30).
    ///
    /// Saved once the camera has rested for `cameraSaveDelay`, never per scroll tick
    /// (`library.canvas.camera-is-saved-when-it-rests`): every save is a preferences write, and every
    /// preferences write re-runs each `@AppStorage` view in the window. The pose and the folder's
    /// callback are taken now, so a board switched away before the save still saves its own camera.
    func cameraDidChange() {
        guard !placeablesById.isEmpty, let onCameraChange else { return }
        // A move the person made: from here the camera is theirs, remembered, never re-fitted.
        cameraIsAutoFit = false
        pendingCameraSave?.cancel()
        let snapshot = cameraSnapshot()
        let save = DispatchWorkItem { onCameraChange(snapshot) }
        pendingCameraSave = save
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.cameraSaveDelay, execute: save)
    }

    /// How long a pan or zoom must rest before its camera is saved.
    static let cameraSaveDelay: TimeInterval = 0.3

    /// Save a pending camera now rather than when it rests; nothing when none is pending.
    func saveCameraNow() {
        guard let save = pendingCameraSave else { return }
        pendingCameraSave = nil
        save.perform()
        save.cancel()
    }
}
