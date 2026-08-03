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

    @Test("the three pane toggles are one group")
    func paneTogglesAreOneGroup() throws {
        let source = try Self.toolbarSource
        #expect(source.contains("ToolbarItemGroup(id: ContentToolbarID.paneToggleGroup"))
        // Exactly one USE — a second would be the #3163 duplicate class.
        #expect(source.components(separatedBy: "ContentToolbarID.paneToggleGroup").count - 1 == 1)
        // …and the three members are inside it, in column order.
        let group = source.components(separatedBy: "ContentToolbarID.paneToggleGroup")[1]
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

    @Test("sort and filter are a separate group from the pane toggles")
    func libraryControlsAreTheirOwnGroup() throws {
        let source = try Self.toolbarSource
        #expect(source.contains("ToolbarItemGroup(id: ContentToolbarID.libraryControlsGroup"))
        #expect(source.components(separatedBy: "ContentToolbarID.libraryControlsGroup").count - 1 == 1)
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

    /// #3163: every window toolbar item and group carries an explicit id, and
    /// the groups are declared unconditionally within their zone rather than
    /// appearing and disappearing with state.
    @Test("every toolbar group carries an explicit identifier")
    func everyGroupHasAnExplicitIdentifier() throws {
        let source = try Self.toolbarSource
        let groupDeclarations = source.components(separatedBy: "ToolbarItemGroup(").count - 1
        let identifiedGroups = source.components(separatedBy: "ToolbarItemGroup(id: ").count - 1
        #expect(groupDeclarations == identifiedGroups, "an unidentified ToolbarItemGroup exists")
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

    /// moves. Recorded so the next reader knows it is known.
    @Test("the principal zone is still contested and untouched")
    func principalZoneIsUntouched() throws {
        let source = try Self.toolbarSource
        #expect(source.contains("ToolbarItem(id: ContentToolbarID.breadcrumb, placement: .principal)"))
        // #4378: the island moved OFF `.principal` — the breadcrumb owns the
        // identity slot, and two principal items is the #3163 crash class.
        #expect(source.contains("ToolbarItem(id: ContentToolbarID.statusIsland, placement: .automatic)"))
        #expect(!source.contains("ToolbarItem(id: ContentToolbarID.statusIsland, placement: .principal)"))
    }
}
