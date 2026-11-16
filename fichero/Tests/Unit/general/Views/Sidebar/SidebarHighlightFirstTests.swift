@testable import Fichero
import Foundation
import Testing

/// A click's highlight first, its routing after (`sidebar.selection.highlight-first`, #4228):
/// the routed primary is written a moment after the highlight set, and only the latest click routes.
@MainActor
@Suite("A sidebar click is highlighted first and routed after")
struct SidebarHighlightFirstTests {

    private func waitPastRouting() async {
        try? await Task.sleep(for: .milliseconds(Int(SidebarSelectionState.routingDelay * 1000) + 80))
    }

    @Test("the routed primary is written after the click, not with it")
    func routingWaitsForTheHighlight() async {
        let state = SidebarSelectionState()
        let folder = SidebarDestination.document("folder")
        state.selectedDestinations = [folder]
        state.routeAfterHighlight(folder)
        #expect(state.selectedDestination == nil)
        await waitPastRouting()
        #expect(state.selectedDestination == folder)
    }

    @Test("only the latest of two quick clicks routes")
    func latestClickWins() async {
        let state = SidebarSelectionState()
        let first = SidebarDestination.document("first")
        let second = SidebarDestination.document("second")
        state.routeAfterHighlight(first)
        state.routeAfterHighlight(second)
        await waitPastRouting()
        #expect(state.selectedDestination == second)
    }

    @Test("a programmatic selection overrides a click still waiting to route")
    func programmaticSelectionWins() async {
        let state = SidebarSelectionState()
        state.routeAfterHighlight(.document("clicked"))
        state.selectedItemId = "doc:revealed"
        await waitPastRouting()
        #expect(state.selectedItemId == "doc:revealed")
    }
}
