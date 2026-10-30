//
//  CloudCapFixTests.swift
//  FicheroTests
//
//  #6295, `ai.where.cloud-spend-cap`: a Start refused for a spend cap says which cap in plain words and offers the fix in place:
//  "Raise the monthly cap to N", "Raise the project cap to N" (N is the engine's, the best estimate with no margin) and "Run the
//  first N pages" (Finder order). The view logic is `CloudCapFix`; the fields' change is `CloudCapFields.change`.
//  Lines are decoded from the engine's JSON, as the app reads them.
//
//  Not covered: a window drawing the row (no mounted-view harness in this target); the engine's amounts are tested in
//  fichero-server/tests/unit/recipes/test_raise_the_cap_in_place_6295.py.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

struct CloudCapFixTests {
    private func line(_ extra: String = "") throws -> Components.Schemas.CloudCapLine {
        let json = """
        {"cap_usd":10,"spent_usd":4,"remaining_usd":6,"unpriced":false,"estimate_usd":14,"over":true\(extra)}
        """
        return try JSONDecoder().decode(Components.Schemas.CloudCapLine.self, from: Data(json.utf8))
    }

    private func usd(_ value: Double) -> String { value.formatted(.currency(code: "USD")) }  // the Mac's locale, as the row

    @Test func aRunOverTheMonthlyCapOffersTheCapTheEngineNames() throws {
        let fix = CloudCapFix(try line(#","over_month":true,"needed_cap_usd":18,"fewer_pages":42"#))
        #expect(fix.monthly == .init(usd: 18, title: "Raise the monthly cap to \(usd(18))"))
        #expect(fix.project == nil)
        #expect(fix.firstPages == 42)
        #expect(fix.isOffered)
        #expect(fix.reason == "This run is estimated at \(usd(14)), more than the monthly cap (\(usd(10))) leaves \(usd(6)).")
    }

    @Test func aRunOverTheProjectCapOffersThatCapAlone() throws {
        let fix = CloudCapFix(try line(
            #","over_project":true,"project_cap_usd":5,"project_spent_usd":2,"project_remaining_usd":3,"#
                + #""needed_project_cap_usd":16"#))
        #expect(fix.monthly == nil)
        #expect(fix.project == .init(usd: 16, title: "Raise the project cap to \(usd(16))"))
        #expect(fix.reason == "This run is estimated at \(usd(14)), more than the project's total cap (\(usd(5))) leaves \(usd(3)).")
    }

    @Test func overBothCapsOffersBothAndNamesBoth() throws {
        let fix = CloudCapFix(try line(
            #","over_month":true,"needed_cap_usd":18,"over_project":true,"project_cap_usd":5,"#
                + #""project_spent_usd":2,"project_remaining_usd":3,"needed_project_cap_usd":16"#))
        #expect(fix.monthly?.usd == 18 && fix.project?.usd == 16)
        #expect(fix.reason?.contains("the monthly cap") == true && fix.reason?.contains("and the project's total cap") == true)
    }

    @Test func aRunNotOverACapOffersNothing() throws {
        let fits = try JSONDecoder().decode(Components.Schemas.CloudCapLine.self, from: Data(
            #"{"cap_usd":10,"spent_usd":0,"remaining_usd":10,"unpriced":false,"estimate_usd":2,"over":false}"#.utf8))
        let fix = CloudCapFix(fits)
        #expect(!fix.isOffered && fix.reason == nil && fix.firstPages == nil)
        let unknown = try JSONDecoder().decode(Components.Schemas.CloudCapLine.self, from: Data(
            #"{"cap_usd":10,"spent_usd":0,"remaining_usd":10,"unpriced":true,"over":false}"#.utf8))
        #expect(CloudCapFix(unknown).reason == nil, "an unknown estimate is never a number to raise a cap to")
    }

    @Test func theFirstPagesAreNamedForTheirCount() {
        #expect(CloudCapFix.firstPagesTitle(1) == "Run the first page")
        #expect(CloudCapFix.firstPagesTitle(40) == "Run the first 40 pages")
    }

    @Test func theEstimateShowsItsBasisPerStep() throws {
        let estimate = try JSONDecoder().decode(Components.Schemas.StartEstimate.self, from: Data("""
        {"pages":120,"total_cost_usd":3.4,"runs":[
          {"workflow":"w1","steps":["lines"],"where":"cloud","pages":120,"cost_usd":2.71,
           "basis":"the model's listed rate","calls_per_page":1},
          {"workflow":"w2","steps":["correct"],"where":"cloud","pages":1,"cost_usd":null,"basis":"unpriced","calls_per_page":3}]}
        """.utf8))
        let lines = CloudCapFix.basis(of: estimate, title: { $0.uppercased() })
        #expect(lines == [
            "LINES: 120 pages · the model's listed rate · \(usd(2.71))",
            "CORRECT: 1 page · 3 calls a page · unpriced · price unknown"
        ])
    }

    /// The cap's refusal is told apart by the engine's own field, not by its words: with another refusal first, the sentence
    /// is still the cap's, and a reworded sentence changes nothing here.
    @Test func theCapsRefusalIsTheOneTheEngineNames() throws {
        let said = "This run costs more than the cap, in whatever words the engine uses."
        let other = "step 1 (find-lines): its model is not pinned in a known form"
        let capped = try line(#","over_month":true,"needed_cap_usd":18,"refusal":"\#(said)""#)
        #expect(CloudCapFix.withoutCapRefusal([other, said], line: capped) == [other])
        #expect(CloudCapFix.withoutCapRefusal([said], line: capped).isEmpty)
        #expect(CloudCapFix.withoutCapRefusal([other], line: nil) == [other], "no line: nothing is hidden")
        #expect(CloudCapFix.isOver(capped) && !CloudCapFix.isOver(nil))
    }

    @Test func aFieldChangeSendsOnlyWhatMovedAndClearsAnEmptiedProjectCap() throws {
        let held = try line(#","project_cap_usd":50"#)
        let same = CloudCapFields.change(monthly: 10, project: 50, line: held)
        #expect(same.monthly == nil && same.project == nil && !same.clear)
        let raised = CloudCapFields.change(monthly: 25, project: 50, line: held)
        #expect(raised.monthly == 25 && raised.project == nil && !raised.clear)
        let both = CloudCapFields.change(monthly: 25, project: 60, line: held)
        #expect(both.monthly == 25 && both.project == 60)
        let emptied = CloudCapFields.change(monthly: 10, project: nil, line: held)
        #expect(emptied.clear && emptied.project == nil, "an emptied total field removes the limit")
        let none = CloudCapFields.change(monthly: 10, project: nil, line: try line())
        #expect(!none.clear, "no total limit and none typed: nothing to clear")
    }

    @Test func theProjectCapIsSavedUnderTheEnginesKeyAndLeftOutUnanswered() throws {
        let set = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
            RecipeSetupAnswers(cloudProjectCapUsd: 60))) as? [String: Any]
        #expect(set?["cloud_project_cap_usd"] as? Double == 60)
        let unset = try JSONSerialization.jsonObject(with: JSONEncoder().encode(RecipeSetupAnswers())) as? [String: Any]
        #expect(unset?["cloud_project_cap_usd"] == nil, "unanswered keeps the saved cap, or no limit")
    }

    /// The strip offers the caps' change by the engine's `stopped_at_cap`, not by reading the run's line: the status says it, the
    /// store keeps its words, the strip has them. A status that is not stopped at a cap leaves nothing.
    @Test func aRunPausedAtACapOffersTheChangeByTheEnginesField() throws {
        let capped = try JSONDecoder().decode(Components.Schemas.RecipeRunStatus.self, from: Data("""
        {"job_id":"r","state":"waiting","reason":"Paused at the cloud spend cap: a call could cost up to $0.04","steps":[],"skipped":[],
         "stopped_at_cap":true}
        """.utf8))
        #expect(capped.stoppedAtCap == true)
        var strip = ProjectRunStrip(jobId: "r", isLive: true, title: "Recipe run paused", detail: "Paused with its run")
        #expect(strip.stoppedAtCap == nil, "no field, no button: the words of the line are never read")
        strip.stoppedAtCap = capped.reason
        #expect(strip.stoppedAtCap?.contains("spend cap") == true)
    }
}
