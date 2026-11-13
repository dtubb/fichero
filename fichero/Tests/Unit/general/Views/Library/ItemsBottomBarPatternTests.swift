//
//  ItemsBottomBarPatternTests.swift
//  FicheroTests
//
//  panes.chrome.one-filter-pattern (owner 2026-11-13): the Items bar is + · Trash · Metadata · Sort · Filter; Sort is
//  left out on the Map, where position is the place. See docs/contributor_manual/specs/ui/panes-workspaces.md.
//

@testable import Fichero
import Testing

struct ItemsBottomBarPatternTests {
    @Test("Sort shows in every Items view but the Map")
    func sortIsLeftOutOnlyOnTheMap() {
        #expect(!LibraryView.barShowsSort(.geoMap))
        for mode in ViewDisplayMode.allCases where mode != .geoMap {
            #expect(LibraryView.barShowsSort(mode), "\(mode) keeps Sort")
        }
    }
}
