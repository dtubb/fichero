import Foundation
import Testing

@testable import Fichero

/// `source.disagree.agreement-is-character-similarity-defined-once-and-never-accuracy` (#6453): the app prints the
/// engine's definition and its own figure labels say agreement, never accuracy.
struct AgreementDefinitionTests {
    @Test func theEnginesDefinitionIsRead() throws {
        let json = #"{"readers":[],"definition":"Agreement is 1 − d / L.","lines":[]}"#
        let page = try ReadingDisagreement.decode(Data(json.utf8))
        #expect(page.definition == "Agreement is 1 − d / L.")
    }

    @Test func aFigureIsSaidAsAgreementNeverAccuracy() {
        let words = ReadingDisagreement.percent(0.82).lowercased()
        #expect(words == "82% agreement")
        #expect(!words.contains("accura"))
    }
}
