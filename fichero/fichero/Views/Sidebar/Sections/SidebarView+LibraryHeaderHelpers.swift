import FicheroAPIClient
import OSLog
import SwiftUI

// MARK: - Library Header Helpers

extension SidebarView {
    @ViewBuilder
    func libraryDisclosureLabel(
        library: LibraryManager.LibraryReference,
        totalCount: Int
    ) -> some View {
        LibraryHeaderRow(
            library: library,
            totalCount: totalCount,
            isCurrentLibrary: library.id == windowState.libraryId,
            onFileDrop: { [library] urls, mode in
                handleLibraryHeaderDrop(urls, mode: mode, library: library)
            },
            onSidebarItemDrop: { [library] droppedIds, modifiers in
                handleLibraryHeaderItemDrop(
                    droppedIds: droppedIds, modifiers: modifiers, library: library
                )
            },
            // The header accepted the drop synchronously; without somewhere to
            // report a refusal the item just appears to vanish (#4401).
            onDropError: { sidebarState.dropErrorMessage = $0 },
            onTap: {
                // The header is OUTSIDE List selection (#160) — its tap is
                // the one writer of both selection halves for this row.
                selectionState.selectedDestinations = [.library(library.id)]
                selectedItemId = sidebarLibrarySelectionId(library.id)
                if windowState.libraryId != library.id { windowState.libraryId = library.id }
                sidebarMode = .library
                viewMode = .library(nil)
            },
            onRename: {
                libraryToRenameId = library.id
                pendingLibraryName = library.displayName
                showingRenameLibraryPrompt = true
            },
            onShare: { libraryToShare = library },
            onClose: { closeLibraryFromSidebar(library) }
        )
    }

    /// Close a library from the sidebar context menu (#1661): unregister it
    /// from the global registry and drop it from the open set. The .fichero
    /// package on disk is NOT deleted. If the closed library was the current
    /// one, fall back to the Global library so the window isn't left pointing
    /// at a closed library.
    private func closeLibraryFromSidebar(_ library: LibraryManager.LibraryReference) {
        let wasCurrent = windowState.libraryId == library.id
        libraryManager.closeAndUnregisterLibrary(library.id)
        if wasCurrent {
            windowState.libraryId = LibraryManager.globalLibraryId
            sidebarMode = .library
            viewMode = .library(nil)
        }
    }

    /// Drop handler for the library disclosure-group header row.
    /// Folders import at the library ROOT (they are sidebar-visible there and
    /// that is where the user dropped them, #4274); plain files route to Inbox
    /// (bare files at root are invisible in the sidebar). An import failure
    /// surfaces on the sidebar's drop-error banner, never only in the log.
    @discardableResult
    func handleLibraryHeaderDrop(
        _ urls: [URL],
        mode: IngestMode = .link,
        library: LibraryManager.LibraryReference
    ) -> Bool {
        let fileURLs = urls.filter { $0.isFileURL }
        guard !fileURLs.isEmpty else {
            // #4533: was silent. Name what arrived — a drop of non-file URLs
            // (a web link, a promise that never resolved) looks identical to
            // a drop that never reached the header at all.
            DragDropLog.refused(
                "sidebar-library-header",
                reason: "no file URLs among \(urls.count) dropped URL(s): "
                    + "[\(urls.map(\.scheme).map { $0 ?? "no-scheme" }.joined(separator: ", "))]"
            )
            return false
        }
        // Loader-staged temp copies (`fichero-drop-*`) are removed once this
        // import is done with them — the same contract the row path keeps.
        let temporaryDirectories = externalDropTemporaryDirectories(for: fileURLs)
        let collections = library.documentStore.collections
        var inboxId: String?
        for col in collections where col.name == "Inbox" && col.parentId == nil && col.docType == .folder {
            inboxId = col.id
            break
        }
        let batches = libraryRootImportBatches(
            urls: fileURLs, inboxId: inboxId, isDirectory: libraryDropURLIsDirectory
        )
        Task {
            defer {
                for tempDir in temporaryDirectories {
                    try? FileManager.default.removeItem(at: tempDir)
                }
            }
            sidebarState.dropErrorMessage = nil
            do {
                // #3276: not throwing only ever meant "not everything failed".
                var outcomes: [ImportOutcome] = []
                for batch in batches {
                    outcomes.append(try await library.importService.importFiles(
                        batch.urls, mode: mode, parentId: batch.parentId
                    ))
                }
                // ONE trailing refresh (#4067/#4522), and ONLY when live
                // delivery is down (#24): a connected change stream has
                // already spliced the imported rows in place.
                await library.documentStore.refreshUnlessLiveDelivery(
                    streamConnected: library.changeStream.isConnected
                )
                if let message = ImportOutcome.merged(outcomes).partialFailureMessage {
                    sidebarState.dropErrorMessage = message
                }
            } catch {
                // #4533: was a THIRD private category ("LibraryHeaderDrop"),
                // so no single filter could show a whole drop and the drop#N
                // stamp had nothing to correlate. Through the shared seam now.
                DragDropLog.refused(
                    "sidebar-library-header",
                    reason: "import failed: \(error.localizedDescription)"
                )
                // A drop that fails must SAY so (#4274 'silently no-ops'):
                // reuse the sidebar's drop-error banner the move paths use.
                sidebarState.dropErrorMessage =
                    "Import failed: \(error.localizedDescription)"
            }
        }
        return true
    }

    /// Applies an in-app drop on the library header at the library root
    /// (parentId = nil), honoring the Finder modifier grammar every other
    /// in-app drop target speaks (#4475): plain reparents, ⌥ copies, ⌘⌥
    /// makes aliases — the header was the one surface that silently ignored
    /// the modifiers and always moved (audit 2026-08-04). After this lands,
    /// the user can drag-reorder the items at root level via native
    /// between-row drops. Saved-search / workflow / chain IDs are filtered
    /// out — they don't belong at the doc-tree root.
    func handleLibraryHeaderItemDrop(
        droppedIds: [String],
        modifiers: SidebarDropModifiers,
        library: LibraryManager.LibraryReference
    ) {
        let bareIds = droppedIds
            .filter { $0.hasPrefix("doc:") }
            .map { extractActualId(from: $0) }
        guard !bareIds.isEmpty else {
            // #4533: was silent. Saved searches, workflows and chains are
            // filtered out here BY DESIGN — but "correctly ignored" and
            // "swallowed" look the same to the user, so say which it was.
            DragDropLog.refused(
                "sidebar-library-header",
                reason: "no document ids among \(droppedIds.count) dropped id(s) — "
                    + "non-document items don't belong at the doc-tree root"
            )
            return
        }
        let operation = sidebarDropOperation(modifiers: modifiers, kind: .document)
        if operation != .move {
            // Same executor the insertion line uses; empty children/offset 0
            // skips the positioning diff — the header has no insertion point.
            let request = SidebarInsertionDropRequest(
                operation: operation, bareIds: bareIds, parentId: nil,
                offset: 0, children: []
            )
            Task {
                await sidebarApplyInsertionDropOperation(
                    request, library: library, sidebarState: sidebarState
                )
            }
            return
        }
        Task {
            await MainActor.run {
                sidebarState.dropErrorMessage = nil
            }
            let moveResult = await moveSidebarDocumentsTransactionally(
                bareIds,
                toParent: nil,
                move: { itemId, parentId in
                    _ = try await library.documentStore.moveDocument(itemId, toParent: parentId)
                },
                refresh: {
                    await library.documentStore.refresh()
                }
            )

            guard moveResult.isSuccessful else {
                await MainActor.run {
                    sidebarState.dropErrorMessage = moveResult.errorMessage
                }
                return
            }
        }
    }
}

// MARK: - Library Header Row (access-gated)

/// The library-name header row (#3152): owns this library's authz snapshot so
/// write affordances — rename, share, and Finder / sidebar-item drops — disable
/// for viewers and no-access users, with an explanatory tooltip. Single-user
/// mode and the still-loading state fail OPEN (the engine enforces access
/// server-side anyway, so we never flash-disable). Self-contained per library —
/// its own `.task(id:)` means a role change refreshes ONE row, never the whole
/// sidebar list.
///
/// The `.contextMenu` used to live inline in `libraryDisclosureLabel`, but that
/// is a stateless `@ViewBuilder` func; a small view is the only place to hang
/// the per-library `@State` the gate needs.
struct LibraryHeaderRow: View {
    let library: LibraryManager.LibraryReference
    let totalCount: Int
    let isCurrentLibrary: Bool
    let onFileDrop: ([URL], IngestMode) -> Bool
    let onSidebarItemDrop: ([String], SidebarDropModifiers) -> Void
    /// Where a refused or unreadable drop is reported. This row has no
    /// `sidebarState` of its own, so the sink is injected by the SidebarView
    /// that does.
    let onDropError: (String) -> Void
    let onTap: () -> Void
    let onRename: () -> Void
    let onShare: () -> Void
    let onClose: () -> Void

    // ponytail: this row loads its own authz snapshot, the same GET the
    // LibrarySharingBadge in the header already makes — two cheap authz reads
    // per visible header. Collapse into one shared load if it shows in profiling.
    @State private var snapshot: Components.Schemas.LibraryAuthzSnapshot?

    private static let readOnlyHelp =
        "You have view-only access to this library. Ask an owner for edit access to rename or add files."

    private var isGlobal: Bool { library.id == LibraryManager.globalLibraryId }

    /// True when the signed-in user may mutate this library. Owner / editor (or
    /// role-manager) can write; a viewer or unresolved role cannot. Fails open
    /// when multi-user is off, the library is Global, or the snapshot hasn't
    /// loaded — the engine is the real gate, this only reflects it in the UI.
    private var canWrite: Bool {
        guard EngineConfig.multiuserEnabled, !isGlobal,
              let snapshot, snapshot.multiuserEnabled else { return true }
        if snapshot.canManageRoles { return true }
        switch snapshot.currentUserRole {
        case "owner", "editor": return true
        default: return false
        }
    }

    var body: some View {
        // #116: the `if !isGlobal` used to sit INSIDE `.contextMenu`, so
        // right-clicking the Global library header opened a real, EMPTY menu —
        // a panel with nothing in it, which reads as broken rather than as
        // "nothing applies here". The condition is now outside, so no menu is
        // attached at all: the right-click does nothing visible, which is
        // #4421's rule (absent beats present-and-useless). The Global library
        // genuinely cannot be renamed, shared or closed.
        if isGlobal {
            header
        } else {
            header.contextMenu { libraryContextMenu }
        }
    }

    @ViewBuilder
    private var libraryContextMenu: some View {
        Button("Rename Library…", action: onRename)
            .disabled(!canWrite)
        // Owners share from here — same sheet as the sidebar sharing badge
        // (#3149). Gated on multi-user mode + write access.
        if EngineConfig.multiuserEnabled {
            Button("Share Library…", action: onShare)
                .disabled(!canWrite)
        }
        Divider()
        // Close removes the library from the sidebar + the global registry
        // WITHOUT deleting the .fichero package on disk (#1661). Stays enabled
        // for viewers — it's a local sidebar op, not a library mutation.
        Button("Close Library", action: onClose)
    }

    private var header: some View {
        LibrarySectionHeader(
            library: library,
            itemCount: totalCount,
            isCurrentLibrary: isCurrentLibrary,
            // Nil callbacks make LibrarySectionHeader reject the drop (its
            // handlers `guard let` the closure) — viewers can't import/reparent.
            onFileDrop: canWrite ? onFileDrop : nil,
            onSidebarItemDrop: canWrite ? onSidebarItemDrop : nil,
            // Same banner every other drop failure uses, so a refused header
            // drop is reported in one place rather than nowhere (#4401).
            onDropError: onDropError,
            onTap: onTap
        )
        .help(canWrite ? "" : Self.readOnlyHelp)
        .task(id: library.id) {
            guard EngineConfig.multiuserEnabled, !isGlobal else {
                snapshot = nil
                return
            }
            snapshot = try? await library.actionsService.loadLibraryAuthzSnapshot()
        }
    }
}
