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
    /// The whole point: a page whose top-level `sequence` is null — the ordinal
    /// path gives up (nil), but the id path still names the page.
    @Test("a page with a null sequence still yields an active page id")
    func nullSequencePageStillHasAnId() {
        let page = Document(
            id: "50421755",
            parentId: "diary-1925",
            docType: .page,
            name: "NCM_Diary_1925IMG_018_part_1",
            sequence: nil
        )
        // The ordinal path cannot land this page…
        #expect(ContentView.readerActivePageNumber(for: page) == nil)
        // …but the id path can.
        #expect(ContentView.readerActivePageId(for: page) == "50421755")
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
    @Test("scrollByIdScript calls the injected function with the page id")
    func scrollByIdScriptShape() {
        let script = ReaderActivePageSync.scrollByIdScript(pageId: "50421755")
        #expect(script.contains("ficheroScrollToPageId?."))
        #expect(script.contains("50421755"))
    }
}
