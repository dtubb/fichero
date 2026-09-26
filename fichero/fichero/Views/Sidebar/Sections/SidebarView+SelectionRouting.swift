import SwiftUI

// MARK: - Selection routing by destination, including the cross-library step (#4995/#4996)
//
// Split out of `SidebarView+SelectionHandling.swift` (#5039), which had crossed the 400-line
// limit: this file holds everything that turns a typed `SidebarDestination` into a
// `sidebarMode`/`viewMode`, beside `CrossLibraryRoute` (which decides the cross-library step).

extension SidebarView {
    func handleSelectionDestination(_ destination: SidebarDestination) {
        // A newer selection supersedes one still waiting for its library.
        pendingCrossLibraryRoute = nil
        // A selection from ANOTHER library switches the window first and routes when that
        // lands — never in the same turn, while the content column still holds the old
        // library's stores (#4995/#4996, `CrossLibraryRoute`).
        let step = CrossLibraryRoute.firstStep(
            destinationLibraryId: libraryId(of: destination),
            windowLibraryId: windowState.libraryId
        )
        if case .switchLibraryFirst(let targetLibraryId) = step {
            sidebarViewLogger.info(
                "Switching window from library \(windowState.libraryId) to library \(targetLibraryId) before routing"
            )
            pendingCrossLibraryRoute = CrossLibraryRoute.Pending(libraryId: targetLibraryId, destination: destination)
            windowState.libraryId = targetLibraryId
            return
        }
        switch destination {
        case .library(let libraryId):
            if windowState.libraryId != libraryId {
                windowState.libraryId = libraryId
            }
            sidebarMode = .library
            viewMode = .library(nil)
            return
        case .knowledgeCollection(_, let libraryId):
            // A per-library KG collection makes THAT library active (so the
            // library-wide claims/entities table scopes to it) and lands in the
            // library — the pane reads `contentCollection` from the selected id to
            // pick which table. Same two axes as `.library`, plus the collection.
            if windowState.libraryId != libraryId {
                windowState.libraryId = libraryId
            }
            sidebarMode = .library
            viewMode = .library(nil)
            return
        case .browser(let section):
            handleBrowserSelectionDestination(section)
            return
        case .run:
            guard let selectedRun = unifiedSelectedRun(forSidebarId: destination.serializedID) else { return }
            viewMode = .activity(selectedRun.toSelectedRun())
            return
        default:
            routeItemSelection(for: destination)
        }
    }

    /// A destination that is an ITEM row: resolve it through the sidebar item index, or, for a
    /// document that missed it, through the stores.
    private func routeItemSelection(for destination: SidebarDestination) {
        let item = cachedItem(id: destination.serializedID)
        if item == nil {
            // S10 (2026-08-23): a DOCUMENT click whose id misses the
            // sidebar item index must still route — dropping it left the
            // content pane on the PARENT folder, which read as "clicking
            // the item selected its parent" and made run-workflow scope
            // to every sibling. The stores still know the document, so
            // resolve through them and route the SAME id.
            if case .document(let docId) = destination {
                for library in libraryManager.openLibraries {
                    if let doc = library.documentStore.resolveDocument(docId) {
                        sidebarViewLogger.warning(
                            "Selection \(docId, privacy: .public) missed the item index — routed via the document store"
                        )
                        routeDocumentSelection(doc, libraryId: library.id)
                        return
                    }
                }
            }
            // LOUD (workflow-routing bug): a click that resolves to
            // nothing routes NOTHING — the pane silently keeps its
            // previous mode, which reads as "it doesn't open the editor".
            sidebarViewLogger.error(
                "Selection \(destination.serializedID) resolved to NO cached item — content pane not rerouted"
            )
            // Launch-restore can arrive before the sidebar caches are
            // built; the id resolves to nothing yet. Un-stamp the
            // destination so `reconcileRestoredSelection()` (#2548)
            // re-drives it once caches exist — otherwise the restored
            // selection is marked handled without ever being applied
            // and the highlighted row never matches the detail view.
            lastHandledSelectionDestination = nil
        }
        handleSelection(item)
    }

    /// The library a destination belongs to, or `nil` for one that belongs to none (the
    /// browser sections, a run) or that the item index cannot resolve.
    private func libraryId(of destination: SidebarDestination) -> UUID? {
        switch destination {
        case .library(let libraryId), .knowledgeCollection(_, let libraryId):
            return libraryId
        case .browser, .run:
            return nil
        default:
            return cachedItem(id: destination.serializedID)?.libraryId
        }
    }

    /// Route the selection that was waiting for `landedLibraryId` (`.onChange(of:
    /// windowState.libraryId)`). If the window landed on a different library than the
    /// selection asked for, nothing routes and the selection is un-stamped so a re-click works.
    func routePendingCrossLibrarySelection(landedLibraryId: UUID) {
        let pending = pendingCrossLibraryRoute
        pendingCrossLibraryRoute = nil
        guard let destination = CrossLibraryRoute.destinationToRoute(
            pending: pending, landedLibraryId: landedLibraryId
        ) else {
            if pending != nil {
                sidebarViewLogger.error("Window landed on \(landedLibraryId), not the selection's library — not routed")
                lastHandledSelectionDestination = nil
            }
            return
        }
        handleSelectionDestination(destination)
    }

    // `SidebarBrowserDestination` routes each browser section to a distinct
    // sidebar mode/view mode — split out of `handleSelectionDestination` to keep
    // that switch's complexity low.
    private func handleBrowserSelectionDestination(_ section: SidebarBrowserDestination) {
        switch section {
        case .activity:
            sidebarMode = .activity
            viewMode = .activity(nil)
        case .workflows:
            sidebarMode = .workflows
            viewMode = .workflow(nil)
        case .batches:
            // BOTH axes, always (views audit 1d): setting only viewMode left
            // the mode bar/menus disagreeing with the pane.
            sidebarMode = .workflows
            viewMode = .batches
        case .entities, .claims:
            // Both KG collections land in the library, library-wide (the pane
            // reads `contentCollection` from the selected item id to pick which
            // table). One rule, two peer sections (P4).
            sidebarMode = .library
            viewMode = .library(nil)
        case .comparison:
            sidebarMode = .chat
            viewMode = .comparison(nil)
        case .research:
            // BOTH axes, always (views audit 1d): setting only sidebarMode
            // was the exact stale-pane bug — the center flips to Research
            // while preview/reader/inspector keep switching on viewMode.
            sidebarMode = .research
            viewMode = .library(nil)
        }
    }
}
