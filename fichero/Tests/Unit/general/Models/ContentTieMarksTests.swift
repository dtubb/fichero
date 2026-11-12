@testable import Fichero
import Foundation
import Testing

/// #6458, `source.editor.content-shows-its-tie-to-the-lines`: one margin mark per line from the line's counting reading, and the
/// head line for page-only text.
@Suite("The Content view shows its tie to the lines (#6458)")
struct ContentTieMarksTests {
    private func reading(from artifact: String? = nil, confidence: Double? = nil, model: String? = nil) -> InspectorText.Reading {
        var reading = InspectorText.Reading(
            id: "r", kind: "transcription", content: "words", maker: "ocr", author: nil, guideline: nil, pairId: nil, pairRole: nil
        )
        reading.derivedFromArtifactId = artifact
        reading.machineConfidence = confidence
        reading.producerModel = model
        return reading
    }

    @Test("a line read per segment is anchored and shows no mark")
    func anchored() {
        #expect(ContentTieMark(counting: reading(model: "kraken")) == .anchored)
    }

    @Test("a line tied from a page read shows a link with the words and the figure")
    func tied() {
        let mark = ContentTieMark(counting: reading(from: "page", confidence: 0.8, model: "gemini"))
        #expect(mark == .tied(percent: 80, reader: "gemini"))
        #expect(mark.glyph == "link")
        #expect(mark.help == "tied from gemini's page read · 80 %")
    }

    @Test("a tied line under the doubt line shows the yellow link")
    func doubtful() {
        let mark = ContentTieMark(counting: reading(from: "page", confidence: 0.4, model: "gemini"))
        #expect(mark == .doubtful(percent: 40, reader: "gemini"))
        #expect(mark.help == "doubtful tie from gemini's page read · 40 %")
    }

    @Test("a line with no counting reading shows the dash")
    func empty() {
        let mark = ContentTieMark(counting: nil)
        #expect(mark == .empty)
        #expect(mark.glyph == "minus")
    }

    @Test("page text with no line map says so in the head line, with both verbs")
    func headLine() {
        let head = ContentTieHeadLine(hasLineMap: false)
        #expect(head?.text == "page text, not tied to lines")
        #expect(head?.verbs == ["Tie Automatically", "Tie by Hand"])
        #expect(ContentTieHeadLine(hasLineMap: true) == nil)
    }
}
