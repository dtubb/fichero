import SwiftUI

extension SidebarItemRow {
    var itemLabel: some View {
        // Standard macOS sidebar label — no foreground-color overrides.
        // `.listStyle(.sidebar)` automatically inverts text and icon
        // colors on the selected row (primary → white on accent-blue),
        // same as Finder / Mail / Music. Previous code set selected text
        // to `.accentColor`, which read blue-on-blue against the native
        // selection highlight and made the row unreadable.
        Label {
            if renameState.renamingItemId == item.id {
                renameField
            } else {
                Text(item.name)
                    .lineLimit(1)
                // No inline double-tap-to-rename gesture: `.simultaneousGesture
                // (TapGesture(count: 2))` causes SwiftUI to hold every single
                // click for ~0.5s waiting for a potential second click, which
                // blocks List's native selection binding. Symptom: first click
                // does nothing; second click does nothing; double-click either
                // renames or nothing; later clicks finally select. Daniel #612.
                // Rename is still reachable via right-click → Rename (see
                // SidebarItemContextMenu).
            }
        } icon: {
            if workflowIsRunning {
                ZStack {
                    Circle()
                        .fill(Color.purple.opacity(isPulsing ? 0.4 : 0.15))
                        .frame(width: 20, height: 20)
                        .animation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true), value: isPulsing)
                    ProgressView()
                        .controlSize(.small)
                        .scaleEffect(0.8)
                }
            } else {
                Image(systemName: item.icon)
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

}
