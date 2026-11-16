import Foundation

/// The app workloads of the performance sweep (`perf-sweep.workload.set`, #6600): W6-W10, each a scripted scenario the Dev Local build
/// runs by itself when `FICHERO_PERF_WORKLOAD` names it, so no XCUITest runner competes for the GUI during an xctrace recording.
/// Test hook only: it answers nil unless the app was launched with `--uitesting`, and `harness.toml [perf.workloads]` declares the
/// same ids. This type selects and names the scenario and its steps; the steps themselves are performed by the view layer's hook.
enum PerfWorkload: String, CaseIterable {
    case launch = "w6"
    case sidebar = "w7"
    case canvasReader = "w8"
    case libraryGrid = "w9"
    case activity = "w10"

    /// The interval or phase names the scenario produces, the ones `InteractionProfile` and `LaunchProfile` already log.
    var phases: [String] {
        switch self {
        case .launch: ["launch-to-engine-ready"]
        case .sidebar: ["sidebar click", "sidebar expand"]
        case .canvasReader: ["preview swipe → image", "preview region press"]
        case .libraryGrid: ["library grid first scroll"]
        case .activity: ["activity table update"]
        }
    }

    /// How many times each scripted action repeats (the spec's fixed counts).
    var repeats: Int {
        switch self {
        case .launch: 1
        case .sidebar: 5 + 3 // five rows clicked, three folders expanded
        case .canvasReader: 10 + 5 // ten page swipes, five region presses
        case .libraryGrid: 200 // cells scrolled through
        case .activity: 200 // rows updating
        }
    }

    static func selected(
        arguments: [String] = ProcessInfo.processInfo.arguments,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> PerfWorkload? {
        guard arguments.contains("--uitesting"),
              let id = environment["FICHERO_PERF_WORKLOAD"] else { return nil }
        return PerfWorkload(rawValue: id.lowercased())
    }
}
