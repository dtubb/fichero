import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "InteractionProfile")

/// Click and drag timing on the Preview image (`preview.page-click-and-drag-are-timed`, #5253).
///
/// A press opens `InteractionProfile`'s `regionPress` interval, which the region layer and the
/// document overlay lap (dispatch, select, overlay, draw) and which ends after the next render.
/// A drag is summed here instead of logged per move: every move is stamped when the pointer feed
/// receives it and measured again on the main thread's next turn, after the commit that draws it,
/// and the release logs one line with the moves, their average and slowest wait, and the overlay
/// rebuilds that happened in between.
@MainActor
enum PreviewPointerProfile {
    struct Drag {
        let started: UInt64
        var waits: [UInt64] = []
        var overlayBuilds = 0
        var overlayNanos: UInt64 = 0
    }

    private(set) static var drag: Drag?

    private static var now: UInt64 { DispatchTime.now().uptimeNanoseconds }

    /// Every pointer event the feed publishes. Returns the drag line a release logged, if any.
    @discardableResult
    static func pointer(_ phase: PreviewPointerPhase) -> String? {
        switch phase {
        case .pressed:
            InteractionProfile.begin(.regionPress)
            drag = Drag(started: now)
        case .dragged:
            guard drag != nil else { return nil }
            let stamp = now
            DispatchQueue.main.async {
                MainActor.assumeIsolated { drag?.waits.append(now &- stamp) }
            }
        case .released:
            guard let finished = drag else { return nil }
            drag = nil
            guard let line = summary(finished, ended: now) else { return nil }
            logger.info("⏱ preview region drag \(line, privacy: .public)")
            return line
        }
        return nil
    }

    /// The region layer handling one event: a press laps dispatch before it and select after it,
    /// and ends `regionPress` after the render that follows.
    static func handling(_ phase: PreviewPointerPhase, _ handle: () -> Void) {
        guard phase == .pressed else { return handle() }
        InteractionProfile.lap(.regionPress, "dispatch")
        handle()
        InteractionProfile.lap(.regionPress, "select")
        InteractionProfile.endAfterNextRender(.regionPress)
    }

    /// Build the document overlay, counting the build and its time against an open drag.
    static func timingOverlay<Overlay>(_ build: () -> Overlay) -> Overlay {
        let started = now
        defer { overlayBuilt(nanos: now &- started) }
        return build()
    }

    /// The document overlay was rebuilt, taking `nanos`; counted against an open drag.
    static func overlayBuilt(nanos: UInt64) {
        guard drag != nil else { return }
        drag?.overlayBuilds += 1
        drag?.overlayNanos &+= nanos
    }

    /// "took 820.0ms: 46 moves, average 12.0ms, slowest 40.5ms; overlay rebuilt 46 times, 300.0ms";
    /// nil for a press with no move, which is a click and is timed by `regionPress`.
    nonisolated static func summary(_ drag: Drag, ended: UInt64) -> String? {
        guard !drag.waits.isEmpty else { return nil }
        let waits = drag.waits.map { Double($0) / 1_000_000 }
        return String(
            format: "took %.1fms: %d moves, average %.1fms, slowest %.1fms; overlay rebuilt %d times, %.1fms",
            Double(ended &- drag.started) / 1_000_000, waits.count,
            waits.reduce(0, +) / Double(waits.count), waits.max() ?? 0,
            drag.overlayBuilds, Double(drag.overlayNanos) / 1_000_000
        )
    }
}
