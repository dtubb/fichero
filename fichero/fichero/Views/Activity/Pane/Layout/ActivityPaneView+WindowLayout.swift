import SwiftUI

/// The Activity window's sizes, in one place because they must fit together (#6661).
///
/// The window is a `NavigationSplitView` (sidebar, centre) with the Inspector beside the centre. The centre runs under
/// the sidebar and the Inspector (their widths are its safe area), so the minimum it reports to the window is its own
/// minimum plus both side columns' widths, and the window adds the sidebar's column again. When that sum is wider than
/// the window, AppKit moves a divider, the reported minimum changes with it, and the window loops its constraints
/// passes until it ends the app ("more Update Constraints in Window passes than there are views in the window"). Side
/// columns can be dragged to their maximums, so the window's minimum width is derived from those, and the centre's
/// minimum height with the toolbar counted twice fits in the window's minimum height (`ActivityWindowLayoutTests`). No
/// column's range is read from its content.
extension ActivityPaneView {
    nonisolated static let sidebarWidths: ClosedRange<CGFloat> = 180...260
    nonisolated static let sidebarIdealWidth: CGFloat = 220
    nonisolated static let inspectorWidths: ClosedRange<CGFloat> = 280...440
    nonisolated static let inspectorIdealWidth: CGFloat = 380
    /// The table scrolls sideways below this; the person can widen the window.
    nonisolated static let centreMinWidth: CGFloat = 160
    nonisolated static let centreMinHeight: CGFloat = 300
    /// The toolbar's height, which a column's reported minimum height counts up to twice (measured, #6661).
    nonisolated static let toolbarHeight: CGFloat = 52
    /// Room left over: the dividers between the columns and a margin.
    nonisolated static let layoutSlack: CGFloat = 20

    /// The widest the columns can make the window need: the centre, the sidebar twice (its column and the centre's
    /// safe area), the Inspector, each side column at its maximum.
    nonisolated static var windowMinWidth: CGFloat {
        centreMinWidth + 2 * sidebarWidths.upperBound + inspectorWidths.upperBound + layoutSlack
    }

    nonisolated static let windowMinHeight: CGFloat = 560
}
