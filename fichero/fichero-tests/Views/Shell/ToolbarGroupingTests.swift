@testable import Fichero
import Foundation
import Testing

/// #4374: the window toolbar's information architecture.
///
/// Six controls of three different kinds sat in one undifferentiated
/// `.automatic` run: a display-mode menu, three pane toggles, a sort menu and a
/// filter toggle. Nothing told the system that the three toggles are one
/// control and the two library controls are another, which is why overflow shed
/// an arbitrary pane toggle rather than collapsing a group as a unit. The
/// missing structure was the bug; the spacing was its symptom.
struct ToolbarGroupingTests {
    private static func appSource(_ relativePath: String) throws -> String {
        // FOUR components: this file sits at fichero-tests/Views/Shell/, so
        // stripping three lands on `fichero-tests` and every read resolved to
        // fichero-tests/fichero/... — a path that cannot exist. Every test here
        // failed with NSCocoaErrorDomain "no such file" while the app was fine.
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static var toolbarSource: String {
        get throws { try appSource("Views/Shell/ContentView/ContentView+Toolbar.swift") }
    }

    // MARK: - The redundant View button is gone

    /// It rendered the same panes the adjacent toggles toggle and the same
    /// display mode the adjacent menu offers. Every item in it had a direct
    /// control within a few points.
    @Test("the toolbar no longer hosts a View menu")
    func toolbarHasNoViewMenu() throws {
        let source = try Self.toolbarSource
        #expect(!source.contains("ToolbarItem(id: ContentToolbarID.viewMenu"))
        #expect(!source.contains("platformViewMenuButton"))
        #expect(!source.contains("ViewMenuCommands()"))
    }

    /// Deleting the button means deleting its identifier and its glyph too —
    /// a dangling id or an orphaned symbol is how a "deleted" control comes
    /// back.
    @Test("the View menu's identifier and glyph are gone with it")
    func viewMenuIdentifierAndGlyphAreGone() throws {
        let source = try Self.toolbarSource
        #expect(!source.contains("static let viewMenu"))

        let symbols = try Self.appSource("Views/Shell/Toolbar/ToolbarSymbols.swift")
        #expect(!symbols.contains("static let viewMenu"))
        #expect(!symbols.contains("(\"view menu\""))
    }

    /// The commands themselves are NOT deleted — a complete list of view
    /// commands belongs in the menu bar, and that is where it stays.
    @Test("the view commands still live in the menu bar")
    func viewCommandsRemainInTheMenuBar() throws {
        let app = try Self.appSource("FicheroApp.swift")
        #expect(app.contains("ViewMenuCommands()"))
        #expect(app.contains("CommandGroup(after: .toolbar)"))
    }

    // MARK: - The controls are grouped

    /// `ToolbarItemGroup` has NO identified initialiser — only
    /// `(placement:content:)` — so the group is recognised by being the one
    /// and only `ToolbarItemGroup` in the file, not by an id (7e02f0954
    /// deleted `ContentToolbarID.paneToggleGroup` with the last reference).
    ///
    /// Shape assertions come BEFORE any subscript: the previous version did a
    /// bare `[1]` on a split whose separator had left the file, and an Array
    /// bounds trap in a test kills the whole host — every test after it in
    /// run order reports failed (the 2026-08-04 whole-suite red).
    @Test("the three pane toggles are one group")
    func paneTogglesAreOneGroup() throws {
        let source = try Self.toolbarSource
        let parts = source.components(separatedBy: "ToolbarItemGroup(")
        try #require(
            parts.count == 2,
            "expected exactly one ToolbarItemGroup — the three-pane control — found \(parts.count - 1)"
        )
        // Bound the group at the next ToolbarItem so membership means "inside
        // THIS builder", not "later in the file". The search toggle (#4521)
        // is deliberately its own item, never a fourth member.
        let group = parts[1].components(separatedBy: "ToolbarItem(").first ?? parts[1]
        // …and the three members are inside it, in column order.
        let library = group.range(of: "libraryPaneToggleButton")
        let preview = group.range(of: "Preview Pane")
        let reading = group.range(of: "Reading Pane")
        #expect(library != nil)
        #expect(preview != nil)
        #expect(reading != nil)
        if let library, let preview, let reading {
            #expect(library.lowerBound < preview.lowerBound)
            #expect(preview.lowerBound < reading.lowerBound)
        }
    }

    /// #4407 dissolved the window-level sort/filter group entirely: the
    /// controls follow the pane they act on, into the library's mini toolbar.
    /// The invariant is now absence here plus presence there — a second sort
    /// path reappearing in the window chrome is the #4282 duplicate class.
    @Test("sort and filter live in the library mini toolbar, not window chrome")
    func libraryControlsLiveInTheMiniToolbar() throws {
        let source = try Self.toolbarSource
        #expect(!source.contains("librarySortMenu"))
        #expect(!source.contains("libraryFilterToggleButton"))
        let mini = try Self.appSource("Views/Library/LibraryView+MiniToolbar.swift")
        #expect(mini.contains("librarySortMenu"))
        #expect(mini.contains("libraryFilterToggleButton"))
    }

    /// The per-item identifiers the toggles used to carry are gone: leaving
    /// them behind would be dead constants that read as live toolbar items.
    @Test("the grouped items' old individual identifiers are gone")
    func oldPerItemIdentifiersAreGone() throws {
        let source = try Self.toolbarSource
        for dead in [
            "static let libraryPaneToggle",
            "static let previewPaneToggle",
            "static let readingPaneToggle",
            "static let librarySortMenu =",
            "static let libraryFilterToggle",
        ] {
            #expect(!source.contains(dead), Comment(rawValue: dead))
        }
    }

    /// #3163: every window toolbar ITEM carries an explicit id. Groups cannot
    /// — `ToolbarItemGroup` has no identified initialiser (7e02f0954), so the
    /// old form of this test ("every group has an id") could never pass. A
    /// group is positional; customisation identity belongs to the items.
    @Test("every toolbar item carries an explicit identifier")
    func everyItemHasAnExplicitIdentifier() throws {
        // Strip the status-island VIEW first: `StatusIslandToolbarItem(` is a
        // plain view whose name merely ends in "ToolbarItem(".
        let source = try Self.toolbarSource
            .replacingOccurrences(of: "StatusIslandToolbarItem(", with: "")
        let itemDeclarations = source.components(separatedBy: "ToolbarItem(").count - 1
        let identifiedItems = source.components(separatedBy: "ToolbarItem(id: ").count - 1
        #expect(itemDeclarations > 0, "no ToolbarItem declarations found — wrong file?")
        #expect(itemDeclarations == identifiedItems, "an unidentified ToolbarItem exists")
    }

    // MARK: - Left alone on purpose

    /// The Filter flag is OFF, not broken (`libraryFilterToolbarEnabledInternal`
    /// defaults false and `resetToV001()` sets it false again). Whether to
    /// enable or delete it is a product decision that needs the filter bar
    /// exercised first, so this change does not touch it — and this test says
    /// so, to stop a later sweep "tidying" it up on the way past.
    @Test("the filter feature flag is deliberately untouched")
    func filterFlagIsUntouched() throws {
        let manager = try Self.appSource("Models/FeatureManager.swift")
        #expect(manager.contains("libraryFilterToolbarEnabledInternal"))
        let tiers = try Self.appSource("Models/FeatureManager+Tiers.swift")
        #expect(tiers.contains("libraryFilterToolbarEnabledInternal = false"))
    }

    /// The `.principal` zone is a separate problem (#4378): breadcrumb and
    /// status island both claim it, and that needs settling before either
    /// #4378 / #3163: `.principal` is a SINGLE slot. Two items claiming it is
    /// a duplicate-identifier crash, not a layout that resolves badly — and it
    /// is invisible in review because each declaration reads fine alone.
    ///
    /// Counts the whole toolbar rather than naming the two known items, so a
    /// third claimant added later fails here instead of at runtime.
    @Test("exactly one toolbar item claims .principal")
    func exactlyOnePrincipalItem() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        let principals = source.components(separatedBy: "placement: .principal").count - 1
        #expect(principals == 1, Comment(rawValue: "\(principals) items claim .principal"))
    }

    /// The breadcrumb is the one that keeps it: `.principal` is the window's
    /// identity slot, which is what makes the proxy icon and ⌘-click-to-parent
    /// possible at all. Status is chrome about a transient condition.
    @Test("the breadcrumb owns the identity slot")
    func breadcrumbOwnsTheIdentitySlot() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(source.contains("ToolbarItem(id: ContentToolbarID.breadcrumb, placement: .principal)"))
    }

    /// #4519 settled the principal zone: the breadcrumb keeps the identity
    /// slot and the status island rides INSIDE it — status beside the path,
    /// not among the pane toggles, and never a second `.principal` claimant.
    @Test("status rides inside the breadcrumb item, not as its own claimant")
    func statusRidesInsideTheBreadcrumbItem() throws {
        let source = try Self.toolbarSource
        #expect(source.contains("ToolbarItem(id: ContentToolbarID.breadcrumb, placement: .principal)"))
        // #4519: no standalone island item at ANY placement — a standalone
        // `.automatic` item is what macOS laid beside the pane-toggle group,
        // making status glyphs read as extra toggles (#4391).
        #expect(!source.contains("ContentToolbarID.statusIsland"))
        #expect(source.contains("StatusIslandToolbarItem("))
    }
}
