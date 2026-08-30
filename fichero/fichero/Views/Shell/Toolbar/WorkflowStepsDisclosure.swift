import SwiftUI

/// The steps of one workflow, each with what it reads and the prompt it would
/// send (Daniel, 2026-08-28: "make it easy to see the prompts used in tools,
/// and the steps in the workflows, as well as the input").
///
/// Collapsed by default: the popover's job is still to choose a verb, and a
/// wall of prompt text would bury that. Expanded, it answers the three
/// questions you actually have before spending money on a multi-step run over
/// a folder — what will run, on what, and what will it ask the model.
///
/// Reads `WorkflowStore.workflowStepCache`, which the store fills once per
/// workflow through the SAME prompt endpoint the node editor's preview uses.
/// No second code path, and no fetch at all on a second look.
struct WorkflowStepsDisclosure: View {
    let workflowId: String
    @Environment(WorkflowStore.self) private var workflowStore
    @State private var isExpanded = false
    /// The load came back empty-handed. Without this the disclosure showed
    /// "Loading steps…" forever on a fetch failure (review fix, 2026-08-29);
    /// collapsing and reopening retries.
    @State private var loadFailed = false

    private var steps: [WorkflowStepPreview]? { workflowStore.steps(for: workflowId) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                isExpanded.toggle()
            } label: {
                Label(
                    isExpanded ? "Hide steps & prompts" : "Show steps & prompts",
                    systemImage: isExpanded ? "chevron.down" : "chevron.right"
                )
                .font(.caption)
                .labelStyle(.titleAndIcon)
                .foregroundStyle(.tint)
            }
            .buttonStyle(.plain)

            if isExpanded {
                if let steps {
                    if steps.isEmpty {
                        Text("This workflow has no steps.")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(steps) { step in
                            stepRow(step)
                        }
                    }
                } else if loadFailed {
                    Text("Couldn't load this workflow's steps. Close and reopen to retry.")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                } else {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.mini)
                        Text("Loading steps…")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        // Keyed on the store's change token as well as the expansion: a
        // workflow edit wipes the step cache, and a disclosure that was open
        // at that moment would otherwise show "Loading steps…" forever with
        // nothing left to re-trigger the fetch (review, 2026-08-29).
        .task(id: "\(isExpanded):\(workflowStore.changeToken)") {
            guard isExpanded else { return }
            loadFailed = false
            await workflowStore.loadSteps(for: workflowId)
            loadFailed = workflowStore.steps(for: workflowId) == nil
        }
    }

    @ViewBuilder
    private func stepRow(_ step: WorkflowStepPreview) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 5) {
                Text("\(step.index + 1)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .frame(width: 12)
                Image(systemName: step.icon)
                    .font(.system(size: 10))
                    .foregroundStyle(.tint)
                Text(step.label)
                    .font(.caption)
                    .fontWeight(.medium)
                Spacer(minLength: 0)
                // A step pinned to its own model is the thing you most want to
                // catch before running: it will NOT follow the bar's model.
                if !step.model.isEmpty {
                    Text(step.model)
                        .font(.system(size: 9))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.head)
                }
            }

            Text("reads: \(step.inputSummary)")
                .font(.system(size: 9))
                .foregroundStyle(.tertiary)
                .padding(.leading, 17)

            if step.usesModel {
                if let prompt = step.prompt, !prompt.isEmpty {
                    Text(prompt)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .lineLimit(8)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(.quaternary.opacity(0.35), in:
                            RoundedRectangle(cornerRadius: 5))
                        .padding(.leading, 17)
                } else {
                    // Said, not hidden: a prompting step whose prompt the
                    // engine would not resolve is a finding, not a blank.
                    Text("prompt unavailable")
                        .font(.system(size: 9))
                        .foregroundStyle(.orange)
                        .padding(.leading, 17)
                }
            }
        }
    }
}
