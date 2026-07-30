import SwiftUI

// MARK: - View Components

extension SidebarView {
    @ViewBuilder
    var sidebarContent: some View {
        standardSidebarContent
    }

    @ViewBuilder
    var standardSidebarContent: some View {
        VStack(spacing: 0) {
            // The persistent shell sidebar (the library/folder tree) stays
            // visible in EVERY mode — Research included. Research no longer
            // swaps the sidebar out for its project list; that list now renders
            // in the content column (ContentView+Navigation.contentView), so
            // switching to Research keeps the shell sidebar like Knowledge Graph,
            // Activity, etc. (sidebar-persistence fix).
            unifiedContent

            // Bottom toolbar — owns the sidebar filter field + sidebar-scoped
            // actions as one unified bottom toolbar (#4061). No standalone
            // filter chrome above the bar.
            if shouldShowBottomToolbar {
                SidebarBottomToolbar(
                    itemRegistry: itemRegistry,
                    importFiles: importFiles,
                    deleteItem: handleDeleteSelection,
                    hasSelection: selectedItem != nil,
                    sidebarFilterText: $sidebarFilterText
                )
            }
        }
    }

    /// Whether to show the bottom toolbar.
    var shouldShowBottomToolbar: Bool {
        true
    }

    /// Unified sidebar content with feature-gated sections per library.
    @ViewBuilder
    var unifiedContent: some View {
        List(selection: sidebarSelectionBinding) {
            ForEach(filteredLibraryHeaders) { libraryHeader in
                unifiedLibrarySection(libraryHeader)
            }
            // App-level destinations pinned once at the bottom, not repeated
            // under every library (#1456).
            pinnedGlobalNavigationRows()
        }
        .listStyle(.sidebar)
        // #4371: the system's own selection fill, tinted to the SAME
        // unemphasized colour the library rows use, so a selected sidebar row
        // reads like Finder's soft grey rather than a saturated accent bar.
        // One selection vocabulary, one colour token — the sidebar is not a
        // second selection language. Row chrome (badges, the open affordance,
        // status dots) sets its colours explicitly, so it does not inherit
        // this tint.
        .tint(LibrarySelectionStyle.fill)
        .scrollContentBackground(.hidden)
        .background(.bar)
        #if os(macOS)
        // Finder-style double-click: open the primary selected row in a new
        // tab or window (#2496), mirroring the library table's container-level
        // double-click contract (#3364). Attached to the List, NOT per row —
        // a row-level TapGesture(count: 2) holds every single click and
        // breaks native List selection (#612). Keyboard/VoiceOver users reach
        // the same action via the row context menu's Open in New Tab/Window.
        .onTapGesture(count: 2) {
            handleSidebarDoubleClick()
        }
        // Delete key removes the whole (deletable) multi-selection, confirming once.
        .onDeleteCommand {
            handleDeleteSelection()
        }
        // Escape collapses a multi-row selection back to the single routed
        // anchor ("shift to stop it"). Plain-click collapse is already native.
        .onExitCommand {
            selectionState.selectedDestinations =
                sidebarCollapsedSelection(primary: selectionState.selectedDestination)
        }
        // Right-arrow on a LEAF row hands keyboard focus to the content pane
        // (Finder-column feel) — the reciprocal of LibraryView's left-arrow
        // handoff into the sidebar. `.ignored` passes every other case
        // (folders, no selection) through to the List's native handling.
        .onKeyPress(.rightArrow, phases: .down) { _ in
            guard sidebarShouldExitFocusRight(selectedItem: selectedItem),
                  let onRequestNextPaneFocus else { return .ignored }
            onRequestNextPaneFocus()
            return .handled
        }
        #endif
    }

    /// Bridges the sidebar tree's native multi-selection to the state.
    ///
    /// macOS `List(selection: Binding<Set>)` gives shift-click contiguous
    /// range, cmd-click toggle, and shift+arrow extend for free. The setter is
    /// the one seam that derives the routed primary (`selectedDestination`,
    /// which drives the detail pane and `.onChange` routing) from the highlight
    /// set. Write ORDER matters: set `selectedDestinations` first so the primary
    /// is derived from the current set, never a stale one.
    private var sidebarSelectionBinding: Binding<Set<SidebarDestination>> {
        Binding(
            get: { selectionState.selectedDestinations },
            set: { proposed in
                // A click that triggers the lazy child load rebuilds the tree,
                // and while the clicked row is momentarily absent from the
                // rendered rows the List writes the selection back WITHOUT it
                // (#4297). Keep any dropped tree row that is currently
                // unresolvable — that drop is the rebuild talking, not the
                // user; the row re-selects itself when it re-materialises. A
                // deselect of a row that IS resolvable is a real user action
                // and passes through untouched.
                let newValue = Self.sidebarResilientSelection(
                    current: selectionState.selectedDestinations,
                    proposed: proposed,
                    isMomentarilyMissing: { destination in
                        switch destination {
                        case .library, .browser, .run:
                            // Pinned/static rows and activity runs are not
                            // resolved through the cached item index (see
                            // `handleSelectionDestination`) — a drop of these
                            // is always the user.
                            return false
                        default:
                            return cachedItem(id: destination.serializedID) == nil
                        }
                    }
                )
                if newValue == selectionState.selectedDestinations, newValue != proposed {
                    // Pure spurious clear — nothing changed; don't open a
                    // click-timeline interval for a write the user never made.
                    return
                }
                // Start of the click timeline (#4228). The setter is the first
                // of OUR code the click reaches; everything before it is AppKit
                // hit-testing. Closed in `handleSelectionChange` once the routed
                // destination has been written.
                InteractionProfile.begin(.selectionCommit)
                selectionState.selectedDestinations = newValue
                let primary = sidebarPrimaryDestination(
                    for: newValue,
                    previous: selectionState.selectedDestination
                )
                // Only reroute when the primary actually changes — a >1 batch
                // selection returns the same primary, so this is a no-op and the
                // detail pane stays put while the selection is built.
                if selectionState.selectedDestination != primary {
                    selectionState.selectedDestination = primary
                } else {
                    // No reroute — `.onChange` will not fire, so close the
                    // interval here rather than leaving it open until the next
                    // click supersedes it. An extend-selection click IS a
                    // measurable interaction; it just ends early.
                    InteractionProfile.end(.selectionCommit, detail: "highlight only")
                }
            }
        )
    }

    /// Selection survives tree rebuilds (#4297): the sanitized selection the
    /// binding setter commits. A destination the proposal DROPS is kept when
    /// `isMomentarilyMissing` says its row cannot currently be resolved — the
    /// List is reconciling a tag that vanished mid-rebuild, not relaying a user
    /// deselect. Additions and drops of resolvable rows pass through unchanged.
    /// Pure so the resilience rule is testable without a rendered List.
    static func sidebarResilientSelection(
        current: Set<SidebarDestination>,
        proposed: Set<SidebarDestination>,
        isMomentarilyMissing: (SidebarDestination) -> Bool
    ) -> Set<SidebarDestination> {
        // A write that ADDS a row is always a genuine gesture — the List's
        // rebuild reconciliation only ever REMOVES tags it cannot resolve. So a
        // replacement click (new row in, old row out) wins outright, even if
        // the old row is mid-rebuild.
        guard proposed.subtracting(current).isEmpty else { return proposed }
        let dropped = current.subtracting(proposed)
        guard !dropped.isEmpty else { return proposed }
        let spurious = dropped.filter(isMomentarilyMissing)
        return proposed.union(spurious)
    }
}
