#if os(macOS)
import AppKit
import SwiftUI

// MARK: - The ONE toolbar search item (#5024, #5225)
//
// The maintainer's ruling (2026-09-20): the toolbar has ONE search control,
// and Ask / Keyword are choices in its menu with a checkmark, not a bar under
// the toolbar. #5225 names the native shape: the system search field with
// the options in its magnifier's own drop-down, as in Mail and Finder.
//
// SwiftUI's `.searchable` gives no way to put a menu on the field's
// magnifier, which is why the toolbar used to carry a second loupe button
// beside it. `NSSearchField.searchMenuTemplate` IS that magnifier menu, so on
// the Mac the field is an `NSSearchField` and the second button is gone.
//
// The menu's rows are not a second definition: they are rendered from the
// SAME `SearchFieldOptionsMenu` value the results bar's loupe renders as
// SwiftUI rows, writing the same bindings the request is built from.

/// The toolbar's search field: a native `NSSearchField` whose magnifier menu
/// holds the search options.
struct ToolbarSearchField: NSViewRepresentable {
    @Binding var text: String
    /// What the magnifier menu holds — the same value the results bar mounts.
    let options: SearchFieldOptionsMenu
    let onSubmit: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSSearchField {
        let field = NSSearchField()
        // #4971: just "Search", as Finder's own field says.
        field.placeholderString = "Search"
        // Enter submits, as the old `.onSubmit(of: .search)` did; typing
        // only edits the text (a search is an engine round trip).
        field.sendsWholeSearchString = true
        field.sendsSearchStringImmediately = false
        field.delegate = context.coordinator
        field.target = context.coordinator
        field.action = #selector(Coordinator.submit(_:))
        field.setAccessibilityLabel("Search")
        field.setAccessibilityIdentifier("toolbar.search")
        field.toolTip = "Search. Click the magnifier for Ask or Keyword, where it looks, and how it retrieves."
        return field
    }

    func updateNSView(_ field: NSSearchField, context: Context) {
        context.coordinator.parent = self
        if field.stringValue != text { field.stringValue = text }
        // Rebuilt every update so the checkmarks follow the state.
        field.searchMenuTemplate = options.nsMenu
    }

    @MainActor
    final class Coordinator: NSObject, NSSearchFieldDelegate {
        var parent: ToolbarSearchField

        init(_ parent: ToolbarSearchField) { self.parent = parent }

        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSSearchField else { return }
            parent.text = field.stringValue
        }

        /// Enter, or the field's clear button (which sends an empty string:
        /// emptying the field is what exits the results, via the
        /// `toolbarSearchText` onChange in ContentView+RootLayout.swift).
        @objc func submit(_ sender: NSSearchField) {
            parent.text = sender.stringValue
            guard !sender.stringValue.isEmpty else { return }
            parent.onSubmit(sender.stringValue)
        }
    }
}

// MARK: - The options as the magnifier's NSMenu

extension SearchFieldOptionsMenu {
    /// The same rows as `body`, as the `NSMenu` an `NSSearchField` hangs off
    /// its magnifier. A plain menu (not an `NSHostingMenu`) because the field
    /// copies its template; plain items with a shared target survive the copy.
    var nsMenu: NSMenu {
        let menu = NSMenu(title: "Search Options")
        menu.autoenablesItems = false

        menu.addItem(.sectionHeader(title: "Search Kind"))
        for (title, kind) in [("Ask", SearchFieldMode.ask), ("Keyword", .keyword)] {
            menu.addItem(Self.item(title, isOn: mode == kind) { $mode.wrappedValue = kind })
        }

        if let contextFolder {
            menu.addItem(.separator())
            menu.addItem(.sectionHeader(title: "Look In"))
            menu.addItem(Self.item(libraryName, isOn: !scopeIsFolder) { $scopeIsFolder.wrappedValue = false })
            menu.addItem(Self.item(contextFolder.trail, isOn: scopeIsFolder) { $scopeIsFolder.wrappedValue = true })
        }

        menu.addItem(.separator())
        menu.addItem(.sectionHeader(title: "Search Type"))
        let current = SearchRetrievalTier(requestValue: searchType)
        for tier in SearchRetrievalTier.ladder {
            let isAvailable = tier != .semanticGraph
                || SearchRetrievalTier.graphTierAvailable(reviewedEntities: reviewedEntityCount)
            let item = Self.item(tier.title, isOn: current == tier) {
                $searchType.wrappedValue = tier.requestValue
            }
            item.isEnabled = isAvailable
            // A dead row says why it is dead.
            item.toolTip = isAvailable ? tier.help : SearchRetrievalTier.noGraphHelp
            menu.addItem(item)
        }

        if canSave {
            menu.addItem(.separator())
            menu.addItem(Self.item("Save Search", isOn: false, onSave))
        }
        return menu
    }

    private static func item(
        _ title: String, isOn: Bool, _ action: @escaping () -> Void
    ) -> NSMenuItem {
        let item = NSMenuItem(
            title: title, action: #selector(SearchMenuTarget.fire(_:)), keyEquivalent: ""
        )
        item.target = SearchMenuTarget.shared
        item.representedObject = SearchMenuAction(action)
        item.state = isOn ? .on : .off
        return item
    }
}

/// The closure a menu row runs. Carried as `representedObject` so the copy
/// the search field makes of its template still runs it.
final class SearchMenuAction: NSObject {
    let run: () -> Void
    init(_ run: @escaping () -> Void) { self.run = run }
}

/// One long-lived target for every search-menu row (a menu item's target is
/// weak, so a per-menu target could be gone by the time the row is chosen).
@MainActor
final class SearchMenuTarget: NSObject {
    static let shared = SearchMenuTarget()

    @objc func fire(_ sender: NSMenuItem) {
        (sender.representedObject as? SearchMenuAction)?.run()
    }
}
#endif
