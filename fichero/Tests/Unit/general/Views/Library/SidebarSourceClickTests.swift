@testable import Fichero
import Foundation
import Testing

/// #6657: one click on a sidebar image is one selection; Show Image is remembered on the source.
@MainActor
struct SidebarSourceClickTests {
    private let folder = Document(id: "fold", docType: .folder, name: "Letters")
    private let other = Document(id: "other", docType: .folder, name: "Diaries")
    private let image = Document(id: "img-1", parentId: "fold", docType: .file, fileType: .image, name: "0970.jpg")
    private let image2 = Document(id: "img-2", parentId: "fold", docType: .file, fileType: .image, name: "0971.jpg")

    // WHY: the click paid a whole folder reload. If this fails, a click on an image in the folder the list already shows
    // writes the container again, or selects the folder before the image.
    @Test("a click on an image in the shown folder is one selection change and no reload")
    func sameFolderOneSelect() throws {
        let open = try #require(SidebarSourceOpen.plan(for: image, previewShowing: true))
        #expect(SidebarSourceOpen.changes(for: open, viewMode: .library(folder)) == [.select(["img-1"])])
    }

    @Test("a click on an image in another folder loads that folder once, already selected on the image")
    func otherFolderOneLoad() throws {
        let open = try #require(SidebarSourceOpen.plan(for: image2, previewShowing: true))
        let changes = SidebarSourceOpen.changes(for: open, viewMode: .library(other))
        #expect(changes == [.openFolder("fold", selecting: ["img-2"])])
    }

    @Test("the click's selection is the image itself; a folder click selects nothing")
    func selectionOnClick() {
        #expect(SidebarSourceOpen.selectionOnClick(image) == ["img-1"])
        #expect(SidebarSourceOpen.selectionOnClick(folder).isEmpty)
        #expect(SidebarSourceOpen.selectionOnClick(nil).isEmpty)
    }

    // WHY: Show Image kept turning itself off. If this fails, the value is not read from the source, or the
    // workspace's value outranks the person's choice on the source.
    @Test("Show Image: toggled on, away to another image and back, is still on")
    func showImageSurvivesNavigation() {
        var docs: [Document] = [image, image2]
        func stored(_ index: Int) -> Bool? { SourceViewSettings.showImage(in: docs[index].metadata) }
        #expect(stored(0) == nil)
        let payload = SourceViewSettings.metadata(settingShowImage: true, in: docs[0].metadata)
        #expect(payload[SourceViewSettings.showImageKey] as? Bool == true)
        docs[0].metadata = payload.mapValues { AnyCodable($0) }
        // Arriving at the other image reads ITS value (none: the workspace) and writes nothing.
        #expect(SourceViewSettings.startValue(stored: stored(1), workspace: false, fallback: true) == false)
        #expect(stored(1) == nil)
        // Back on the first: the source's own choice wins over the workspace's.
        #expect(SourceViewSettings.startValue(stored: stored(0), workspace: false, fallback: false) == true)
    }

    @Test("the toggle keeps the source's other metadata")
    func toggleKeepsOtherKeys() {
        let payload = SourceViewSettings.metadata(settingShowImage: false, in: ["note": AnyCodable("x")])
        #expect(payload["note"] as? String == "x")
        #expect(payload[SourceViewSettings.showImageKey] as? Bool == false)
    }
}
