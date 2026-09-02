import SwiftUI

extension ChatInspector {
    var headerView: some View {
        HStack {
            Text("Chat Scope")
                .font(.headline)

            Spacer()

            if !selectedDocuments.isEmpty {
                Button {
                    listSelection = selectedDocuments
                } label: {
                    Text("Select All")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                // No ⌘A binding (2026-09-02): a second view-level ⌘A anywhere
                // in the window fights the Edit menu's SelectAllButton — the
                // one-chord-one-owner rule (#4354's lesson, applied to ⌘A).
                // It also stole the shortcut LABEL from Edit ▸ Select All.
                // The button stays clickable; the chord routes by focus.

                Button {
                    removeSelectedFromScope()
                } label: {
                    Image(systemName: "trash")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .help("Remove the selected documents from the chat scope")
                .accessibilityLabel("Remove Selected from Scope")
                .disabled(listSelection.isEmpty)
                .keyboardShortcut(.delete, modifiers: [])

                Button {
                    selectedDocuments.removeAll()
                    listSelection.removeAll()
                } label: {
                    Text("Clear")
                        .font(.caption)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .frame(height: MiniToolbar<EmptyView, EmptyView>.standardHeight)
        // Tahoe glass treatment (#3061 / #2550), matching the document inspector
        // strips + sidebar bars — replaces the flat `.bar` material.
        .inspectorGlassStrip()
    }
}
