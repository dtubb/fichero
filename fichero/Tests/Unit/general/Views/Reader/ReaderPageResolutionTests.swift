@testable import Fichero
import Foundation
import Testing

/// Where a reader page click actually finds its page document (#4373 follow-up).
///
/// Daniel's live "Reader page click found no page document at index 0" was not
/// an off-by-one: the pages existed but lived in `childrenCache` (the library
/// selection was the folder containing the PDF), while resolution searched
/// only `currentDocuments` — the browsed container's children. These tests pin
/// the candidate set: cache + browsed container, scoped to the reader
/// document's own page parent, deduplicated.
@MainActor
struct ReaderPageResolutionTests {
    // MARK: - Where the pages actually live (the "index 0" click failure)

    /// Daniel's live error: "Reader page click found no page document at
    /// index 0". The pages were there — but in `childrenCache`, because the
    /// library selection was the FOLDER containing the PDF, so
    /// `currentDocuments` held the PDF and its siblings, not its pages.
    /// Resolution must read both, the same split #4357 fixed for per-page
    /// run progress.
    @Test("a click resolves pages that live only in the children cache")
    func clickResolvesPagesFromTheChildrenCache() {
        let pdf = Document(id: "pdf-1", docType: .file, name: "Scan.pdf")
        let pages = (1...3).map { (sequence: Int) in
            Document(
                id: "page-\(sequence)",
                parentId: "pdf-1",
                docType: .page,
                name: "Page \(sequence)",
                sequence: sequence
            )
        }
        // Folder is the browsed container: currentDocuments = the PDF + a sibling.
        let candidates = ContentView.readerPageCandidates(
            readerDocument: pdf,
            childrenCache: ["pdf-1": pages],
            currentDocuments: [pdf, Document(id: "sibling", docType: .file, name: "Other.pdf")]
        )
        let resolved = ContentView.pageDocument(atPDFIndex: 0, in: candidates)
        #expect(resolved?.id == "page-1")
        // And every other page of the same document resolves too.
        #expect(ContentView.pageDocument(atPDFIndex: 2, in: candidates)?.id == "page-3")
    }

    /// When the PDF itself is the browsed container the pages are in
    /// `currentDocuments` — the pre-fix working case must keep working.
    @Test("a click still resolves pages that live in currentDocuments")
    func clickResolvesPagesFromCurrentDocuments() {
        let pdf = Document(id: "pdf-1", docType: .file, name: "Scan.pdf")
        let pages = (1...2).map { (sequence: Int) in
            Document(
                id: "page-\(sequence)",
                parentId: "pdf-1",
                docType: .page,
                name: "Page \(sequence)",
                sequence: sequence
            )
        }
        let candidates = ContentView.readerPageCandidates(
            readerDocument: pdf,
            childrenCache: [:],
            currentDocuments: pages
        )
        #expect(ContentView.pageDocument(atPDFIndex: 1, in: candidates)?.id == "page-2")
    }

    /// Scoping: pages of some OTHER document sharing a sequence number must
    /// never satisfy a click on this one — substituting a different document's
    /// page is the same quiet wrong answer as clamping the page number.
    @Test("a click never resolves to another document's page")
    func clickNeverResolvesToAnotherDocumentsPage() {
        let pdf = Document(id: "pdf-1", docType: .file, name: "Scan.pdf")
        let stranger = Document(
            id: "stranger-page-1",
            parentId: "other-pdf",
            docType: .page,
            name: "Page 1",
            sequence: 1
        )
        let candidates = ContentView.readerPageCandidates(
            readerDocument: pdf,
            childrenCache: [:],
            currentDocuments: [stranger]
        )
        #expect(ContentView.pageDocument(atPDFIndex: 0, in: candidates) == nil)
    }

    /// A page in both the cache and the browsed container appears once.
    @Test("candidates deduplicate a page present in both sources")
    func candidatesDeduplicate() {
        let pdf = Document(id: "pdf-1", docType: .file, name: "Scan.pdf")
        let page = Document(
            id: "page-1", parentId: "pdf-1", docType: .page, name: "Page 1", sequence: 1
        )
        let candidates = ContentView.readerPageCandidates(
            readerDocument: pdf,
            childrenCache: ["pdf-1": [page]],
            currentDocuments: [page]
        )
        #expect(candidates.count == 1)
    }

    /// A reader rooted at a page child scopes by that page's parent — the
    /// pages of the SAME document, not children of the page itself.
    @Test("a page-child reader document scopes candidates by its parent")
    func pageChildReaderDocumentScopesByParent() {
        let page2 = Document(
            id: "page-2", parentId: "pdf-1", docType: .page, name: "Page 2", sequence: 2
        )
        let siblings = (1...3).map { (sequence: Int) in
            Document(
                id: "page-\(sequence)",
                parentId: "pdf-1",
                docType: .page,
                name: "Page \(sequence)",
                sequence: sequence
            )
        }
        let candidates = ContentView.readerPageCandidates(
            readerDocument: page2,
            childrenCache: ["pdf-1": siblings],
            currentDocuments: []
        )
        #expect(ContentView.pageDocument(atPDFIndex: 0, in: candidates)?.id == "page-1")
    }

    /// No reader document → nothing to scope by → the legacy behavior
    /// (search the browsed container) is preserved rather than silently
    /// resolving nothing.
    @Test("without a reader document the browsed container is searched")
    func withoutAReaderDocumentTheBrowsedContainerIsSearched() {
        let page = Document(
            id: "page-1", parentId: "pdf-1", docType: .page, name: "Page 1", sequence: 1
        )
        let candidates = ContentView.readerPageCandidates(
            readerDocument: nil,
            childrenCache: [:],
            currentDocuments: [page]
        )
        #expect(ContentView.pageDocument(atPDFIndex: 0, in: candidates)?.id == "page-1")
    }

}

/// The page-turn prefetch set (#18): pages either side of a turn are warmed
/// so the next flip swaps in place instead of fetching through the
/// white-frame window.
@MainActor
struct ReaderAdjacentPagePrefetchTests {
    private func pages(_ count: Int) -> [Document] {
        (1...count).map { sequence in
            Document(
                id: "page-\(sequence)",
                parentId: "pdf-1",
                docType: .page,
                name: "Page \(sequence)",
                sequence: sequence
            )
        }
    }

    @Test("a mid-document turn prefetches ±1 then ±2, nearest first")
    func midDocumentTurnPrefetchesNeighbors() {
        let ids = ContentView.adjacentPageIds(around: 4, in: pages(10))
        #expect(ids == ["page-4", "page-6", "page-3", "page-7"])
    }

    @Test("the first page prefetches only forward")
    func firstPagePrefetchesOnlyForward() {
        let ids = ContentView.adjacentPageIds(around: 0, in: pages(5))
        #expect(ids == ["page-2", "page-3"])
    }

    @Test("the last page prefetches only backward")
    func lastPagePrefetchesOnlyBackward() {
        let ids = ContentView.adjacentPageIds(around: 4, in: pages(5))
        #expect(ids == ["page-4", "page-3"])
    }

    @Test("no page children means nothing to prefetch")
    func noPagesMeansNoPrefetch() {
        #expect(ContentView.adjacentPageIds(around: 0, in: []).isEmpty)
    }
}
