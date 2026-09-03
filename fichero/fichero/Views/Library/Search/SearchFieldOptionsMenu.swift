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
    /// Retrieval tier (#4112/S8, re-cut as a ladder 2026-09-02): the raw
    /// request value, so the menu and the request cannot disagree.
    @Binding var searchType: String

    /// What the whole-library choice is CALLED — the library the results
    /// actually came from, so this menu and the results header cannot name
    /// different libraries.
    let libraryName: String
    /// The breadcrumb context, when there is one to offer. Absent at the
    /// library root: there is no second scope to choose, so the scope
    /// section does not appear rather than showing one dead option.
    let contextFolder: TransientSearchFolder?
    /// Reviewed knowledge-graph entities in this library, from the last
    /// response's `kg_entities.reviewed`. `nil` = the engine did not say, and
    /// an unknown count keeps the graph rung ENABLED (honest, not cautious).
    let reviewedEntityCount: Int?
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

        // The retrieval LADDER (Daniel, 2026-09-02) — three rungs in cost
        // order, each adding a leg to the one below, and the user can see
        // which one is running. Not a `Picker`: the top rung has to be able
        // to go dead with a sentence explaining why, and a Picker row cannot
        // carry its own `.disabled` + `.help`. Buttons with an explicit
        // checkmark are the same radio gesture with that control kept.
        Section("Search Type") {
            ForEach(SearchRetrievalTier.ladder) { tier in
                retrievalTierRow(tier)
            }
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

    /// One rung. Checked when it is the tier the next request will use — read
    /// through `SearchRetrievalTier(requestValue:)` so a saved search carrying
    /// the legacy pure-vector `"semantic"` still shows a checked row.
    @ViewBuilder
    private func retrievalTierRow(_ tier: SearchRetrievalTier) -> some View {
        let isSelected = SearchRetrievalTier(requestValue: searchType) == tier
        let isAvailable = tier != .semanticGraph
            || SearchRetrievalTier.graphTierAvailable(reviewedEntities: reviewedEntityCount)
        Button {
            searchType = tier.requestValue
        } label: {
            if isSelected {
                Label(tier.title, systemImage: "checkmark")
            } else {
                Text(tier.title)
            }
        }
        .disabled(!isAvailable)
        // A dead row that does not say why it is dead is the defect this
        // whole change exists to remove.
        .help(isAvailable ? tier.help : SearchRetrievalTier.noGraphHelp)
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
    let reviewedEntityCount: Int?
    let canSave: Bool
    let onSave: () -> Void
    /// Distinguishes the mounts. The button is deliberately mountable more
    /// than once (the results bar AND the main toolbar, 2026-09-03), and two
    /// controls sharing one accessibility identifier make a UI test's
    /// "the options menu" ambiguous — so each mount names itself.
    var accessibilityId: String = "library.search.optionsMenu"

    var body: some View {
        Menu {
            SearchFieldOptionsMenu(
                mode: $mode,
                scopeIsFolder: $scopeIsFolder,
                searchType: $searchType,
                libraryName: libraryName,
                contextFolder: contextFolder,
                reviewedEntityCount: reviewedEntityCount,
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
        // Icon-only, so VoiceOver has nothing to read off the glyph.
        .accessibilityLabel("Search Options")
        .accessibilityIdentifier(accessibilityId)
    }
}
