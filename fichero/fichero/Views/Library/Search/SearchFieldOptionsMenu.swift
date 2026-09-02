import SwiftUI

// MARK: - The search field's own options menu (Daniel, 2026-09-02)
//
// "The row above the results should fold into a submenu attached to the
// search field." What used to be a strip of chrome over every result set —
// an Ask/Keyword segmented control, scope pills, a retrieval-type button and
// Save Search — is one loupe menu here. The row above the results is now
// only what the results themselves say: a count, and the pager that count
// justifies.
//
// The menu CONTENT is a separate view from the button that hosts it on
// purpose. `SearchFieldOptionsMenu` is a bare `@ViewBuilder` body of menu
// rows, so the same rows can be mounted:
//   * inside the results bar's loupe button (`SearchFieldOptionsMenuButton`,
//     below — where they live today), and
//   * inside the toolbar search item itself, whenever the file that owns the
//     `.searchable` registration wants them, with no duplicated control
//     definitions and no second source of truth for the scope.
//
// SwiftUI offers no API for putting a menu inside the system search field's
// magnifier, so a nested `Menu` next to the field is the closest the
// framework allows; the split above is what keeps that placement decision a
// one-line change rather than a rewrite.

/// The rows of the search options menu. Mount inside a `Menu { }`.
struct SearchFieldOptionsMenu: View {
    /// Ask vs Keyword (#4117) — how the query is interpreted.
    @Binding var mode: SearchFieldMode
    /// Scope (#4107/S3): false = the whole library, true = the breadcrumb
    /// context. Two choices, never three (Daniel: "dead simple").
    @Binding var scopeIsFolder: Bool
    /// Retrieval type (#4112/S8): hybrid / semantic / fulltext.
    @Binding var searchType: String

    /// What the whole-library choice is CALLED — the library the results
    /// actually came from, so this menu and the results header cannot name
    /// different libraries.
    let libraryName: String
    /// The breadcrumb context, when there is one to offer. Absent at the
    /// library root: there is no second scope to choose, so the scope
    /// section does not appear rather than showing one dead option.
    let contextFolder: TransientSearchFolder?
    /// Save is offered only for a result set there is something to save.
    let canSave: Bool
    let onSave: () -> Void

    var body: some View {
        Picker("Interpretation", selection: $mode) {
            Text("Ask").tag(SearchFieldMode.ask)
            Text("Keyword").tag(SearchFieldMode.keyword)
        }

        if let contextFolder {
            Divider()
            // The scope IS the breadcrumb (Daniel, 2026-09-02). A menu row
            // can afford the whole trail, which is what the pills could not:
            // "1885" alone is ambiguous in a library with three of them.
            Picker("Look in", selection: $scopeIsFolder) {
                Text(libraryName).tag(false)
                Text(contextFolder.trail).tag(true)
            }
        }

        Divider()

        Picker("Search Type", selection: $searchType) {
            Text("Hybrid").tag("hybrid")
            Text("Semantic").tag("semantic")
            Text("Full Text").tag("fulltext")
        }

        if canSave {
            Divider()
            // The ONE explicit persistence path (#4086) — searching itself
            // still persists nothing.
            Button {
                onSave()
            } label: {
                Label("Save Search", systemImage: "square.and.arrow.down")
            }
        }
    }
}

/// The loupe button that hosts `SearchFieldOptionsMenu`.
///
/// A magnifier with a disclosure chevron, matching the gesture Daniel asked
/// for ("the loupe icon in the search box") wherever the button is mounted.
struct SearchFieldOptionsMenuButton: View {
    @Binding var mode: SearchFieldMode
    @Binding var scopeIsFolder: Bool
    @Binding var searchType: String
    let libraryName: String
    let contextFolder: TransientSearchFolder?
    let canSave: Bool
    let onSave: () -> Void

    var body: some View {
        Menu {
            SearchFieldOptionsMenu(
                mode: $mode,
                scopeIsFolder: $scopeIsFolder,
                searchType: $searchType,
                libraryName: libraryName,
                contextFolder: contextFolder,
                canSave: canSave,
                onSave: onSave
            )
        } label: {
            Label("Search Options", systemImage: "magnifyingglass")
                .labelStyle(.iconOnly)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .help("How this search runs: Ask or Keyword, where it looks, and how it retrieves")
        .accessibilityIdentifier("library.search.optionsMenu")
    }
}
