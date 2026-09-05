import SwiftUI

// MARK: - The reader's FOLDER PROXY (Daniel, 2026-09-05)
//
// "reader doesn't seem to show contents of a folder if it's just folders. We
// should do that. (it would say the name of the folder not page 1). Have a
// proxy icon. The top would show us the folder we're working on. I don't think
// it should show contents unless you zoom in."
//
// A folder is not a page and has no "page 1" to assemble. Pointing the Page
// tab's WebKit transcript at a folder-of-folders assembled nothing and the
// pane went blank. The rule the whole reader now obeys: a view shows the node
// you SELECTED, never silently substituting a descendant. So a selected folder
// reads as ITSELF — its name, a proxy icon, and its OWN ficha (`page_content`,
// which the engine now carries on the folder, not only as an artifact) — and
// the pane's breadcrumb head already names the folder you are working on.
//
// Descending into a child page is what shows page text; that is the "zoom in"
// Daniel means, and it happens through selection, not here.

/// The reader's rendering of a selected folder: the folder itself, as a proxy.
/// Pure and value-typed so the "a folder reads as itself" rule is testable
/// without a view.
struct ReaderFolderProxy: Equatable {
    /// The folder's OWN id — what the artifact panel and every scoped fetch key
    /// on, so the catalogue artifact resolves for this folder and no descendant.
    let documentId: String
    /// The folder's display name — the reader's subject line, in place of the
    /// "page 1" the transcript path would have shown.
    let name: String
    /// The folder's proxy glyph (its `displaySymbol` — a folder, or a locked
    /// folder for a system node).
    let icon: String
    /// The folder's own ficha (`page_content`), when it has one — nil when the
    /// folder carries no content of its own, in which case the proxy is name +
    /// icon alone (still not blank, and still not a child's page).
    let fichaContent: String?
}

extension ReadingPaneView {
    /// The folder proxy for a node, or nil when the node is NOT a folder — a
    /// page/file/PDF keeps the transcript path, whose multi-page assembly is the
    /// whole point of the reader. Static so tests call it without a view.
    static func folderProxy(for doc: Document) -> ReaderFolderProxy? {
        guard doc.docType == .folder else { return nil }
        let trimmed = doc.pageContent?.trimmingCharacters(in: .whitespacesAndNewlines)
        return ReaderFolderProxy(
            documentId: doc.id,
            name: DocumentTitle.displayName(for: doc),
            icon: doc.displaySymbol(),
            fichaContent: (trimmed?.isEmpty == false) ? doc.pageContent : nil
        )
    }

    func folderProxy(for doc: Document) -> ReaderFolderProxy? { Self.folderProxy(for: doc) }

    /// The folder-proxy reading of the Page tab: the folder's name beside its
    /// proxy icon, then its own ficha (via `MarkdownText`, the app's one
    /// Markdown renderer) when it has one. Never the assembled transcript of
    /// its descendants — that is the substitution this whole path removes.
    @ViewBuilder
    func folderProxyContent(_ proxy: ReaderFolderProxy) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    Image(systemName: proxy.icon)
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                    Text(proxy.name)
                        .font(.title2)
                        .fontWeight(.semibold)
                        .textSelection(.enabled)
                }
                if let ficha = proxy.fichaContent {
                    Divider()
                    MarkdownText(ficha)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.textBackgroundColor))
        .accessibilityIdentifier("readerFolderProxy")
    }
}
