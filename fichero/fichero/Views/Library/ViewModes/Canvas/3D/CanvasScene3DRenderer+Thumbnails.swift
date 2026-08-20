import RealityKit
import SwiftUI

// MARK: - Page-thumbnail textures (split for file_length, 2026-08-20)

extension CanvasScene3DRenderer {
    func loadThumbnail(sourceId: String, into entity: ModelEntity, retriesLeft: Int = 4) {
        Task { @MainActor in
            do {
                let texture = try await SpaceTextureCache.shared.texture(
                    forSourceId: sourceId, using: storageService
                )
                // First load: memoize the true aspect and rebuild the card
                // once (#4193) — makeCard reads the memo, so the rebuilt card
                // (mesh, collision, selection outline) takes the page's real
                // shape and later reskins keep it. The rebuild's own reload
                // is a cache hit that records no change, so this terminates.
                if CanvasCardGeometry.recordAspect(of: texture, forSourceId: sourceId) {
                    reskinCard(entity.name)
                } else {
                    entity.model?.materials = [UnlitMaterial(texture: texture)]
                }
            } catch {
                // Say WHY (perf audit 2026-08-19: 1,500 silent failures in
                // 16s made 'no thumbnails' undiagnosable) — and retry once:
                // fresh imports 404 until the derivative stage lands them.
                log.error("space thumbnail load failed for \(sourceId, privacy: .public): \(error.localizedDescription)")
                if retriesLeft > 0 {
                    try? await Task.sleep(for: .seconds(25))
                    loadThumbnail(sourceId: sourceId, into: entity, retriesLeft: retriesLeft - 1)
                }
            }
        }
    }

    /// The page-image source id for a source-node placeable, nil otherwise.
    func sourceId(of placeable: CanvasPlaceable) -> String? {
        guard case .node(let node) = placeable.content,
              node.nodeType == .source,
              let sourceId = node.sourceId, !sourceId.isEmpty else { return nil }
        return sourceId
    }
}
