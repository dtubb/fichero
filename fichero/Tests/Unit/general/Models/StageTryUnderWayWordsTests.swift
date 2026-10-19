@testable import Fichero
import Foundation
import Testing

/// A comparison that is waiting says why beside its spinner, never a spinner alone ("Compare on These Pages does nothing").
struct StageTryUnderWayWordsTests {
    private func result(_ json: String) throws -> SetupStageTryResult {
        try JSONDecoder().decode(SetupStageTryResult.self, from: Data(json.utf8))
    }

    @Test("a waiting comparison shows the engine's reason")
    func waitingShowsTheReason() throws {
        let held = try result(#"{"state":"waiting","comparison":{"state":"waiting","reason":"Waiting for the imported pages' thumbnails."}}"#)
        #expect(held.underWayWords == "Waiting for the imported pages' thumbnails.")
    }

    @Test("under way with no reason still says something; done says nothing")
    func fallbackAndDone() throws {
        let running = try result(#"{"state":"running","comparison":{"state":"running"}}"#)
        #expect(running.underWayWords?.isEmpty == false)
        #expect(try result(#"{"state":"done"}"#).underWayWords == nil)
    }
}
