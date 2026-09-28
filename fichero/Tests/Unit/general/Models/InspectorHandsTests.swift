@testable import Fichero
import Testing

/// The Inspector's Hands section (#5161). What breaks without these: the ink and the record merged
/// into one line (`source.hand.not-provenance`), a rival judgement hidden, or an imported `<handShift>`
/// shown as if a person here had judged it.
struct InspectorHandsTests {
    private let hands: [InspectorHands.ListedHand] = [
        .init(id: "b", label: "hand B", scribe: nil, date: nil, style: "Estrangela"),
        .init(id: "c", label: "hand C", scribe: "Rabbula", date: nil, style: nil)
    ]

    @Test("the ink and the record are separate lines; rival attributions are all shown")
    func inkAndRecordApartRivalsKept() {
        let rows = InspectorHands.rows([
            .init(id: "a1", handId: "b", certainty: 0.8, judgedBy: "owner", fromFile: nil),
            .init(id: "a2", handId: "c", certainty: nil, judgedBy: "reviewer", fromFile: nil)
        ], hands: hands)
        #expect(rows.map(\.ink) == ["hand B (Estrangela)", "hand C (Rabbula)"])
        #expect(rows.map(\.record) == ["judged by owner · sure 80%", "judged by reviewer"])
    }

    @Test("an attribution the FILE made says so, not who ran the import")
    func fromTheFile() {
        let rows = InspectorHands.rows(
            [.init(id: "a", handId: "b", certainty: nil, judgedBy: "owner", fromFile: "file: 0065.xml")], hands: hands
        )
        #expect(rows.first?.record == "from the file 0065.xml")
        #expect(InspectorHands.rows([.init(id: "x", handId: "gone", certainty: nil, judgedBy: nil, fromFile: nil)],
                                    hands: hands).first?.ink == "an unlisted hand")
    }
}
