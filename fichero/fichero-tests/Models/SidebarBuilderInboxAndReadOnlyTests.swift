import Foundation
import XCTest

@testable import Fichero

/// Adversarial coverage of the least-exercised branch of
/// `SidebarItemBuilder.buildLibraryHierarchy`: the special-cased **Inbox**
/// root, which is built by its own `buildInboxItem` rather than by
/// `SidebarItem.fromDocument`, plus how `attributes.read_only` reaches the
/// tree (#4514).
///
/// The Inbox branch is where a row can VANISH rather than render wrong, which
/// is the failure mode the Finder rule ("show ALL items") exists to prevent —
/// and the one no screenshot catches. The shared folder-path walker lives in
/// `SidebarFolderPathHierarchyTests`.
@MainActor
final class SidebarBuilderInboxAndReadOnlyTests: XCTestCase {

    private let libraryId = UUID()

    private func folder(
        id: String, name: String, parentId: String? = nil, sortOrder: Int = 0,
        childCount: Int = 0, attributes: [String: AnyCodable] = [:]
    ) -> Document {
        Document(
            id: id, parentId: parentId, docType: .folder, name: name,
            childCount: childCount, sortOrder: sortOrder, attributes: attributes
        )
    }

    private func file(
        id: String, name: String, parentId: String? = nil, fileType: FileType? = nil,
        sortOrder: Int = 0
    ) -> Document {
        Document(
            id: id, parentId: parentId, docType: .file, fileType: fileType, name: name,
            sortOrder: sortOrder
        )
    }

    private func names(_ items: [SidebarItem]) -> [String] { items.map(\.name) }

    private func build(_ documents: [Document]) -> [SidebarItem] {
        SidebarItemBuilder.buildLibraryHierarchy(from: documents, libraryId: libraryId)
    }

    // MARK: - Inbox: the special case, at its edges

    /// The ordinary shape, so the edge cases below are read against a known
    /// baseline: one Inbox, pinned first, tray icon, folder.
    func testTheOrdinaryInboxIsPinnedFirstWithTheTrayIcon() {
        let items = build([folder(id: "z", name: "Zebra"), folder(id: "in", name: "Inbox")])
        XCTAssertEqual(names(items), ["Inbox", "Zebra"])
        XCTAssertEqual(items[0].icon, "tray.fill")
        XCTAssertTrue(items[0].isFolder)
    }

    /// FIXED (#4527): the loop now hoists only the FIRST root folder named
    /// "Inbox"; any later duplicate (reachable via #3970's empty-collections
    /// window, since `ensureInboxFolder` infers its guard from a `collections`
    /// list that is also empty after a failed load) renders as an ordinary
    /// root folder instead of silently replacing the winner and vanishing.
    func testTwoRootsNamedInboxMustBothRender() {
        let items = build([
            folder(id: "inbox-old", name: "Inbox", childCount: 12),
            folder(id: "inbox-new", name: "Inbox")
        ])
        XCTAssertEqual(items.count, 2, "no row may be dropped from the tree")
        XCTAssertEqual(
            Set(items.compactMap { item -> String? in
                guard case .document(let doc) = item.itemType else { return nil }
                return doc.id
            }),
            ["inbox-old", "inbox-new"]
        )
        XCTAssertEqual(items[0].icon, "tray.fill", "the first Inbox keeps the special row")
        XCTAssertNotEqual(items[1].icon, "tray.fill", "the duplicate is an ordinary folder")
    }

    /// FIXED (#4527): the Inbox match now mirrors
    /// `LibraryManager.ensureInboxFolder` — name AND `docType == .folder` — so
    /// a root FILE the user happens to call "Inbox" (a note, a Markdown
    /// scratchpad) renders as the ordinary row it is instead of a
    /// folder-affordanced dead end that refuses every drop.
    func testARootFileNamedInboxMustNotBecomeAFolder() {
        let items = build([file(id: "note", name: "Inbox", fileType: .text)])
        XCTAssertEqual(items.count, 1)
        XCTAssertFalse(items[0].isFolder, "a .file document is not a folder")
        XCTAssertNotEqual(items[0].icon, "tray.fill", "no tray for a plain file")
    }

    /// FIXED (#4527): `buildInboxItem` now threads `parent` into `buildItem`
    /// like every other branch, so a direct child of the Inbox whose own name
    /// is the engine's storage artifact gets DocumentTitle's parent-fallback
    /// rung (#116/#4416) instead of falling all the way to "Untitled". The
    /// Inbox is where freshly-imported documents land — exactly the ones whose
    /// names are still `fichero_upload_…`.
    func testInboxChildrenGetTheSameNameFallbackAsEveryOtherFolder() {
        let storageNamed = file(
            id: "kid", name: "\(DocumentTitle.storageNamePrefix)c84fgjke.pdf",
            parentId: "parent", fileType: .pdf
        )

        let underInbox = build([
            folder(id: "parent", name: "Inbox"),
            storageNamed
        ])
        let underOrdinaryFolder = build([
            folder(id: "parent", name: "18590129"),
            storageNamed
        ])

        let inboxChildName = underInbox.first?.children?.first?.name
        let ordinaryChildName = underOrdinaryFolder.first?.children?.first?.name

        XCTAssertEqual(
            ordinaryChildName, "18590129",
            "the parent-fallback rung works everywhere else"
        )
        XCTAssertNotEqual(
            inboxChildName, DocumentTitle.placeholder,
            "an Inbox child must get the same name ladder as any other child"
        )
        XCTAssertEqual(
            inboxChildName, "Inbox",
            "the parent-fallback rung resolves to the Inbox's own name"
        )
    }

    /// An Inbox with no loaded children but a positive `child_count` must still
    /// show a chevron — the #4515 invariant, checked on the special-cased row
    /// rather than only on ordinary folders.
    func testAnUnloadedInboxWithChildrenIsStillExpandable() {
        let items = build([folder(id: "in", name: "Inbox", childCount: 7)])
        XCTAssertEqual(items.count, 1)
        XCTAssertNil(items[0].children, "children are not loaded yet")
        XCTAssertTrue(items[0].isExpandable, "child_count is what draws the chevron")
    }

    /// An empty Inbox has no chevron. The other half of the same rule: a
    /// `child_count` of 0 must be believed, not treated as "unknown".
    func testAnEmptyInboxIsNotExpandable() {
        let items = build([folder(id: "in", name: "Inbox", childCount: 0)])
        XCTAssertFalse(items[0].isExpandable)
    }

    /// A NON-root folder called "Inbox" is an ordinary folder — the special
    /// case is keyed on being a root, and a nested folder of that name must not
    /// be hoisted out of its parent.
    func testANestedFolderNamedInboxStaysWhereItIs() {
        let items = build([
            folder(id: "archive", name: "Archive"),
            folder(id: "nested", name: "Inbox", parentId: "archive")
        ])
        XCTAssertEqual(names(items), ["Archive"])
        XCTAssertEqual(items[0].children?.map(\.name), ["Inbox"])
        XCTAssertNotEqual(
            items[0].children?.first?.icon, "tray.fill",
            "only the library's own root Inbox gets the tray"
        )
    }

    /// The Inbox is pinned FIRST regardless of sort order — a user reorder that
    /// gives another root a lower `sortOrder` must not displace it.
    func testTheInboxOutranksSortOrder() {
        let items = build([
            folder(id: "a", name: "Alpha", sortOrder: -5),
            folder(id: "in", name: "Inbox", sortOrder: 99)
        ])
        XCTAssertEqual(names(items), ["Inbox", "Alpha"])
    }

    // MARK: - Read-only propagation into the tree

    /// `attributes.read_only` arrives WITH the row, so the lock is drawn on
    /// first paint without any ancestry lookup (#4514). Checked through the
    /// real builder rather than through `fromDocument` directly.
    func testReadOnlyArrivesWithTheRowAndLocksTheFolder() {
        let locked = folder(
            id: "locked", name: "Default Workflows",
            attributes: ["read_only": AnyCodable(true)]
        )
        let items = build([locked])
        XCTAssertTrue(items[0].isDefaultWorkflowFolder)
        XCTAssertEqual(items[0].icon, "folder.badge.gearshape")
        guard case .document(let doc) = items[0].itemType else {
            return XCTFail("expected a document row")
        }
        XCTAssertFalse(doc.acceptsItemDrops, "a read-only folder refuses drops")
    }

    /// Read-only-ness is FOLDER-scoped on purpose: a workflow mirror row is
    /// read-only too, but it is not a folder and must not claim the locked
    /// folder flag (or it would be drawn with a folder-gear glyph).
    func testAReadOnlyLeafDoesNotClaimTheLockedFolderFlag() {
        let mirror = Document(
            id: "wf-1", parentId: nil, docType: .file, name: "Transcribe",
            prototypeKey: "workflow", attributes: ["read_only": AnyCodable(true)]
        )
        let items = build([mirror])
        XCTAssertFalse(items[0].isDefaultWorkflowFolder)
        XCTAssertNotEqual(items[0].icon, "folder.badge.gearshape")
    }

    /// Read-only-ness does NOT propagate down: a writable folder nested under a
    /// read-only one keeps its own answer unless the ancestry rule (the
    /// `Default Workflows` container) says otherwise. Pinned so a future
    /// "inherit the lock" change is deliberate.
    func testReadOnlyDoesNotLeakToUnrelatedChildren() {
        let items = build([
            folder(id: "locked", name: "Locked", attributes: ["read_only": AnyCodable(true)]),
            folder(id: "kid", name: "Kid", parentId: "locked")
        ])
        let kid = items.first?.children?.first
        XCTAssertEqual(kid?.name, "Kid")
        XCTAssertFalse(kid?.isDefaultWorkflowFolder ?? true)
    }

}
