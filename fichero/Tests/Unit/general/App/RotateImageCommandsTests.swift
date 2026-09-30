@testable import Fichero
import Testing

/// #5304: ⌘R / ⌘L rotate the selected images anywhere (library, Preview, canvas), as Apple Preview
/// does. What breaks without these: a rotate that reaches a folder or a PDF page (which have no image
/// chain to edit), or that ignores the card chosen on a folder's canvas.
@Suite("Rotate the selected images (#5304)")
struct RotateImageCommandsTests {
    private let photo = Document(id: "img-1", docType: .file, fileType: .image, name: "0970.jpg")
    private let photo2 = Document(id: "img-2", docType: .file, fileType: .image, name: "0971.jpg")
    private let folder = Document(id: "fold", docType: .folder, name: "Test")
    private let pdf = Document(id: "pdf-1", docType: .file, fileType: .pdf, name: "deed.pdf")

    private func lookUp(_ id: String) -> Document? {
        [photo, photo2, folder, pdf].first { $0.id == id }
    }

    @Test("only the selected images rotate; folders and PDFs are left alone")
    func onlyImages() {
        let ids = rotatableImageIds(selection: ["img-2", "fold", "pdf-1", "img-1"], canvasFocus: nil, lookUp: lookUp)
        #expect(ids == ["img-1", "img-2"])
    }

    @Test("the card chosen on a folder's canvas is what rotates, not the selected folder")
    func canvasFocusWins() {
        let ids = rotatableImageIds(selection: ["fold"], canvasFocus: photo, lookUp: lookUp)
        #expect(ids == ["img-1"])
    }

    @Test("nothing rotatable selected: the menu items are off")
    func nothingToRotate() {
        #expect(rotatableImageIds(selection: ["fold"], canvasFocus: nil, lookUp: lookUp).isEmpty)
    }
}
