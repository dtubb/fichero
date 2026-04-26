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
            } else if case .document(let doc) = item.itemType,
                      let badge = ingestBadge(for: doc) {
                // #603: visible per-mode badges driven by metadata.ingest_mode
                // exposed in 8eb002cf. LINK shows a Finder-style alias arrow,
                // MOVE shows an arrow-into-box, COPY shows no badge (default).
                ZStack(alignment: .bottomTrailing) {
                    Image(systemName: item.icon)
                    Image(systemName: badge.symbol)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.white, badge.color)
                        .background(
                            Circle()
                                .fill(.background)
                                .frame(width: 13, height: 13)
                        )
                        .offset(x: 4, y: 4)
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

    /// Resolve the ingest-mode badge for a document. Returns nil for COPY
    /// (default mode shows no badge — matches Finder where copies don't get
    /// alias decoration). #603 part 2.
    private func ingestBadge(for doc: Document) -> (symbol: String, color: Color)? {
        switch doc.ingestMode {
        case .link:
            return ("arrow.up.forward.square.fill", Color.accentColor)
        case .move:
            return ("arrow.right.square.fill", Color.orange)
        case .copy:
            return nil
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
