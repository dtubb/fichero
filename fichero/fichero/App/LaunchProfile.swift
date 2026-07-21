import Darwin
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "LaunchProfile")

/// The launch timeline (#3946), emitted twice for two different readers:
///
/// **A log line, for `log stream`** — every milestone carries elapsed-since-
/// process-start, so one command answers "where did the 23 seconds go", and a
/// phase duration is just the gap between two lines:
///
///     log stream --info --predicate 'subsystem == "app.fichero.fichero"'
///
/// **A signpost, for Instruments** — because a log line cannot be a trace.
/// Signposts nest, carry real intervals, and Instruments renders them natively:
/// the `.pointsOfInterest` category lands on the Points of Interest track in
/// EVERY template (Time Profiler included) with no configuration, so a launch
/// shows up as labelled bars above the sampled stacks rather than as text you
/// have to correlate by hand.
///
/// **The epoch is the kernel's process-start time**, not our first line of Swift.
/// That distinction is the entire first interval: "app start → AppState.init" is
/// dyld + static init + everything before our code, and measuring it from our own
/// first line would report it as ~0ms and hide it.
enum LaunchProfile {
    /// `.pointsOfInterest` is what makes these show up without configuring an
    /// os_signpost instrument by hand.
    static let signposter = OSSignposter(
        subsystem: "app.fichero.fichero",
        category: .pointsOfInterest
    )

    /// Process start, from `KERN_PROC_PID`. Falls back to first touch — which
    /// makes the first interval read ~0 instead of absurd — and says so loudly,
    /// because a profile that quietly measures the wrong thing is worse than none.
    static let epoch: Date = {
        if let start = processStartDate() { return start }
        logger.warning("⏱ launch epoch unavailable — times are from first touch, NOT process start")
        return Date()
    }()

    /// Milliseconds since the process started.
    static var elapsedMs: Double { Date().timeIntervalSince(epoch) * 1000 }

    /// Record a launch milestone: one line on the absolute timeline, one signpost
    /// event for Instruments.
    ///
    /// Milestones are absolute rather than durations because the question is
    /// "where did the time go", which needs one ordered timeline, not a scatter of
    /// independent stopwatches. The signpost carries no elapsed value — Instruments
    /// timestamps it, which is the whole point of using signposts over log lines.
    ///
    /// `name` is a `StaticString` so it can be the signpost's real name (varying
    /// data goes in `detail`); a dynamic name would collapse every milestone into
    /// one indistinguishable lane in Instruments.
    static func milestone(_ name: StaticString, detail: String = "") {
        let label = detail.isEmpty ? name.description : "\(name.description) (\(detail))"
        logger.info("⏱ \(label, privacy: .public) @ \(elapsedMs, format: .fixed(precision: 1))ms")
        signposter.emitEvent(name, id: .exclusive, "\(detail, privacy: .public)")
        emitToStderrIfProfiling(label)
    }

    /// Also print the milestone to stderr when `FICHERO_LAUNCH_PROFILE_STDOUT=1`.
    /// The os_log timeline is invisible to a headless launcher (a shell can't read
    /// another process's unified log without TCC), so this makes the launch
    /// timeline capturable by `nohup app 2>timeline.log` for CI/headless startup
    /// measurement. Off by default; zero cost in normal runs.
    private static let profileToStderr =
        ProcessInfo.processInfo.environment["FICHERO_LAUNCH_PROFILE_STDOUT"] == "1"
    private static func emitToStderrIfProfiling(_ label: String) {
        guard profileToStderr else { return }
        FileHandle.standardError.write(
            Data("⏱ \(label) @ \(String(format: "%.1f", elapsedMs))ms\n".utf8)
        )
    }

    /// Open a signpost interval for a launch phase. The caller holds the returned
    /// state and closes it with `endPhase` — usually via `defer`, so a phase that
    /// throws still renders as a bar that ends where it failed.
    static func beginPhase(_ name: StaticString) -> OSSignpostIntervalState {
        signposter.beginInterval(name, id: signposter.makeSignpostID())
    }

    static func endPhase(_ name: StaticString, _ state: OSSignpostIntervalState) {
        signposter.endInterval(name, state)
    }

    // MARK: - The whole-launch interval

    /// The one interval whose ends live in different types — `AppState.init` opens
    /// it, `ContentView`'s first frame closes it — so it cannot be a local `defer`
    /// and needs exactly this much state.
    ///
    /// It starts at the earliest code we own, NOT at process start: a signpost
    /// cannot be emitted retroactively. The pre-main run-up is what the log line's
    /// elapsed value covers, and what Instruments' App Launch template already
    /// measures on its own.
    @MainActor private static var launchState: OSSignpostIntervalState?

    @MainActor static func beginLaunch() {
        guard launchState == nil else { return }
        launchState = beginPhase("launch")
    }

    /// Idempotent: only the FIRST frame closes the launch. `onAppear` fires again
    /// on later re-appearances, and re-closing would either crash or draw a
    /// nonsense bar across the whole session.
    @MainActor static func endLaunch() {
        guard let state = launchState else { return }
        launchState = nil
        endPhase("launch", state)
    }

    /// The kernel's start time for this process. Reading our OWN pid is permitted
    /// under the App Sandbox, so this works in every channel.
    private static func processStartDate() -> Date? {
        var info = kinfo_proc()
        var size = MemoryLayout<kinfo_proc>.stride
        var mib: [Int32] = [CTL_KERN, KERN_PROC, KERN_PROC_PID, getpid()]
        guard sysctl(&mib, u_int(mib.count), &info, &size, nil, 0) == 0 else { return nil }
        let started = info.kp_proc.p_starttime
        guard started.tv_sec > 0 else { return nil }
        return Date(
            timeIntervalSince1970: TimeInterval(started.tv_sec)
                + TimeInterval(started.tv_usec) / 1_000_000
        )
    }
}
