import Foundation

/// A workflow run launched from the bar and now executing on its own, tracked
/// in Activity (Daniel, 2026-09-07: "it stays in activity. not queued behind
/// vision. it can run in parallel. it lets us do one thing, then try the
/// next").
///
/// The bar DETACHES a run the instant it launches: the run keeps executing
/// concurrently with any others — Apple Vision AND Google at the same time —
/// each on the steps, scope and framing frozen at ▶-press, so a run acts on
/// what was selected when it was launched, never on whatever the selection has
/// wandered to since. Steps/scope/context are kept for the record and for a
/// re-launch; the live execution is the engine's, watched through Activity.
struct ActiveWorkflowRun: Identifiable, Equatable {
    let id: UUID
    /// The chain this run executes, in order, with each step's own model pin.
    var steps: [StagedWorkflowStep]
    /// What the run acts on, resolved and frozen at ▶-press.
    var scope: WorkflowBarPolicy.RunScope
    /// The run's user framing ("this is a historical diary"), frozen.
    var userContext: String
    /// A short name for the "N running" indicator — read from the steps so the
    /// strip can name the run without opening Activity.
    var title: String

    init(
        id: UUID = UUID(),
        steps: [StagedWorkflowStep],
        scope: WorkflowBarPolicy.RunScope,
        userContext: String
    ) {
        self.id = id
        self.steps = steps
        self.scope = scope
        self.userContext = userContext
        self.title = ActiveWorkflowRun.makeTitle(for: steps)
    }

    /// The run's name: its only step's, or the first step plus a count so a
    /// three-step chain reads as "Transcribe +2" rather than just its head.
    static func makeTitle(for steps: [StagedWorkflowStep]) -> String {
        guard let first = steps.first else { return "Empty run" }
        if steps.count == 1 { return first.displayName }
        return "\(first.displayName) +\(steps.count - 1)"
    }
}

/// The runs launched from the bar that are still executing — the bar's view of
/// what Activity is running, so it can show "N running" and know it is no longer
/// idle (Daniel, 2026-09-07). PARALLEL, not a queue: a run is registered the
/// instant it launches and executes concurrently with every other registered
/// run; none waits behind another, and finishing one leaves the rest untouched.
///
/// A pure value type with no SwiftUI, Tasks or engine calls, so the invariant
/// that matters — launch registers, several run at once independently, and a
/// finish (in any order) removes only that run — is tested without a window.
/// The host (ContentView) owns the Tasks and the Activity wiring; this type
/// owns only the set and its order of arrival.
struct WorkflowRunRegistry: Equatable {
    private(set) var runs: [ActiveWorkflowRun] = []

    var isEmpty: Bool { runs.isEmpty }
    /// How many runs are executing concurrently, for the "N running" chip.
    var count: Int { runs.count }

    /// A representative title for the compact status — the most RECENT launch,
    /// which is what "N running" collapses to when only one is left. nil when
    /// nothing is running.
    var latestTitle: String? { runs.last?.title }

    /// Record a run as it launches. Order is arrival order (newest last), so
    /// `latestTitle` names the run just launched.
    mutating func register(_ run: ActiveWorkflowRun) {
        runs.append(run)
    }

    /// Drop a run when it settles — completed, failed or stopped. Removes only
    /// that run; every other concurrent run keeps executing. Unknown ids are a
    /// no-op (a double-finish must not disturb the rest).
    mutating func finish(_ id: UUID) {
        runs.removeAll { $0.id == id }
    }

    func run(_ id: UUID) -> ActiveWorkflowRun? {
        runs.first { $0.id == id }
    }
}
