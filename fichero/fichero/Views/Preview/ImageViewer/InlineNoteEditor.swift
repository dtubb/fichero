#if os(macOS)
import SwiftUI

/// Inline note entry AT ITS ANCHOR (Daniel, 2026-09-04: "adding a note should
/// create/edit it inline at the anchor, like a margin note on the page, not
/// open a popover"). Replaces the markup bar's `MarkupNotePopover`, which
/// asked for the words in a popover hanging off the toolbar — nowhere near
/// the spot the note is about.
///
/// Save semantics are the popover's, unchanged: Return (or losing the field
/// with text) commits through `AnnotationStore.updateText` — one audited
/// write per note; Esc or an empty commit on a note that never had words
/// DELETES the blank annotation rather than leaving one behind. Editing an
/// existing note (tap its mark) starts from its current text, and cancelling
/// leaves it as it was.
struct InlineNoteEditor: View {
    let annotationId: String
    /// The note's current text; empty for a note the canvas just created.
    let initialText: String
    /// Close the editor (both commit and cancel end here).
    let onDismiss: () -> Void

    @Environment(AnnotationStore.self) private var annotationStore: AnnotationStore?

    @State private var text = ""
    @State private var finished = false
    @FocusState private var fieldFocused: Bool

    var body: some View {
        TextField("Note…", text: $text)
            .textFieldStyle(.plain)
            .font(.caption)
            .frame(width: 180)
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 4))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color.accentColor.opacity(0.6), lineWidth: 1)
            )
            .focused($fieldFocused)
            .onSubmit(commit)
            .onExitCommand(perform: cancel)
            .onAppear {
                text = initialText
                fieldFocused = true
            }
            .onChange(of: fieldFocused) { _, focused in
                // Click-away behaves like Return: keep what was typed, or
                // clean up a note that never got words.
                if !focused, !finished { commit() }
            }
            .accessibilityIdentifier("markupNoteField")
    }

    private func commit() {
        guard !finished else { return }
        finished = true
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.isEmpty {
            deleteIfBlank()
        } else if value != initialText, let annotationStore {
            let id = annotationId
            Task { _ = await annotationStore.updateText(id: id, text: value) }
        }
        onDismiss()
    }

    private func cancel() {
        guard !finished else { return }
        finished = true
        deleteIfBlank()
        onDismiss()
    }

    /// A note that never had words is not a note — remove it. One that DID
    /// have words keeps them on cancel/empty.
    private func deleteIfBlank() {
        guard initialText.isEmpty, let annotationStore else { return }
        let id = annotationId
        Task { _ = await annotationStore.delete(id: id) }
    }
}
#endif
