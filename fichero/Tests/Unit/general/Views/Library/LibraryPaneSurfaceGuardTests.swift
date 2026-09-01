@testable import Fichero
import Foundation
import Testing

/// Source guards for the two library-pane surfaces Daniel re-tested on
/// 2026-09-01 and found still broken: the bottom bar that must be the SAME bar
/// in every view mode, and the pane drop that must accept files at the folder
/// the pane is showing (the library root included).
///
/// Both are structural facts about which modifier is mounted where, so a source
/// guard is the honest instrument: neither can be observed from a pure function,
/// and both regressed once already by a control being moved rather than by any
/// logic changing.
@Suite("Library pane — one bottom bar, and a pane that accepts drops")
struct LibraryPaneSurfaceGuardTests {

    private static func appSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        #expect(!source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }

    // MARK: - One bottom bar (Daniel: "data/dataset mode shows a different bar")

    @Test("every view mode mounts the ONE bottom action bar")
    func oneBottomBarForEveryMode() throws {
        // `bottomInsetContent` is unconditional — no mode branch may reach it.
        // Sliced to that property's own body: the file also hosts the spatial
        // projection helper, which reads `displayMode` for unrelated reasons.
        let insets = try Self.appSource("Views/Library/LibraryView+Insets.swift")
        let marker = "var bottomInsetContent: some View {"
        let body = try #require(insets.range(of: marker)).upperBound
        let end = try #require(insets.range(of: "// MARK: - Spatial projection", range: body ..< insets.endIndex))
        let inset = String(insets[body ..< end.lowerBound])
        #expect(inset.contains("libraryBottomActionBar"))
        #expect(
            !inset.contains("displayMode"),
            "the bottom inset started branching on the view mode — that is a second bar"
        )
    }

    @Test("the shared Show control is not suppressed in Data mode")
    func showControlIsNotModeSwapped() throws {
        let bar = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(
            !bar.contains("if displayMode.group != .dataset {"),
            """
            Data mode is hiding a shared bar control again. Mode-specific \
            controls are added INLINE as extras; nothing may be swapped out \
            from under the user (Daniel, 2026-09-01).
            """
        )
        #expect(bar.contains("libraryLevelToggle"))
        #expect(bar.contains("librarySortMenu"))
        #expect(bar.contains("libraryFilterToggleButton"))
    }

    @Test("the dataset cluster is an extra, not a second Show menu")
    func datasetClusterCarriesNoLevel() throws {
        let cluster = try Self.appSource("Views/Library/ViewModes/Dataset/DatasetFilterCluster.swift")
        #expect(
            !cluster.contains("Section(\"Level\")"),
            """
            The dataset cluster grew the reading level back. The level is a \
            library-wide fact (DocumentStore.libraryLevel) and belongs to the \
            one shared Show control every mode carries.
            """
        )
        #expect(cluster.contains("Label(\"Types\""))
    }

    // MARK: - Drop to the library root (Daniel: "not sure it works")

    @Test("the library pane itself is a drop target, not only its folder cells")
    func paneAcceptsDrops() throws {
        let body = try Self.appSource("Views/Library/LibraryView+Body.swift")
        #expect(
            body.contains(".modifier(libraryPaneDrop)"),
            """
            The library pane has no drop target of its own again. Without it a \
            Finder drag onto the gutter, the empty-folder placeholder, or a \
            non-folder row lands on nothing at all.
            """
        )
        // The alert that reports a failed pane drop must stay with it.
        #expect(body.contains("LibraryDropAlertModifier"))
    }

    @Test("a pane drop targets the browsed folder, and nil means the ROOT")
    func paneDropTargetsBrowsedFolderOrRoot() throws {
        let drop = try Self.appSource("Views/Library/ViewModes/LibraryView+PaneDrop.swift")
        #expect(drop.contains("struct LibraryPaneDrop"))
        #expect(drop.contains("func handleLibraryPaneDrop"))
        // It must route through the ONE shared root rule, not a private copy —
        // the sidebar header and the Data menu already use it.
        #expect(
            drop.contains("libraryRootImportBatches("),
            "the pane invented its own root routing instead of sharing #4274's"
        )
        // The pane drop reads the folder it is SHOWING.
        #expect(drop.contains("let targetFolderId = folderId"))
    }
}
