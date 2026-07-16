import Darwin
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "LaunchProfile")

/// The launch timeline (#3946): every milestone says what happened and how long
/// since the process started, so one command tells the whole story in order:
///
///     log stream --info --predicate 'subsystem == "app.fichero.fichero"'
///
/// The markers this replaces logged "entry" / "services ready" with no number,
/// so a launch could be read as a sequence but never as a cost.
///
/// **The epoch is the kernel's process-start time, not our first line of Swift.**
/// That distinction is the whole first interval: "app start → AppState.init" is
/// dyld, static init, and everything before our code runs. Measured from our own
/// first line it would report as ~0ms and hide itself.
enum LaunchProfile {
    /// Process start, from `KERN_PROC_PID`. Falls back to first touch — which
    /// makes the first interval read ~0 instead of negative or absurd — and says
    /// so loudly, because a launch profile that quietly measures the wrong thing
    /// is worse than none.
    static let epoch: Date = {
        if let start = processStartDate() { return start }
        logger.warning("⏱ launch epoch unavailable — times are from first touch, NOT process start")
        return Date()
    }()

    /// Milliseconds since the process started.
    static var elapsedMs: Double { Date().timeIntervalSince(epoch) * 1000 }

    /// Record a launch milestone on the absolute timeline.
    ///
    /// Milestones are absolute (since process start) rather than durations: the
    /// question a launch profile has to answer is "where did the 23 seconds go",
    /// which needs one ordered timeline, not a scatter of independent stopwatches.
    /// Phase durations are then just the gaps between two milestones.
    static func milestone(_ name: String) {
        logger.info("⏱ \(name, privacy: .public) @ \(elapsedMs, format: .fixed(precision: 1))ms")
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
