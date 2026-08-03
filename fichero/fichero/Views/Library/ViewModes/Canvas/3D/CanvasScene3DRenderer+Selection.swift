import CoreGraphics
import Foundation
import RealityKit
import simd

// MARK: - The 3D scene's selection frames (#4409)

/// Split out of `CanvasScene3DRenderer` by cohesion, and mirroring the 2D
/// renderer's own split. 3D draws frames but NO resize handles — see
/// `CanvasSelectionDecorator.showsHandles`.
extension CanvasScene3DRenderer {

    // MARK: - Selection decoration (#4409)

    /// Redraw the selection frames from the cards' LIVE positions. 3D draws no
    /// resize handles — see `CanvasSelectionDecorator.showsHandles`.
    func refreshSelectionDecoration() {
        // `depth` is non-escaping and consumed inside this call, so capturing
        // self strongly is correct — a `[weak self]` here would only add a
        // `?? 0` fallback that silently draws frames on the wrong plane.
        decorator.update(items: selectionFrameItems(), depth: { self.sceneZ(of: $0) })
    }

    func sceneZ(of id: String) -> Float {
        placeablesRoot.findEntity(named: id)?.position.z
            ?? placeablesById[id].map { Canvas3DProjection.scenePosition($0.position).z }
            ?? 0
    }

    func selectionFrameItems() -> [CanvasSelectionFrame.Item] {
        selection.compactMap { id in
            guard let placeable = placeablesById[id] else { return nil }
            let entity = placeablesRoot.findEntity(named: id)
            let scene = entity?.position ?? Canvas3DProjection.scenePosition(placeable.position)
            let size = placeable.size ?? Self.defaultCardSize
            let (width, height) = CanvasCardGeometry.dimensions(
                area: Float(size.width) * Float(size.height),
                aspect: sourceId(of: placeable).flatMap { CanvasCardGeometry.knownAspect(forSourceId: $0) },
                fallback: Float(size.width) / Float(size.height)
            )
            return CanvasSelectionFrame.Item(
                id: id,
                centerX: scene.x,
                centerY: scene.y,
                width: width,
                height: height,
                isResizable: CanvasSelectionFrame.isResizable(placeable.content)
            )
        }
    }
}
