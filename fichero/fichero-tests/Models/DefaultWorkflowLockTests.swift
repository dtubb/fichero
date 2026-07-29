@testable import Fichero
import Foundation
import Testing

// The lock badge / gear icon on "Default Workflows" rows used to key off id
// STRUCTURE (`id == container || id.hasPrefix("container:")`). The engine's
// heal RE-PARENTS legacy preset folders under the container without RE-IDing
// them, so a re-homed folder sat inside a locked container rendering unlocked
// (#4200). Locked-ness now follows the PARENT chain.
@Suite("Default Workflows lock — ancestry, not id shape (#4200)")
struct DefaultWorkflowLockTests {

    private static let container = Document.defaultWorkflowsContainerID

    private func folder(id: String, parentId: String? = nil) -> Document {
        Document(id: id, parentId: parentId, docType: .folder, name: id)
    }

    /// Resolver over a fixed document set, standing in for the tree builder's
    /// live-store lookup.
    private func resolver(_ documents: [Document]) -> (String) -> Document? {
        let byId = Dictionary(documents.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return { byId[$0] }
    }

    @Test("The container itself is locked")
    func containerIsLocked() {
        let container = folder(id: Self.container)
        #expect(container.isDefaultWorkflowFolder(resolveParent: resolver([container])))
    }

    @Test("Engine-seeded subfolders in the id namespace stay locked")
    func seededSubfolderIsLocked() {
        let seeded = folder(id: "\(Self.container):books", parentId: Self.container)
        #expect(seeded.isDefaultWorkflowFolder(resolveParent: resolver([seeded])))
    }

    // THE BUG: a legacy-shaped id, NOT in the container namespace, re-homed
    // under the container by the heal. The id test misses it entirely.
    @Test("A re-homed legacy folder under the container is locked")
    func rehomedLegacyFolderIsLocked() {
        let legacy = folder(id: "legacy-books-1a2b", parentId: Self.container)
        #expect(legacy.hasDefaultWorkflowContainerID == false, "fixture must not be in the namespace")
        #expect(legacy.isDefaultWorkflowFolder(resolveParent: resolver([legacy])))
    }

    @Test("Descendants deeper than one level are locked")
    func deepDescendantIsLocked() {
        let legacyChild = folder(id: "legacy-books", parentId: Self.container)
        let grandchild = folder(id: "legacy-books-1900s", parentId: legacyChild.id)
        let greatGrandchild = folder(id: "legacy-books-1900s-drafts", parentId: grandchild.id)
        let all = [folder(id: Self.container), legacyChild, grandchild, greatGrandchild]
        #expect(grandchild.isDefaultWorkflowFolder(resolveParent: resolver(all)))
        #expect(greatGrandchild.isDefaultWorkflowFolder(resolveParent: resolver(all)))
    }

    @Test("An ordinary user folder is not locked")
    func unrelatedFolderIsNotLocked() {
        let parent = folder(id: "user-archive")
        let child = folder(id: "user-letters", parentId: parent.id)
        #expect(child.isDefaultWorkflowFolder(resolveParent: resolver([parent, child])) == false)
    }

    // Only parentId is followed. A row that merely POINTS AT the container is
    // not inside it, so it must not inherit the lock.
    @Test("Merely referencing the container does not lock a folder")
    func referencingContainerIsNotLocked() {
        let elsewhere = folder(id: "user-archive")
        let referencing = Document(
            id: "user-shortcut",
            parentId: elsewhere.id,
            docType: .folder,
            name: "Shortcut",
            prototypeKey: Self.container,
            aliasTargetId: Self.container
        )
        #expect(referencing.isDefaultWorkflowFolder(resolveParent: resolver([elsewhere, referencing])) == false)
    }

    @Test("Files under the container are not folders and do not take the folder lock")
    func fileUnderContainerIsNotAFolder() {
        let file = Document(id: "some-file", parentId: Self.container, docType: .file, name: "notes")
        #expect(file.isDefaultWorkflowFolder(resolveParent: resolver([file])) == false)
    }

    // A parent cycle (bad heal, hand-edited row) must terminate, not spin the
    // sidebar build.
    @Test("A parent cycle terminates instead of looping")
    func parentCycleTerminates() {
        let first = folder(id: "cycle-a", parentId: "cycle-b")
        let second = folder(id: "cycle-b", parentId: "cycle-a")
        #expect(first.isDefaultWorkflowFolder(resolveParent: resolver([first, second])) == false)
    }

    @Test("A row whose ancestor is not loaded falls back to the id fast path")
    func unresolvableAncestorFallsBack() {
        let orphan = folder(id: "legacy-books", parentId: "not-loaded")
        #expect(orphan.isDefaultWorkflowFolder(resolveParent: { _ in nil }) == false)
        let seeded = folder(id: "\(Self.container):books", parentId: "not-loaded")
        #expect(seeded.isDefaultWorkflowFolder(resolveParent: { _ in nil }))
    }

    // End to end through the tree builder: the re-homed row must come out of
    // the sidebar build carrying the lock AND the gear icon.
    @MainActor
    @Test("The sidebar tree marks a re-homed legacy folder locked and gear-badged")
    func builderMarksRehomedFolder() throws {
        let container = folder(id: Self.container)
        let legacy = folder(id: "legacy-books-1a2b", parentId: Self.container)
        let userFolder = folder(id: "user-archive")

        let items = SidebarItemBuilder.buildLibraryHierarchy(
            from: [container, legacy, userFolder],
            libraryId: UUID()
        )

        let containerItem = try #require(items.first { $0.id == "doc:\(Self.container)" })
        #expect(containerItem.isDefaultWorkflowFolder)
        let legacyItem = try #require(containerItem.children?.first { $0.id == "doc:\(legacy.id)" })
        #expect(legacyItem.isDefaultWorkflowFolder)
        #expect(legacyItem.icon == "folder.badge.gearshape")

        let userItem = try #require(items.first { $0.id == "doc:\(userFolder.id)" })
        #expect(userItem.isDefaultWorkflowFolder == false)
        #expect(userItem.icon != "folder.badge.gearshape")
    }
}
