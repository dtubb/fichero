//
//  BudgetBlockTests.swift
//  FicheroTests
//
//  #6295, `designer.budget.beside-the-estimate` and `designer.budget.run-cap`: the Budget block above Start reads the engine's
//  `cloud_cap` line: the run cap it proposes (the estimate, no margin), the step that costs most, and the step "Change the model"
//  opens. Lines are decoded from the engine's JSON. Not covered: the field drawn in a window (no mounted-view harness here); the
//  engine's figures are tested in fichero-server/tests/unit/recipes/test_budget_in_the_plan.py.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct BudgetBlockTests {
    private func line(_ extra: String = "") throws -> Components.Schemas.CloudCapLine {
        let json = """
        {"cap_usd":10,"spent_usd":4,"remaining_usd":6,"unpriced":false,"estimate_usd":14,"over":true\(extra)}
        """
        return try JSONDecoder().decode(Components.Schemas.CloudCapLine.self, from: Data(json.utf8))
    }

    @Test func theBlockReadsTheProposedRunCapTheDearestStepAndTheModelToChange() throws {
        let block = BudgetBlock(try line(
            #","proposed_run_cap_usd":14,"dearest_step":"describe","fixes":[{"kind":"change-model","step":"describe"}]"#))
        #expect(block.proposedRunCapUsd == 14)
        #expect(block.dearestStep == "describe" && block.changeModelStep == "describe")
        let words = block.dearestWords(title: { "Catalogue (\($0))" })
        #expect(words == "Catalogue (describe) costs most: change its model to bring the run under the cap.")
    }

    @Test func aPlanWithNoProposalHasNoRunCapToUseAndNoStepToBlame() throws {
        let block = BudgetBlock(try line())
        #expect(block.proposedRunCapUsd == nil && block.dearestStep == nil && block.changeModelStep == nil)
        #expect(block.prompt == "No limit" && block.dearestWords(title: { $0 }) == nil)
    }

    @Test func theFieldPromptIsTheEnginesProposalAndNoCapBelowZeroCanBeTyped() throws {
        #expect(BudgetBlock(try line(#","proposed_run_cap_usd":3.46"#)).prompt == CloudCapFix.usd(3.46))
        #expect(BudgetBlock.clamped(-5) == 0 && BudgetBlock.clamped(7) == 7 && BudgetBlock.clamped(nil) == nil)
    }
}
