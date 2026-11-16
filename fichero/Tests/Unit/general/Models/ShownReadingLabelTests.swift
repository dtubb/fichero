@testable import Fichero
import Foundation
import Testing

/// #6455: the Reader's Lines row labels the reading it shows, from the line's readings: the counting one with its basis, or, where none
/// counts, the newest person's reading with the dash and "N readings, none chosen".
@Suite("The shown reading's label (#6455)")
struct ShownReadingLabelTests {
    private func reading(_ id: String, maker: String, level: String? = nil, model: String? = nil, day: Double) -> InspectorText.Reading {
        var reading = InspectorText.Reading(
            id: id, kind: "transcription", content: "words \(id)", maker: maker, author: maker == "human" ? "ann" : nil,
            guideline: nil, pairId: nil, pairRole: nil
        )
        reading.level = level
        reading.producerModel = model
        reading.createdAt = Date(timeIntervalSince1970: day * 86_400)
        return reading
    }

    @Test("a chosen reading names its reader and level with a check")
    func chosen() throws {
        let kraken = reading("k", maker: "ocr", level: "diplomatic", model: "kraken", day: 1)
        let text = InspectorText(readings: [kraken], counting: ["transcription": .init(readingId: "k", why: .chosen)])
        let label = try #require(ShownReadingLabel(text))
        #expect(label.text == "kraken · diplomatic")
        #expect(label.glyph == "checkmark")
        #expect(label.shown.id == "k")
    }

    @Test("a person's correction shows the person glyph and 'as written' with no level")
    func correction() throws {
        let fix = reading("c", maker: "human", day: 2)
        let text = InspectorText(readings: [fix], counting: ["transcription": .init(readingId: "c", why: .correction)])
        let label = try #require(ShownReadingLabel(text))
        #expect(label.text == "ann · as written")
        #expect(label.glyph == "person")
    }

    @Test("when none counts the newest person's reading is shown, with the dash and the count")
    func noneChosen() throws {
        let older = reading("a", maker: "human", day: 1)
        let newer = reading("b", maker: "human", day: 2)
        let machine = reading("m", maker: "ocr", model: "kraken", day: 3)
        let text = InspectorText(readings: [older, newer, machine], counting: ["transcription": .init(readingId: nil, why: .noneCounts)])
        let label = try #require(ShownReadingLabel(text))
        #expect(label.shown.id == "b")
        #expect(label.text == "3 readings, none chosen")
        #expect(label.glyph == "minus")
    }

    @Test("a line with no readings has no label")
    func absent() {
        #expect(ShownReadingLabel(nil) == nil)
        #expect(ShownReadingLabel(InspectorText(readings: [], counting: [:])) == nil)
    }
}
