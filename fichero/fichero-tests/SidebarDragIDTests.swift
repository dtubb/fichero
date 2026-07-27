@testable import Fichero
import AppKit
import Foundation
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
