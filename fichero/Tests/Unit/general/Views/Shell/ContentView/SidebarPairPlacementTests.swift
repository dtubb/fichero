//
//  SidebarPairPlacementTests.swift
//  FicheroTests
//
//  panes.toolbar.sidebar-pair-once (owner 2026-11-13): the Sidebar/Chat pair is in the window toolbar once. See
//  docs/contributor_manual/specs/ui/panes-workspaces.md.
//

@testable import Fichero
import Testing

struct SidebarPairPlacementTests {
    @Test("sidebar up: the pair is the sidebar column's; sidebar hidden: the window's island, never both")
    func onePlaceAtATime() {
        #expect(SidebarPairPlacement.placement(sidebarShown: true) == .sidebarColumn)
        #expect(SidebarPairPlacement.placement(sidebarShown: false) == .windowIsland)
    }
}
