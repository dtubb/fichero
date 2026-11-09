import SwiftUI

/// What Edit › Mark ▸ acts on (#6454): the Reader's selected stretch, when it holds one. Published by the Reader; the menu is one more
/// way in to the same audited calls, disabled with its reason while nothing is selected.
struct ReaderMarkTarget {
    let hasSelection: Bool
    let mark: (ReaderMark.Kind) -> Void
}

extension FocusedValues {
    @Entry var readerMark: ReaderMarkTarget?
}

/// Edit › Mark ▸: Unclear (⇧⌘U), Lost, Supplied on the selected stretch.
struct ReaderMarkMenu: View {
    @FocusedValue(\.readerMark) private var target

    static let reason = "Select text in the Reader to mark it"

    var body: some View {
        Menu("Mark") {
            Button("Mark Unclear") { target?.mark(.unclear) }
                .keyboardShortcut("u", modifiers: [.command, .shift])
                .disabled(target?.hasSelection != true)
            Button("Mark Lost") { target?.mark(.lost) }
                .disabled(target?.hasSelection != true)
            Button("Mark Supplied") { target?.mark(.supplied) }
                .disabled(target?.hasSelection != true)
            if target?.hasSelection != true { Text(Self.reason) }
        }
    }
}
