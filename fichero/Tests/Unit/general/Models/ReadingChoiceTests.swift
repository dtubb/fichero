@testable import Fichero
import Foundation
import Testing

/// #5153: "Make This Count". What breaks without these: choosing the reading that already counts
/// (an audited action that changed nothing), or a choice sent with the wrong key names, which the
/// engine refuses.
struct ReadingChoiceTests {
    private func reading(_ id: String) -> InspectorText.Reading {
        .init(id: id, kind: "transcription", content: id, maker: "human", author: nil, guideline: nil,
              pairId: nil, pairRole: nil)
    }

    @Test("the counting reading offers no choice; another one sends reading.choose with its id")
    func chooseOnlyWhatDoesNotCount() throws {
        let text = InspectorText(
            readings: [reading("a"), reading("b")],
            counting: ["transcription": .init(readingId: "a", why: .chosen)]
        )
        #expect(ReadingChoice.choose(text.readings[0], of: "line-1", in: text) == nil)
        let params = try #require(ReadingChoice.choose(text.readings[1], of: "line-1", in: text))
        let json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(params)) as? [String: String])
        #expect(json == ["segment_id": "line-1", "kind": "transcription", "representation_id": "b"])
    }

    @Test("with nothing counting yet, every reading can be chosen")
    func noneCountsEveryoneCanBeChosen() {
        let text = InspectorText(readings: [reading("a"), reading("b")],
                                 counting: ["transcription": .init(readingId: nil, why: .noneCounts)])
        #expect(text.readings.allSatisfy { ReadingChoice.choose($0, of: "l", in: text) != nil })
    }
}
