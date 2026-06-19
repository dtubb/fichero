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
        .background(.bar)
    }
}
