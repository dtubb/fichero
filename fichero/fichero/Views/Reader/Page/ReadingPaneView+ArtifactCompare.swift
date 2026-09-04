import SwiftUI
import WebKit

// MARK: - The reader's COMPARE lens (Daniel, 2026-09-04)
//
// "A 2–5-way diff of artifact results — three transcription reviews side by
// side with the differences highlighted, HTML-style. The reader is WebKit, so
// an HTML diff renderer is at home there."
//
// The comparison is picked from the SAME by-run submenu that picks a single
// artifact: point the pane at one artifact, then choose what to compare it
// with. The one you were already reading is the BASELINE, which is why the
// page names it — a diff whose reference is implicit is a diff you can read
// backwards without noticing.
//
// The diff itself lives in `ReaderArtifactDiff` and is pure; this file is the
// pane's state, the fetch, and the WebKit host.

/// The reader's host for CLIENT-rendered HTML: a plain string in a web view,
/// no engine route. The comparison below is one such rendering; the CSV table
/// (`ReaderCSVTable`) is the other. Both are computed from bytes the client
/// already holds, so neither needs a round trip to draw.
struct ReaderHTMLPane {
    let html: String

    func makeWebView() -> WKWebView {
        let configuration = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: configuration)
        // Nothing here navigates: the page is a rendering of two texts, and a
        // link inside a transcription must not take the reader to the web.
        webView.navigationDelegate = nil
        return webView
    }
}

#if os(macOS)
extension ReaderHTMLPane: NSViewRepresentable {
    func makeNSView(context: Context) -> WKWebView { makeWebView() }

    func updateNSView(_ webView: WKWebView, context: Context) {
        guard context.coordinator.lastHTML != html else { return }
        context.coordinator.lastHTML = html
        webView.loadHTMLString(html, baseURL: nil)
    }

    func makeCoordinator() -> ReaderHTMLPaneCoordinator { ReaderHTMLPaneCoordinator() }
}
#else
extension ReaderHTMLPane: UIViewRepresentable {
    func makeUIView(context: Context) -> WKWebView { makeWebView() }

    func updateUIView(_ webView: WKWebView, context: Context) {
        guard context.coordinator.lastHTML != html else { return }
        context.coordinator.lastHTML = html
        webView.loadHTMLString(html, baseURL: nil)
    }

    func makeCoordinator() -> ReaderHTMLPaneCoordinator { ReaderHTMLPaneCoordinator() }
}
#endif

/// Remembers the HTML already loaded, so an unrelated re-render does not
/// reload the web view and throw away the reader's scroll position.
final class ReaderHTMLPaneCoordinator {
    var lastHTML: String?
}

extension ReadingPaneView {

    /// Whether a comparison is on screen. The compare lens outranks the single
    /// artifact lens, the representation switcher and the live content — it is
    /// the most specific thing the user asked for.
    var isComparingArtifacts: Bool { artifactCompareIds.count >= 2 }

    /// The comparison surface: the rendered diff, an honest error, or the
    /// wait. Never an empty page pretending to be a comparison.
    @ViewBuilder
    var artifactCompareContent: some View {
        if let artifactCompareError {
            ContentUnavailableView(
                "Couldn't compare these artifacts",
                systemImage: "exclamationmark.triangle",
                description: Text(artifactCompareError)
            )
        } else if artifactCompareColumns.count >= 2 {
            ReaderHTMLPane(html: ReaderArtifactDiff.html(columns: artifactCompareColumns))
        } else {
            ProgressView()
                .controlSize(.small)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    /// The rows the "Compare with" submenu offers: every artifact of the
    /// document except the ones already in the comparison. Flat and by-run
    /// ordered, because it is the same list the Showing menu just showed.
    var artifactCompareCandidates: [ReaderArtifactLens] {
        ReaderArtifactMenu.flattened(artifactLensGroups)
            .filter { !artifactCompareIds.contains($0.artifactId) }
    }

    /// Start (or widen) a comparison. The artifact the pane is already reading
    /// is the baseline; each pick adds a column, up to five — beyond that the
    /// columns are too narrow to read, which is not a comparison.
    func compareArtifact(with choice: ReaderArtifactLens) {
        var ids = artifactCompareIds
        if ids.isEmpty, let artifactLens { ids = [artifactLens.artifactId] }
        guard !ids.contains(choice.artifactId), ids.count < Self.maxCompareColumns else { return }
        ids.append(choice.artifactId)
        artifactCompareIds = ids
    }

    func stopComparingArtifacts() {
        artifactCompareIds = []
        artifactCompareColumns = []
        artifactCompareError = nil
    }

    /// Five columns is Daniel's own ceiling ("2–5-way"), and it is also where
    /// the page stops being readable.
    static var maxCompareColumns: Int { 5 }

    /// Fetch the FULL text of every artifact in the comparison. List payloads
    /// carry truncated content, and a diff of two truncations is a diff of the
    /// truncation, so this always asks for the whole artifact.
    func loadArtifactComparison() async {
        artifactCompareError = nil
        artifactCompareColumns = []
        guard artifactCompareIds.count >= 2 else { return }
        let library = LibraryManager.shared
            .getLibrary(id: LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId)
        guard let service = paneArtifactService ?? library?.artifactService else {
            artifactCompareError = "This window has no library to read artifacts from."
            return
        }
        // `uniquingKeysWith`, not `uniqueKeysWithValues`: the latter TRAPS on a
        // duplicate key, and a menu label map is not worth a crash if the
        // grouping ever lists an artifact twice.
        let labels = Dictionary(
            ReaderArtifactMenu.flattened(artifactLensGroups).map { ($0.artifactId, $0.label) },
            uniquingKeysWith: { first, _ in first }
        )
        var columns: [ReaderArtifactDiff.Column] = []
        for id in artifactCompareIds {
            do {
                let artifact = try await service.getArtifact(id: id)
                let content = artifact.content ?? ""
                guard !content.isEmpty else {
                    // An artifact with no text cannot be compared, and
                    // comparing against an empty string would report the whole
                    // document as deleted — a confident lie.
                    artifactCompareError = "\(labels[id] ?? "One of these artifacts") has no text to compare."
                    return
                }
                columns.append(
                    ReaderArtifactDiff.Column(title: labels[id] ?? "Artifact", text: content)
                )
            } catch {
                artifactCompareError = error.localizedDescription
                return
            }
        }
        artifactCompareColumns = columns
    }

    /// Render a `.csv` document as a table, or leave `nil` so the ordinary
    /// reader shows the text.
    ///
    /// The document row the grid carries may not include `page_content` — the
    /// list payload is deliberately lean — so this asks for the full document
    /// rather than concluding "no text" from a lean row. Failure is silent by
    /// design: the fallback IS the ordinary reader, which shows the same
    /// bytes, so there is nothing the user needs to be told.
    func loadReaderCSVTable() async {
        readerCSVHTML = nil
        guard let doc = effectiveDocument, doc.fileType == .csv else { return }
        if let inline = doc.pageContent, !inline.isEmpty {
            readerCSVHTML = ReaderCSVTable.html(inline, title: DocumentTitle.displayName(for: doc))
            return
        }
        guard let full = try? await documentStore.documentService.getDocument(doc.id),
              let text = full.pageContent, !text.isEmpty,
              // The document may have changed under a slow fetch.
              full.id == effectiveDocument?.id
        else { return }
        readerCSVHTML = ReaderCSVTable.html(text, title: DocumentTitle.displayName(for: full))
    }
}
