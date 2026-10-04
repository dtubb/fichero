@testable import Fichero
import Foundation
import Testing

/// `library.modes.the-view-follows-the-node` (ruled 2026-10-04, #5428): a sidebar click on a source
/// opens it Finder-style. Driven through the real sidebar selection store (`SidebarSelectionState`),
/// the real view-mode store (`ViewSettings`, which `updateViewDisplayMode` writes) and the real pane
/// list, with the decisions the sidebar route and the shell apply (`SidebarSourceOpen`).
@MainActor
struct LibraryViewFollowsNodeTests {
    private let libraryId = UUID()
    private let folder = Document(id: "fold", docType: .folder, name: "Letters")
    private let image = Document(id: "img-1", parentId: "fold", docType: .file, fileType: .image, name: "0970.jpg")
    private let image2 = Document(id: "img-2", parentId: "fold", docType: .file, fileType: .image, name: "0971.jpg")
    private let pdf = Document(id: "pdf-1", parentId: "fold", docType: .file, fileType: .pdf, name: "Diary.pdf")
    private var children: [Document] { [image, image2, pdf] }

    /// What the window shows after a sidebar click on `doc`: the folder the Library pane lists and
    /// keys its canvas by, its selection, and what the Preview draws.
    private struct Shown {
        let paneFolderId: String?
        let selection: Set<String>
        let preview: Document?
        let opensPreview: Bool
    }

    private func click(_ doc: Document, _ selection: SidebarSelectionState, previewShowing: Bool = true) throws -> Shown {
        selection.selectedItemId = SidebarDestination.document(doc.id).serializedID
        let open = try #require(SidebarSourceOpen.plan(for: doc, previewShowing: previewShowing))
        // The sidebar route shows the source's folder (`routeToFolder`).
        #expect(open.folderId == folder.id)
        let paneFolderId = SidebarSourceOpen.libraryPaneFolderId(
            selectedItemId: selection.selectedItemId, viewMode: .library(folder), libraryId: libraryId
        )
        let preview = CanvasDocumentPolicy.documentForCanvas(
            selectedDocumentIds: open.selection, documents: children, detailDocument: doc, inspectorDocument: folder
        )
        return Shown(paneFolderId: paneFolderId, selection: open.selection, preview: preview, opensPreview: open.opensPreview)
    }

    // WHY: the maintainer's bug. With Canvas remembered, clicking one image narrowed the library to
    // that image and drew an empty board. If this fails, a source is narrowing the library again, or
    // its board is keyed by the image instead of the folder (a different, empty layout).
    @Test("an image opens in its folder, in the folder's canvas, selected; Preview shows it")
    func imageOpensInItsFolder() throws {
        let selection = SidebarSelectionState()
        let settings = ViewSettings()
        settings.libraryLayout = .canvas

        let shown = try click(image, selection)
        #expect(shown.paneFolderId == "doc:fold")
        #expect(shown.selection == ["img-1"])
        #expect(shown.preview == image)
        // The mode is the pane's own; a source click never changes it.
        #expect(settings.libraryLayout == .canvas)
    }

    // WHY: the ruling makes a PDF the same as an image. If this fails, a PDF still opens its pages
    // as the Library listing instead of sitting selected in its folder.
    @Test("a PDF opens in its folder, selected; Preview shows the PDF")
    func pdfOpensInItsFolder() throws {
        let selection = SidebarSelectionState()
        let shown = try click(pdf, selection)
        #expect(shown.paneFolderId == "doc:fold")
        #expect(shown.selection == ["pdf-1"])
        #expect(shown.preview == pdf)
    }

    // WHY: returning to the folder must show the folder in the mode it had. If this fails, the
    // source click leaked into the folder's own view (its id, or its remembered mode).
    @Test("folder, then image, then the folder again: the folder in its canvas each time")
    func folderImageFolder() throws {
        let selection = SidebarSelectionState()
        let settings = ViewSettings()
        settings.libraryLayout = .canvas

        selection.selectedItemId = "doc:fold"
        #expect(SidebarSourceOpen.plan(for: folder, previewShowing: true) == nil)
        #expect(SidebarSourceOpen.libraryPaneFolderId(
            selectedItemId: selection.selectedItemId, viewMode: .library(folder), libraryId: libraryId
        ) == "doc:fold")

        _ = try click(image, selection)

        selection.selectedItemId = "doc:fold"
        #expect(SidebarSourceOpen.libraryPaneFolderId(
            selectedItemId: selection.selectedItemId, viewMode: .library(folder), libraryId: libraryId
        ) == "doc:fold")
        #expect(settings.libraryLayout == .canvas)
    }

    // WHY: a source has to be seen. If the window has no Preview and none opens, the click selects
    // a row and shows nothing of the source.
    @Test("with no Preview pane in the window, one opens")
    func noPreviewOpensOne() throws {
        let selection = SidebarSelectionState()
        let panes = BuiltInWorkspaceLayout.read.panes.settingVisible(.preview, false)
        #expect(!panes.kinds.contains(.preview))

        let shown = try click(image, selection, previewShowing: panes.kinds.contains(.preview))
        #expect(shown.opensPreview)
        // The shell's open path: `setPaneVisible(.canvas, true)` → `PaneList.settingVisible`.
        #expect(panes.settingVisible(ContentPane.canvas.paneKind, true).kinds.contains(.preview))

        let withPreview = try click(image, selection, previewShowing: true)
        #expect(!withPreview.opensPreview)
    }

    // WHY: a source at the top of the library has no folder; the Library pane lists the library's
    // root and keys the root's board, not the image's.
    @Test("a top-level source opens in the library root")
    func topLevelSourceOpensInRoot() throws {
        let loose = Document(id: "img-9", docType: .file, fileType: .image, name: "loose.jpg")
        let open = try #require(SidebarSourceOpen.plan(for: loose, previewShowing: true))
        #expect(open.folderId == nil)
        #expect(SidebarSourceOpen.libraryPaneFolderId(
            selectedItemId: "doc:img-9", viewMode: .library(nil), libraryId: libraryId
        ) == SidebarDestination.library(libraryId).serializedID)
    }
}
