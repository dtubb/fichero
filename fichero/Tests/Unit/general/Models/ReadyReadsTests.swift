@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Ready's two engine reads (`designer.defaults.says-why`, `designer.how.chain-risk-on-ready`, #6052) and the run's paged failed pages
/// (`activity.run.failed-pages-paged`, #5960): the app lists what the engine said, in the order it fixes, and works nothing out.
struct ReadyReadsTests {
    private func why(_ text: String, because: String) throws -> Components.Schemas.WhyOfDefault {
        try JSONDecoder().decode(Components.Schemas.WhyOfDefault.self,
                                 from: Data(#"{"why":"\#(text)","because":"\#(because)"}"#.utf8))
    }

    @Test func theReasonsComeInTheOrderOfTheDefaultsAndOncePerSentence() throws {
        let same = try why("a clean print reads well with a free reader", because: "print, clean")
        let rows = DefaultWhy.rows([
            "cap": try why("the cap is the estimate", because: "cloud"),
            "model_kind": same, "steps": same,
            "review": try why("unsure lines are checked again", because: "handwriting")
        ])
        #expect(rows.map(\.id) == ["steps", "review", "cap"])
        #expect(rows.first?.because == "print, clean")
    }

    @Test func noReasonsIsNoRows() {
        #expect(DefaultWhy.rows([:]).isEmpty)
    }

    @Test func theFailedPagesAreRowsWithTheirOneReasonAndAPageWithNoneSaysFailed() throws {
        let json = #"""
        {"job_id":"j1","total":2,"offset":0,"items":[
          {"document_id":"d1","name":"p1.jpg","state":"failed","reason":"the provider refused this letter"},
          {"document_id":"d2","name":"p2.jpg","state":"failed"}]}
        """#
        let list = try JSONDecoder().decode(Components.Schemas.RunPageStates.self, from: Data(json.utf8))
        let rows = ActivityStore.failedRows(list)
        #expect(rows.map(\.id) == ["d1", "d2"])
        #expect(rows.map(\.title) == ["p1.jpg", "p2.jpg"])
        #expect(rows.map(\.reason) == ["the provider refused this letter", "Failed"])
    }
}
