import SwiftUI

// MARK: - The one toolbar search item (#5024, #5225)
//
// The toolbar has ONE search control (the maintainer's ruling, 2026-09-20).
// On the Mac it is `ToolbarSearchField`, a native `NSSearchField` whose
// magnifier menu holds Ask / Keyword (checkmarked), where it looks, the
// search type and Save Search, as in Mail and Finder. The Ask/Keyword scope
// bar under the toolbar (`.searchScopes`) and the second "Search Options"
// loupe button beside the field are gone.
//
// iOS keeps the system `.searchable` field (Mail-style `.minimize`) with the
// options loupe beside it: UIKit has no magnifier menu to hang them on.
//
// Behaviour is otherwise the old field's:
// - Submit fires the SAME engine-search action (`runToolbarSearch`).
// - Emptying the field exits transient-search presentation via the
//   `toolbarSearchText` onChange in ContentView+RootLayout.swift.
// - Esc clears it (`SearchEscapeDismiss`).
// - The Hybrid/Semantic/Full-Text method is the menu's Search Type section,
//   as it is in the results bar's Options menu (#4112).
//
// This file holds the window's single `.searchable` registration (iOS only)
// — the #3163 duplicate-identifier crash class;
// ToolbarDuplicateRegistrationGuardTests allowlists exactly this file.

extension ContentView {
    /// Ask/Keyword (#4117) as a typed binding over the persisted raw mode —
    /// the one state every way of choosing the search kind writes.
    var searchFieldModeBinding: Binding<SearchFieldMode> {
        // A key-path binding, the same one every render (#5228).
        $searchFieldModeRaw.asSearchFieldMode
    }

    /// What the search menu holds, over the SAME bindings the request is
    /// built from (`runTransientSearch` reads `transientSearchScopeIsFolder`
    /// and `transientSearchType`; `runToolbarSearch` reads `searchFieldMode`),
    /// so the menu can never show a setting the next search will not honour.
    var toolbarSearchOptions: SearchFieldOptionsMenu {
        SearchFieldOptionsMenu(
            mode: searchFieldModeBinding,
            scopeIsFolder: $transientSearchScopeIsFolder,
            searchType: $transientSearchType,
            libraryName: searchChromeLibraryName,
            contextFolder: transientSearchContextFolder,
            reviewedEntityCount: transientSearchStore?.searchStats?.reviewedEntityCount,
            // Save needs a result set to save. With no search up there is
            // none, so the row is absent rather than dead — the same rule the
            // results-bar mount follows.
            canSave: {
                guard let store = transientSearchStore else { return false }
                return !store.results.isEmpty && store.searchFailure == nil
            }(),
            onSave: { Task { await saveTransientSearch() } }
        )
    }

    /// The search behaviour on the detail/inspector content: Esc, and on iOS
    /// the system `.searchable` registration (internal — `private` is
    /// file-scoped).
    func nativeToolbarSearch<Content: View>(_ content: Content) -> some View {
        let dismissable = content
            // Esc IS Done (Daniel, 2026-09-01): the gesture every other
            // transient state answers to, next to the field it clears.
            .modifier(SearchEscapeDismiss(
                isPresenting: activeSearchQuery != nil || !toolbarSearchText.isEmpty,
                dismiss: {
                    toolbarSearchText = ""
                    clearTransientSearch()
                }
            ))
        #if os(iOS)
        return dismissable
            .searchable(text: $toolbarSearchText, placement: .toolbar, prompt: "Search")
            .onSubmit(of: .search) {
                runToolbarSearch(toolbarSearchText)
            }
            // Mail-style: a magnifier until tapped, then the field expands.
            .searchToolbarBehavior(.minimize)
        #else
        return dismissable
        #endif
    }

    #if os(macOS)
    /// THE toolbar search item on the Mac: the field, with the options in
    /// its magnifier menu.
    var toolbarSearchItem: some View {
        ToolbarSearchField(
            text: $toolbarSearchText,
            options: toolbarSearchOptions,
            onSubmit: { runToolbarSearch($0) }
        )
        .frame(minWidth: 120, idealWidth: 200, maxWidth: 280)
    }
    #else
    /// iOS: the options loupe beside the system search item.
    var searchOptionsToolbarButton: some View {
        let options = toolbarSearchOptions
        return SearchFieldOptionsMenuButton(
            mode: options.$mode,
            scopeIsFolder: options.$scopeIsFolder,
            searchType: options.$searchType,
            libraryName: options.libraryName,
            contextFolder: options.contextFolder,
            reviewedEntityCount: options.reviewedEntityCount,
            canSave: options.canSave,
            onSave: options.onSave,
            accessibilityId: "toolbar.search.optionsMenu"
        )
    }
    #endif
}

/// Esc clears the search — `onExitCommand` is macOS/tvOS only, so the
/// gesture wears a modifier coat rather than scattering `#if os(macOS)`
/// through the view chain. On touch platforms the field's own cancel button
/// is the same gesture.
private struct SearchEscapeDismiss: ViewModifier {
    let isPresenting: Bool
    let dismiss: () -> Void

    func body(content: Content) -> some View {
        #if os(macOS)
        content.onExitCommand {
            guard isPresenting else { return }
            dismiss()
        }
        #else
        content
        #endif
    }
}
