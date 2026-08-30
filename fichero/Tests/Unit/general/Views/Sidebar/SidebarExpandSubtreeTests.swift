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

import FicheroAPIClient
import Foundation
import SwiftUI
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

/// Option-click collapse-all (#48, Daniel 2026-08-10): closing an open
/// chevron with ⌥ held must also close every descendant, from the CACHE
/// only — no network — and must not touch unrelated expanded rows.
@MainActor
struct SidebarCollapseSubtreeTests {

    private static func makeStore() -> DocumentStore {
        let client = FicheroClient(
            baseURL: URL(string: "https://test.fichero")!,
            libraryPath: "/tmp/test.fichero",
            session: URLSession(configuration: .ephemeral)
        )
        return DocumentStore(apiClient: APIClient(client: client))
    }

    @Test("Collapse removes the folder and every cached descendant, nothing else")
    func collapseRemovesWholeSubtree() {
        let store = Self.makeStore()
        let root = Document(id: "r", docType: .folder, name: "Inbox", childCount: 2)
        let child = Document(id: "c", docType: .folder, name: "Letters", childCount: 1)
        let grandchild = Document(id: "g", docType: .file, fileType: .pdf, name: "Diary.pdf", childCount: 3)
        store.childrenCache = ["r": [child], "c": [grandchild]]

        var expanded: Set<String> = ["doc:r", "doc:c", "doc:g", "doc:unrelated"]
        let binding = Binding(get: { expanded }, set: { expanded = $0 })
        sidebarCollapseSubtree(root, store: store, expandedItems: binding)

        #expect(expanded == ["doc:unrelated"])
    }

    @Test("An uncached subtree collapses just the clicked row — cache-only walk")
    func uncachedSubtreeCollapsesRowOnly() {
        let store = Self.makeStore()
        let root = Document(id: "r", docType: .folder, name: "Inbox", childCount: 5)

        var expanded: Set<String> = ["doc:r"]
        let binding = Binding(get: { expanded }, set: { expanded = $0 })
        sidebarCollapseSubtree(root, store: store, expandedItems: binding)

        #expect(expanded.isEmpty)
    }
}
