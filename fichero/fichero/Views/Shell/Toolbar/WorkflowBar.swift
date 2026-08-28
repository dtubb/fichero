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
/// inspector too, claiming a scope it does not have.
///
/// Items follow the NATIVE toolbar grammar (Daniel, 2026-08-28): a larger
/// centred glyph with a small label beneath it, not a glyph with the label
/// beside it. Vertical stacking is what lets a dozen verbs read as a toolbar
/// rather than as a sentence, and it is the shape of both Fichero's own
/// Library/Preview/Reader/Chat items and Preview's markup bar.
struct WorkflowBar: View {
    let workflows: [WorkflowSidebarItem]
    let target: WorkflowBarPolicy.Target
    /// `(workflowId, provider, model)` — provider/model are nil for a default
    /// run, and carry the pick when one is made from a variant's submenu.
    let onRun: (String, String?, String?) -> Void

    /// One item's footprint. Fixed so the verbs sit on an even rhythm the way
    /// toolbar items do, rather than jittering with label length.
    private let itemWidth: CGFloat = 68

    private var families: [WorkflowBarPolicy.VerbFamily] {
        WorkflowBarPolicy.families(from: workflows, target: target)
    }

    var body: some View {
        HStack(spacing: 0) {
            if let reason = WorkflowBarPolicy.emptyReason(from: workflows, target: target) {
                // An empty bar with no explanation reads as a broken app rather
                // than as "nothing applies to this".
                Text(reason)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.leading, 12)
                Spacer(minLength: 0)
            } else {
                // Horizontal scroll rather than clipping: a library with many
                // preset folders overflows any toolbar width, and a verb the
                // user cannot reach is the same as a verb that does not exist.
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 2) {
                        ForEach(families) { family in
                            familyItem(family)
                        }
                    }
                    .padding(.horizontal, 8)
                }
            }

            if let label = WorkflowBarPolicy.targetLabel(target) {
                Divider().frame(height: 28).padding(.horizontal, 6)
                // What the run will act on, stated BEFORE it starts — a paid
                // multi-step run over a folder should never be ambiguous about
                // its scope.
                Label(label, systemImage: "scope")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize()
                    .padding(.trailing, 12)
                    .accessibilityLabel("Will run on \(label)")
            }
        }
        .frame(height: 52)
        .background(.bar)
        .overlay(alignment: .bottom) { Divider() }
    }

    /// One verb, drawn as a toolbar item: glyph above, small label below.
    @ViewBuilder
    private func familyItem(_ family: WorkflowBarPolicy.VerbFamily) -> some View {
        Menu {
            ForEach(family.workflows) { workflow in
                Button(workflow.displayName) { onRun(workflow.id, nil, nil) }
            }
        } label: {
            VStack(spacing: 2) {
                Image(systemName: family.symbol)
                    // Semantic size, not a hard-coded point size, so the item
                    // tracks the user's text size like the native toolbar does.
                    .font(.title3)
                    .frame(height: 20)
                Text(family.title)
                    .font(.caption2)
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
            }
            .frame(width: itemWidth)
            .contentShape(Rectangle())
        } primaryAction: {
            // Clicking the verb runs its first variant — the menu is for
            // choosing a different one, not a toll on every run.
            if let first = family.workflows.first {
                onRun(first.id, nil, nil)
            }
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .buttonStyle(.plain)
        .help(helpText(for: family))
        .accessibilityLabel(helpText(for: family))
    }

    private func helpText(for family: WorkflowBarPolicy.VerbFamily) -> String {
        let count = family.workflows.count
        guard let first = family.workflows.first else { return family.title }
        return count == 1
            ? "Run \(first.displayName)"
            : "Run \(first.displayName) — \(count) variants available"
    }
}
