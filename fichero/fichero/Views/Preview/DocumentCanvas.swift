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
    /// Extra normalized `[x,y,w,h]` boxes drawn over an image canvas — the
    /// entry-source highlight (preview-layers M1, #27). Display-only; the
    /// annotation region layer is unaffected.
    var highlightBoxes: [[Double]] = []
    /// Entry ladder (2026-08-23): open zoomed to this normalized rect, and
    /// route vertical steps to the host's containment ladder. Image canvases
    /// only; other content kinds ignore both.
    var focusRegion: [Double]?
    var onContainmentStep: ((Int) -> Bool)?

    enum Content {
        /// A backend storage display image, resolved by document id.
        case imageStorageDisplay(documentId: String)
        /// A backend-rendered PlatformImage (editor mode — may be nil while
        /// loading). `renditionId` names the rendition those pixels ARE when
        /// the preferred-first path fetched them (2026-08-24) — the preview
        /// then lands its flip index there without re-fetching.
        case imageRendered(image: PlatformImage?, documentId: String, renditionId: String? = nil)
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
                isEditing: isEditing,
                highlightBoxes: highlightBoxes,
                focusRegion: focusRegion,
                onContainmentStep: onContainmentStep
            )
        case .imageRendered(let nsImage, let docId, let renditionId):
            #if os(macOS)
            ZoomableImagePreview(
                documentId: docId,
                renderedImage: nsImage,
                renderedRenditionId: renditionId,
                onNavigateToDocument: onNavigateToDocument,
                isEditing: isEditing,
                highlightBoxes: highlightBoxes,
                focusRegion: focusRegion,
                onContainmentStep: onContainmentStep
            )
            #else
            // The iOS preview has no rendition-flip state (macOS-only today),
            // so it takes the rendered image without the rendition id.
            // swiftlint:disable:next redundant_discardable_let
            let _ = renditionId
            ZoomableImagePreview(
                documentId: docId,
                renderedImage: nsImage,
                onNavigateToDocument: onNavigateToDocument,
                isEditing: isEditing,
                highlightBoxes: highlightBoxes,
                focusRegion: focusRegion,
                onContainmentStep: onContainmentStep
            )
            #endif
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
