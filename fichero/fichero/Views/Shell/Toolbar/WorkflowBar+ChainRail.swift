import SwiftUI

/// The chain rail — the chips under the verb row, in run order.
///
/// Split out of `WorkflowBar` (2026-08-28) once the bar crossed SwiftLint's
/// file- and type-length rules. The division is the one the UI already makes:
/// the verb row is what you can ADD, the rail is what you have BUILT. Kept as
/// an extension rather than a separate view so the chips keep reading `staged`
/// as a binding and writing back into it directly, which is what makes
/// drag-to-reorder and per-chip removal one-liners.
extension WorkflowBar {
    /// The chain being assembled: one chip per step, in order, each removable.
    ///
    /// Horizontal and icon-led because a chain is a SEQUENCE and sequences read
    /// left to right — the same reading as the node canvas, which is what makes
    /// the rail a miniature of the graph rather than a second idiom. Eight
    /// steps is a real chain here (regions, transcribe, review, entities, SVO,
    /// merge, persist, catalogue), so chips stay compact enough to all fit.
    @ViewBuilder
    var chainRail: some View {
        // A SENTENCE, not a symbol chain (Daniel, 2026-08-29: "could this not
        // have verbs and subjects — With [3 selected items] use [model] to
        // detect regions, then use [model] to extract transcript"). The
        // subject, each step's model and the step itself are live tokens; the
        // connective tissue is plain words, which is what makes an eight-step
        // paid run readable as a plan rather than a rebus.
        ChainFlowLayout(
            spacing: 5, rowSpacing: WorkflowBar.chainRailRowSpacing
        ) {
            contextToken
            Text("With")
                .font(WorkflowBar.chainConnectiveFont)
                .foregroundStyle(.secondary)
            if let label = targetDetail ?? WorkflowBarPolicy.targetLabel(target) {
                subjectToken(label)
            } else {
                Text("nothing selected")
                    .font(WorkflowBar.chainConnectiveFont)
                    .foregroundStyle(.tertiary)
            }
            Text(",")
                .font(WorkflowBar.chainConnectiveFont)
                .foregroundStyle(.secondary)
                .padding(.leading, -5)
            ForEach(Array(staged.enumerated()), id: \.element.id) { index, step in
                Text(index == 0 ? "use" : "then use")
                    .font(WorkflowBar.chainConnectiveFont)
                    .foregroundStyle(.secondary)
                modelToken(for: step, at: index)
                Text("to")
                    .font(WorkflowBar.chainConnectiveFont)
                    .foregroundStyle(.secondary)
                chainChip(step, at: index)
            }
        }
    }

    /// The sentence's SUBJECT as a clickable token (Daniel, 2026-08-29): the
    /// chip that names the scope is also where you CHANGE it — aim the run
    /// at the browser selection, the focused artifact, or an artifact by
    /// type. "Automatic" (always first) restores the ladder. Falls back to a
    /// plain label when the host provides no menu.
    @ViewBuilder
    private func subjectToken(_ label: String) -> some View {
        if let onSelectScope, !scopeOptions.isEmpty {
            Menu {
                ForEach(scopeOptions) { option in
                    Button(option.label) { onSelectScope(option.scope) }
                }
            } label: {
                subjectLabel(label)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Choose what the chain runs on")
            .accessibilityLabel("Run scope: \(label)")
        } else {
            subjectLabel(label)
        }
    }

    /// The chip itself — shared by the menu label and the plain fallback so
    /// a clickable subject looks exactly like a static one.
    private func subjectLabel(_ label: String) -> some View {
        Label {
            Text(label)
        } icon: {
            Image(systemName: "scope")
        }
        .labelStyle(ChainTokenLabelStyle())
        .chainTokenLozenge(tint: Color.accentColor.opacity(0.12))
    }

    /// The step's model as a clickable token in the sentence. The same menu
    /// the chip's right-click offers — one wiring, two doors.
    @ViewBuilder
    private func modelToken(for step: StagedWorkflowStep, at index: Int) -> some View {
        Menu {
            modelMenu(forStepAt: index)
        } label: {
            // A real LOZENGE, not a whisper of one (Daniel, 2026-08-29:
            // "model needs lozenges") — same weight as the subject chip so
            // the sentence's three token kinds read as one family.
            //
            // It NAMES the model even when nothing is pinned (Daniel,
            // 2026-08-31): "default model" told the reader that a model had
            // been chosen without saying which, and the whole point of the
            // sentence is that a paid run states what it will actually do.
            // Still TEXT — the name is the fact a paid run has to state — but
            // with the family's mark in front of it (Daniel, 2026-09-01:
            // "keep the model as text but add the provider/model icon"). The
            // logo is what lets the eye find "the Claude step" in an
            // eight-step sentence without reading every lozenge.
            Label {
                Text(step.hasModelOverride
                     ? step.modelDescription
                     : resolvedDefaultModelLabel(for: step))
            } icon: {
                ModelFamilyMark(
                    model: step.modelOverride ?? resolvedDefaultModelId(for: step),
                    provider: step.providerOverride ?? resolvedDefaultModelProvider(for: step),
                    side: 12
                )
            }
            .labelStyle(ChainTokenLabelStyle())
            .foregroundStyle(step.hasModelOverride ? Color.primary : Color.secondary)
            .chainTokenLozenge(tint: Color.accentColor.opacity(0.10))
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .disabled(isRunning)
        .help(step.hasModelOverride
              ? "This step is pinned to \(step.modelDescription) — click to change it"
              : "This step runs on \(resolvedDefaultModelLabel(for: step)), the "
              + "configured \(defaultTierName(for: step)) default for what this "
              + "step does — click to pin a different model")
        .accessibilityLabel(
            step.hasModelOverride
                ? "Model: \(step.modelDescription)"
                : "Model: \(resolvedDefaultModelLabel(for: step)) (default)"
        )
    }

    /// One step. Extracted from `chainRail` because the inline expression grew
    /// past the Swift type-checker's budget — the documented hazard in this
    /// codebase's view layer, and the reason the shell's layout is already
    /// split across several properties.
    @ViewBuilder
    private func chainChip(_ step: StagedWorkflowStep, at index: Int) -> some View {
        chipBody(step, at: index)
            .chainTokenLozenge(tint: chipBackground(for: step))
            .foregroundStyle(chipForeground(for: step))
            .overlay(alignment: .leading) { chipLeadingAccessory(step, at: index) }
            .help(chipHelp(for: step, index: index))
            .contextMenu { modelMenu(forStepAt: index) }
            // A RUNNING step opens on a single click — you are watching it, and
            // asking for a double-click to see live output is a toll on the one
            // moment it matters. A finished step keeps the double-click, so a
            // stray click while assembling cannot fling a window open.
            .onTapGesture(count: 2) { onOpenStep?(step) }
            .onTapGesture { if step.state == .running { onOpenStep?(step) } }
            .draggable(step.id.uuidString) {
                Text(step.name).font(.caption).padding(4)
            }
            .dropDestination(for: String.self) { items, _ in
                handleChipDrop(items, at: index)
            } isTargeted: { targeted in
                dropTargetIndex = targeted ? index : (dropTargetIndex == index ? nil : dropTargetIndex)
            }
    }

    @ViewBuilder
    private func chipBody(_ step: StagedWorkflowStep, at index: Int) -> some View {
        HStack(spacing: 3) {
            Image(systemName: step.toolIcon ?? folders[
                WorkflowBarPolicy.folderKey(step.folderPath)
            ]?.icon ?? WorkflowBarPolicy.symbol(
                forFamily: WorkflowBarPolicy.folderKey(step.folderPath)
            ))
            .font(WorkflowBar.chainTokenFont)

            if showsLabels {
                // The SAME type as the subject and model tokens (Daniel,
                // 2026-09-01: "render each part as a lozenge with the same
                // text style"). The step used to be a size-10 regular next to
                // two size-10 mediums, which read as a caption dropped into a
                // sentence rather than as its verb.
                Text(step.name)
                    .font(WorkflowBar.chainTokenFont)
                    .lineLimit(1)
            }
            if let symbol = chipSymbol(for: step) {
                Image(systemName: symbol)
                    .font(.system(size: 8))
            }
            // The model moved OUT of the chip into the sentence's own
            // "use [model] to" token (2026-08-29) — stating it twice made
            // every chip wider for nothing.
            Button { staged.remove(at: index) } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 7))
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            // The run's plan froze at ▶ — removing a chip mid-run would not
            // stop its step, just hide a billed run from the rail (review,
            // 2026-08-29). Same rule as Run/Clear.
            .disabled(isRunning)
            .help("Remove \(step.name) from the chain")
            .accessibilityLabel("Remove \(step.name) from the chain")
        }
    }

    /// The running spinner, or the caret marking where a dragged step lands.
    @ViewBuilder
    private func chipLeadingAccessory(_ step: StagedWorkflowStep, at index: Int) -> some View {
        if step.state == .running {
            ProgressView()
                .controlSize(.mini)
                .scaleEffect(0.55)
                .offset(x: -3)
        } else if dropTargetIndex == index {
            Rectangle()
                .fill(Color.accentColor)
                .frame(width: 2)
                .offset(x: -3)
        }
    }

    private func handleChipDrop(_ items: [String], at index: Int) -> Bool {
        guard let raw = items.first,
              let from = staged.firstIndex(where: { $0.id.uuidString == raw }),
              from != index
        else { return false }
        let moved = staged.remove(at: from)
        // Land where the caret POINTS — the leading edge of the target chip.
        // Removing first shifts a rightward target left by one, so without
        // this the drop landed one slot past the indicator (review,
        // 2026-08-29: the caret and the drop disagreed in that direction).
        let destination = from < index ? index - 1 : index
        staged.insert(moved, at: min(destination, staged.count))
        return true
    }

    /// What the chip promises on hover — including HOW to open it, which
    /// differs by state and would otherwise be undiscoverable.
    private func chipHelp(for step: StagedWorkflowStep, index: Int) -> String {
        let base = "Step \(index + 1): \(step.displayName) — \(step.modelDescription)"
        switch step.state {
        case .running:   return "\(base). Click to watch it run."
        case .succeeded: return "\(base). Double-click to see what it produced."
        case .failed:    return "\(base). This step failed — double-click to see why."
        case .pending:   return "\(base). Drag to reorder; right-click to pin a model."
        }
    }

    /// Colour states the step's OUTCOME, not merely its position: a chain
    /// that half finished must not read as uniformly blue. Green succeeded,
    /// red failed, emphasised accent running, quiet accent still to come.
    private func chipBackground(for step: StagedWorkflowStep) -> Color {
        switch step.state {
        case .pending:   return Color.accentColor.opacity(0.12)
        case .running:   return Color.accentColor.opacity(0.30)
        case .succeeded: return Color.green.opacity(0.20)
        case .failed:    return Color.red.opacity(0.20)
        }
    }

    private func chipForeground(for step: StagedWorkflowStep) -> Color {
        switch step.state {
        case .succeeded: return .green
        case .failed:    return .red
        default:         return .primary
        }
    }

    private func chipSymbol(for step: StagedWorkflowStep) -> String? {
        switch step.state {
        case .succeeded: return "checkmark"
        case .failed:    return "exclamationmark.triangle"
        default:         return nil
        }
    }}

/// ONE lozenge for every part of the sentence (Daniel, 2026-09-01: "render
/// each part — selection, model, step — as a lozenge with the same text
/// style"). The three tokens used to carry three different paddings, two
/// fonts and an inconsistent border; only the TINT is meant to differ, since
/// the tint is what carries a step's outcome.
struct ChainTokenLozenge: ViewModifier {
    let tint: Color

    func body(content: Content) -> some View {
        content
            .font(WorkflowBar.chainTokenFont)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(tint, in: Capsule())
            .overlay(Capsule().strokeBorder(.quaternary, lineWidth: 1))
    }
}

extension View {
    func chainTokenLozenge(tint: Color) -> some View {
        modifier(ChainTokenLozenge(tint: tint))
    }
}

/// Icon-then-text on one baseline, tight enough for a 10pt lozenge —
/// `.titleAndIcon` leaves a gap sized for body text, which pushed the
/// sentence's tokens apart.
struct ChainTokenLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 3) {
            configuration.icon
            configuration.title
        }
    }
}

extension WorkflowBar {
    /// The sentence's one type style, worn by every token.
    static let chainTokenFont = Font.system(size: 10, weight: .medium)
    /// The plain words between tokens — same size, unemphasised, so the
    /// lozenges are what the eye lands on.
    static let chainConnectiveFont = Font.system(size: 10)
}

/// A minimal flow layout: rows wrap, the container grows (Daniel,
/// 2026-08-29: "if it's multiple rows, make the rows expand so we can
/// see"). Just enough Layout for the sentence — leading-aligned, fixed
/// spacing, no fancy distribution.
struct ChainFlowLayout: Layout {
    var spacing: CGFloat = 5
    var rowSpacing: CGFloat = 6

    func sizeThatFits(
        proposal: ProposedViewSize, subviews: Subviews, cache: inout ()
    ) -> CGSize {
        let width = proposal.width ?? .infinity
        var cursorX: CGFloat = 0, cursorY: CGFloat = 0, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if cursorX > 0, cursorX + size.width > width {
                cursorX = 0
                cursorY += rowHeight + rowSpacing
                rowHeight = 0
            }
            cursorX += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: proposal.width ?? cursorX, height: cursorY + rowHeight)
    }

    func placeSubviews(
        in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews,
        cache: inout ()
    ) {
        var cursorX = bounds.minX, cursorY = bounds.minY, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if cursorX > bounds.minX, cursorX + size.width > bounds.maxX {
                cursorX = bounds.minX
                cursorY += rowHeight + rowSpacing
                rowHeight = 0
            }
            subview.place(
                at: CGPoint(x: cursorX, y: cursorY),
                anchor: .topLeading,
                proposal: .unspecified
            )
            cursorX += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
