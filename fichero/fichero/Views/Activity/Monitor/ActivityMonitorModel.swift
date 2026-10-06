import Foundation

/// One row of the Activity window's table (#2546 / B2, rebuilt for #5415):
/// a run, a step, a page, or a job of its own (an embedding queue, a waiting
/// kind of work).
///
/// The tree is the engine's (`GET /api/activity/jobs/{id}`, #5353): a run's
/// steps and their pages, with time, cost and errors rolled up. A run the
/// engine has no tree for still has its row, from the runs table alone.
///
/// Every level shares this one row type so a `Table` renders them with one
/// set of columns. Display values are precomputed here so the column closures
/// stay tiny: hierarchical `Table` bodies type-check slowly.
struct ActivityMonitorRow: Identifiable, Equatable {
    enum Kind { case run, step, page, job }

    /// The state, coarsely, in the order the State column sorts it.
    enum Phase: Int {
        case running, waiting, paused, failed, cancelled, done

        init(engineState: String) {
            switch engineState.lowercased() {
            case "running", "stalled": self = .running
            case "waiting", "accepted", "queued": self = .waiting
            case "paused": self = .paused
            case "failed", "error": self = .failed
            case "cancelled", "canceled", "stopped": self = .cancelled
            default: self = .done
            }
        }

        init(_ status: ActivityRunStatus) {
            switch status {
            case .running: self = .running
            case .paused: self = .paused
            case .completed: self = .done
            case .failed: self = .failed
            case .cancelled: self = .cancelled
            }
        }

        init(_ state: ActivityJob.State) {
            switch state {
            case .running, .stalled: self = .running
            case .waiting, .other: self = .waiting
            case .paused: self = .paused
            case .failed: self = .failed
            case .completed: self = .done
            }
        }

        var word: String {
            switch self {
            case .running: "Running"
            case .waiting: "Waiting"
            case .paused: "Paused"
            case .failed: "Failed"
            case .cancelled: "Stopped"
            case .done: "Done"
            }
        }

        var isLive: Bool { self == .running || self == .waiting || self == .paused }

        /// The state as an SF Symbol (#5560).
        var symbol: String {
            switch self {
            case .running: "play.circle.fill"
            case .waiting: "clock"
            case .paused: "pause.circle.fill"
            case .failed: "xmark.circle.fill"
            case .cancelled: "stop.circle.fill"
            case .done: "checkmark.circle.fill"
            }
        }
    }

    /// What a row's Pause, Resume and Stop buttons offer.
    enum Control: String, Identifiable {
        case pause, resume, stop
        var id: String { rawValue }
        var label: String {
            switch self {
            case .pause: "Pause"
            case .resume: "Resume"
            case .stop: "Stop"
            }
        }
        var systemImage: String {
            switch self {
            case .pause: "pause.fill"
            case .resume: "play.fill"
            case .stop: "stop.fill"
            }
        }
    }

    /// Unique across levels and projects.
    let id: String
    let kind: Kind
    let libraryId: UUID?
    /// The owning run's row id (`ActivityRun.id`): what Delete and the detail
    /// window act on from any row of its tree.
    let runRowID: String?
    /// The owning run's thread id: the key of its tree in `ActivityStore`.
    let runThreadId: String?
    /// The job Pause and Stop act on (`/api/activity/jobs/{id}/…`); `nil` for
    /// a row with no job behind it, which shows no controls.
    let jobId: String?
    let name: String
    /// The project, shown before a run's name when rows are not grouped.
    let projectName: String?
    let phase: Phase
    /// Why it failed, or what it is waiting for, in the engine's words.
    let reason: String?
    /// What a running row is working on now.
    let workingOn: String?
    let done: Int
    let total: Int
    let started: Date?
    /// How long it took, start to finish (or until the last read, while it runs).
    let seconds: Double?
    let costUsd: Double?
    let tokens: Int
    let errors: Int
    let model: String?
    /// Live from this window's own executions: its time ticks as a timer.
    let isLive: Bool
    /// `nil` = a leaf (no disclosure triangle).
    var children: [ActivityMonitorRow]?
    /// A run's account (#5555): what its row says beyond the counts. `nil`
    /// on steps, pages, other jobs and runs the engine has no account for.
    var account: ActivityRunAccount?
    /// The engine's kind of work ("read-a-page", "train-a-model", …), for the
    /// row's kind icon (#5560); `nil` when the row has no job behind it.
    var engineKind: String?

    // MARK: - Icons (#5560)

    /// What kind of row it is, as an SF Symbol: a run, a step, a page, a model
    /// load, training, or other work of its own.
    var kindSymbol: String {
        let work = (engineKind ?? "").lowercased()
        if work.contains("train") { return "graduationcap" }
        if work.contains("download") || work.contains("load-model") || work.contains("install") {
            return "arrow.down.circle"
        }
        switch kind {
        case .run: return "flowchart"
        case .step: return "list.bullet.indent"
        case .page: return "doc.text"
        case .job: return "gearshape"
        }
    }

    /// The kind in words, for VoiceOver beside the icon.
    var kindWord: String {
        switch kindSymbol {
        case "graduationcap": "Training"
        case "arrow.down.circle": "Model load"
        case "flowchart": "Run"
        case "list.bullet.indent": "Step"
        case "doc.text": "Page"
        default: "Job"
        }
    }

    /// Whether ⓘ (and double-click) can open this row's log and details: a row
    /// that belongs to a run.
    var opensDetails: Bool { runRowID != nil }

    // MARK: - Columns

    /// "Failed: the provider refused this letter", "Waiting: memory is tight",
    /// "Running: Entities". The reason is the point of a failed row.
    var stateText: String {
        // An interrupted run says so, and when ("Interrupted: the engine stopped at 14:05, …").
        if let account, account.interrupted, let why = account.reason ?? reason {
            return why
        }
        // A running run whose page waits (for memory, #5537) says what for.
        if phase == .running, let waiting = account?.waitingReason, !waiting.isEmpty {
            return waiting
        }
        if let reason, !reason.isEmpty, phase == .failed || phase == .waiting || phase == .paused {
            if reason.lowercased().hasPrefix(phase.word.lowercased()) || reason.hasPrefix("Paused") {
                return reason
            }
            return "\(phase.word): \(reason)"
        }
        if phase == .running, let workingOn, !workingOn.isEmpty {
            return "Running: \(workingOn)"
        }
        return phase.word
    }

    /// Seconds left at the pace so far, while it runs and some are done: the
    /// engine's estimate when the run's account has one.
    var remainingSeconds: Double? {
        guard phase == .running else { return nil }
        if let estimate = account?.estimateSecondsLeft { return estimate }
        guard let seconds, done > 0, total > done else { return nil }
        return seconds / Double(done) * Double(total - done)
    }

    /// The run's failed pages with why, one a line, then its peak memory:
    /// what the State cell's help shows (#5555).
    var accountDetail: String? {
        guard let account else { return nil }
        var lines = account.failures.map { failure in
            "\(failure.page): \(failure.reason)" + (failure.retried ? " (read twice)" : "")
        }
        if account.pagesFailed > account.failures.count {
            lines.append("and \(account.pagesFailed - account.failures.count) more")
        }
        if let peak = peakMemoryText { lines.append(peak) }
        return lines.isEmpty ? nil : lines.joined(separator: "\n")
    }

    /// "Peak memory: engine 2.0 GB, model server 3.5 GB" (#5537), when measured.
    var peakMemoryText: String? {
        guard let account else { return nil }
        let parts = [
            account.enginePeakMemoryBytes.map { "engine \(Self.gigabytes($0))" },
            account.modelServerPeakMemoryBytes.map { "model server \(Self.gigabytes($0))" }
        ].compactMap { $0 }
        return parts.isEmpty ? nil : "Peak memory: " + parts.joined(separator: ", ")
    }

    /// "Read the 3 pages that failed": the run's one action at its end, or nil.
    var readAgainLabel: String? {
        guard kind == .run, !phase.isLive else { return nil }
        return account?.offerLabel
    }

    static func gigabytes(_ bytes: Int) -> String {
        let value = Double(bytes) / 1_073_741_824
        return value.formatted(.number.precision(.fractionLength(1)).locale(Locale(identifier: "en_US_POSIX"))) + " GB"
    }

    /// "12 of 40", plus "about 3 min left" while it runs.
    var progressText: String {
        guard total > 0 else { return "" }
        let counts = "\(done) of \(total)"
        guard let remaining = remainingSeconds else { return counts }
        return "\(counts), \(Self.duration(remaining)) left"
    }

    /// "$0.0023"; "Not priced" when a call under it has no price; empty when
    /// nothing under it called a model. Never zero for unknown.
    var costText: String {
        if let costUsd {
            // Dollars, as the price list states them, in any locale.
            return "$" + costUsd.formatted(.number.precision(.significantDigits(1...3)).locale(Locale(identifier: "en_US_POSIX")))
        }
        return tokens > 0 ? "Not priced" : ""
    }

    var secondsText: String { seconds.map(Self.duration) ?? "" }

    var errorsText: String { errors > 0 ? "\(errors)" : "" }

    /// What Pause and Stop offer on this row: nothing on a finished row, or a
    /// row with no job behind it.
    var controls: [Control] {
        guard jobId != nil else { return [] }
        switch phase {
        case .running, .waiting: return [.pause, .stop]
        case .paused: return [.resume, .stop]
        case .failed, .cancelled, .done: return []
        }
    }

    // MARK: - Sort keys (non-optional, so a column can sort on them)

    /// Live rows first: the default order is what is happening now, then the newest.
    var liveKey: Int { phase.isLive ? 0 : 1 }
    var phaseKey: Int { phase.rawValue }
    var startedKey: Date { started ?? .distantPast }
    var secondsKey: Double { seconds ?? -1 }
    var costKey: Double { costUsd ?? -1 }
    var progressKey: Double { total > 0 ? Double(done) / Double(total) : -1 }
    var modelKey: String { model ?? "" }

    static let defaultSort: [KeyPathComparator<ActivityMonitorRow>] = [
        KeyPathComparator(\.liveKey),
        KeyPathComparator(\.startedKey, order: .reverse)
    ]

    /// Rows in `comparators`' order, each level's children too.
    static func sorted(
        _ rows: [ActivityMonitorRow],
        using comparators: [KeyPathComparator<ActivityMonitorRow>]
    ) -> [ActivityMonitorRow] {
        rows.sorted(using: comparators).map { row in
            var row = row
            row.children = row.children.map { sorted($0, using: comparators) }
            return row
        }
    }

    static func duration(_ seconds: Double) -> String {
        Duration.seconds(seconds.rounded()).formatted(
            .units(allowed: [.hours, .minutes, .seconds], width: .abbreviated, maximumUnitCount: 2)
        )
    }
}

// MARK: - Building rows

extension ActivityMonitorRow {
    /// A run's row, with its tree under it when the engine has one.
    static func run(_ run: ActivityRun, tree: ActivityJobNode?) -> ActivityMonitorRow {
        let library = run.libraryId?.uuidString ?? ""
        let steps = tree?.children.map { node($0, run: run, library: library) } ?? []
        let phase = Phase(run.status)
        return ActivityMonitorRow(
            id: run.id,
            kind: .run,
            libraryId: run.libraryId,
            runRowID: run.id,
            runThreadId: run.threadId ?? run.runId,
            jobId: tree?.id,
            name: run.workflowName,
            projectName: run.libraryName,
            phase: phase,
            reason: run.failureReason ?? tree?.reason,
            workingOn: run.currentStep.flatMap { $0.isEmpty ? nil : $0 } ?? tree.flatMap(Self.runningLabel),
            done: tree?.done ?? (run.isLive ? Int((Double(run.fileCount) * (run.progress ?? 0)).rounded()) : 0),
            total: tree?.total ?? (run.isLive ? run.fileCount : 0),
            started: run.timestamp,
            seconds: tree?.seconds,
            costUsd: tree?.costUsd,
            tokens: tree?.tokens ?? 0,
            errors: tree?.failed ?? run.errorCount,
            model: tree.flatMap(Self.models),
            isLive: run.isLive && phase == .running,
            children: steps.isEmpty ? nil : steps,
            account: tree?.account,
            engineKind: "workflow"
        )
    }

    /// A job of its own from `GET /api/activity/jobs` that is not a workflow
    /// run (those are run rows): an embedding queue, a kind of queued work.
    static func job(_ job: ActivityJob, libraryId: UUID?, projectName: String?) -> ActivityMonitorRow {
        ActivityMonitorRow(
            id: "\(libraryId?.uuidString ?? "")|job:\(job.id)",
            kind: .job,
            libraryId: libraryId,
            runRowID: nil,
            runThreadId: nil,
            jobId: nil,
            name: job.name,
            projectName: projectName,
            phase: Phase(job.state),
            reason: job.reason,
            workingOn: nil,
            done: job.current,
            total: job.total,
            started: nil,
            seconds: nil,
            costUsd: nil,
            tokens: 0,
            errors: job.state.isFailed ? 1 : 0,
            model: nil,
            isLive: false,
            children: nil,
            engineKind: job.taskType
        )
    }

    private static func node(_ node: ActivityJobNode, run: ActivityRun, library: String) -> ActivityMonitorRow {
        let children = node.children.map { self.node($0, run: run, library: library) }
        let isStep = node.kind == "workflow-step" || node.kind == "workflow" || node.kind == "batch"
        return ActivityMonitorRow(
            id: "\(library)|\(node.id)",
            kind: isStep ? .step : .page,
            libraryId: run.libraryId,
            runRowID: run.id,
            runThreadId: run.threadId ?? run.runId,
            jobId: node.id,
            name: label(node),
            projectName: nil,
            phase: Phase(engineState: node.state),
            reason: node.reason,
            workingOn: runningLabel(node),
            done: node.done,
            total: node.total,
            started: nil,
            seconds: node.seconds,
            costUsd: node.costUsd,
            tokens: node.tokens,
            errors: node.failed,
            model: models(node),
            isLive: false,
            children: children.isEmpty ? nil : children,
            engineKind: node.kind
        )
    }

    /// A step's subject is "<run id>:<step>"; a page's is what it read, named
    /// by its file (the engine's `label`, #5560), never its id.
    private static func label(_ node: ActivityJobNode) -> String {
        if let label = node.label, !label.isEmpty { return label }
        var subject = node.subject
        if let parent = node.parentId, subject.hasPrefix(parent + ":") {
            subject.removeFirst(parent.count + 1)
        } else if let colon = subject.lastIndex(of: ":"), node.kind == "workflow-step" {
            subject = String(subject[subject.index(after: colon)...])
        }
        return subject.isEmpty ? node.name : subject
    }

    /// The deepest running node's label: what a running row is working on now.
    private static func runningLabel(_ node: ActivityJobNode) -> String? {
        for child in node.children where Phase(engineState: child.state) == .running {
            return runningLabel(child).map { "\(label(child)), \($0)" } ?? label(child)
        }
        return nil
    }

    /// The model, or the models, under a node.
    private static func models(_ node: ActivityJobNode) -> String? {
        var found = Set<String>()
        func collect(_ node: ActivityJobNode) {
            if let model = node.model, !model.isEmpty { found.insert(model) }
            node.children.forEach(collect)
        }
        collect(node)
        return found.isEmpty ? nil : found.sorted().joined(separator: ", ")
    }

    /// One group of the window when rows are grouped by project: a project's
    /// rows, or the Mac's own work (the global library), its own group.
    struct Group: Identifiable {
        let id: String
        let title: String
        let isMac: Bool
        var rows: [ActivityMonitorRow]
    }

    /// Job kinds that are runs: shown as their run's row, never twice.
    static let runKinds: Set<String> = ["workflow", "workflow-step", "batch"]

    /// One library's group: its runs (each with its tree when loaded) and its
    /// jobs of their own. A job under a run, or a run's own job, is not a row
    /// of its own: it is in its run's tree. The global library is the Mac's.
    static func group(
        libraryId: UUID,
        libraryName: String,
        isMac: Bool,
        runRows: [ActivityMonitorRow],
        jobs: [ActivityJob]
    ) -> Group {
        let runIds = Set(runRows.compactMap(\.runThreadId))
        let jobRows = jobs
            .filter { $0.parentId == nil && !runIds.contains($0.id) && !runKinds.contains($0.taskType) }
            .map { job($0, libraryId: libraryId, projectName: libraryName) }
        return Group(
            id: libraryId.uuidString,
            title: isMac ? "This Mac" : libraryName,
            isMac: isMac,
            rows: runRows + jobRows
        )
    }
}
