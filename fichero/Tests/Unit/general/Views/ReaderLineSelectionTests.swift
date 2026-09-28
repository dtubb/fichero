@testable import Fichero
import Foundation
import Testing

/// #5155: the Reader's caret line and the Source view's selection are one selection. What breaks
/// without these: a malformed page message selecting something anyway, or a segment id with a quote
/// in it breaking the script the app sends the page.
struct ReaderLineSelectionTests {
    @Test("a whole lineFocused message is read; a partial one is not")
    func parsesOnlyWholeMessages() {
        #expect(ReaderLineSelection.focus(from: ["pageId": "p1", "segmentId": "l7"]) == .init(pageId: "p1", segmentId: "l7"))
        #expect(ReaderLineSelection.focus(from: ["pageId": "p1"]) == nil)
        #expect(ReaderLineSelection.focus(from: ["pageId": "", "segmentId": "l7"]) == nil)
    }

    @Test("the ids reach the page as a JSON array, safely escaped, through an optional call")
    func showLinesScriptIsSafe() throws {
        let script = ReaderLineSelection.showLinesScript(["a", #"b"); alert("x"#])
        #expect(script.hasPrefix("window.fichero?.showLines?.(") && script.hasSuffix(");"))
        let json = String(script.dropFirst("window.fichero?.showLines?.(".count).dropLast(2))
        let ids = try JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String]
        #expect(ids == ["a", #"b"); alert("x"#])
        #expect(ReaderLineSelection.showLinesScript([]) == "window.fichero?.showLines?.([]);")
    }
}
