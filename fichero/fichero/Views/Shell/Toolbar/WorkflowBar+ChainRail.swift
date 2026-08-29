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
        HStack(spacing: 3) {
            ForEach(Array(staged.enumerated()), id: \.element.id) { index, step in
                if index > 0 {
                    Image(systemName: "arrow.right")
                        .font(.system(size: 7))
                        .foregroundStyle(.tertiary)
                }
                chainChip(step, at: index)
            }

        }
        .fixedSize()
    }

    /// One step. Extracted from `chainRail` because the inline expression grew
    /// past the Swift type-checker's budget — the documented hazard in this
    /// codebase's view layer, and the reason the shell's layout is already
    /// split across several properties.
    @ViewBuilder
    private func chainChip(_ step: StagedWorkflowStep, at index: Int) -> some View {
        chipBody(step, at: index)
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(chipBackground(for: step), in: Capsule())
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
            .font(.system(size: 11))

            if showsLabels {
                Text(step.name)
                    .font(.system(size: 10))
                    .lineLimit(1)
            }
            if let symbol = chipSymbol(for: step) {
                Image(systemName: symbol)
                    .font(.system(size: 8))
            }
            // A pinned model is stated ON the chip: a chain whose steps run on
            // different models must show which, or the cheap step and the
            // expensive one look identical.
            if step.hasModelOverride {
                Text(step.modelDescription)
                    .font(.system(size: 8))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Button { staged.remove(at: index) } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 7))
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
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
        staged.insert(moved, at: min(index, staged.count))
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
