import SwiftUI

/// Shared annotation controls shown along the bottom of a reader (#2458).
///
/// One bar for every reader type — text/markdown today (slice 1), PDF/image
/// next. Highlight acts on the current text selection (or region); Note adds a
/// comment scoped to the page. The host owns persistence (via `AnnotationStore`)
/// and passes the closures + state below, so this view stays presentation-only.
struct AnnotationToolbar: View {
    /// True when the reader has a selection/region a highlight can attach to.
    let canAnnotateSelection: Bool
    /// Number of saved annotations on the current page, shown as a count.
    let savedCount: Int
    var onHighlight: () -> Void
    var onNote: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: onHighlight) {
                Label("Highlight", systemImage: "highlighter")
            }
            .disabled(!canAnnotateSelection)
            .help(canAnnotateSelection
                  ? "Highlight the selected text"
                  : "Select text to highlight")

            Button(action: onNote) {
                Label("Note", systemImage: "note.text.badge.plus")
            }
            .help(canAnnotateSelection
                  ? "Add a note on the selected text"
                  : "Add a note on this page")

            Spacer(minLength: 0)

            if savedCount > 0 {
                Label("\(savedCount)", systemImage: "bubble.left.and.text.bubble.right")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .help("\(savedCount) annotation\(savedCount == 1 ? "" : "s") on this page")
            }
        }
        .buttonStyle(.bordered)
        .controlSize(.small)
        .labelStyle(.titleAndIcon)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color(.windowBackgroundColor))
    }
}
