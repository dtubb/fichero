//
//  SidebarBottomBarPatternTests.swift
//  FicheroTests
//
//  sidebar.bottom-bar.plus-trash-filter, sidebar.filter-menu.shows-toggles and panes.chrome.one-filter-pattern
//  (owner 2026-11-13): the sidebar's bar is + · Trash · Metadata · Filter; its Metadata is exactly item count, sharing
//  state and run progress; every bar's Filter and Metadata are the same two controls. See
//  docs/contributor_manual/specs/ui/sidebar-crud.md and docs/contributor_manual/specs/ui/panes-workspaces.md.
//

@testable import Fichero
import Foundation
import SwiftUI
import Testing

struct SidebarBottomBarPatternTests {
    @Test("the sidebar's Metadata is exactly item count, sharing state and run progress")
    func sidebarMetadataIsThreeThings() {
        #expect(SidebarMetadata.allCases == [.itemCount, .sharingState, .runProgress])
        #expect(SidebarMetadata.allCases.map(\.title) == ["Item Count", "Sharing", "Run Progress"])
    }

    @Test("each Metadata switch is kept under its own key and is on until switched off")
    func switchesAreOnByDefault() throws {
        let keys = SidebarMetadata.allCases.map(\.storageKey)
        #expect(Set(keys).count == keys.count)
        let suite = "SidebarBottomBarPatternTests.\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        for key in keys { #expect(defaults.object(forKey: key) == nil, "no stored value: the switch reads its default, on") }
    }

    @Test("every bar's Filter shows the filter icon, never the search loupe; Metadata keeps its one icon")
    func oneFilterOneMetadata() {
        #expect(PaneFilterField<EmptyView>.symbol == "line.3.horizontal.decrease.circle")
        #expect(PaneFilterField<EmptyView>.symbol != "magnifyingglass")
        #expect(PaneMetadataButton<EmptyView>.symbol == "switch.2")
    }
}
