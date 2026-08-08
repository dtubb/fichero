//
//  SidebarExpandSubtreeTests.swift
//  FicheroTests
//
//  Option-click expand-all (#3355 follow-up, Daniel 2026-08-08): the walk
//  must descend into EVERY container with children — folders and
//  page-bearing documents (PDFs) — not folders alone, or PDF pages stay
//  unloaded until each PDF's own chevron fires even though every page row
//  already sits in the database.
//

import Foundation
import Testing
@testable import Fichero

struct SidebarExpandSubtreeTests {

    @Test("Folders are always descended, even before childCount arrives")
    func foldersAlwaysDescend() {
        let emptyCountFolder = Document(id: "f1", docType: .folder, name: "Letters", childCount: 0)
        #expect(sidebarSubtreeShouldDescend(into: emptyCountFolder))
    }

    @Test("A PDF with page children is descended — its pages are already in the DB")
    func pdfWithPagesDescends() {
        let pdf = Document(
            id: "d1", docType: .file, fileType: .pdf, name: "Diary.pdf", childCount: 10
        )
        #expect(sidebarSubtreeShouldDescend(into: pdf))
    }

    @Test("A childless leaf is not descended — nothing to fetch")
    func childlessLeafDoesNotDescend() {
        let image = Document(
            id: "d2", docType: .file, fileType: .image, name: "scan.tif", childCount: 0
        )
        #expect(!sidebarSubtreeShouldDescend(into: image))
    }
}
