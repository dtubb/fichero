import FicheroAPIClient
import Foundation

//  Extracted from Document.swift for file_length (#5113). Behaviour unchanged:
//  the declarations below are byte-for-byte what they were, moved so the file
//  that carries the Document model itself stays readable.

// MARK: - Ingest Mode

extension Document {
    enum IngestMode: String {
        case link
        case copy
        case move
    }

    /// Resolved ingest mode for this document. Backend now writes the
    /// explicit `metadata.ingest_mode` ("link"/"copy"/"move") since #603
    /// Part 2; for older docs without that key we fall back to the legacy
    /// heuristic: bookmark presence → LINK, otherwise COPY.
    var ingestMode: IngestMode {
        if let raw = metadata["ingest_mode"]?.value as? String,
           let mode = IngestMode(rawValue: raw) {
            return mode
        }
        return metadata["bookmark"]?.value != nil ? .link : .copy
    }

    /// True when this document was imported via LINK mode (bookmark reference; original stays on disk).
    var isLinked: Bool { ingestMode == .link }

    /// Reference (alias) node, Finder-style (#2591): renders with an alias
    /// badge and selection resolves to `aliasTargetId` instead of itself.
    var isAlias: Bool {
        nodeKind == "alias" && !(aliasTargetId ?? "").isEmpty
    }

    /// True when this document was imported via MOVE mode (relocated; original deleted).
    /// MOVE deletes are terminal; the delete-confirmation should reflect that.
    var isMoved: Bool { ingestMode == .move }
}

// MARK: - Navigation

extension Document {
    /// True if double-clicking should navigate *into* this document
    /// (show its children) rather than preview it.
    ///
    /// Containers in 0.0.2:
    ///   - Folders — children are the folder's contents
    ///   - PDFs — children are one `Document` per page (see #568)
    var isNavigableContainer: Bool {
        if docType == .folder { return true }
        if fileType == .pdf { return true }
        return false
    }

    /// True for the workflow rows the engine MIRRORS into the document tree to
    /// sit under the seeded "Default Workflows" folder (#11 Phase 1 — the
    /// `workflows` table stays source of truth). A mirror is a plain `.file`
    /// doc with NO `fileType` — see `SidebarItemBuilder.isSidebarVisible`.
    var isWorkflowNode: Bool { prototypeKey == "workflow" }

    /// The engine's own answer to "may the user edit this node?", read from
    /// `attributes.read_only` — the same flag every mutating route enforces
    /// with a 403. It arrives WITH the row, so a surface can render the lock
    /// on first paint instead of inferring it from ancestry once the children
    /// cache has filled (#4514's flicker).
    var isReadOnly: Bool { attributes["read_only"]?.value as? Bool == true }

    /// System-owned row: the ONE predicate the sidebar row and both library
    /// view modes read to decide "purple, locked, and refuses drops" (#4514).
    /// Two surfaces asking the same question two ways is how the library grid
    /// ended up with no read-only concept at all.
    /// LOCKED means the ENGINE will refuse writes (`read_only`) — nothing
    /// else. Being a workflow node no longer implies locked (Daniel,
    /// 2026-08-10: "when you make a new one outside the Default Workflows
    /// folder it should be editable — currently my new workflow has a lock
    /// icon"). Default Workflows ship with read_only set; user workflows
    /// don't.
    var isLockedSystemNode: Bool { isReadOnly }

    /// The purple "system/workflow" icon treatment — a VISUAL family cue,
    /// deliberately separate from the lock: every workflow node is purple,
    /// locked or not.
    var usesWorkflowTint: Bool { isWorkflowNode || isReadOnly }

    /// A folder the user may drop items INTO. A read-only system folder is
    /// not one: the engine 403s the move, so lighting the cell and then
    /// showing a failure banner is the surface asserting a capability it does
    /// not have (#4514).
    var acceptsItemDrops: Bool { docType == .folder && !isReadOnly }

    /// The single icon ladder for a document node, read by the sidebar row and
    /// by every library view mode (#4516). One SF Symbol per node, chosen in
    /// one place: a workflow mirror that reads as a workflow in the sidebar
    /// and as a blank thumbnail well in the grid is two answers to one
    /// question.
    ///
    /// `treatAsLockedFolder` is the sidebar tree builder's ancestry answer for
    /// a legacy preset folder RE-HOMED under the container without a
    /// backfilled `read_only` (#4200); everything else needs no argument.
    func displaySymbol(treatAsLockedFolder: Bool = false) -> String {
        if docType == .folder, treatAsLockedFolder || isReadOnly {
            return "folder.badge.gearshape"
        }
        if isWorkspace { return "square.grid.2x2" }
        if isWorkflowNode { return ItemCategory.workflow.icon }
        return fileType?.icon ?? docType.icon
    }
}

// MARK: - Default Workflows

extension Document {
    /// A VIRTUAL page cursor (2026-08-09): stands in for a page that is not
    /// imported as a document, so the PDF reader can keep its place when the
    /// user pages through an unprocessed PDF. Marked in metadata; consumers
    /// that resolve artifacts tolerate the unknown id (they already tolerate
    /// not-yet-processed pages). Never written to any store and never placed
    /// in browserSelection.
    ///
    /// `isVirtualPageCursorId` is how server-state consumers (artifact loads,
    /// document fetches) recognise these ids and short-circuit instead of
    /// asking the engine about a document that does not exist — the source of
    /// the per-swipe `…:vpage:N … 404` churn (2026-08-11).
    static func isVirtualPageCursorId(_ id: String) -> Bool {
        id.contains(":vpage:")
    }

    static func virtualPageCursor(pdfParentId: String, pageIndex: Int) -> Document {
        Document(
            id: "\(pdfParentId):vpage:\(pageIndex)",
            parentId: pdfParentId,
            docType: .page,
            name: "Page \(pageIndex + 1)",
            sequence: pageIndex + 1,
            metadata: [
                "virtual_page": AnyCodable(true),
                "pdf_parent_id": AnyCodable(pdfParentId)
            ]
        )
    }
}

extension Document {
    /// Stable id of the engine's locked "Default Workflows" container folder;
    /// its system subfolders are ids in the `"\(id):…"` namespace. Mirrors
    /// `_DEFAULT_WORKFLOWS_CONTAINER_ID` in `fichero-server/src/fichero_server/db/__init__.py`.
    static let defaultWorkflowsContainerID = "system-default-workflows"

    /// The container itself, or a subfolder the engine SEEDED into its id
    /// namespace. A fast path only: it says where a row's id came from, not
    /// where the row currently lives.
    var hasDefaultWorkflowContainerID: Bool {
        id == Self.defaultWorkflowsContainerID
            || id.hasPrefix("\(Self.defaultWorkflowsContainerID):")
    }

    /// True for the locked "Default Workflows" container folder or ANY folder
    /// beneath it. These are read-only, non-editable nodes, so the sidebar
    /// marks them with a distinct icon and a lock badge (see
    /// `SidebarItem.fromDocument` and `SidebarItemRow.iconView`).
    ///
    /// Parentage, not id structure, decides this (#4200). `heal_default_workflow_tree`
    /// RE-PARENTS legacy preset folders under the container without RE-IDing
    /// them (b2b9f6899), so a re-homed "Books" keeps its legacy id and the
    /// namespace test alone misses it — it renders unlocked inside a locked
    /// container. Encoding hierarchy in identifiers is what broke here; any
    /// future reparent would break it again.
    ///
    /// Only `parentId` is followed, so a document that merely REFERENCES the
    /// container (alias target, prototype key) is not treated as inside it.
    /// `resolveParent` returns nil for an ancestor the caller hasn't loaded —
    /// the row then falls back to the id fast path rather than claiming to
    /// know it is unlocked.
    func isDefaultWorkflowFolder(resolveParent: (String) -> Document?) -> Bool {
        guard docType == .folder else { return false }
        if hasDefaultWorkflowContainerID { return true }

        // Walk to the root. `visited` guards against a parent cycle: a bad
        // heal or a hand-edited row must not spin the sidebar build.
        var visited: Set<String> = [id]
        var currentParentId = parentId
        while let ancestorId = currentParentId, visited.insert(ancestorId).inserted {
            if ancestorId == Self.defaultWorkflowsContainerID { return true }
            guard let ancestor = resolveParent(ancestorId) else { return false }
            if ancestor.hasDefaultWorkflowContainerID { return true }
            currentParentId = ancestor.parentId
        }
        return false
    }
}
