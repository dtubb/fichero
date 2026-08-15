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
        let url = try AppSource.root()
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
        let library = // LibraryView.swift was split 2026-08-13; scan all four parts.
            ((try Self.appSource("Views/Library/LibraryView.swift")) + (try Self.appSource("Views/Library/LibraryView+Body.swift")) + (try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")) + (try Self.appSource("Views/Library/LibraryView+Insets.swift")))
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

        let library = // LibraryView.swift was split 2026-08-13; scan all four parts.
            ((try Self.appSource("Views/Library/LibraryView.swift")) + (try Self.appSource("Views/Library/LibraryView+Body.swift")) + (try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")) + (try Self.appSource("Views/Library/LibraryView+Insets.swift")))
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
        let library = // LibraryView.swift was split 2026-08-13; scan all four parts.
            ((try Self.appSource("Views/Library/LibraryView.swift")) + (try Self.appSource("Views/Library/LibraryView+Body.swift")) + (try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")) + (try Self.appSource("Views/Library/LibraryView+Insets.swift")))
        #expect(library.contains("var searchFieldText: Binding<String>"))
        #expect(library.contains("var searchFieldMode: Binding<SearchFieldMode>"))

        let navigation = try Self.appSource("Views/Shell/ContentView/ContentView+Navigation.swift")
        #expect(navigation.contains("searchFieldText: $toolbarSearchText"))
        #expect(navigation.contains("searchFieldMode: Binding("))
    }

    // MARK: - Scope order at the bottom edge (#4424)

    /// ONE bottom inset, not two. SwiftUI applies insets outward in modifier
    /// order, so a second `.safeAreaInset(edge: .bottom)` added later lands
    /// FURTHEST from the content — which is how the window-scoped status row
    /// ended up beneath the pane-scoped mini toolbar. Two bottom insets is two
    /// orderings competing; one with a stated order cannot drift.
    @Test("the library has exactly one bottom safe-area inset")
    func oneBottomInset() throws {
        let source = // LibraryView.swift was split 2026-08-13; scan all four parts.
            ((try Self.appSource("Views/Library/LibraryView.swift")) + (try Self.appSource("Views/Library/LibraryView+Body.swift")) + (try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")) + (try Self.appSource("Views/Library/LibraryView+Insets.swift")))
        let code = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        #expect(code.components(separatedBy: ".safeAreaInset(edge: .bottom").count - 1 == 1)
    }

    /// Content outward: the pane's own control, then the row it reveals, then
    /// the status bar beneath everything. A control lives with the surface it
    /// acts on; the status row belongs to the window and must be outermost.
    @Test("the bottom stack runs pane-scoped first, window-scoped last")
    func bottomStackOrderFollowsScope() throws {
        let source = // LibraryView.swift was split 2026-08-13; scan all four parts.
            ((try Self.appSource("Views/Library/LibraryView.swift")) + (try Self.appSource("Views/Library/LibraryView+Body.swift")) + (try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")) + (try Self.appSource("Views/Library/LibraryView+Insets.swift")))
        // Promoted private -> internal in the 2026-08-13 LibraryView file
        // split. Guarded: a force-[1] on a missed anchor crashes the whole
        // test PROCESS, taking unrelated suites down with it.
        let pieces = source.components(separatedBy: "var bottomInsetContent: some View {")
        try #require(pieces.count > 1, "bottomInsetContent declaration not found")
        let body = pieces[1]
            .components(separatedBy: "\n    }")[0]
        let mini = body.range(of: "libraryMiniToolbar")
        let filter = body.range(of: "filterBarView")
        let status = body.range(of: "libraryBottomActionBar")
        #expect(mini != nil)
        #expect(filter != nil)
        #expect(status != nil)
        if let mini, let filter, let status {
            #expect(mini.lowerBound < filter.lowerBound, "the pane's control sits nearest its rows")
            #expect(filter.lowerBound < status.lowerBound, "the status row is outermost")
        }
    }

    /// The top/bottom question for Mac mini toolbars is Daniel's to decide and
    /// is explicitly deferred (#4424) — this change must not have quietly
    /// answered it. The placement still comes from the one shared decision.
    @Test("the placement decision is untouched and still shared with the reader")
    func placementDecisionIsUntouched() throws {
        let mini = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(mini.contains("MiniToolbarPlacement.preferredForReader"))
        let library = // LibraryView.swift was split 2026-08-13; scan all four parts.
            ((try Self.appSource("Views/Library/LibraryView.swift")) + (try Self.appSource("Views/Library/LibraryView+Body.swift")) + (try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")) + (try Self.appSource("Views/Library/LibraryView+Insets.swift")))
        #expect(library.contains("if Self.miniToolbarPlacement == .top"))
        #expect(library.contains("if Self.miniToolbarPlacement == .bottom"))
    }

    // MARK: - Summoned search (#4521)

    /// The search field is summoned, not resident: the mini toolbar renders
    /// it only while `searchFieldVisible` is on, and a toolbar toggle exists
    /// to turn it on — without the toggle, conditional chrome would make
    /// search unreachable.
    @Test("the search field is summoned by a toolbar toggle, not resident")
    func searchFieldIsSummonedNotResident() throws {
        let mini = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(mini.contains("if searchFieldVisible.wrappedValue {"))

        let toolbar = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(toolbar.contains("ToolbarItem(id: ContentToolbarID.searchToggle"))
        #expect(toolbar.contains("setSearchFieldVisible($0)"))
        // Deliberately NOT `.searchable`: it attaches to a navigation
        // container (the #4407 three-pane span, and the duplicate-.searchable
        // crash class). The summon state is plain per-window storage instead.
        #expect(!toolbar.contains(".searchable("))
    }

    /// Dismissing the chrome exits transient-search presentation through the
    /// ONE existing path — hiding the field must not leave the library
    /// silently showing results for a query nobody can see (#4106/S2).
    @Test("dismissing the field clears the transient search")
    func dismissClearsTheTransientSearch() throws {
        let actions = try Self.appSource("Views/Shell/ContentView/Actions/ContentView+ActionsUI.swift")
        let handler = actions
            .components(separatedBy: "func setSearchFieldVisible(")[1]
            .components(separatedBy: "\n    }")[0]
        #expect(handler.contains("clearTransientSearch()"))
        #expect(handler.contains("toolbarSearchText = \"\""))
    }

    /// A programmatic search (entity lozenge, saved search) summons the
    /// chrome too — results with no visible query field would read as an
    /// unexplained library.
    @Test("a programmatic search summons the chrome")
    func programmaticSearchSummonsTheChrome() throws {
        let run = try Self.appSource("Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift")
        let body = run
            .components(separatedBy: "func runToolbarSearch(")[1]
            .components(separatedBy: "\n    }")[0]
        #expect(body.contains("showSearchField = true"))
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
