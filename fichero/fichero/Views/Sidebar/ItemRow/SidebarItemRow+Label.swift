import SwiftUI

extension SidebarItemRow {
    /// Mail's grammar (Daniel, 2026-08-08, #4563): EVERY member of a
    /// multi-selection reads the same — grey row, accent name+icon. The
    /// morning's version keyed the label on the routed PRIMARY alone, which
    /// rendered one row of a five-row selection differently ("one selected
    /// that is lighter green gray"). Membership drives the STYLE; the primary
    /// gets a distinct glyph later (#4563), never a text shade.
    var isRowInSelection: Bool {
        selectedDestinations.contains(item.destination)
    }

    /// The label treatment, from the app's one selection vocabulary (#4371).
    /// Applied explicitly so the row can never inherit the native emphasized
    /// selection's white-and-bold inversion.
    var rowLabelStyle: LibrarySelectionStyle.SidebarRowLabel {
        LibrarySelectionStyle.sidebarLabel(isSelected: isRowInSelection)
    }

    var itemLabel: some View {
        // Manual HStack instead of `Label { ... } icon: { ... }`:
        // SwiftUI's `Label` registers its inner `Text` as an
        // `NSDraggingSource` at AppKit level on macOS, which wins
        // over a `.draggable` on a parent ancestor and produces a
        // text-only drag (icon+name preview, bypassing our
        // SidebarDragID Transferable). Composing the row with a
        // plain `HStack { Image; Text }` keeps the visual identical
        // but lets the row container's `.draggable` be the sole
        // drag source (#711). Selection styling is applied EXPLICITLY
        // below rather than inherited: the native source-list treatment
        // paints white-on-accent and bolds the label, which is the
        // #4371 complaint, not the goal.
        HStack(spacing: 6) {
            iconView
                .allowsHitTesting(false)
            if renameState.renamingItemId == item.id {
                renameField
            } else {
                Text(item.name)
                    .lineLimit(1)
                    // Stated explicitly, never inherited (#4371's mechanism
                    // stands): the native emphasized source-list selection
                    // forces white-and-bold. The COLOURS follow Finder
                    // (Daniel, 2026-08-08): accent name when selected, white
                    // over the solid accent fill while a drop targets this
                    // row, primary otherwise.
                    .foregroundStyle(isDropTargeted ? .white : rowLabelStyle.color)
                    .fontWeight(rowLabelStyle.weight)
                    // Finder's alias grammar, both halves: the tiny arrow
                    // badge on the icon (ingestBadge) AND an italic name —
                    // the badge alone is invisible at sidebar sizes (Daniel,
                    // 2026-08-04).
                    .italic(rowIsAlias)
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
            #if os(macOS)
            Spacer(minLength: 4)
            lockedRowBadge
            trailingOpenAffordance
            #else
            if rowIsLocked {
                Spacer(minLength: 4)
                lockedRowBadge
            }
            #endif
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

    /// System-seeded rows are read-only — the trailing lock says so at a
    /// glance (Xcode's locked-file convention). Covers the "Default
    /// Workflows" container, its preset subfolders, and the mirrored
    /// workflow rows inside them.
    var rowIsLocked: Bool {
        if case .document(let doc) = item.itemType {
            // `doc.isLockedSystemNode` is the shared predicate the library
            // views read too (#4514) — one question, one answer, both panes.
            // `item.isDefaultWorkflowFolder` stays OR-ed in for the legacy
            // folder RE-HOMED under the container, which keeps its old id and
            // may predate the engine's `read_only` backfill (#4200).
            return item.isDefaultWorkflowFolder || doc.isLockedSystemNode
        }
        return false
    }

    @ViewBuilder
    var lockedRowBadge: some View {
        if rowIsLocked {
            Image(systemName: "lock.fill")
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .allowsHitTesting(false)
                .accessibilityLabel("Read-only")
        }
    }

    #if os(macOS)
    /// Trailing hover affordance (#2496): a small "open" button that appears
    /// while the pointer is over the row and performs the same action as
    /// double-click — open this row in a new tab or window, honoring the
    /// system "Prefer tabs" setting. The button is ALWAYS in the layout
    /// (opacity-toggled, hit-testing gated) so hovering never relayouts or
    /// re-truncates the row name (Every-Frame-Perfect). Hidden from
    /// accessibility: VoiceOver and keyboard users reach the identical
    /// action via the row context menu's Open in New Tab / New Window.
    @ViewBuilder
    var trailingOpenAffordance: some View {
        if item.libraryId != nil {
            let prefersTab = sidebarOpenPrefersTab(NSWindow.userTabbingPreference)
            let visible = sidebarRowShowsOpenAffordance(
                isHovered: isRowHovered,
                isRenaming: renameState.renamingItemId == item.id,
                hasLibrary: item.libraryId != nil
            )
            Button {
                openInNewWindow(asTab: prefersTab)
            } label: {
                Image(systemName: "arrow.up.forward.square")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.borderless)
            .opacity(visible ? 1 : 0)
            .allowsHitTesting(visible)
            .help(prefersTab ? "Open in New Tab" : "Open in New Window")
            .accessibilityHidden(true)
        }
    }
    #endif

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
                    // The List's tint is the selection FILL colour (#4371);
                    // restate the accent here so an in-flight row still spins
                    // in the user's accent rather than inheriting grey.
                    .tint(.accentColor)
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
                // See above (#4371): the List tint is a fill colour, not an
                // accent, so progress restates its own.
                .tint(.accentColor)
        } else if let progress = containerActivity.progress {
            // The container's CONTENTS are being worked on (#4417). A
            // determinate ring, deliberately unlike the leaf spinner: a
            // container is not being processed, and this is the one row where
            // a summary of the children makes sense.
            ProgressView(value: progress)
                .progressViewStyle(.circular)
                .controlSize(.small)
                .scaleEffect(0.8)
                .frame(width: 16, alignment: .center)
                .tint(.secondary)
                .help(containerActivity.summary ?? "")
                .accessibilityLabel(containerActivity.summary ?? "")
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
                // #4098: `.caption2` instead of `.system(size: 11)` — a
                // hardcoded point size does not track the user's text-size or
                // accessibility settings, which is a standing hard rule here.
                // caption2 is ~11pt at the default setting, so the intended
                // look is unchanged and now scales.
                //
                // The backing circle SIZES ITSELF from the symbol (padding +
                // `.background`) rather than a fixed 13pt frame, so it grows
                // with the glyph instead of letting it clip out at larger text
                // sizes. Deliberately not `@ScaledMetric`: a self-sizing
                // background needs no separate scale factor to keep in step,
                // and nothing else in this app uses that property yet.
                Image(systemName: badge.symbol.isEmpty ? "questionmark.circle" : badge.symbol)
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(.white, badge.color)
                    .padding(1)
                    .background(Circle().fill(.background))
                    .offset(x: 4, y: 4)
            }
            .frame(width: 16, alignment: .center)
        } else if item.isDefaultWorkflowFolder {
            // Locked "Default Workflows" container/subfolders: a colored,
            // gear-badged folder icon so they read as system/default and
            // not user-editable (#11). Purple matches the workflow-running
            // accent used above, keeping the sidebar's workflow visual
            // language consistent. `.hierarchical` keeps the badge legible.
            Image(systemName: item.icon.isEmpty ? "folder.badge.gearshape" : item.icon)
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(.purple)
                .frame(width: 16, alignment: .center)
        } else {
            // Defensive empty-icon guard — see comment above. (#1015)
            Image(systemName: item.icon.isEmpty ? "doc" : item.icon)
                .foregroundStyle(iconTint)
                .frame(width: 16, alignment: .center)
        }
    }

    /// True when this row renders a Finder-style alias (reference node,
    /// #2591). Drives the italic name beside the arrow badge.
    private var rowIsAlias: Bool {
        if case .document(let doc) = item.itemType { return doc.isAlias }
        return false
    }

    /// Color only the glyph. Text remains `.primary`, and selected rows revert
    /// to the system foreground so SwiftUI keeps its native contrast treatment.
    private var iconTint: Color {
        // Drop target: white over the solid accent fill (Finder's drag
        // grammar — Daniel, 2026-08-08).
        if isDropTargeted { return .white }
        // Selected: accent icon on the grey row fill, like Finder's sidebar.
        // (Used to return .primary here under #4371; superseded.)
        guard !selectedDestinations.contains(item.destination) else { return .accentColor }
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
        // Finder-style alias badge takes precedence — the reference arrow is
        // the node's identity, not an ingest annotation (#2591).
        if doc.isAlias {
            return ("arrowshape.turn.up.right.fill", Color.gray)
        }
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
