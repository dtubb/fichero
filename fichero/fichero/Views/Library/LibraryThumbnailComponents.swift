import FicheroAPIClient
import SwiftUI

//  Extracted for file_length (#5113) with that issue's checklist: path asserted free, cut
//  above the declaration's attributes and doc comment, no file-scope conditional-compilation
//  blocks and no file-scope `private` declarations to strand, imports copied verbatim.

// MARK: - Document Thumbnail

/// What a document's thumbnail well actually renders.
///
/// Deliberately a FILE-SCOPE enum, not a static on `DocumentThumbnail`: under
/// the macOS 26 SDK any static declared on a `View` inherits the type's
/// MainActor isolation, and Swift Testing calls such a helper off-main, which
/// SIGTRAPs the whole test process. Keeping the classifier off the View makes
/// it testable with no isolation at all. This placement is load-bearing.
enum DocumentThumbnailKind: Equatable {
    case folder
    case textPreview(String)
    case storageImage

    static func forDocument(_ document: Document) -> DocumentThumbnailKind {
        // Workflow mirrors join folders in the symbol branch (2026-08-09):
        // a mirror is a `.file` with no fileType, so it fell through to a
        // storage fetch that returns nothing and rendered an EMPTY well —
        // which is why MailStyleRow grew a second, inline glyph (#4516)
        // that then showed folders' icons TWICE. One glyph, in the well.
        if document.docType == .folder || document.isWorkflowNode { return .folder }
        if document.fileType == .image { return .storageImage }
        // Text-preview thumbnail (#625) is only for genuinely text documents
        // (JSON/plain text) with no page image. A PDF page ALWAYS shows its
        // rendered page image via the storage endpoint — never a rendering of
        // its extracted text, even though the page also carries
        // `pageContent`. (#2052)
        if document.docType != .page,
           document.fileType != .pdf,
           let preview = document.pageContent,
           !preview.isEmpty {
            return .textPreview(preview)
        }
        return .storageImage
    }

    /// Whether rendering this well hits the storage thumbnail endpoint — the
    /// prefetch window filters on it so PDFs and pages (most of an archive)
    /// are batched too, not just `.image` documents (#4202).
    var fetchesStorageThumbnail: Bool {
        self == .storageImage
    }
}

/// Shared thumbnail well for Mail-style list rows and the table's name cell
/// (#4202). Icon tiles keep their own larger tile view.
struct DocumentThumbnail: View {
    let document: Document
    let width: CGFloat
    let height: CGFloat
    /// List rows crop-to-fill — their 28×36 well already matches page aspect.
    /// The denser table well passes `.fit` so the image letterboxes rather
    /// than cropping, consistent with #4197's scale-to-fit decision.
    var contentMode: ContentMode = .fill
    var folderSymbolSize: CGFloat = 20

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(.windowBackgroundColor))

            switch DocumentThumbnailKind.forDocument(document) {
            case .folder:
                // The one symbol ladder the sidebar reads (#4516), lock-aware
                // (#4514): purple gear-badged treatment for read-only system
                // folders — previously an inline glyph in MailStyleRow, which
                // doubled real folders' icons.
                Image(systemName: document.displaySymbol())
                    .font(.system(size: folderSymbolSize))
                    .symbolVariant(document.docType == .folder ? .fill : .none)
                    .symbolRenderingMode(document.usesWorkflowTint ? .hierarchical : .monochrome)
                    .foregroundColor(document.usesWorkflowTint ? .purple : .accentColor)
            case .textPreview(let preview):
                TextPreviewThumbnail(text: preview)
                    .frame(width: width, height: height)
                    .clipped()
            case .storageImage:
                LibraryImageView(documentId: document.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: contentMode)
                    .frame(width: width, height: height)
                    .clipped()
            }
        }
        .frame(width: width, height: height)
        .clipShape(RoundedRectangle(cornerRadius: 4))
    }
}

// MARK: - Progress Cell

struct ProgressCell: View {
    let document: Document

    @Environment(DocumentStore.self) private var documentStore

    var body: some View {
        switch document.status {
        case .processing:
            // #4417: a container whose CHILDREN are busy now reads as
            // "Processing contents — 3 of 4 done" here too, not as "...".
            LibraryActivityIndicator(document: document, showsSummaryText: true)
        case .completed:
            HStack(spacing: 4) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
                    .font(.caption)
                Text("100%")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        case .failed:
            HStack(spacing: 4) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.red)
                    .font(.caption)
                Text("Failed")
                    .font(.caption)
                    .foregroundColor(.red)
            }
        case .pending:
            Text("Pending")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}
