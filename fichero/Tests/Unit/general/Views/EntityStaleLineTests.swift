@testable import Fichero
import Testing

/// #5360 (review 121): "Not embedded" is not "Out of date"; current says nothing.
struct EntityStaleLineTests {
    @Test func theEntityInspectorWordsEachReason() {
        #expect(EntityDigestContent.staleLine("not-embedded") == "Not embedded")
        #expect(EntityDigestContent.staleLine("text-changed") == "Out of date")
        #expect(EntityDigestContent.staleLine("model-changed") == "Out of date")
        #expect(EntityDigestContent.staleLine(nil) == nil)
        #expect(EntityDigestContent.staleLine("something-new") == nil)
    }
}
