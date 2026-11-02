@testable import Fichero
import Foundation
import Testing

/// The page text the tie did not tie to a line is carried from the engine's result and listed, never dropped
/// (`wide.nomodel.untied-remainder-kept`).
struct TieRemainderTests {
    @Test("a page's remainder decodes with its reason; an older result without one still decodes")
    func decodes() throws {
        let json = #"{"counts":{"tied":1},"pages":{"p1":{"tied":1,"doubtful":1,"untied":0,"draft":false,"#
            + #""remainder":[{"segment_id":"s2","text":"algo distinto","why":"doubtful: page text and line disagree"}]},"#
            + #""p2":{"tied":0,"doubtful":0,"untied":0,"draft":true}}}"#
        let tie = try JSONDecoder().decode(SetupStageTie.self, from: Data(json.utf8))
        #expect(tie.pages?["p1"]?.remainder?.first?.text == "algo distinto")
        #expect(tie.pages?["p1"]?.remainder?.first?.segmentId == "s2")
        #expect(tie.pages?["p2"]?.remainder == nil)
    }
}
