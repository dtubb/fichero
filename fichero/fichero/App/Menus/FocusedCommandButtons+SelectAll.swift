import SwiftUI

// MARK: - Select All (#4376)

/// ⌘A — Select All, routed by what actually has focus.
///
/// The library published a `librarySelectAll` focused action but nothing in the
/// menu ever consumed it, and the app declared no ⌘A of its own. So ⌘A went to
/// the system Select All, down the responder chain, to a SwiftUI
/// `ScrollView`+`LazyVStack` that implements no `selectAll(_:)` — and did
/// nothing at all. The action existed; the command never reached it.
///
/// This is the ⌘Z shape from #4354, reusing its `FocusedTextResponder` probe
/// rather than inventing a second answer to "what has focus". One place decides;
/// each command asks it.
///
/// The disabled case matters as much as the enabled ones: when neither a text
/// editor nor the library holds focus — the reader, which is a WebKit surface —
/// this item disables so the key equivalent falls through to the system Select
/// All and the web view selects its own text. Claiming ⌘A there and guessing
/// would be the #4354 bug in a new costume.
@MainActor
struct SelectAllButton: View {
    @FocusedValue(\.librarySelectAll) private var librarySelectAll

    var body: some View {
        Button("Select All") {
            performSelectAll()
        }
        .keyboardShortcut("a", modifiers: .command)
        .disabled(route == .none)
    }

    /// Recomputed on every body evaluation — which is when AppKit rebuilds and
    /// validates the menu, immediately before display and before a key
    /// equivalent fires. That is the moment the focus probe has to be read.
    private var route: SelectAllRoute {
        SelectAllRoutingPolicy.route(
            isTextEditing: FocusedTextResponder.isEditing,
            libraryHasSelectableRows: librarySelectAll?.isEnabled == true
        )
    }

    private func performSelectAll() {
        switch route {
        case .none:
            return
        case .focusedTextEditor:
            // Hand it back to the editor that has focus — the shape the
            // responder chain would have produced if a key equivalent had not
            // matched first (#4354/#4376).
            FocusedTextResponder.selectAll()
        case .libraryRows:
            librarySelectAll?.run()
        }
    }
}
