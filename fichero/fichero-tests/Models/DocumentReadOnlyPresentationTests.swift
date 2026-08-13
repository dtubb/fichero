@testable import Fichero
import Foundation
import Testing

/// #4514 / #4516 — one read-only predicate and one icon ladder, shared by the
/// sidebar and every library view mode.
///
/// Before this, `read_only` never reached the client at all (the converter
/// dropped `attributes`), the sidebar inferred locked-ness from ancestry —
/// which is false until the children cache fills, hence the flicker — and the
/// library views had no read-only concept whatsoever: they switched on
/// `docType == .folder` and nothing else, so a Default Workflows folder looked
/// and behaved like any folder the user owns.
@Suite("Read-only + display symbol — one predicate, both panes (#4514/#4516)")
struct DocumentReadOnlyPresentationTests {

    private func folder(
        id: String = "f1",
        parentId: String? = nil,
        readOnly: Bool? = nil,
        isWorkspace: Bool = false
    ) -> Document {
        Document(
            id: id,
            parentId: parentId,
            docType: .folder,
            name: id,
            isWorkspace: isWorkspace,
            attributes: readOnly.map { ["read_only": AnyCodable($0)] } ?? [:]
        )
    }

    private func workflowMirror(readOnly: Bool = true) -> Document {
        Document(
            id: "wf-1",
            parentId: Document.defaultWorkflowsContainerID,
            docType: .file,
            name: "Transcribe",
            nodeKind: "workflow",
            attributes: ["read_only": AnyCodable(readOnly)]
        )
    }

    // MARK: - isReadOnly

    @Test("The engine's read_only attribute is the answer")
    func readOnlyComesFromAttributes() {
        #expect(folder(readOnly: true).isReadOnly)
        #expect(folder(readOnly: false).isReadOnly == false)
        #expect(folder().isReadOnly == false, "absent means writable, not unknown")
    }

    @Test("A non-boolean read_only is not a lock")
    func nonBooleanReadOnlyIsNotALock() {
        let odd = Document(
            id: "f", docType: .folder, name: "f",
            attributes: ["read_only": AnyCodable("yes")]
        )
        #expect(odd.isReadOnly == false)
    }

    // MARK: - isLockedSystemNode (the shared predicate)

    @Test("The lock keys on read_only alone; the workflow tint is a separate fact")
    func lockedSystemNodeKeysOnReadOnlyAlone() {
        // Ruling 1f2edfc4c (Daniel 2026-08-10): a NEW user workflow must be
        // editable — `isReadOnly || isWorkflowNode` put a lock on every
        // workflow node. The lock now follows the engine's read_only flag
        // alone; the purple family cue (usesWorkflowTint) still covers every
        // workflow node, locked or not.
        #expect(folder(readOnly: true).isLockedSystemNode)
        #expect(folder().isLockedSystemNode == false)

        var mirror = workflowMirror(readOnly: false)
        mirror.prototypeKey = "workflow"
        #expect(mirror.isWorkflowNode)
        #expect(mirror.isLockedSystemNode == false, "a user workflow is not locked")
        #expect(mirror.usesWorkflowTint, "the visual family cue survives without the lock")

        #expect(workflowMirror(readOnly: true).isLockedSystemNode, "shipped defaults stay locked")
    }

    // MARK: - Drop refusal (the behaviour, not the glyph)

    @Test("A read-only folder refuses item drops; an ordinary folder accepts")
    func readOnlyFolderRefusesDrops() {
        #expect(folder().acceptsItemDrops)
        #expect(folder(readOnly: true).acceptsItemDrops == false)
    }

    @Test("Only folders are drop targets at all")
    func nonFoldersAreNotDropTargets() {
        let file = Document(id: "d", docType: .file, name: "d")
        #expect(file.acceptsItemDrops == false)
        #expect(workflowMirror().acceptsItemDrops == false)
    }

    // MARK: - displaySymbol (one glyph per node, every surface)

    @Test("A read-only folder gets the gear-badged folder without any tree context")
    func readOnlyFolderIsGearBadged() {
        // No `resolveParent`, no children cache, no ancestry walk — this is
        // what removes the "unlocked until loaded" flicker.
        #expect(folder(readOnly: true).displaySymbol() == "folder.badge.gearshape")
    }

    @Test("The sidebar's ancestry answer can still force the locked glyph")
    func ancestryOverrideStillWorks() {
        // A legacy preset folder re-homed under the container before the
        // engine backfilled read_only (#4200).
        let legacy = folder(id: "legacy-books", parentId: Document.defaultWorkflowsContainerID)
        #expect(legacy.displaySymbol() == "folder")
        #expect(legacy.displaySymbol(treatAsLockedFolder: true) == "folder.badge.gearshape")
    }

    @Test("A workflow mirror gets the branch glyph — this is #4516's whole bug")
    func workflowMirrorGetsTheBranchGlyph() {
        var mirror = workflowMirror()
        mirror.prototypeKey = "workflow"
        #expect(mirror.displaySymbol() == ItemCategory.workflow.icon)
        // The pre-fix state: `prototypeKey` was dropped by the converter, so
        // `isWorkflowNode` was false and the row fell through to the generic
        // file glyph — a blank thumbnail well in the library grid.
        var dropped = mirror
        dropped.prototypeKey = nil
        #expect(dropped.displaySymbol() == "doc")
    }

    @Test("Workspaces, file types and plain folders keep their existing glyphs")
    func remainingRungsAreUnchanged() {
        #expect(folder(isWorkspace: true).displaySymbol() == "square.grid.2x2")
        #expect(folder().displaySymbol() == "folder")
        let pdf = Document(id: "p", docType: .file, fileType: .pdf, name: "p")
        #expect(pdf.displaySymbol() == "doc.richtext")
        #expect(Document(id: "x", docType: .file, name: "x").displaySymbol() == "doc")
    }

    @Test("A locked folder is locked BEFORE it is a workspace")
    func lockOutranksWorkspace() {
        #expect(folder(readOnly: true, isWorkspace: true).displaySymbol() == "folder.badge.gearshape")
    }

    // MARK: - The sidebar reads the same answer

    @MainActor
    @Test("A read_only folder is locked and gear-badged with no ancestor loaded")
    func sidebarUsesTheFlagWithoutAncestry() throws {
        // The flicker case: a legacy-id preset folder the ancestry walk cannot
        // place (no container in the loaded set). Ancestry says "unknown →
        // unlocked"; the flag says locked, and the flag is the engine's own
        // answer, available on the very first paint.
        let legacy = folder(id: "legacy-books-1a2b", readOnly: true)
        #expect(
            SidebarItemBuilder.lockedSystemFolderIds(in: [legacy]).isEmpty,
            "fixture must be invisible to the ancestry walk, or this proves nothing"
        )
        let items = SidebarItemBuilder.buildLibraryHierarchy(
            from: [legacy], libraryId: UUID()
        )
        let item = try #require(items.first { $0.id == "doc:\(legacy.id)" })
        #expect(item.isDefaultWorkflowFolder)
        #expect(item.icon == "folder.badge.gearshape")
    }

    // MARK: - The wire shape actually carries it

    @Test("attributes and child_count decode from the engine's JSON")
    func wireShapeDecodes() throws {
        let json = """
        {
          "id": "system-default-workflows",
          "doc_type": "folder",
          "name": "Default Workflows",
          "status": "pending",
          "metadata": {},
          "child_count": 3,
          "prototype_key": "folder",
          "node_kind": "workflow_container",
          "attributes": {"read_only": true, "scope": "global", "system": true},
          "created_at": "2026-08-04T00:00:00Z",
          "updated_at": "2026-08-04T00:00:00Z"
        }
        """
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let doc = try decoder.decode(Document.self, from: Data(json.utf8))
        #expect(doc.childCount == 3, "#4515: a visible folder must know it has children")
        #expect(doc.isReadOnly)
        #expect(doc.nodeKind == "workflow_container")
        #expect(doc.acceptsItemDrops == false)
    }
}
