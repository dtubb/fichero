@testable import Fichero
import Foundation
import Testing

/// `source.onboard.stages.try-progress-in-place` and `.compare-results-per-model` (#5855, #5856): the words a try
/// shows in place (Set Up is modal, so Activity cannot be reached) and each model's counts side by side.
struct StageTryProgressTests {
    private func result(_ json: String) throws -> SetupStageTryResult {
        try JSONDecoder().decode(SetupStageTryResult.self, from: Data(json.utf8))
    }

    private static let twoModels = #"""
    {"state":"running","job_id":"j1","waiting_for":"Making the page images, 3 of 5","candidates":[
      {"card":"kraken","name":"Kraken","state":"running",
       "progress":{"state":"running","done":1,"total":5,"page":"IMG_2","step":"finding lines","waiting_for":null},
       "per_page":[{"id":"p1","segments":{"line":27,"region":3}},{"id":"p2","segments":{"line":1,"region":1}}]},
      {"card":"apple","name":"Apple Vision","state":"waiting",
       "progress":{"state":"waiting","done":0,"total":5,"page":null,"step":"finding lines","waiting_for":"the lane"},
       "per_page":[{"id":"p1","segments":{"line":25}}]}]}
    """#

    @Test func theTryNamesEachModelsPageAndStepInPlace() throws {
        let r = try result(Self.twoModels)
        #expect(r.progressLines == ["Kraken: page 2 of 5, finding lines", "Apple Vision: waiting, the lane"])
    }

    @Test func theWaitingReasonComesFromTheEngineAndNeverPointsToActivity() throws {
        let r = try result(Self.twoModels)
        #expect(r.underWayWords == "Making the page images, 3 of 5")
        let bare = try result(#"{"state":"running"}"#)
        #expect(bare.underWayWords == "Working on it.")
    }

    /// A try with no compared candidates carries its progress on the result itself.
    @Test func aTryWithNoCandidatesShowsItsOwnProgress() throws {
        let r = try result(#"{"state":"running","progress":{"state":"running","done":1,"total":5,"step":"finding lines"}}"#)
        #expect(r.progressLines == ["Page 2 of 5, finding lines"])
        let done = try result(#"{"state":"done","progress":{"state":"done","done":5,"total":5}}"#)
        #expect(done.progressLines.isEmpty)
    }

    @Test func aFinishedModelShowsNoProgressLine() throws {
        let r = try result(#"{"state":"done","candidates":[{"card":"k","name":"Kraken","progress":{"state":"done","done":5,"total":5}}]}"#)
        #expect(r.progressLines.isEmpty)
    }

    @Test func eachPageShowsEachModelsCountsSideBySideWithPlurals() throws {
        let r = try result(Self.twoModels)
        #expect(r.sideBySide(pageId: "p1") == "Kraken: 27 lines, 3 regions · Apple Vision: 25 lines")
        #expect(r.sideBySide(pageId: "p2") == "Kraken: 1 line, 1 region")
        #expect(r.sideBySide(pageId: "p9") == "")
    }

    @Test func aModelsShapesDecodeForTheWindow() throws {
        let r = try result(#"{"state":"done","candidates":[{"card":"k","per_page":[{"id":"p1","segments":{"line":1},"shapes":[{"kind":"line","bbox":[0.1,0.2,0.5,0.05],"baseline":[[0.1,0.24],[0.6,0.24]]}]}]}]}"#)
        let shape = try #require(r.candidates?.first?.perPage?.first?.shapes?.first)
        #expect(shape.kind == "line" && shape.bbox == [0.1, 0.2, 0.5, 0.05] && shape.baseline?.count == 2)
    }
}
