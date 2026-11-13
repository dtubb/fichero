//
//  PaneBarStyleTests.swift
//  FicheroTests
//
//  panes.chrome.bar-buttons-accessory-style (owner 2026-11-13): pane heads and bottom bars wear the accessory-bar style
//  on macOS, borderless on touch. See docs/contributor_manual/specs/ui/panes-workspaces.md.
//

@testable import Fichero
import Testing

struct PaneBarStyleTests {
    @Test("the Mac's bars wear the accessory-bar style; touch keeps borderless")
    func onePlatformChoice() {
        #if os(macOS)
        #expect(PaneBarStyle.kind == .accessoryBar)
        #else
        #expect(PaneBarStyle.kind == .borderless)
        #endif
    }

    /// `panes.chrome.bars-flush-on-mac`: the Mac's bars are flat in the pane's material; touch keeps the glass island.
    @Test("the Mac's bottom bars and inspector strip are flush; touch keeps the glass")
    func barsFlushOnlyOnMac() {
        #if os(macOS)
        #expect(PaneBarStyle.barIsFlush)
        #else
        #expect(!PaneBarStyle.barIsFlush)
        #endif
    }
}
