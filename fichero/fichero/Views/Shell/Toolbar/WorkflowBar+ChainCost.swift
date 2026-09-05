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
/// Once the chain has RUN, `chainActualCost` is present and the chip flips from
/// the estimate to what the run actually SPENT — read from each step's run
/// accounting, the same number Activity shows — pairing the two as
/// "est $X → $Y" so the estimate can be judged against the bill.
///
/// Expanding it lists one line per step, each naming the model that step will
/// really run on beside its own estimate (and its actual, after the run) — the
/// routing truth read before a paid run, so "which model, at what cost" is
/// answerable pre-flight.
extension WorkflowBar {

    @ViewBuilder
    func chainCostChip(_ estimate: StagedChainCost) -> some View {
        Button {
            showsCostBreakdown.toggle()
        } label: {
            chainCostSummary(estimate)
        }
        .buttonStyle(.plain)
        .help(chainCostHelp(estimate))
        .accessibilityLabel(chainCostAccessibility(estimate))
        .popover(isPresented: $showsCostBreakdown, arrowEdge: .bottom) {
            costBreakdown(estimate)
        }
    }

    /// The chip face: the estimate before a run, and "est $X → $Y" (the actual
    /// leading) once the run has recorded what it spent.
    @ViewBuilder
    private func chainCostSummary(_ estimate: StagedChainCost) -> some View {
        HStack(spacing: 3) {
            if let actual = chainActualCost {
                // Calibration: the estimate, quietly, then what it actually
                // cost. The estimate is only shown when it HAD a figure — an
                // unpriced estimate has nothing to calibrate against.
                if estimate.hasPricedStep {
                    Text("est \(estimate.pricedTotal, format: .currency(code: "USD")) →")
                        .foregroundStyle(.tertiary)
                        .monospacedDigit()
                }
                amountPhrase(actual, prefix: nil)
            } else {
                amountPhrase(estimate, prefix: "est.")
            }
            Image(systemName: "chevron.down")
                .font(.system(size: 7))
                .foregroundStyle(.tertiary)
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
    }

    /// The ≤/≥/unpriced phrase for one cost, with an optional leading word
    /// ("est." for the estimate; nil for the measured actual). Shared so an
    /// estimate and an actual read in the same grammar.
    @ViewBuilder
    private func amountPhrase(_ cost: StagedChainCost, prefix: String?) -> some View {
        let lead = prefix.map { "\($0) " } ?? ""
        if !cost.hasPricedStep {
            // A price MISS is a QUESTION, not a zero. "unpriced" is the honest
            // word; "US$0.00" told the user a paid run was free.
            Text("\(lead)unpriced")
        } else if cost.isCompletePricing {
            // A CEILING (estimate) or the settled total (actual): every step
            // priced, so the sum is the whole figure.
            Text("\(lead)≤ \(cost.pricedTotal, format: .currency(code: "USD"))")
                .monospacedDigit()
        } else {
            // A FLOOR — priced steps are a lower bound on a total whose unpriced
            // tail is unknown. "≥", with the tail named.
            Text("\(lead)≥ \(cost.pricedTotal, format: .currency(code: "USD"))")
                .monospacedDigit()
            Text("· \(cost.unpricedCount) unpriced")
                .foregroundStyle(.tertiary)
        }
    }

    /// The expanded breakdown: one line per step, each naming the model it will
    /// really run on and its estimate — and, after the run, its actual too.
    @ViewBuilder
    private func costBreakdown(_ estimate: StagedChainCost) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(chainActualCost == nil
                 ? "Estimated cost per step"
                 : "Cost per step — est → actual (run total)")
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
                    breakdownAmounts(for: step, estimate: estimate)
                }
                .font(.caption)
            }
            Divider()
            chainCostTotalLine(estimate)
        }
        .padding(12)
        .frame(minWidth: 280, maxWidth: 380, alignment: .leading)
    }

    /// One step's amount(s): the estimate, and after a run "→ actual". Free,
    /// priced and unpriced are kept distinct in each.
    @ViewBuilder
    private func breakdownAmounts(
        for step: StagedWorkflowStep, estimate: StagedChainCost
    ) -> some View {
        HStack(spacing: 4) {
            amountText(estimate.line(forStepId: step.id)?.estimate)
                .foregroundStyle(chainActualCost == nil ? .primary : .secondary)
            if let actual = chainActualCost {
                Text("→").foregroundStyle(.quaternary)
                amountText(actual.line(forStepId: step.id)?.estimate)
            }
        }
        .monospacedDigit()
    }

    /// A single amount cell: the price, "free" for a real zero, "—" for a miss
    /// or a step with no line yet (optional chaining flattens both to nil).
    @ViewBuilder
    private func amountText(_ amount: Double?) -> some View {
        if let value = amount {
            if value == 0 {
                Text("free").foregroundStyle(.secondary)
            } else {
                Text(value, format: .currency(code: "USD"))
            }
        } else {
            Text("—").foregroundStyle(.tertiary)
        }
    }

    /// The breakdown's footer: the aggregate, estimate and (after a run) actual.
    @ViewBuilder
    private func chainCostTotalLine(_ estimate: StagedChainCost) -> some View {
        HStack {
            Text(totalLabel(for: chainActualCost ?? estimate))
            Spacer()
            if chainActualCost != nil, estimate.hasPricedStep {
                Text("est \(estimate.pricedTotal, format: .currency(code: "USD"))")
                    .foregroundStyle(.tertiary)
                    .monospacedDigit()
            }
            if let total = (chainActualCost ?? estimate).pricedTotalOrNil {
                Text(total, format: .currency(code: "USD"))
                    .monospacedDigit()
            } else {
                Text("unpriced").foregroundStyle(.secondary)
            }
        }
        .font(.caption.weight(.medium))
    }

    private func totalLabel(for cost: StagedChainCost) -> String {
        if !cost.hasPricedStep { return "No step could be priced" }
        if cost.isCompletePricing {
            return chainActualCost == nil ? "Upper bound" : "Run total"
        }
        return "At least (\(cost.unpricedCount) unpriced)"
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
        if chainActualCost != nil {
            return "What this chain actually spent, per step, read from the run "
                + "accounting (the same figure Activity shows). Click for the "
                + "per-step est → actual breakdown."
        }
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

    private func chainCostAccessibility(_ estimate: StagedChainCost) -> String {
        if let actual = chainActualCost {
            guard actual.hasPricedStep else { return "Actual cost: unpriced" }
            return "Actual cost \(actual.pricedTotal.formatted(.currency(code: "USD")))"
        }
        if !estimate.hasPricedStep { return "Estimated cost: unpriced" }
        let amount = estimate.pricedTotal.formatted(.currency(code: "USD"))
        if estimate.isCompletePricing { return "Estimated cost at most \(amount)" }
        return "Estimated cost at least \(amount), \(estimate.unpricedCount) unpriced"
    }
}

extension StagedChainCost {
    /// The priced total, or nil when nothing priced — so a footer can say
    /// "unpriced" instead of rendering a bare US$0.00.
    var pricedTotalOrNil: Double? { hasPricedStep ? pricedTotal : nil }
}
