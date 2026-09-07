import Foundation

/// A chain the user composed and launched while another run was still
/// executing, frozen at the moment they pressed ▶ (Daniel, 2026-09-07: "start a
/// run and compose the next thing, e.g. do Apple Vision, then do Google").
///
/// Steps, scope and the user's framing are captured HERE rather than read at
/// drain time, so a queued run acts on what was selected when it was launched —
/// not on whatever the selection has wandered to by the time the run ahead of
/// it finishes. This is the same freeze `runStagedChain` makes for the live
/// run; the queue simply keeps it until its turn.
struct QueuedWorkflowRun: Identifiable, Equatable {
    let id: UUID
    /// The chain to run, in order, with each step's own model pin.
    var steps: [StagedWorkflowStep]
    /// What the run acts on, resolved and frozen at ▶-press.
    var scope: WorkflowBarPolicy.RunScope
    /// The run's user framing ("this is a historical diary"), frozen so a
    /// detached run carries the context it was launched with rather than one
    /// the window may have edited since.
    var userContext: String
    /// A short label for the "N queued" / next-up indicator — read from the
    /// steps so the strip can name the run without opening Activity.
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
        self.title = QueuedWorkflowRun.makeTitle(for: steps)
    }

    /// The run's name: its only step's, or the first step plus a count so a
    /// three-step chain reads as "Transcribe +2" rather than just its head.
    static func makeTitle(for steps: [StagedWorkflowStep]) -> String {
        guard let first = steps.first else { return "Empty run" }
        if steps.count == 1 { return first.displayName }
        return "\(first.displayName) +\(steps.count - 1)"
    }
}

/// The FIFO of runs waiting behind the one currently executing in the workflow
/// bar — the queue that makes "Apple Vision THEN Google" possible (Daniel,
/// 2026-09-07).
///
/// A pure value type with no SwiftUI and no engine calls, so the behavior that
/// matters — enqueue while a run is executing, drain in the order launched,
/// and an empty queue leaving the single-run path untouched — is tested without
/// a window. The host (ContentView) owns starting the runs; this type only owns
/// their order.
struct WorkflowRunQueue: Equatable {
    private(set) var pending: [QueuedWorkflowRun] = []

    var isEmpty: Bool { pending.isEmpty }
    var count: Int { pending.count }

    /// The label of the run that will start next, for the compact "next up"
    /// indicator. nil when nothing is queued.
    var nextTitle: String? { pending.first?.title }

    /// Add a run to the back of the queue — launched later means runs later.
    mutating func enqueue(_ run: QueuedWorkflowRun) {
        pending.append(run)
    }

    /// Take the next run to start, removing it, or nil once the queue has
    /// drained. FIFO: the run launched first comes out first.
    mutating func dequeue() -> QueuedWorkflowRun? {
        pending.isEmpty ? nil : pending.removeFirst()
    }

    /// Drop a still-pending run — its "remove from queue" affordance. A run
    /// already dequeued and executing is halted through the run controls
    /// (Stop / Activity), never here; this only touches what has not started.
    mutating func remove(_ id: UUID) {
        pending.removeAll { $0.id == id }
    }

    /// Discard every pending run without starting any — the queue's own Clear,
    /// for abandoning a backlog the user no longer wants. Leaves the executing
    /// run alone.
    mutating func clear() {
        pending.removeAll()
    }
}
