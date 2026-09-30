@testable import Fichero
import Foundation
import Testing

/// #5280: two panes of one kind shared a single app-wide key, so changing an option in one pane
/// changed the other. Each pane now keeps its own entry, and the map is what gets saved, so both
/// survive a relaunch unchanged.
struct PaneScopedOptionTests {
    private let left = UUID()
    private let right = UUID()

    @Test("two panes keep different values, and both read back from the saved map")
    func twoPanesKeepTheirOwnValues() {
        var map = "{}"
        map = PaneScopedOption.setting(6, in: map, pane: left)
        map = PaneScopedOption.setting(2, in: map, pane: right)

        // `map` is the string @AppStorage writes; reading it back is what a relaunch does.
        #expect(PaneScopedOption.value(map, pane: left, shared: 4) == 6)
        #expect(PaneScopedOption.value(map, pane: right, shared: 4) == 2)
    }

    @Test("a pane that never chose reads the shared value")
    func newPaneFallsBackToShared() {
        let map = PaneScopedOption.setting("entities,status", in: "{}", pane: left)
        #expect(PaneScopedOption.value(map, pane: right, shared: "entities") == "entities")
        #expect(PaneScopedOption.value(map, pane: nil, shared: "entities") == "entities")
    }

    @Test("with no pane nothing is written to the map, and a damaged map falls back")
    func noPaneAndBadJSON() {
        #expect(PaneScopedOption.setting(6, in: "{}", pane: nil) == "{}")
        #expect(PaneScopedOption.value("not json", pane: left, shared: 4) == 4)
    }
}
