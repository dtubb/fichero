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
    var isSelected: Bool = false
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
        "You have view-only access to this project. Ask an owner for edit access to rename or add files."

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
        // Only projects a person set up have this row; the always-there project has no row and no
        // name (ruled 2026-10-10). `ProjectRowMenuOffers` still refuses it everything but folders
        // and imports, so the menu is never empty (#116) whatever row it lands on.
        header.contextMenu { libraryContextMenu }
            .accessibilityIdentifier(SidebarAccessibilityID.project(library.id))
            // The key window's project, for File's and Project's project verbs (#5652): the same target this menu
            // renders. Only the window's own project's row publishes it.
            .focusedSceneValue(\.projectVerbs, isCurrentLibrary ? verbs : nil)
    }

    /// New Folder at this project's top, for someone who may write to it.
    private var newFolder: (@MainActor () -> Void)? {
        guard canWrite else { return nil }
        let onNewFolder = onNewFolder
        return { onNewFolder() }
    }

    /// This project, as its verbs act on it: this row's own prompt, sheet, editor and confirmation.
    private var verbs: ProjectVerbsTarget {
        var target = ProjectVerbsTarget(projectId: library.id, offers: offers, canWrite: canWrite)
        if offers.rename { target.rename = { onRename() } }
        target.editDocumentTypes = { showTypeEditor = true }
        if offers.share { target.share = { onShare() } }
        #if os(macOS)
        let url = library.url
        target.showInFinder = { NSWorkspace.shared.activateFileViewerSelecting([url]) }
        #endif
        if offers.delete { target.delete = { showDeleteLibraryConfirmation = true } }
        return target
    }

    private var offers: ProjectRowMenuOffers {
        ProjectRowMenuOffers.forProject(isAlwaysThere: isGlobal, multiuser: EngineConfig.multiuserEnabled)
    }

    /// The project's verbs: the shared items File and Project render on the key window's project (#5652).
    @ViewBuilder
    private var libraryContextMenu: some View {
        if offers.rename {
            RenameProjectMenuItem(target: verbs)
        }
        // The prototype (document type) editor from the library itself
        // (Daniel 2026-08-13: "yes to contextual menu" — prototypes are just
        // nodes of this library). Same sheet the inspector's picker opens.
        EditDocumentTypesMenuItem(target: verbs)
        // Owners share from here — same sheet as the sidebar sharing badge
        // (#3149). Gated on multi-user mode + write access.
        if offers.share {
            ShareProjectMenuItem(target: verbs)
        }
        // Where the package actually lives (Daniel, 2026-08-25: "we should
        // be able to show in finder in contextual menu") — the standard Mac
        // answer to "what IS this thing on disk".
        #if os(macOS)
        ShowProjectInFinderMenuItem(target: verbs)
        #endif
        Divider()
        // Finder semantics again: create into / import into the thing you
        // right-clicked. Both closures select this library first, so the
        // shared dialogs (which resolve via `selectedItemLibrary`) target it.
        NewFolderMenuItem(create: newFolder)
        Button("Import Files…", action: onImport)
            .disabled(!canWrite)
        if offers.close || offers.delete {
            Divider()
        }
        // Close removes the library from the sidebar + the global registry
        // WITHOUT deleting the .fichero package on disk (#1661). Stays enabled
        // for viewers — it's a local sidebar op, not a library mutation.
        if offers.close {
            CloseProjectMenuItem(close: { onClose() })
        }
        // Delete = close AND move the package to the TRASH (recoverable,
        // never an unlink) after an explicit confirmation. Write access
        // required — a viewer must not be able to trash a shared library.
        if offers.delete {
            DeleteProjectMenuItem(target: verbs)
        }
    }

    /// Close the library, then move its package to the Trash. Trash, not
    /// unlink: a mistaken delete of an archive is recoverable from the bin,
    /// and Finder shows exactly what happened.
    private func deleteLibraryMovingToTrash() {
        let packageURL = library.url
        do {
            try LibraryManager.closeAndTrash(packageURL, close: onClose)
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
            isSelected: isSelected,
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
        .alert("Delete Project?", isPresented: $showDeleteLibraryConfirmation) {
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

#if DEBUG
#Preview("Library Header Row") {
    // `LibraryPreviewFixtures.library` (Views/Library/ViewModes/LibraryModeFixtures.swift):
    // the app's one inert `LibraryReference` — a nil-path client, no network, no engine.
    // This row is the reason that fixture is shared rather than one-off per view: it needs
    // the same nine-plus services LibraryView's canvas already built a fixture for.
    LibraryHeaderRow(
        library: LibraryPreviewFixtures.library,
        totalCount: 42,
        isCurrentLibrary: true,
        onFileDrop: { _, _ in true },
        onSidebarItemDrop: { _, _ in },
        onDropError: { _ in },
        onTap: {},
        onRename: {},
        onShare: {},
        onClose: {},
        onNewFolder: {},
        onImport: {}
    )
    .frame(width: 260)
    .padding()
}
#endif

/// What a project row's context menu offers (ruled 2026-10-10,
/// `library.always-there-project.never-closed`): every project a person set up is renamed, shared,
/// closed and deleted from its row; the always-there project has no name and is never renamed,
/// closed, deleted or shared (the engine never releases it: "The engine's global library is not a
/// project; it is never released").
nonisolated struct ProjectRowMenuOffers: Equatable {
    let rename: Bool
    let share: Bool
    let close: Bool
    let delete: Bool

    static func forProject(isAlwaysThere: Bool, multiuser: Bool) -> Self {
        Self(rename: !isAlwaysThere, share: multiuser && !isAlwaysThere, close: !isAlwaysThere, delete: !isAlwaysThere)
    }
}

/// Whether a FOLDER row offers Share… (`sharing.settings.project-share-sheet`, #5967): with Multi-user on, for a project this engine
/// hosts, and never the always-there project (which is never shared). Pure, so the gating is tested without a window.
nonisolated enum FolderShareOffer {
    static func isOffered(multiuser: Bool, isAlwaysThere: Bool, hostIsLocal: Bool) -> Bool {
        multiuser && !isAlwaysThere && hostIsLocal
    }
}
