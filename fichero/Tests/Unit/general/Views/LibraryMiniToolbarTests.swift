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

    @Test("the mini toolbar keeps sort and filter; search moved to the window toolbar")
    func allThreeLiveInOneContainer() throws {
        // #4604 (2026-08-19) SUPERSEDED #4521's summoned field: search is a
        // RESIDENT top-right window field (ContentView+ToolbarSearch.swift),
        // so the mini toolbar keeps the two library-scoped controls only.
        let mini = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(mini.contains("var libraryMiniToolbar"))
        #expect(mini.contains("var librarySortMenu"))
        #expect(mini.contains("var libraryFilterToggleButton"))
        #expect(
            !mini.contains("librarySearchField"),
            "a second search field in the mini toolbar would compete with the #4604 resident one"
        )
    }

    /// One container, mounted once per edge — not one per control.
    @Test("the cluster lives ONLY inside the one bottom action bar")
    func clusterLivesInTheActionBar() throws {
        // ONE bottom row (Daniel, 2026-08-23): no PaneFilterBar mount for the
        // library cluster on either edge — the action bar's adaptive row
        // hosts it (inline when wide, overflow menu when narrow).
        let library = // LibraryView.swift was split 2026-08-13; scan all four parts.
            ((try Self.appSource("Views/Library/LibraryView.swift")) + (try Self.appSource("Views/Library/LibraryView+Body.swift")) + (try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")) + (try Self.appSource("Views/Library/LibraryView+Insets.swift")))
        #expect(!library.contains("PaneFilterBar(placement: .top) { libraryMiniToolbar }"))
        #expect(!library.contains("PaneFilterBar(placement: .bottom) { libraryMiniToolbar }"))
        let bar = try Self.appSource("Views/Library/LibraryView+BottomActionBar.swift")
        #expect(bar.contains("libraryMiniToolbar"))
        #expect(bar.contains("librarySortMenu"))
    }

    /// The reader keeps its find bar in the shared container at the shared
    /// bottom placement (its .top branch is Mac-dead by the one decision).
    @Test("the reader keeps the shared find-bar container")
    func readerKeepsTheSharedContainer() throws {
        let reader = try Self.appSource("Views/Reader/Page/ReadingPaneView.swift")
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
        // ONE persistent row since 2026-08-23: the transient ⌘F reveal sits
        // above the action bar, which hosts the whole cluster.
        let filter = body.range(of: "filterBarView")
        let bar = body.range(of: "libraryBottomActionBar")
        #expect(filter != nil)
        #expect(bar != nil)
        if let filter, let bar {
            #expect(filter.lowerBound < bar.lowerBound, "the reveal sits above the one bar")
        }
    }

    /// ANSWERED 2026-08-23 (supersedes the #4424 deferral): bottom, for every
    /// pane — one shared decision, one shared value.
    @Test("the placement decision is bottom, shared with the reader")
    func placementDecisionIsBottom() throws {
        let mini = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(mini.contains("MiniToolbarPlacement.preferredForReader"))
        // The library no longer branches on the placement at all: its ONE
        // bottom row is the action bar, unconditionally at the bottom.
    }

    // MARK: - Native toolbar search (Daniel, 2026-08-29, superseding #4604)

    /// #4604's resident hand-rolled lozenge is gone in turn: "not proper
    /// macOS search… use the default one". The SYSTEM search item carries the
    /// field (`.searchable` + `.searchToolbarBehavior(.minimize)`, the
    /// Mail-style magnifier collapse), sited as its OWN trailing item by
    /// `DefaultToolbarItem(kind: .search)` in the inspector-section toolbar.
    /// Still resident (no summon toggle), and still exactly ONE registration
    /// per window — the #3163 duplicate-identifier crash class.
    @Test("search is the native toolbar search item, its own trailing item")
    func searchIsTheNativeToolbarItem() throws {
        let toolbarSearch = try Self.appSource("Views/Shell/ContentView/ContentView+ToolbarSearch.swift")
        #expect(toolbarSearch.contains(".searchable("))
        #expect(toolbarSearch.contains("prompt: \"Search your library\""))
        #expect(toolbarSearch.contains(".searchToolbarBehavior(.minimize)"))
        // Submit fires the SAME engine-search action the old field fired.
        #expect(toolbarSearch.contains("runToolbarSearch(toolbarSearchText)"))
        // The hand-rolled lozenge would be a SECOND search UI now.
        #expect(!toolbarSearch.contains("var toolbarSearchField"))
        #expect(!toolbarSearch.contains("TextField("))

        // Sited in the inspector-section toolbar since 2026-08-23 (right of
        // the inspector toggle); the summon state stays gone in both homes.
        let inspector = try Self.appSource(
            "Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"
        )
        #expect(inspector.contains("DefaultToolbarItem(kind: .search"))
        #expect(inspector.contains("nativeToolbarSearch(detailView)"))
        let toolbar = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(!toolbar.contains(".searchable("))
        for source in [toolbar, inspector] {
            #expect(
                !source.contains("setSearchFieldVisible"),
                "the #4521 summon state is back — the field stays resident"
            )
        }
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
