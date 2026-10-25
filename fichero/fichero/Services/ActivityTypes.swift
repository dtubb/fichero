import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// MARK: - Activity Types
// Shared types used by ActivityService and views

/// Wrapper to decode any JSON value as String
struct AnyValueAsString: Codable, Hashable {
    let value: String

    init(_ stringValue: String) {
        self.value = stringValue
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let string = try? container.decode(String.self) {
            value = string
        } else if let int = try? container.decode(Int.self) {
            value = String(int)
        } else if let double = try? container.decode(Double.self) {
            value = String(double)
        } else if let bool = try? container.decode(Bool.self) {
            value = String(bool)
        } else {
            value = ""
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(value)
    }
}

typealias ActivityItem = Components.Schemas.ActivityResponse

// The hand-rolled ActivityItem was Identifiable (id: String); the generated
// schema has the same `id`, so opt it into Identifiable for ForEach (#1702).
extension Components.Schemas.ActivityResponse: @retroactive Identifiable {}

extension Components.Schemas.ActivityResponse {
    var type: String { _type }

    /// Metadata with all values as strings. Named distinctly from the generated
    /// `metadata` (a `MetadataPayload?`) to avoid shadowing it (#1702).
    var metadataStrings: [String: String]? {
        guard let metadata else { return nil }
        let converted = metadata.additionalProperties.value.mapValues { value -> String in
            if let string = value as? String {
                return string
            }
            // #4024: Bool BEFORE NSNumber — a bridged Bool IS an NSNumber (__NSCFBoolean),
            // so testing NSNumber first rendered `true` as "1".
            if let bool = value as? Bool {
                return String(bool)
            }
            if let number = value as? NSNumber {
                return number.stringValue
            }
            return String(describing: value)
        }
        return converted.isEmpty ? nil : converted
    }

    init(
        id: String,
        type: String,
        level: String,
        timestamp: String,
        message: String,
        workflowId: String? = nil,
        batchId: String? = nil,
        threadId: String? = nil,
        nodeId: String? = nil,
        metadataRaw: [String: AnyValueAsString]? = nil,
        durationMs: Double? = nil,
        error: String? = nil
    ) {
        let metadataPayload = metadataRaw.map { raw -> Components.Schemas.ActivityResponse.MetadataPayload in
            let object = (try? OpenAPIObjectContainer(unvalidatedValue: raw.mapValues(\.value))) ?? .init()
            return .init(additionalProperties: object)
        }
        self.init(
            id: id,
            _type: type,
            level: level,
            timestamp: timestamp,
            message: message,
            workflowId: workflowId,
            batchId: batchId,
            threadId: threadId,
            nodeId: nodeId,
            metadata: metadataPayload,
            durationMs: durationMs,
            error: error
        )
    }

    var parsedTimestamp: Date? {
        let isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = isoFormatter.date(from: timestamp) {
            return date
        }
        isoFormatter.formatOptions = [.withInternetDateTime]
        if let date = isoFormatter.date(from: timestamp) {
            return date
        }

        let dateFormatter = DateFormatter()
        dateFormatter.locale = Locale(identifier: "en_US_POSIX")
        dateFormatter.timeZone = .current

        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        if let date = dateFormatter.date(from: timestamp) {
            return date
        }

        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
        if let date = dateFormatter.date(from: timestamp) {
            return date
        }

        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return dateFormatter.date(from: timestamp)
    }

    var levelColor: String {
        switch level {
        case "error", "critical": return "red"
        case "warning": return "orange"
        case "info": return "blue"
        case "debug": return "gray"
        default: return "primary"
        }
    }

    var typeIcon: String {
        switch type {
        case "workflow_started": return "play.circle"
        case "workflow_completed": return "checkmark.circle"
        case "workflow_failed": return "xmark.circle"
        case "workflow_paused": return "pause.circle"
        case "workflow_resumed": return "play.circle"
        case "workflow_cancelled": return "stop.circle"
        case "node_started": return "circle.dashed"
        case "node_completed": return "circle.fill"
        case "node_failed": return "exclamationmark.circle"
        case "batch_started": return "square.stack.3d.up"
        case "batch_completed": return "square.stack.3d.up.fill"
        case "batch_item_completed": return "checkmark.square"
        case "batch_item_failed": return "xmark.square"
        default: return "circle"
        }
    }

    var name: String {
        let displayMessage = message.prefix(40)
        return displayMessage.isEmpty ? type : String(displayMessage) + (message.count > 40 ? "..." : "")
    }

    var statusIcon: String { typeIcon }

    var status: String {
        switch type {
        case "workflow_started", "node_started", "batch_started": return "running"
        case "workflow_completed", "node_completed", "batch_completed", "batch_item_completed": return "completed"
        case "workflow_failed", "node_failed", "batch_item_failed": return "failed"
        case "workflow_paused": return "paused"
        case "workflow_cancelled": return "cancelled"
        default: return level
        }
    }
}

// MARK: - Background jobs (#user-machine-always-useful FIX 2)

/// One live background job as the Activity surfaces render it.
///
/// Maps the generated `BackgroundJob` schema (`GET /api/activity/jobs`) into a
/// small app value with a typed `state`, so BOTH the toolbar Activity popover
/// and the full Activity viewer read ONE type from ONE source and cannot
/// disagree about what is running — or whether it FAILED (a failed Kraken
/// "Detect Regions" that reads as silent is exactly what made Daniel re-run it
/// three times).
struct ActivityJob: Identifiable, Equatable {
    /// The job's lifecycle as reported by the backend. `.other` keeps any
    /// future backend state renderable rather than swallowed; `.failed` folds
    /// "failed"/"error" so a failure is always visibly a failure.
    enum State: Equatable {
        case running
        case stalled
        case paused
        /// Queued, not started: the row's `reason` says what it waits for
        /// ("Paused by you", "Waiting: memory is tight", …).
        case waiting
        case failed
        case completed
        case other(String)

        init(raw: String) {
            switch raw.lowercased() {
            case "running": self = .running
            case "stalled": self = .stalled
            case "paused": self = .paused
            case "waiting": self = .waiting
            case "failed", "error": self = .failed
            case "completed", "complete", "done", "finished": self = .completed
            default: self = .other(raw)
            }
        }

        var isFailed: Bool { self == .failed }

        /// The engine's own name for a state this app does not know (#5957).
        var otherName: String? {
            if case .other(let name) = self { return name }
            return nil
        }

        /// Still consuming compute — counts toward the toolbar badge. A failed
        /// or completed job is surfaced but is not "active work".
        var isActive: Bool {
            switch self {
            case .running, .stalled, .paused: return true
            case .waiting, .failed, .completed, .other: return false
            }
        }
    }

    let id: String
    /// The kind of work — "derivatives"/"embedding"/"import"/… or "workflow"
    /// for a workflow run (Kraken Detect Regions, HTR, transcription). Flows
    /// through generically; the surfaces render by `state`, not `taskType`.
    let taskType: String
    let name: String
    let library: String?
    let current: Int
    let total: Int
    let percent: Double
    let state: State
    /// Why a FAILED job failed, when the backend knows it ("Kraken not
    /// installed"). `nil` for non-failed jobs or when no reason was recorded.
    let reason: String?
    /// The job this one belongs to (a page's step, a step's run), #5353;
    /// `nil` for a job of its own, which is what the Activity table lists.
    let parentId: String?
    /// What the row offers (#5615): "Resume" on a job set aside after its interruptions, done by its retry.
    let offer: String?
    /// The workflow run a page's work is for (#5615); `nil` for a row not under a run.
    let runId: String?
    /// When it failed, as the engine records it (`failed_at`); nil unless failed, and cleared on a retry.
    let failedAt: Date?
    /// A run sent to a cluster or Hugging Face Jobs (`activity.remote-under-its-step`): the row says where, how far.
    let remote: Remote?
    /// The engine put this row in History (`group` is "earlier"): a run that ended, was stopped or was interrupted
    /// (`activity.window.history-group`, #5851). A live row, a queue beside it, is false.
    let isEarlier: Bool

    struct Remote: Equatable {
        let target: String
        let farState: String
        let shards: String
        let pagesLanded: Int
        /// "Rorqual · running · 3 of 4 shards · 120 pages landed": the row's words.
        var words: String { "\(target) · \(farState) · \(shards) · \(pagesLanded) pages landed" }
    }

    init(_ job: Components.Schemas.BackgroundJob) {
        self.id = job.id
        self.taskType = job.taskType
        self.name = job.name
        self.library = job.library
        self.current = job.current
        self.total = job.total
        self.percent = job.percent
        self.state = State(raw: job.state)
        self.reason = job.reason
        self.parentId = job.parentId
        self.offer = job.offer
        self.runId = job.runId
        self.failedAt = job.failedAt
        self.remote = job.remote.map {
            Remote(target: $0.target ?? "", farState: $0.farState, shards: $0.shards, pagesLanded: $0.pagesLanded ?? 0)
        }
        self.isEarlier = job.group?.rawValue == "earlier"
    }

    /// Test/preview seam — construct without the generated schema.
    init(
        id: String,
        taskType: String = "",
        name: String,
        library: String? = nil,
        current: Int = 0,
        total: Int = 0,
        percent: Double = 0,
        state: State = .running,
        reason: String? = nil,
        parentId: String? = nil,
        offer: String? = nil,
        runId: String? = nil,
        failedAt: Date? = nil,
        remote: Remote? = nil,
        isEarlier: Bool = false
    ) {
        self.id = id
        self.taskType = taskType
        self.name = name
        self.library = library
        self.current = current
        self.total = total
        self.percent = percent
        self.state = state
        self.reason = reason
        self.parentId = parentId
        self.offer = offer
        self.runId = runId
        self.failedAt = failedAt
        self.remote = remote
        self.isEarlier = isEarlier
    }

    /// A determinate bar is only meaningful once the backend knows the total.
    var showsProgress: Bool { total > 0 }

    /// Integer percent for display.
    var displayPercent: Int { Int(percent.rounded()) }
}

/// A point-in-time read of `GET /api/activity/jobs`: the running jobs plus the
/// rough process-wide CPU usage the same call reports, so the Activity surfaces
/// can show WHAT is consuming compute (Daniel: "a way to see how much CPU
/// something is using").
struct BackgroundJobsSnapshot: Equatable {
    var jobs: [ActivityJob] = []
    /// Process CPU% since the last poll (100 == one core busy; may exceed 100
    /// on multiple cores). `nil` on the first poll or if unavailable.
    var processCpuPercent: Double?
    var cpuCount: Int = 0
    /// Pause Background Work is on (`activity.pause.global`).
    var paused: Bool = false
    /// How background work runs on this Mac (`activity.mode.start-stop`, #5621).
    var mode: ActivityMode = .automatic
    /// This Mac's state as the engine's throttle reads it (`activity.popover.summary`).
    var machine: Components.Schemas.MachineState?
    /// The engine's one summary of the live blocks, the background group and History
    /// (`activity.popover.same-summary`, #5852): the window and the popover both read it.
    var activity: Components.Schemas.ActivitySummary?
}

/// How background work runs on this Mac (`activity.mode.start-stop`, #5621):
/// the engine's `mode`, set by the one Start / Stop control in the main
/// toolbar and the Activity window (`PUT /api/activity/jobs/mode`).
enum ActivityMode: String, Equatable, CaseIterable {
    /// Heavy work waits while the person uses the Mac or it is on battery.
    case automatic
    /// Start: it goes ahead anyway (memory and heat still hold it) until set back.
    case started
    /// Stop: Pause Background Work.
    case paused

    /// The engine's word; an unknown one reads as automatic (the engine's own default).
    init(engine raw: String?) {
        self = raw.flatMap(ActivityMode.init(rawValue:)) ?? .automatic
    }
}
