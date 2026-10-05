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

    // MARK: - Columns

    /// "Failed: the provider refused this letter", "Waiting: memory is tight",
    /// "Running: Entities". The reason is the point of a failed row.
    var stateText: String {
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

    /// Seconds left at the pace so far, while it runs and some are done.
    var remainingSeconds: Double? {
        guard phase == .running, let seconds, done > 0, total > done else { return nil }
        return seconds / Double(done) * Double(total - done)
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
            children: steps.isEmpty ? nil : steps
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
            children: nil
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
            children: children.isEmpty ? nil : children
        )
    }

    /// A step's subject is "<run id>:<step>"; a page's is what it read.
    private static func label(_ node: ActivityJobNode) -> String {
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
