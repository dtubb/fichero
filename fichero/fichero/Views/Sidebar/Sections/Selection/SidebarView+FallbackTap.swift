import SwiftUI

// MARK: - The click fallback for a sidebar row's name (#145, #6534)
//
// Split out of `SidebarView+UnifiedRows.swift`, which had reached the 400-line limit.

extension SidebarView {
    /// The row's own name, while expanded, takes the same fallback (`sidebarExpandedLabelTapActs`). On touch the List
    /// takes every tap itself, so there is none.
    func expandedLabelTap(on item: SidebarItem, orderedSiblings: [SidebarDestination]) -> (() -> Void)? {
        #if os(macOS)
        { fallbackTap(on: item, orderedSiblings: orderedSiblings) }
        #else
        nil
        #endif
    }

    #if os(macOS)
    /// A click that the List did not commit (a draggable row's name), as Finder reads it. #145 widened it to MODIFIER
    /// clicks: on rows whose drag payload owns label presses, ⇧/⌘ on the NAME never reached the List either ('you
    /// shift click on the name of the next line, it isn't added' / 'ditto for command click'). Same Finder semantics,
    /// same ONE commit seam. Called by the whole-row gesture while the row is collapsed, and by the row's own label
    /// while it is expanded (`sidebarExpandedLabelTapActs`).
    func fallbackTap(on item: SidebarItem, orderedSiblings: [SidebarDestination]) {
        let proposal = sidebarFallbackProposal(
            clicked: item.destination,
            current: selectionState.selectedDestinations,
            anchor: selectionState.selectedDestination,
            orderedSiblings: orderedSiblings,
            modifiers: sidebarClickModifiers()
        )
        logFallbackTap(on: item, proposal: proposal)
        guard proposal != selectionState.selectedDestinations else { return }
        applySidebarSelectionProposal(proposal)
    }

    /// #6534: child rows sit inside an expanded row's tap gesture; this says whose handler fired.
    func logFallbackTap(on item: SidebarItem, proposal: Set<SidebarDestination>) {
        let ids = proposal.map(\.serializedID).sorted().joined(separator: ",")
        sidebarRowLogger.debug("fallback tap on \(item.id, privacy: .public) proposal=\(ids, privacy: .public)")
    }
    #endif
}
