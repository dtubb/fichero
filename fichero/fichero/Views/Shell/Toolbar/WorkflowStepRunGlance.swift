import Foundation

/// What a chain step's popover says about the run (#5564,
/// `workflowbar.step-popover.run-glance`): only the step running now, or,
/// when nothing runs, the recent errors with their reasons. Everything else
/// (every step, every page, the log) is one click away in Activity details.
///
/// Built from data the app already holds: the chain's own steps (their state
/// and run thread) and `ActivityStore.runTrees`, the engine's run → step →
/// page tree the Activity table draws. A plain value, so tests pin what the
/// popover shows without a mounted view.
enum WorkflowStepRunGlance: Equatable {
    /// The work running now.
    struct Now: Equatable {
        /// The run whose details "Details" opens.
        let threadId: String?
        /// The chain step that is running (what the chip says).
        let workflow: String
        /// The step inside that run working now, when the engine names one
        /// other than the chain step itself.
        let step: String?
        /// The page it is on, by file name.
        let page: String?
        /// Running, Waiting or Paused.
        let state: String
        /// Why, when the engine says (e.g. its wait for memory).
        let reason: String?
    }

    /// One failure, with its reason.
    struct Failure: Equatable, Identifiable {
        let id: String
        let threadId: String
        /// The page that failed, by file name; nil when the run as a whole failed.
        let page: String?
        let reason: String
    }

    case running(Now)
    /// Newest first, at most `errorsShown`.
    case failed([Failure])
    /// The chain ran, and nothing failed.
    case finished(threadId: String)
    /// No run yet for this step: the popover says what the step does.
    case notRun

    static let errorsShown = 3
    static let noReason = "No reason was recorded."

    /// The run whose Activity details "Details" opens; nil when there is none.
    var detailsThreadId: String? {
        switch self {
        case .running(let now): return now.threadId
        case .failed(let failures): return failures.first?.threadId
        case .finished(let threadId): return threadId
        case .notRun: return nil
        }
    }

    /// The glance for `step`'s popover, read from its whole chain: while any
    /// step runs, that step; else, once this step has run, the chain's
    /// recent errors (or that it finished); else nothing to glance at.
    static func make(
        step: StagedWorkflowStep,
        chain: [StagedWorkflowStep],
        trees: [String: ActivityJobNode]
    ) -> WorkflowStepRunGlance {
        if let running = chain.first(where: { $0.state == .running }) {
            return .running(now(
                workflow: running.displayName,
                threadId: running.threadId,
                tree: running.threadId.flatMap { trees[$0] }
            ))
        }
        guard let threadId = step.threadId else { return .notRun }
        let ran = chain.filter { $0.threadId != nil }
        let failures = ran.flatMap { ranStep -> [Failure] in
            guard let id = ranStep.threadId else { return [] }
            return Self.failures(threadId: id, state: ranStep.state, tree: trees[id])
        }
        // Chain order is run order; each run's failures are in the engine's
        // order. Newest is last, so turn it round.
        let newest = Array(failures.reversed().prefix(errorsShown))
        return newest.isEmpty ? .finished(threadId: threadId) : .failed(newest)
    }

    /// The deepest working node of a running run: its active step, and that
    /// step's active page. A run with no tree yet says only that it runs.
    static func now(workflow: String, threadId: String?, tree: ActivityJobNode?) -> Now {
        guard let tree else {
            return Now(threadId: threadId, workflow: workflow, step: nil, page: nil, state: "Running", reason: nil)
        }
        let step = active(in: tree.children)
        let page = step.flatMap { active(in: $0.children) }
        let deepest = page ?? step ?? tree
        let phase = Phase(engineState: deepest.state)
        let stepName = step.map(label).flatMap { $0 == workflow ? nil : $0 }
        let reason = page?.reason ?? step?.reason
            ?? (phase == .running ? nil : (tree.account?.waitingReason ?? tree.reason))
        return Now(
            threadId: threadId,
            workflow: workflow,
            step: stepName,
            page: page.map(label),
            state: phase.word,
            reason: reason.flatMap { $0.isEmpty ? nil : $0 }
        )
    }

    /// One run's failures, in the engine's order: its account's failed
    /// pages; else its failed pages in the tree; else the run's own reason
    /// when the run failed as a whole.
    static func failures(threadId: String, state: StagedStepState, tree: ActivityJobNode?) -> [Failure] {
        if let account = tree?.account, !account.failures.isEmpty {
            return account.failures.enumerated().map { index, failure in
                Failure(id: "\(threadId)#\(index)", threadId: threadId, page: failure.page, reason: failure.reason)
            }
        }
        if let tree {
            let leaves = failedLeaves(tree)
            if !leaves.isEmpty {
                return leaves.map {
                    Failure(id: $0.id, threadId: threadId, page: label($0), reason: nonEmpty($0.reason) ?? noReason)
                }
            }
        }
        let runFailed = state == .failed || tree.map { Phase(engineState: $0.state) == .failed } == true
        guard runFailed else { return [] }
        return [Failure(id: threadId, threadId: threadId, page: nil, reason: nonEmpty(tree?.reason) ?? noReason)]
    }

    // MARK: - Tree reading

    /// Coarse state of an engine node, in the Activity table's words.
    enum Phase: Equatable {
        case running, waiting, paused, failed, other

        init(engineState: String) {
            switch engineState.lowercased() {
            case "running", "stalled": self = .running
            case "waiting", "accepted", "queued": self = .waiting
            case "paused": self = .paused
            case "failed", "error": self = .failed
            default: self = .other
            }
        }

        var word: String {
            switch self {
            case .running, .other: return "Running"
            case .waiting: return "Waiting"
            case .paused: return "Paused"
            case .failed: return "Failed"
            }
        }
    }

    /// The node working now: a running one first, else a waiting, else a paused one.
    private static func active(in nodes: [ActivityJobNode]) -> ActivityJobNode? {
        for wanted in [Phase.running, .waiting, .paused] {
            if let node = nodes.first(where: { Phase(engineState: $0.state) == wanted }) { return node }
        }
        return nil
    }

    private static func failedLeaves(_ node: ActivityJobNode) -> [ActivityJobNode] {
        if node.children.isEmpty {
            return Phase(engineState: node.state) == .failed && node.parentId != nil ? [node] : []
        }
        return node.children.flatMap(failedLeaves)
    }

    /// What a person calls a node: a page's file name; a step's own name
    /// (its subject is "<run id>:<step>"), never an id.
    static func label(_ node: ActivityJobNode) -> String {
        if let name = nonEmpty(node.displayName) { return name }
        var subject = node.subject
        if let parent = node.parentId, subject.hasPrefix(parent + ":") {
            subject.removeFirst(parent.count + 1)
        } else if node.kind == "workflow-step", let colon = subject.lastIndex(of: ":") {
            subject = String(subject[subject.index(after: colon)...])
        }
        return subject.isEmpty ? node.name : subject
    }

    private static func nonEmpty(_ text: String?) -> String? {
        guard let text, !text.isEmpty else { return nil }
        return text
    }
}
