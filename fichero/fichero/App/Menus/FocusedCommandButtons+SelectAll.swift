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
    @FocusedValue(\.inspectorSelectAll) private var inspectorSelectAll
    @FocusedValue(\.focusedPaneKind) private var focusedPane

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
            focusedSurface: focusedSurface
        )
    }

    /// The surface that both HOLDS focus and has rows to select.
    ///
    /// Both halves are required. A publication alone is not focus — these are
    /// scene-scoped, so the library's is live whenever a library pane is on
    /// screen — and focus alone is not rows, since an empty list must decline
    /// so the key equivalent can fall through.
    private var focusedSurface: SelectAllSurface? {
        switch focusedPane {
        case .inspector:
            return inspectorSelectAll?.isEnabled == true ? .inspectorList : nil
        default:
            // The library is the default owner, as it was before the inspector
            // could answer: no pane hint at all still means the library, which
            // is what keeps a plain library window behaving exactly as it did.
            return librarySelectAll?.isEnabled == true ? .libraryRows : nil
        }
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
        case .inspectorList:
            inspectorSelectAll?.run()
        }
    }
}
