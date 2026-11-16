import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "InteractionProfile")

/// Post-launch interaction timing — the sidebar-click counterpart to
/// `LaunchProfile` (#4228).
///
/// It deliberately reuses the SAME subsystem and the `.pointsOfInterest`
/// category, so one Instruments recording shows launch phases and interaction
/// phases on the same Points of Interest track, in one timeline, with no
/// instrument configuration. And, like `LaunchProfile`, every phase is emitted
/// twice: a signpost interval for Instruments and a log line carrying the
/// measured milliseconds, so
///
///     log stream --info --predicate 'subsystem == "app.fichero.fichero"'
///
/// answers "how long did that click take" without launching Instruments at all.
/// A trace you can only read in a GUI profiler is a trace nobody on this project
/// can read from a headless lane.
///
/// The phases are begun and ended in DIFFERENT types — a click is committed in
/// the sidebar and finished in the content column — so the open interval state
/// has to live somewhere shared. That, and only that, is what this enum is.
enum InteractionProfile {
    static let signposter = OSSignposter(
        subsystem: "app.fichero.fichero",
        category: .pointsOfInterest
    )

    /// The three intervals that make up "I clicked a sidebar row and the
    /// content area showed me the thing".
    enum Phase: Hashable {
        /// The AppKit click landing in the `List` selection binding through to
        /// the routed `sidebarMode`/`viewMode` write. This is pure synchronous
        /// main-thread work: whatever is in here is latency the user feels
        /// before anything on screen can possibly change.
        case selectionCommit

        /// Selection committed → the content column has been rebuilt for it.
        ///
        /// Ends on `LibraryView`'s `task(id: folderId)`, which runs after the
        /// view update that carried the new folder id. Read the bar as "SwiftUI
        /// finished rebuilding the content column", NOT as a CoreAnimation
        /// commit — and read the `contentDataLoad` bar beside it for the fetch.
        /// A selection that routes somewhere other than a document (Trash, chat,
        /// a workflow) never reaches that hook, so it opens no interval
        /// (`selectionReachesContentHook`).
        case selectionToContent

        /// The content fetch for a newly selected container — the part that is
        /// legitimately asynchronous. Split out precisely so a slow click can be
        /// attributed to the main thread or to the engine, which #4228 and
        /// #4235 could not tell apart without it.
        case contentDataLoad

        /// A chevron click on a sidebar folder → its child rows are drawn. Laps split it into the
        /// child fetch, the wait for the sidebar observer, `SidebarItemBuilder`'s rebuild, the
        /// reindex and the render after it, so a slow expand names its slow part.
        case sidebarExpand

        /// A Preview swipe (or ←/→) to the neighbouring item → the Preview's canvas holds that
        /// item's image (#5462). Begun by `SiblingStep.commit`, ended where the display canvas
        /// publishes the image, so the bar is the whole wait the user sees.
        case siblingStepToImage

        /// A press on the Preview image → the frame that shows what it did (#5253). Begun by
        /// `PreviewPointerProfile` as the pointer feed receives the mouse-down; lapped by the region
        /// layer (dispatch, select) and the document overlay (overlay, draw).
        case regionPress

        /// Signpost names must be `StaticString` (a dynamic name collapses every
        /// interval into one indistinguishable lane in Instruments), so the
        /// mapping is a switch rather than a raw value.
        fileprivate var signpostName: StaticString {
            switch self {
            case .selectionCommit: return "sidebar selection commit"
            case .selectionToContent: return "sidebar selection → content"
            case .contentDataLoad: return "sidebar content data load"
            case .sidebarExpand: return "sidebar expand"
            case .siblingStepToImage: return "preview swipe → image"
            case .regionPress: return "preview region press"
            }
        }
    }

    /// One step inside an interval: its name and the uptime (nanoseconds) at which it ended.
    struct Lap: Equatable {
        let name: String
        let endedAt: UInt64
    }

    private struct OpenInterval {
        let state: OSSignpostIntervalState
        let started: DispatchTime
        /// Tells this interval from a later one of the same phase, for `endAfterNextRender`.
        let token: UInt64
        var laps: [Lap] = []
    }

    @MainActor private static var open: [Phase: OpenInterval] = [:]
    @MainActor private static var nextToken: UInt64 = 0

    /// Whether a selection's content column closes `selectionToContent`. Only a document
    /// destination reaches `LibraryView`'s `task(id: folderId)`; Trash, chat, a workflow and the
    /// rest never do, and an interval opened for them stayed open until the next click, which
    /// logged it as a click that took as long as the user had waited (a false 40 s on Trash).
    static func selectionReachesContentHook(_ destination: SidebarDestination) -> Bool {
        if case .document = destination { return true }
        return false
    }

    /// Each lap's own duration, in order: "fetch 812.0ms · splice 0.4ms". A lap is measured
    /// from the one before it (the first from the interval's start), and empty laps give "".
    static func lapBreakdown(started: UInt64, laps: [Lap]) -> String {
        var previous = started
        return laps.map { lap in
            let milliseconds = Double(lap.endedAt &- previous) / 1_000_000
            previous = lap.endedAt
            return "\(lap.name) \(String(format: "%.1f", milliseconds))ms"
        }
        .joined(separator: " · ")
    }

    /// Open an interval. A second `begin` for a phase that is still open — the
    /// user clicked again before the last click finished — closes the stale one
    /// as `superseded` rather than leaking it, so the trace keeps one bar per
    /// click instead of one unterminated bar forever.
    ///
    /// A superseded interval never reached its end point, so its line says that instead of
    /// "took": the time it shows is how long the user waited before clicking again, not how
    /// long the work took.
    @MainActor static func begin(_ phase: Phase, detail: String = "") {
        if let stale = open.removeValue(forKey: phase) {
            signposter.endInterval(phase.signpostName, stale.state, "superseded")
            let name = phase.signpostName.description
            let waitedMs = Double(DispatchTime.now().uptimeNanoseconds &- stale.started.uptimeNanoseconds) / 1_000_000
            logger.info(
                "⏱ \(name, privacy: .public) never reached its end point (superseded after \(waitedMs, format: .fixed(precision: 1))ms)"
            )
        }
        nextToken &+= 1
        open[phase] = OpenInterval(
            state: signposter.beginInterval(phase.signpostName, id: signposter.makeSignpostID()),
            started: .now(),
            token: nextToken
        )
    }

    /// Mark the end of one step inside an open interval; `end` prints each step's time. A no-op
    /// when the phase is not open, like `end`.
    @MainActor static func lap(_ phase: Phase, _ step: String) {
        guard open[phase] != nil else { return }
        open[phase]?.laps.append(Lap(name: step, endedAt: DispatchTime.now().uptimeNanoseconds))
    }

    /// End the interval once the main thread has taken its next turn, with a last lap named
    /// "render". A state change made now is drawn when this run-loop turn ends (SwiftUI and Core
    /// Animation commit before the run loop waits), and a block queued on the main queue now runs
    /// in the next turn, after that commit. If the phase has been begun again by then, the newer
    /// interval is left alone.
    @MainActor static func endAfterNextRender(_ phase: Phase, detail: String = "") {
        guard let token = open[phase]?.token else { return }
        DispatchQueue.main.async {
            MainActor.assumeIsolated {
                guard open[phase]?.token == token else { return }
                lap(phase, "render")
                end(phase, detail: detail)
            }
        }
    }

    /// Close an interval. Ending a phase that was never begun is a silent no-op:
    /// the end points are view-lifecycle callbacks that also fire for selections
    /// this profile never opened (a restored selection, a programmatic
    /// navigation), and those are not measurement failures.
    @MainActor static func end(_ phase: Phase, detail: String = "") {
        guard let interval = open.removeValue(forKey: phase) else { return }
        signposter.endInterval(phase.signpostName, interval.state, "\(detail, privacy: .public)")
        let elapsedMs =
            Double(DispatchTime.now().uptimeNanoseconds &- interval.started.uptimeNanoseconds)
            / 1_000_000
        let name = phase.signpostName.description
        let label = detail.isEmpty ? name : "\(name) (\(detail))"
        let breakdown = lapBreakdown(started: interval.started.uptimeNanoseconds, laps: interval.laps)
        let steps = breakdown.isEmpty ? "" : ": \(breakdown)"
        logger.info("⏱ \(label, privacy: .public) took \(elapsedMs, format: .fixed(precision: 1))ms\(steps, privacy: .public)")
    }
}
