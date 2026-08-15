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

    /// Finder's grammar, settled in Daniel's preview review (2026-08-08,
    /// #4563): a selected sidebar row is the GREY platter with accent
    /// name+icon in EVERY focus state — sidebarDropHighlight paints that
    /// platter itself, so the native emphasized (accent) selection never
    /// draws and no prominence switch is needed. White content appears only
    /// over the one solid-accent fill left: the drop target (Mail).
    var rowContentColor: Color {
        if isDropTargeted { return .white }
        return rowLabelStyle.color
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
        // inside the core rather than inherited: the native source-list
        // treatment paints white-on-accent and bolds the label, which is
        // the #4371 complaint, not the goal.
        //
        // The icon+name pair lives in `SidebarRowLabelCore`, an EQUATABLE
        // view: one selection change used to re-evaluate every one of a
        // 204-row folder's label subtrees (selection commits 0.4–2.6s in
        // Daniel's 2026-08-14 night log; 91.6ms/flip in
        // SidebarSelectionPerfTests before this change). With the core
        // comparable, SwiftUI skips the ~200 rows whose inputs are
        // unchanged and re-renders only the rows entering/leaving the
        // selection.
        HStack(spacing: 6) {
            if renameState.renamingItemId == item.id {
                labelCore(iconOnly: true)
                renameField
            } else {
                labelCore(iconOnly: false)
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
    }

    private func labelCore(iconOnly: Bool) -> SidebarRowLabelCore {
        var badge: (symbol: String, color: Color)?
        if case .document(let doc) = item.itemType {
            badge = ingestBadge(for: doc)
        }
        let activity = containerActivity
        return SidebarRowLabelCore(
            iconOnly: iconOnly,
            name: item.name,
            icon: item.icon,
            contentColor: rowContentColor,
            weight: rowLabelStyle.weight,
            isAlias: rowIsAlias,
            iconTint: iconTint,
            badgeSymbol: badge?.symbol,
            badgeColor: badge?.color,
            childrenLoading: childrenLoading,
            workflowRunning: workflowIsRunning,
            documentProcessing: documentIsProcessing,
            containerProgress: activity.progress,
            containerSummary: activity.summary,
            isDefaultWorkflowFolder: item.isDefaultWorkflowFolder
        )
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
    /// `NSWindow.userTabbingPreference` is a PREFERENCES read (IPC) and this
    /// getter runs per row per render — it showed up six times in Daniel's
    /// 2026-08-09 stall log. Read once per launch; ponytail: a user changing
    /// the System Settings tabbing preference mid-run sees the new behavior
    /// after relaunch, which is also how most AppKit apps behave.
    private static let cachedUserTabbingPreference = NSWindow.userTabbingPreference

    @ViewBuilder
    var trailingOpenAffordance: some View {
        if item.libraryId != nil {
            let prefersTab = sidebarOpenPrefersTab(Self.cachedUserTabbingPreference)
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

    /// The row is expanded and its known children haven't arrived yet —
    /// the OPENING row's icon carries the spinner (Daniel, 2026-08-09),
    /// never a synthetic child row.
    private var childrenLoading: Bool {
        expandedItems.contains(item.id) && sidebarNeedsDeferredDisclosureContent(item)
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
        // Drop target: white over the solid accent platter — same rule as
        // the name (rowContentColor, #4563).
        if isDropTargeted { return .white }
        // Selection: accent icon on the grey row fill (Finder).
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

    /// Plain-click fallback for CHILD rows (Daniel, 2026-08-10: "still not
    /// working for clicking on name of item child of folder") — the
    /// UnifiedRows fallback only wraps TOP-LEVEL rows, so a nested row's
    /// name-press was claimed by the drag machinery and never committed.
    /// Plain clicks only; modifier clicks stay with the List.
    ///
    /// Lives HERE, not in `+Drop.swift`, although its only caller is
    /// `childrenList`: it is a CLICK gesture, and the drop-path files are
    /// scanned by SidebarDropHighlightScopeTests for selection writes (#4229).
    func childPlainClickFallback(_ child: SidebarItem) -> some Gesture {
        TapGesture().onEnded {
            #if os(macOS)
            guard !NSEvent.modifierFlags.contains(.shift),
                  !NSEvent.modifierFlags.contains(.command) else { return }
            #endif
            selectedItemId = child.id
        }
    }
}
