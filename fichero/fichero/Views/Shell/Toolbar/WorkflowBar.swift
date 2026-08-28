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
    /// Labels under the glyphs. Off gives a dense icon rail; on names every
    /// verb for someone still learning the vocabulary (Daniel, 2026-08-28).
    var showsLabels: Bool = true
    /// The chain being assembled. Clicking a verb APPENDS to this rather
    /// than running (Daniel, 2026-08-28: "it shouldn't run right away, it
    /// should construct the chain") — the run is one deliberate press of ▶,
    /// which is what makes a paid multi-step job over a folder safe to build.
    @Binding var staged: [WorkflowSidebarItem]
    /// Runs the staged chain, in order.
    let onRunChain: () -> Void
    /// True while the chain is running — ▶ becomes a progress affordance.
    var isRunning: Bool = false

    /// One item's footprint. Fixed so the verbs sit on an even rhythm the way
    /// toolbar items do, rather than jittering with label length.
    private var itemWidth: CGFloat { showsLabels ? 68 : 34 }

    private var families: [WorkflowBarPolicy.VerbFamily] {
        WorkflowBarPolicy.families(from: workflows, target: target)
    }

    var body: some View {
        VStack(spacing: 0) {
            verbRow
            // The chain gets its OWN full-width row rather than a slot on the
            // right (Daniel, 2026-08-28: "to right seems a bit small"). An
            // eight-step chain — regions, transcribe, review, entities, SVO,
            // merge, persist, catalogue — has no chance in a corner, and the
            // split is honest besides: the top row is what you CAN do, this one
            // is what you are ABOUT to do.
            if !staged.isEmpty {
                Divider()
                chainRow
            }
        }
        .background(.bar)
        .overlay(alignment: .bottom) { Divider() }
    }

    private var verbRow: some View {
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
    }

    /// The chain: full width, left-aligned so it reads as a sequence, with the
    /// run control and the step count anchored right.
    private var chainRow: some View {
        HStack(spacing: 8) {
            ScrollView(.horizontal, showsIndicators: false) {
                chainRail.padding(.horizontal, 10)
            }
            Spacer(minLength: 0)
            Text(staged.count == 1 ? "1 step" : "\(staged.count) steps")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.trailing, 10)
        }
        .frame(height: 34)
    }

    /// The chain being assembled: one chip per step, in order, each removable.
    ///
    /// Horizontal and icon-led because a chain is a SEQUENCE and sequences read
    /// left to right — the same reading as the node canvas, which is what makes
    /// the rail a miniature of the graph rather than a second idiom. Eight
    /// steps is a real chain here (regions, transcribe, review, entities, SVO,
    /// merge, persist, catalogue), so chips stay compact enough to all fit.
    @ViewBuilder
    private var chainRail: some View {
        HStack(spacing: 3) {
            ForEach(Array(staged.enumerated()), id: \.offset) { index, workflow in
                if index > 0 {
                    Image(systemName: "arrow.right")
                        .font(.system(size: 7))
                        .foregroundStyle(.tertiary)
                }
                HStack(spacing: 3) {
                    Image(systemName: WorkflowBarPolicy.symbol(
                        forFamily: WorkflowBarPolicy.folderKey(workflow.folderPath)
                    ))
                    .font(.system(size: 11))
                    // The name is redundant beside a glyph whose tooltip
                    // already says it, and eight labelled chips do not fit
                    // (Daniel, 2026-08-28). It follows the bar's own label
                    // preference so both readings are one toggle apart.
                    if showsLabels {
                        Text(workflow.name)
                            .font(.system(size: 10))
                            .lineLimit(1)
                    }
                    Button {
                        staged.remove(at: index)
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 7))
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Remove \(workflow.name) from the chain")
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(Color.accentColor.opacity(0.12), in: Capsule())
                // The whole chip names its step, so an icon-only rail stays
                // readable on hover rather than becoming a rebus.
                .help("Step \(index + 1): \(workflow.displayName)")
            }

            Button(action: onRunChain) {
                Image(systemName: isRunning ? "stop.circle.fill" : "play.circle.fill")
                    .font(.title3)
                    .foregroundStyle(isRunning ? Color.secondary : Color.accentColor)
            }
            .buttonStyle(.plain)
            .disabled(isRunning)
            .help(isRunning
                  ? "Chain is running"
                  : "Run \(staged.count) step(s) in order on the selection")
            .accessibilityLabel("Run the chain")

            Button { staged.removeAll() } label: {
                Image(systemName: "trash")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .disabled(isRunning)
            .help("Clear the chain")
        }
        .fixedSize()
    }

    /// One verb, drawn as a toolbar item: glyph above, small label below.
    ///
    /// A plain `Button` owns the layout deliberately. A `Menu` re-flows its own
    /// label on macOS, which is why the first attempt at this kept rendering
    /// the name BESIDE the glyph however the label was composed. The variants
    /// live behind a separate chevron, shown only when there is more than one.
    @ViewBuilder
    private func familyItem(_ family: WorkflowBarPolicy.VerbFamily) -> some View {
        HStack(spacing: 0) {
            Button {
                if let first = family.workflows.first { stage(first) }
            } label: {
                VStack(spacing: 1) {
                    Image(systemName: family.symbol)
                        .font(.body)
                        .frame(height: 17)
                    if showsLabels {
                        Text(family.title)
                            .font(.system(size: 9))
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                    }
                }
                .frame(width: itemWidth)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help(helpText(for: family))
            .accessibilityLabel(helpText(for: family))

            if family.workflows.count > 1 {
                Menu {
                    ForEach(family.workflows) { workflow in
                        Button(workflow.displayName) { stage(workflow) }
                    }
                } label: {
                    Image(systemName: "chevron.down")
                        .font(.system(size: 8))
                        .foregroundStyle(.secondary)
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
                .help("Choose a \(family.title) variant — \(family.workflows.count) available")
            }
        }
    }

    private func stage(_ workflow: WorkflowSidebarItem) {
        staged.append(workflow)
    }

    private func helpText(for family: WorkflowBarPolicy.VerbFamily) -> String {
        let count = family.workflows.count
        guard let first = family.workflows.first else { return family.title }
        return count == 1
            ? "Add \(first.displayName) to the chain"
            : "Add \(first.displayName) to the chain — \(count) variants available"
    }
}
