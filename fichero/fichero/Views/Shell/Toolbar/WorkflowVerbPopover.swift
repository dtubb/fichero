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
    /// Opens the variant in the node editor — the full graph, its steps and
    /// prompts, everything the card can only summarise (Daniel, 2026-08-29:
    /// "give us an i to open ... and see steps as well"). nil hides the ⓘ.
    var onInspect: ((WorkflowSidebarItem) -> Void)?

    /// Cards in a grid, not one long column (Daniel, 2026-08-29: "I was
    /// actually imagining two or three columns, so shorter descriptions").
    /// Two columns up to six variants, three beyond — a nine-variant
    /// Transcribe family scans as a page, not a scroll.
    private var columnCount: Int {
        family.workflows.count <= 2 ? 1 : family.workflows.count <= 6 ? 2 : 3
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(family.title)
                .font(.headline)
                .padding(.horizontal, 14)
                .padding(.top, 12)
                .padding(.bottom, 8)

            Divider()

            ScrollView {
                LazyVGrid(
                    columns: Array(
                        repeating: GridItem(.flexible(), spacing: 10, alignment: .top),
                        count: columnCount
                    ),
                    alignment: .leading,
                    spacing: 10
                ) {
                    ForEach(family.workflows) { workflow in
                        variantRow(workflow)
                    }
                }
                .padding(12)
            }
            .frame(maxHeight: 440)
        }
        .frame(width: CGFloat(columnCount) * 250 + 30)
    }

    @ViewBuilder
    private func variantRow(_ workflow: WorkflowSidebarItem) -> some View {
        VStack(alignment: .leading, spacing: 0) {
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
                    if let onInspect {
                        Button {
                            onInspect(workflow)
                        } label: {
                            Image(systemName: "info.circle")
                                .font(.system(size: 11))
                                .foregroundStyle(.tint)
                        }
                        .buttonStyle(.plain)
                        .help("Open \(workflow.displayName) in the node editor")
                        .accessibilityLabel("Open \(workflow.displayName) in the node editor")
                    }
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
                        // FULL description (Daniel, 2026-08-29: "show full
                        // description") — the preset's "use this when" prose
                        // is the whole point of the card.
                        .fixedSize(horizontal: false, vertical: true)
                }

                Text("\(workflow.effectiveStepCount) step(s) in this workflow")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Add \(workflow.displayName) to the chain")

        // OUTSIDE the add button: expanding to read a prompt must not stage
        // the workflow. Two different intentions, two different targets.
        WorkflowStepsDisclosure(workflowId: workflow.id)
            .padding(.horizontal, 10)
            .padding(.bottom, 8)
        }
        .background(.quaternary.opacity(0.3), in: RoundedRectangle(cornerRadius: 8))
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
