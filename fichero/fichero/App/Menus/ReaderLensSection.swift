import SwiftUI

// MARK: - Reader lenses in the View menu (R3)

/// The same lens list the pane head shows, in the menu bar.
///
/// R3 requires both: the head is where you switch while looking at the pane,
/// the menu bar is where you find it when you do not know the head exists (and
/// where the keyboard reaches it). They read ONE published value, so they
/// cannot drift — the mistake this whole audit has been unwinding.
///
/// Disabled with no focused reader, like every other focused section: a control
/// that cannot apply should not tease.
struct ReaderLensSection: View {
    @FocusedValue(\.readerLens) private var readerLens

    var body: some View {
        Section("Reader") {
            ForEach(ReaderLens.allCases) { lens in
                Button {
                    readerLens?.set(lens)
                } label: {
                    Label(lens.title, systemImage: lens.icon)
                    if readerLens?.value == lens {
                        Image(systemName: "checkmark")
                    }
                }
                .disabled(readerLens == nil)
            }
        }
    }
}
