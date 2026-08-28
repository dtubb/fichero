import SwiftUI

/// The variants of one verb, with enough context to choose between them
/// (Daniel, 2026-08-28: "more than a menu — a popover with a bit of context
/// for each").
///
/// A bare menu of names asked the user to already know the difference between
/// "Paleografía Española (s. XVI–XVII)" and "Transcribe Paleography (Economy)".
/// Every preset already carries a description written for exactly this moment,
/// plus the engine's own answers about whether it needs vision and whether it
/// has been validated — none of which a menu row can hold.
struct WorkflowVerbPopover: View {
    let family: WorkflowBarPolicy.VerbFamily
    /// Adds a variant as the next step of the chain.
    let onAdd: (WorkflowSidebarItem) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(family.title)
                .font(.headline)
                .padding(.horizontal, 14)
                .padding(.top, 12)
                .padding(.bottom, 8)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(family.workflows) { workflow in
                        variantRow(workflow)
                        if workflow.id != family.workflows.last?.id {
                            Divider().padding(.leading, 14)
                        }
                    }
                }
            }
            .frame(maxHeight: 320)
        }
        .frame(width: 340)
    }

    @ViewBuilder
    private func variantRow(_ workflow: WorkflowSidebarItem) -> some View {
        Button {
            onAdd(workflow)
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(workflow.name)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .multilineTextAlignment(.leading)
                    Spacer(minLength: 0)
                    // The engine's own answers, not the client's guesses.
                    if workflow.requiresVision {
                        badge("Vision", systemImage: "eye", tint: .blue)
                    }
                    if workflow.isUntested {
                        // Stated, not hidden: a preset nobody has validated
                        // end to end should say so before it spends money.
                        badge("Untested", systemImage: "exclamationmark.triangle", tint: .orange)
                    }
                }

                if let description = workflow.description, !description.isEmpty {
                    Text(description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.leading)
                        .lineLimit(4)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Text("\(workflow.effectiveStepCount) step(s) in this workflow")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Add \(workflow.displayName) to the chain")
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

extension WorkflowSidebarItem {
    /// Node count as the engine counted it — the summary payload omits the
    /// graph, so measuring `nodes` here would report 0 for every preset.
    var effectiveStepCount: Int { nodeCount }
}
