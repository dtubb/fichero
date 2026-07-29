@testable import Fichero
import Foundation
import Testing

/// #4228 — `sidebarTreeSignature` runs on EVERY `DocumentStore` mutation,
/// including the status polls whose whole purpose is to be cheaply rejected.
/// It used to `.sorted(by: id)` the entire document list first — a full array
/// copy plus an O(N log N) sort — only to get order-independence out of a
/// dictionary-backed collection. XOR-combining per-row hashes gives the same
/// order-independence in one pass.
///
/// These tests pin the contract the signature depends on: the row hash sees
/// exactly the tree-shaping fields, and nothing else.
struct SidebarTreeRowHashTests {

    private func doc(
        id: String = "doc-1",
        parentId: String? = nil,
        name: String = "Doc",
        sortOrder: Int = 0,
        sequence: Int? = nil,
        docType: DocType = .file,
        fileType: FileType? = nil,
        status: Status = .pending,
        pageContent: String? = nil,
        structure: [DocumentStructureNode] = []
    ) -> Document {
        Document(
            id: id,
            parentId: parentId,
            docType: docType,
            fileType: fileType,
            name: name,
            sequence: sequence,
            status: status,
            pageContent: pageContent,
            structure: structure,
            sortOrder: sortOrder
        )
    }

    private func node(id: String, start: Int = 1, end: Int = 2) -> DocumentStructureNode {
        DocumentStructureNode(
            id: id,
            title: "Chapter",
            kind: "chapter",
            level: 1,
            pageRange: .init(start: start, end: end),
            basis: nil,
            confidence: nil,
            sourcePageLabel: nil,
            children: []
        )
    }

    // MARK: - Fields that DO shape the tree

    @Test("identical documents hash identically")
    func stableForEqualDocuments() {
        #expect(sidebarTreeRowHash(doc()) == sidebarTreeRowHash(doc()))
    }

    @Test("a rename changes the hash")
    func nameMatters() {
        #expect(sidebarTreeRowHash(doc(name: "A")) != sidebarTreeRowHash(doc(name: "B")))
    }

    @Test("a move changes the hash")
    func parentMatters() {
        #expect(sidebarTreeRowHash(doc(parentId: nil)) != sidebarTreeRowHash(doc(parentId: "folder")))
    }

    @Test("a reorder changes the hash")
    func sortOrderMatters() {
        #expect(sidebarTreeRowHash(doc(sortOrder: 0)) != sidebarTreeRowHash(doc(sortOrder: 3)))
    }

    @Test("page sequence changes the hash")
    func sequenceMatters() {
        #expect(sidebarTreeRowHash(doc(sequence: nil)) != sidebarTreeRowHash(doc(sequence: 4)))
    }

    @Test("doc type and file type change the hash")
    func typesMatter() {
        #expect(sidebarTreeRowHash(doc(docType: .file)) != sidebarTreeRowHash(doc(docType: .folder)))
        #expect(sidebarTreeRowHash(doc(fileType: nil)) != sidebarTreeRowHash(doc(fileType: .pdf)))
    }

    /// Structure drives the PDF outline rows, so a re-parse that keeps the same
    /// count must still be seen.
    @Test("a re-parse with the same node count changes the hash")
    func structureIdsMatter() {
        let before = doc(structure: [node(id: "n1")])
        let after = doc(structure: [node(id: "n2")])
        #expect(sidebarTreeRowHash(before) != sidebarTreeRowHash(after))
    }

    // MARK: - Fields that deliberately do NOT

    /// The reason the signature exists: a processing-status poll must not
    /// rebuild the whole tree. The sidebar never renders status.
    @Test("processing status does not change the hash")
    func statusIsIgnored() {
        #expect(sidebarTreeRowHash(doc(status: .pending)) == sidebarTreeRowHash(doc(status: .completed)))
    }

    @Test("page content does not change the hash")
    func contentIsIgnored() {
        #expect(sidebarTreeRowHash(doc(pageContent: nil)) == sidebarTreeRowHash(doc(pageContent: "text")))
    }

    // MARK: - The order-independence the signature relies on

    /// `sidebarDocuments` is `collections + childrenCache.values`, and
    /// dictionary iteration order is unstable, so the same set of documents in
    /// two orders must produce the same signature — otherwise the sidebar
    /// rebuilds itself for no reason on every mutation.
    @Test("XOR-combining is order independent")
    func combineIsOrderIndependent() {
        let docs = (0..<8).map { doc(id: "d\($0)", name: "Doc \($0)") }
        func signature(_ list: [Document]) -> Int {
            list.reduce(0) { $0 ^ sidebarTreeRowHash($1) }
        }
        #expect(signature(docs) == signature(docs.reversed()))
        #expect(signature(docs) == signature(docs.shuffled()))
    }

    /// Rows cannot cancel each other out, because `id` is unique and is part of
    /// every row hash — the property XOR-combining depends on.
    @Test("distinct documents do not cancel out")
    func distinctRowsDoNotCancel() {
        let first = doc(id: "a", name: "Same")
        let second = doc(id: "b", name: "Same")
        #expect(sidebarTreeRowHash(first) != sidebarTreeRowHash(second))
        #expect((sidebarTreeRowHash(first) ^ sidebarTreeRowHash(second)) != 0)
    }

    @Test("adding a document changes the signature")
    func signatureSeesAnInsertion() {
        let base = [doc(id: "a"), doc(id: "b")]
        let grown = base + [doc(id: "c")]
        func signature(_ list: [Document]) -> Int {
            list.reduce(0) { $0 ^ sidebarTreeRowHash($1) }
        }
        #expect(signature(base) != signature(grown))
    }
}
