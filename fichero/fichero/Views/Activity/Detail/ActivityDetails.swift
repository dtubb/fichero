import Foundation

/// What the Activity details view shows for one selected row (#5561), worded
/// from the record the table reads: the row the table builds for that job
/// (`ActivityMonitorRow`, from the store's run tree or its jobs poll) and that
/// row's node of the job tree. Nothing is fetched or counted here, so the
/// details and the table cannot disagree (`activity.details.one-record`), and
/// a tree re-read that updates the row updates the details
/// (`activity.details.follows-the-row`).
struct ActivityDetails: Equatable {
    /// One action the view offers; an action that does not apply is absent
    /// (`activity.details.actions-are-the-rows`).
    enum Action: Hashable {
        case control(ActivityMonitorRow.Control)
        case readAgain(label: String)
        case openPage(documentId: String)
        case showPages(documentIds: [String])
        case showTrace(threadId: String)
    }

    struct FailedPage: Equatable, Identifiable {
        let id: String
        let name: String
        let reason: String
    }

    struct Resource: Equatable, Identifiable {
        let label: String
        let value: String
        var id: String { label }
    }

    /// Pages done, failed and left, and the time left at the pace so far.
    struct Counts: Equatable {
        let done: Int
        let failed: Int
        let left: Int
        let total: Int
        let timeLeft: String?

        var fraction: Double { total > 0 ? Double(done + failed) / Double(total) : 0 }

        /// "212 done · 3 failed · 185 left"
        var text: String { "\(done) done · \(failed) failed · \(left) left" }
    }

    /// The table's row for this job: its State, Progress, Cost and Errors words.
    let row: ActivityMonitorRow
    /// The row's node of the job tree; `nil` for a run whose tree the engine has none of.
    let node: ActivityJobNode?
    /// The run this row belongs to, when it belongs to one (its trace, its offer).
    let runThreadId: String?
    let heading: String
    /// The project, the model or models, who or what started it.
    let subheading: [String]
    let stateText: String
    /// This Mac's reading a waiting row rests on ("memory pressure warn"), or nil.
    let machineText: String?
    let counts: Counts?
    let failedPages: [FailedPage]
    /// How many failed pages are under it, more than `failedPages` may list.
    let failedCount: Int
    let resources: [Resource]
    let actions: [Action]

    /// The job the details read and the log is keyed by.
    var jobId: String { row.detailsJobId ?? node?.id ?? row.id }

    /// What the log read is keyed on: the row's node changing (a page done, a
    /// state, a reason) re-reads the log; nothing else does.
    var logKey: String {
        guard let node else { return "\(jobId)|\(row.phase.rawValue)" }
        return [node.id, node.state, node.reason ?? "", "\(node.done)", "\(node.failed)", "\(node.total)",
                node.finishedAt.map { "\($0.timeIntervalSince1970)" } ?? ""].joined(separator: "|")
    }

    var isLive: Bool { row.phase.isLive }
}

// MARK: - Built from the store

extension ActivityDetails {
    /// The details of `selection`'s row from what `store` already holds, or
    /// `nil` while the store has neither its run's tree nor its job.
    @MainActor
    init?(store: ActivityStore, selection: ActivitySelection) {
        let jobId = selection.jobId
        let treeKey = store.treeKey(containing: jobId)
        let tree = treeKey.flatMap { store.runTrees[$0] }
        let node = store.node(jobId: jobId)
        let projectName = store.projectName

        // The table's row: a run's row with its tree, then the row for this job under it.
        var runRow: ActivityMonitorRow?
        if let treeKey, let tree, Self.runKinds.contains(tree.kind) {
            let run = store.runs.first { ($0.threadId ?? $0.runId) == treeKey }
                ?? ActivityRun(node: tree, libraryId: selection.libraryId, libraryName: projectName)
            runRow = ActivityMonitorRow.run(run, tree: tree)
        } else if node == nil, let run = store.runs.first(where: { ($0.threadId ?? $0.runId) == jobId }) {
            runRow = ActivityMonitorRow.run(run, tree: nil)  // a run recorded before the job table
        }
        let row: ActivityMonitorRow
        if let runRow, let found = Self.find(jobId, in: runRow) {
            row = found
        } else if let job = store.backgroundJobs.first(where: { $0.id == jobId }) {
            row = ActivityMonitorRow.job(job, libraryId: selection.libraryId, projectName: projectName)
        } else if let node {
            // A job of its own with a tree (a queued job): its own row, named by its node.
            row = ActivityMonitorRow.job(
                ActivityJob(node: node), libraryId: selection.libraryId, projectName: projectName)
        } else {
            return nil
        }
        // Who started it: the row's own record, else its run's (a run's steps and pages say "workflow").
        let startedBy = [node?.startedBy, tree?.startedBy].compactMap { $0 }.first { $0 != "workflow" }
        self.init(row: row, node: node, runRow: runRow, projectName: projectName, startedBy: startedBy,
                  machine: store.machine)
    }

    /// The details from the table's row and its node: pure, so a test can build them.
    init(
        row: ActivityMonitorRow,
        node: ActivityJobNode?,
        runRow: ActivityMonitorRow?,
        projectName: String?,
        startedBy: String?,
        machine: MachineReading?
    ) {
        self.row = row
        self.node = node
        runThreadId = row.runThreadId
        let owningRun = runRow?.kind == .run ? runRow : nil

        heading = Self.heading(row: row, node: node)
        subheading = [projectName, row.model, Self.startedByWords(startedBy)].compactMap { value in
            value.flatMap { $0.isEmpty ? nil : $0 }
        }
        stateText = row.stateText
        machineText = row.phase == .waiting || row.stateText.hasPrefix("Waiting") ? machine?.words : nil

        // Progress: a row with pages counts them; a page, or a job with no total, does not.
        if row.kind != .page, row.total > 0 {
            let failed = node?.failed ?? row.errors
            counts = Counts(done: row.done, failed: failed, left: max(0, row.total - row.done - failed),
                            total: row.total, timeLeft: row.remainingSeconds.map(ActivityMonitorRow.duration))
        } else {
            counts = nil
        }

        // The failed pages under it by name, each with its reason.
        let failedLeaves = (node?.leaves ?? []).filter {
            ActivityMonitorRow.Phase(engineState: $0.state) == .failed && !Self.runKinds.contains($0.kind)
        }
        if row.kind == .run, let account = row.account, !account.failures.isEmpty {
            failedPages = account.failures.enumerated().map {
                FailedPage(id: "\($0.offset)", name: $0.element.page,
                           reason: $0.element.reason + ($0.element.retried ? " (read twice)" : ""))
            }
            failedCount = max(account.pagesFailed, account.failures.count)
        } else if row.kind != .page {
            failedPages = failedLeaves.map {
                FailedPage(id: $0.id, name: $0.displayName ?? $0.name, reason: $0.reason ?? "No reason recorded")
            }
            failedCount = max(failedLeaves.count, node?.failed ?? 0)
        } else {
            failedPages = []
            failedCount = 0
        }

        // Resources: absolute times, elapsed, tokens, cost and the run's peak memory; unmeasured left out.
        var resources: [Resource] = []
        if let started = node?.startedAt ?? row.started {
            resources.append(Resource(label: "Started", value: ActivityTimeText.absolute(started)))
        }
        if let finished = node?.finishedAt {
            resources.append(Resource(label: "Finished", value: ActivityTimeText.absolute(finished)))
        }
        if !row.secondsText.isEmpty { resources.append(Resource(label: "Elapsed", value: row.secondsText)) }
        if row.tokens > 0 { resources.append(Resource(label: "Tokens", value: row.tokens.formatted())) }
        if !row.costText.isEmpty { resources.append(Resource(label: "Cost", value: row.costText)) }
        if let account = owningRun?.account ?? row.account {
            if let bytes = account.enginePeakMemoryBytes {
                resources.append(Resource(label: "Peak memory, engine", value: ActivityMonitorRow.gigabytes(bytes)))
            }
            if let bytes = account.modelServerPeakMemoryBytes {
                resources.append(Resource(label: "Peak memory, model server", value: ActivityMonitorRow.gigabytes(bytes)))
            }
        }
        self.resources = resources

        // Actions: the row's own Pause, Resume and Stop; the run's offer; open the pages; the trace.
        var actions: [Action] = row.controls.map(Action.control)
        if let label = (owningRun ?? row).readAgainLabel {
            actions.append(.readAgain(label: label.hasSuffix(" again") ? label : label + " again"))
        }
        if row.kind == .page, let documentId = node?.documentId {
            actions.append(.openPage(documentId: documentId))
        } else if row.kind == .run || row.kind == .step {
            var seen: Set<String> = []
            let ids = (node?.leaves ?? []).compactMap(\.documentId).filter { seen.insert($0).inserted }
            if !ids.isEmpty { actions.append(.showPages(documentIds: ids)) }
        }
        if row.kind == .run, let threadId = row.runThreadId {
            actions.append(.showTrace(threadId: threadId))
        }
        self.actions = actions
    }

    static let runKinds: Set<String> = ["workflow", "workflow-step", "batch"]

    private static func find(_ jobId: String, in row: ActivityMonitorRow) -> ActivityMonitorRow? {
        if row.detailsJobId == jobId || row.jobId == jobId { return row }
        for child in row.children ?? [] {
            if let found = find(jobId, in: child) { return found }
        }
        return nil
    }

    /// "Transcribe · 40 pages", "Read a page · SM_NPQ_C01_004.jpg", "Embedding queue".
    private static func heading(row: ActivityMonitorRow, node: ActivityJobNode?) -> String {
        switch row.kind {
        case .run, .step:
            let name = row.kind == .run ? row.name : (node?.displayName ?? row.name)
            return row.total > 0 ? "\(name) · \(row.total) \(row.total == 1 ? "page" : "pages")" : name
        case .page:
            let work = node?.name ?? row.kindWord
            guard let page = node?.displayName, !page.isEmpty, page != work else { return work }
            return "\(work) · \(page)"
        case .job:
            return node?.displayName ?? row.name
        }
    }

    /// Who or what started it, in words; nil for the run's own rows ("workflow").
    static func startedByWords(_ raw: String?) -> String? {
        guard let raw, !raw.isEmpty, raw != "workflow" else { return nil }
        if raw == "automatic" { return "Started automatically" }
        if raw.hasPrefix("schedule") { return "Started by a schedule" }
        if raw.hasPrefix("trigger") { return "Started by a trigger" }
        if raw.hasPrefix("read-again") { return "Started to read failed pages again" }
        return "Started by \(raw)"
    }
}

/// This Mac's state as the throttle read it (`MachineState`), in words.
typealias MachineReading = Components.Schemas.MachineState

extension Components.Schemas.MachineState {
    /// "This Mac: memory pressure warn, thermal fair, on battery", or nil when nothing is read.
    var words: String? {
        var parts: [String] = []
        if let pressure = memoryPressure?.rawValue { parts.append("memory pressure \(pressure)") }
        if let thermal = thermalState?.rawValue, thermal != "nominal" { parts.append("thermal \(thermal)") }
        if onBattery == true { parts.append("on battery") }
        if inUse == true { parts.append("in use") }
        if let why = whyWait, !why.isEmpty { parts.insert(why, at: 0) }
        return parts.isEmpty ? nil : "This Mac: " + parts.joined(separator: ", ")
    }
}

// MARK: - Rows the table has no record for

extension ActivityRun {
    /// A run the store's run list has not read yet (started from another
    /// window, the CLI or a schedule), from its node of the job tree: it shows
    /// live like any other (#5561).
    init(node: ActivityJobNode, libraryId: UUID?, libraryName: String?) {
        let status: ActivityRunStatus
        switch ActivityMonitorRow.Phase(engineState: node.state) {
        case .running, .waiting: status = .running
        case .paused: status = .paused
        case .failed: status = .failed
        case .cancelled: status = .cancelled
        case .done: status = .completed
        }
        self.init(
            id: "\(libraryId?.uuidString ?? "")|\(node.id)",
            runId: node.id,
            workflowId: nil,
            threadId: node.id,
            workflowName: node.displayName ?? node.name,
            timestamp: node.startedAt,
            status: status,
            progress: nil,
            currentStep: nil,
            errorCount: node.failed,
            fileCount: node.total,
            isLive: false,
            libraryId: libraryId,
            libraryName: libraryName,
            failureReason: status == .failed ? node.reason : nil
        )
    }
}

extension ActivityJob {
    /// A queued job's row from its node (a job of its own with a tree).
    init(node: ActivityJobNode) {
        self.init(id: node.id, taskType: node.kind, name: node.displayName ?? node.name,
                  current: node.done, total: node.total, state: State(raw: node.state), reason: node.reason)
    }
}
