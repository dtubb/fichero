import PDFKit
import SwiftUI

/// One canonical canvas for image and PDF documents (#1402).
///
/// Replaces the three parallel zoom wrappers (ZoomableImageView, and the
/// since-removed ZoomableNSImageView) with a single entry point that reuses
/// the existing viewer stack:
///   • image storage      → StorageDisplayImageCanvas — full loupe/zoom/magnifier via HTTP
///   • image rendered     → ZoomableImagePreview(renderedImage:) — same stack, NSImage override
///   • PDF                → PDFPageWithToolbar
///
/// Plain preview, folder-page reading surface, and the editor all route here.
struct DocumentCanvas: View {
    let content: Content
    /// Fired when the user navigates to a different PDF page within the canvas.
    var onPageIndexChange: ((Int) -> Void)?
    /// Fired when the user steps to a sibling image in the folder image viewer.
    var onNavigateToDocument: ((String) -> Void)?
    /// Drives the image reader toolbar's edit button. `nil` greys the tool out
    /// (e.g. PDFs, which have no in-app editor). Threaded down to the image
    /// viewer so the edit control lives in the bottom reader toolbar instead of
    /// floating over the split control (#2421).
    var isEditing: Binding<Bool>?

    enum Content {
        /// A backend storage display image, resolved by document id.
        case imageStorageDisplay(documentId: String)
        /// A backend-rendered PlatformImage (editor mode — may be nil while loading).
        case imageRendered(image: PlatformImage?, documentId: String)
        /// A PDF document at a given page index.
        case pdf(documentId: String, pageIndex: Int)
        /// A text/Markdown representation (#2264) — e.g. a `convert` artifact.
        case markdown(text: String)
        /// A model-generated HTML rendition of the page (#4329), WebKit-rendered.
        case html(content: String)
        /// A model-generated SVG rendition of the page (#4329), WebKit-rendered.
        case svg(content: String)
    }

    /// The canvas content for a `conversion` artifact, routed by its stamped
    /// `target_format` (falling back to sniffing the markup) — so a rendition
    /// renders, never shows raw source (#4329).
    static func renditionContent(for artifact: Artifact) -> Content {
        let text = artifact.content ?? ""
        let format = (artifact.data?["target_format"]?.value as? String)
            ?? Self.sniffRenditionFormat(text)
        switch format {
        case "svg": return .svg(content: text)
        case "html": return .html(content: text)
        default: return .markdown(text: text)
        }
    }

    /// Best-effort format sniff for legacy conversion artifacts saved before
    /// the `target_format` stamp existed.
    static func sniffRenditionFormat(_ text: String) -> String {
        let head = text.trimmingCharacters(in: .whitespacesAndNewlines)
            .prefix(500)
            .lowercased()
        if head.contains("<svg") { return "svg" }
        if head.hasPrefix("<!doctype html") || head.contains("<html") { return "html" }
        return "markdown"
    }

    var body: some View {
        switch content {
        case .imageStorageDisplay(let docId):
            StorageDisplayImageCanvas(
                documentId: docId,
                onNavigateToDocument: onNavigateToDocument,
                isEditing: isEditing
            )
        case .imageRendered(let nsImage, let docId):
            ZoomableImagePreview(
                documentId: docId,
                renderedImage: nsImage,
                onNavigateToDocument: onNavigateToDocument,
                isEditing: isEditing
            )
        case .pdf(let documentId, let pageIndex):
            PDFPageWithToolbar(
                documentId: documentId,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange
            )
        case .markdown(let text):
            MarkdownCanvas(text: text)
        case .html(let content):
            WebContentCanvas(content: content, kind: .html)
        case .svg(let content):
            WebContentCanvas(content: content, kind: .svg)
        }
    }
}

/// Renders a Markdown representation as scrollable, selectable text (#2264).
///
/// Native rendering only — `AttributedString(markdown:)` for inline + block
/// syntax, falling back to the raw text if it doesn't parse. Heavier Markdown
/// (tables, images) can graduate to a web view later if a corpus needs it.
private struct MarkdownCanvas: View {
    let text: String

    private var attributed: AttributedString {
        (try? AttributedString(
            markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(text)
    }

    var body: some View {
        ScrollView {
            Text(attributed)
                .font(.body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                // Slim margin — more width for the text (Daniel, 2026-08-10).
                .padding(8)
        }
    }
}

private struct StorageDisplayImageCanvas: View {
    let documentId: String
    var onNavigateToDocument: ((String) -> Void)?
    var isEditing: Binding<Bool>?

    @Environment(StorageService.self) private var storageService
    @State private var image: PlatformImage?
    @State private var loadError: Error?
    /// Monotonic token: each load claims a generation and only the latest may
    /// publish. Guards the rapid page-flip race — an older page's slower fetch
    /// must not land AFTER the current page's image and replace it.
    @State private var loadGeneration = 0

    var body: some View {
        ZStack {
            if image != nil {
                DocumentCanvas(
                    content: .imageRendered(image: image, documentId: documentId),
                    onNavigateToDocument: onNavigateToDocument,
                    isEditing: isEditing
                )
            } else if let loadError {
                // Surface the failure with a message + Retry instead of a mute
                // icon (#3210), matching QuickLookDownloadView in the same pane
                // (raise-not-silent).
                ContentUnavailableView {
                    Label("Couldn't load image", systemImage: "photo")
                } description: {
                    Text(loadError.localizedDescription)
                } actions: {
                    Button("Retry") { Task { await loadImage() } }
                }
            } else {
                // ★ EVERY FRAME PERFECT (#3616): a sized skeleton filling the
                // reserved pane instead of a bare spinner, so the image/PDF page
                // cross-fades in (below) with no blank frame or pop.
                SkeletonPlaceholder()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // Cross-fade the branch swap as the loaded image replaces the skeleton.
        .animation(FrameAnimation.crossfade, value: image == nil)
        .task(id: documentId) { await loadImage() }
    }

    private func loadImage() async {
        // ★ EVERY FRAME PERFECT (#18/#113 page-turn flash): do NOT nil the
        // current image while the next page loads. Nil-first meant every page
        // flip dropped to the white skeleton for the fetch+decode window; the
        // previous page now stays up and the new one replaces it in place
        // (instant on a cache/prefetch hit). The skeleton still shows on
        // FIRST load, when there is nothing older to hold.
        loadGeneration += 1
        let claimed = loadGeneration
        loadError = nil
        do {
            let loaded = try await storageService.getDisplayPlatformImage(documentId)
            guard claimed == loadGeneration else { return }  // a newer flip won
            image = loaded
        } catch {
            guard claimed == loadGeneration else { return }
            // A failed load must not silently keep showing the WRONG page.
            image = nil
            loadError = error
        }
    }
}
