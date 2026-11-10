@testable import Fichero
import Foundation
import Testing

/// `source.editor.reader-line-discloses-its-versions` (#6492): a line's readings as a tree.
struct ReadingTreeTests {
    private func reading(
        _ id: String, at minute: Double, from: String? = nil, corrects: String? = nil
    ) -> InspectorText.Reading {
        var r = InspectorText.Reading(id: id, kind: "transcription", content: id, maker: "workflow", author: nil,
                                      guideline: nil, pairId: nil, pairRole: nil)
        r.createdAt = Date(timeIntervalSince1970: minute * 60)
        r.derivedFromId = from
        r.correctsId = corrects
        return r
    }

    @Test("Kraken and Google are roots oldest first; Google's modernisation and a correction hang under their source")
    func derivedAndCorrectedNest() {
        let roots = ReadingTree.build([
            reading("modern", at: 3, from: "google"),
            reading("google", at: 2),
            reading("kraken", at: 1),
            reading("fix", at: 4, corrects: "kraken"),
        ])
        #expect(roots.map(\.id) == ["kraken", "google"])
        #expect(roots[0].children.map(\.id) == ["fix"])
        #expect(roots[1].children.map(\.id) == ["modern"])
        #expect(ReadingTree.discloses(roots))
    }

    @Test("a reading whose parent is withdrawn or not this line's is a root, never dropped")
    func orphanIsRoot() {
        let all = [reading("google", at: 1), reading("modern", at: 2, from: "google"), reading("x", at: 3, from: "elsewhere")]
        let roots = ReadingTree.build(all, retracted: ["google"])
        #expect(roots.map(\.id) == ["modern", "x"])
        #expect(ReadingTree.build(all, retracted: ["google"], showsWithdrawn: true).map(\.id) == ["google", "x"])
    }

    @Test("one reading, or none, has nothing to disclose")
    func singleDoesNotDisclose() {
        #expect(!ReadingTree.discloses(ReadingTree.build([reading("only", at: 1)])))
        #expect(!ReadingTree.discloses(ReadingTree.build([])))
    }

    @Test("Show Withdrawn Readings: the text keeps retracted readings apart, and the tree lists them only when asked")
    func withdrawnReadingsAreKeptApart() {
        let text = InspectorText(
            readings: [reading("kraken", at: 1), reading("old", at: 2)], retracted: ["old"], counting: [:]
        )
        #expect(text.readings.map(\.id) == ["kraken"], "a retracted reading is still not a reading")
        #expect(text.withdrawn.map(\.id) == ["old"])
        let retracted = Set(text.withdrawn.map(\.id))
        #expect(ReadingTree.build(text.allReadings, retracted: retracted).map(\.id) == ["kraken"])
        #expect(ReadingTree.build(text.allReadings, retracted: retracted, showsWithdrawn: true).map(\.id) == ["kraken", "old"])
    }
}
