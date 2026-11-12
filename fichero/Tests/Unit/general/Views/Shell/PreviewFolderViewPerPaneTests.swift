@testable import Fichero
import Foundation
import Testing

/// spec: library-view-modes `library.preview.folder-view-per-pane`, `-defaults`, `-persists-per-pane`,
/// `-cannot-show-says-so` and `library.preview.folder-opens-as-table-then-last-view` (#6365, #6172).
/// The pure rules of the Preview's folder view: the default, the per-pane write, the split copy and the
/// remembered-list round trip. No app, no window.
struct PreviewFolderViewPerPaneTests {
    private let leftId = UUID()
    private let rightId = UUID()

    private func twoPreviews(left: String? = nil, right: String? = nil) -> PaneList {
        PaneList([
            .leaf(id: leftId, kind: .preview, scope: .current, config: PaneConfig(previewFolderView: left)),
            .leaf(id: rightId, kind: .preview, scope: .current, config: PaneConfig(previewFolderView: right))
        ])
    }

    /// Every leaf's config anywhere in a list, splits flattened.
    private func configs(_ list: PaneList) -> [PaneConfig] {
        func walk(_ node: PaneNode) -> [PaneConfig] {
            switch node {
            case let .leaf(_, _, _, config): [config]
            case let .split(_, _, children): children.flatMap(walk)
            }
        }
        return list.nodes.flatMap(walk)
    }

    private func folderView(_ list: PaneList, _ id: UUID) -> String? { list.config(for: id)?.previewFolderView }

    @Test("a pane that has never been given a choice opens a folder as a Table")
    func defaultIsTable() {
        #expect(PreviewFolderView.effective(nil) == .table)
        #expect(PreviewFolderView.defaultView == .table)
        #expect(PaneConfig.none.previewFolderView == nil)
    }

    @Test("an unreadable stored value reads as the default, never a blank pane")
    func unknownStringIsTheDefault() {
        #expect(PreviewFolderView.effective("columns") == .table)
        #expect(PreviewFolderView.effective("") == .table)
    }

    @Test("each stored raw string reads back as its own view")
    func storedChoiceIsReadBack() {
        #expect(PreviewFolderView.effective("canvas") == .canvas)
        #expect(PreviewFolderView.effective("list") == .list)
        #expect(PreviewFolderView.effective("table") == .table)
        #expect(PreviewFolderView.effective("icons") == .icons)
        #expect(PreviewFolderView.allCases.map(\.rawValue) == ["list", "table", "icons", "canvas"])
    }

    @Test("Canvas is the folder canvas; List, Table and Icons are the Library's own views")
    func displayModes() {
        #expect(PreviewFolderView.canvas.displayMode == nil)
        #expect(PreviewFolderView.list.displayMode == .list)
        #expect(PreviewFolderView.table.displayMode == .table)
        #expect(PreviewFolderView.icons.displayMode == .icon)
        #expect(PreviewFolderView.icons.title == "Icons")
    }

    /// `library.preview.folder-view-one-head` (#6562): the folder's rows under the Source head draw no head of their own,
    /// while a Library pane keeps its head.
    @Test("a folder in the Source pane has one pane head: the embedded rows draw none")
    func folderRowsDrawNoSecondHead() {
        #expect(FolderRowsPreview.showsLibraryHead == false)
        let library = LibraryView(
            documents: [], contentCollection: .documents, isLoading: false, isConnected: true, errorMessage: nil,
            onRetry: {}, libraryToolbar: LibraryToolbarState(), selection: .constant([]), detailDocument: .constant(nil),
            defaultDisplayMode: .table, folderId: nil)
        #expect(library.showsPaneHead)
    }

    @Test("choosing in one Preview pane changes nothing in the other")
    func choiceIsPerPane() {
        let after = twoPreviews().changingLeafPreviewFolderView(leftId, to: "canvas")
        #expect(folderView(after, leftId) == "canvas")
        #expect(folderView(after, rightId) == nil)
        let again = after.changingLeafPreviewFolderView(rightId, to: "list")
        #expect(folderView(again, leftId) == "canvas")
        #expect(folderView(again, rightId) == "list")
    }

    @Test("clearing a pane's choice goes back to the default and leaves the other pane alone")
    func clearingRestoresTheDefault() {
        let cleared = twoPreviews(left: "canvas", right: "list").changingLeafPreviewFolderView(leftId, to: nil)
        #expect(PreviewFolderView.effective(folderView(cleared, leftId)) == .table)
        #expect(folderView(cleared, rightId) == "list")
    }

    @Test("the write reaches a pane nested inside a split and writes no other field")
    func writeReachesNestedLeaf() throws {
        let preview = PaneNode.leaf(
            id: leftId, kind: .preview, scope: .current, config: PaneConfig(previewLens: "edit")
        )
        let list = PaneList([.split(.horizontal, [.leaf(.library), preview])])
        let after = list.changingLeafPreviewFolderView(leftId, to: "list")
        let config = try #require(after.config(for: leftId))
        #expect(config.previewFolderView == "list")
        #expect(config.previewLens == "edit")
        #expect(config.libraryLayout == nil)
    }

    @Test("a pane holding only a folder view counts as configured")
    func folderViewCountsAsConfigured() {
        #expect(!PaneConfig.none.isConfigured)
        #expect(PaneConfig(previewFolderView: "canvas").isConfigured)
    }

    @Test("a split's new half starts with its parent's choice")
    func splitCopiesTheChoice() {
        let list = twoPreviews(left: "list").splittingLeaf(leftId, axis: .horizontal)
        let views = configs(list).map(\.previewFolderView)
        #expect(views.filter { $0 == "list" }.count == 2)
    }

    @Test("the choice round-trips the remembered applied pane list")
    func roundTripsThroughTheRememberedList() throws {
        let suite = "PreviewFolderViewPerPaneTests-\(UUID().uuidString)"
        let store = try #require(UserDefaults(suiteName: suite))
        defer { store.removePersistentDomain(forName: suite) }
        let list = twoPreviews(left: "canvas", right: "list")
        WorkspaceLayoutDefaults.rememberPaneList(list, in: store)
        let restored = try #require(WorkspaceLayoutDefaults.rememberedPaneList(in: store))
        #expect(folderView(restored, leftId) == "canvas")
        #expect(folderView(restored, rightId) == "list")
    }

    @Test("a saved workspace written before the field existed decodes with no choice")
    func olderSavedListDecodes() throws {
        let json = Data(#"{"libraryLayout":"table"}"#.utf8)
        let config = try JSONDecoder().decode(PaneConfig.self, from: json)
        #expect(config.previewFolderView == nil)
        #expect(config.libraryLayout == "table")
    }

    @Test("a built-in workspace starts every pane with no choice, so it opens the default")
    func builtInWorkspacesStartWithNoChoice() {
        for layout in BuiltInWorkspaceLayout.allCases {
            #expect(configs(layout.panes).allSatisfy { $0.previewFolderView == nil })
        }
    }

    @Test("a file selection ignores the folder view, and the choice is kept for the next folder")
    func onlyAFolderUsesTheFolderView() {
        #expect(PreviewFolderView.applies(selectionIsSingleFolder: true))
        #expect(!PreviewFolderView.applies(selectionIsSingleFolder: false))
        // Nothing in the rule rewrites the stored choice: it is read, never written, by the branch.
        let list = twoPreviews(left: "list")
        #expect(folderView(list, leftId) == "list")
    }
}
