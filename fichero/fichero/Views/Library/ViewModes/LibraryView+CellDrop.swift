import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let cellDropLogger = Logger(
    subsystem: "app.fichero.fichero", category: "LibraryCellDrop"
)

// MARK: - Per-cell folder drop (#4124, #4474, #4475)
//
// Grid/list/table cells were drag SOURCES only — the sole drop target was the
// whole content pane, so hovering anywhere lit every cell and the drop
// imported into the folder being VIEWED, not the folder under the cursor.
// This modifier gives folder cells a real drop target for in-app item drags,
// with a per-cell highlight, routed through the same operation grammar and the
// same executor the sidebar uses.
//
// It was a Transferable `dropDestination` TYPED on the library pane's own
// payload. Two payload types encode one concept ("a library item, being
// dragged"): the sidebar vends `SidebarDragID` and the library pane vends
// `LibraryItemDrag`. A typed destination on one of them silently matches
// nothing when handed the other, so dragging a sidebar row onto a library
// folder cell did nothing at all — no move, no feedback, no error (#4474).
//
// (The old typed spelling is deliberately not repeated anywhere in this file:
// `LibraryDropPairingTests` asserts its ABSENCE, and a mention in a comment
// would make that guardrail unfalsifiable.)
//
// Widening it means the untyped provider API, which is what the sidebar's own
// row drop already uses, so both surfaces now read a drop through the SAME
// `readSidebarDropPayload` and get back the same `doc:`-prefixed ids whichever
// pane the drag started in. Nothing here knows about `LibraryItemDrag` any more.

/// Accepts in-app library-item drags on folder cells; non-folders and
/// read-only system folders pass through untouched. Per-cell `isTargeted`
/// state = only the hovered folder highlights.
///
/// `acceptsDrop`, not `isFolder`: a Default Workflows folder IS a folder and
/// must still refuse (#4514). Callers pass `doc.acceptsItemDrops`, the same
/// answer the sidebar's lock badge is drawn from.
struct LibraryFolderCellDrop: ViewModifier {
    let acceptsDrop: Bool
    let onDropProviders: @MainActor ([NSItemProvider]) -> Bool

    @State private var isTargeted = false

    func body(content: Content) -> some View {
        if acceptsDrop {
            content
                // A delegate, deliberately: it is the only drop form that can
                // say what the drop will DO, and the closure form always said
                // copy over a cell that moves (#4401 reopened — dragging TIFs
                // from Inbox onto a folder showed a plus badge). See
                // LibraryItemDropDelegate for the whole account.
                .onDrop(
                    of: SidebarItemRow.dropTypes,
                    delegate: LibraryItemDropDelegate(
                        acceptedTypes: SidebarItemRow.dropTypes,
                        isTargeted: $isTargeted,
                        onDropProviders: onDropProviders
                    )
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.accentColor, lineWidth: 2)
                        .opacity(isTargeted ? 1 : 0)
                        .allowsHitTesting(false)
                )
        } else {
            content
        }
    }
}

extension LibraryView {
    /// Handle a drop onto a library folder cell. Returns whether the drop was
    /// accepted.
    ///
    /// The Finder modifier grammar applies here exactly as it does in the
    /// sidebar: plain = move, ⌥ = copy, ⌘⌥ = alias. It used to always move, so
    /// the same gesture on the same objects obeyed two different rules
    /// depending on which pane you performed it in (#4475 B).
    ///
    /// Modifiers are sampled ONCE, here at the drop entry point, and the
    /// sampled value is passed to the executor — never re-read further down
    /// (#4475 C).
    func handleFolderCellDrop(_ providers: [NSItemProvider], into folder: Document) -> Bool {
        // Re-asserted here, not only on the modifier: a refusal that lives
        // solely in the view's `if` is one call site away from being lost.
        guard folder.acceptsItemDrops, !providers.isEmpty else { return false }

        let capabilities = sidebarDropCapabilities(of: providers)
        guard sidebarDropMightCarryInternalID(capabilities) else {
            // No string flavour at all: a pure external file drag. Folder cells
            // do not import — refusing lets the drop fall through to the content
            // pane, which does. Unchanged behaviour, now by decision rather than
            // as a side effect of the destination's static type.
            return false
        }

        let operation = sidebarDropOperation(modifiers: .current(), kind: .document)

        Task { @MainActor in
            let payload = await readSidebarDropPayload(providers)
            switch payload {
            case .internalItems(let prefixedIDs):
                await applyCellDrop(prefixedIDs, operation: operation, into: folder)

            case .unreadableInternal:
                // Started inside the app and we could not read what it was.
                // Re-importing would create a hollow duplicate of something
                // already here — the #4401 data loss. Say so instead.
                cellDropLogger.error(
                    "Folder-cell drop came from inside the app but carried no readable item id"
                )
                windowState.dropErrorMessage =
                    "Couldn't read what was dragged. Nothing was moved or copied."

            case .externalFiles, .unsupported:
                break
            }
        }
        return true
    }

    /// Apply the resolved operation to each dragged document, then refresh
    /// once. Failures are reported to the user, not merely logged — a drop that
    /// appears to do nothing is the whole complaint behind #4474.
    private func applyCellDrop(
        _ prefixedIDs: [String],
        operation: SidebarDropOperation,
        into folder: Document
    ) async {
        guard let library = activeLibraryReference else { return }
        let ids = prefixedIDs
            .map { extractActualId(from: $0) }
            .filter { !$0.isEmpty && $0 != folder.id }
        guard !ids.isEmpty else { return }

        windowState.dropErrorMessage = nil
        var failures: [String] = []
        for id in ids {
            switch await applyLibraryItemDropOperation(
                operation, documentId: id, intoFolderId: folder.id, library: library
            ) {
            case .applied:
                break
            case .failed(let reason):
                failures.append(reason)
                let verb = String(describing: operation)
                cellDropLogger.error(
                    """
                    \(verb, privacy: .public) of \(id, privacy: .public) \
                    into \(folder.id, privacy: .public) failed: \(reason, privacy: .public)
                    """
                )
            }
        }
        await documentStore.refresh()

        if let message = libraryCellDropOutcomeMessage(
            attempted: ids.count, failures: failures
        ) {
            windowState.dropErrorMessage = message
        }
    }
}

/// Presents the library pane's drop failure. Mirrors the sidebar's
/// `SidebarDropAlertsModifier` — same shape, so the two panes report a refused
/// drop the same way.
struct LibraryDropAlertModifier: ViewModifier {
    @Bindable var windowState: WindowState

    func body(content: Content) -> some View {
        content.alert(
            "Drop Failed",
            isPresented: Binding(
                get: { windowState.dropErrorMessage != nil },
                set: { isPresented in
                    if !isPresented {
                        windowState.dropErrorMessage = nil
                    }
                }
            )
        ) {
            Button("OK", role: .cancel) {
                windowState.dropErrorMessage = nil
            }
        } message: {
            Text(windowState.dropErrorMessage ?? "The drop could not be completed.")
        }
    }
}

/// Pure outcome summary for a folder-cell drop. Nil = everything applied, so
/// nothing needs saying.
func libraryCellDropOutcomeMessage(attempted: Int, failures: [String]) -> String? {
    guard !failures.isEmpty else { return nil }
    let noun = attempted == 1 ? "item" : "items"
    let prefix = failures.count == attempted
        ? "Couldn’t drop \(attempted == 1 ? "that item" : "those \(attempted) \(noun)")."
        : "\(failures.count) of \(attempted) \(noun) couldn’t be dropped."
    guard let reason = failures.first else { return prefix }
    return "\(prefix) \(reason)"
}
