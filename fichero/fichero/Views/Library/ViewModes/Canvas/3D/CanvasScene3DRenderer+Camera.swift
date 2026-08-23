import CoreGraphics
import Foundation
import RealityKit
import simd

// MARK: - Camera ops (split from CanvasScene3DRenderer for file_length /
// type_body_length — the class keeps state + reconcile; the camera verbs
// live here).

/// Which camera the 3D shell puts on the board (§18.1 defect 1). One flag on
/// the SHELL, deliberately not on the arrangement: a board is a board whichever
/// arrangement filled it, and perspective belongs to a different kind of shell.
enum CanvasCameraProjection: Equatable {
    /// Boards — Grid, Shelf, As Filed, Timeline, Calendar, Terrain. Position is
    /// the datum and comparability is the point, so no foreshortening.
    case orthographic
    /// Reserved for panel-sequence and station-walk shells, where depth carries
    /// the sequence. Not built yet; the camera path is kept alive so building
    /// one is a flag, not a rewrite.
    case perspective
}

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
        // Face the card head-on (Daniel, 2026-08-22: "camera is not set to
        // straight on") — the reading pose, not the orbit's last angle.
        yaw = 0
        pitch = 0
        setDistance(CanvasZoomRange.minDistance(itemExtent: Self.itemExtent) * 1.4)
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
    /// (user, 2026-08-20: "3D shift-option rubber band"). Projected by hand from
    /// the camera basis; RealityView exposes no projector on macOS. It has to
    /// use the SAME projection the camera does, or the rubber band selects cards
    /// other than the ones it is drawn around — which is why this follows
    /// `projection` rather than assuming perspective.
    func screenPositions(in viewSize: CGSize) -> [String: CGPoint] {
        guard viewSize.width > 0, viewSize.height > 0 else { return [:] }
        let forward = simd_normalize(lookAt - camera.position)
        let orthoScale = Canvas3DProjection.orthoScale(forDistance: distance)
        var out: [String: CGPoint] = [:]
        for (id, placeable) in placeablesById {
            let rel = Canvas3DProjection.scenePosition(placeable.position) - camera.position
            let depth = simd_dot(rel, forward)
            guard depth > 0.01 else { continue }  // behind the camera
            let lateral = simd_dot(rel, cameraRight)
            let vertical = simd_dot(rel, cameraUp)
            switch projection {
            case .orthographic:
                out[id] = Canvas3DProjection.orthoScreenPoint(
                    lateral: lateral, vertical: vertical, orthoScale: orthoScale, viewSize: viewSize
                )
            case .perspective:
                out[id] = Canvas3DProjection.perspectiveScreenPoint(
                    lateral: lateral, vertical: vertical, depth: depth, viewSize: viewSize
                )
            }
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
        applyProjection()
    }

    /// Put the current projection on the camera entity. `distance` remains the
    /// one zoom variable in both modes — under ortho it becomes a scale rather
    /// than a standoff, so every consumer of `distance` (zoom range, detail
    /// tier, pan speed, fit, focus) is unchanged.
    private func applyProjection() {
        switch projection {
        case .orthographic:
            var ortho = OrthographicCameraComponent()
            ortho.scale = Canvas3DProjection.orthoScale(forDistance: distance)
            camera.components.remove(PerspectiveCameraComponent.self)
            camera.components.set(ortho)
        case .perspective:
            camera.components.remove(OrthographicCameraComponent.self)
            camera.components.set(PerspectiveCameraComponent())
        }
    }
}
