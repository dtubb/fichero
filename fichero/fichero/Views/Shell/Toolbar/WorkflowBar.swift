import SwiftUI

/// The capability bar — verbs that can act on what is selected, above the
/// content (2026-08-28).
///
/// Fichero ships ~90 tools and ~50 workflows and showed none of them outside
/// the node editor, so nothing ever told a user what the app could do to the
/// page in front of them. This bar is a projection of the selection through
/// each workflow's server-declared `accepted_inputs`: select a page and the
/// vision verbs appear, select a passage and only the verbs taking text do.
/// The decision itself lives in `WorkflowBarPolicy`, with no SwiftUI in it, so
/// it is tested without a window.
///
/// Deliberately NOT a second window-spanning toolbar row: it acts on the
/// CONTENT selection, and a full-width row would sit above the sidebar and
/// inspector too, claiming a scope it does not have. Sitting on the content
/// pane also means it survives either side pane being resized.
struct WorkflowBar: View {
    let workflows: [WorkflowSidebarItem]
    let target: WorkflowBarPolicy.Target
    /// `(workflowId, provider, model)` — provider/model are nil for a default
    /// run, and carry the pick when one is made from a variant's submenu.
    let onRun: (String, String?, String?) -> Void

    private var families: [WorkflowBarPolicy.VerbFamily] {
        WorkflowBarPolicy.families(from: workflows, target: target)
    }

    var body: some View {
        HStack(spacing: 8) {
            if let reason = WorkflowBarPolicy.emptyReason(from: workflows, target: target) {
                // An empty bar with no explanation reads as a broken app rather
                // than as "nothing applies to this".
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(families) { family in
                    familyMenu(family)
                }
            }

            Spacer(minLength: 0)

            if let label = WorkflowBarPolicy.targetLabel(target) {
                // What the run will act on, stated BEFORE it starts — a paid
                // multi-step run over a folder should never be ambiguous about
                // its scope.
                Label(label, systemImage: "scope")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .labelStyle(.titleAndIcon)
                    .accessibilityLabel("Will run on \(label)")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.bar)
        .overlay(alignment: .bottom) { Divider() }
    }

    /// One verb: the family's variants in a menu, with the first entry running
    /// the family's default so the common case is two clicks, not three.
    @ViewBuilder
    private func familyMenu(_ family: WorkflowBarPolicy.VerbFamily) -> some View {
        Menu {
            ForEach(family.workflows) { workflow in
                Button(workflow.displayName) { onRun(workflow.id, nil, nil) }
            }
        } label: {
            Label(family.title, systemImage: family.symbol)
        } primaryAction: {
            // Clicking the verb itself runs its first variant — the menu is
            // for choosing a different one, not a toll on every run.
            if let first = family.workflows.first {
                onRun(first.id, nil, nil)
            }
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help(helpText(for: family))
    }

    private func helpText(for family: WorkflowBarPolicy.VerbFamily) -> String {
        let count = family.workflows.count
        guard let first = family.workflows.first else { return family.title }
        return count == 1
            ? "Run \(first.displayName)"
            : "Run \(first.displayName) — \(count) variants available"
    }
}
