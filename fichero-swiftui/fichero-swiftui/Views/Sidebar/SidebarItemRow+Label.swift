import SwiftUI

extension SidebarItemRow {
    var itemLabel: some View {
        Label {
            if renameState.renamingItemId == item.id {
                renameField
            } else {
                Text(item.name)
                    .lineLimit(1)
                    // Selected row text tints to accent colour, matching
                    // Finder / Mail / Music sidebar convention. Unselected
                    // rows use `.primary` (system label colour — black in
                    // light mode, white in dark).
                    .foregroundColor(item.id == selectedItemId ? .accentColor : .primary)
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

    /// Finder / Mail sidebar convention: icons are monochrome (adapts to
    /// light/dark via `.primary`) when the row is unselected, and tint to
    /// the system accent colour when the row is the current selection.
    /// Previously per-category colours (folder=blue, search=orange, etc.)
    /// read as visually loud compared to Apple's apps — Daniel asked for
    /// the black-and-white look matching Finder / Mail / Music.
    var iconColor: Color {
        item.id == selectedItemId ? .accentColor : .primary
    }
}
