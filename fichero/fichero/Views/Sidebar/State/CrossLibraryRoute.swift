import Foundation

/// The order of a sidebar selection that belongs to a DIFFERENT library than the one the window
/// is showing (#4995, #4996).
///
/// The per-library stores reach `ContentView` through the ENVIRONMENT (`LibraryWorkspaceRoot`
/// injects them), and the environment only changes once the window has re-evaluated for the new
/// `windowState.libraryId`. Routing the selection in the same turn as the library write set
/// `viewMode` while the content column still held the OLD library's stores, so the first load
/// asked the old library for the new library's document ("Document not found"), then the
/// library-change teardown cleared it all and every pane fetched again.
///
/// So a cross-library selection is two steps: switch the library and REMEMBER the selection;
/// route it when the switch lands (`SidebarView`'s `.onChange(of: windowState.libraryId)`).
/// Pure, so the rule is tested without a view.
enum CrossLibraryRoute {
    enum FirstStep: Equatable {
        /// Same library (or a destination that belongs to none): route immediately.
        case routeNow
        /// Different library: switch to it, route nothing yet.
        case switchLibraryFirst(UUID)
    }

    /// The selection waiting for its library to land.
    struct Pending: Equatable {
        let libraryId: UUID
        let destination: SidebarDestination
    }

    static func firstStep(destinationLibraryId: UUID?, windowLibraryId: UUID) -> FirstStep {
        guard let destinationLibraryId, destinationLibraryId != windowLibraryId else { return .routeNow }
        return .switchLibraryFirst(destinationLibraryId)
    }

    /// The destination to route now that the window shows `landedLibraryId` — `nil` when
    /// nothing is waiting, or when the window landed somewhere ELSE (the library closed under
    /// the click and the window fell back): routing then would be the wrong-library request
    /// this type exists to prevent.
    static func destinationToRoute(pending: Pending?, landedLibraryId: UUID) -> SidebarDestination? {
        guard let pending, pending.libraryId == landedLibraryId else { return nil }
        return pending.destination
    }
}
