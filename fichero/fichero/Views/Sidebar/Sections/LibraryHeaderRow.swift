import FicheroAPIClient
import OSLog
import SwiftUI

private let libraryHeaderLogger = Logger(
    subsystem: "app.fichero.fichero", category: "LibraryHeader"
)

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
    // Create/import INTO this library (Daniel, 2026-08-25: "right click on
    // library, ought to be able to add folder, or import to there"). Injected
    // like onDropError — the row has no sidebarState of its own; both flows
    // resolve their target via the selection the closure sets first.
    let onNewFolder: () -> Void
    let onImport: () -> Void

    // ponytail: this row loads its own authz snapshot, the same GET the
    // LibrarySharingBadge in the header already makes — two cheap authz reads
    // per visible header. Collapse into one shared load if it shows in profiling.
    @State private var snapshot: Components.Schemas.LibraryAuthzSnapshot?
    /// Presents the prototype (document type) editor for THIS library.
    @State private var showTypeEditor = false
    /// Confirms Delete Library… before anything moves to the Trash.
    @State private var showDeleteLibraryConfirmation = false

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
        // The prototype (document type) editor from the library itself
        // (Daniel 2026-08-13: "yes to contextual menu" — prototypes are just
        // nodes of this library). Same sheet the inspector's picker opens.
        Button("Edit Document Types…") {
            showTypeEditor = true
        }
        .disabled(!canWrite)
        // Owners share from here — same sheet as the sidebar sharing badge
        // (#3149). Gated on multi-user mode + write access.
        if EngineConfig.multiuserEnabled {
            Button("Share Library…", action: onShare)
                .disabled(!canWrite)
        }
        // Where the package actually lives (Daniel, 2026-08-25: "we should
        // be able to show in finder in contextual menu") — the standard Mac
        // answer to "what IS this thing on disk".
        #if os(macOS)
        Button("Show in Finder") {
            NSWorkspace.shared.activateFileViewerSelecting([library.url])
        }
        #endif
        Divider()
        // Finder semantics again: create into / import into the thing you
        // right-clicked. Both closures select this library first, so the
        // shared dialogs (which resolve via `selectedItemLibrary`) target it.
        Button("New Folder", action: onNewFolder)
            .disabled(!canWrite)
        Button("Import Files…", action: onImport)
            .disabled(!canWrite)
        Divider()
        // Close removes the library from the sidebar + the global registry
        // WITHOUT deleting the .fichero package on disk (#1661). Stays enabled
        // for viewers — it's a local sidebar op, not a library mutation.
        Button("Close Library", action: onClose)
        // Delete = close AND move the package to the TRASH (recoverable,
        // never an unlink) after an explicit confirmation. Write access
        // required — a viewer must not be able to trash a shared library.
        Button("Delete Library…", role: .destructive) {
            showDeleteLibraryConfirmation = true
        }
        .disabled(!canWrite)
    }

    /// Close the library, then move its package to the Trash. Trash, not
    /// unlink: a mistaken delete of an archive is recoverable from the bin,
    /// and Finder shows exactly what happened.
    private func deleteLibraryMovingToTrash() {
        let packageURL = library.url
        onClose()
        do {
            try FileManager.default.trashItem(at: packageURL, resultingItemURL: nil)
        } catch {
            libraryHeaderLogger.error(
                "Delete Library: trash failed for \(packageURL.path): \(error.localizedDescription)"
            )
        }
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
        .sheet(isPresented: $showTypeEditor) {
            PrototypeEditorSheet(entityService: library.entityService)
        }
        .alert("Delete Library?", isPresented: $showDeleteLibraryConfirmation) {
            Button("Cancel", role: .cancel) {}
            Button("Move to Trash", role: .destructive) {
                deleteLibraryMovingToTrash()
            }
        } message: {
            Text(
                "\u{201C}\(library.displayName)\u{201D} will close and its "
                + "package will move to the Trash. You can restore it from "
                + "the Trash and open it again."
            )
        }
        .task(id: library.id) {
            guard EngineConfig.multiuserEnabled, !isGlobal else {
                snapshot = nil
                return
            }
            snapshot = try? await library.actionsService.loadLibraryAuthzSnapshot()
        }
    }
}
