import RealityKit
import SwiftUI

// MARK: - Page-thumbnail textures (split for file_length, 2026-08-20)

extension CanvasScene3DRenderer {
    func reskinCard(_ id: String) {
        guard let placeable = placeablesById[id] else { return }
        // The rebuilt entity starts flat; the reload below re-adds it.
        texturedIds.remove(id)
        placeablesRoot.findEntity(named: id)?.removeFromParent()
        let card = makeCard(placeable)
        // A rebuilt card is a NEW entity, so it carries none of the old one's
        // components — without this, a card that reskins mid-search (its
        // thumbnail landing, a resize) would come back at full strength while
        // its dimmed neighbours stayed dim.
        CanvasEmphasisPainter.apply(emphasis, to: card, id: id)
        placeablesRoot.addChild(card)
        // S12 (2026-08-23): the FIRST texture triggers an aspect-reskin, and
        // the rebuilt card starts flat — but makeCard only fetches at
        // thumbnail tier, so after fit() zoomed out to .glyph the texture
        // was thrown away and `texturedIds` forgot it ("textures absent on
        // first render, appear after zoom"). A known aspect PROVES a texture
        // was measured (it's in the cache), so hand it back to the rebuilt
        // card regardless of tier — the reload is a cache hit.
        if let src = sourceId(of: placeable),
           CanvasCardGeometry.knownAspect(forSourceId: src) != nil {
            loadThumbnail(sourceId: src, into: card)
        }
    }

    func loadThumbnail(sourceId: String, into entity: ModelEntity, retriesLeft: Int = 12) {
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
                    texturedIds.insert(entity.name)
                }
            } catch {
                // Say WHY (perf audit 2026-08-19: 1,500 silent failures in
                // 16s made 'no thumbnails' undiagnosable) — and retry once:
                // fresh imports 404 until the derivative stage lands them.
                log.error(
                    "space thumbnail load failed for \(sourceId, privacy: .public): \(error.localizedDescription)"
                )
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

    /// The page-image source id for a source-node placeable, nil otherwise.
    func sourceId(of placeable: CanvasPlaceable) -> String? {
        guard case .node(let node) = placeable.content,
              node.nodeType == .source,
              let sourceId = node.sourceId, !sourceId.isEmpty else { return nil }
        return sourceId
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
