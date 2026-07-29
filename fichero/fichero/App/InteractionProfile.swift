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
        /// A selection that routes somewhere other than the library (chat, a
        /// workflow) never reaches that hook, so its interval is closed by the
        /// next click's `begin` rather than leaking.
        case selectionToContent

        /// The content fetch for a newly selected container — the part that is
        /// legitimately asynchronous. Split out precisely so a slow click can be
        /// attributed to the main thread or to the engine, which #4228 and
        /// #4235 could not tell apart without it.
        case contentDataLoad

        /// Signpost names must be `StaticString` (a dynamic name collapses every
        /// interval into one indistinguishable lane in Instruments), so the
        /// mapping is a switch rather than a raw value.
        fileprivate var signpostName: StaticString {
            switch self {
            case .selectionCommit: return "sidebar selection commit"
            case .selectionToContent: return "sidebar selection → content"
            case .contentDataLoad: return "sidebar content data load"
            }
        }
    }

    private struct OpenInterval {
        let state: OSSignpostIntervalState
        let started: DispatchTime
    }

    @MainActor private static var open: [Phase: OpenInterval] = [:]

    /// Open an interval. A second `begin` for a phase that is still open — the
    /// user clicked again before the last click finished — closes the stale one
    /// as `superseded` rather than leaking it, so the trace keeps one bar per
    /// click instead of one unterminated bar forever.
    @MainActor static func begin(_ phase: Phase, detail: String = "") {
        if open[phase] != nil {
            end(phase, detail: "superseded")
        }
        open[phase] = OpenInterval(
            state: signposter.beginInterval(phase.signpostName, id: signposter.makeSignpostID()),
            started: .now()
        )
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
        logger.info("⏱ \(label, privacy: .public) took \(elapsedMs, format: .fixed(precision: 1))ms")
    }
}
