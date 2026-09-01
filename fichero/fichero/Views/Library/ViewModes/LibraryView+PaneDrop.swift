import OSLog
import SwiftUI
import UniformTypeIdentifiers

private let paneDropLogger = Logger(
    subsystem: "app.fichero.fichero", category: "LibraryPaneDrop"
)

// MARK: - Pane drop: the browsed folder / library ROOT (2026-09-01)
//
// Daniel's re-test: "drag and drop to library, not sure it works". It did not.
// The library pane had exactly one class of drop target — folder CELLS, added
// by #4124 — and nothing at all on the pane itself. So a Finder drag onto the
// gutter, onto the empty-folder placeholder, or onto a non-folder row landed on
// no target, no badge appeared, and the drop snapped back. The pane even mounts
// `LibraryDropAlertModifier` to report a failed pane drop; there was no pane
// drop to report on.
//
// The rule this restores is the one the sidebar's library header already
// keeps: **a drop on a surface targets what that surface is SHOWING.** The
// library pane is showing `folderId`, which is nil exactly when it is showing
// the library root — so `parentId: nil` here is the root, deliberately, not the
// #4449 "silently landed at root" bug (that was a cell claiming a folder it was
// not showing). At root the shared `libraryRootImportBatches` routing applies,
// so a user who has MADE an Inbox folder still gets loose files there and
// nothing creates one.

/// Accepts drops on the library pane itself and routes them to the folder the
/// pane is browsing. Mounted OUTSIDE the folder cells, so a cell — a deeper
/// drop target — always wins for a drop that lands on one.
struct LibraryPaneDrop: ViewModifier {
    let onDropProviders: @MainActor ([NSItemProvider]) -> Bool

    @State private var isTargeted = false

    func body(content: Content) -> some View {
        content
            // The same delegate the cells use, so the drag BADGE tells the
            // truth here too (move vs copy vs alias). The closure form always
            // claims copy — see LibraryItemDropDelegate for that whole account.
            .onDrop(
                of: SidebarItemRow.dropTypes,
                delegate: LibraryItemDropDelegate(
                    acceptedTypes: SidebarItemRow.dropTypes,
                    isTargeted: $isTargeted,
                    surface: "library-pane",
                    onDropProviders: onDropProviders
                )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Color.accentColor, lineWidth: 2)
                    .opacity(isTargeted ? 1 : 0)
                    .allowsHitTesting(false)
            )
    }
}

extension LibraryView {
    /// The pane's own drop modifier, wired to the folder this pane is showing.
    var libraryPaneDrop: LibraryPaneDrop {
        LibraryPaneDrop(onDropProviders: { providers in
            handleLibraryPaneDrop(providers)
        })
    }

    /// Handle a drop on the library pane's own surface — gutter, empty state,
    /// or any row that is not a folder cell. Returns whether it was accepted.
    ///
    /// Targets `folderId`: the folder being browsed, or the library ROOT when
    /// that is nil. Modifiers are sampled ONCE here, at the drop entry point,
    /// exactly as `handleFolderCellDrop` does (#4475 C).
    func handleLibraryPaneDrop(_ providers: [NSItemProvider]) -> Bool {
        guard !providers.isEmpty else {
            DragDropLog.refused("library-pane", reason: "empty provider set")
            return false
        }
        // The entity browser is not the document tree — there is nowhere for a
        // dropped file to land in it. Refuse LOUDLY rather than importing into
        // whatever folder was browsed before (prefer-raise-over-silent-fallback).
        guard !isShowingEntitiesCollection else {
            DragDropLog.refused(
                "library-pane",
                reason: "the entity browser is showing — a file has no parent here"
            )
            return false
        }
        let targetFolderId = folderId.map { $0.hasPrefix("doc:") ? String($0.dropFirst(4)) : $0 }
        let operation = sidebarDropOperation(modifiers: .current(), kind: .document)
        let eager = eagerSidebarDropLoads(providers)
        Task { @MainActor in
            let payload = await readSidebarDropPayload(
                providers, surface: "library-pane", preloaded: eager
            )
            switch payload {
            case .externalFiles:
                await importExternalPaneDrop(providers, into: targetFolderId)

            case .internalItems(let prefixedIDs):
                await applyPaneDrop(prefixedIDs, operation: operation, into: targetFolderId)

            case .internalEntities, .internalArtifacts:
                // Both curate INTO something — a workspace, a folder. The pane
                // is not an item, so there is nothing to curate into.
                DragDropLog.refused(
                    "library-pane",
                    reason: "entities and artifacts drop onto a folder or workspace, not the pane"
                )

            case .unreadableInternal:
                // Re-importing would create a hollow duplicate of something
                // already here — the #4401 data loss. Say so, no alert (#136).
                paneDropLogger.error(
                    "Library-pane drop came from inside the app but carried no readable item id (no-op)"
                )

            case .unsupported:
                DragDropLog.refused(
                    "library-pane",
                    reason: "payload classified unsupported — nothing readable, nothing importable"
                )
            }
        }
        return true
    }

    /// Finder-style import into the browsed folder, or the library root.
    ///
    /// At root this goes through the SHARED `libraryRootImportBatches` — the
    /// same routing the sidebar library header and the Data-menu import use —
    /// so the three surfaces cannot disagree about where a loose file lands.
    private func importExternalPaneDrop(_ providers: [NSItemProvider], into parentId: String?) async {
        guard let library = activeLibraryReference else {
            DragDropLog.refused("library-pane", reason: "no active library reference")
            return
        }
        var stableURLs: [URL] = []
        var temporaryURLs: [URL] = []
        for provider in providers {
            if let url = try? await ExternalFileDropLoader.loadAnyFileURL(from: provider) {
                if url.path.contains("/fichero-drop-") {
                    temporaryURLs.append(url)
                } else {
                    stableURLs.append(url)
                }
            }
        }
        guard !stableURLs.isEmpty || !temporaryURLs.isEmpty else {
            DragDropLog.refused(
                "library-pane",
                reason: "no provider yielded a file URL — nothing was imported"
            )
            windowState.dropErrorMessage = "Couldn't read the dropped item(s). Nothing was imported."
            return
        }
        let temporaryDirectories = externalDropTemporaryDirectories(for: temporaryURLs)
        defer {
            for directory in temporaryDirectories {
                try? FileManager.default.removeItem(at: directory)
            }
        }
        windowState.dropErrorMessage = nil
        do {
            var outcomes: [ImportOutcome] = []
            // A stable Finder file LINKS in place; a loader-staged temp copy is
            // COPIED, because the staging directory is deleted below.
            for (urls, mode) in [(stableURLs, IngestMode.link), (temporaryURLs, IngestMode.copy)]
            where !urls.isEmpty {
                for batch in paneImportBatches(urls: urls, parentId: parentId, library: library) {
                    outcomes.append(try await library.importService.importFiles(
                        batch.urls, mode: mode, parentId: batch.parentId
                    ))
                }
            }
            // ONE trailing refresh, and only when live delivery is down (#24):
            // a connected change stream has already spliced the rows in.
            await library.documentStore.refreshUnlessLiveDelivery(
                streamConnected: library.changeStream.isConnected
            )
            DragDropLog.performed(
                "library-pane",
                outcome: "imported \(stableURLs.count) linked + \(temporaryURLs.count) copied file(s) "
                    + "into \(parentId ?? "the library root")"
            )
            // #3276: not throwing only ever meant "not everything failed".
            if let message = ImportOutcome.merged(outcomes).partialFailureMessage {
                windowState.dropErrorMessage = message
            }
        } catch {
            DragDropLog.refused("library-pane", reason: "import threw: \(error.localizedDescription)")
            windowState.dropErrorMessage = "Import failed: \(error.localizedDescription)"
        }
    }

    /// One batch for a subfolder; the shared root routing at the root.
    private func paneImportBatches(
        urls: [URL],
        parentId: String?,
        library: LibraryManager.LibraryReference
    ) -> [LibraryRootImportBatch] {
        guard parentId == nil else {
            return [LibraryRootImportBatch(parentId: parentId, urls: urls)]
        }
        // A root "Inbox" the USER made routes loose files; nothing creates one
        // (ruling 2026-08-31). Same lookup the sidebar header does.
        let inboxId = library.documentStore.collections.first {
            $0.name == "Inbox" && $0.parentId == nil && $0.docType == .folder
        }?.id
        return libraryRootImportBatches(
            urls: urls, inboxId: inboxId, isDirectory: libraryDropURLIsDirectory
        )
    }

    /// Reparent in-app items into the browsed folder / root.
    private func applyPaneDrop(
        _ prefixedIDs: [String],
        operation: SidebarDropOperation,
        into parentId: String?
    ) async {
        guard let library = activeLibraryReference else { return }
        let ids = prefixedIDs
            .map { extractActualId(from: $0) }
            .filter { !$0.isEmpty && $0 != parentId }
        guard !ids.isEmpty else {
            DragDropLog.refused("library-pane", reason: "no document ids in the dropped payload")
            return
        }
        windowState.dropErrorMessage = nil
        var failures: [String] = []
        for id in ids {
            // `applyLibraryItemDropOperation` requires a folder id, so the ROOT
            // takes the move path directly — `moveDocument(_:toParent:)` already
            // accepts nil, which is how the sidebar header moves to root.
            if let parentId {
                if case .failed(let reason) = await applyLibraryItemDropOperation(
                    operation, documentId: id, intoFolderId: parentId, library: library
                ) {
                    failures.append(reason)
                }
                continue
            }
            do {
                _ = try await library.documentStore.moveDocument(id, toParent: nil)
            } catch {
                failures.append(error.localizedDescription)
            }
        }
        await documentStore.refresh()
        if let message = libraryCellDropOutcomeMessage(attempted: ids.count, failures: failures) {
            windowState.dropErrorMessage = message
        }
    }
}
