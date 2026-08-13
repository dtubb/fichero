import Foundation

// MARK: - Sidebar Structure

/// Category of sidebar item (for icon/display purposes)
enum ItemCategory: String, CaseIterable, Identifiable {
    case folder = "Folder"
    case search = "Search"
    case chat = "Chat"
    case workflow = "Workflow"
    case automation = "Automation"  // Schedules and triggers
    case batch = "Batch"  // Running batches
    case activity = "Activity"  // Workflow runs
    case library = "Library"  // For library group headers

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .folder: return "folder"
        case .search: return "magnifyingglass"
        case .chat: return "bubble.left.and.bubble.right"
        case .workflow: return "arrow.triangle.branch"
        case .automation: return "clock.arrow.2.circlepath"
        case .batch: return "square.stack.3d.up"
        case .activity: return "waveform.path.ecg"
        case .library: return "book.closed"
        }
    }

    /// A restrained category cue for sidebar glyphs. The label stays primary so
    /// the native selected-row treatment remains responsible for legibility.
    var sidebarTint: SidebarItem.Tint {
        switch self {
        case .folder, .library: return .accent
        case .search: return .teal
        case .chat: return .indigo
        case .workflow: return .purple
        case .automation: return .orange
        case .batch: return .blue
        case .activity: return .green
        }
    }
}

extension SidebarItem {
    enum Tint: Equatable {
        case accent
        case teal
        case indigo
        case purple
        case orange
        case blue
        case green
    }
}

/// Generic sidebar item that can be a document, search, chat, or workflow
/// In library-grouped mode, items from all categories can be siblings within a library
struct SidebarItem: Identifiable, Hashable {
    let id: String
    let name: String
    let icon: String
    let category: ItemCategory
    let itemType: ItemType
    var children: [SidebarItem]?
    var progress: Double?  // Optional progress indicator (0.0 to 1.0)
    var showProgress: Bool = false  // Whether to show the progress indicator

    // Multi-library support
    let libraryId: UUID?  // Which library this item belongs to (nil for library group headers)

    // Hierarchical support
    let folderPath: String  // Unix-style path: "/archive/letters"
    let sortOrder: Int      // User-defined order within folder
    let isFolder: Bool      // True for folder items, false for leaf items

    /// Locked "Default Workflows" container or a folder beneath it — the row
    /// renders a distinct colored icon and a lock badge to signal it is
    /// system/default and not user-editable (#11).
    ///
    /// STORED, not derived from the document: locked-ness is a question about
    /// the row's ANCESTRY, and only the tree builder holds the sibling set
    /// needed to answer it (#4200). It is computed once per rebuild, and the
    /// sidebar rebuilds whenever DocumentStore changes, so it tracks the live
    /// store without a per-row lookup on every render.
    var isDefaultWorkflowFolder: Bool = false

    /// `indirect` is LOAD-BEARING perf, not style (Daniel's 2026-08-12 stall
    /// traces: "SidebarItemVwcp" 654ms of value-witness copies). The
    /// `.document` payload is a full `Document` — metadata dictionary,
    /// curated items, structure, and possibly the whole `pageContent`
    /// transcript — stored INLINE in every SidebarItem, so each tree copy,
    /// List diff, and `children` array CoW paid a deep value-witness copy of
    /// all of it, per row. Boxing the payloads turns those copies into a
    /// retain/release; the tree builder allocates each box once per rebuild.
    indirect enum ItemType: Hashable {
        case document(Document)
        case savedSearch(SavedSearch)
        case conversation(Conversation)
        case workflow(WorkflowSidebarItem)
        case chain(WorkflowChain)
        case comparison(ComparisonSummary)
        case schedule(ScheduleInfo)
        case trigger(TriggerInfo)
        case batch(BatchInfo)
        case activityRun(ActivityItem)
        case folder(folderPath: String)  // Folder item (no data, just structure)
        case libraryHeader  // For library group headers
    }

    /// Hash by id alone — the synthesized hash walked every field, including
    /// the boxed `Document` payload and the whole `children` subtree, on
    /// every Set/selection operation. Equality stays synthesized (deep), so
    /// the a == b ⇒ hash(a) == hash(b) contract holds: equal items always
    /// share an id; unequal items sharing one merely collide.
    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }

    var isExpandable: Bool {
        if let children, !children.isEmpty {
            return true
        }
        guard case .document(let document) = itemType else { return false }
        if !document.structure.isEmpty {
            return true
        }
        return document.isNavigableContainer && document.childCount > 0
    }

    var destination: SidebarDestination {
        SidebarDestination(serializedID: id) ?? .document(id)
    }

    /// The icon tint is intentionally isolated to the glyph so List can retain
    /// its native selected-row contrast and accessibility behavior.
    var sidebarTint: Tint {
        switch itemType {
        case .document, .folder, .libraryHeader:
            return category.sidebarTint
        case .savedSearch: return .teal
        case .conversation, .comparison: return .indigo
        case .workflow, .chain: return .purple
        case .schedule, .trigger: return .orange
        case .batch: return .blue
        case .activityRun: return .green
        }
    }

    /// Whether this row can actually be reordered by dragging in the sidebar.
    /// Mirrors the kinds `handleUnifiedRowsMove` dispatches (documents/folders,
    /// saved searches, workflows/chains); everything else has no reorder
    /// endpoint, so its rows disable the move drag rather than show a system
    /// insertion indicator that snaps back with no effect.
    var supportsSidebarReorder: Bool {
        switch itemType {
        case .document, .savedSearch, .workflow, .chain, .folder:
            return true
        case .conversation, .comparison, .schedule, .trigger, .batch, .activityRun, .libraryHeader:
            return false
        }
    }

    /// What kind of items can this item accept as drop targets, if any?
    ///
    /// Returns:
    /// - `.document` for document folders (real `.folder` docType with a
    ///   backing `Document` record).
    /// - `.savedSearch` / `.conversation` / `.workflow` for virtual folders
    ///   in the corresponding sections (type is `.folder(folderPath:)`,
    ///   category distinguishes which section owns the folder).
    /// - `nil` for everything else (leaves, library headers, non-folder
    ///   items) — the drop handler uses that to reject the drop.
    ///
    /// Used by `SidebarItemRow+DropHandlers.swift:handleDropIntoFolder` to
    /// decide whether a drop on this item is valid and which backend
    /// service to call for the move. Sidebar plan Step 9 (#585).
    var folderKind: SidebarItemKind? {
        switch itemType {
        case .document(let doc) where doc.docType == .folder:
            return .document
        case .folder:
            switch category {
            case .search: return .savedSearch
            case .chat: return .conversation
            case .workflow: return .workflow
            default: return nil
            }
        default:
            return nil
        }
    }

    // Convenience initializers
    /// `isDefaultWorkflowFolder` is passed IN rather than read off the
    /// document: the answer depends on the row's ancestry, which only the
    /// caller building the tree can resolve (#4200). Callers with no tree
    /// context get the id-namespace fast path, which still covers every
    /// engine-SEEDED row.
    static func fromDocument(
        _ doc: Document,
        libraryId: UUID,
        children: [SidebarItem]? = nil,
        isDefaultWorkflowFolder: Bool? = nil,
        parent: Document? = nil
    ) -> SidebarItem {
        // `attributes.read_only` is the engine's own answer and arrives WITH
        // the row, so it needs no tree context and no children cache — which
        // is what removes #4514's "unlocked until loaded" flicker. The
        // ancestry answer stays OR-ed in for legacy preset folders re-homed
        // under the container before the flag was backfilled (#4200).
        // Folder-scoped on purpose: a workflow MIRROR row is read-only too,
        // but it is not a folder and must not claim this flag.
        let isLockedSystemFolder = doc.docType == .folder
            && (doc.isReadOnly
                || (isDefaultWorkflowFolder ?? doc.hasDefaultWorkflowContainerID))
        return SidebarItem(
            id: "doc:\(doc.id)",
            // #116/#4416: this was `doc.pageThumbnailLabel ?? doc.name`, and the
            // sidebar was the ONE document surface composing a name by hand —
            // zero uses of DocumentTitle across 42 files, against 30 call sites
            // elsewhere. That is why #4416 needed three sweeps: each fixed the
            // surfaces that used the composer and could not see the one that
            // did not. Hand-rolling lost all three of its rungs — a user-set
            // metadata title was ignored, an unfiltered
            // `fichero_upload_<random>.pdf` rendered verbatim, and a page read
            // as a bare "1" instead of "Page 1". The row label, the VoiceOver
            // label and the help text all derive from this one string.
            name: DocumentTitle.displayName(for: doc, parent: parent),
            // Default-workflow container/subfolders are locked, system-seeded
            // folders — give them a distinct gear-badged folder icon (colored
            // in `SidebarItemRow.iconView`) so they read as non-editable (#11).
            // Workflow mirror nodes carry no fileType, so name them explicitly
            // rather than let them fall through to the generic "doc" glyph
            // (#4058) — they must match `fromWorkflow`'s icon to read as
            // workflows. Otherwise prefer the file-type-specific icon (e.g.
            // "doc.richtext" for PDFs) over the generic docType icon ("doc"
            // for any .file) — makes PDFs visually distinct (#574).
            // Workspace folders (#4308/#4335) read as workspaces, not plain
            // folders — one typed node vocabulary in the tree.
            //
            // The ladder itself now lives on `Document.displaySymbol` so the
            // library views render the SAME glyph for the same node (#4516).
            // It used to be spelled out here, which is why a workflow mirror
            // was a branch icon in the sidebar and an empty thumbnail well in
            // the grid.
            icon: doc.displaySymbol(treatAsLockedFolder: isLockedSystemFolder),
            category: .folder,
            itemType: .document(doc),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: doc.parentId ?? "/",  // Documents use parentId for hierarchy
            sortOrder: doc.sortOrder,  // backed by backend /documents/reorder (#572)
            isFolder: doc.docType == .folder,
            isDefaultWorkflowFolder: isLockedSystemFolder
        )
    }

    static func fromSearch(_ search: SavedSearch, libraryId: UUID, children: [SidebarItem]? = nil) -> SidebarItem {
        SidebarItem(
            id: "search:\(search.id)",
            name: search.name,
            icon: search.icon,
            category: .search,
            itemType: .savedSearch(search),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: search.folderPath,
            sortOrder: search.sortOrder,
            isFolder: false
        )
    }

    static func fromWorkflow(
        _ workflow: WorkflowSidebarItem,
        libraryId: UUID,
        children: [SidebarItem]? = nil
    ) -> SidebarItem {
        SidebarItem(
            id: "workflow:\(workflow.id)",
            name: workflow.name,
            icon: "arrow.triangle.branch",
            category: .workflow,
            itemType: .workflow(workflow),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: workflow.folderPath,
            sortOrder: workflow.sortOrder,
            isFolder: false
        )
    }

    static func fromConversation(
        _ conversation: Conversation,
        libraryId: UUID,
        children: [SidebarItem]? = nil
    ) -> SidebarItem {
        SidebarItem(
            id: "chat:\(conversation.id)",
            name: conversation.title,
            icon: "bubble.left.and.bubble.right",
            category: .chat,
            itemType: .conversation(conversation),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: conversation.folderPath,
            sortOrder: conversation.sortOrder,
            isFolder: false
        )
    }

    // Create a folder item
    static func folder(
        name: String,
        folderPath: String,
        category: ItemCategory,
        libraryId: UUID,
        children: [SidebarItem]? = nil
    ) -> SidebarItem {
        SidebarItem(
            id: "folder:\(folderPath):\(category.rawValue)",
            name: name,
            icon: "folder",
            category: category,
            itemType: .folder(folderPath: folderPath),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: folderPath,
            sortOrder: 0,
            isFolder: true
        )
    }

    // Create a library group header (top-level library item)
    @MainActor
    static func libraryHeader(
        library: LibraryManager.LibraryReference,
        children: [SidebarItem]
    ) -> SidebarItem {
        SidebarItem(
            id: "library:\(library.id.uuidString)",
            name: library.displayName,
            icon: "book.closed",
            category: .library,
            itemType: .libraryHeader,
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: library.id,  // Library headers have their own ID
            folderPath: "/",
            sortOrder: 0,
            isFolder: true
        )
    }
}
