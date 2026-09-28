@testable import Fichero
import Testing

/// Edit… in the Inspector (#5201, Daniel on the calfa chinese-vertical page: the Text section had no way to
/// correct a transcription). It must be the Reader's typing, not a second path. What breaks without these:
/// the Inspector writes a reading the stale check never sees, corrects the wrong reading, or lays a
/// vertical or right-to-left line out as Latin.
@MainActor
struct InspectorEditReadingTests {
    private let counting = InspectorText.Reading(
        id: "rep-counting", kind: "transcription", content: "登庸九年", maker: "workflow", author: nil,
        guideline: nil, pairId: nil, pairRole: nil
    )

    @Test("the edit is the Reader's typed-line message, correcting the reading shown, under the stale check")
    func theReadersMessage() {
        let message = InspectorReadingEdit.message(documentId: "p1", segmentId: "l1", text: "登庸十年", editing: counting)
        #expect(message == .edited(pageId: "p1", segmentId: "l1", text: "登庸十年", basedOn: "rep-counting"))
        let params = ReaderTextEdit.newReading(for: message)
        #expect(params?.correctsRepresentationId == "rep-counting", "a correction OF the reading shown")
        #expect(params?.expectedCountingId == "rep-counting", "refused (409) if another reading counts now")
        #expect(params?.kind == "transcription")
    }

    @Test("the field lays out in the segment's resolved direction")
    func layoutFollowsDirection() {
        #expect(InspectorReadingEdit.layout(direction: "ttb") == .vertical)
        #expect(InspectorReadingEdit.layout(direction: "rtl") == .horizontal(rightToLeft: true))
        #expect(InspectorReadingEdit.layout(direction: "ltr") == .horizontal(rightToLeft: false))
        #expect(InspectorReadingEdit.layout(direction: nil) == .horizontal(rightToLeft: false), "no direction: as written")
    }

    @Test("a stale edit says another reading counts now; any other refusal says why")
    func notes() {
        #expect(InspectorReadingEdit.note(for: ReaderTextEditRunner.staleProblem).contains("Another reading counts now"))
        #expect(InspectorReadingEdit.note(for: "engine unreachable") == "Not saved: engine unreachable")
    }
}
