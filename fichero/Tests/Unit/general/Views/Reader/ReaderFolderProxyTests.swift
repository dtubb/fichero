@testable import Fichero
import Foundation
import Testing

/// A selected folder reads as ITSELF in the reader (Daniel, 2026-09-05:
/// "reader doesn't seem to show contents of a folder if it's just folders …
/// it would say the name of the folder not page 1. Have a proxy icon").
///
/// The Page tab used to point its multi-page transcript at whatever was
/// selected; a folder-of-folders assembled nothing and the pane went blank.
/// `ReadingPaneView.folderProxy(for:)` is the pure seam that decides "this node
/// reads as a folder proxy" — a folder yields one, everything else yields nil
/// so the transcript path (the reader's whole point for pages) is untouched.
@MainActor
struct ReaderFolderProxyTests {
    @Test("a folder node yields a proxy naming the folder, not a child page")
    func folderYieldsProxy() {
        let folder = Document(
            id: "folder-1",
            docType: .folder,
            name: "1933",
            pageContent: "# Ledger 1933\n\nThe year's accounts."
        )
        let proxy = ReadingPaneView.folderProxy(for: folder)
        #expect(proxy != nil)
        // Names the folder — the reader's subject line stands in for "page 1".
        #expect(proxy?.name == "1933")
        #expect(proxy?.name.isEmpty == false)
        // Carries the folder's OWN ficha, so the proxy is not blank.
        #expect(proxy?.fichaContent == "# Ledger 1933\n\nThe year's accounts.")
        // A folder glyph — the proxy icon Daniel asked for.
        #expect(proxy?.icon.hasPrefix("folder") == true)
    }

    @Test("the proxy keys on the folder's OWN id (the artifact panel scope)")
    func proxyUsesTheFoldersOwnId() {
        let folder = Document(id: "folder-42", docType: .folder, name: "Diaries")
        // The artifact panel and every scoped fetch key on this id, so the
        // folder's catalogue artifact resolves for the folder and no descendant.
        #expect(ReadingPaneView.folderProxy(for: folder)?.documentId == "folder-42")
    }

    @Test("a folder with only whitespace ficha still proxies, with no content")
    func folderWithBlankFichaProxiesWithoutContent() {
        let folder = Document(
            id: "folder-2", docType: .folder, name: "Empty", pageContent: "   \n  "
        )
        let proxy = ReadingPaneView.folderProxy(for: folder)
        // Not blank — name + icon still stand in for the missing "page 1".
        #expect(proxy != nil)
        #expect(proxy?.name == "Empty")
        // Whitespace is not content: the proxy shows the folder, not an empty pane.
        #expect(proxy?.fichaContent == nil)
    }

    @Test("a folder with no ficha at all still proxies")
    func folderWithNoFichaProxies() {
        let folder = Document(id: "folder-3", docType: .folder, name: "Box 7")
        let proxy = ReadingPaneView.folderProxy(for: folder)
        #expect(proxy != nil)
        #expect(proxy?.fichaContent == nil)
    }

    // MARK: - The transcript path is preserved (never a child page in a folder)

    @Test("a PDF file is NOT a folder proxy — the transcript path stands")
    func pdfIsNotAProxy() {
        let pdf = Document(id: "pdf-1", docType: .file, fileType: .pdf, name: "Scan.pdf")
        #expect(ReadingPaneView.folderProxy(for: pdf) == nil)
    }

    @Test("a page is NOT a folder proxy — a page reads its own content")
    func pageIsNotAProxy() {
        let page = Document(
            id: "page-1", parentId: "pdf-1", docType: .page, name: "Page 1", sequence: 1
        )
        #expect(ReadingPaneView.folderProxy(for: page) == nil)
    }
}
