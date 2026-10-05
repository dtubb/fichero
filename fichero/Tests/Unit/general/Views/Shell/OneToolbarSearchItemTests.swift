#if os(macOS)
@testable import Fichero
import AppKit
import SwiftUI
import Testing

/// #5024 (ruled 2026-09-20) + #5225: the toolbar has ONE search item. Its
/// magnifier menu holds Ask / Keyword with a checkmark on the active one, and
/// everything the second "Search Options" button used to offer; the
/// Ask/Keyword bar under the toolbar is gone. Spec:
/// `search.one-toolbar-button-with-the-kind-menu` (ui/search.md).
///
/// The menu is exercised as the real `NSMenu` the field hangs off its
/// magnifier, over real bindings, because a menu that LOOKS right but writes
/// nothing is exactly the class of defect a source scan cannot see.
@MainActor
struct OneToolbarSearchItemTests {

    /// The window's search state, as the bindings ContentView passes.
    @MainActor
    final class SearchState {
        var mode: SearchFieldMode = .ask
        var scopeIsFolder = false
        var searchType = SearchRetrievalTier.semantic.requestValue
        var saves = 0
    }

    private static func options(
        _ state: SearchState,
        folder: TransientSearchFolder? = nil,
        reviewed: Int? = nil,
        canSave: Bool = false
    ) -> SearchFieldOptionsMenu {
        SearchFieldOptionsMenu(
            mode: Binding(get: { state.mode }, set: { state.mode = $0 }),
            scopeIsFolder: Binding(get: { state.scopeIsFolder }, set: { state.scopeIsFolder = $0 }),
            searchType: Binding(get: { state.searchType }, set: { state.searchType = $0 }),
            libraryName: "Marshall Diaries",
            contextFolder: folder,
            reviewedEntityCount: reviewed,
            canSave: canSave,
            onSave: { state.saves += 1 }
        )
    }

    private static func item(_ title: String, in menu: NSMenu) throws -> NSMenuItem {
        try #require(menu.items.first { $0.title == title && !$0.isSectionHeader })
    }

    private static func choose(_ title: String, in menu: NSMenu) throws {
        let index = menu.index(of: try item(title, in: menu))
        menu.performActionForItem(at: index)
    }

    // MARK: - The kind is chosen in the one menu

    /// The ruling's core: picking Keyword in the search item's menu is what
    /// sets the search kind the next query runs with — the one state
    /// (`search.fieldMode`) `runToolbarSearch` reads.
    @Test("choosing Keyword then Ask from the menu sets the search kind")
    func choosingFromTheMenuSetsTheKind() throws {
        let state = SearchState()
        try Self.choose("Keyword", in: Self.options(state).nsMenu)
        #expect(state.mode == .keyword)
        try Self.choose("Ask", in: Self.options(state).nsMenu)
        #expect(state.mode == .ask)
    }

    /// "with a checkmark on the active one": the mark follows the state, so
    /// the menu says which kind will run.
    @Test("the checkmark sits on the active kind and only there")
    func checkmarkFollowsTheActiveKind() throws {
        let state = SearchState()
        state.mode = .keyword
        let menu = Self.options(state).nsMenu
        #expect(try Self.item("Keyword", in: menu).state == .on)
        #expect(try Self.item("Ask", in: menu).state == .off)
    }

    /// The field COPIES its menu template; a row that only works on the
    /// original would be a menu that does nothing when clicked.
    @Test("a copied menu row still sets the kind")
    func copiedRowStillWrites() throws {
        let state = SearchState()
        let original = try Self.item("Keyword", in: Self.options(state).nsMenu)
        let copy = try #require(original.copy() as? NSMenuItem)
        let target = try #require(copy.target as? NSObject)
        target.perform(copy.action, with: copy)
        #expect(state.mode == .keyword)
    }

    // MARK: - Nothing the second button offered is lost

    /// The "Search Options" button's rows (where it looks, search type, Save
    /// Search) moved into this one menu; deleting the button must not delete
    /// what it did.
    @Test("the menu holds scope, search type and Save Search")
    func menuHoldsWhatTheSecondButtonOffered() throws {
        let state = SearchState()
        let folder = TransientSearchFolder(id: "f1", name: "1885", path: ["Diaries", "1885"])
        let menu = Self.options(state, folder: folder, canSave: true).nsMenu

        try Self.choose("Diaries ▸ 1885", in: menu)
        #expect(state.scopeIsFolder)

        try Self.choose(SearchRetrievalTier.fulltext.title, in: menu)
        #expect(state.searchType == SearchRetrievalTier.fulltext.requestValue)

        try Self.choose("Save Search", in: menu)
        #expect(state.saves == 1)
    }

    /// Absent rather than dead: no context folder → no scope rows; nothing
    /// to save → no Save row; and the graph rung, when unavailable, is
    /// disabled with the sentence saying why.
    @Test("rows with nothing to do are absent, and a dead rung says why")
    func absentAndDeadRowsAreHonest() throws {
        let state = SearchState()
        let menu = Self.options(state, reviewed: 0).nsMenu
        #expect(!menu.items.contains { $0.title == "Marshall Diaries" })
        #expect(!menu.items.contains { $0.title == "Save Search" })
        let graph = try Self.item(SearchRetrievalTier.semanticGraph.title, in: menu)
        #expect(!graph.isEnabled)
        #expect(graph.toolTip == SearchRetrievalTier.noGraphHelp)
    }

    // MARK: - The field itself

    /// Enter submits the text through the same action the old field fired;
    /// the clear button (an empty string) only empties the text, which is
    /// what exits the results.
    @Test("Enter submits; clearing empties the text without searching")
    func submitAndClear() {
        var text = ""
        var submitted: [String] = []
        let view = ToolbarSearchField(
            text: Binding(get: { text }, set: { text = $0 }),
            options: Self.options(SearchState()),
            onSubmit: { submitted.append($0) }
        )
        let coordinator = ToolbarSearchField.Coordinator(view)
        let field = NSSearchField()

        field.stringValue = "Quibdó"
        coordinator.submit(field)
        #expect(text == "Quibdó")
        #expect(submitted == ["Quibdó"])

        field.stringValue = ""
        coordinator.submit(field)
        #expect(text == "")
        #expect(submitted == ["Quibdó"])
    }

    // MARK: - One toolbar item, no scope bar

    /// SwiftUI toolbar content cannot be enumerated at run time, so the
    /// declaration is read: the Mac branch declares exactly one search item,
    /// not the system item plus a second options loupe.
    @Test("the Mac toolbar declares one search item, not two")
    func macToolbarDeclaresOneSearchItem() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"
            ),
            encoding: .utf8
        )
        let afterMac = try #require(
            source.components(separatedBy: "#if os(macOS)").dropFirst().first
        )
        let macBranch = try #require(afterMac.components(separatedBy: "#else").first)
        #expect(macBranch.components(separatedBy: "ToolbarItem(").count - 1 == 1)
        #expect(macBranch.contains("ContentToolbarID.search,"))
        #expect(macBranch.contains("toolbarSearchItem"))
        #expect(!macBranch.contains("DefaultToolbarItem(kind: .search"))
        #expect(!macBranch.contains("searchOptions"))
    }

    /// The bar under the toolbar WAS `.searchScopes`; no live registration
    /// of it may survive anywhere in the app.
    @Test("no view registers search scopes, so the bar under the toolbar is gone")
    func scopeBarIsGone() throws {
        let root = try AppSource.root()
        let files = try #require(FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil))
        var offenders: [String] = []
        for case let url as URL in files where url.pathExtension == "swift" {
            let source = try String(contentsOf: url, encoding: .utf8)
            let live = source.split(separator: "\n").contains { line in
                let code = line.components(separatedBy: "//").first ?? ""
                return code.contains(".searchScopes(")
            }
            if live { offenders.append(url.lastPathComponent) }
        }
        #expect(offenders.isEmpty, "search scopes are back in \(offenders)")
    }
}
#endif
