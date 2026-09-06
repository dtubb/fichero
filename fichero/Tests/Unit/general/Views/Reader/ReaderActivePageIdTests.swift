@testable import Fichero
import Foundation
import Testing

/// Scroll-by-page-id (#reader-page-id).
///
/// Daniel's live defect: picking a library-search hit in the Marshall corpus
/// showed the parent diary's FIRST page, not the selected image. Root cause:
/// those page nodes are manifest-imported with a null top-level `sequence`
/// (the ordinal lives only in `metadata`), so `readerActivePageNumber` returned
/// nil and the transcript never scrolled. A page's own id always names its
/// transcript `<article data-page-id>`, so scroll-by-id lands on the exact page
/// regardless of `sequence`. These pin the pure Swift side of that path.
@MainActor
struct ReaderActivePageIdTests {
    /// The whole point: a page whose top-level `sequence` is null. The ordinal
    /// path cannot identify it — it COLLAPSES to 1 (`max(1, sequence ?? 1)`),
    /// i.e. the parent's FIRST page, which is exactly the "shows the folder's
    /// first page, not the selected image" defect. The id path names the real
    /// page, so scroll-by-id lands it.
    @Test("a null-sequence page collapses to ordinal 1 but keeps its own id")
    func nullSequencePageCollapsesToOneButKeepsItsId() {
        let page = Document(
            id: "50421755",
            parentId: "diary-1925",
            docType: .page,
            name: "NCM_Diary_1925IMG_018_part_1",
            sequence: nil
        )
        // The ordinal stranded the reader on the parent's first page…
        #expect(ContentView.readerActivePageNumber(for: page) == 1)
        // …but the id path names the ACTUAL selected page.
        #expect(ContentView.readerActivePageId(for: page) == "50421755")
    }

    /// A virtual page cursor (an unprocessed PDF's synthetic `:vpage:` cursor)
    /// names no transcript article, so it must NOT drive scroll-by-id — it keeps
    /// the ordinal path, which its real `sequence` makes correct.
    @Test("a virtual page cursor yields no active page id")
    func virtualPageCursorYieldsNoId() {
        let cursor = Document.virtualPageCursor(pdfParentId: "pdf-1", pageIndex: 4)
        #expect(cursor.docType == .page)
        #expect(ContentView.readerActivePageId(for: cursor) == nil)
        // Its ordinal is real (pageIndex + 1), so the ordinal path still pages it.
        #expect(ContentView.readerActivePageNumber(for: cursor) == 5)
    }

    /// A page that DOES carry a sequence keeps both paths — the id path is
    /// additive, never a replacement.
    @Test("a sequenced page yields both an ordinal and an id")
    func sequencedPageYieldsBoth() {
        let page = Document(
            id: "page-3",
            parentId: "pdf-1",
            docType: .page,
            name: "Page 3",
            sequence: 3
        )
        #expect(ContentView.readerActivePageNumber(for: page) == 3)
        #expect(ContentView.readerActivePageId(for: page) == "page-3")
    }

    /// Only pages name a page; a folder or file must not, or the reader would
    /// try to scroll a container to itself.
    @Test("non-page documents yield no active page id")
    func nonPageYieldsNoId() {
        let folder = Document(id: "diary-1925", docType: .folder, name: "NCM_Diary_1925")
        let file = Document(id: "pdf-1", docType: .file, name: "Scan.pdf")
        #expect(ContentView.readerActivePageId(for: folder) == nil)
        #expect(ContentView.readerActivePageId(for: file) == nil)
        #expect(ContentView.readerActivePageId(for: nil) == nil)
    }

    /// The emitted JS calls the injected function with the page id, and is a
    /// no-op-safe optional call (`?.`) so it never throws on a DOM that has not
    /// installed the helper yet.
    @Test("scrollByIdScript calls the injected function with the page id + ordinal fallback")
    func scrollByIdScriptShape() {
        let script = ReaderActivePageSync.scrollByIdScript(pageId: "50421755", fallbackPage: 7, fallbackCount: 40)
        #expect(script.contains("ficheroScrollToPageId?."))
        #expect(script.contains("'50421755'"))
        // The ordinal fallback rides along for legacy no-data-page-id transcripts.
        #expect(script.contains("7"))
        #expect(script.contains("40"))
    }

    @Test("scrollByIdScript emits null for an absent ordinal fallback")
    func scrollByIdScriptNilFallback() {
        let script = ReaderActivePageSync.scrollByIdScript(pageId: "p1", fallbackPage: nil, fallbackCount: nil)
        #expect(script.contains("'p1', null, null"))
    }
}
