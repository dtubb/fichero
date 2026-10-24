@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// A recipe run's Activity Details by Set Up's stages (#5670, §7c), from the maintainer's screen of 2026-10-11 (EAP
/// 1740, Run the recipe, Done): the details were one long list, with "Skipped" lines starting with step ids
/// ("find-statements: …") and stages named by ids ("prepare-the-image · Step prepare-the-image"). Now each stage of
/// Set Up is a card, in Set Up's order, with its state, its bar, what it made and why it did not run, never a step id.
@MainActor
struct ActivityStageCardsTests {
    /// A finished recipe run as `GET /api/activity/jobs/{id}` answers it: three stage runs (images, then lines and
    /// reading in one workflow, then names and dates), Statements skipped for want of a model.
    static let treeJSON = """
    {"id":"r1","kind":"run-a-recipe","name":"Run the recipe","subject":"r1","state":"done","done":92,"total":92,
     "stages":[
       {"steps":["prepare-the-image"],"card":"workflow","state":"done","child_id":"w0",
        "account":{"state":"done","pages_total":92,"pages_done":92}},
       {"steps":["find-lines","read-a-line"],"card":"workflow","state":"partial","child_id":"w1",
        "why":"91 of 92 pages done; 1 failed: IMG_001: Kraken could not read its lines",
        "account":{"state":"done","pages_total":92,"pages_done":91,"pages_failed":1}},
       {"steps":["find-names-tag-words","work-out-dates"],"card":"workflow","state":"done","child_id":"w2",
        "account":{"state":"done","pages_total":92,"pages_done":92}}],
     "summary":{"job_id":"r1","state":"done","finished":true,"pages":92,"pages_read":91,
       "names":[{"kind":"person","label":"People","count":73},{"kind":"location","label":"Places","count":69},
                {"kind":"organization","label":"Organisations","count":18},{"kind":"event","label":"Events","count":0}],
       "dates":0,"statements":0,
       "failed":[{"steps":["find-lines","read-a-line"],"thread_id":"w1","pages_failed":1,"failures":[],
                  "offer":"Read Again"}],
       "pages_failed":1,
       "skipped":[{"step":"find-statements","why":"find-statements: no model for Find statements. The rules found no \
    statement model that knows es on this Mac, and pages may not leave it, so the step was left out of the plan.",
                   "fix":"choose-model"}],
       "not_run":[]},
     "children":[
       {"id":"w0","kind":"workflow","name":"Clean up","subject":"w0","state":"done","done":92,"total":92},
       {"id":"w1","kind":"workflow","name":"Transcribe (Kraken)","subject":"w1","state":"done","done":91,"total":92},
       {"id":"w2","kind":"workflow","name":"Names and dates","subject":"w2","state":"done","done":92,"total":92}]}
    """

    static func cards() throws -> [ActivityDetails.StageCard] {
        let tree = try JSONDecoder().decode(Components.Schemas.JobTree.self, from: Data(treeJSON.utf8))
        return ActivityDetails.stageCards(of: ActivityJobNode(tree))
    }

    @Test("a run reads as Set Up's stages, in Set Up's order, and never by a step id")
    func stagesInSetUpsOrder() throws {
        let cards = try Self.cards()
        #expect(cards.map(\.title) == ["Prepare Images", "Find Lines", "Read", "Names", "Statements", "Dates & Times"])
        let words = cards.flatMap { [$0.title] + $0.made + [$0.why ?? ""] }.joined(separator: " ")
        for stepId in ["prepare-the-image", "read-a-line", "find-statements", "work-out-dates"] {
            #expect(!words.contains(stepId), "no step id: \(stepId)")
        }
    }

    @Test("each stage says its state, its bar and what it made")
    func whatEachMade() throws {
        let cards = Dictionary(uniqueKeysWithValues: try Self.cards().map { ($0.id, $0) })
        let read = try #require(cards["read"])
        #expect(read.state == .partial && read.stateWords == "Partial", "a stage that lost a page is never Done")
        #expect(read.why == "91 of 92 pages done; 1 failed: IMG_001: Kraken could not read its lines.")
        #expect(read.done == 91 && read.total == 92, "the bar is the stage's own pages")
        #expect(read.made == ["Read 91 of 92 pages"])
        #expect(read.failed?.text == "1 page failed" && read.failed?.offer == "Read Again")
        #expect(cards["names"]?.made == ["73 People · 69 Places · 18 Organisations"], "kinds with none are left out")
        #expect(cards["dates"]?.made == ["0 dates"], "a stage that made nothing says so")
        #expect(cards["find-lines"]?.made == [], "a stage the summary has no figure for says only its state")
    }

    /// WHY (`finddocs.review.activity`): after a run the person needs to know how much Organise left for them:
    /// what it proposed and how many of those were applied, the rest waiting in Items.
    @Test("Organise says the documents it proposed and how many were applied")
    func organiseSaysProposedAndApplied() throws {
        let json = Self.treeJSON
            .replacingOccurrences(
                of: #"{"steps":["find-names-tag-words","work-out-dates"]"#,
                with: #"{"steps":["find-documents-in-a-folder"],"card":"find-documents","state":"done","child_id":"f1"},"#
                    + #"{"steps":["find-names-tag-words","work-out-dates"]"#
            )
            .replacingOccurrences(of: #""dates":0,"statements":0,"#,
                                  with: #""dates":0,"statements":0,"documents_proposed":12,"documents_accepted":3,"#
                                      + #""groups_proposed":0,"#)
        let tree = try JSONDecoder().decode(Components.Schemas.JobTree.self, from: Data(json.utf8))
        let organise = try #require(ActivityDetails.stageCards(of: ActivityJobNode(tree)).first { $0.id == "organise" })
        #expect(organise.title == "Organise")
        #expect(organise.made == ["12 documents proposed, 3 applied"], "no groups line when none were proposed")
    }

    @Test("a skipped stage says why in one short sentence, and Open Set Up… goes to that stage")
    func skippedSaysWhy() throws {
        let statements = try #require(try Self.cards().first { $0.id == "statements" })
        #expect(statements.state == .skipped)
        #expect(statements.why == "No model for Find statements.")
        #expect(statements.offersSetUp)
        #expect(ActivityDetails.Action.openSetUp(stage: statements.id) == .openSetUp(stage: "statements"))
    }

    @Test("a reason loses its step id and keeps its first sentence")
    func oneSentence() {
        #expect(ActivityDetails.oneSentence("find-statements: no model for Find statements. More words.")
                == "No model for Find statements.")
        #expect(ActivityDetails.oneSentence("Pages may not leave this Mac") == "Pages may not leave this Mac.")
        let long = String(repeating: "word ", count: 40)
        #expect(ActivityDetails.oneSentence(long).hasSuffix("…"))
    }

    @Test("every step of the job registry's stages has one stage; a check or an export has none")
    func stepsMapToOneStage() {
        let jobs = SetupStages.all.flatMap(\.jobs)
        #expect(Set(jobs).count == jobs.count, "a job belongs to one stage")
        // Thirteen since section 7d (2026-10-11): Find Regions apart from Find Lines, Normalise apart from Translate;
        // Catalogue last, at folder level (#6087).
        #expect(SetupStages.all.map(\.id) == ["prepare-images", "find-regions", "find-lines", "read", "normalise",
                                              "translate", "organise", "names", "statements", "dates", "passages",
                                              "structured-data", "search", "catalogue"])
        #expect(SetupStages.stage(of: "work-out-dates")?.title == "Dates & Times")
        #expect(SetupStages.stage(of: "describe-for-the-catalogue")?.title == "Catalogue")
        #expect(SetupStages.stage(of: "check") == nil && SetupStages.stage(of: "export") == nil)
    }
}
