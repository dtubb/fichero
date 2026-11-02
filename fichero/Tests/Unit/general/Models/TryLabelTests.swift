import Foundation
import Testing

@testable import Fichero

struct TryLabelTests {
    @Test("a try is headed as a try's, with its stage, day and model")
    func title() {
        let found = TryLabel(stage: "find-lines", ranAt: Date(timeIntervalSince1970: 0), model: "kraken", lines: [])
        #expect(found.title.hasPrefix("Try · find lines"))
        #expect(found.title.hasSuffix("kraken"))
    }

    @Test("no day and no model leave only what is known")
    func bare() {
        #expect(TryLabel(stage: "read", ranAt: nil, model: nil, lines: []).title == "Try · read")
    }

    @Test("the note says a try's readings are not the project's")
    func note() {
        #expect(TryLabel.note.contains("not yours"))
    }
}
