import SwiftUI

// MARK: - Next / Previous Doubtful Word (#5665, `source.disagree.next-doubtful`)

extension FocusedValues {
    /// ⌥⌘G — move the selection to the next word the readers disagree on, in the focused Reader's lens.
    @Entry var nextDoubtfulWord: FocusedLibraryAction?
    /// ⇧⌥⌘G — the previous one.
    @Entry var previousDoubtfulWord: FocusedLibraryAction?
}

/// Read › Next Doubtful Word and Previous Doubtful Word: Find Next's ⌘G with ⌥, as the next match of a kind.
/// Disabled without the lens, or with no word below unanimous.
struct DoubtfulWordMenuSection: View {
    @FocusedValue(\.nextDoubtfulWord) private var next
    @FocusedValue(\.previousDoubtfulWord) private var previous

    var body: some View {
        Button("Next Doubtful Word") { next?.run() }
            .keyboardShortcut("g", modifiers: [.command, .option])
            .disabled(next?.isEnabled != true)
        Button("Previous Doubtful Word") { previous?.run() }
            .keyboardShortcut("g", modifiers: [.command, .option, .shift])
            .disabled(previous?.isEnabled != true)
    }
}
