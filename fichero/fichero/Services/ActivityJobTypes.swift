import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// Split out of ActivityTypes.swift by its file_length limit (#6134); the types are unchanged.

/// One node of `GET /api/activity/jobs/{id}` (#5353): a run, a step or a
/// page, with what is under it rolled up (pages done, in all and failed, time,
/// tokens, cost). Mirrors the engine's `JobTree` field for field; the Activity
/// table's rows are built from it (`ActivityMonitorRow`).
struct ActivityJobNode: Identifiable, Equatable {
    let id: String
    let kind: String
    let name: String
    let subject: String
    /// What a person calls it (#5560, #5561, the engine's `display_name`): a
    /// page's file name, a run's or a step's name as its record has it.
    let displayName: String?
    /// The page's document, to open it (#5561); `nil` for runs and steps.
    let documentId: String?
    let model: String?
    var state: String
    let reason: String?
    let parentId: String?
    /// When it started and ended, as the engine recorded them (#5561); `nil`
    /// when not started, not ended, or unreadable. Never "now".
    let startedAt: Date?
    let finishedAt: Date?
    /// Who or what started it, in the engine's words ("automatic", "schedule:…").
    let startedBy: String?
    /// What a running row works on now, by name (#5561).
    let workingOn: String?
    let done: Int
    let total: Int
    let failed: Int
    let seconds: Double?
    let tokens: Int
    /// `nil` unless every model call under it is priced (never a guess).
    let costUsd: Double?
    /// A workflow run's account (#5555); `nil` on steps, pages and other jobs.
    let account: ActivityRunAccount?
    /// A recipe run's stages in order (#5576), those not started and not run
    /// included; empty on any other job.
    let stages: [ActivityRecipeStage]
    /// What a recipe run made, once it has ended (#5577); `nil` otherwise.
    let summary: Components.Schemas.RecipeRunSummary?
    var children: [ActivityJobNode]

    init(_ tree: Components.Schemas.JobTree) {
        id = tree.id
        kind = tree.kind
        name = tree.name
        subject = tree.subject
        displayName = tree.displayName
        documentId = tree.documentId
        model = tree.model
        state = tree.state
        reason = tree.reason
        parentId = tree.parentId
        startedAt = tree.startedAt.flatMap(parseEngineDate)
        finishedAt = tree.finishedAt.flatMap(parseEngineDate)
        startedBy = tree.startedBy
        workingOn = tree.workingOn
        done = tree.done
        total = tree.total
        failed = tree.failed ?? 0
        seconds = tree.seconds
        tokens = tree.tokens ?? 0
        costUsd = tree.costUsd
        account = tree.account.map(ActivityRunAccount.init)
        stages = (tree.stages ?? []).map(ActivityRecipeStage.init)
        summary = tree.summary
        children = (tree.children ?? []).map(ActivityJobNode.init)
    }

    /// A job of its own that the job table has no row for (the embedding and
    /// derivative queue, #5561): its node from the jobs poll, so it has details
    /// like any run. It has no children and nothing to price.
    init(job: ActivityJob) {
        id = job.id
        kind = job.taskType
        name = job.name
        subject = job.id
        displayName = job.name
        documentId = nil
        model = nil
        switch job.state {
        case .running, .stalled: state = "running"
        case .paused: state = "paused"
        case .waiting, .other: state = "waiting"
        case .failed: state = "failed"
        case .completed: state = "done"
        }
        reason = job.reason
        parentId = job.parentId
        startedAt = nil
        finishedAt = nil
        startedBy = nil
        workingOn = nil
        done = job.current
        total = job.total
        failed = job.state.isFailed ? 1 : 0
        seconds = nil
        tokens = 0
        costUsd = nil
        account = nil
        stages = []
        summary = nil
        children = []
    }

    /// This node, or the one with `id` anywhere under it.
    func node(withId id: String) -> ActivityJobNode? {
        if self.id == id { return self }
        for child in children {
            if let found = child.node(withId: id) { return found }
        }
        return nil
    }

    /// The pages (leaf jobs) under it, itself when it is one.
    var leaves: [ActivityJobNode] {
        children.isEmpty ? [self] : children.flatMap(\.leaves)
    }

    /// This node with `id`'s state set to `state`, wherever it is under it;
    /// `nil` when `id` is not in this tree.
    func settingState(_ state: String, of id: String) -> ActivityJobNode? {
        if self.id == id {
            var copy = self
            copy.state = state
            return copy
        }
        for (index, child) in children.enumerated() {
            if let changed = child.settingState(state, of: id) {
                var copy = self
                copy.children[index] = changed
                return copy
            }
        }
        return nil
    }
}

/// One stage of a recipe run (#5576): the card that carries one or more of its
/// steps, its state and why, and, for a workflow stage that has started, its
/// run's account: the same one that run's own row shows.
struct ActivityRecipeStage: Equatable, Identifiable {
    let steps: [String]
    /// The stage in the engine's words (the job registry's names), never the job ids.
    let title: String?
    let card: String
    let job: String?
    let state: String
    let why: String?
    let childId: String?
    let account: ActivityRunAccount?
    /// What each reader of a stage that reads with several says ("Also reads print pages with Apple Vision"), the engine's own
    /// words (`StageReader.sentence`); empty for a single reader (#6134).
    let readerSentences: [String]

    var id: String { steps.joined(separator: ",") }

    init(_ step: Components.Schemas.RecipeRunStep) {
        steps = step.steps
        title = step.title
        card = step.card
        job = step.job
        state = step.state
        why = step.why
        childId = step.childId
        account = step.account.map(ActivityRunAccount.init)
        let readers = step.readers ?? []
        readerSentences = readers.count > 1 ? readers.compactMap { $0.sentence }.filter { !$0.isEmpty } : []
    }
}

/// A workflow run's account (#5555, `activity.run.account`): the engine's one
/// record of how the run went, which its status and Activity both show. The
/// Activity row only words it; nothing here is counted again.
struct ActivityRunAccount: Equatable {
    struct Failure: Equatable {
        /// The failed page's title as the Reader names it ("18590129.pdf › Page 3"): the engine sends a display
        /// title in the account's `page` field, never a storage name (542d845eb).
        let title: String
        let reason: String
        /// Failed for a passing cause, was read once more, and failed again.
        let retried: Bool
    }

    let state: String
    let pagesTotal: Int
    let pagesDone: Int
    let pagesFailed: Int
    let pagesLeft: Int
    let failures: [Failure]
    let waitingReason: String?
    let reason: String?
    let interrupted: Bool
    let estimateSecondsLeft: Double?
    let enginePeakMemoryBytes: Int?
    let modelServerPeakMemoryBytes: Int?
    /// "Read the 3 pages that failed": the run's one action at its end.
    let offerLabel: String?

    init(_ account: Components.Schemas.RunAccount) {
        state = account.state
        pagesTotal = account.pagesTotal ?? 0
        pagesDone = account.pagesDone ?? 0
        pagesFailed = account.pagesFailed ?? 0
        pagesLeft = account.pagesLeft ?? 0
        failures = (account.failures ?? []).map {
            Failure(title: $0.page, reason: $0.reason, retried: $0.retried ?? false)
        }
        waitingReason = account.waitingReason
        reason = account.reason
        interrupted = account.interrupted ?? false
        estimateSecondsLeft = account.estimateSecondsLeft
        enginePeakMemoryBytes = account.enginePeakMemoryBytes
        modelServerPeakMemoryBytes = account.modelServerPeakMemoryBytes
        offerLabel = account.offer?.label
    }

    /// Test/preview seam — construct without the generated schema.
    init(
        state: String,
        pagesTotal: Int = 0,
        pagesDone: Int = 0,
        pagesFailed: Int = 0,
        pagesLeft: Int = 0,
        failures: [Failure] = [],
        waitingReason: String? = nil,
        reason: String? = nil,
        interrupted: Bool = false,
        estimateSecondsLeft: Double? = nil,
        enginePeakMemoryBytes: Int? = nil,
        modelServerPeakMemoryBytes: Int? = nil,
        offerLabel: String? = nil
    ) {
        self.state = state
        self.pagesTotal = pagesTotal
        self.pagesDone = pagesDone
        self.pagesFailed = pagesFailed
        self.pagesLeft = pagesLeft
        self.failures = failures
        self.waitingReason = waitingReason
        self.reason = reason
        self.interrupted = interrupted
        self.estimateSecondsLeft = estimateSecondsLeft
        self.enginePeakMemoryBytes = enginePeakMemoryBytes
        self.modelServerPeakMemoryBytes = modelServerPeakMemoryBytes
        self.offerLabel = offerLabel
    }
}

/// One line of a row's log (#5561, `GET /api/activity/jobs/{id}/log`): what
/// the engine wrote for that row or a row under it, oldest first so the
/// newest is last (`activity.details.log-filtered-newest-last`).
struct ActivityJobLogLine: Equatable, Identifiable {
    /// Its place in the log: lines have no id of their own.
    let id: Int
    /// `nil` for what a row waits for now (the engine's newest line).
    let timestamp: Date?
    let level: String
    let message: String
    /// The row it is about: the one asked for, or one under it.
    let jobId: String

    init(index: Int, _ line: Components.Schemas.JobLogLine) {
        id = index
        timestamp = line.timestamp.flatMap(parseEngineDate)
        level = line.level
        message = line.message
        jobId = line.jobId
    }

    /// The line as copied: "06/10/2026, 14:05:01  error  Failed: p1.png: …", in this Mac's time.
    var plainText: String {
        let when = timestamp.map { $0.formatted(date: .numeric, time: .standard) } ?? "now"
        return "\(when)  \(level)  \(message)"
    }
}

/// Activity statistics from the API
struct ActivityStats: Codable {
    let totalActivities: Int
    let activitiesByType: [String: Int]
    let activitiesByLevel: [String: Int]
    let errorCount: Int
    let warningCount: Int
    let avgWorkflowDurationMs: Double?
    let successRate: Double
    let periodStart: String
    let periodEnd: String

    enum CodingKeys: String, CodingKey {
        case totalActivities = "total_activities"
        case activitiesByType = "activities_by_type"
        case activitiesByLevel = "activities_by_level"
        case errorCount = "error_count"
        case warningCount = "warning_count"
        case avgWorkflowDurationMs = "avg_workflow_duration_ms"
        case successRate = "success_rate"
        case periodStart = "period_start"
        case periodEnd = "period_end"
    }
}

/// One job queued behind a kind's row (`activity.window.expands-to-pages`, #5839): what it is for, where it stands, and
/// why when it waits or failed.
struct ActivityQueuedItem: Equatable, Identifiable {
    let id: String
    let subject: String
    let state: String
    let reason: String?

    init(_ item: Components.Schemas.QueuedItem) {
        id = item.id
        subject = item.subject
        state = item.state
        reason = item.reason
    }
}
