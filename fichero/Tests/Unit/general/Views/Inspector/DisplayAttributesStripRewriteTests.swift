@testable import Fichero
import Foundation
import Testing

/// The attribute strip writes its saved choices only when normalizing changed them: every
/// `@AppStorage` write, even of the same value, re-evaluates every `@AppStorage` view in the
/// window, and the strip normalized on every click (`read.a-click-shows-its-folder-at-once`, #4228).
@Suite("The attribute strip rewrites a saved choice only when it changed")
struct DisplayAttributesStripRewriteTests {

    @Test("an already-normal value is not written again")
    func unchangedIsNotWritten() {
        #expect(DisplayAttributesStrip.rewrite("entities,claims", as: "entities,claims") == nil)
        #expect(DisplayAttributesStrip.rewrite("", as: "") == nil)
    }

    @Test("a value that normalizing changed is written")
    func changedIsWritten() {
        #expect(DisplayAttributesStrip.rewrite("entities,,claims,", as: "entities,claims") == "entities,claims")
    }
}
