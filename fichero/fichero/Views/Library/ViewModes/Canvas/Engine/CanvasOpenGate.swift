import Foundation
#if canImport(RealityKit)
import RealityKit
#endif

// MARK: - A canvas opens settled (#5629, `library.canvas.cards-move-only-when-asked`)

/// What a canvas waits for before it draws its first card, shared by the 2D and 3D canvases.
///
/// Why it waits: the canvas used to draw on the first frame, before its scope's saved places and
/// items had loaded and before any page's shape was known. It drew the default grid, then the saved
/// places arrived and every card slid to its real place (an animated move, because many cards moved
/// at once), then page shapes landed, the grid's spacing widened and the board re-flowed again with
/// the camera re-fitting behind it. Waiting for those inputs is what lets the first frame be the
/// settled one.
@MainActor
enum CanvasOpenGate {
    /// At most this many pages have their shape fetched before the board opens: enough to cover
    /// the cards a fitted first frame shows, few enough that a box of thousands opens promptly.
    static let aspectPrefetchLimit = 120
    /// The longest the board waits for page shapes; past it the board opens with what it has.
    static let aspectPrefetchDeadline: Duration = .milliseconds(1500)
    /// The longest the board waits for a load another view already started for the same scope.
    static let storeLoadDeadline: Duration = .seconds(3)

    /// Whether a canvas may draw its scope: the scope has settled and the pane has a size.
    nonisolated static func mayDraw(settledScope: String?, scope: String, viewport: CGSize) -> Bool {
        settledScope == scope && viewport.width > 0 && viewport.height > 0
    }

    /// The source ids whose page shape is not known yet, in board order, at most `limit`.
    static func sourceIdsNeedingAspects(_ sourceIds: [String], limit: Int = aspectPrefetchLimit) -> [String] {
        var seen: Set<String> = []
        var wanted: [String] = []
        for sourceId in sourceIds where !sourceId.isEmpty && CanvasCardGeometry.knownAspect(forSourceId: sourceId) == nil {
            guard wanted.count < limit else { break }
            if seen.insert(sourceId).inserted { wanted.append(sourceId) }
        }
        return wanted
    }

    /// Wait until `condition` holds, the deadline passes, or the task is cancelled.
    static func wait(until condition: () -> Bool, deadline: Duration) async {
        let clock = ContinuousClock()
        let end = clock.now.advanced(by: deadline)
        while !condition(), clock.now < end, !Task.isCancelled {
            try? await Task.sleep(for: .milliseconds(30))
        }
    }

    /// Learn the page shapes of the first cards before the board opens, so the grid is laid out on
    /// their real spacing and no card changes shape on screen. Fetches go through the same texture
    /// cache the cards load from, so the cards then draw from the cache.
    static func prefetchAspects(forSourceIds sourceIds: [String], using storage: StorageService?) async {
        #if canImport(RealityKit)
        let wanted = sourceIdsNeedingAspects(sourceIds)
        guard !wanted.isEmpty else { return }
        final class Remaining { var left = 0 }
        let remaining = Remaining()
        remaining.left = wanted.count
        for sourceId in wanted {
            Task { @MainActor in
                defer { remaining.left -= 1 }
                guard let texture = try? await SpaceTextureCache.shared.texture(forSourceId: sourceId, using: storage) else { return }
                CanvasCardGeometry.recordAspect(of: texture, forSourceId: sourceId)
            }
        }
        await wait(until: { remaining.left <= 0 }, deadline: aspectPrefetchDeadline)
        #endif
    }
}
