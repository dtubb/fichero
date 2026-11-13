//
//  SidebarBottomBarPlacementTests.swift
//  FicheroTests
//
//  sidebar.bottom-bar.flush-in-sidebar-material and panes.chrome.bar-hairline-rule (owner 2026-11-13): the sidebar's
//  bottom bar draws one hairline above it on macOS, none on touch. See docs/contributor_manual/specs/ui/sidebar-crud.md.
//

@testable import Fichero
import Testing

struct SidebarBottomBarPlacementTests {
    @Test("the sidebar's bottom bar has one hairline above it on the Mac, none on touch")
    func hairlineOnlyOnMac() {
        #if os(macOS)
        #expect(SidebarBottomToolbar.drawsHairlineAbove)
        #else
        #expect(!SidebarBottomToolbar.drawsHairlineAbove)
        #endif
    }

    @Test("a filter bar draws its hairline by default exactly where the bar is flush")
    func filterBarHairlineFollowsFlush() {
        #expect(PaneBarStyle.barsDrawHairline == PaneBarStyle.barIsFlush)
    }
}
