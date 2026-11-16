@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Ready's sections (`wide.ready.only-what-will-run`): the steps that run, in order, the skipped ones with why, and no offered,
/// left-off or taken-out rows.
struct ReadyOnlyRunsTests {
    private func plan() throws -> Components.Schemas.StartPlan {
        let json = """
        {"runs":[{"steps":["prep"],"job":"prepare-the-image","card":"prepare","runs_on":"this-mac"},
                 {"steps":["lines","read"],"job":"read-a-line","card":"workflow","runs_on":"this-mac","done":4,"of":92}],
         "workflows":[],"skipped":[{"step":"names","why":"no model fits","fix":"choose a model"}],
         "offered":["train-a-model"],"left_off":["Find Statements: about 2 minutes"],
         "refusals":[],"estimate":{"pages":92,"runs":[],"total_cost_usd":0.5}}
        """
        return try JSONDecoder().decode(Components.Schemas.StartPlan.self, from: Data(json.utf8))
    }

    @Test("the sections hold the runs in order with their progress, the skipped step with its fix, and the estimate")
    func sections() throws {
        let sections = ReadyWillRun(plan: try plan(), startReason: nil)
        #expect(sections.running.map(\.job) == ["prepare-the-image", "read-a-line"])
        #expect(sections.running[0].progress == nil && sections.running[1].progress == "done on 4 of 92")
        #expect(sections.stepIds == ["prep", "lines", "read"])
        #expect(sections.skipped == [.init(id: "names", why: "no model fits", fix: "choose a model")])
        #expect(sections.pages == 92 && sections.totalCostUsd == 0.5 && sections.startReason == nil)
    }

    @Test("an offered job and a left-off step are not Ready's: the model has nowhere to hold them")
    func noOfferedNoLeftOff() throws {
        let sections = ReadyWillRun(plan: try plan(), startReason: "Start waits: no model")
        let mirror = Mirror(reflecting: sections).children.compactMap(\.label)
        #expect(!mirror.contains(where: { $0.lowercased().contains("offered") || $0.lowercased().contains("leftoff") }))
        #expect(sections.startReason == "Start waits: no model")
    }
}
