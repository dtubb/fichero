import SwiftUI

// MARK: - Entry → source-page preview (preview-layers milestone 1, #27)

/// The preview for an EXTRACTED node (`node_kind == "entry"`): the SOURCE
/// page image with the entry's bounding box highlighted — never the entry's
/// text repeated (Daniel 2026-08-15: "we should see in preview the image …
/// with bbox of source part, and then the actual reader showing us the diary
/// entry"). The reader keeps showing the entry's own text; this pane answers
/// "where on the page did this come from".
struct EntrySourcePreview: View {
    let entry: Document
    var onNavigateToDocument: ((String) -> Void)?

    @Environment(DocumentStore.self) private var documentStore
    @State private var source: Document?
    @State private var loadFailed = false

    var body: some View {
        Group {
            if let source {
                DocumentCanvas(
                    content: .imageStorageDisplay(documentId: source.id),
                    onNavigateToDocument: onNavigateToDocument,
                    highlightBoxes: Self.highlight(for: entry, sourceMetadata: source.metadata)
                )
            } else if loadFailed {
                // The reference is broken (source deleted, cross-library) —
                // fall back to the entry's own text rather than a dead pane,
                // and say why.
                VStack(spacing: 0) {
                    Label("Source page unavailable", systemImage: "link.badge.plus")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                    Divider()
                    DocumentTextReader(document: entry, content: entry.pageContent ?? "")
                }
            } else {
                SkeletonPlaceholder()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: entry.id) {
            loadFailed = false
            guard let sourceId = Self.sourceDocumentId(of: entry) else {
                loadFailed = true
                return
            }
            source = try? await documentStore.documentService.getDocument(sourceId)
            if source == nil { loadFailed = true }
        }
    }

    /// The page this entry came from: the stamped provenance id first, the
    /// tree parent as fallback (older runs predate the stamp).
    static func sourceDocumentId(of entry: Document) -> String? {
        if let stamped = entry.metadata["source_document_id"]?.value as? String,
           !stamped.isEmpty {
            return stamped
        }
        return entry.parentId
    }

    /// Step 3 (bbox retirement, 2026-08-22): new extractions write ONLY the
    /// typed `region_in_parent` (already normalized — no page-size dependency,
    /// which is exactly why entries on pages with no recorded size now get
    /// regions at all). Pre-rename rows still carry pixel `bbox`; both render.
    static func highlight(
        for entry: Document,
        sourceMetadata: [String: AnyCodable]
    ) -> [[Double]] {
        if let region = entry.regionInParent, region.rect.count == 4,
           region.space ?? "normalized" == "normalized" {
            return [region.rect]
        }
        return normalizedHighlight(bbox: entry.bbox, sourceMetadata: sourceMetadata)
    }

    /// `Document.bbox` pixel ints `[x, y, w, h]` → the overlay's normalized
    /// rects, using the source page's stamped pixel dimensions. Missing or
    /// degenerate dimensions → no highlight (recorded honestly by the engine
    /// as `bbox_basis`), never a guessed box.
    static func normalizedHighlight(
        bbox: [Int]?,
        sourceMetadata: [String: AnyCodable]
    ) -> [[Double]] {
        guard let bbox, bbox.count == 4,
              let width = intValue(sourceMetadata["width"]?.value),
              let height = intValue(sourceMetadata["height"]?.value),
              width > 0, height > 0 else { return [] }
        let pageWidth = Double(width)
        let pageHeight = Double(height)
        return [[
            Double(bbox[0]) / pageWidth,
            Double(bbox[1]) / pageHeight,
            Double(bbox[2]) / pageWidth,
            Double(bbox[3]) / pageHeight
        ]]
    }

    /// Metadata numbers decode as Int, Int64 or Double depending on the JSON
    /// path — a bare `as? Int` silently drops the others.
    private static func intValue(_ raw: Any?) -> Int? {
        switch raw {
        case let int as Int: return int
        case let int64 as Int64: return Int(int64)
        case let double as Double: return Int(double)
        default: return nil
        }
    }
}
