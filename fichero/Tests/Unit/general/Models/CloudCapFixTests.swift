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
    /// WHY: the basis list was keyed by its own words, so two runs that print the same line (two Review steps at one price) repeated
    /// an id: SwiftUI drew one row for two, or the wrong one on an update.
    @Test func twoRunsWithTheSameWordsAreTwoRows() throws {
        let estimate = try JSONDecoder().decode(Components.Schemas.StartEstimate.self, from: Data("""
        {"pages":10,"total_cost_usd":2,"runs":[
          {"workflow":"w","steps":["correct"],"where":"cloud","pages":10,"cost_usd":1,"basis":"the model's listed rate"},
          {"workflow":"w","steps":["correct"],"where":"cloud","pages":10,"cost_usd":1,"basis":"the model's listed rate"}]}
        """.utf8))
        let lines = CloudCapFix.basisLines(of: estimate, title: { $0 })
        #expect(lines.count == 2 && lines[0].text == lines[1].text)
        #expect(Set(lines.map(\.id)).count == 2, "each row has an id of its own")
        #expect(CloudCapFix.basis(of: estimate, title: { $0 }) == lines.map(\.text))
    }

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

    /// WHY: an emptied monthly field returned "no change", so nothing was sent and nothing said: the field stayed empty while the cap
    /// was still the old one. Only the total cap may be emptied (no limit); the monthly one says so and goes back.
    @Test func anEmptiedMonthlyFieldIsToldSoAndNotLeftEmpty() throws {
        #expect(CloudCapFields.emptiedMonthlyWords(nil)?.contains("cannot be left empty") == true)
        #expect(CloudCapFields.emptiedMonthlyWords(0) == nil, "0 is a cap")
        #expect(CloudCapFields.emptiedMonthlyWords(10) == nil)
        let none = CloudCapFields.change(monthly: nil, project: nil, line: try line())
        #expect(none.monthly == nil && !none.clear, "nothing is sent for the emptied field")
    }

    /// WHY: Return and the field losing focus both save, before the plan has come back, so both read the same stale line and sent the
    /// same change: two PUTs, two audit rows, two undo steps for one edit.
    @Test func oneEditIsOneChangeNotTwo() throws {
        let held = try line(#","project_cap_usd":50"#)
        let edit = CloudCapFields.change(monthly: 25, project: 50, line: held)
        #expect(CloudCapFields.shouldSend(edit, after: nil))
        #expect(!CloudCapFields.shouldSend(edit, after: edit), "the same change just sent is not sent again")
        let another = CloudCapFields.change(monthly: 30, project: 50, line: held)
        #expect(CloudCapFields.shouldSend(another, after: edit), "a different edit is sent")
        let nothing = CloudCapFields.change(monthly: 10, project: 50, line: held)
        #expect(!CloudCapFields.shouldSend(nothing, after: nil), "nothing moved: nothing is sent")
    }

    /// WHY: a fixed 110-point field cut a larger amount off at larger text sizes. There is no mounted-view harness here, so this reads
    /// the view's source: the width must come from a `@ScaledMetric`, not a literal passed to `.frame`.
    @Test func theCapFieldWidthScalesWithTheTextSize() throws {
        let tests = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let view = tests.deletingLastPathComponent().appendingPathComponent("fichero/Views/Onboarding/RecipeCloudCapViews.swift")
        let source = try String(contentsOf: view, encoding: .utf8)
        #expect(source.contains("@ScaledMetric"), "the width is a scaled metric")
        #expect(!source.contains("maxWidth: 110"), "no literal width on the field")
        #expect(CloudCapFields.baseFieldWidth == 110)
    }

    @Test func theProjectCapIsSavedUnderTheEnginesKeyAndLeftOutUnanswered() throws {
        let set = try JSONSerialization.jsonObject(with: JSONEncoder().encode(
            RecipeSetupAnswers(cloudProjectCapUsd: 60))) as? [String: Any]
        #expect(set?["cloud_project_cap_usd"] as? Double == 60)
        let unset = try JSONSerialization.jsonObject(with: JSONEncoder().encode(RecipeSetupAnswers())) as? [String: Any]
        #expect(unset?["cloud_project_cap_usd"] == nil, "unanswered keeps the saved cap, or no limit")
    }

    /// The strip offers the caps' change by the engine's `stopped_at_cap`, not by reading the run's line, and the popover offers the
    /// cap that lets the refused call through, which the plan (its estimate may fit) cannot say.
    @Test func aRunPausedAtACapOffersTheChangeByTheEnginesField() throws {
        let status = try JSONDecoder().decode(Components.Schemas.RecipeRunStatus.self, from: Data("""
        {"job_id":"r","state":"waiting","reason":"Paused at the cloud spend cap: a call could cost up to $0.04","steps":[],"skipped":[],
         "stopped_at_cap":true,"stopped_needs_cap_usd":1.04}
        """.utf8))
        let stop = try #require(CloudCapFix.Stop(status))
        #expect(stop.monthly == .init(usd: 1.04, title: "Raise the monthly cap to \(usd(1.04))") && stop.project == nil)
        var strip = ProjectRunStrip(jobId: "r", isLive: true, title: "Recipe run paused", detail: "Paused with its run")
        #expect(strip.stoppedAtCap == nil, "no field, no button: the words of the line are never read")
        strip.stoppedAtCap = stop
        #expect(strip.stoppedAtCap?.words.contains("spend cap") == true)
        let quiet = try JSONDecoder().decode(Components.Schemas.RecipeRunStatus.self, from: Data(
            #"{"job_id":"r","state":"running","steps":[],"skipped":[]}"#.utf8))
        #expect(CloudCapFix.Stop(quiet) == nil)
    }
}
