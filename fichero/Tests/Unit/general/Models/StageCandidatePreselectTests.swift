@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `source.onboard.stages.model-ticked-by-default` (#6119): a stage page opens with its best model already ticked.
struct StageCandidatePreselectTests {
    private func candidate(_ id: String, byDefault: Bool = false, otherPeriod: Bool = false, chosen: Bool = false) -> String {
        """
        {"id":"\(id)","name":"\(id)","source":"kraken-repository","offered_because":"","pin":{},"jobs":["find-lines"],
         "open_licence":true,"size":"16 MB","measured":"","in_recipe_rules":true,"runs_where":"this_mac",
         "availability":"installed","availability_words":"On this Mac","other_period":\(otherPeriod),
         "compared_by_default":\(byDefault),"chosen":\(chosen)}
        """
    }

    private static let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!,
                                              libraryPath: "/tmp/Preselect.fichero")

    private func list(_ rows: String...) throws -> [Components.Schemas.ModelCandidate] {
        try JSONDecoder().decode([Components.Schemas.ModelCandidate].self,
                                 from: Data("[\(rows.joined(separator: ","))]".utf8))
    }

    @Test("the only model is ticked")
    func theOnlyModel() throws {
        #expect(StageCandidateChoice.preselected(try list(candidate("blla"))) == ["blla"])
    }

    @Test("with several, the best-ranked one the engine would compare is ticked, not the first listed")
    func theBestRanked() throws {
        let rows = try list(candidate("a"), candidate("b", byDefault: true), candidate("c", byDefault: true))
        #expect(StageCandidateChoice.preselected(rows) == ["b"])
        #expect(StageCandidateChoice.preselected(try list(candidate("a"), candidate("b"))) == ["a"],
                "the engine marked none: the first")
    }

    @Test("the step's reader now (chosen) comes before the engine's compared ones")
    func theChosenOneFirst() throws {
        let rows = try list(candidate("a", byDefault: true), candidate("b", chosen: true))
        #expect(StageCandidateChoice.preselected(rows) == ["b"])
    }

    @Test("a reader made for another period is never ticked for the person")
    func notAnotherPeriod() throws {
        #expect(StageCandidateChoice.preselected(try list(candidate("old", byDefault: true, otherPeriod: true))).isEmpty)
        #expect(StageCandidateChoice.preselected([]).isEmpty)
    }

    @MainActor
    @Test("ticked once: unticking it is not undone by a reload, and a choice already made stays")
    func tickedOnce() throws {
        let rows = try list(candidate("blla"))
        let store = SetupStageTryStore(client: Self.client, stageId: "find-lines")
        store.preselect(from: rows)
        #expect(store.chosenCandidates == ["blla"])
        store.chosenCandidates = []
        store.preselect(from: rows)
        #expect(store.chosenCandidates.isEmpty)
        let chosen = SetupStageTryStore(client: Self.client, stageId: "find-lines")
        chosen.chosenCandidates = ["mine"]
        chosen.preselect(from: rows)
        #expect(chosen.chosenCandidates == ["mine"])
    }
}
