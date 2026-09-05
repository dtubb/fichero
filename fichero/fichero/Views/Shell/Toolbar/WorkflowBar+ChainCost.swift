import SwiftUI

/// The chain's COST chip and its per-step breakdown.
///
/// Split out of `WorkflowBar+ChainRow` (2026-09-05) both to keep that type
/// under SwiftLint's body-length rule and because the cut is honest: the row
/// decides how much room the sentence gets, this file prices the run the
/// sentence describes. The chip states one of three things and NEVER "US$0.00"
/// for a price miss (Daniel screenshotted exactly that on a real paid chain):
///
///   • nothing priced         → "est. unpriced"
///   • some steps unpriceable  → "est. ≥ $X · N unpriced"   (a FLOOR)
///   • every step priced       → "est. ≤ $X"                (a CEILING)
///
/// Expanding it lists one line per step, each naming the model that step will
/// really run on beside its own estimate — the routing truth read before a
/// paid run, so "which model, at what cost" is answerable pre-flight.
extension WorkflowBar {

    @ViewBuilder
    func chainCostChip(_ cost: StagedChainCost) -> some View {
        Button {
            showsCostBreakdown.toggle()
        } label: {
            chainCostSummary(cost)
        }
        .buttonStyle(.plain)
        .help(chainCostHelp(cost))
        .accessibilityLabel(chainCostAccessibility(cost))
        .popover(isPresented: $showsCostBreakdown, arrowEdge: .bottom) {
            costBreakdown(cost)
        }
    }

    @ViewBuilder
    private func chainCostSummary(_ cost: StagedChainCost) -> some View {
        HStack(spacing: 3) {
            if !cost.hasPricedStep {
                // A price MISS is a QUESTION, not a zero. "unpriced" is the
                // honest word; "US$0.00" told the user a paid run was free.
                Text("est. unpriced")
            } else if cost.isCompletePricing {
                // A CEILING — every step priced, so the sum is an upper bound
                // the run can be held to.
                Text("est. ≤ \(cost.pricedTotal, format: .currency(code: "USD"))")
                    .monospacedDigit()
            } else {
                // A FLOOR — the priced steps are a lower bound on a total whose
                // unpriced tail is unknown. "≥", with the tail named, so the
                // number is never mistaken for the whole bill.
                Text("est. ≥ \(cost.pricedTotal, format: .currency(code: "USD"))")
                    .monospacedDigit()
                Text("· \(cost.unpricedCount) unpriced")
                    .foregroundStyle(.tertiary)
            }
            Image(systemName: "chevron.down")
                .font(.system(size: 7))
                .foregroundStyle(.tertiary)
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
    }

    /// The expanded breakdown: one line per step, each naming the model it will
    /// really run on and its own estimate — routing truth, read before the run.
    @ViewBuilder
    private func costBreakdown(_ cost: StagedChainCost) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Estimated cost per step")
                .font(.caption.weight(.semibold))
            ForEach(Array(staged.enumerated()), id: \.element.id) { index, step in
                HStack(spacing: 6) {
                    Text("\(index + 1).")
                        .foregroundStyle(.tertiary)
                        .monospacedDigit()
                    Text(step.name)
                        .lineLimit(1)
                    if stepTakesModel(step) {
                        Text("·").foregroundStyle(.quaternary)
                        Text(breakdownModelLabel(for: step))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 12)
                    breakdownAmount(for: step, in: cost)
                }
                .font(.caption)
            }
            Divider()
            chainCostTotalLine(cost)
        }
        .padding(12)
        .frame(minWidth: 260, maxWidth: 360, alignment: .leading)
    }

    /// One step's amount in the breakdown — its price, "free" for a real zero,
    /// or "unpriced" for a miss. The three are kept distinct on purpose.
    @ViewBuilder
    private func breakdownAmount(
        for step: StagedWorkflowStep, in cost: StagedChainCost
    ) -> some View {
        if let line = cost.line(forStepId: step.id), let estimate = line.estimate {
            if estimate == 0 {
                Text("free").foregroundStyle(.secondary).monospacedDigit()
            } else {
                Text(estimate, format: .currency(code: "USD"))
                    .monospacedDigit()
            }
        } else {
            Text("unpriced").foregroundStyle(.tertiary)
        }
    }

    /// The breakdown's footer: the same sentence the chip states, spelled out.
    @ViewBuilder
    private func chainCostTotalLine(_ cost: StagedChainCost) -> some View {
        HStack {
            if !cost.hasPricedStep {
                Text("No step could be priced")
                    .foregroundStyle(.secondary)
            } else if cost.isCompletePricing {
                Text("Upper bound")
                Spacer()
                Text(cost.pricedTotal, format: .currency(code: "USD"))
                    .monospacedDigit()
            } else {
                Text("At least (\(cost.unpricedCount) unpriced)")
                Spacer()
                Text(cost.pricedTotal, format: .currency(code: "USD"))
                    .monospacedDigit()
            }
        }
        .font(.caption.weight(.medium))
    }

    /// The model a breakdown line names — the SAME resolution the sentence's
    /// model token uses, so the two can never disagree about what a step runs.
    private func breakdownModelLabel(for step: StagedWorkflowStep) -> String {
        if let choice = effectiveChoice(for: step), !choice.model.isEmpty {
            return ModelChipToolbarItem.shorten(choice.model)
        }
        return resolvedDefaultModelLabel(for: step)
    }

    private func chainCostHelp(_ cost: StagedChainCost) -> String {
        if !cost.hasPricedStep {
            return "No step in this chain could be priced from the model "
                + "registry. Click for the per-step breakdown."
        }
        if cost.isCompletePricing {
            return "Estimated upper bound for this chain over \(staged.count) "
                + "step(s), priced from the live model registry. Click for the "
                + "per-step breakdown."
        }
        return "Estimated lower bound: \(cost.unpricedCount) of \(staged.count) "
            + "step(s) could not be priced and are not in the total. Click for "
            + "the per-step breakdown."
    }

    private func chainCostAccessibility(_ cost: StagedChainCost) -> String {
        if !cost.hasPricedStep { return "Estimated cost: unpriced" }
        let amount = cost.pricedTotal.formatted(.currency(code: "USD"))
        if cost.isCompletePricing { return "Estimated cost at most \(amount)" }
        return "Estimated cost at least \(amount), \(cost.unpricedCount) unpriced"
    }
}
