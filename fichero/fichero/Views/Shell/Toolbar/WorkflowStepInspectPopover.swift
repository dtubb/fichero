import SwiftUI

/// The popover for a step staged in the chain rail.
///
/// During and after a run it is a glance, not a list (#5564,
/// `workflowbar.step-popover.run-glance`): while the chain runs, ONLY the
/// step running now — its name, the page it is on by file name, its state
/// and why (e.g. waiting for memory); when nothing runs, ONLY the chain's
/// recent errors with their reasons, newest first. Everything else is one
/// click away: "Details" opens the run's Activity details through the same
/// selection + window the Activity table's ⓘ uses. What it shows is the
/// plain `WorkflowStepRunGlance` value, so tests pin it without a view.
///
/// Before the step has run it says what the step does (Daniel, 2026-09-06):
/// the workflow's description and `WorkflowStepsDisclosure` (its steps +
/// prompts), the same pieces the verb popover uses. A tool step has no
/// sub-steps to disclose, so it states what it is instead.
struct WorkflowStepInspectPopover: View {
    let step: StagedWorkflowStep
    /// The whole chain this step is in: the glance reads the step running
    /// now, or every run's errors, from it.
    var chain: [StagedWorkflowStep] = []
    /// Opens the full node editor — the same action the chip's double-click uses.
    var onOpen: (() -> Void)?

    @Environment(ActivityStore.self) private var activityStore: ActivityStore?
    @Environment(\.openWindow) private var openWindow

    private var glance: WorkflowStepRunGlance {
        WorkflowStepRunGlance.make(step: step, chain: chain, trees: activityStore?.runTrees ?? [:])
    }

    var body: some View {
        let glance = glance
        VStack(alignment: .leading, spacing: 8) {
            switch glance {
            case .running(let now):
                WorkflowStepRunningNowView(now: now)
                detailsButton(glance)
            case .failed(let failures):
                WorkflowStepRecentErrorsView(failures: failures)
                detailsButton(glance)
            case .finished:
                header
                Text("Finished with no errors.")
                    .font(.body)
                    .foregroundStyle(.secondary)
                detailsButton(glance)
            case .notRun:
                whatItDoes
            }
        }
        .padding(12)
        .frame(width: 300, alignment: .leading)
        // Read each run's tree once if no Activity surface has yet; later
        // changes arrive from the change stream into the same store.
        .task(id: chain.compactMap(\.threadId)) {
            guard let activityStore else { return }
            for threadId in chain.compactMap(\.threadId) {
                await activityStore.loadRunTree(threadId: threadId)
            }
        }
    }

    @ViewBuilder
    private var whatItDoes: some View {
        header

        if let workflow = step.workflow {
            if let description = workflow.description, !description.isEmpty {
                Text(description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text("\(workflow.effectiveStepCount) step(s) in this workflow")
                .font(.caption2)
                .foregroundStyle(.tertiary)
            Divider()
            WorkflowStepsDisclosure(workflowId: workflow.id)
        } else {
            // A single tool realised as a one-step run — no graph to show.
            Text(step.usesModelStepDescription)
                .font(.caption)
                .foregroundStyle(.secondary)
        }

        if let onOpen {
            Divider()
            Button {
                onOpen()
            } label: {
                Label("Open in node editor", systemImage: "square.and.pencil")
                    .font(.caption)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.tint)
        }
    }

    /// One click to everything else: the run's Activity details.
    @ViewBuilder
    private func detailsButton(_ glance: WorkflowStepRunGlance) -> some View {
        if let threadId = glance.detailsThreadId {
            Divider()
            Button("Details") { openDetails(threadId: threadId, glance: glance) }
                .accessibilityIdentifier("workflowbar.step-popover.details")
                .help("Open this run's Activity details")
        }
    }

    /// The Activity table's ⓘ path (`ActivityMonitorWindow.openDetails`):
    /// select the run, open the one details window. The store's own run row
    /// when it has one, so the details match the table's.
    private func openDetails(threadId: String, glance: WorkflowStepRunGlance) {
        let ranStep = chain.first { $0.threadId == threadId }
        let status: SelectedActivityRun.ActivityRunStatusType
        switch glance {
        case .running: status = .running
        case .failed: status = .failed
        case .finished, .notRun: status = .completed
        }
        let selected = activityStore?.runs.first { $0.threadId == threadId || $0.runId == threadId }?.toSelectedRun()
            ?? SelectedActivityRun(
                id: threadId,
                name: ranStep?.name ?? step.name,
                workflowId: ranStep?.workflow?.id,
                threadId: threadId,
                timestamp: nil,
                status: status,
                isLive: status == .running,
                libraryId: nil,
                libraryName: nil,
                childType: nil
            )
        ActivityWindowSelectionState.shared.select(selected)
        openWindow(id: ActivityWindowSelectionState.detailWindowID)
    }

    @ViewBuilder
    private var header: some View {
        HStack(spacing: 6) {
            Text(step.displayName)
                .font(.headline)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
            Spacer(minLength: 0)
            if let workflow = step.workflow {
                if workflow.requiresVision {
                    badge("Vision", systemImage: "eye", tint: .blue)
                }
                if workflow.isUntested {
                    badge("Untested", systemImage: "exclamationmark.triangle", tint: .orange)
                }
            }
        }
    }

    private func badge(_ title: String, systemImage: String, tint: Color) -> some View {
        Label(title, systemImage: systemImage)
            .font(.caption2)
            .foregroundStyle(tint)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(tint.opacity(0.12), in: Capsule())
    }
}

/// The step running now: its name, the page by file name, its state and why.
private struct WorkflowStepRunningNowView: View {
    let now: WorkflowStepRunGlance.Now

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(now.workflow)
                .font(.headline)
                .lineLimit(2)
            if let step = now.step {
                Text(step)
                    .font(.body)
            }
            if let page = now.page {
                Text(page)
                    .font(.body)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .textSelection(.enabled)
            }
            Text(now.reason.map { "\(now.state): \($0)" } ?? now.state)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("workflowbar.step-popover.running")
    }
}

/// The chain's recent errors, newest first, each with its reason.
private struct WorkflowStepRecentErrorsView: View {
    let failures: [WorkflowStepRunGlance.Failure]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Recent errors")
                .font(.headline)
            ForEach(failures) { failure in
                VStack(alignment: .leading, spacing: 2) {
                    if let page = failure.page {
                        Text(page)
                            .font(.body)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    Text(failure.reason)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
            }
        }
        .accessibilityIdentifier("workflowbar.step-popover.errors")
    }
}

extension StagedWorkflowStep {
    /// One line for a bare tool step, whose "what it does" is just whether it
    /// spends a model call.
    var usesModelStepDescription: String {
        if case .tool(_, _, _, let usesLLM) = kind {
            return usesLLM
                ? "A single tool step that runs a model."
                : "A single tool step (no model call)."
        }
        return "A single step."
    }
}
