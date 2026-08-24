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
    /// The containment ladder (Daniel, 2026-08-23: "we should only show the
    /// bounding box, but be able to get back to full page by swiping…which
    /// will also bring us up to the full spread"). Fingers-up (step +1) walks
    /// OUT — region → page → spread; fingers-down walks back in. On an entry
    /// the vertical axis IS this ladder; renditions keep the axis on plain
    /// pages.
    private enum LadderLevel: Int { case region = 0, page = 1, spread = 2 }
    @State private var ladderLevel: LadderLevel = .region
    /// The source page's parent — the spread/opening — loaded lazily the
    /// first time the ladder reaches for it. nil while unknown; the ladder
    /// simply stops at .page when the parent has no image of its own.
    @State private var spread: Document?

    var body: some View {
        Group {
            if let source {
                entryLadderCanvas(source: source)
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
            ladderLevel = entry.regionInParent == nil ? .page : .region
            spread = nil
            guard let sourceId = Self.sourceDocumentId(of: entry) else {
                loadFailed = true
                return
            }
            source = try? await documentStore.documentService.getDocument(sourceId)
            if source == nil { loadFailed = true }
        }
    }

    /// The three rungs share ONE canvas type; `.id` keys the rung so a step
    /// re-opens at the rung's own framing (the region rung opens zoomed to
    /// the band, the page rung fitted, the spread rung fitted with the
    /// page's band highlighted when the import recorded one).
    @ViewBuilder
    private func entryLadderCanvas(source: Document) -> some View {
        let region = Self.highlight(for: entry, sourceMetadata: source.metadata)
        switch ladderLevel {
        case .region, .page:
            DocumentCanvas(
                content: .imageStorageDisplay(documentId: source.id),
                onNavigateToDocument: onNavigateToDocument,
                highlightBoxes: region,
                focusRegion: ladderLevel == .region ? region.first : nil,
                onContainmentStep: { step in containmentStep(step, source: source) }
            )
            .id("entry-ladder-\(entry.id)-\(ladderLevel.rawValue)")
        case .spread:
            DocumentCanvas(
                content: .imageStorageDisplay(documentId: spread?.id ?? source.id),
                onNavigateToDocument: onNavigateToDocument,
                // The PAGE's band on the spread, when the import recorded one
                // (the Marshall drop folders stamp part regions) — so the
                // zoom-out keeps pointing at where you came from.
                // Same frame gate: the page's band draws on the spread only
                // when it was measured in the spread's own frame.
                highlightBoxes: spread != nil
                    ? (source.regionInParent.flatMap { $0.isInParentFrame ? [$0.rect] : nil } ?? [])
                    : region,
                onContainmentStep: { step in containmentStep(step, source: source) }
            )
            .id("entry-ladder-\(entry.id)-2")
        }
    }

    /// Walk the ladder. Returns true when the step was consumed — the viewer
    /// falls back to its rendition flip otherwise (never here: an entry's
    /// vertical axis is the ladder end to end).
    private func containmentStep(_ step: Int, source: Document) -> Bool {
        switch (ladderLevel, step > 0) {
        case (.region, true):
            ladderLevel = .page
        case (.page, true):
            guard let parentId = source.parentId else { return true }
            if let spread {
                _ = spread  // already loaded — reuse
                ladderLevel = .spread
                return true
            }
            Task { @MainActor in
                let parent = try? await documentStore.documentService.getDocument(parentId)
                // A parent with no visual of its own (a plain folder) is not
                // a rung — the ladder honestly stops at the page.
                guard let parent, parent.docType != .folder else { return }
                spread = parent
                ladderLevel = .spread
            }
        case (.spread, false):
            ladderLevel = .page
        case (.page, false):
            if entry.regionInParent != nil { ladderLevel = .region }
        case (.region, false), (.spread, true):
            break  // ends of the ladder — a step past them is a no-op
        }
        return true
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
           region.space ?? "normalized" == "normalized",
           // Frame gate (2026-08-23): a region measured on a NAMED rendition
           // is only valid on that rendition's pixels — drawing it on the
           // parent's base image is a plausible band in the wrong place (the
           // misplaced spread-band bug's class). No highlight beats a lie.
           region.isInParentFrame {
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
