import Foundation

// MARK: - Run step records (#4284)
//
// One record per PLANNED step of a run. The server emits N records for N
// planned steps, so a step that ran and produced nothing arrives as a record
// saying exactly that — distinguishable from a step that never ran, which the
// progress timeline alone could only express as an absence.
//
// Collapsing those two is the defect this type exists to prevent: a gap reads
// as "nothing happened" when the truth may be "this ran and found nothing",
// and those demand different responses from the person reading the run.

/// One step of a run: what it was asked to do, what it did, and what it
/// produced. Mirrors the server's `WorkflowRunStepResponse`.
struct WorkflowRunStep: Codable, Identifiable, Equatable {
    let nodeId: String
    let nodeName: String
    let tool: String
    /// Raw server status: `not_run`, `running`, `completed`, `skipped`,
    /// `failed`, `cancelled`. Deliberately the server's own string rather
    /// than a Swift enum: a status added server-side would decode into a
    /// closed enum as either a throw or some neighbouring case, and quietly
    /// showing the wrong state is the failure this whole record set exists
    /// to end. Mapping to something renderable happens once, in
    /// `RunTraceModelBuilder.stepStatus(status:producedNothing:)`.
    let status: String
    let startedAt: String?
    let completedAt: String?
    let durationMs: Double?
    let error: String?
    let skipReason: String?
    /// The step's terminal status came from the RUN ending, not from the step
    /// reporting an outcome of its own.
    let terminatedByRun: Bool?
    let filesTotal: Int?
    let filesSucceeded: Int?
    let filesFailed: Int?
    let artifactCount: Int?
    /// Reached a terminal state having produced no artifact. Read from the
    /// server's own statement, never inferred here from an empty `artifacts`
    /// list — an empty list also means "this step never ran", and telling
    /// those apart is the entire point.
    let producedNothing: Bool?
    let artifacts: [WorkflowRunArtifact]?

    var id: String { nodeId }

    /// True only when the server said so.
    var didProduceNothing: Bool { producedNothing == true }

    /// True when the run ended underneath this step rather than the step
    /// reaching an outcome of its own.
    var wasTerminatedByRun: Bool { terminatedByRun == true }

    enum CodingKeys: String, CodingKey {
        case nodeId = "node_id"
        case nodeName = "node_name"
        case tool
        case status
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case durationMs = "duration_ms"
        case error
        case skipReason = "skip_reason"
        case terminatedByRun = "terminated_by_run"
        case filesTotal = "files_total"
        case filesSucceeded = "files_succeeded"
        case filesFailed = "files_failed"
        case artifactCount = "artifact_count"
        case producedNothing = "produced_nothing"
        case artifacts
    }
}
