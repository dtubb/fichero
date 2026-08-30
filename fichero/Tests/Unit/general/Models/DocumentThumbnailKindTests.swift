@testable import Fichero
import Foundation
import Testing

// Tests for the shared thumbnail-well classifier (#4202). The table's name
// cell, Mail-style list rows, and the prefetch window all branch on this one
// function, so a wrong answer either shows the wrong art or leaves a document
// fetching its image one row at a time on scroll.
//
// DocumentThumbnailKind lives at file scope rather than as a static on the
// `DocumentThumbnail` view precisely so this suite can call it: a static on a
// `View` inherits MainActor under the macOS 26 SDK, and Swift Testing calling
// it off-main SIGTRAPs the whole test process.
@Suite("DocumentThumbnailKind — shared thumbnail well branches (#4202)")
struct DocumentThumbnailKindTests {

    private func makeDoc(
        docType: DocType = .file,
        fileType: FileType? = nil,
        pageContent: String? = nil
    ) -> Document {
        Document(docType: docType, fileType: fileType, name: "doc", pageContent: pageContent)
    }

    @Test("Folders draw a symbol, never a storage fetch")
    func folderIsSymbol() {
        let kind = DocumentThumbnailKind.forDocument(makeDoc(docType: .folder))
        #expect(kind == .folder)
        #expect(kind.fetchesStorageThumbnail == false)
    }

    @Test("A folder carrying page content is still a folder")
    func folderWinsOverTextPreview() {
        let kind = DocumentThumbnailKind.forDocument(
            makeDoc(docType: .folder, pageContent: "some text")
        )
        #expect(kind == .folder)
    }

    // A mirror is a `.file` with no fileType: it used to fall through to a
    // storage fetch that returns nothing (EMPTY well) — which is why the list
    // row grew a second inline glyph that doubled folders' icons (2026-08-09).
    @Test("Workflow mirrors draw their symbol, never an empty storage well")
    func workflowMirrorIsSymbol() {
        let mirror = Document(docType: .file, name: "flow", prototypeKey: "workflow")
        let kind = DocumentThumbnailKind.forDocument(mirror)
        #expect(kind == .folder)
        #expect(kind.fetchesStorageThumbnail == false)
    }

    @Test("Images load from storage")
    func imageIsStorageImage() {
        let kind = DocumentThumbnailKind.forDocument(makeDoc(fileType: .image))
        #expect(kind == .storageImage)
        #expect(kind.fetchesStorageThumbnail)
    }

    @Test("An image with extracted text still shows the image, not a text preview")
    func imageWinsOverTextPreview() {
        let kind = DocumentThumbnailKind.forDocument(
            makeDoc(fileType: .image, pageContent: "ocr output")
        )
        #expect(kind == .storageImage)
    }

    @Test("Text documents with content render their preview and skip storage")
    func textDocumentIsPreview() {
        let kind = DocumentThumbnailKind.forDocument(
            makeDoc(fileType: .text, pageContent: "hello")
        )
        #expect(kind == .textPreview("hello"))
        #expect(kind.fetchesStorageThumbnail == false)
    }

    @Test("Empty page content is not a text preview")
    func emptyPageContentFallsThrough() {
        #expect(DocumentThumbnailKind.forDocument(makeDoc(fileType: .text, pageContent: "")) == .storageImage)
        #expect(DocumentThumbnailKind.forDocument(makeDoc(fileType: .text)) == .storageImage)
    }

    // #2052: a PDF page always shows its RENDERED page image, never a
    // rendering of the text it happens to carry.
    @Test("PDF pages render their page image despite carrying page content")
    func pdfPageIsStorageImage() {
        let page = DocumentThumbnailKind.forDocument(
            makeDoc(docType: .page, fileType: .pdf, pageContent: "extracted text")
        )
        #expect(page == .storageImage)
        let pdf = DocumentThumbnailKind.forDocument(
            makeDoc(fileType: .pdf, pageContent: "extracted text")
        )
        #expect(pdf == .storageImage)
    }

    // The prefetch window used to filter on `fileType == .image`, so pages and
    // PDFs — most of an archive — fetched one image per row on scroll (#4202).
    @Test("Prefetch covers every well that hits storage, not just images")
    func prefetchPredicateCoversPagesAndPDFs() {
        let documents = [
            makeDoc(docType: .folder),
            makeDoc(fileType: .image),
            makeDoc(docType: .page, fileType: .pdf, pageContent: "text"),
            makeDoc(fileType: .pdf),
            makeDoc(fileType: .text, pageContent: "note"),
            makeDoc(fileType: .word)
        ]
        let fetching = documents.filter { DocumentThumbnailKind.forDocument($0).fetchesStorageThumbnail }
        #expect(fetching.count == 4)
        #expect(fetching.allSatisfy { $0.docType != .folder })
    }
}
