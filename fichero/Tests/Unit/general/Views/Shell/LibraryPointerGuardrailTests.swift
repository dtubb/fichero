@testable import Fichero
import Testing

/// #4860 (`panes.head.names-its-own-window`): no view may read the app-wide
/// `LibraryManager.shared.currentLibraryId`. With two window tabs on different libraries it names
/// whichever tab was activated most recently ANYWHERE, so a pane head, drag payload or
/// new-window open would use the WRONG library. Every view reads its own window's
/// `windowState.libraryId` instead.
///
/// One tree-wide scan replaces the per-site scrapes in `LibraryPaneHeadOwnWindowTests` and
/// `PaneOwnWindowLibraryTests` (#5052): the property is the ABSENCE of a pointer, and a new view
/// that reads it would have slipped past a list of named sites.
struct LibraryPointerGuardrailTests {
    @Test("no view under Views/ reads the app-wide current-library pointer")
    func noViewReadsTheAppWideLibraryPointer() throws {
        // The walk lives in AppSource because it needs Foundation, and importing
        // Foundation into a `Testing` file broke this toolchain's whole build
        // (2026-09-20). Files come back comment-stripped: doc comments here and in
        // the views name the pointer to explain what they replaced.
        let views = try AppSource.swiftFiles(under: "Views")
        let offenders = views
            .filter { $0.code.contains("LibraryManager.shared.currentLibraryId") }
            .map(\.path)
        #expect(
            views.count > 100,
            "the scan must actually see the views (saw \(views.count)), never pass vacuously"
        )
        #expect(
            offenders.isEmpty,
            "These views read LibraryManager.shared.currentLibraryId; use their own windowState.libraryId (#4860): \(offenders.joined(separator: ", "))"
        )
    }
}
