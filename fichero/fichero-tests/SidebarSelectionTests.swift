import Testing
@testable import Fichero

struct SidebarSelectionTests {
    @Test("#1165 sidebar tap fallback ignores already-selected rows")
    func tapFallbackIgnoresCurrentSelection() {
        #expect(sidebarSelectionFallback(current: "doc:1", tapped: "doc:1") == nil)
    }

    @Test("#1165 sidebar tap fallback only requests missing selection")
    func tapFallbackRequestsDifferentSelection() {
        #expect(sidebarSelectionFallback(current: nil, tapped: "doc:1") == "doc:1")
        #expect(sidebarSelectionFallback(current: "doc:1", tapped: "doc:2") == "doc:2")
    }
}
