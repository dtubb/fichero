import RealityKit
import SwiftUI

// MARK: - Page-thumbnail textures (split for file_length, 2026-08-20)

extension CanvasOrtho2DRenderer {
    /// Rebuild ONE card in place — the texture-driven path (a loaded page's true
    /// aspect, a resize). Lives beside the loader that triggers it, and out of
    /// the main file, which is at its file_length ceiling.
    func reskinCard(_ id: String) {
        guard let placeable = placeablesById[id] else { return }
        // The rebuilt entity starts flat; the reload below re-adds it.
        texturedIds.remove(id)
        placeablesRoot.findEntity(named: id)?.removeFromParent()
        let card = makeCard(placeable)
        // A rebuilt card is a NEW entity carrying none of the old one's
        // components — else a card reskinning mid-search comes back bright.
        CanvasEmphasisPainter.apply(emphasis, to: card, id: id)
        placeablesRoot.addChild(card)
    }

    func loadThumbnail(sourceId: String, into entity: ModelEntity, retriesLeft: Int = 12) {
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
                    texturedIds.insert(entity.name)
                }
            } catch {
                log.debug("canvas thumbnail load failed for \(sourceId, privacy: .public)")
                // Fresh imports 404 until their thumbnail generates moments
                // later — retry so the card doesn't stay a placeholder until
                // the next full reconcile.
                // 12 tries ≈ 5 minutes (Daniel: "loads many and then stops",
                // and 3D on a fresh import gave up before derivatives
                // landed) — enough tail for a full import's thumbnail wave.
                if retriesLeft > 0 {
                    try? await Task.sleep(for: .seconds(25))
                    loadThumbnail(sourceId: sourceId, into: entity, retriesLeft: retriesLeft - 1)
                }
            }
        }
    }

    /// Fetch textures for every card that has none — the zoom-in catch-up.
    ///
    /// Called when the detail tier RISES past `.thumbnail`, because cards take
    /// their texture at build time and a reconcile with no changes builds
    /// nothing. Bounded by the same tier gate as `makeCard`, so a zoomed-out
    /// board still issues zero requests.
    func loadMissingThumbnails() {
        for (id, placeable) in placeablesById {
            guard !texturedIds.contains(id),
                  let sourceId = sourceId(of: placeable),
                  let entity = placeablesRoot.findEntity(named: id) as? ModelEntity
            else { continue }
            loadThumbnail(sourceId: sourceId, into: entity)
        }
    }

}
