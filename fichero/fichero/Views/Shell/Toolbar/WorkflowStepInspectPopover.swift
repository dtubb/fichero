import SwiftUI

/// "What does this step do?" — the light, click-to-read popover for a step
/// already staged in the chain rail (Daniel, 2026-09-06: "workflow bar should
/// let us click on a workflow and see what it does").
///
/// A single click on an assembling step opens THIS (double-click still opens the
/// full node editor). It reuses the same pieces the verb popover uses — the
/// workflow's description and `WorkflowStepsDisclosure` (its steps + prompts) —
/// so there is one representation of "what a workflow does", not a second.
///
/// A tool step has no sub-steps to disclose, so it states what it is instead.
struct WorkflowStepInspectPopover: View {
    let step: StagedWorkflowStep
    /// Opens the full node editor — the same action the chip's double-click uses.
    var onOpen: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
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
        .padding(12)
        .frame(width: 300, alignment: .leading)
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
            .font(.system(size: 9))
            .foregroundStyle(tint)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(tint.opacity(0.12), in: Capsule())
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
