import OSLog
import SwiftUI

private let actualCostLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "WorkflowBarActualCost"
)

// The chain chip's ESTIMATE → ACTUAL transition (Daniel, 2026-09-05). Before
// and during a run the chip states an estimate; on completion it states what
// the run actually SPENT, read from each step's recorded accounting — the same
// RunUsage.costUsd Activity shows, so there is one source of truth and the two
// surfaces can never disagree.
extension ContentView {

    /// Read each completed step's ACTUAL cost from its run accounting and build
    /// a `StagedChainCost` of actuals, so the chip can transition est → actual.
    ///
    /// Cost is recorded PER RUN (`RunUsage` is a run total), so each step's line
    /// carries that step's run total — labelled honestly as such in the chip.
    /// A step with no thread id (it never launched), a run with no usage (it
    /// made no model call, or predates usage accounting), or a run whose models
    /// could not be priced all become UNPRICED lines — never a stand-in zero,
    /// the same rule the estimate follows.
    @MainActor
    func refreshChainActualCost() async {
        let steps = stagedWorkflowChain
        guard !steps.isEmpty else {
            stagedChainActualCost = nil
            return
        }
        guard let activityService =
            libraryManager.getLibrary(id: windowState.libraryId)?.activityService
            ?? libraryManager.globalLibrary?.activityService
        else { return }

        var lines: [StagedChainCost.Line] = []
        for step in steps {
            lines.append(
                StagedChainCost.Line(
                    id: step.id,
                    estimate: await actualStepCost(
                        threadId: step.threadId, service: activityService
                    )
                )
            )
        }
        stagedChainActualCost = StagedChainCost(lines: lines)
    }

    /// One step's measured cost, or nil when it cannot be known. nil (unpriced)
    /// is deliberately distinct from a real zero (a free on-device model, whose
    /// run prices at 0): free is a fact, unknown is a question.
    @MainActor
    private func actualStepCost(
        threadId: String?, service: ActivityService
    ) async -> Double? {
        guard let threadId else { return nil }
        do {
            return try await service.getWorkflowRun(threadId: threadId).runUsage?.costUsd
        } catch {
            actualCostLogger.warning(
                "No run accounting for thread \(threadId, privacy: .public): \(error.localizedDescription, privacy: .public)"
            )
            return nil
        }
    }
}
