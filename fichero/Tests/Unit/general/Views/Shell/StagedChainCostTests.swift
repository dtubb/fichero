//
//  StagedChainCostTests.swift
//  FicheroTests
//
//  The workflow-bar cost chip's arithmetic and its three states (2026-09-05).
//  Daniel screenshotted "est. ≤ US$0.00" on a real 90-image × 5-step chain: a
//  price MISS had rendered as free. The model under test keeps a miss (nil)
//  distinct from a real zero (a free on-device model) so the chip can say
//  "unpriced" — never a US$0.00 charge — and quotes a FLOOR ("≥") the moment
//  any step cannot be priced, a CEILING ("≤") only when every step can.
//

@testable import Fichero
import Foundation
import Testing

struct StagedChainCostTests {

    private func lines(_ estimates: [Double?]) -> StagedChainCost {
        StagedChainCost(
            lines: estimates.map { StagedChainCost.Line(id: UUID(), estimate: $0) }
        )
    }

    // MARK: - Arithmetic

    @Test func pricedTotalSumsOnlyPricedSteps() {
        let cost = lines([0.10, 0.25, nil, 0.05])
        #expect(abs(cost.pricedTotal - 0.40) < 0.0001)
        #expect(cost.pricedCount == 3)
        #expect(cost.unpricedCount == 1)
    }

    @Test func anUnpricedStepIsNeverReadAsZero() {
        // The whole defect in one assertion: a step the registry could not
        // price contributes NOTHING to the total and is counted as unpriced —
        // it must never be folded in as a 0 that drags an average or reads as
        // free.
        let cost = lines([0.30, nil])
        #expect(cost.pricedTotal == 0.30)
        #expect(cost.unpricedCount == 1)
    }

    @Test func aFreeStepIsPricedAtZeroNotUnpriced() {
        // A real zero — a free on-device model — is a PRICE, distinct from a
        // miss. It counts as priced; it just adds nothing.
        let cost = lines([0.0, 0.20])
        #expect(cost.pricedTotal == 0.20)
        #expect(cost.pricedCount == 2)
        #expect(cost.unpricedCount == 0)
        #expect(cost.isCompletePricing)
    }

    // MARK: - The three chip states

    @Test func nothingPricedIsUnpricedNeverZeroDollars() {
        // Every step a miss: the chip must say "unpriced", NOT "US$0.00". The
        // total is arithmetically zero, so the guard cannot be the number — it
        // has to be `hasPricedStep`, which this asserts is false here.
        let cost = lines([nil, nil, nil])
        #expect(cost.hasPricedStep == false)
        #expect(cost.isCompletePricing == false)
        #expect(cost.pricedTotal == 0.0)  // …and yet nothing renders "$0.00".
    }

    @Test func everyStepPricedIsACeiling() {
        let cost = lines([0.10, 0.20, 0.05])
        #expect(cost.hasPricedStep)
        #expect(cost.isCompletePricing)  // → "est. ≤ $0.35"
        #expect(abs(cost.pricedTotal - 0.35) < 0.0001)
    }

    @Test func someStepsUnpricedIsAFloorWithATail() {
        let cost = lines([0.10, nil, 0.20, nil])
        #expect(cost.hasPricedStep)
        #expect(cost.isCompletePricing == false)  // → "est. ≥ $0.30 · 2 unpriced"
        #expect(abs(cost.pricedTotal - 0.30) < 0.0001)
        #expect(cost.unpricedCount == 2)
    }

    // MARK: - Per-step lookup (the breakdown joins lines to live steps)

    @Test func lineLookupFindsTheStepsEstimate() {
        let priced = UUID()
        let missed = UUID()
        let cost = StagedChainCost(lines: [
            StagedChainCost.Line(id: priced, estimate: 0.42),
            StagedChainCost.Line(id: missed, estimate: nil),
        ])
        #expect(cost.line(forStepId: priced)?.estimate == 0.42)
        #expect(cost.line(forStepId: missed)?.estimate == nil)
        #expect(cost.line(forStepId: missed)?.isPriced == false)
        #expect(cost.line(forStepId: UUID()) == nil)
    }

    // MARK: - Estimate → actual (the same struct carries measured costs)

    @Test func actualTotalEqualsTheSumOfRecordedPerStepCosts() {
        // The chip's ACTUAL is the sum of each step's recorded run cost
        // (RunUsage.costUsd). Building actuals as StagedChainCost lines and
        // summing must reproduce that number exactly — one source of truth.
        let recorded: [Double] = [0.0123, 0.0456, 0.0001]
        let actual = lines(recorded.map { Optional($0) })
        #expect(actual.pricedTotal == recorded.reduce(0, +))
        #expect(actual.isCompletePricing)
    }

    @Test func aRunWithUnpricedModelsIsAFloorNotAZero() {
        // A step whose models the registry could not price records costUsd nil.
        // The actual chip must read that as a FLOOR (≥) with the tail named —
        // never fold the unpriced step in as a zero.
        let actual = lines([0.02, nil, 0.03])
        #expect(actual.hasPricedStep)
        #expect(actual.isCompletePricing == false)
        #expect(actual.pricedTotal == 0.05)
        #expect(actual.unpricedCount == 1)
    }

    @Test func pricedTotalOrNilGuardsTheFooterFromZeroDollars() {
        #expect(lines([nil, nil]).pricedTotalOrNil == nil)
        #expect(lines([0.10, nil]).pricedTotalOrNil == 0.10)
    }
}
