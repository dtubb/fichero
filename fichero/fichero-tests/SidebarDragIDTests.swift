@testable import Fichero
import AppKit
import Foundation
import PDFKit
import Testing

/// #4123: dragging OUT of the sidebar delivers real content — a file copy /
/// RTF transcript — never the bare internal "doc:<uuid>" clipping. The
/// in-process id flavor stays for the move pipeline (#623/#711).
struct SidebarDragIDTests {
    private let libraryId = UUID()

    private func docItem(
        _ id: String, name: String, content: String? = nil, docType: DocType = .file
    ) -> SidebarItem {
        SidebarItem(
            id: "doc:\(id)",
            name: name,
            icon: "doc",
            category: .folder,
            itemType: .document(Document(
                id: id,
                docType: docType,
                name: name,
                pageContent: content
            )),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: docType == .folder
        )
    }

    @Test("document rows carry the export payload")
    func documentRowsExport() {
        let drag = SidebarDragID(item: docItem("d1", name: "Ledger.pdf", content: "transcript text"))
        #expect(drag.id == "doc:d1")
        #expect(drag.documentId == "d1")
        #expect(drag.libraryId == libraryId)
        #expect(drag.name == "Ledger.pdf")
        #expect(drag.exportsFile)
        #expect(drag.exportsText)
        #expect(drag.transcript == "transcript text")
    }

    @Test("folder rows stay in-process only")
    func folderRowsDoNotExport() {
        let drag = SidebarDragID(item: docItem("f1", name: "Books", docType: .folder))
        #expect(drag.id == "doc:f1")
        #expect(!drag.exportsFile)
        #expect(!drag.exportsText)
    }

    @Test("transcript-less documents export the file but no text")
    func noTranscriptNoTextExport() {
        let drag = SidebarDragID(item: docItem("d2", name: "scan.jpg"))
        #expect(drag.exportsFile)
        #expect(!drag.exportsText)
    }

    @Test("RTF export round-trips the transcript")
    func rtfRoundTrips() throws {
        let data = try SidebarDragID.transcriptRTFData("Cacao harvest notes")
        var attributes: NSDictionary?
        let decoded = NSAttributedString(rtf: data, documentAttributes: &attributes)
        #expect(decoded?.string == "Cacao harvest notes")
    }

    @Test("Content-Disposition filename parsing")
    func dispositionParsing() {
        #expect(SidebarDragID.filename(fromContentDisposition: "attachment; filename=\"a.pdf\"") == "a.pdf")
        #expect(SidebarDragID.filename(fromContentDisposition: "inline; filename=b.jpg") == "b.jpg")
        #expect(SidebarDragID.filename(fromContentDisposition: nil) == nil)
        #expect(SidebarDragID.filename(fromContentDisposition: "attachment") == nil)
        // No header-driven path traversal into the temp directory.
        #expect(SidebarDragID.filename(fromContentDisposition: "attachment; filename=\"../x.pdf\"") == "..-x.pdf")
    }

    @Test("page rows carry a 0-based PDF page index")
    func pageRowsCarryPageIndex() {
        var pageDoc = Document(id: "p3", docType: .page, name: "page 3", pageContent: "text")
        pageDoc.sequence = 3
        let item = SidebarItem(
            id: "doc:p3", name: "page 3", icon: "doc", category: .folder,
            itemType: .document(pageDoc), children: nil, progress: nil,
            showProgress: false, libraryId: libraryId, folderPath: "/",
            sortOrder: 0, isFolder: false
        )
        // sequence is 1-based; PDFKit indices are 0-based.
        #expect(SidebarDragID(item: item).pageIndex == 2)
        // Non-page rows never trim.
        #expect(SidebarDragID(item: docItem("d1", name: "Ledger.pdf")).pageIndex == nil)
    }

    @Test("single-page trim extracts just the requested page")
    func singlePageTrim() throws {
        // Build a 2-page PDF with PDFKit.
        let pdf = PDFDocument()
        for _ in 0..<2 {
            let page = PDFPage()
            pdf.insert(page, at: pdf.pageCount)
        }
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("drag-trim-\(UUID().uuidString).pdf")
        #expect(pdf.write(to: url))
        defer { try? FileManager.default.removeItem(at: url) }

        let trimmed = try #require(SidebarDragID.singlePagePDF(from: url, pageIndex: 1))
        defer { try? FileManager.default.removeItem(at: trimmed) }
        #expect(PDFDocument(url: trimmed)?.pageCount == 1)
        #expect(trimmed.lastPathComponent.hasSuffix("page 2.pdf"))

        // No pageIndex, single-page files, and non-PDFs all keep the original.
        #expect(SidebarDragID.singlePagePDF(from: url, pageIndex: nil) == nil)
        let txt = FileManager.default.temporaryDirectory
            .appendingPathComponent("drag-trim-\(UUID().uuidString).txt")
        try "not a pdf".write(to: txt, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: txt) }
        #expect(SidebarDragID.singlePagePDF(from: txt, pageIndex: 0) == nil)
    }

    @Test("plain-text markdown flavor is exported for editors")
    func plainTextFlavorExists() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("fichero/Views/Sidebar/ItemRow/SidebarItemRow.swift"),
            encoding: .utf8
        )
        #expect(source.contains("DataRepresentation(exportedContentType: .utf8PlainText)"))
    }

    @Test("in-process id flavor survives for the move pipeline")
    func ownProcessIdFlavorSurvives() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("fichero/Views/Sidebar/ItemRow/SidebarItemRow.swift"),
            encoding: .utf8
        )
        #expect(source.contains(".visibility(.ownProcess)"))
        // External-facing representations come FIRST so Finder/editors never
        // fall back to the internal id string.
        let fileIdx = source.range(of: "FileRepresentation(exportedContentType: .data)")!.lowerBound
        let idIdx = source.range(of: "ProxyRepresentation(exporting: \\.id)")!.lowerBound
        #expect(fileIdx < idIdx)
    }
}
