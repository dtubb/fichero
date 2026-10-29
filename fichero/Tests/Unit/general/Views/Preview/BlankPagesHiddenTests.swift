import Foundation
@testable import Fichero
import Testing

/// Blank pages the run hid: out of the rows, one "N hidden" line, Unhide (`prep.blank-pages-hidden-in-the-item-view`).
struct BlankPagesHiddenTests {
    private func page(_ name: String, excluded: Bool, blank: Bool?) -> Document {
        var metadata: [String: AnyCodable] = [:]
        if let blank { metadata["blank"] = AnyCodable(["blank": blank, "by": "run r1"] as [String: Any]) }
        return Document(name: name, metadata: metadata, excludeFromProcessing: excluded)
    }

    @Test("only a blank-marked, excluded page is hidden; a page a person merely excluded stays in the rows")
    func onlyBlankMarkedPagesAreHidden() {
        let docs = [page("blank", excluded: true, blank: true), page("excluded", excluded: true, blank: nil),
                    page("written", excluded: false, blank: nil), page("unhidden", excluded: false, blank: false)]
        #expect(HiddenPages.hidden(in: docs).map(\.name) == ["blank"])
    }

    @Test("the line says the count")
    func lineSaysTheCount() {
        #expect(HiddenPages.line(3) == "3 hidden")
    }

    @Test("unhide shows the page again and keeps the person's word on the mark")
    func unhideClearsTheMark() {
        let shown = HiddenPages.unhidden(page("blank", excluded: true, blank: true))
        #expect(shown.excludeFromProcessing == false)
        #expect(HiddenPages.isHiddenBlank(shown) == false)
        let mark = shown.metadata["blank"]?.value as? [String: Any]
        #expect(mark?["by"] as? String == "person")
    }

    @Test("unhide and square go by the audited actions, with the engine's parameter names")
    func requestsUseTheActionsParameterNames() throws {
        let hide = try JSONSerialization.jsonObject(
            with: JSONEncoder().encode(ImageMarkBlankRequest(documentId: "d1", blank: false))) as? [String: Any]
        #expect(hide?["document_id"] as? String == "d1" && hide?["blank"] as? Bool == false)
        let square = try JSONSerialization.jsonObject(
            with: JSONEncoder().encode(ImageSquareRequest(documentId: "d1", quad: [[0, 0], [1, 0], [1, 1], [0, 1]]))) as? [String: Any]
        #expect((square?["quad"] as? [[Double]])?.count == 4)
    }
}
