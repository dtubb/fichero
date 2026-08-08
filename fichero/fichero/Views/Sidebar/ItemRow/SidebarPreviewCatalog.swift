import SwiftUI

// MARK: - Sidebar preview catalog (Daniel, 2026-08-08)
//
// REAL components, inert dependencies — unlike SidebarItemRow+Preview's
// static look-alike, these render the actual `SidebarItemRow` (and the
// actual drop-highlight modifier), so selection colors, badges, locks and
// spinners can be judged in the canvas or via `mcp__xcode__RenderPreview`
// without launching the app. Each part gets its own #Preview so a change
// to one state is reviewed against exactly that state.
//
// The dependencies are real instances constructed empty: the state
// managers are plain @Observable holders; `LibraryManager.shared` resolves
// the fixture's random library id to nil, so every service on the row is
// nil and nothing touches the network.

// MARK: Fixtures

private enum SidebarPreviewFixtures {
    static let libraryId = UUID()

    static func doc(
        _ name: String,
        type: DocType = .file,
        fileType: FileType? = nil,
        childCount: Int = 0
    ) -> Document {
        Document(
            id: name.lowercased().replacingOccurrences(of: " ", with: "-"),
            docType: type,
            fileType: fileType,
            name: name,
            childCount: childCount
        )
    }

    static func item(
        _ document: Document,
        icon: String,
        children: [SidebarItem]? = nil,
        locked: Bool = false
    ) -> SidebarItem {
        SidebarItem(
            id: "doc:\(document.id)",
            name: document.name,
            icon: icon,
            category: .folder,
            itemType: .document(document),
            children: children,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: document.docType == .folder,
            isDefaultWorkflowFolder: locked
        )
    }

    @MainActor
    static func row(
        _ item: SidebarItem,
        selectedId: String? = nil,
        expanded: Set<String> = []
    ) -> some View {
        SidebarItemRow(
            item: item,
            lookupItem: { _ in nil },
            expandedItems: .constant(expanded),
            selectedItemId: .constant(selectedId),
            selectedDestinations: selectedId.flatMap {
                SidebarDestination(serializedID: $0).map { [$0] }
            } ?? [],
            renameState: RenameStateManager(),
            deleteState: DeleteStateManager(),
            sidebarState: SidebarState(),
            libraryManager: LibraryManager.shared
        )
        .environment(WorkflowExecutionObserver())
        .environment(WindowState(libraryId: libraryId))
        .tag(item.destination)
    }
}

// MARK: Row states — every visual state of the REAL row
//
// The pdf row is SELECTED (both in the row's own selection inputs AND the
// List's native selection) — Finder's grammar: grey platter, accent name and
// icon, in every focus state. If an accent platter appears here, the native
// emphasized selection is leaking around the listRowBackground platter.

#Preview("Row states") {
    let folder = SidebarPreviewFixtures.doc("Letters 1893", type: .folder, childCount: 4)
    let pdf = SidebarPreviewFixtures.doc("Diary.pdf", fileType: .pdf, childCount: 10)
    let page = SidebarPreviewFixtures.doc("Page 3", type: .page)
    let image = SidebarPreviewFixtures.doc("scan_001.tif", fileType: .image)
    let locked = SidebarPreviewFixtures.doc("Default Workflows", type: .folder, childCount: 10)
    let selection: Set<SidebarDestination> = SidebarDestination(
        serializedID: "doc:\(pdf.id)"
    ).map { [$0] } ?? []

    return List(selection: .constant(selection)) {
        SidebarPreviewFixtures.row(SidebarPreviewFixtures.item(folder, icon: "folder"))
        SidebarPreviewFixtures.row(
            SidebarPreviewFixtures.item(pdf, icon: "doc.richtext"),
            selectedId: "doc:\(pdf.id)"  // the SELECTED state, for color review
        )
        SidebarPreviewFixtures.row(SidebarPreviewFixtures.item(page, icon: "doc.text"))
        SidebarPreviewFixtures.row(SidebarPreviewFixtures.item(image, icon: "photo"))
        SidebarPreviewFixtures.row(
            SidebarPreviewFixtures.item(locked, icon: "folder.badge.gearshape", locked: true)
        )
    }
    .listStyle(.sidebar)
    .frame(width: 280, height: 320)
}

// MARK: Expanded + selected folder — the #4229 regression watch
//
// The selected platter and the drop fill share one listRowBackground canvas.
// This preview expands a SELECTED folder: the grey platter must cover ONLY
// the folder row. If the children show grey too, the platter is washing the
// subtree — the exact #4229 shape, caught here without a live drag.

#Preview("Expanded selected folder") {
    let pageA = SidebarPreviewFixtures.doc("Page 1", type: .page)
    let pageB = SidebarPreviewFixtures.doc("Page 2", type: .page)
    let folder = SidebarPreviewFixtures.doc("Letters 1893", type: .folder, childCount: 2)
    let children = [
        SidebarPreviewFixtures.item(pageA, icon: "doc.text"),
        SidebarPreviewFixtures.item(pageB, icon: "doc.text")
    ]
    let folderItem = SidebarPreviewFixtures.item(folder, icon: "folder", children: children)
    let selection: Set<SidebarDestination> = SidebarDestination(
        serializedID: folderItem.id
    ).map { [$0] } ?? []

    return List(selection: .constant(selection)) {
        SidebarPreviewFixtures.row(
            folderItem,
            selectedId: folderItem.id,
            expanded: [folderItem.id]
        )
    }
    .listStyle(.sidebar)
    .frame(width: 280, height: 200)
}

// MARK: Drop target — the REAL platter modifier
//
// ONE style for every operation (Daniel's preview review): the full row goes
// solid accent with white content; move/copy/alias feedback is the CURSOR
// badge, which a static preview cannot show.

#Preview("Drop target states") {
    List {
        ForEach(
            [
                ("Drop target (any operation)", true, false),
                ("Selected", false, true),
                ("Plain", false, false)
            ],
            id: \.0
        ) { name, targeted, selected in
            Label(name, systemImage: "folder")
                .foregroundStyle(targeted ? .white : .primary)
                .padding(.vertical, 1)
                .frame(maxWidth: .infinity, alignment: .leading)
                .sidebarDropHighlight(targeted, selected: selected)
        }
    }
    .listStyle(.sidebar)
    .frame(width: 280, height: 160)
}
