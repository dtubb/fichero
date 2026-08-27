//
//  SidebarPageClickRoutingTests.swift
//  FicheroTests
//
//  Pins the 2026-08-08 sidebar page-click fix: clicking a PAGE row in the
//  sidebar previewed the FIRST page of the PDF, because the "single file in
//  gallery" branch never touched the reader state — the canvas kept the old
//  `detailDocument` (the PDF itself) and `pdfPageIndex(for:)` returns 0 for
//  anything that isn't a page. The fix moves the page-focus cursor (the same
//  #1463 seam reader scroll/click uses) and re-roots `detailDocument` only
//  when the page belongs to a different document than the one on canvas.
//

@testable import Fichero
import Foundation
import Testing

struct SidebarPageClickRoutingTests {

    private func page(_ id: String, parent: String?, sequence: Int? = nil) -> Document {
        Document(id: id, parentId: parent, docType: .page, name: id, sequence: sequence)
    }

    private func pdf(_ id: String) -> Document {
        Document(id: id, docType: .file, fileType: .pdf, name: id)
    }

    @Test("a page resolves its parent PDF via the metadata stamp, then the tree parent")
    func parentResolution() {
        var stamped = page("p1", parent: "tree-parent")
        stamped.metadata["pdf_parent_id"] = AnyCodable("stamped-parent")
        #expect(sidebarPageParentPDFId(for: stamped) == "stamped-parent")
        #expect(sidebarPageParentPDFId(for: page("p2", parent: "tree-parent")) == "tree-parent")
        #expect(sidebarPageParentPDFId(for: page("p3", parent: nil)) == nil)
    }

    @Test("the canvas root id resolves for both shapes detailDocument takes")
    func canvasRootResolution() {
        #expect(sidebarDetailPDFId(for: pdf("book")) == "book")
        #expect(sidebarDetailPDFId(for: page("p1", parent: "book")) == "book")
        #expect(sidebarDetailPDFId(for: nil) == nil)
        // A non-PDF, non-page detail document roots no PDF canvas.
        #expect(sidebarDetailPDFId(for: Document(id: "img", docType: .file, fileType: .image, name: "img")) == nil)
    }

    @Test("clicking a page of the SAME pdf must not re-root the canvas")
    func samePDFKeepsRoot() {
        // The #1463 contract: within one PDF, only the page-focus cursor moves.
        let detail = pdf("book")
        let clicked = page("p2", parent: "book", sequence: 2)
        #expect(sidebarPageParentPDFId(for: clicked) == sidebarDetailPDFId(for: detail))
    }

    @Test("clicking a page of a DIFFERENT pdf re-roots the canvas")
    func differentPDFReroots() {
        let detail = pdf("book")
        let clicked = page("x1", parent: "other-book", sequence: 1)
        #expect(sidebarPageParentPDFId(for: clicked) != sidebarDetailPDFId(for: detail))
    }
}
