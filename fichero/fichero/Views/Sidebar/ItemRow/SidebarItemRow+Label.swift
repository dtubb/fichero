import SwiftUI

extension SidebarItemRow {
    var itemLabel: some View {
        // Manual HStack instead of `Label { ... } icon: { ... }`:
        // SwiftUI's `Label` registers its inner `Text` as an
        // `NSDraggingSource` at AppKit level on macOS, which wins
        // over a `.draggable` on a parent ancestor and produces a
        // text-only drag (icon+name preview, bypassing our
        // SidebarDragID Transferable). Composing the row with a
        // plain `HStack { Image; Text }` keeps the visual identical
        // but lets the row container's `.draggable` be the sole
        // drag source (#711). Sidebar selection styling (white-on-
        // accent for selected row) still works because we're inside
        // `.listStyle(.sidebar)` and use `.foregroundStyle(.primary)`.
        HStack(spacing: 6) {
            iconView
                .allowsHitTesting(false)
            if renameState.renamingItemId == item.id {
                renameField
            } else {
                Text(item.name)
                    .lineLimit(1)
                    .allowsHitTesting(false)
                // `.allowsHitTesting(false)` on the Text (and Image) is
                // critical: SwiftUI `Text` on macOS registers itself as
                // an AppKit `NSDraggingSource` for selectable text, which
                // intercepts press-and-drag from the name area BEFORE the
                // row container's `.draggable` sees it — producing a
                // text-flavored drag that bypasses our `.dropDestination`
                // (#713). Disabling hit-testing on the Text makes presses
                // fall through to the parent's `.contentShape(Rectangle())`
                // so the row's `.draggable` claims them uniformly. The
                // outer `.simultaneousGesture(TapGesture)` on the row body
                // still fires for selection because contentShape provides
                // the clickable surface.
                //
                // No inline double-tap-to-rename gesture: `.simultaneousGesture
                // (TapGesture(count: 2))` causes SwiftUI to hold every single
                // click for ~0.5s waiting for a potential second click, which
                // blocks List's native selection binding. Symptom: first click
                // does nothing; second click does nothing; double-click either
                // renames or nothing; later clicks finally select. #612.
                // Rename is still reachable via right-click → Rename (see
                // SidebarItemContextMenu).
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

    @ViewBuilder
    private var iconView: some View {
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
            .frame(width: 20, height: 20)
        } else if documentIsProcessing {
            // Per-doc / folder spinner — REPLACES the icon while in flight.
            // Earlier version was a tiny corner overlay that the user
            // couldn't see at glance ("spinner is not on the right of the
            // folder, or replacing the icon"). Matches the workflow-row
            // spinner visual so users get one consistent "this is in
            // flight" signal across all sidebar rows. (#785)
            ProgressView()
                .controlSize(.small)
                .scaleEffect(0.8)
                .frame(width: 16, alignment: .center)
        } else if case .document(let doc) = item.itemType,
                  let badge = ingestBadge(for: doc) {
            // #603: visible per-mode badges driven by metadata.ingest_mode
            // exposed in 8eb002cf. LINK shows a Finder-style alias arrow,
            // MOVE shows an arrow-into-box, COPY shows no badge (default).
            ZStack(alignment: .bottomTrailing) {
                // Defensive: empty icon strings spam the SF Symbols
                // log ("No symbol named '' found in system symbol set")
                // every render. Fall back to a generic doc icon when an
                // upstream factory forgets to set one. (#1015)
                Image(systemName: item.icon.isEmpty ? "doc" : item.icon)
                    .foregroundStyle(iconTint)
                Image(systemName: badge.symbol.isEmpty ? "questionmark.circle" : badge.symbol)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.white, badge.color)
                    .background(
                        Circle()
                            .fill(.background)
                            .frame(width: 13, height: 13)
                    )
                    .offset(x: 4, y: 4)
            }
            .frame(width: 16, alignment: .center)
        } else {
            // Defensive empty-icon guard — see comment above. (#1015)
            Image(systemName: item.icon.isEmpty ? "doc" : item.icon)
                .foregroundStyle(iconTint)
                .frame(width: 16, alignment: .center)
        }
    }

    /// Color only the glyph. Text remains `.primary`, and selected rows revert
    /// to the system foreground so SwiftUI keeps its native contrast treatment.
    private var iconTint: Color {
        guard !selectedDestinations.contains(item.destination) else { return .primary }
        switch item.sidebarTint {
        case .accent: return .accentColor
        case .teal: return .teal
        case .indigo: return .indigo
        case .purple: return .purple
        case .orange: return .orange
        case .blue: return .blue
        case .green: return .green
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
            .accessibilityLabel("Rename \(item.name)")
            .accessibilityIdentifier("renameField.\(item.id)")
            .lineLimit(1)
            .truncationMode(.tail)
            .onSubmit {
                commitRename()
            }
            #if os(macOS)
            .onExitCommand {
                renameState.cancelRename()
                isRenameFocused = false
            }
            #endif
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
