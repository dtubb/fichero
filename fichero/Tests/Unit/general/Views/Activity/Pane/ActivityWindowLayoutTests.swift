@testable import Fichero
import SwiftUI
import Testing

/// `activity.window.sidebar`, `activity.window.graph-on-every-view`, `activity.graphs.own-pane` (spec
/// docs/contributor_manual/specs/ui/activity-pane.md), #6661: opening Window › Activity ended the app ("more Update
/// Constraints in Window passes than there are views in the window"). The window's columns reported minimums that did
/// not fit it together, so its constraints passes never settled. Measured on the running window: the centre's reported
/// minimum width is its own plus the sidebar's and the Inspector's widths (they are its safe area), and the window adds
/// the sidebar's column again; its minimum height counts the toolbar twice. These hold the sizes in
/// `ActivityPaneView+WindowLayout.swift` to that, with each side column dragged to its widest; and the rows-over-graphs
/// split, which is no AppKit split view, to keeping both panes.
struct ActivityWindowLayoutTests {
    private typealias Layout = ActivityPaneView

    // The rule itself was measured on the running window (#6661: below it the constraints passes looped, above it they
    // settled); these keep the constants to it, so a column widened without the window failing here.
    @Test("the window's minimum width holds the centre, the sidebar twice and the Inspector, each side column at its widest")
    func widthsFitWithSideColumnsAtTheirMaximums() {
        let widest = Layout.centreMinWidth + 2 * Layout.sidebarWidths.upperBound + Layout.inspectorWidths.upperBound
        #expect(widest < Layout.windowMinWidth)
        // Room for the two dividers at least.
        #expect(Layout.windowMinWidth - widest >= 2)
    }

    @Test("at the ideal widths the window opens with room to spare")
    func widthsFitAtTheIdeals() {
        let opening = Layout.centreMinWidth + 2 * Layout.sidebarIdealWidth + Layout.inspectorIdealWidth
        #expect(opening < Layout.windowMinWidth)
    }

    @Test("the centre's minimum height, with the toolbar counted twice, fits under the window's toolbar")
    func heightsFit() {
        #expect(Layout.centreMinHeight + 2 * Layout.toolbarHeight <= Layout.windowMinHeight - Layout.toolbarHeight)
    }

    @Test("each side column's range runs min ≤ ideal ≤ max")
    func columnRangesAreOrdered() {
        #expect(Layout.sidebarWidths.contains(Layout.sidebarIdealWidth))
        #expect(Layout.inspectorWidths.contains(Layout.inspectorIdealWidth))
    }

    @Test("the graphs keep the height the person dragged to when it fits")
    func graphsHeightKept() {
        #expect(ActivityGraphsSplitStack<EmptyView, EmptyView>.clamped(200, total: 600) == 200)
    }

    @Test("the graphs are never shorter than their minimum")
    func graphsHeightFloor() {
        let split = ActivityGraphsSplitStack<EmptyView, EmptyView>.self
        #expect(split.clamped(10, total: 600) == split.graphsMinHeight)
    }

    @Test("dragged up past the rows' minimum, the graphs stop where the rows keep theirs")
    func graphsHeightCeiling() {
        let split = ActivityGraphsSplitStack<EmptyView, EmptyView>.self
        let total = 600.0
        #expect(split.clamped(10_000, total: total) == total - split.rowsMinHeight - split.dividerHeight)
    }

    @Test("in a centre too short for both, the graphs keep their minimum")
    func graphsHeightInAShortCentre() {
        let split = ActivityGraphsSplitStack<EmptyView, EmptyView>.self
        #expect(split.clamped(200, total: 100) == split.graphsMinHeight)
    }

    @Test("a height that is not a number draws the default")
    func graphsHeightNotFinite() {
        let split = ActivityGraphsSplitStack<EmptyView, EmptyView>.self
        #expect(split.clamped(.nan, total: 600) == split.defaultGraphsHeight)
        #expect(split.clamped(.infinity, total: 600) == split.defaultGraphsHeight)
    }
}
