import SwiftUI

// MARK: - Native toolbar search (Daniel, 2026-08-29)
//
// The hand-rolled magnifier+TextField lozenge (#4604) is gone: "not proper
// macOS search… use the default one". The SYSTEM toolbar search item carries
// the field now — `.searchable` + `.searchToolbarBehavior(.minimize)` gives
// the Mail-style field that collapses to a magnifier and expands on click,
// and `DefaultToolbarItem(kind: .search)` in
// ContentView+InspectorContainer.swift sites it as its OWN trailing toolbar
// item, fused to nothing.
//
// Behaviour is otherwise the old field's, unchanged:
// - Submit fires the SAME engine-search action (`runToolbarSearch`).
// - Ask/Keyword scoping survives as native search scopes, shown only while
//   the field is presented (`.onSearchPresentation`) — never the #4407
//   window-spanning scope bar, because the registration lives on the
//   detail/inspector content, not the whole NavigationSplitView.
// - The Hybrid/Semantic/Full-Text method stays where #4112 put it: the
//   results bar's Options menu.
// - Emptying the field still exits transient-search presentation via the
//   existing `toolbarSearchText` onChange in ContentView+RootLayout.swift.
//
// This is the single `.searchable` registration in the window (#3163
// duplicate-identifier crash class) — ToolbarDuplicateRegistrationGuardTests
// allowlists exactly this file.

extension ContentView {
    /// Ask/Keyword (#4117) as a typed binding over the persisted raw mode.
    var searchFieldModeBinding: Binding<SearchFieldMode> {
        Binding(
            get: { SearchFieldMode(rawValue: searchFieldModeRaw) ?? .ask },
            set: { searchFieldModeRaw = $0.rawValue }
        )
    }

    /// The native search registration, applied to the detail/inspector
    /// content by ContentView+InspectorContainer.swift (internal — `private`
    /// is file-scoped).
    func nativeToolbarSearch<Content: View>(_ content: Content) -> some View {
        let searchable = content
            .searchable(
                text: $toolbarSearchText,
                placement: .toolbar,
                prompt: "Search your library"
            )
            .searchScopes(searchFieldModeBinding, activation: .onSearchPresentation) {
                Text("Ask").tag(SearchFieldMode.ask)
                Text("Keyword").tag(SearchFieldMode.keyword)
            }
            .onSubmit(of: .search) {
                runToolbarSearch(toolbarSearchText)
            }
            // Esc IS Done (Daniel, 2026-09-01). The results bar carried a
            // "Done" button whose only job was to clear the field and leave
            // the result presentation — the gesture every other transient
            // state in the app already answers to. The button is gone; the
            // gesture is here, next to the field it clears.
            .modifier(SearchEscapeDismiss(
                isPresenting: activeSearchQuery != nil || !toolbarSearchText.isEmpty,
                dismiss: {
                    toolbarSearchText = ""
                    clearTransientSearch()
                }
            ))
        #if os(iOS)
        // Mail-style: a magnifier until tapped, then the field expands.
        return searchable.searchToolbarBehavior(.minimize)
        #else
        // `.minimize` is explicitly unavailable on macOS (build-verified):
        // there the system NSSearchToolbarItem already carries the Mail
        // idiom — a field that collapses to the magnifier as space demands.
        return searchable
        #endif
    }
}

/// Esc clears the search — `onExitCommand` is macOS/tvOS only, so the
/// gesture wears a modifier coat rather than scattering `#if os(macOS)`
/// through the `.searchable` chain. On touch platforms the field's own
/// cancel button is the same gesture.
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
