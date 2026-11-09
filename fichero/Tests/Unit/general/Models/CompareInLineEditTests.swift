import Testing

@testable import Fichero

/// `source.editor.compare-two-to-four-readings-with-the-line-picture-and-edit-in-line` (#6462): the 2 to 4 rule and the
/// correction an edit writes (a new reading derived from the compared one, at its level and kind).
struct CompareInLineEditTests {
    @Test func aComparisonTakesTwoToFourReadings() {
        #expect(!CompareInLineEdit.isComparable(1))
        #expect([2, 3, 4].allSatisfy(CompareInLineEdit.isComparable))
        #expect(!CompareInLineEdit.isComparable(5))
    }

    @Test func aFifthReadingIsRefusedInOneLine() {
        #expect(CompareInLineEdit.refusal(adding: 3) == nil)
        #expect(CompareInLineEdit.refusal(adding: 4) == "Compare takes two to four readings.")
    }

    @Test func anEditIsANewReadingDerivedFromTheComparedOneAtItsLevelAndKind() {
        let reading = CompareInLineEdit.Reading(id: "r1", level: "regularised", kind: "transcription", text: "Yten dixo")
        let fix = CompareInLineEdit.correction(of: reading, to: "Item dixo")
        #expect(fix == .init(derivedFromRepresentationId: "r1", level: "regularised", kind: "transcription", content: "Item dixo"))
    }

    @Test func savingUnchangedTextWritesNothing() {
        #expect(CompareInLineEdit.correction(of: .init(id: "r1", level: nil, kind: "transcription", text: "same"), to: "same") == nil)
    }
}
