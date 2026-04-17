import SwiftUI

extension SidebarItemRow {
    var itemLabel: some View {
        Label {
            if renameState.renamingItemId == item.id {
                renameField
            } else {
                Text(item.name)
                    .lineLimit(1)
                    // Double-click on the label name starts inline rename.
                    // Sidebar plan Step 8. Attaches only to the Text so
                    // the disclosure chevron (outside the Label) and the
                    // icon tap-through to the outer selection tap are
                    // unaffected. Single-click continues to propagate to
                    // the row's outer `.onTapGesture` (selection change)
                    // because SwiftUI prefers the more specific gesture
                    // only when the count matches.
                    .onTapGesture(count: 2) {
                        renameState.startRename(itemId: item.id, currentName: item.name)
                    }
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
