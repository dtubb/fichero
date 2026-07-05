import OSLog
import SwiftUI

// MARK: - Library Header Helpers

extension SidebarView {
    @ViewBuilder
    func libraryDisclosureLabel(
        library: LibraryManager.LibraryReference,
        totalCount: Int
    ) -> some View {
        LibrarySectionHeader(
            library: library,
            itemCount: totalCount,
            isCurrentLibrary: library.id == windowState.libraryId,
            onFileDrop: { [library] urls in handleLibraryHeaderDrop(urls, library: library) },
            onSidebarItemDrop: { [library] droppedIds in
                handleLibraryHeaderItemDrop(droppedIds: droppedIds, library: library)
            },
            onTap: {
                selectedItemId = sidebarLibrarySelectionId(library.id)
                if windowState.libraryId != library.id { windowState.libraryId = library.id }
                sidebarMode = .library
                viewMode = .library(nil)
            }
        )
        .contextMenu {
            if library.id != LibraryManager.globalLibraryId {
                Button("Rename Library…") {
                    libraryToRenameId = library.id
                    pendingLibraryName = library.displayName
                    showingRenameLibraryPrompt = true
                }
                // Owners share a library from here — opens the same sheet as the
                // sidebar sharing badge (#3149). Gated on multi-user mode.
                if EngineConfig.multiuserEnabled {
                    Button("Share Library…") {
                        libraryToShare = library
                    }
                }
                Divider()
                // Close removes the library from the sidebar + the global
                // registry WITHOUT deleting the .fichero package on disk (#1661).
                Button("Close Library") {
                    closeLibraryFromSidebar(library)
                }
            }
        }
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
    /// Imports dropped files into the library Inbox (or root if no Inbox exists).
    @discardableResult
    func handleLibraryHeaderDrop(_ urls: [URL], library: LibraryManager.LibraryReference) -> Bool {
        let fileURLs = urls.filter { $0.isFileURL }
        guard !fileURLs.isEmpty else { return false }
        let collections = library.documentStore.collections
        var inboxId: String?
        for col in collections where col.name == "Inbox" && col.parentId == nil && col.docType == .folder {
            inboxId = col.id
            break
        }
        Task {
            do {
                _ = try await library.importService.importFiles(fileURLs, mode: .link, parentId: inboxId)
                await library.documentStore.refresh()
                try? await Task.sleep(for: .milliseconds(500))
                await library.documentStore.refresh()
            } catch {
                Logger(subsystem: "app.fichero.fichero", category: "LibraryHeaderDrop")
                    .error("Library root drop failed: \(error.localizedDescription)")
            }
        }
        return true
    }

    /// Reparents sidebar documents dropped onto the library header to
    /// the library root (parentId = nil). After this lands, the user
    /// can drag-reorder the items at root level via native between-row
    /// drops. Saved-search / workflow / chain IDs are filtered out —
    /// they don't belong at the doc-tree root.
    func handleLibraryHeaderItemDrop(droppedIds: [String], library: LibraryManager.LibraryReference) {
        let bareIds = droppedIds
            .filter { $0.hasPrefix("doc:") }
            .map { extractActualId(from: $0) }
        guard !bareIds.isEmpty else { return }
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
