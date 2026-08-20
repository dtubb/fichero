import RealityKit
import SwiftUI

// MARK: - Page-thumbnail textures (split for file_length, 2026-08-20)

extension CanvasOrtho2DRenderer {
    func loadThumbnail(sourceId: String, into entity: ModelEntity, retriesLeft: Int = 2) {
        Task { @MainActor in
            do {
                // The CURRENT library's storage (user, live 2026-08-19): the
                // no-service call fell back to the GLOBAL library, so any
                // other library's 2D canvas never loaded a thumbnail.
                let texture = try await SpaceTextureCache.shared.texture(
                    forSourceId: sourceId, using: storageService
                )
                // First load: memoize the true aspect and rebuild the card
                // once (#4193) — makeCard reads the memo, so the rebuilt card
                // (mesh, collision, selection ring) takes the page's real
                // shape and later reskins keep it. The rebuild's own reload
                // is a cache hit that records no change, so this terminates.
                if CanvasCardGeometry.recordAspect(of: texture, forSourceId: sourceId) {
                    reskinCard(entity.name)
                } else {
                    entity.model?.materials = [UnlitMaterial(texture: texture)]
                }
            } catch {
                log.debug("canvas thumbnail load failed for \(sourceId, privacy: .public)")
                // Fresh imports 404 until their thumbnail generates moments
                // later — retry so the card doesn't stay a placeholder until
                // the next full reconcile.
                if retriesLeft > 0 {
                    try? await Task.sleep(for: .seconds(25))
                    loadThumbnail(sourceId: sourceId, into: entity, retriesLeft: retriesLeft - 1)
                }
            }
        }
    }
}
