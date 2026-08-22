import CoreGraphics
import Foundation
import RealityKit
import simd

// MARK: - Camera ops (split from CanvasScene3DRenderer for file_length /
// type_body_length — the class keeps state + reconcile; the camera verbs
// live here).

extension CanvasScene3DRenderer {
    /// Pan the look-at target across the camera's right/up plane; speed scales
    /// with distance so the pan feels constant at any zoom (ported from #3088).
    func pan(byScreenDelta delta: CGSize) {
        let speed = distance * 0.0022
        lookAt += (-cameraRight * Float(delta.width) + cameraUp * Float(delta.height)) * speed
        // CLAMP to content bounds + margin (user, 2026-08-20: canvas pans
        // must never lose the board) — mirror of the 2D camera clamp.
        let points = placeablesById.values.map { Canvas3DProjection.scenePosition($0.position) }
        if !points.isEmpty {
            let margin: Float = max(distance * 0.5, 2)  // ~half a viewport (Daniel: one was too wide)
            let xCoords = points.map(\.x), yCoords = points.map(\.y), zCoords = points.map(\.z)
            lookAt.x = min(max(lookAt.x, xCoords.min()! - margin), xCoords.max()! + margin)
            lookAt.y = min(max(lookAt.y, yCoords.min()! - margin), yCoords.max()! + margin)
            lookAt.z = min(max(lookAt.z, zCoords.min()! - margin), zCoords.max()! + margin)
        }
        updateCamera()
    }

    /// Camera pose for double-click zoom's return trip.
    func cameraSnapshot() -> (lookAt: SIMD3<Float>, distance: Float) {
        (lookAt, distance)
    }

    func restoreCamera(_ snapshot: (lookAt: SIMD3<Float>, distance: Float)) {
        lookAt = snapshot.lookAt
        setDistance(snapshot.distance)
    }

    /// Double-click: close in on ONE card; double-click again returns (user,
    /// 2026-08-20). Distance = the legibility floor with breathing room.
    func focusZoom(on id: String) {
        guard let placeable = placeablesById[id] else { return }
        lookAt = Canvas3DProjection.scenePosition(placeable.position)
        setDistance(CanvasZoomRange.minDistance(itemExtent: Self.itemExtent) * 1.8)
    }

    func setDistance(_ value: Float) {
        // #4411: was clamped to a fixed 2.2…16 — about 7x, which is neither
        // enough to read a page nor enough to see a whole arrangement. The
        // bounds now come from the content.
        distance = CanvasZoomRange.clamp(
            value, arrangementSpan: arrangementSpan, itemExtent: Self.itemExtent
        )
        updateCamera()
    }

    var currentDistance: Float { distance }

    /// A screen drag → a world delta in the camera's view plane, for dragging a
    /// card in 3D. ponytail: distance-scaled camera-plane heuristic (depth is the
    /// card's; exact feel is the calibration knob — tune with the flag on).
    /// Keep the content under the cursor fixed across a distance change:
    /// world-per-point at the content plane scales with distance (the pan
    /// speed's own constant), so the look-at shifts by the anchor times the
    /// speed delta. `anchor` is the cursor's offset from view center, y-down.
    func shiftLookAtForCursorZoom(anchor: CGPoint, oldDistance: Float) {
        let speedDelta = (oldDistance - distance) * 0.0022
        lookAt += (cameraRight * Float(anchor.x) - cameraUp * Float(anchor.y)) * speedDelta
        updateCamera()
    }

    func worldDragDelta(screenTranslation: CGSize, moveInZ: Bool = false) -> SIMD3<Double> {
        // Board-plane by DEFAULT: the raw camera basis carries a z component
        // whenever the orbit is tilted, so plain drags drifted in depth and
        // "popped back" on release. z moves only behind ⌥ (Daniel's ruling:
        // "drag must move X/Y only, z locked behind a modifier").
        let speed = distance * 0.0022
        var right = cameraRight; right.z = 0
        var planarUp = cameraUp; planarUp.z = 0
        if simd_length(right) > 0.0001 { right = simd_normalize(right) }
        if simd_length(planarUp) > 0.0001 { planarUp = simd_normalize(planarUp) }
        if moveInZ {
            let planar = right * Float(screenTranslation.width) * speed
            // Fingers up = toward the viewer (+z), matching the lift metaphor.
            let depth = Double(-screenTranslation.height) * Double(speed)
            return SIMD3<Double>(Double(planar.x), Double(planar.y), depth)
        }
        let delta = (right * Float(screenTranslation.width) - planarUp * Float(screenTranslation.height)) * speed
        return SIMD3<Double>(Double(delta.x), Double(delta.y), 0)
    }

    /// Screen positions of every placeable — the ⇧⌥ marquee's hit metric
    /// (user, 2026-08-20: "3D shift-option rubber band"). Manual perspective
    /// projection from the camera basis; RealityView exposes no projector on
    /// macOS. Vertical fov matches PerspectiveCamera's 60° default.
    func screenPositions(in viewSize: CGSize) -> [String: CGPoint] {
        guard viewSize.width > 0, viewSize.height > 0 else { return [:] }
        let forward = simd_normalize(lookAt - camera.position)
        let fovRadians: Float = 60 * .pi / 180
        let focal = Float(viewSize.height) / (2 * tan(fovRadians / 2))
        var out: [String: CGPoint] = [:]
        for (id, placeable) in placeablesById {
            let rel = Canvas3DProjection.scenePosition(placeable.position) - camera.position
            let depth = simd_dot(rel, forward)
            guard depth > 0.01 else { continue }  // behind the camera
            let lateral = simd_dot(rel, cameraRight)
            let vertical = simd_dot(rel, cameraUp)
            out[id] = CGPoint(
                x: CGFloat(Float(viewSize.width) / 2 + focal * lateral / depth),
                y: CGFloat(Float(viewSize.height) / 2 - focal * vertical / depth)
            )
        }
        return out
    }

    func updateCamera() {
        let offset = SIMD3<Float>(
            sin(yaw) * cos(pitch) * distance,
            sin(pitch) * distance,
            cos(yaw) * cos(pitch) * distance
        )
        camera.position = lookAt + offset
        camera.look(at: lookAt, from: camera.position, relativeTo: nil)
    }
}
