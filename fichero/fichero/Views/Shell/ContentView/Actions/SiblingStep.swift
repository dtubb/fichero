import Foundation

/// A Preview swipe (or ←/→) to the neighbouring item (#5462).
///
/// The neighbour shows AT ONCE when the image it will display is already in memory: the step
/// commits in the same turn as the swipe, with no engine round-trip between them. Only a
/// neighbour whose image is not in memory yet holds the step, for at most `holdCap`, so the page
/// and the selection still land together instead of on the skeleton.
///
/// What made each swipe slow (measured through the real stores, `SiblingStepTests`): the
/// neighbours were warmed with the BASE display image, but the canvas shows the PREFERRED
/// rendition (background removed, enhanced, edited) and asks for the page's rendition list and
/// edit chain first. So every swipe found its neighbour cold and paid the list, the edit chain and
/// the rendition's bytes, one after another, before anything changed — and the 140 ms cap did not
/// cap: it raced the warm in a task group, which waits for every child, so the step waited for the
/// whole warm. And a swipe during a hold stepped from the item still shown, so it went nowhere.
@MainActor
final class SiblingStep {
    /// The longest a step waits for its image before committing anyway: navigation must never
    /// feel stuck, and a cold page then loads in place (the canvas keeps the previous image up).
    static let holdCap: Duration = .milliseconds(140)

    /// A step decided but not shown yet, because its image is still being fetched.
    private(set) var pending: Document?
    private var hold: Task<Void, Never>?
    private var prefetch: Task<Void, Never>?

    /// Step to `target`. Shows it now when its image is in memory, else after the warm (≤ `holdCap`);
    /// then warms `neighbours` the same way, so the next swipe finds its image in memory.
    /// The previous step's hold and neighbour warm are cancelled: they are for an item left behind.
    func commit(
        to target: Document,
        neighbours: [String],
        storage: StorageService,
        renditions: RenditionService?,
        show: @escaping (Document) -> Void
    ) {
        hold?.cancel()
        prefetch?.cancel()
        InteractionProfile.begin(.siblingStepToImage, detail: target.id)
        let landed: (Document) -> Void = { [weak self] doc in
            show(doc)
            self?.prefetch = Task { await Self.warm(neighbours, storage: storage, renditions: renditions) }
        }
        if Self.isWarm(target.id, storage: storage, renditions: renditions) {
            pending = nil
            landed(target)
            return
        }
        pending = target
        // Whichever comes first lands the step: the warm finishing, or the cap. Both are guarded by
        // `pending`, so a step lands once, and never after a newer swipe replaced or flushed it.
        // (Before #5462 the cap raced the warm inside a task group, which waits for EVERY child: the
        // warm's `value` ignores cancellation, so the "140 ms cap" waited for the whole warm.)
        let land: () -> Void = { [weak self] in
            guard let self, self.pending?.id == target.id else { return }
            self.pending = nil
            landed(target)
        }
        // The warm is not cancelled by a newer swipe: the canvas joins the same fetch through the
        // services' coalescing, so aborting it would only make the canvas start it again.
        Task {
            await Self.warm(target.id, storage: storage, renditions: renditions)
            land()
        }
        hold = Task {
            try? await Task.sleep(for: Self.holdCap)
            guard !Task.isCancelled else { return }
            land()
        }
    }

    /// A new swipe during a hold: show the held step NOW, so the new one steps from it rather than
    /// from the item still on screen (which turned two quick swipes into one).
    func flush(show: (Document) -> Void) {
        guard let held = pending else { return }
        hold?.cancel()
        pending = nil
        show(held)
    }

    /// The image the canvas will show for `documentId` is in memory: the rendition list, and the
    /// preferred rendition's bytes (or the base display image when the engine's primary is preferred).
    /// The same choice as `StorageDisplayImageCanvas.loadImageOnce`, so warm means no fetch there.
    static func isWarm(_ documentId: String, storage: StorageService, renditions: RenditionService?) -> Bool {
        #if os(macOS)
        if let renditions {
            guard renditions.renditionsByDocument[documentId] != nil else { return false }
            if let preferred = preferredFlipTarget(documentId, renditions: renditions) {
                return renditions.hasContent(renditionId: preferred.id)
            }
        }
        #endif
        return storage.cachedDisplayPlatformImage(for: documentId) != nil
    }

    /// Fetch what the canvas will show for `documentId` (see `isWarm`). Best-effort: a failure
    /// only means the canvas fetches it itself.
    static func warm(_ documentId: String, storage: StorageService, renditions: RenditionService?) async {
        #if os(macOS)
        if let renditions {
            await renditions.load(documentId: documentId)
            if let preferred = preferredFlipTarget(documentId, renditions: renditions) {
                _ = try? await renditions.contentData(documentId: documentId, renditionId: preferred.id)
                return
            }
        }
        #endif
        _ = try? await storage.getDisplayPlatformImage(documentId)
    }

    /// Warm several items, nearest first (the caller orders them), two at a time.
    static func warm(_ documentIds: [String], storage: StorageService, renditions: RenditionService?) async {
        var queue = documentIds[...]
        while !queue.isEmpty, !Task.isCancelled {
            let batch = queue.prefix(2)
            queue = queue.dropFirst(2)
            await withTaskGroup(of: Void.self) { group in
                for id in batch {
                    group.addTask { await warm(id, storage: storage, renditions: renditions) }
                }
            }
        }
    }

    #if os(macOS)
    /// The rendition the canvas lands on when it is not the engine's primary (index 0, which the
    /// cheaper, cached base display image serves). Nil when the base display is what shows.
    private static func preferredFlipTarget(_ documentId: String, renditions: RenditionService) -> DocumentRendition? {
        let displayable = renditions.displayable(documentId: documentId)
        let sticky = EngineConfig.defaults.string(forKey: ZoomableImagePreview.stickyRenditionRoleKey)
        let preferred = preferredRenditionIndex(in: displayable, stickyRole: sticky)
        guard preferred != 0, displayable.indices.contains(preferred) else { return nil }
        return displayable[preferred]
    }
    #endif
}
