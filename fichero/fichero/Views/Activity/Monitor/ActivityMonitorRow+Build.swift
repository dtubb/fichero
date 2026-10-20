import Foundation

// MARK: - Building rows

extension ActivityMonitorRow {
    static func endFromStart(_ start: Date?, seconds: Double?) -> Date? {
        guard let start, let seconds else { return nil }
        return start.addingTimeInterval(seconds)
    }

    /// A run's row, with its tree under it when the engine has one.
    static func run(_ run: ActivityRun, tree: ActivityJobNode?) -> ActivityMonitorRow {
        let library = run.libraryId?.uuidString ?? ""
        let steps = tree?.children.map { node($0, run: run, library: library) } ?? []
        // A run seen only as a node of the job tree says what the engine said (waiting is waiting, not Running; #5958).
        let phase = run.engineState.map { Phase(engineState: $0) } ?? Phase(run.status)
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
            engineKind: "workflow",
            unknownState: phase == .unknown ? run.engineState : nil,
            transientState: Phase.transientWord(run.engineState),
            ended: tree?.finishedAt ?? Self.endFromStart(run.timestamp, seconds: tree?.seconds)
        )
    }

    /// A job of its own from `GET /api/activity/jobs` that is not a workflow
    /// run (those are run rows): an embedding queue, a kind of queued work.
    /// Its Pause, Resume and Stop act on its id (#5621, `activity.pause.per-queue`):
    /// one job's, or a row that stands for many (the import's `derivatives`,
    /// `waiting:<kind>`), which the engine applies to each job not started.
    static func job(_ job: ActivityJob, libraryId: UUID?, projectName: String?) -> ActivityMonitorRow {
        ActivityMonitorRow(
            id: "\(libraryId?.uuidString ?? "")|job:\(job.id)",
            kind: .job,
            libraryId: libraryId,
            runRowID: nil,
            runThreadId: nil,
            jobId: job.id,
            name: job.name,
            projectName: projectName,
            phase: Phase(job.state),
            reason: job.remote?.words ?? job.reason,
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
            engineKind: job.taskType,
            ownJobId: job.id,
            offer: job.offer,
            unknownState: Phase(job.state) == .unknown ? job.state.otherName : nil,
            transientState: Phase.transientWord(job.state.otherName),
            ended: job.failedAt
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
            engineKind: node.kind,
            unknownState: Phase(engineState: node.state) == .unknown ? node.state : nil,
            transientState: Phase.transientWord(node.state)
        )
    }

    /// A step's subject is "<run id>:<step>"; a page's is what it read, named
    /// by its file (the engine's `label`, #5560), never its id.
    private static func label(_ node: ActivityJobNode) -> String {
        if let name = node.displayName, !name.isEmpty { return name }
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
        // The engine lists waiting jobs in the order the lane will pick them; the table keeps that order (#5839).
        let jobRows = jobs
            .filter { $0.parentId == nil && !runIds.contains($0.id) && !runKinds.contains($0.taskType) }
            .enumerated()
            .map { index, listed -> ActivityMonitorRow in
                var row = job(listed, libraryId: libraryId, projectName: libraryName)
                row.queuePosition = index
                return row
            }
        return Group(
            id: libraryId.uuidString,
            title: isMac ? "This Mac" : libraryName,
            isMac: isMac,
            rows: runRows + jobRows
        )
    }
}
