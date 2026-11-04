@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `designer.budget.refusal-offers-the-fix` (#6295): the buttons of a refused Start come from the engine's typed `fixes[]`
/// (the cap that refuses and the amount that fits, the first pages that fit, the step whose model to change); the app computes none
/// and an engine that serves none is read from the line's own figures.
struct BudgetRefusalFixTests {
    private func line(_ extra: String) throws -> Components.Schemas.CloudCapLine {
        let json = """
        {"cap_usd":10,"spent_usd":4,"remaining_usd":6,"unpriced":false,"estimate_usd":14,"over":true\(extra)}
        """
        return try JSONDecoder().decode(Components.Schemas.CloudCapLine.self, from: Data(json.utf8))
    }

    private func usd(_ value: Double) -> String { value.formatted(.currency(code: "USD")) }

    @Test func theRaiseAmountsAndFirstPagesComeFromTheTypedFixes() throws {
        let fix = CloudCapFix(try line(#"""
        ,"over_month":true,"over_project":true,"needed_cap_usd":99,"needed_project_cap_usd":98,"fewer_pages":97,
        "fixes":[{"kind":"raise-cap","cap":"monthly","raise_to_usd":18},
                 {"kind":"raise-cap","cap":"project","raise_to_usd":21},
                 {"kind":"run-fewer-pages","pages_that_fit":42},
                 {"kind":"change-model","step":"read-a-page"}]
        """#))
        #expect(fix.monthly == .init(usd: 18, title: "Raise the monthly cap to \(usd(18))"))
        #expect(fix.project == .init(usd: 21, title: "Raise the project cap to \(usd(21))"))
        #expect(fix.firstPages == 42)
    }

    @Test func aFixTheEngineDidNotServeIsNotOffered() throws {
        let fix = CloudCapFix(try line(#"""
        ,"over_month":true,"needed_cap_usd":18,"fewer_pages":42,"fixes":[{"kind":"change-model","step":"read-a-page"}]
        """#))
        #expect(fix.monthly == nil && fix.project == nil && fix.firstPages == nil)
        #expect(fix.reason != nil, "the reason is still said")
    }

    @Test func anEngineThatServesNoFixesIsReadFromTheLinesOwnFigures() throws {
        let fix = CloudCapFix(try line(#","over_month":true,"needed_cap_usd":18,"fewer_pages":42"#))
        #expect(fix.monthly?.usd == 18)
        #expect(fix.firstPages == 42)
    }

    @Test func theChangeModelFixNamesTheStepWhoseFinderOpens() throws {
        let block = BudgetBlock(try line(#"""
        ,"fixes":[{"kind":"raise-cap","cap":"monthly","raise_to_usd":18},{"kind":"change-model","step":"read-a-page"}]
        """#))
        #expect(block.changeModelStep == "read-a-page")
        #expect(BudgetBlock(try line(#","fixes":[]"#)).changeModelStep == nil)
    }

    @Test func aRunNotOverACapOffersNothing() throws {
        let under = try JSONDecoder().decode(Components.Schemas.CloudCapLine.self, from: Data(
            #"{"cap_usd":10,"spent_usd":4,"remaining_usd":6,"unpriced":false,"estimate_usd":2,"over":false,"fixes":[]}"#.utf8))
        let fix = CloudCapFix(under)
        #expect(!fix.isOffered && fix.reason == nil && fix.firstPages == nil)
    }
}
