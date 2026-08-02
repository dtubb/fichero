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
                .keyboardShortcut("a", modifiers: .command)

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
