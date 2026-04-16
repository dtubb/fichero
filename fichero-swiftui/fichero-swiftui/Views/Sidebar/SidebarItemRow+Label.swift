import SwiftUI

extension SidebarItemRow {
    var itemLabel: some View {
        Label {
            if renameState.renamingItemId == item.id {
                renameField
            } else {
                Text(item.name)
                    .lineLimit(1)
            }
        } icon: {
            ZStack {
                if workflowIsRunning {
                    Circle()
                        .fill(Color.purple.opacity(isPulsing ? 0.4 : 0.15))
                        .frame(width: 20, height: 20)
                        .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: isPulsing)

                    ProgressView()
                        .controlSize(.small)
                        .scaleEffect(0.8)
                } else {
                    Image(systemName: item.icon)
                        .foregroundColor(iconColor)
                }
            }
        }
        .onChange(of: workflowIsRunning) { _, isRunning in
            isPulsing = isRunning
        }
        .onAppear {
            if workflowIsRunning {
                isPulsing = true
            }
        }
    }

    /// Tint color used by `.listRowBackground` when this row is a drag-drop target.
    /// Folders get a stronger wash (drop imports *into* them); leaf rows get a
    /// lighter tint to signal "drop here imports beside this item".
    var dropTint: Color {
        guard isDropTargeted else { return .clear }
        return Color.accentColor.opacity(isFolder ? 0.25 : 0.15)
    }

    var renameField: some View {
        TextField("Name", text: $renameState.editingName)
            .textFieldStyle(.plain)
            .focused($isRenameFocused)
            .lineLimit(1)
            .truncationMode(.tail)
            .onSubmit {
                commitRename()
            }
            .onExitCommand {
                renameState.cancelRename()
                isRenameFocused = false
            }
            .onChange(of: isRenameFocused) { _, newValue in
                if !newValue && renameState.renamingItemId == item.id && !isCommittingRename {
                    renameState.cancelRename()
                }
            }
            .task {
                isRenameFocused = true
            }
    }

    var iconColor: Color {
        switch item.category {
        case .folder:
            return .accentColor
        case .search:
            return .orange
        case .chat:
            return .green
        case .workflow:
            return .purple
        case .automation:
            return .teal
        case .batch:
            return .indigo
        case .activity:
            return .cyan
        case .library:
            return .blue
        }
    }
}
