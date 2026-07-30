@testable import Fichero
import Foundation
import Testing

/// #4407 + #4374 finding 3: **a control lives with the surface it acts on.**
///
/// Search, sort and filter all act on the library list, so they belong above
/// that list — resizing with the pane, disappearing with it. Window chrome is
/// for things that act on the window.
///
/// Built as ONE container carrying all three rather than three separate
/// relocations: three passes over the same layout is three chances for the
/// container to end up subtly different. These tests hold that it stayed one.
struct LibraryMiniToolbarTests {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    // MARK: - The three controls left the window

    @Test("sort and filter are gone from the window toolbar")
    func sortAndFilterLeftTheWindowToolbar() throws {
        let toolbar = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(!toolbar.contains("var librarySortMenu"))
        #expect(!toolbar.contains("var libraryFilterToggleButton"))
        #expect(!toolbar.contains("ContentToolbarID.libraryControlsGroup"))
        #expect(!toolbar.contains("static let libraryControlsGroup"))
    }

    /// The window-level `.searchable` is what actually spanned three panes:
    /// it attaches to a NAVIGATION CONTAINER, and this one was on the whole
    /// `NavigationSplitView`, so `.searchScopes` drew the Ask/Keyword selector
    /// across library + preview + reader.
    @Test("the window-level searchable and its scope bar are gone")
    func theWindowSearchableIsGone() throws {
        let root = try Self.appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        #expect(!root.contains(".searchable("))
        #expect(!root.contains(".searchScopes("))
        // …and the modifier that applied them is deleted, not merely unused.
        #expect(!root.contains("private struct ToolbarSearchableModifier"))
    }

    /// The special case dissolves rather than moving: sort/filter used to sit
    /// outside the split-pane block because "sorting and filtering a list is
    /// not a split-pane concept". Once they belong to the library pane they
    /// follow it, compact flow included, and there is nothing left to except.
    @Test("the split-pane workaround is deleted, not ported")
    func theSplitPaneWorkaroundIsDeleted() throws {
        let toolbar = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(!toolbar.contains("not a split-pane concept"))
    }

    // MARK: - …and arrived in one container

    @Test("all three controls live in the one library mini toolbar")
    func allThreeLiveInOneContainer() throws {
        let mini = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(mini.contains("var libraryMiniToolbar"))
        #expect(mini.contains("librarySearchField"))
        #expect(mini.contains("var librarySortMenu"))
        #expect(mini.contains("var libraryFilterToggleButton"))
    }

    /// One container, mounted once per edge — not one per control.
    @Test("the container is mounted exactly once per edge")
    func containerIsMountedOncePerEdge() throws {
        let library = try Self.appSource("Views/Library/LibraryView.swift")
        #expect(
            library.components(separatedBy: "PaneFilterBar(placement: .top) { libraryMiniToolbar }")
                .count - 1 == 1
        )
        #expect(
            library.components(separatedBy: "PaneFilterBar(placement: .bottom) { libraryMiniToolbar }")
                .count - 1 == 1
        )
    }

    /// It uses the SAME shared container and the SAME platform decision as the
    /// reader's find bar — the bar that was already correctly scoped, and the
    /// reason the window-spanning one looked wrong beside it.
    @Test("it reuses the reader's container and placement decision")
    func itReusesTheReadersModel() throws {
        let mini = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(mini.contains("MiniToolbarPlacement.preferredForReader"))

        let library = try Self.appSource("Views/Library/LibraryView.swift")
        #expect(library.contains("PaneFilterBar("))

        // The reader still owns its own find bar — unchanged, and still the model.
        let reader = try Self.appSource("Views/Reader/Page/ReadingPaneView.swift")
        #expect(reader.contains("PaneFilterBar(placement: .top) { readerFindBar }"))
        #expect(reader.contains("PaneFilterBar(placement: .bottom) { readerFindBar }"))
    }

    /// The pane has to be handed the field's state, since the field no longer
    /// lives where that state does.
    @Test("the search field's state reaches the pane that now owns the field")
    func searchStateReachesThePane() throws {
        let library = try Self.appSource("Views/Library/LibraryView.swift")
        #expect(library.contains("var searchFieldText: Binding<String>"))
        #expect(library.contains("var searchFieldMode: Binding<SearchFieldMode>"))

        let navigation = try Self.appSource("Views/Shell/ContentView/ContentView+Navigation.swift")
        #expect(navigation.contains("searchFieldText: $toolbarSearchText"))
        #expect(navigation.contains("searchFieldMode: Binding("))
    }

    // MARK: - Left alone on purpose

    /// Moving the control does not decide whether to enable the feature. The
    /// flag defaults to `false` and `resetToV001()` sets it `false` again —
    /// Filter is switched OFF, not broken, and turning it on needs someone to
    /// exercise the filter bar first (#4374 finding 4).
    @Test("the filter feature flag is still untouched")
    func filterFlagIsStillUntouched() throws {
        let tiers = try Self.appSource("Models/FeatureManager+Tiers.swift")
        #expect(tiers.contains("libraryFilterToolbarEnabledInternal = false"))
        let mini = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        // The control still asks the flag rather than assuming it.
        #expect(mini.contains("featureManager.isLibraryFilterToolbarEnabled"))
    }
}
